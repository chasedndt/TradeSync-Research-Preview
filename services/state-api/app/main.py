import os
import re
import json
import math
import uuid
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone
from collections import defaultdict

import asyncpg
import redis.asyncio as redis
import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field
from tradesync_core import normalize_symbol, normalize_venue
from tradesync_core.quarantine import (
    QuarantineError,
    evaluate_submission,
    promotion_blockers,
)
from tradesync_core.state_history import annotate_node, detect_transitions
from tradesync_core.tradingview_webhook import parse_alert
from app.macro_feed import macro_feed
from app.context_feed import context_feed
from tradesync_core.graph_snapshot import SnapshotRejected
from app import background
from app import webhook_source
from app import error_responses
from app.deprecation import apply_deprecation_headers
# Moved to app/execution_flags.py; still read from here by tests and callers.
from app.execution_flags import execution_gate_enabled, paper_mode_enabled  # noqa: F401
from app.graph_projection import (
    available_snapshots,
    current_snapshot,
    neighbours,
    project_snapshot,
    read_snapshot,
    snapshot_directory,
)
from app.integration_pipeline import collect_integration_pipeline
from app import pipeline_feeds
from app.regime_lab import (
    RegimeLabEngine,
    collect_live_feature_results,
)

# --- Logging Setup ---
class DefaultTraceIdFilter(logging.Filter):
    """Supply a safe trace field for dependency and server log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] trace_id=%(trace_id)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
for handler in logging.getLogger().handlers:
    handler.addFilter(DefaultTraceIdFilter())
# httpx logs every request URL at INFO. FRED accepts its API key only as a
# query parameter, so that line would carry the key into the container log.
# Seen once on 2026-09-12 and closed here: no outbound URL is logged at all.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("state-api")

# --- Metrics Storage ---
class MetricsCollector:
    def __init__(self):
        self.request_count = defaultdict(int)  # {(method, path, status): count}
        self.request_latency_sum = defaultdict(float)  # {(method, path): sum_ms}
        self.request_latency_count = defaultdict(int)  # {(method, path): count}
        self.startup_time = time.time()

    def record_request(self, method: str, path: str, status: int, latency_ms: float):
        key = (method, path, status)
        self.request_count[key] += 1
        latency_key = (method, path)
        self.request_latency_sum[latency_key] += latency_ms
        self.request_latency_count[latency_key] += 1

    def to_prometheus(self, db_stats: dict = None) -> str:
        lines = []

        # HTTP request metrics
        lines.append("# HELP http_requests_total Total HTTP requests")
        lines.append("# TYPE http_requests_total counter")
        for (method, path, status), count in self.request_count.items():
            lines.append(f'http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')

        lines.append("# HELP http_request_duration_ms_sum Sum of HTTP request durations in ms")
        lines.append("# TYPE http_request_duration_ms_sum counter")
        for (method, path), total in self.request_latency_sum.items():
            lines.append(f'http_request_duration_ms_sum{{method="{method}",path="{path}"}} {total:.2f}')

        lines.append("# HELP http_request_duration_ms_count Count of HTTP requests for latency")
        lines.append("# TYPE http_request_duration_ms_count counter")
        for (method, path), count in self.request_latency_count.items():
            lines.append(f'http_request_duration_ms_count{{method="{method}",path="{path}"}} {count}')

        # Uptime
        lines.append("# HELP process_uptime_seconds Uptime in seconds")
        lines.append("# TYPE process_uptime_seconds gauge")
        lines.append(f"process_uptime_seconds {time.time() - self.startup_time:.2f}")

        # Database pool stats
        if db_stats:
            lines.append("# HELP db_pool_size Current database pool size")
            lines.append("# TYPE db_pool_size gauge")
            lines.append(f"db_pool_size {db_stats.get('size', 0)}")

            lines.append("# HELP db_pool_free Free connections in pool")
            lines.append("# TYPE db_pool_free gauge")
            lines.append(f"db_pool_free {db_stats.get('free', 0)}")

        return "\n".join(lines) + "\n"

metrics = MetricsCollector()

# --- Trace ID Middleware ---
class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Get or generate trace ID
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())

        # Store in request state for access in endpoints
        request.state.trace_id = trace_id

        # Log request start
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={"trace_id": trace_id}
        )

        # Time the request
        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Request failed: {request.method} {request.url.path} - {str(e)}",
                extra={"trace_id": trace_id}
            )
            metrics.record_request(request.method, request.url.path, 500, latency_ms)
            raise

        latency_ms = (time.time() - start_time) * 1000

        # Record metrics
        metrics.record_request(request.method, request.url.path, response.status_code, latency_ms)

        # Log request completion
        logger.info(
            f"Request completed: {request.method} {request.url.path} {response.status_code} {latency_ms:.2f}ms",
            extra={"trace_id": trace_id}
        )

        # Add trace ID to response headers
        response.headers["X-Trace-Id"] = trace_id

        return response

# --- Config ---
PG_DSN = os.getenv("PG_DSN", "postgresql://tradesync:CHANGE_ME@postgres:5432/tradesync")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
POOL_MIN_SIZE = int(os.getenv("POOL_MIN_SIZE", "5"))
POOL_MAX_SIZE = int(os.getenv("POOL_MAX_SIZE", "20"))
POOL_TIMEOUT = float(os.getenv("POOL_TIMEOUT", "5.0"))
VALID_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "1d"]
regime_lab_engine = RegimeLabEngine()

# --- Global Client ---
redis_client = None

async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    return redis_client

# --- Models ---
class EventResponse(BaseModel):
    id: str
    ts: datetime
    source: str
    kind: str
    symbol: str
    timeframe: str
    payload: Dict[str, Any]

class SignalResponse(BaseModel):
    id: str
    created_at: datetime
    agent: str
    symbol: str
    timeframe: str
    kind: str
    confidence: float
    direction: str = Field(alias="dir")
    features: Dict[str, Any]

class HealthResponse(BaseModel):
    status: str
    postgres: bool
    last_event_ts: Optional[datetime]
    last_signal_ts: Optional[datetime]
    latency_ms: float

class OpportunityResponse(BaseModel):
    id: str
    symbol: str
    timeframe: str
    bias: float
    quality: float
    direction: str = Field(alias="dir")
    status: str
    snapshot_ts: datetime
    # When the opportunity stops being live; status reads expired after it.
    expires_at: Optional[datetime] = None
    links: Dict[str, Any]
    # Phase 3C: Enhanced scoring data
    confluence: Optional[Dict[str, Any]] = None

class DecisionResponse(BaseModel):
    id: str
    opportunity_id: str
    venue: str
    requested: Dict[str, Any]
    risk: Dict[str, Any]
    created_at: datetime

class ExecOrderResponse(BaseModel):
    id: str
    decision_id: str
    venue: str
    status: str
    request: Dict[str, Any]
    response: Dict[str, Any]
    dry_run: bool
    created_at: datetime

class EvidenceResponse(BaseModel):
    opportunity: Optional[OpportunityResponse]
    signals: List[SignalResponse] = []
    events: List[EventResponse] = []
    decisions: List[Dict[str, Any]] = []
    exec_orders: List[Dict[str, Any]] = []

class Position(BaseModel):
    venue: str
    symbol: str
    side: str
    size_usd: float
    entry_price: float
    mark_price: float
    pnl_usd: float
    leverage: float
    timestamp: datetime

class SnapshotResponse(BaseModel):
    latest_event_ts: Optional[datetime]
    latest_signal_ts: Optional[datetime]
    latest_opportunity_ts: Optional[datetime]
    execution_gate: str
    hl_status: str
    hl_circuit: Optional[Dict[str, Any]] = None
    stream_lengths: Dict[str, int] = {}
    ingest_sources: List[Dict[str, Any]] = []

# --- Lifespan & State ---
class AppState:
    pool: asyncpg.Pool = None

state = AppState()

async def _warm_macro_cache() -> None:
    """Populate the macro cache once, at startup, without blocking readiness."""
    try:
        await macro_feed.fetch_headlines()
        logger.info(
            f"Macro cache warmed: {len(macro_feed.cache)} headlines",
            extra={"trace_id": "startup"},
        )
    except Exception as exc:
        logger.warning(
            f"Macro cache warm failed; the feed will be fetched on first read: {exc}",
            extra={"trace_id": "startup"},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        print(f"Connecting to DB pool: min={POOL_MIN_SIZE} max={POOL_MAX_SIZE}")
        try:
            state.pool = await asyncpg.create_pool(
                dsn=PG_DSN,
                min_size=POOL_MIN_SIZE,
                max_size=POOL_MAX_SIZE,
                command_timeout=POOL_TIMEOUT
            )
        except Exception as exc:
            if os.getenv("STATE_API_DEGRADED_START", "false").lower() != "true":
                raise
            state.pool = None
            logger.warning(
                f"Starting without PostgreSQL for bounded read-only/development surfaces: {exc}",
                extra={"trace_id": "startup"},
            )
        # Warm the macro cache behind startup rather than making the first
        # caller pay for it. Three external RSS feeds take ~17s cold, and
        # stale-while-revalidate only helps once there is something to serve;
        # the very first request after a restart would otherwise still block.
        #
        # Deliberately not awaited: the API must come up whether or not a news
        # feed answers, and a failure here is logged, not fatal.
        asyncio.create_task(_warm_macro_cache())

        # Loops the routers registered: the Hermes heartbeat, event reactions,
        # the edition schedule. FastAPI ignores on_event hooks under a lifespan,
        # so they are started here; see app/background.py.
        started = background.start_all()
        print(f"Background loops started: {', '.join(started) or 'none'}")

        yield
    finally:
        # Shutdown
        await background.stop_all()
        await macro_feed.close()
        await context_feed.close()
        if state.pool:
            print("Closing DB pool")
            await state.pool.close()

app = FastAPI(
    title="TradeSync State API",
    version="0.1.0",
    lifespan=lifespan
)

# Add Trace ID Middleware
app.add_middleware(TraceIdMiddleware)
# A 500 answers with a trace id, never the exception's text (app/error_responses.py).
error_responses.install(app)

# --- Endpoints ---

@app.get("/healthz")
async def healthz():
    """Simple liveness probe for k8s/docker."""
    return {"ok": True}

@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Prometheus-compatible metrics endpoint."""
    db_stats = {}
    if state.pool:
        db_stats = {
            "size": state.pool.get_size(),
            "free": state.pool.get_idle_size()
        }

    # Get additional application metrics from database
    app_metrics = {}
    if state.pool:
        try:
            async with state.pool.acquire() as conn:
                # Get counts
                row = await conn.fetchrow("""
                    SELECT
                        (SELECT COUNT(*) FROM events) as events_total,
                        (SELECT COUNT(*) FROM signals) as signals_total,
                        (SELECT COUNT(*) FROM opportunities) as opportunities_total,
                        (SELECT COUNT(*) FROM opportunities WHERE status = 'new') as opportunities_new,
                        (SELECT COUNT(*) FROM decisions) as decisions_total,
                        (SELECT COUNT(*) FROM exec_orders) as exec_orders_total,
                        (SELECT COUNT(*) FROM exec_orders WHERE status = 'placed') as exec_orders_placed
                """)
                if row:
                    app_metrics = dict(row)
        except Exception as e:
            logger.warning(f"Failed to fetch app metrics: {e}", extra={"trace_id": "metrics"})

    # Build Prometheus output
    output = metrics.to_prometheus(db_stats)

    # Add application-specific metrics
    if app_metrics:
        output += "\n# HELP tradesync_events_total Total events in database\n"
        output += "# TYPE tradesync_events_total gauge\n"
        output += f"tradesync_events_total {app_metrics.get('events_total', 0)}\n"

        output += "\n# HELP tradesync_signals_total Total signals in database\n"
        output += "# TYPE tradesync_signals_total gauge\n"
        output += f"tradesync_signals_total {app_metrics.get('signals_total', 0)}\n"

        output += "\n# HELP tradesync_opportunities_total Total opportunities in database\n"
        output += "# TYPE tradesync_opportunities_total gauge\n"
        output += f"tradesync_opportunities_total {app_metrics.get('opportunities_total', 0)}\n"

        output += "\n# HELP tradesync_opportunities_new New opportunities awaiting action\n"
        output += "# TYPE tradesync_opportunities_new gauge\n"
        output += f"tradesync_opportunities_new {app_metrics.get('opportunities_new', 0)}\n"

        output += "\n# HELP tradesync_decisions_total Total decisions made\n"
        output += "# TYPE tradesync_decisions_total gauge\n"
        output += f"tradesync_decisions_total {app_metrics.get('decisions_total', 0)}\n"

        output += "\n# HELP tradesync_exec_orders_total Total execution orders\n"
        output += "# TYPE tradesync_exec_orders_total gauge\n"
        output += f"tradesync_exec_orders_total {app_metrics.get('exec_orders_total', 0)}\n"

        output += "\n# HELP tradesync_exec_orders_placed Successfully placed orders\n"
        output += "# TYPE tradesync_exec_orders_placed gauge\n"
        output += f"tradesync_exec_orders_placed {app_metrics.get('exec_orders_placed', 0)}\n"

    return output

