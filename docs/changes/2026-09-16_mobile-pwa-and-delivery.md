# 2026-09-16 — Mobile PWA, Web Push delivery, tap acknowledgement and delivery reliability

Branch `claude/mobile-pwa` from `f8bfdd5`. **Not merged, not deployed**, and **migration 038 is not
applied** to the live database. Paper mode untouched (`DRY_RUN=true`, `EXECUTION_ENABLED=false`); no
paper entry, paper portfolio, key, signer, wallet or execution path changed.

Once deployed and configured, state-api **will send real Web Push messages**. **No test or acceptance run
sent one**: the push service and ntfy were local fakes throughout, and every run refused to build any HTTP
client that was not in-process.

It covers the Week 3 items for the PWA, Web Push, retries, dead letters, acknowledgement and the delivery
ledger; the runbook's Remaining work lists what is still open. Before it there was no manifest, no service
worker, no permission flow, no Web Push subscription or sender, no way to know a notification was opened, and
delivery had no dead letter and no ledger beyond a status and an attempt count.

## What it adds

**An installable Cockpit** (`public/manifest.webmanifest`, `public/sw.js`, `public/offline.html`,
`index.html`, `nginx.conf`, `src/pwa/`). The manifest names the Cockpit, opens standalone at `/` and uses
the Cockpit's own canvas colour (`#07111f`). Icons at 192, 512 and a maskable 512 are made from
`public/brand/tradesync-mark.png`. The service worker shows a notification for a push, opens or focuses the
dashboard when one is tapped and posts that notification's tap token, tells the operator to subscribe again
when the browser rotates its subscription, and shows one static offline page when a page load fails. It
**caches no dashboard data**: its fetch handler never touches an API request, and the only cached files are the offline
page, the manifest and two icons. A tap can only ever go to a path on this site. nginx serves the worker, the
manifest and the offline page `no-cache`.

**The permission flow, in Settings → Mobile notifications** (`components/mobile/WebPushSetup.tsx`,
`pwaText.ts`, `src/pwa/`). It shows the real state of this browser: cannot show notifications, add to the
Home Screen first, not asked yet, allowed, or blocked. It also shows whether the worker is registered, the
browser subscribed, the key pair configured and sending ready, then the one step to take. An iPhone or iPad
in a Safari tab is told plainly that notifications need **Add to Home Screen** first, with no Xcode project
and no Apple Developer membership. A subscribed browser whose server lacks the sender's contact is told that
nothing is sent to it yet, why, and the command that fixes it.

**Web Push subscriptions** (`app/mobile_web_push.py`, `mobile_web_push_store.py`, `mobile_vapid.py`; Cockpit
`WebPushSubscriptions.tsx`, `subscriptionText.ts`). The VAPID public key is served only when the private key
is its other half. The private key is never returned, logged, displayed or written to the database. One row per browser (an
upsert on the endpoint), at most five active per phone, and the same browser re-subscribing is never refused.
An endpoint must be HTTPS, carry no credentials and belong to a push service browsers use (FCM, Mozilla,
Apple, Windows). The browser's key must be a real P-256 point. The endpoint is a capability URL, so no route
returns it: only its host and a digest, with the result of the last push sent to that browser, or when and
why it expired.

**The Web Push sender** (`app/mobile_dispatch.py`, `mobile_web_push_sender.py`, `web_push_encryption.py`,
`web_push_jwt.py`). Each attempt picks a transport. When Web Push can send and the phone has a browser that is
not expired, the attempt goes to all its browsers at once; otherwise it goes to ntfy. Both land on the same
outbox row through the same claim, lease, backoff, dead letter, quiet hours and budget, and the row records
which transport carried it.

- **Encryption** is RFC 8291 in the aes128gcm coding. Every message gets a new P-256 key pair and salt, ECDH
  with the browser's key, the RFC key schedule, and one AES-128-GCM record padded so every push is 614 octets.
- **Signing** is RFC 8292: an ES256 token for the push service's origin, expiring in twelve hours, with the
  sender's contact, and an RFC 6979 deterministic nonce.
- **The payload** is the sentence ntfy sends, the short reference, the path `/` and the tap token. No trade,
  symbol, price, amount or wallet.
- **Headers** are `TTL: 600` (the outbox window) and `Urgency: high`. Redirects are not followed and proxy
  settings are ignored.

