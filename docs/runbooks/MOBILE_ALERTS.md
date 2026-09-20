# Mobile alerts: Android and iPhone

Status: the ntfy.sh path is implemented and locally deployed; **no real device
enrolled or delivery verified yet**. Web Push to a Home Screen web app is
implemented on branch `claude/mobile-pwa` and **not deployed** (see the end of this
runbook). Neither is a custom native application, and neither carries signing or
trading authority.

## Setup and acceptance

1. Configure a dedicated random **32+ character application control key** as
   `MOBILE_ALERTS_CONTROL_KEY` in the private
   `E:/Projects/TradeSync/dashboard-runtime/runtime.env`, using the governed
   private-configuration workflow. This is not a wallet key, seed, provider key
   or new paid subscription. Do not paste it in chat, logs or this repository.
2. Recreate only State API using the existing compose project and files:
   `docker compose --project-name tradesync-full --env-file E:/Projects/TradeSync/dashboard-runtime/runtime.env -f ops/compose.full.yml -f ops/compose.market-command.yml up -d --no-deps --no-build state-api`.
3. Authorized browser/API requests must supply the same key as `X-API-Key`.
   The existing local Cockpit API-key mechanism sends this header. Use the
   trusted local workstation/browser profile; it currently stores that control
   credential in browser local storage. Do not expose the dashboard/API to the
   internet or enter the credential into another project's API configuration.
   A hardened session-based local control flow remains a security improvement.