@app.get("/state/health", response_model=HealthResponse)
async def state_health():
    """Aggregated health check with component status and data freshness."""
    if not state.pool:
         raise HTTPException(status_code=503, detail="DB Pool not ready")
    
    t0 = time.time()
    try:
        async with state.pool.acquire() as conn:
            # Check DB + get latest timestamps in one go for efficiency
            row = await conn.fetchrow("""
                SELECT 
                    (SELECT ts FROM events ORDER BY ts DESC LIMIT 1) as last_evt,
                    (SELECT created_at FROM signals ORDER BY created_at DESC LIMIT 1) as last_sig
            """)
            
            latency = (time.time() - t0) * 1000
            
            return HealthResponse(
                status="healthy",
                postgres=True,
                last_event_ts=row['last_evt'] if row else None,
                last_signal_ts=row['last_sig'] if row else None,
                latency_ms=round(latency, 2)
            )
    except Exception as e:
        # Log error in real app
        print(f"Health check failed: {e}")
        return HealthResponse(
            status="degraded",
            postgres=False,
            last_event_ts=None,
            last_signal_ts=None,
            latency_ms=round((time.time() - t0) * 1000, 2)
        )

@app.get("/state/snapshot", response_model=SnapshotResponse)
async def get_state_snapshot():
    """Returns a high-level overview of system status."""
    if not state.pool:
         raise HTTPException(status_code=503, detail="DB Pool not ready")
    
    try:
        r = await get_redis()
        async with state.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    (SELECT ts FROM events ORDER BY ts DESC LIMIT 1) as last_evt,
                    (SELECT created_at FROM signals ORDER BY created_at DESC LIMIT 1) as last_sig,
                    (SELECT snapshot_ts FROM opportunities ORDER BY snapshot_ts DESC LIMIT 1) as last_opp
            """)
            
            # Check execution services health + circuit
            hl_status = "error"
            hl_circuit = None
            ingest_sources = []
            
            async with httpx.AsyncClient() as client:
                
                try:
                    resp = await client.get("http://exec-hl-svc:8004/exec/hl/circuit-status", timeout=1.0)
                    if resp.status_code == 200:
                        hl_circuit = resp.json()
                        hl_status = "ok"
                except Exception:
                    pass
                
                try:
                    resp = await client.get("http://ingest-gateway:8080/ingest/sources", timeout=1.0)
                    if resp.status_code == 200:
                        ingest_sources = resp.json()
                except Exception:
                    pass
            
            # Stream lengths
            stream_lengths = {}
            for s in ["x:events.norm", "x:signals.funding"]:
                try:
                    stream_lengths[s] = await r.xlen(s)
                except Exception:
                    stream_lengths[s] = -1

            return SnapshotResponse(
                latest_event_ts=row['last_evt'] if row else None,
                latest_signal_ts=row['last_sig'] if row else None,
                latest_opportunity_ts=row['last_opp'] if row else None,
                execution_gate=os.getenv("EXECUTION_ENABLED", "false"),
                hl_status=hl_status,
                hl_circuit=hl_circuit,
                stream_lengths=stream_lengths,
                ingest_sources=ingest_sources
            )
    except Exception as e:
        print(f"Snapshot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/state/events/latest", response_model=List[EventResponse])
async def get_latest_events(
    request: Request,
    symbol: str, 
    tf: Optional[str] = None,
    timeframe: str = Query("1m"), 
    kind: str = "market_snapshot", 
    limit: int = Query(20, le=100)
):
    """Fetch latest events for a given symbol/tf/kind."""
    # Logic for tf vs timeframe
    params = request.query_params
    final_tf = timeframe
    if "tf" in params and "timeframe" not in params:
        final_tf = tf
    
    if final_tf not in VALID_TIMEFRAMES:
        final_tf = "1m" # Default back to 1m if invalid variant passed
        
    symbol = normalize_symbol(symbol)

    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, ts, source, kind, symbol, timeframe, payload
                FROM events
                WHERE symbol = $1 AND timeframe = $2 AND kind = $3
                ORDER BY ts DESC
                LIMIT $4
            """, symbol, final_tf, kind, limit)
            
            return [
                {
                    "id": str(r["id"]),
                    "ts": r["ts"],
                    "source": r["source"],
                    "kind": r["kind"],
                    "symbol": r["symbol"],
                    "timeframe": r["timeframe"],
                    "payload":  r["payload"]
                }
                for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/state/signals/latest", response_model=List[SignalResponse])
async def get_latest_signals(
    request: Request,
    symbol: str, 
    tf: Optional[str] = None,
    timeframe: str = Query("1m"), 
    kind: str = "funding_oi_squeeze",
    limit: int = Query(20, le=100)
):
    """Fetch latest signals for a given symbol/tf/kind."""
    params = request.query_params
    final_tf = timeframe
    if "tf" in params and "timeframe" not in params:
        final_tf = tf
    
    if final_tf not in VALID_TIMEFRAMES:
        final_tf = "1m"

    symbol = normalize_symbol(symbol)

    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, created_at, agent, symbol, timeframe, kind, confidence, dir, features
                FROM signals
                WHERE symbol = $1 AND timeframe = $2 AND kind = $3
                ORDER BY created_at DESC
                LIMIT $4
            """, symbol, final_tf, kind, limit)
            
            return [
                {
                    "id": str(r["id"]),
                    "created_at": r["created_at"],
                    "agent": r["agent"],
                    "symbol": r["symbol"],
                    "timeframe": r["timeframe"],
                    "kind": r["kind"],
                    "confidence": r["confidence"],
                    "dir": r["dir"],
                    "features": r["features"]
                }
                for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/state/evidence", response_model=EvidenceResponse)
async def get_evidence(opportunity_id: str):
    """Assembles all evidence for a given opportunity ID."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    try:
        async with state.pool.acquire() as conn:
            # 1. Fetch Opportunity
            opp_row = await conn.fetchrow("SELECT * FROM opportunities WHERE id = $1", opportunity_id)
            if not opp_row:
                return EvidenceResponse(opportunity=None)
            
            opportunity = {
                "id": str(opp_row["id"]),
                "symbol": opp_row["symbol"],
                "timeframe": opp_row["timeframe"],
                "bias": opp_row["bias"],
                "quality": opp_row["quality"],
                "dir": opp_row["dir"],
                "status": opp_row["status"],
                "snapshot_ts": opp_row["snapshot_ts"],
                "links": json.loads(opp_row["links"]) if isinstance(opp_row["links"], str) else opp_row["links"]
            }
            links = opportunity["links"] or {}
            
            # 2. Fetch Signals
            signal_ids = links.get("signal_id")
            signals = []
            if signal_ids:
                if not isinstance(signal_ids, list):
                    signal_ids = [signal_ids]
                sig_rows = await conn.fetch("SELECT * FROM signals WHERE id = ANY($1)", signal_ids)
                signals = [
                    {
                        "id": str(r["id"]), "created_at": r["created_at"], "agent": r["agent"],
                        "symbol": r["symbol"], "timeframe": r["timeframe"], "kind": r["kind"],
                        "confidence": r["confidence"], "dir": r["dir"],
                        "features": json.loads(r["features"]) if isinstance(r["features"], str) else r["features"]
                    } for r in sig_rows
                ]

            # 3. Fetch Events
            event_ids = links.get("event_ids", [])
            events = []
            if event_ids:
                evt_rows = await conn.fetch("SELECT * FROM events WHERE id = ANY($1)", event_ids)
                events = [
                    {
                        "id": str(r["id"]), "ts": r["ts"], "source": r["source"], "kind": r["kind"],
                        "symbol": r["symbol"], "timeframe": r["timeframe"],
                        "payload": json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
                    } for r in evt_rows
                ]

            # 4. Fetch Decisions
            dec_rows = await conn.fetch("SELECT * FROM decisions WHERE opportunity_id = $1", opportunity_id)
            decisions = [
                {
                    "id": str(r["id"]), "venue": r["venue"], 
                    "requested": json.loads(r["requested"]) if isinstance(r["requested"], str) else r["requested"],
                    "risk": json.loads(r["risk"]) if isinstance(r["risk"], str) else r["risk"]
                } for r in dec_rows
            ]

            # 5. Fetch Exec Orders
            decision_ids = [r["id"] for r in dec_rows]
            exec_orders = []
            if decision_ids:
                ord_rows = await conn.fetch("SELECT * FROM exec_orders WHERE decision_id = ANY($1)", decision_ids)
                exec_orders = [
                    {
                        "id": str(r["id"]), "decision_id": str(r["decision_id"]), "venue": r["venue"],
                        "status": r["status"], 
                        "request": json.loads(r["request"]) if isinstance(r["request"], str) else r["request"],
                        "response": json.loads(r["response"]) if isinstance(r["response"], str) else r["response"],
                        "dry_run": r["dry_run"]
                    } for r in ord_rows
                ]

            return EvidenceResponse(
                opportunity=opportunity,
                signals=signals,
                events=events,
                decisions=decisions,
                exec_orders=exec_orders
            )
    except Exception as e:
        print(f"Evidence error: {e}")
        return EvidenceResponse(opportunity=None) # Empty instead of 500

@app.get("/state/positions", response_model=List[Position])
async def get_aggregated_positions(venue: str = "all"):
    """Aggregates positions from execution services."""
    # "all" is this route's own default, so it is settled before the venue is
    # normalised (normalize_venue knows only real venues); an unknown venue is
    # the caller's mistake (400), never a server failure.
    if venue.strip().lower() == "all":
        venue = "all"
    else:
        try:
            venue = normalize_venue(venue)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
    venues = ["hyperliquid"] if venue == "all" else [venue]
    urls = {
        "hyperliquid": "http://exec-hl-svc:8004/exec/hl/positions"
    }
    
    all_positions = []
    async with httpx.AsyncClient() as client:
        tasks = []
        for v in venues:
            if v in urls:
                tasks.append(client.get(urls[v], timeout=2.0))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, httpx.Response) and res.status_code == 200:
                all_positions.extend(res.json())
            else:
                print(f"Failed to fetch positions: {res}")
                
    return all_positions

