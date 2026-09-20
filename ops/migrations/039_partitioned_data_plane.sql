-- UP
-- Versioned, partition-ready durable boundaries for raw market events, candles
-- and reusable alert events.  The default partitions keep ingestion available
-- before an operator creates time-bounded partitions; production maintenance
-- may attach monthly partitions without changing writers.

create table if not exists data_event_registry (
  event_id text primary key check (length(btrim(event_id)) between 1 and 160),
  event_kind text not null check (event_kind in ('market_event_v1','alert_event_v1')),
  first_seen_at timestamptz not null default now()
);

create table if not exists market_events_v1 (
  event_id text not null,
  observed_at timestamptz not null,
  received_at timestamptz not null default now(),
  source text not null check (length(btrim(source)) between 1 and 80),
  symbol text not null check (length(btrim(symbol)) between 1 and 40),
  event_type text not null check (length(btrim(event_type)) between 1 and 80),
  sequence_no bigint,
  authority text not null check (authority in ('authoritative','context','derived','proxy')),
  lineage jsonb not null check (jsonb_typeof(lineage) = 'object' and lineage ? 'source_ref'),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  payload_hash text not null check (payload_hash ~ '^[0-9a-f]{64}$'),
  primary key (event_id, observed_at),
  check (received_at >= observed_at - interval '5 minutes')
) partition by range (observed_at);

create table if not exists market_events_v1_default
  partition of market_events_v1 default;
create index if not exists market_events_v1_symbol_time
  on market_events_v1 (symbol, observed_at desc);
create index if not exists market_events_v1_source_sequence
  on market_events_v1 (source, sequence_no) where sequence_no is not null;
create index if not exists market_events_v1_hash
  on market_events_v1 (payload_hash);

create table if not exists market_candles_v1 (
  source text not null check (length(btrim(source)) between 1 and 80),
  symbol text not null check (length(btrim(symbol)) between 1 and 40),
  interval text not null check (interval in ('1m','3m','5m','15m','30m','1h','2h','4h','8h','12h','1d')),
  open_time timestamptz not null,
  close_time timestamptz not null,
  open double precision not null check (open > 0),
  high double precision not null check (high > 0),
  low double precision not null check (low > 0),
  close double precision not null check (close > 0),
  volume double precision not null check (volume >= 0),
  received_at timestamptz not null default now(),
  lineage jsonb not null check (jsonb_typeof(lineage) = 'object' and lineage ? 'source_ref'),
  payload_hash text not null check (payload_hash ~ '^[0-9a-f]{64}$'),
  primary key (source, symbol, interval, open_time),
  check (close_time > open_time),
  check (high >= greatest(open, close, low) and low <= least(open, close, high))
) partition by range (open_time);

create table if not exists market_candles_v1_default
  partition of market_candles_v1 default;
create index if not exists market_candles_v1_lookup
  on market_candles_v1 (symbol, interval, open_time desc);
create index if not exists market_candles_v1_received
  on market_candles_v1 (received_at desc);

create table if not exists alert_events_v1 (
  event_id text not null,
  project text not null check (length(btrim(project)) between 1 and 80),
  source text not null check (length(btrim(source)) between 1 and 80),
  category text not null check (length(btrim(category)) between 1 and 120),
  severity text not null check (severity in ('info','warning','critical')),
  environment text not null check (environment in ('paper','testnet','live','system')),
  title text not null check (length(title) between 1 and 120),
  body text not null check (length(body) between 1 and 1000),
  created_at timestamptz not null,
  received_at timestamptz not null default now(),
  expires_at timestamptz,
  dedupe_key text not null check (length(btrim(dedupe_key)) between 1 and 160),
  data_classification text not null check (data_classification in ('public','internal','restricted')),
  requires_ack boolean not null default false,
  symbol text,
  timeframe text,
  evidence_refs jsonb not null default '[]'::jsonb check (jsonb_typeof(evidence_refs) = 'array'),
  deep_link text,
  correlation_id text,
  causation_id text,
  attributes jsonb not null default '{}'::jsonb check (jsonb_typeof(attributes) = 'object'),
  payload_hash text not null check (payload_hash ~ '^[0-9a-f]{64}$'),
  route_status text not null check (route_status in ('queued','suppressed','expired')),
  route_reason text not null,
  primary key (event_id, created_at),
  check (expires_at is null or expires_at > created_at)
) partition by range (created_at);

create table if not exists alert_events_v1_default
  partition of alert_events_v1 default;
create index if not exists alert_events_v1_recent
  on alert_events_v1 (created_at desc);
create index if not exists alert_events_v1_project_category
  on alert_events_v1 (project, category, created_at desc);
create index if not exists alert_events_v1_dedupe
  on alert_events_v1 (project, dedupe_key, created_at desc);

alter table mobile_alert_outbox add column if not exists alert_event_id text;
create index if not exists mobile_alert_outbox_alert_event
  on mobile_alert_outbox (alert_event_id) where alert_event_id is not null;

-- DOWN
drop index if exists mobile_alert_outbox_alert_event;
alter table mobile_alert_outbox drop column if exists alert_event_id;
drop table if exists alert_events_v1;
drop table if exists market_candles_v1;
drop table if exists market_events_v1;
drop table if exists data_event_registry;
