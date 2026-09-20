-- UP
-- Operator onboarding: public settings the Cockpit saves and reads back, and a
-- separate phone opt-in for control events.
--
-- operator_public_settings holds values that are public by nature. Today that is
-- only the WalletConnect (Reown) project ID, which the relay receives with every
-- pairing: an identifier, not a credential. A secret never belongs here; secrets
-- stay in runtime.env and the dashboard only learns whether one is configured.
-- The database checks the project ID's shape as well as the API, and every change
-- keeps an audit row with who made it, when, and the value it replaced. It creates
-- no setting.
--
-- mobile_alert_devices.control_events_enabled_at is when a phone opted in to
-- control-event notifications (the paper kill switch engaged or cleared), so
-- opting in never replays earlier events. Null means not opted in, which is every
-- existing phone.

create table if not exists operator_public_settings (
  name text primary key check (name in ('walletconnect_project_id')),
  value text not null check (name <> 'walletconnect_project_id' or value ~ '^[0-9a-fA-F]{32}$'),
  updated_by text not null check (length(btrim(updated_by)) > 0),
  updated_at timestamptz not null default now()
);

create table if not exists operator_public_settings_audit (
  id uuid primary key default gen_random_uuid(),
  name text not null check (name in ('walletconnect_project_id')),
  changed_by text not null check (length(btrim(changed_by)) > 0),
  changed_at timestamptz not null default now(),
  previous text,
  next text
);

create index if not exists idx_operator_public_settings_audit_latest
  on operator_public_settings_audit (name, changed_at desc);

alter table mobile_alert_devices add column if not exists control_events_enabled_at timestamptz;

-- DOWN
alter table mobile_alert_devices drop column if exists control_events_enabled_at;
drop table if exists operator_public_settings_audit;
drop table if exists operator_public_settings;