# --- Market Data Endpoints (Phase 3B) ---

MARKET_DATA_URL = os.getenv("MARKET_DATA_URL", "http://market-data:8005")
# The account to preview. An address is public — it appears in every
# transaction the account has ever made — so this is not a secret and is not
# treated as one. The key that controls it never appears in this service.
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "").strip()
# The venue's public info endpoint. Read-only by construction: it takes an
# address and returns state, and has no authenticated surface at all.
HYPERLIQUID_INFO_URL = os.getenv(
    "HYPERLIQUID_INFO_URL", "https://api.hyperliquid.xyz/info"
)


def _market_data_get(path: str, *, timeout: float = 10.0) -> httpx.Response:
    """Fetch an internal market-data route without blocking the API worker."""

    with httpx.Client(timeout=timeout, trust_env=False) as client:
        return client.get(f"{MARKET_DATA_URL}{path}")


class MarketSnapshotResponse(BaseModel):
    """Market snapshot with truthfulness indicators."""
    venue: str
    symbol: str
    ts: int
    data_age_ms: int
    available_metrics: List[Dict[str, Any]]
    funding: Optional[Dict[str, Any]] = None
    oi: Optional[Dict[str, Any]] = None
    liquidations: Optional[Dict[str, Any]] = None
    volume: Optional[Dict[str, Any]] = None
    orderbook: Optional[Dict[str, Any]] = None
    # Phase 3C: Derived microstructure data
    microstructure: Optional[Dict[str, Any]] = None
    regimes: Dict[str, Any]
    sources: List[Dict[str, Any]] = []