What each answer means. An alert is accepted when any of the phone's browsers accepted it; the rows below
decide what happens when none did, and an answer worth retrying wins over a refusal.

| Push service answer | What happens |
| --- | --- |
| 2xx | Accepted (not proof the phone showed it) |
| 404 or 410 | The browser is marked **expired** with the reason and never sent to again. When every browser of a phone is gone, the retry uses ntfy |
| 429, 5xx, timeout, lost connection | Retried on the usual waits |
| Any other 4xx (400, 401, 403, 413) | Dead letter at once, the HTTP status as its reason |
| A redirect (never followed) | Tried again, then a dead letter when the five attempts run out |

Web Push sends only when the key pair is usable **and** `MOBILE_WEB_PUSH_SUBJECT` is a `mailto:` or `https:`
contact. Apple's push service refuses a push without one. The status reports the contact only as missing,
malformed or ok, never the address.

**Tap acknowledgement** (`app/mobile_ack_token.py`, `mobile_tap_ack.py`, `public/sw.js`).

- **The token.** Every Web Push attempt carries its own single-use token: 32 random octets, of which only the
  SHA-256 digest is stored on the outbox row, expiring one hour after the attempt. A later attempt replaces
  it, and the sweep drops expired digests.
- **The worker.** On `notificationclick` it posts the token, and nothing else, to
  `POST /state/mobile-alerts/acknowledgements`: same-origin, no credentials, no redirects. It holds no key.
  Opening the dashboard does not wait on the acknowledgement.
- **Exactly once.** One UPDATE records `acknowledged_by = 'device'` and the time, keeps an acknowledgement
  that came first, and clears the digest in the same statement, so the token works once however many taps race.
- **Refusals.** A used, expired or unknown token gets the same 410, a malformed one never reaches the
  database, and no answer names the alert, its phone, its kind or its time.
- **Guards.** The route stays behind the Host check and the cross-site refusal, unchanged. Its body limit
  is tightened to 1 KiB.

**Delivery reliability** (`app/mobile_delivery.py`, migration 038). At most five attempts, waiting 15, 30, 60
and 120 seconds, inside the ten-minute window. A row that runs out of attempts, or is refused with a 4xx other
than 429, becomes `dead_letter` with a reason built only from an HTTP status and a short error name. The sweep
dead-letters rows that can never be claimed again and leaves a row inside its lease alone.

**Acknowledgement and the ledger** (`app/mobile_ledger.py`; Cockpit `DeliveryLedger.tsx`,
`deliveryLedgerText.ts`). An acknowledgement is a pair of columns, not a status. `device` now always means a
proven tap. The control-key route records the operator only and refuses `by: "device"`, and "I received this
on my phone" records the operator acknowledgement in the same statement as the attestation. The ledger shows
each notification's status, transport, attempts out of five, last error, every time to the second,
acceptance by the provider or push service ("not proof a phone showed it"), dead letters with their reason,
and acknowledgements by the operator or by a tap.

**Deploy plumbing.** `ops/compose.market-command.yml` passes the key pair and the contact to state-api, empty
by default. `.env.example` lists them. The only change to `services/state-api/app/main.py` is three
`register(...)` calls appended at the tail. `tests/test_migrations.py` reserves 039 and 040 for parallel
branches.

| Route | Needs | Does |
| --- | --- | --- |
| `GET /state/mobile-alerts/web-push` | — | Key and contact states, public key when usable, whether sending is ready and why not |
| `POST /state/mobile-alerts/devices/{id}/web-push/subscriptions` | control key, key pair | Record a browser |
| `GET /state/mobile-alerts/web-push/subscriptions` | control key | Browsers by push service and digest, with their last result |
| `DELETE /state/mobile-alerts/web-push/subscriptions/{id}` | control key | Remove a record |
| `GET /state/mobile-alerts/ledger` | control key | Every delivery fact with the transport and exact times |
| `POST /state/mobile-alerts/events/{id}/acknowledge` | control key | The operator records that an alert was seen |
| `POST /state/mobile-alerts/acknowledgements` | the tap token (origin check applies; no operator token) | A tapped notification records that it was seen, once |

## Dependency added

`pycryptodome==3.23.0`, pinned in `services/state-api/requirements.txt`, and in root `requirements.txt` so
the state-api tests do not rely on eth-account pulling it in. The reasons:

