"""Parse and authenticate a TradingView alert body.

TradingView cannot send custom HTTP headers, so there is no `Authorization`
header to check. The shared secret must travel inside the alert message itself.
That single constraint shapes everything here, and it was verified against the
venue's own documentation rather than assumed.

Also verified: TradingView posts from four fixed addresses, accepts only ports
80 and 443, and abandons a request after three seconds. The IP allowlist belongs
at the edge (Cloudflare WAF) and is the strongest single control available; this
module is the second layer, not the first.

One webhook URL exists per alert, but many alerts may target the same URL. So
the body must identify itself — which indicator fired, on what symbol, at what
timeframe — rather than relying on a distinct endpoint per alert.

Nothing parsed here becomes a signal. The output is a quarantine submission.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
from dataclasses import dataclass, field
from typing import Any, Collection, Mapping

SCHEMA_VERSION = "tradingview_alert_v1"

# Published TradingView webhook source addresses. Verified 2026-09-08 from the
# venue's own documentation; an allowlist at the edge should use these.
TRADINGVIEW_SOURCE_IPS = (
    "52.89.214.238",
    "34.212.75.30",
    "54.218.53.128",
    "52.32.178.7",
)

# The venue abandons a request after three seconds, so intake must accept fast
# and verify afterwards rather than doing expensive work inline.
VENUE_TIMEOUT_SECONDS = 3

REQUIRED_FIELDS = ("secret", "indicator", "ticker")
MAX_BODY_BYTES = 16 * 1024

# The address TradingView posts to: the one path the Cloudflare tunnel publishes. The
# tunnel profile (ops/ingress/TRADESYNC_CLOUDFLARE_PROFILE.md) records the same host and
# path, and tests/test_tradingview_webhook.py keeps the two in agreement.
PUBLIC_WEBHOOK_URL = "https://tradesync-pine.chaseintech.com/webhook/tradingview"

# What an operator pastes into a TradingView alert's Message box. TradingView fills the
# {{...}} placeholders when the alert fires; the operator replaces SECRET_PLACEHOLDER with
# the configured secret and the other <...> values by hand. Only REQUIRED_FIELDS are
# needed; everything else is kept as evidence in quarantine.
SECRET_PLACEHOLDER = "<paste your webhook secret>"
_MESSAGE_TEMPLATE = (
    ("secret", SECRET_PLACEHOLDER),
    ("indicator", "<indicator name>"),
    ("ticker", "{{ticker}}"),
    ("exchange", "{{exchange}}"),
    ("interval", "{{interval}}"),
    ("time", "{{timenow}}"),
    ("close", "{{close}}"),
    ("direction", "<long|short|none>"),
    ("note", "<what fired>"),
)


def message_template() -> dict[str, str]:
    """A fresh copy of the alert message template, in the order it is pasted."""
    return dict(_MESSAGE_TEMPLATE)


class WebhookError(ValueError):
    """Raised for malformed input, never for a failed authentication."""


@dataclass(frozen=True)
class ParsedAlert:
    """A TradingView alert, authenticated or not."""

    authenticated: bool
    indicator: str
    ticker: str
    interval: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    reasons: list[dict[str, str]] = field(default_factory=list)

    def to_submission(self) -> dict[str, Any]:
        """The quarantine payload. The secret is never carried forward."""
        return {
            "schema_version": SCHEMA_VERSION,
            "indicator": self.indicator,
            "ticker": self.ticker,
            "interval": self.interval,
            "action": self.action,
            "alert": self.payload,
        }


def _reason(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def parse_alert(body: str | bytes, expected_secret: str) -> ParsedAlert:
    """Parse and authenticate one alert body.

    Authentication failure is reported, not raised: a wrong secret is an
    ordinary event on a public endpoint and must be recorded rather than
    crashing the receiver.
    """

    if not expected_secret:
        raise WebhookError(
            "no expected secret configured; refusing to accept unauthenticated alerts"
        )

    if isinstance(body, bytes):
        if len(body) > MAX_BODY_BYTES:
            return ParsedAlert(
                False, "", "", "", "",
                reasons=[_reason("body_too_large", f"{len(body)} bytes exceeds bound")],
            )
        try:
            body = body.decode("utf-8")
        except UnicodeDecodeError:
            return ParsedAlert(
                False, "", "", "", "",
                reasons=[_reason("body_not_utf8", "body was not valid UTF-8")],
            )

    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        # TradingView sends text/plain when the message is not valid JSON. A
        # plain-text alert cannot carry a secret, so it cannot be authenticated.
        return ParsedAlert(
            False, "", "", "", "",
            reasons=[
                _reason(
                    "body_not_json",
                    "alert message must be JSON carrying a secret; plain text "
                    "cannot be authenticated",
                )
            ],
        )

    if not isinstance(payload, Mapping):
        return ParsedAlert(
            False, "", "", "", "",
            reasons=[_reason("body_not_object", "alert JSON must be an object")],
        )

    reasons: list[dict[str, str]] = []
    missing = [f for f in REQUIRED_FIELDS if not str(payload.get(f, "")).strip()]
    if missing:
        reasons.append(
            _reason(
                "missing_fields",
                "one endpoint serves many alerts, so each must identify itself: "
                + ", ".join(missing),
            )
        )

    supplied = str(payload.get("secret", ""))
    # Constant-time comparison: a timing oracle on a public endpoint would let
    # an attacker recover the secret byte by byte.
    if not hmac.compare_digest(supplied, expected_secret):
        reasons.append(
            _reason(
                "bad_secret",
                "shared secret did not match; TradingView cannot send headers "
                "so the secret must be in the alert body",
            )
        )

    # The secret never travels onward into storage.
    scrubbed = {k: v for k, v in payload.items() if k != "secret"}

    return ParsedAlert(
        authenticated=not reasons,
        indicator=str(payload.get("indicator", "")).strip(),
        ticker=str(payload.get("ticker", "")).strip(),
        interval=str(payload.get("interval", "")).strip(),
        action=str(payload.get("action", "")).strip(),
        payload=scrubbed,
        reasons=reasons,
    )


def normalise_ip(value: str | None) -> str | None:
    """One IP address in canonical form, an IPv4-mapped IPv6 address unwrapped; None for anything else."""
    if not value:
        return None
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return str(address)


def alert_source(peer: str | None, cf_connecting_ip: str | None, tunnel_peers: Collection[str]) -> str | None:
    """Who sent an alert, as far as the receiver can establish; None when it cannot.

    Behind Cloudflare Tunnel the TCP peer is the cloudflared connector, and
    Cloudflare names the sender in ``CF-Connecting-IP``. That header is believed
    only when the peer is one of ``tunnel_peers``. From any other peer it is
    ignored and the peer is the source, so no caller becomes TradingView by
    setting a header.
    """
    peer_address = normalise_ip(peer)
    if peer_address is None:
        return None
    if peer_address in {normalise_ip(address) for address in tunnel_peers}:
        return normalise_ip(cf_connecting_ip)
    return peer_address


def is_allowed_source(remote_ip: str | None) -> bool:
    """Whether a request came from a published TradingView address.

    The edge allowlist (Cloudflare WAF) is the first layer. state-api's webhook
    route calls this as the second, on the address ``alert_source`` establishes,
    because an edge rule can be edited or disabled.
    """
    return normalise_ip(remote_ip) in TRADINGVIEW_SOURCE_IPS