class MarketAlertResponse(BaseModel):
    """Market alert for regime changes."""
    id: str
    venue: str
    symbol: str
    ts: int
    alert_type: str
    metric: str
    previous_value: Optional[str] = None
    new_value: str
    context: Dict[str, Any] = {}

@app.get("/state/market/snapshot", response_model=MarketSnapshotResponse)
async def get_market_snapshot(venue: str, symbol: str):
    """
    Get latest market snapshot for venue/symbol.

    Returns truthful market data with available_metrics[] showing
    REAL/PROXY/UNAVAILABLE status for each metric.
    """
    symbol = normalize_symbol(symbol)
    venue = normalize_venue(venue)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{MARKET_DATA_URL}/snapshot/{venue}/{symbol}",
                timeout=5.0
            )
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"No snapshot for {venue}:{symbol}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            # The status only: the exception's text names market-data's internal address.
            raise HTTPException(status_code=e.response.status_code, detail=f"market-data answered HTTP {e.response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching market snapshot: {e}", extra={"trace_id": "market"})
            raise HTTPException(status_code=503, detail="Market data service unavailable")

@app.get("/state/market/snapshots")
async def get_all_market_snapshots():
    """Get all current market snapshots."""
    try:
        # Keep the internal proxy off the main event loop: the legacy dashboard
        # polls several slower routes concurrently and must not create a false
        # market-data outage.
        resp = await asyncio.to_thread(_market_data_get, "/snapshots")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error fetching market snapshots: {e}", extra={"trace_id": "market"})
        raise HTTPException(status_code=503, detail="Market data service unavailable")

class QuarantineSubmission(BaseModel):
    """One external submission. Nothing here confers authority."""

    source: str
    payload: Dict[str, Any]
    observed_at_ms: Optional[int] = None