- **Nothing already in state-api could do the job.** Web Push needs P-256 ECDH, ECDSA and AES-128-GCM. The
  standard library has none of the three, and the state-api image has no cryptography library at all
  (checked with `pip list` inside `tradesync/state-api:dev`, offline). Hand-rolling any of them was rejected.
- **It adds no new package to the project.** pycryptodome 3.23.0 is the exact version signer-svc already
  installs through eth-account (checked with `pip show` inside `tradesync/signer-svc:dev`, offline), and the
  test venv already had it.
- **`cryptography`, the other candidate, would have been new.** No requirements file in the repository names
  it, and it is not in the state-api image.

No npm dependency was added. The image build installs the pinned wheel from PyPI like every other
requirement. The state-api image was not rebuilt on this branch; signer-svc, built from the same
`python:3.11-slim` base, already installs this exact version.

## Decisions a reviewer should look at

- **One exemption in the access guard.** `POST /state/mobile-alerts/acknowledgements`, that exact path only,
  is listed in `TOKEN_EXEMPT_PATHS`, so it does not need `STATE_API_OPERATOR_TOKEN` when one is configured.
  A service worker must not hold that token, and the tap token is narrower in every way: one alert, one use,
  one hour, and it can only mark the alert seen. The origin check still runs for it, a neighbouring path is
  guarded as before, and `GET /state/access-policy` lists the exemption. Without it, taps would be refused
  whenever an operator token is set.
- **Web Push replaces ntfy for a phone, not in addition.** A phone with a subscribed, unexpired browser gets
  its alerts there and not in the ntfy app, so it is not notified twice. It falls back to ntfy when every
  browser is gone or sending is not ready.
- **A contact is required to send**, because Apple refuses a push without one. Until it is set, the
  failure mode is "alerts keep going through ntfy", not dead letters.
- **Only known push services.** The endpoint is a URL state-api posts to, so the host must be one browsers
  use. A browser on an unlisted service cannot subscribe, and says so.
- **401 or 403 does not expire a browser.** It usually means the key pair changed after subscribing. The
  browser stays recorded with the HTTP status for the operator to act on, and an alert no other browser
  accepted becomes a dead letter, rather than the phone silently switching to ntfy.
- **Migration 038 was extended** rather than a new migration added, since it is applied nowhere.

## What it does not do

- **No phone can reach the dashboard today.** Every port is bound to 127.0.0.1, and Web Push needs HTTPS
  outside `localhost`. Exposing the Cockpit to a phone is a separate deployment and security decision; the
  Pine tunnel must not be reused for it. The phone's HTTPS host and origin will also need adding to
  `STATE_API_ALLOWED_HOSTS` and `STATE_API_ALLOWED_ORIGINS`; otherwise the Host check refuses every request
  from that name, taps included.
- **No real push was sent or received, and no browser QA was done.** The service worker was tested by
  running `sw.js` in Node against a stand-in `self`, not in a browser. The encryption and signing are proven
  against the RFC's published example and by an independent implementation, not by a real push service.
- **A lost acceptance means a repeated push.** If state-api stops between a push service's 201 and
  recording it, the lease lapses and the retry pushes again with a new token. The notification carries the
  same tag, so a browser that honours tags replaces the first rather than showing two, and only the newer
  token can then acknowledge it.
- **The worker does not re-subscribe on its own.** When a browser rotates its subscription, it still asks
  the operator to subscribe again.
- **Existing rows.** Rows already `failed` stay so, and rows attempted before migration 038 are marked as
  carried by ntfy.

## Verification

All on this branch, in the worktree `E:\Projects\TradeSync\mobile-pwa-2026-09-16`. The first two bullets ran on
the final code, `6923f49`, with `.env.example` and the compose comments already edited. The runbook, the index
and this record were still being worded during those runs; no test reads them.

- **Every Python suite**, `tools/run_tests.py`, the runner's own exit code **0**: root **1139 passed**
  (17 deselected, 49 subtests passed), state-api **669 passed**, market-data **160**, exec-hl-svc **11**,
  signer-svc **14**. Integration tests were not run; they need the stack up. New for the sender and taps:
  `test_web_push_encryption.py`, `test_web_push_jwt.py`, `test_mobile_vapid_pair.py`,
  `test_mobile_web_push_sender.py`, `test_mobile_dispatch_transport.py`, `test_mobile_tap_ack.py`, and
  additions to the access-guard, body-limit, delivery and subscription tests.
