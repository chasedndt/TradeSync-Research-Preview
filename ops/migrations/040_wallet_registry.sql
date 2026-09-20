-- UP
-- Public wallet registry for the operator cockpit.  This table deliberately
-- cannot hold a private key, seed phrase, signature or signing session.  It
-- records only the EVM address TradeSync may read from Hyperliquid and how that
-- address was introduced to the workstation.

create table if not exists wallet_connections (
  id uuid primary key default gen_random_uuid(),
  address text not null unique check (address ~ '^0x[0-9a-f]{40}$'),
  label text not null check (length(btrim(label)) between 1 and 80),
  connector text not null check (connector in ('phantom','browser_wallet','walletconnect','watch_only')),
  status text not null default 'active' check (status in ('active','disconnected')),
  added_by text not null check (length(btrim(added_by)) between 1 and 80),
  added_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  constraint wallet_connections_public_address_only check (length(address) = 42)
);

create index if not exists wallet_connections_status_seen
  on wallet_connections (status, last_seen_at desc);

create table if not exists wallet_connection_events (
  id uuid primary key default gen_random_uuid(),
  wallet_id uuid not null references wallet_connections(id) on delete restrict,
  action text not null check (action in ('added','reconnected','disconnected','renamed')),
  operator text not null check (length(btrim(operator)) between 1 and 80),
  reason text not null check (length(btrim(reason)) between 1 and 240),
  connector text not null check (connector in ('phantom','browser_wallet','walletconnect','watch_only')),
  created_at timestamptz not null default now()
);

create index if not exists wallet_connection_events_wallet_time
  on wallet_connection_events (wallet_id, created_at desc);

-- DOWN
drop table if exists wallet_connection_events;
drop table if exists wallet_connections;
