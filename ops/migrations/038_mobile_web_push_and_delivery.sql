-- UP
-- Mobile delivery reliability, and browser (Web Push) subscriptions.
--
-- Delivery reliability. Until now an outbox row was tried at most three times,
-- sixty seconds apart, and a row that ran out of attempts was left as 'failed'
-- carrying only an exception class name. Three facts were missing: when the last
-- attempt happened, why a row was given up on, and whether anyone actually saw
-- the alert. The new columns record them:
--
--   attempted_at      when the last delivery attempt was made
--   dead_lettered_at  when the row was given up on, with dead_letter_reason
--   acknowledged_at   when the alert was marked seen, and acknowledged_by whom
--
-- 'dead_letter' joins the status check. 'failed' stays a legal value: rows
-- written before this migration keep it, and the constraint must still hold for
-- them. An acknowledgement is a column rather than a status, because a row can be
-- accepted by the provider, acknowledged, and still be the row that was retried
-- twice; folding all of that into one status loses the history.
--
-- Web Push subscriptions. One row per browser: the push endpoint that browser
-- gave us, and the two public values a sender needs (p256dh, auth). None of it is
-- a TradeSync secret. The VAPID private key stays in the environment and never
-- reaches this database. The endpoint is a capability URL — anyone holding it can
-- push to that browser — so it is stored once, uniquely, and the API returns only
-- its host and a short digest, never the URL itself.
--
-- Two transports, one ledger. An attempt goes to the phone's subscribed browsers
-- when Web Push can send, and to ntfy otherwise; 'transport' records which one
-- carried the latest attempt, on the same row, through the same retries and dead
-- letters. Each browser keeps its own last result, and one the push service
-- reports gone (404 or 410) is marked expired with the reason instead of being
-- tried again.
--
-- Tap acknowledgement. A Web Push message carries a single-use token; only its
-- SHA-256 digest is stored here, with when it stops working. Tapping the
-- notification posts the token, which records the acknowledgement once and
-- clears the digest. The service worker holds no key of any kind.
--
-- Rows attempted before this migration were all carried by ntfy, so they say so.

alter table mobile_alert_outbox add column if not exists attempted_at timestamptz;
alter table mobile_alert_outbox add column if not exists dead_lettered_at timestamptz;
alter table mobile_alert_outbox add column if not exists dead_letter_reason text;
alter table mobile_alert_outbox add column if not exists acknowledged_at timestamptz;
alter table mobile_alert_outbox add column if not exists acknowledged_by text;

alter table mobile_alert_outbox drop constraint if exists mobile_alert_outbox_status_check;
alter table mobile_alert_outbox add constraint mobile_alert_outbox_status_check
  check (status in ('queued','sending','retry','provider_accepted','operator_confirmed','failed','expired','dead_letter'));

alter table mobile_alert_outbox drop constraint if exists mobile_alert_outbox_acknowledged_by_check;
alter table mobile_alert_outbox add constraint mobile_alert_outbox_acknowledged_by_check
  check (acknowledged_by is null or acknowledged_by in ('operator','device'));

alter table mobile_alert_outbox drop constraint if exists mobile_alert_outbox_acknowledged_pair_check;
alter table mobile_alert_outbox add constraint mobile_alert_outbox_acknowledged_pair_check
  check ((acknowledged_at is null) = (acknowledged_by is null));

alter table mobile_alert_outbox drop constraint if exists mobile_alert_outbox_dead_letter_reason_check;
alter table mobile_alert_outbox add constraint mobile_alert_outbox_dead_letter_reason_check
  check (dead_lettered_at is null or length(btrim(coalesce(dead_letter_reason, ''))) > 0);

create index if not exists mobile_alert_outbox_recent on mobile_alert_outbox (created_at desc);

alter table mobile_alert_outbox add column if not exists transport text;
alter table mobile_alert_outbox add column if not exists ack_token_hash text;
alter table mobile_alert_outbox add column if not exists ack_token_expires_at timestamptz;

alter table mobile_alert_outbox drop constraint if exists mobile_alert_outbox_transport_check;
alter table mobile_alert_outbox add constraint mobile_alert_outbox_transport_check
  check (transport is null or transport in ('ntfy','web_push'));

alter table mobile_alert_outbox drop constraint if exists mobile_alert_outbox_ack_token_check;
alter table mobile_alert_outbox add constraint mobile_alert_outbox_ack_token_check
  check ((ack_token_hash is null) = (ack_token_expires_at is null)
         and (ack_token_hash is null or ack_token_hash ~ '^[0-9a-f]{64}$'));

create unique index if not exists mobile_alert_outbox_ack_token
  on mobile_alert_outbox (ack_token_hash) where ack_token_hash is not null;

update mobile_alert_outbox set transport = 'ntfy' where transport is null and attempts > 0;

create table if not exists mobile_web_push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  device_id uuid not null references mobile_alert_devices(id),
  endpoint text not null unique,
  endpoint_digest text not null check (endpoint_digest ~ '^[0-9a-f]{12}$'),
  p256dh text not null check (length(p256dh) between 80 and 200),
  auth text not null check (length(auth) between 16 and 40),
  label text not null default '' check (length(label) <= 60),
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  last_attempt_at timestamptz,
  last_status integer check (last_status is null or last_status between 100 and 599),
  last_error text check (last_error is null or length(last_error) between 1 and 80),
  accepted_at timestamptz,
  expired_at timestamptz,
  expired_reason text,
  constraint mobile_web_push_https check (endpoint like 'https://%' and length(endpoint) between 20 and 2000),
  constraint mobile_web_push_expired_reason check (expired_at is null or length(btrim(coalesce(expired_reason, ''))) > 0)
);

create index if not exists mobile_web_push_by_device on mobile_web_push_subscriptions (device_id);

-- DOWN
drop table if exists mobile_web_push_subscriptions;
drop index if exists mobile_alert_outbox_ack_token;
alter table mobile_alert_outbox drop constraint if exists mobile_alert_outbox_ack_token_check;
alter table mobile_alert_outbox drop constraint if exists mobile_alert_outbox_transport_check;
alter table mobile_alert_outbox drop column if exists ack_token_expires_at;
alter table mobile_alert_outbox drop column if exists ack_token_hash;
alter table mobile_alert_outbox drop column if exists transport;
drop index if exists mobile_alert_outbox_recent;
alter table mobile_alert_outbox drop constraint if exists mobile_alert_outbox_dead_letter_reason_check;
alter table mobile_alert_outbox drop constraint if exists mobile_alert_outbox_acknowledged_pair_check;
alter table mobile_alert_outbox drop constraint if exists mobile_alert_outbox_acknowledged_by_check;
alter table mobile_alert_outbox drop constraint if exists mobile_alert_outbox_status_check;
alter table mobile_alert_outbox add constraint mobile_alert_outbox_status_check
  check (status in ('queued','sending','retry','provider_accepted','operator_confirmed','failed','expired'));
alter table mobile_alert_outbox drop column if exists acknowledged_by;
alter table mobile_alert_outbox drop column if exists acknowledged_at;
alter table mobile_alert_outbox drop column if exists dead_letter_reason;
alter table mobile_alert_outbox drop column if exists dead_lettered_at;
alter table mobile_alert_outbox drop column if exists attempted_at;