- **Cockpit**: `npm test` exit 0, **176 tests, 176 pass, 0 fail**; `npm run build` exit 0. New: the tap tests
  in `pwa-service-worker`, and `web-push-subscription-text`.
- **RFC 8291 test vector.** `test_web_push_encryption.py` reproduces the section 5 example message byte for
  byte (144 octets) and every intermediate value in Appendix A. The values were taken from the RFC as
  published on rfc-editor.org, and the test recomputes the whole chain from the inputs, so a transcription
  slip would fail it rather than pass. No network is used by the test.
- The Node cross-check, both real-SQL acceptance scripts and the migration reversal below ran on the code of
  `b29557e`. The only later code change, `6923f49`, is wording and one unit test.
- **Independent implementation.** `tools/qa_web_push_node_crosscheck.py`, exit 0, on Node v24.14.1
  (OpenSSL, sharing no code with pycryptodome). Node opened the RFC's example with the RFC's browser key, and
  opened a padded 614-octet message state-api sealed. It verified state-api's ES256 VAPID token and refused
  one signed by another key.
- **Real-SQL acceptance** on a throwaway PostgreSQL 16.15 container on 127.0.0.1:55461, database
  `tradesync_qa`, with `ops/sql/schema.sql` and migrations 001–034 and 036–038 applied through
  `ops/apply_schema.py`.
  - `tools/qa_mobile_web_push_sql.py` (exit 0) ran in one rolled-back transaction, with a fake push service
    that verified every VAPID signature and opened every message with the browser's own private key:
    - schema: the new constraints;
    - delivery through the real dispatcher: 410 expiry and never sent to again, 503 retried and delivered,
      ntfy fallback, revival by re-subscribing, 403 dead-lettered at once, five 503s waiting 15, 30, 60 and
      120 seconds, no contact meaning ntfy, every push 614 octets;
    - budget counted and enforced;
    - taps through the deployed guard layering, using tokens the fake browsers actually received;
    - 13 requests to the fake push service, 2 to the fake ntfy.
  - A **real race**, on two connections: the second tap with the same token blocked until the first
    committed, then matched nothing. Its two committed rows were deleted.
  - The acceptance output was searched for token-shaped strings: none.
  - `tools/qa_mobile_pwa_delivery_sql.py`, updated for real in-memory keys and the operator-only control
    route, passed its four sections again (exit 0).
  - The container was removed afterwards.
- **Migration 038 reverses.** DOWN removed all eight new outbox columns, the subscriptions table, the token
  index and the new constraints, and restored the old status check. UP re-applied, and applied a second time
  over itself. All inside a rolled-back transaction.
- **The key-generation command** was run once in Windows PowerShell 5.1, printing only lengths: public 87
  characters with the `0x04` prefix, private 43. The throwaway pair was discarded; no key was stored.

## Deploy needs

1. Apply migration 038.
2. Rebuild and recreate **state-api** (new modules, the pinned `pycryptodome`, the compose variables) and
   **cockpit-ui** (the worker, new public files, `nginx.conf`, the bundle).
3. At merge, drop 039 and 040 from `SKIPPED_MIGRATION_NUMBERS` once those migrations arrive.

## Still the operator's to do

1. **Generate the key pair** on this PC with the command in the runbook (also on the Settings page).
2. **Set the contact** with the runbook command. It is required to send.
3. **Recreate state-api.** Settings then reads "Sending: ready".
4. **Decide how a phone may reach the dashboard over HTTPS**, and add that host and origin to
   `STATE_API_ALLOWED_HOSTS` and `STATE_API_ALLOWED_ORIGINS`. Until then, installing and subscribing work only
   in a browser on this PC.
5. **On each phone, once reachable:**
   - install to the Home Screen (on iPhone, Safari → Share → Add to Home Screen, required);
   - allow notifications and subscribe the browser to its enrolled phone;
   - send the generic test and tap it, then check that the ledger reads "Marked seen by a tap on the
     notification";
   - confirm receipt with "I received this on my phone" to unlock automatic alerts.
6. **Keep ntfy for any phone without a subscribed browser.** Its steps stand as before.