@app.post("/state/quarantine", tags=["quarantine"])
async def submit_to_quarantine(submission: QuarantineSubmission):
    """Accept external material for review. This is not admission to anything.

    Tier B connectors submit here. A stored row is untrusted material an
    operator can inspect; it carries no scoring, approval or execution
    authority and cannot become evidence without a deliberate promotion.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    received_ms = int(time.time() * 1000)
    try:
        async with state.pool.acquire() as conn:
            seen = await conn.fetch(
                "SELECT content_digest FROM quarantine_intake WHERE source = $1",
                submission.source,
            )
            verdict = evaluate_submission(
                submission.source,
                submission.payload,
                received_ms,
                observed_at_ms=submission.observed_at_ms,
                seen_digests=[r["content_digest"] for r in seen],
            )
            # Refusals are stored too: "what did that connector try to send"
            # is exactly the question an operator needs answered later.
            await conn.execute(
                """
                INSERT INTO quarantine_intake
                    (source, accepted, content_digest, payload, reasons, observed_at)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb,
                        CASE WHEN $6::bigint IS NULL THEN NULL
                             ELSE to_timestamp($6::bigint / 1000.0) END)
                ON CONFLICT (source, content_digest) DO NOTHING
                """,
                submission.source,
                verdict.accepted,
                verdict.content_digest,
                json.dumps(submission.payload),
                json.dumps(verdict.reasons),
                submission.observed_at_ms,
            )
    except QuarantineError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return verdict.to_dict()


@app.get("/state/quarantine", tags=["quarantine"])
async def list_quarantine(
    source: Optional[str] = None,
    pending_only: bool = False,
    limit: int = Query(50, le=200),
):
    """What connectors have sent, accepted or not, newest first."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT q.id, q.source, q.accepted, q.content_digest, q.payload, q.reasons,
                       q.observed_at, q.received_at, q.reviewed_by, q.reviewed_at, q.promoted_to,
                       x.claims AS rule_claims, x.reason AS rule_reason,
                       h.claims AS harness_claims, h.reason AS harness_reason
                FROM quarantine_intake q
                LEFT JOIN quarantine_extractions x ON x.quarantine_id = q.id
                LEFT JOIN quarantine_harness_extractions h ON h.quarantine_id = q.id
                WHERE ($1::text IS NULL OR q.source = $1)
                  AND ($2::boolean IS FALSE OR q.reviewed_at IS NULL)
                ORDER BY q.received_at DESC
                LIMIT $3
                """,
                source,
                pending_only,
                limit,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "schema_version": "quarantine_v1",
        "authority": "none",
        "items": [
            {
                "id": str(r["id"]),
                "source": r["source"],
                "accepted": r["accepted"],
                "content_digest": r["content_digest"],
                "payload": json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"],
                "reasons": json.loads(r["reasons"]) if isinstance(r["reasons"], str) else r["reasons"],
                "observed_at": r["observed_at"].isoformat() if r["observed_at"] else None,
                "received_at": r["received_at"].isoformat(),
                "reviewed_by": r["reviewed_by"],
                "promoted_to": r["promoted_to"],
                # What extraction made of it: rule pass first, harness pass if asked.
                "extraction": {
                    "rule": None if r["rule_claims"] is None else {"claims": int(r["rule_claims"]), "reason": r["rule_reason"] or ""},
                    "harness": None if r["harness_claims"] is None else {"claims": int(r["harness_claims"]), "reason": r["harness_reason"] or ""},
                },
            }
            for r in rows
        ],
        "note": (
            "Quarantined material is untrusted and confers no authority. "
            "Promotion to admitted evidence is a separate operator act."
        ),
    }


class QuarantineReview(BaseModel):
    """An operator decision on one quarantined item."""

    reviewed_by: str
    promote: bool = False
    target_provenance: str = "context_only"
    note: str = ""


@app.get("/state/execution/wallet-preview", tags=["execution"])
async def get_wallet_preview(address: Optional[str] = None):
    """Account state for the configured address, read-only.

    An address is public: it is in every transaction the account has ever made.
    Reading state for one requires no key and grants nothing, which is why this
    can exist while the signer stays separate.

    What it answers is the question you want answered *before* an order, not
    after: what is actually in the account, what is already open, and how much
    margin is already committed. A preview computed from this system's own
    records would tell you what TradeSync believes; this tells you what the
    venue believes, and the difference between those is the interesting part.
    """
    preview_address = address.strip() if address is not None else WALLET_ADDRESS
    if address is not None and not re.fullmatch(r"0x[0-9a-fA-F]{40}", preview_address):
        raise HTTPException(status_code=422, detail="Expected a public EVM address: 0x followed by 40 hexadecimal characters. Never enter a private key.")
    if not preview_address:
        return {
            "configured": False,
            "address": None,
            "status": "not_configured",
            "detail": "WALLET_ADDRESS is unset; no account is being previewed",
            "authority": "read_only",
        }

    try:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            response = await client.post(
                HYPERLIQUID_INFO_URL,
                json={"type": "clearinghouseState", "user": preview_address},
            )
            response.raise_for_status()
            state_payload = response.json()
    except Exception:
        raise HTTPException(status_code=503, detail="Venue account read unavailable")

    if not isinstance(state_payload, dict) or not isinstance(state_payload.get("marginSummary"), dict) or not isinstance(state_payload.get("assetPositions"), list):
        raise HTTPException(status_code=503, detail="Venue account response is incomplete; no balance is inferred")
    margin = state_payload["marginSummary"]
    positions = []
    for entry in state_payload.get("assetPositions") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("position"), dict):
            raise HTTPException(status_code=503, detail="Venue position response malformed")
        position = entry.get("position") or {}
        size = _as_float(position.get("szi"))
        if size is None or not math.isfinite(size):
            raise HTTPException(status_code=503, detail="Venue position size unavailable")
        if size == 0:
            continue
        positions.append({
            "symbol": f"{position.get('coin')}-PERP",
            "size": size,
            # szi is signed; the sign is the side. Reporting it separately means
            # nobody downstream has to rediscover that convention.
            "side": "LONG" if size > 0 else "SHORT",
            "entry_price": _as_float(position.get("entryPx")),
            "unrealized_pnl": _as_float(position.get("unrealizedPnl")),
            "position_value": _as_float(position.get("positionValue")),
            "leverage": (position.get("leverage") or {}).get("value"),
            "liquidation_price": _as_float(position.get("liquidationPx")),
        })

    account_value = _as_float(margin.get("accountValue"))
    total_margin_used = _as_float(margin.get("totalMarginUsed"))
    if account_value is None or total_margin_used is None or not math.isfinite(account_value) or not math.isfinite(total_margin_used):
        raise HTTPException(status_code=503, detail="Venue balance fields are unavailable; no balance is inferred")

    return {
        "configured": True,
        "address": preview_address,
        "lookup_mode": "session_watch_only" if address is not None else "configured_watch_only",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "network": "testnet" if "testnet" in HYPERLIQUID_INFO_URL else "mainnet",
        "account_value_usd": account_value,
        "withdrawable_usd": _as_float(state_payload.get("withdrawable")),
        "total_margin_used_usd": total_margin_used,
        # The number that matters when deciding whether another position is
        # sane. Reported rather than left for a reader to divide.
        "margin_utilization": round(total_margin_used / account_value, 4)
        if account_value > 0
        else None,
        "open_positions": positions,
        "position_count": len(positions),
        "source": "hyperliquid clearinghouseState",
        "authority": "read_only",
        "note": (
            "Read from a public address. No key is involved and nothing here "
            "authorises anything; the signer is a separate process."
        ),
    }


def _as_float(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


@app.get("/state/execution/wallet-activity", tags=["execution"])
async def get_wallet_activity(address: str):
    from .wallet_activity import read_activity
    address = address.strip()
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
        raise HTTPException(status_code=422, detail="Expected a public EVM address; never enter a private key")
    return await read_activity(HYPERLIQUID_INFO_URL, address)


@app.post("/state/quarantine/{item_id}/review", tags=["quarantine"])
async def review_quarantine_item(item_id: str, review: QuarantineReview):
    """Record an operator decision on quarantined material.

    Promotion is an operator act and stays one. This endpoint records the
    decision and the blockers that applied; it does not itself grant a
    quarantined item any scoring or execution authority.
    """
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    if not review.reviewed_by.strip():
        raise HTTPException(status_code=400, detail="reviewed_by is required")

    try:
        async with state.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, accepted, promoted_to FROM quarantine_intake WHERE id = $1::uuid",
                item_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="quarantine item not found")

            blockers = promotion_blockers(
                row["accepted"], review.reviewed_by, review.target_provenance
            )
            promoted = review.promote and not blockers
            await conn.execute(
                """
                UPDATE quarantine_intake
                SET reviewed_by = $2, reviewed_at = now(),
                    promoted_to = CASE WHEN $3 THEN $4 ELSE promoted_to END
                WHERE id = $1::uuid
                """,
                item_id,
                review.reviewed_by,
                promoted,
                review.target_provenance if promoted else None,
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "schema_version": "quarantine_v1",
        "id": item_id,
        "reviewed_by": review.reviewed_by,
        "promoted": promoted,
        "blockers": blockers,
        "authority": "none",
        "note": (
            "Review is recorded. Promotion marks an item as admitted context; "
            "it never grants scoring, approval or execution authority."
        ),
    }


TRADINGVIEW_WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "").strip()


@app.post("/webhook/tradingview", tags=["quarantine"])
async def tradingview_webhook(request: Request):
    """Receive a TradingView (including Strike Zone Pine) alert.

    The alert lands in quarantine as untrusted material. It is never a signal,
    and nothing here can approve or execute.

    Disabled unless TRADINGVIEW_WEBHOOK_SECRET is set: an unauthenticated public
    endpoint into a trading system is not an acceptable default. TradingView
    cannot send custom headers, so the secret travels in the alert body.
    """
    # The source first: a sender that is not TradingView learns nothing about
    # this endpoint's configuration (L2, app/webhook_source.py).
    refused = await webhook_source.refusal(request)
    if refused is not None:
        return refused
    if not TRADINGVIEW_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "webhook disabled: set TRADINGVIEW_WEBHOOK_SECRET before "
                "exposing this endpoint"
            ),
        )
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")

    body = await request.body()
    alert = parse_alert(body, TRADINGVIEW_WEBHOOK_SECRET)

    # An unauthenticated alert is refused without touching the database, so a
    # flood of bad secrets cannot fill the intake table.
    if not alert.authenticated:
        logger.warning(
            f"tradingview alert refused: {[r['code'] for r in alert.reasons]}",
            extra={"trace_id": "webhook"},
        )
        return JSONResponse(
            status_code=401,
            content={
                "accepted": False,
                "reasons": alert.reasons,
                "authority": "none",
            },
        )

    submission = alert.to_submission()
    received_ms = int(time.time() * 1000)
    try:
        async with state.pool.acquire() as conn:
            seen = await conn.fetch(
                "SELECT content_digest FROM quarantine_intake WHERE source = 'tradingview'"
            )
            verdict = evaluate_submission(
                "tradingview",
                submission,
                received_ms,
                seen_digests=[r["content_digest"] for r in seen],
            )
            await conn.execute(
                """
                INSERT INTO quarantine_intake
                    (source, accepted, content_digest, payload, reasons)
                VALUES ('tradingview', $1, $2, $3::jsonb, $4::jsonb)
                ON CONFLICT (source, content_digest) DO NOTHING
                """,
                verdict.accepted,
                verdict.content_digest,
                json.dumps(submission),
                json.dumps(verdict.reasons),
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return verdict.to_dict()


@app.get("/state/market/candles")
async def get_market_candles(
    venue: str = "hyperliquid",
    symbol: str = "BTC-PERP",
    interval: str = "15m",
    limit: int = Query(300, ge=1, le=1000),
    start_ms: int | None = Query(None, ge=0),
    end_ms: int | None = Query(None, ge=0),
):
    """Proxy venue OHLCV candles for the Market Canvas.

    Display only. Candles are not catalog features and carry no scoring
    authority; the upstream response states that explicitly.
    """
    from urllib.parse import quote, urlencode
    if start_ms is not None and end_ms is not None and start_ms >= end_ms:
        raise HTTPException(status_code=400, detail="start_ms must be before end_ms")
    params = {"interval": interval, "limit": limit}
    if start_ms is not None:
        params["start_ms"] = start_ms
    if end_ms is not None:
        params["end_ms"] = end_ms
    path = f"/candles/{quote(venue, safe='')}/{quote(symbol, safe='')}?{urlencode(params)}"
    try:
        resp = await asyncio.to_thread(_market_data_get, path)
    except Exception as e:
        logger.error(f"Error fetching candles: {e}", extra={"trace_id": "market"})
        raise HTTPException(status_code=503, detail="Market data service unavailable")

    if resp.status_code == 400:
        raise HTTPException(status_code=400, detail=resp.json().get("detail", "invalid request"))
    if resp.status_code == 404:
        # Hyperliquid is the only venue this system carries. Asking for another
        # is a client error and says so; it is not a fault in market-data.
        raise HTTPException(
            status_code=404,
            detail=resp.json().get("error", "unsupported venue or symbol"),
        )
    if resp.status_code >= 500 or resp.status_code == 503:
        raise HTTPException(status_code=503, detail="Market data service unavailable")
    resp.raise_for_status()
    return resp.json()


@app.get("/state/market/context")
async def get_market_context(
    venue: str = "hyperliquid",
    symbol: str = "BTC-PERP",
    interval: str = "15m",
    limit: int = Query(300, le=1000),
):
    """Funding and open interest bucketed onto the canvas candle boundaries.

    The two series have different reaches and the response keeps them apart
    rather than blending them: funding is the venue's own hourly record and
    covers the whole chart, open interest is our rolling 24-hour recording
    because Hyperliquid publishes only the current value. Each carries a
    coverage block so the pane can state where its data actually stops.

    Display only, like candles. Neither series gains scoring authority here.
    """
    path = f"/context/{venue}/{symbol}?interval={interval}&limit={limit}"
    try:
        resp = await asyncio.to_thread(_market_data_get, path)
    except Exception as e:
        logger.error(f"Error fetching canvas context: {e}", extra={"trace_id": "market"})
        raise HTTPException(status_code=503, detail="Market data service unavailable")

    if resp.status_code == 400:
        raise HTTPException(
            status_code=400, detail=resp.json().get("detail", "invalid request")
        )
    if resp.status_code == 404:
        # Hyperliquid is the only venue this system carries. Asking for another
        # is a client error and says so; it is not a fault in market-data.
        raise HTTPException(
            status_code=404,
            detail=resp.json().get("error", "unsupported venue or symbol"),
        )
    if resp.status_code >= 500 or resp.status_code == 503:
        raise HTTPException(status_code=503, detail="Market data service unavailable")
    resp.raise_for_status()
    return resp.json()


@app.get("/state/market/depth")
async def get_market_depth(
    venue: str = "hyperliquid",
    symbol: str = "BTC-PERP",
):
    """The current L2 book as a cumulative ladder.

    A single poll rather than a series: the book is replaced wholesale each
    time, so there is nothing to draw across past candles. A book the venue did
    not return is a 503, never an empty ladder that would render as a market
    with no resting size.
    """
    path = f"/depth/{venue}/{symbol}"
    try:
        resp = await asyncio.to_thread(_market_data_get, path)
    except Exception as e:
        logger.error(f"Error fetching depth: {e}", extra={"trace_id": "market"})
        raise HTTPException(status_code=503, detail="Market data service unavailable")

    if resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=resp.json().get("error", "unsupported venue or symbol"),
        )
    if resp.status_code >= 500 or resp.status_code == 503:
        raise HTTPException(status_code=503, detail="Order book unavailable")
    resp.raise_for_status()
    return resp.json()


@app.get("/state/market/book-history")
async def get_market_book_history(symbol: str = "BTC-PERP"):
    if not re.fullmatch(r"[A-Z0-9]{1,20}-PERP", symbol):
        raise HTTPException(status_code=400, detail="Invalid symbol")
    try:
        resp = await asyncio.to_thread(_market_data_get, f"/book-history/{symbol}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Unsupported symbol")
        resp.raise_for_status()
        return resp.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Order-book history unavailable")


@app.get("/state/market/liquidation-context")
async def get_market_liquidation_context(symbol: str = "BTC-PERP"):
    if not re.fullmatch(r"[A-Z0-9]{1,20}-PERP", symbol):
        raise HTTPException(status_code=400, detail="Invalid symbol")
    try:
        resp = await asyncio.to_thread(_market_data_get, f"/liquidation-context/{symbol}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Unsupported symbol")
        resp.raise_for_status()
        return resp.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Liquidation context unavailable")


@app.get("/state/market/timeseries")
async def get_market_timeseries(
    venue: str,
    symbol: str,
    metric: str = "funding",
    window: str = "1h"
):
    """
    Get rolling timeseries data for a metric.

    Useful for sparklines and charts.
    """
    symbol = normalize_symbol(symbol)
    venue = normalize_venue(venue)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{MARKET_DATA_URL}/timeseries/{venue}/{symbol}/{metric}",
                params={"window": window},
                timeout=5.0
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error fetching market timeseries: {e}", extra={"trace_id": "market"})
            raise HTTPException(status_code=503, detail="Market data service unavailable")

@app.get("/state/market/alerts", response_model=List[MarketAlertResponse])
async def get_market_alerts(limit: int = 50):
    """
    Get recent market alerts (regime changes, extreme values).

    These appear in the /logs page.
    """
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{MARKET_DATA_URL}/alerts",
                params={"limit": limit},
                timeout=5.0
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("alerts", [])
        except Exception as e:
            logger.error(f"Error fetching market alerts: {e}", extra={"trace_id": "market"})
            raise HTTPException(status_code=503, detail="Market data service unavailable")

@app.get("/state/market/status")
async def get_market_data_status():
    """Get status of market data service and providers."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{MARKET_DATA_URL}/status", timeout=5.0)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error fetching market status: {e}", extra={"trace_id": "market"})
            ref = error_responses.reference(e, "market status")
            return {
                "status": "unavailable",
                # The type and a log reference, never the text: an httpx error names the internal address (L4).
                "error": f"market-data did not answer ({type(e).__name__}); log reference {ref}",
                "providers": []
            }


