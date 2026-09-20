"""``POST /state/mobile-alerts/acknowledgements``: tapping a notification records that it was seen.

The service worker (services/cockpit-ui/public/sw.js) posts the token its notification carried and nothing else.
It holds no key, neither the mobile control key nor the operator token. The token is the whole authorization, and
it authorizes one thing, once (app/mobile_ack_token.py):

- its digest must match a row's, and it must not have expired;
- the first use records ``acknowledged_by='device'`` and the time, unless someone acknowledged the alert first,
  whose record is kept; either way the digest is cleared in the same statement, so a second use finds nothing;
- every refusal is the same 410, whether the token was used, expired or never issued, and a success says only that
  it was recorded. Neither names the alert, its phone, its kind or its time.

Nothing else about the alert changes, and nothing here can create, approve or change a trade.

The route stays behind every guard in app/asgi.py. The Host check applies as it does to any path. The cross-site
check applies: a change sent from a page that is not the Cockpit is refused. Its body is capped at 1 KiB
(app/body_limit.py). The one thing it does not need is the operator token (``TOKEN_EXEMPT_PATHS`` in
app/access_guard.py): a service worker must not hold that token, and this one is narrower in every way.
"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app import mobile_ack_token

PATH = "/state/mobile-alerts/acknowledgements"
MAX_BODY_BYTES = 1024

REFUSED = ("This notification can no longer be marked seen: its acknowledgement was already used, has expired, or "
           "was never issued. Nothing was recorded.")


class TapAcknowledgement(BaseModel):
    token: str = Field(min_length=mobile_ack_token.TOKEN_CHARACTERS, max_length=mobile_ack_token.TOKEN_CHARACTERS,
                       pattern=r"^[A-Za-z0-9_-]+$")


def register(app, state) -> None:
    @app.post(PATH)
    async def tap_acknowledgement(body: TapAcknowledgement):
        if getattr(state, "pool", None) is None:
            raise HTTPException(503, "Notification database unavailable")
        async with state.pool.acquire() as conn:
            recorded = await mobile_ack_token.consume(conn, body.token)
        if not recorded:
            raise HTTPException(410, REFUSED)
        return {"status": "acknowledged", "authority": "none",
                "note": "Recorded that the notification was opened. Nothing else changed."}
