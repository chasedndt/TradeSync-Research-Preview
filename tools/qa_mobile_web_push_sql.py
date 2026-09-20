"""Real-SQL acceptance for Web Push delivery and tap acknowledgement, on a THROWAWAY PostgreSQL only.

The database must have ops/sql/schema.sql and every migration through 038 applied (ops/apply_schema.py), and no
mobile outbox rows. The script refuses the compose PostgreSQL port (5432) and a database named tradesync
(tools/qa_mobile_support.py). The delivery and tap sections run inside one transaction that is rolled back at the
end, whatever happens; the race section afterwards commits two rows of its own and deletes them.

No request leaves the process. The push service is a local fake that verifies each VAPID signature and opens each
message with the receiving browser's own private key (tools/qa_web_push_fakes.py); ntfy is a local fake; and any
HTTP client that is not an in-process ASGI client refuses to be built. The VAPID pair, the browsers' keys and the
contact are made in memory for this run, set only in this process's environment, and discarded with it.

Sections: tools/qa_web_push_delivery.py (schema, delivery through the real dispatcher, the budget) and
tools/qa_web_push_tap.py (taps through the deployed guards, and a real race for one token).

    python tools/qa_mobile_web_push_sql.py --dsn postgresql://qa:qa@127.0.0.1:55461/tradesync_qa
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs" / "tradesync_core"))
sys.path.insert(0, str(ROOT / "services" / "state-api"))
sys.path.insert(0, str(ROOT / "services" / "state-api" / "tests"))

# First, so the no-egress guard is installed before anything could build an HTTP client.
from qa_mobile_support import KEY, Pool, Provider, throwaway_connection  # noqa: E402

import httpx  # noqa: E402
from Crypto.PublicKey import ECC  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from app import mobile_alerts as mobile  # noqa: E402
from app import mobile_vapid, mobile_web_push, mobile_web_push_sender  # noqa: E402
from qa_web_push_delivery import budget, delivery_through_the_dispatcher, schema  # noqa: E402
from qa_web_push_fakes import FakePushService  # noqa: E402
from qa_web_push_tap import race, taps  # noqa: E402
from web_push_receiver import b64  # noqa: E402

SUBJECT = "mailto:qa@example.invalid"
ENVIRONMENT = ("MOBILE_ALERTS_CONTROL_KEY", mobile_vapid.PUBLIC_ENV, mobile_vapid.PRIVATE_ENV, mobile_vapid.SUBJECT_ENV)


async def main(dsn: str) -> None:
    conn = await throwaway_connection(dsn)
    server = ECC.generate(curve="P-256")
    public, private = b64(server.public_key().export_key(format="raw")), b64(int(server.d).to_bytes(32, "big"))
    os.environ.update(dict(zip(ENVIRONMENT, (KEY, public, private, SUBJECT))))
    assert mobile_vapid.sender_ready(), mobile_vapid.sender_problem()
    service, provider, pool = FakePushService(public, SUBJECT), Provider(), Pool(conn)
    mobile.publish = provider.publish
    mobile_web_push_sender.post = service.post
    outer = conn.transaction()
    await outer.start()
    try:
        await schema(conn)
        routes = FastAPI()
        mobile_web_push.register(routes, SimpleNamespace(pool=pool))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=routes), base_url="http://qa",
                                     headers={"X-API-Key": KEY}) as client:
            delivered = await delivery_through_the_dispatcher(pool, conn, service, provider, client)
        delivered.update(await budget(pool, conn, service, delivered))
        await taps(pool, conn, delivered)
        print(f"{service.requests} requests to the local push service and {provider.calls} to the local ntfy fake; "
              "no request left the process.")
    finally:
        await outer.rollback()
        await conn.close()
        for name in ENVIRONMENT:
            os.environ.pop(name, None)
        print("Rolled back; nothing kept.")
    await race(dsn)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(main(parser.parse_args().dsn))