async def _record_and_annotate_states(status: dict) -> dict:
    """Persist state changes and attach how long each stage has held its state.

    Failures here are logged and swallowed: state ageing is operator context,
    and losing it must never take down the pipeline view itself.
    """
    nodes = status.get("nodes") or []
    if not state.pool or not nodes:
        return status

    now_s = int(time.time())
    observed = {node["id"]: node["status"] for node in nodes}

    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (node_id) node_id, new_state, entered_at
                FROM node_state_history
                ORDER BY node_id, entered_at DESC
                """
            )
            last_known = {r["node_id"]: r["new_state"] for r in rows}
            entered = {
                r["node_id"]: int(r["entered_at"].timestamp()) for r in rows
            }

            transitions = detect_transitions(observed, last_known, now_s)
            for transition in transitions:
                await conn.execute(
                    """
                    INSERT INTO node_state_history (node_id, previous_state, new_state)
                    VALUES ($1, $2, $3)
                    """,
                    transition.node_id,
                    transition.previous_state,
                    transition.new_state,
                )
                entered[transition.node_id] = transition.at_epoch_s

            # Recent changes per node, for flap detection.
            recent = await conn.fetch(
                """
                SELECT node_id, entered_at FROM node_state_history
                WHERE entered_at > now() - interval '15 minutes'
                """
            )
    except Exception as exc:
        logger.warning(f"state history unavailable: {exc}", extra={"trace_id": "pipeline"})
        return status

    by_node: dict[str, list] = {}
    for row in recent:
        by_node.setdefault(row["node_id"], []).append(
            {"at_epoch_s": int(row["entered_at"].timestamp())}
        )

    status["nodes"] = [
        annotate_node(
            node,
            entered.get(node["id"]),
            now_s,
            by_node.get(node["id"], []),
        )
        for node in nodes
    ]
    return status


@app.get("/state/integration-pipeline", tags=["pipeline"])
async def get_integration_pipeline():
    """Return live Tier A probes and honest optional-connector boundaries."""

    status, feeds = await asyncio.gather(
        collect_integration_pipeline(
            pool=state.pool,
            redis_client=await get_redis(),
            market_data_url=MARKET_DATA_URL,
            catalog_feature_count=len(regime_lab_engine.catalog.features),
        ),
        pipeline_feeds.collect(MARKET_DATA_URL),
    )
    # Feed heartbeats sit beside the stages as transport evidence; they change no node or readiness.
    status["feeds"] = feeds
    return await _record_and_annotate_states(status)


@app.get("/state/integration-pipeline/history", tags=["pipeline"])
async def get_pipeline_state_history(node_id: Optional[str] = None, limit: int = Query(50, le=200)):
    """Recent state transitions, newest first."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT node_id, previous_state, new_state, entered_at
                FROM node_state_history
                WHERE ($1::text IS NULL OR node_id = $1)
                ORDER BY entered_at DESC
                LIMIT $2
                """,
                node_id,
                limit,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "schema_version": "node_state_history_v1",
        "transitions": [
            {
                "node_id": r["node_id"],
                "previous_state": r["previous_state"],
                "new_state": r["new_state"],
                "entered_at": r["entered_at"].isoformat(),
            }
            for r in rows
        ],
    }

# --- Private paper-only Regime Lab ---

async def _regime_lab_evidence(venue: str, symbol: str):
    normalized_venue = normalize_venue(venue)
    normalized_symbol = normalize_symbol(symbol)
    return await collect_live_feature_results(
        regime_lab_engine,
        MARKET_DATA_URL,
        normalized_venue,
        normalized_symbol,
    )


# --- Legacy Aliases (Step 0 Compat) ---

@app.get("/opps", response_model=List[OpportunityResponse], tags=["legacy"])
async def get_opportunities_alias(
    response: Response,
    symbol: Optional[str] = None, 
    status: str = "new", 
    limit: int = Query(20, le=100)
):
    apply_deprecation_headers(response, "/state/opportunities")
    return await get_opportunities(symbol=symbol, status=status, limit=limit)

@app.get("/opps/{opportunity_id}", response_model=EvidenceResponse, tags=["legacy"])
async def get_opportunity_by_id_alias(response: Response, opportunity_id: str):
    apply_deprecation_headers(response, f"/state/evidence?opportunity_id={opportunity_id}")
    return await get_evidence(opportunity_id=opportunity_id)



# Paper rehearsal: preview, refuse, journal, with the execution gate shut.
# Registered last so it sees the same pool the rest of the app uses. It has no
# path to an execution service; see app/rehearsal.py.
from app.rehearsal import register as register_rehearsal  # noqa: E402

register_rehearsal(app, state)

# The skill gate measured the corrected way; see app/skill_gate.py.
from app.skill_gate import register as register_skill_gate  # noqa: E402

register_skill_gate(app, state)

# Evidence cards: what each candidate feature has earned; see app/evidence_cards.py.
from app.evidence_cards import register as register_evidence_cards  # noqa: E402

register_evidence_cards(app, state)

# Source cards: what each external source has earned; see app/source_cards.py.
from app.source_cards import register as register_source_cards  # noqa: E402

register_source_cards(app, state)

# The Thesis page's read model: the SOP's minimum valid thesis from evidence.
from app.thesis import register as register_thesis  # noqa: E402

register_thesis(
    app,
    state,
    market_data_url=MARKET_DATA_URL,
    calendar=lambda: context_feed.fetch_overview(force_refresh=False),
    evidence=_regime_lab_evidence,
)

# The Hermes fleet read model and directives; fed by the host bridge. See app/fleet.py.
from app.fleet import register as register_fleet  # noqa: E402

register_fleet(app, state)

# Each Hermes job's run progress and stored output for the Fleet page; see app/fleet_activity.py.
from app.fleet_activity import register as register_fleet_activity  # noqa: E402

register_fleet_activity(app, state)

# The Hermes link: a continuous heartbeat on the gateway; see app/hermes_link.py.
from app import hermes_link  # noqa: E402


@app.get("/state/hermes/status", tags=["agents"])
async def get_hermes_status():
    """Hermes gateway link as of the last heartbeat, plus the gateway's own state file."""
    return {
        **hermes_link.status_now(),
        "gateway": await hermes_link.gateway_state(state.pool),
        "boundary": {"may_explain": True, "may_compare": True, "may_read_posts_for_claims": True,
                     "may_score": False, "may_approve": False, "may_execute": False},
    }


