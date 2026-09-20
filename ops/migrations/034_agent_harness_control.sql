-- UP
-- The agent harness kill switch: what the operator asked for, what the host control process did
-- about it, and an append-only audit of both (state-api harness_control_store).
--
-- agent_harness_control is one row. desired_state is enforced by TradeSync at once: while it is
-- 'stopped', every TradeSync caller of Hermes refuses. Each request issues a new command_id; the
-- host control process on Windows claims it before running anything, stops or starts the Hermes
-- gateway, and reports the command, its exit status and `systemctl --user is-active` afterwards.
-- Seeded 'running' with no command, so installing this changes nothing and gives the host control
-- process nothing to apply.
--
-- agent_harness_control_events keeps every request, claim and result. An update or delete is
-- refused, so the record of who stopped Hermes, when and why cannot be rewritten, and each command
-- has at most one request, one claim and one result.

create table if not exists agent_harness_control (
  singleton boolean primary key default true check (singleton),
  desired_state text not null default 'running' check (desired_state in ('running', 'stopped')),
  operator text not null default 'migration 034' check (char_length(btrim(operator)) between 1 and 80),
  reason text not null default 'Agent harness kill switch installed; the gateway is left as it was'
    check (char_length(btrim(reason)) between 5 and 240),
  requested_at timestamptz not null default clock_timestamp(),
  command_id uuid,
  claimed_command_id uuid,
  claimed_at timestamptz,
  result_command_id uuid,
  result_status text check (result_status in ('applied', 'failed')),
  result_command text,
  result_exit_status integer,
  result_is_active text,
  result_detail text,
  result_at timestamptz,
  check ((claimed_command_id is null) = (claimed_at is null)),
  check ((result_command_id is null) = (result_status is null) and (result_status is null) = (result_at is null))
);

insert into agent_harness_control (singleton) values (true) on conflict (singleton) do nothing;

create table if not exists agent_harness_control_events (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default clock_timestamp(),
  kind text not null check (kind in ('requested', 'applying', 'applied', 'failed')),
  command_id uuid not null,
  desired_state text not null check (desired_state in ('running', 'stopped')),
  previous_state text check (previous_state in ('running', 'stopped')),
  operator text check (operator is null or char_length(btrim(operator)) between 1 and 80),
  reason text check (reason is null or char_length(btrim(reason)) between 5 and 240),
  command text,
  exit_status integer,
  is_active text,
  detail text,
  check (kind <> 'requested' or (operator is not null and reason is not null and previous_state is not null))
);

create index if not exists idx_agent_harness_control_events_latest
  on agent_harness_control_events (created_at desc);

-- One request, one claim and one result per command; applied and failed are the same result.
create unique index if not exists idx_agent_harness_control_events_once
  on agent_harness_control_events (command_id, (case when kind = 'failed' then 'applied' else kind end));

create or replace function agent_harness_control_events_append_only() returns trigger language plpgsql as $$
begin
  raise exception 'agent_harness_control_events is append-only';
end $$;

drop trigger if exists agent_harness_control_events_append_only on agent_harness_control_events;
create trigger agent_harness_control_events_append_only before update or delete on agent_harness_control_events
  for each row execute function agent_harness_control_events_append_only();

-- DOWN
drop table if exists agent_harness_control_events;
drop function if exists agent_harness_control_events_append_only();
drop table if exists agent_harness_control;