4. Install [ntfy on the phone](https://docs.ntfy.sh/subscribe/phone/).
   In TradeSync **Settings → Mobile notifications**, select Android or iPhone,
   enter a label and explicitly accept generic public-topic delivery.
   **Create subscription details** creates a local record only; it sends nothing.
5. In the ntfy app, subscribe using server `https://ntfy.sh` and the generated
   topic. Enable phone notification permission. Save the topic privately;
   **Show subscription details** can reveal it again to an authorized operator.
6. Click **Send generic test**. Watch the delivery ledger. `provider_accepted`
   means the response matched the topic/message and included a provider ID.
   It does **not** mean the phone received a notification.
7. On the specified physical phone, find the matching reference. Only then click
   **I received this on my phone**. This records operator attestation, not
   automated telemetry. Repeat independently for the other phone platform.
8. Disable a channel to stop pending sends. An already in-flight HTTP request
   cannot be recalled. Notifications cannot approve, modify or execute a trade.

No real topic, control credential or physical-device receipt is included here.
There is no need to invent a TradingView/Reown/crypto wallet key for this setup.

## Reliability and privacy

PostgreSQL `mobile_alert_outbox` stores events separately from provider delivery.
`(device_id, dedupe_key)` deduplicates enqueue calls. Events expire after ten
minutes; the worker claims rows with a lease and makes at most five attempts,
waiting 15, 30, 60 and 120 seconds between them (migration 038,
`app/mobile_delivery.py`). A row that runs out of attempts, or is refused with a
400-class status other than rate limiting, becomes a **dead letter** that keeps
its reason. HTTP redirects are not followed. Topic format and fixed HTTPS provider prevent arbitrary URL
publishing. Only two hardcoded generic templates are permitted.

Transport is **at least once**, not exactly once: a timeout after provider
acceptance can produce a duplicate on retry. A stable short reference lets the
operator recognize duplicates. The service can also be offline beyond expiry;
this is not a guaranteed emergency notification service. Device disable and
expired entries never create execution authority.

Public ntfy topics are not authenticated private channels. Anyone who learns a
topic may subscribe or spoof messages. High-entropy generated topics reduce
guessability but are not a replacement for access control. Do not send balances,
wallet addresses, trade details, secrets or approval actions. Provider quotas
can delay/refuse messages; a future authenticated/private adapter can replace
this transport without changing the durable event ledger.

Web Push, described at the end of this runbook, writes to the same ledger. Each
message is encrypted for one browser, so the push service cannot read it, and
signed with the operator's key pair, which the push service checks against the key
the browser subscribed with. It posts only to the push services browsers use.

## Remaining work

- Actual setup, subscription and receipt on **both** Android and iPhone.
- Managed-paper open/close producer, per-phone opt-in, quiet hours/timezone and
  rolling 24-hour budgets are deployed and isolated-test verified. Actual phone
  delivery remains unverified. Chart-alert producers are still unconnected.
- Preferences by symbol/category/severity, global cross-device budgets,
  acknowledgement reminders and long-running outage recovery tests remain.
- Web Push to an actual phone. The PWA, the sender, tap acknowledgement and the
  delivery ledger exist on branch `claude/mobile-pwa` (see the end of this runbook)
  and are verified without a network, but no phone can reach the dashboard over
  HTTPS yet, so no real push has been sent or received.
- Optional authenticated self-hosting/private delivery.
- Phone-to-dashboard remote access remains separate. Do not publish the entire
  State API or reuse the restricted Pine ingress as a mobile dashboard tunnel.

References: [ntfy publishing and limitations](https://docs.ntfy.sh/publish/),
[phone clients](https://docs.ntfy.sh/subscribe/phone/).
# Lifecycle preferences update — 14 September

After receiving and confirming a test on a phone, open its **Paper lifecycle
notification preferences** in Settings. Explicitly opt in to future managed-paper
opens/closes, choose an IANA timezone, quiet hours and a rolling 24-hour budget.
Default: opt-out, Europe/London, quiet 22:00–08:00, maximum 10 lifecycle messages.
Equal start/end means all-day quiet. Suppressed events are recorded but not
replayed; manual tests bypass quiet hours. Opt-out cannot recall an in-flight
request. Messages remain generic, without symbols, balances or trade instructions.

Implementation/isolated SQL/UI checks passed; actual Android/iPhone delivery
remains unverified and requires the private setup described below.

# PWA, Web Push and delivery reliability — 16 September

Source on branch `claude/mobile-pwa`; **not deployed**, and migration 038 must be
applied first. Once deployed and configured, state-api will send real Web Push
messages to subscribed browsers. Change record:
[2026-09-16_mobile-pwa-and-delivery.md](../changes/2026-09-16_mobile-pwa-and-delivery.md).

## Install the dashboard as a Home Screen app

The Cockpit serves `/manifest.webmanifest` and a service worker at `/sw.js`.

- **Android (Chrome):** open the dashboard, open the browser menu and choose
  **Install app** or **Add to Home screen**.
- **iPhone or iPad (iOS/iPadOS 16.4 or later):** open the dashboard in
  **Safari**, tap **Share**, then **Add to Home Screen**, and open it from that
  icon. This step is required: iOS offers notifications only to a web app added
  to the Home Screen, never to a Safari tab. No Xcode project, App Store listing
  or Apple Developer membership is involved.

Web Push needs HTTPS outside `localhost`. Today the dashboard listens only on
127.0.0.1, so a phone cannot reach it. Exposing it to a phone is a separate
deployment and security decision, and the Pine tunnel must not be reused for it.

The service worker caches no dashboard data. Its fetch handler never touches an API
request, a page load always goes to the network, and without a connection it shows one
static page saying so, because a kept copy of a price or a paper number would be
wrong.

## Generate the VAPID key pair (operator, on this PC)

Web Push identifies the sender with a VAPID key pair. It is generated on this PC,
never committed, and the dashboard never generates or receives the private half.
In Windows PowerShell (the same command is on the Settings page):

```powershell
Set-Location E:\Projects\TradeSync\dashboard-overhaul-2026-09-01
$pair = node -e "const {generateKeyPairSync}=require('crypto');const {privateKey}=generateKeyPairSync('ec',{namedCurve:'prime256v1'});const k=privateKey.export({format:'jwk'});const b=(s)=>Buffer.from(s,'base64url');console.log(JSON.stringify({public:Buffer.concat([Buffer.from([4]),b(k.x),b(k.y)]).toString('base64url'),private:k.d}))" | ConvertFrom-Json
Set-Clipboard -Value $pair.private
powershell -ExecutionPolicy Bypass -File tools\set-runtime-secret.ps1 -Name MOBILE_WEB_PUSH_VAPID_PRIVATE_KEY
Set-Clipboard -Value $pair.public
powershell -ExecutionPolicy Bypass -File tools\set-runtime-secret.ps1 -Name MOBILE_WEB_PUSH_VAPID_PUBLIC_KEY
Set-Clipboard -Value ' '
Write-Output "Public key, safe to show: $($pair.public)"
```

It makes a P-256 key pair offline with Node's built-in crypto: nothing is
downloaded and no account is created. It stores the private half through the
desktop prompt without displaying it, then the public half, clears the clipboard
and prints only the public key. Then recreate state-api so it reads them:

```powershell
Set-Location E:\Projects\TradeSync\dashboard-overhaul-2026-09-01
docker compose --project-name tradesync-full --env-file E:/Projects/TradeSync/dashboard-runtime/runtime.env -f ops/compose.full.yml -f ops/compose.market-command.yml up -d --no-deps --no-build state-api
```

**Settings → Mobile notifications → Notifications in this browser** then reads
"Key pair on this PC: configured". Until both keys are set, and are the two halves
of one pair, every surface says a browser cannot subscribe, and the subscribe
route refuses with the variable's name. `GET /state/mobile-alerts/web-push`
reports each key as `missing`, `malformed` or `ok`, and returns the public key
only when the pair is usable.

## Set the sender's contact (operator, on this PC)

Push services are given a contact for whoever sends, and Apple's refuses a push
without one. Until `MOBILE_WEB_PUSH_SUBJECT` is a `mailto:` address or an `https:`
URL, alerts keep going through ntfy and Settings reads "Sending: waiting for a
contact address". Store it through the desktop prompt (also on the Settings page),
then recreate state-api with the command above:

```powershell
Set-Location E:\Projects\TradeSync\dashboard-overhaul-2026-09-01
powershell -ExecutionPolicy Bypass -File tools\set-runtime-secret.ps1 -Name MOBILE_WEB_PUSH_SUBJECT -Prompt 'A mailto: address or an https: URL push services can use to reach you, for example mailto:you@example.com'
```

The address is the operator's own, so no route returns it: the status says only
`missing`, `malformed` or `ok`. Settings then reads "Sending: ready".

## Allow and subscribe a browser

In the installed app, open Settings. The panel shows the real state — cannot show
notifications, add to the Home Screen first, not asked yet, allowed, or blocked —
and the one step to take. **Allow notifications** asks once; a blocked site is
changed in the browser's own site settings. Once allowed, choose the enrolled
phone the browser belongs to and **Subscribe this browser**. State-api records the
endpoint and its two public values, one row per browser, at most five active
browsers per phone. It accepts only the push services browsers use (Google FCM,
Mozilla, Apple, Windows) and a browser key that is a real P-256 point. The Cockpit
shows only the push service and a digest, never the endpoint, with the result of
the last push sent to each browser.

## How an alert travels

Each attempt picks one transport. When Web Push can send (a usable key pair and a
contact) and the phone has a browser that is not expired, the attempt goes to all
of its browsers at once; otherwise it goes to ntfy. Both land on the same ledger
row, through the same five attempts, the same 15, 30, 60 and 120 second waits,
the same dead letter, quiet hours and daily budget, and the row records which
transport carried it.

Every browser gets its own encrypted copy (RFC 8291) of the same generic payload,
signed for its push service (RFC 8292): "TradeSync needs attention. Open your
dashboard." or the test sentence, the eight-character reference, and a tap token.
Every push is padded to the same size, so no trade, symbol, price or amount can
reach a lock screen or be guessed from a message's length. A push service holds a
push for at most ten minutes (`TTL: 600`) and is asked to wake the phone
(`Urgency: high`).

What a push service's answer means. An alert is accepted when any of the phone's
browsers accepted it; the rest applies when none did, and an answer worth retrying
wins over a refusal.

- **2xx**: accepted. The ledger says "Push service accepted it", which is not proof
  the phone showed it.
- **404 or 410**: that browser's subscription no longer exists. The browser is
  marked expired with the reason and never sent to again. When every browser of a
  phone is gone, the retry goes through ntfy. Subscribing the browser again
  revives it.
- **429, 5xx, a timeout or a lost connection**: the alert is retried on the usual
  waits.
- **Any other 4xx** (400, 401, 403, 413): a dead letter at once, with the HTTP
  status as its reason. A 401 or 403 usually means the key pair changed after the
  browser subscribed: subscribe it again.
- **A redirect** is never followed. The alert is tried again, and becomes a dead
  letter when the five attempts run out.

## Tap acknowledgement

Tapping a Web Push notification opens the dashboard and records that the alert was
seen: the ledger shows "Marked seen by a tap on the notification". The service
worker holds no key. The notification carries a single-use token, 32 random
octets. State-api stores only its SHA-256 digest, and the token stops working one
hour after the attempt. The worker posts it to
`POST /state/mobile-alerts/acknowledgements`, same-origin, without credentials.
One statement records the acknowledgement once and clears the digest. A used,
expired or unknown token gets the same 410, and neither answer names the alert.
An earlier acknowledgement by the operator is the one kept.

The route stays behind the Host check and the cross-site refusal, and its body is
capped at 1 KiB. Apart from the TradingView webhook, it is the only change that
does not need the operator token (`STATE_API_OPERATOR_TOKEN`), because a service
worker must not hold that token; `GET /state/access-policy` lists it under
`operator_token_exempt_paths`. When a phone later reaches the dashboard under its
own HTTPS name, that name must be added to `STATE_API_ALLOWED_HOSTS` and its origin
to `STATE_API_ALLOWED_ORIGINS`. Otherwise the Host check refuses every request from
that name, and the origin check every change, taps included.

## Delivery ledger

Settings lists every notification with its status, the transport that carried it,
attempts out of five, the last error, when the last attempt was made, when the
provider or push service accepted it, dead letters with their reason, and
acknowledgements with who and when, every time to the second. **Mark seen** records
an operator acknowledgement against the row. **I received this on my phone** is
still the attestation that unlocks automatic notifications, and it records the
acknowledgement in the same statement. Both need the mobile control key, and the
control route records the operator only: a phone acknowledges only by a tap.