background.add("hermes_link", hermes_link.run_forever)

# The agent harness kill switch: the Cockpit's switch, the host control queue, the audit and the ask
# route's gate; see app/harness_control_routes.py.
from app.harness_control_routes import register as register_harness_control  # noqa: E402

register_harness_control(app, state)


# Measured event reactions and recent coverage; see app/event_outlook.py.
from app.event_outlook import register as register_outlook  # noqa: E402

register_outlook(
    app,
    state,
    market_data_url=MARKET_DATA_URL,
    calendar=lambda: context_feed.fetch_overview(force_refresh=False),
)

# Thesis editions: the thesis for every symbol, frozen on the StrikeZone cadence.
from app.editions import register as register_editions  # noqa: E402

register_editions(
    app,
    state,
    market_data_url=MARKET_DATA_URL,
    calendar=lambda: context_feed.fetch_overview(force_refresh=False),
    evidence=_regime_lab_evidence,
)

# The StrikeZone quant lab: forward-test ledger, outcomes, scorecards, health and
# charts, posted by the host bridge; see app/strikezone_ingest.py and strikezone_lab.py.
from app.strikezone_ingest import register as register_strikezone_ingest  # noqa: E402
from app.strikezone_lab import register as register_strikezone_lab  # noqa: E402

register_strikezone_ingest(app, state)
register_strikezone_lab(app, state)

from app.trade_research import register as register_trade_research  # noqa: E402
register_trade_research(app, state, market_data_url=MARKET_DATA_URL)

# The timeframe outlook: three days to six months, from daily candles; see app/horizons.py.
from app.horizons import register as register_horizons  # noqa: E402

register_horizons(app, state, market_data_url=MARKET_DATA_URL)

# Keeps the warm markets' timeframe measurements fresh; see app/horizons_warm.py.
from app.horizons_warm import register as register_horizons_warm  # noqa: E402

register_horizons_warm(market_data_url=MARKET_DATA_URL)

# Hermes readings of the timeframe outlook on an operator's daily schedule, off by default; see app/reading_schedule.py.
from app.reading_schedule import register as register_reading_schedule  # noqa: E402

register_reading_schedule(app, state, market_data_url=MARKET_DATA_URL)

# Feature histories for the per-feature charts on Regime Lab; see app/feature_history.py.
from app.feature_history import register as register_feature_history  # noqa: E402

register_feature_history(app, state, market_data_url=MARKET_DATA_URL)

from app.market_recorder import register as register_market_recorder  # noqa: E402

register_market_recorder(app, state, market_data_url=MARKET_DATA_URL)

from app.liquidity import register as register_liquidity  # noqa: E402

register_liquidity(app, state, market_data_url=MARKET_DATA_URL)

from app.mobile_alerts import register as register_mobile_alerts  # noqa: E402
register_mobile_alerts(app, state)

from app.managed_paper import register as register_managed_paper  # noqa: E402
register_managed_paper(app, state, market_data_url=MARKET_DATA_URL)

# Immutable research-trial registration and forward evaluation. See app/research_trials.py.
from app.research_trials import register as register_research_trials  # noqa: E402
register_research_trials(app, state, market_data_url=MARKET_DATA_URL)

# The paper risk engine: account, limits, kill switch and restart reconciliation; see app/paper_risk_routes.py.
from app.paper_risk_routes import register as register_paper_risk  # noqa: E402
register_paper_risk(app, state, market_data_url=MARKET_DATA_URL)

# Market Canvas drawings, versioned server-side; see app/canvas_drawings.py.
from app.canvas_drawings import register as register_canvas_drawings  # noqa: E402

register_canvas_drawings(app, state)

# The Regime Lab's overview and draft experiments; see app/regime_lab_routes.py.
from app.regime_lab_routes import register as register_regime_lab  # noqa: E402

register_regime_lab(app, state, engine=regime_lab_engine, evidence=_regime_lab_evidence)

# Fixed-window replay of stored decisions under a challenger; see app/regime_replay.py.
from app.regime_replay import register as register_regime_replay  # noqa: E402

register_regime_replay(app, state, engine=regime_lab_engine)

# The opportunities list, moved to app/opportunities_routes.py; the /opps alias
# above calls the handler returned here.
from app.opportunities_routes import register as register_opportunities  # noqa: E402

get_opportunities = register_opportunities(app, state, OpportunityResponse)

# Opportunity learning: attributions, verdicts, walk-forward proposals and the
# operator's adopt/reject/revert; see app/learning_routes.py.
from app.learning_routes import register as register_learning  # noqa: E402

register_learning(app, state, regime_lab_engine.baseline)

# The declared entry-evidence comparisons; research reading only. See app/entry_evidence_comparison.py.
from app.entry_evidence_comparison import register as register_entry_evidence_comparison  # noqa: E402
register_entry_evidence_comparison(app, state)

# Evidence combination by measured likelihood ratios; research reading only. See app/evidence_combination.py.
from app.evidence_combination import register as register_evidence_combination  # noqa: E402

register_evidence_combination(app, state)

# Public operator settings (the WalletConnect project ID), audited per change; see app/public_settings.py.
from app.public_settings import register as register_public_settings  # noqa: E402

register_public_settings(app, state)

# Audited public-address wallet registry. It stores no key, phrase, signature or
# session and grants no execution authority; see app/wallet_registry.py.
from app.wallet_registry import register as register_wallet_registry  # noqa: E402

register_wallet_registry(app, state)

# TradingView alert setup for Knowledge intake: webhook URL, message template, whether the secret is configured
# (never its value) and the latest receipts; see app/tradingview_setup.py.
from app.tradingview_setup import register as register_tradingview_setup  # noqa: E402

register_tradingview_setup(app, state)

# The ChaseOS knowledge-graph projection, moved to app/graph_routes.py.
from app.graph_routes import register as register_graph  # noqa: E402

register_graph(app, state)

# Macro headlines and the secondary context feeds; see app/feed_routes.py.
from app.feed_routes import register as register_feeds  # noqa: E402

register_feeds(app, state)

# Outcomes by regime, the evidence timeline, the summary and refusal history;
# see app/outcome_routes.py.
from app.outcome_routes import register as register_outcomes  # noqa: E402

register_outcomes(app, state)

# The advisory harness: status, and asking it a question; see app/harness_routes.py.
from app.harness_routes import register as register_harness  # noqa: E402

register_harness(app, state)

# The other five reconciliation views, beside the execution reconciliation
# (app/execution_reconciliation_routes.py): orphaned events, duplicate candidates, stale approvals, partial orders
# and missing outcomes. Read-only; see app/reconciliation_routes.py.
from app.reconciliation_routes import register as register_reconciliation_views  # noqa: E402

register_reconciliation_views(app, state)

# The bounded audit export of decisions, approvals, orders and outcomes, as JSON
# and CSV; see app/audit_export_routes.py.
from app.audit_export_routes import register as register_audit_export  # noqa: E402

register_audit_export(app, state)

# Thesis adherence and regime fit, measured from evidence frozen at entry;
# see app/outcome_metrics.py.
from app.outcome_metrics import register as register_outcome_metrics  # noqa: E402

register_outcome_metrics(app, state)

# The regime summary for one market: the condition, the evidence behind it, what
# disagrees and why confidence is not higher; see app/regime_summary_routes.py.
from app.regime_summary_routes import register as register_regime_summary  # noqa: E402

register_regime_summary(app, state, market_data_url=MARKET_DATA_URL)

# Opportunity briefs: side, regime fit, entry conditions, plan, evidence, provenance and paper
# state, each read from stored records; see app/opportunity_brief_routes.py.
from app.opportunity_brief_routes import register as register_opportunity_briefs  # noqa: E402

register_opportunity_briefs(app, state)

# How long each record is kept, read from the code that deletes it; see app/operator_retention_routes.py.
from app.operator_retention_routes import register as register_operator_retention  # noqa: E402

register_operator_retention(app, state)

# The mobile delivery ledger and acknowledgements; see app/mobile_ledger.py and app/mobile_delivery.py.
from app.mobile_ledger import register as register_mobile_ledger  # noqa: E402

register_mobile_ledger(app, state)

# Browser (Web Push) subscriptions; see app/mobile_web_push.py. Sending is app/mobile_web_push_sender.py.
from app.mobile_web_push import register as register_mobile_web_push  # noqa: E402

register_mobile_web_push(app, state)

# A tapped notification records that it was seen, with its single-use token; see app/mobile_tap_ack.py.
from app.mobile_tap_ack import register as register_mobile_tap_ack  # noqa: E402

register_mobile_tap_ack(app, state)


# The execution chain's route groups, moved out of this file unchanged: preview,
# execute, risk limits, the execution status reads, execution reconciliation, the
# Strike Zone candidate route and the ChaseOS Gate. Each module says what it holds.
from app.preview_routes import register as register_preview  # noqa: E402

register_preview(app, state, market_data_url=MARKET_DATA_URL)

from app.execute_routes import register as register_execute  # noqa: E402

register_execute(app, state)

from app.risk_limit_routes import register as register_risk_limits  # noqa: E402

register_risk_limits(app, state)

from app.execution_status_routes import register as register_execution_status  # noqa: E402

register_execution_status(app, state)

from app.execution_reconciliation_routes import register as register_execution_reconciliation  # noqa: E402

register_execution_reconciliation(app, state)

from app.candidate_routes import register as register_candidates  # noqa: E402

extract_trade_candidate = register_candidates(app, state)

from app.knowledge_gate_routes import register as register_knowledge_gate  # noqa: E402

register_knowledge_gate(app, state, extract_trade_candidate=extract_trade_candidate)
