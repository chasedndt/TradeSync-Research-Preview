"""What the Hyperliquid market stream has delivered: asset contexts, full-precision books and candles.

Pure state; the socket lives in ``market_stream``. Every reading keeps the local
time it was received, and freshness is judged on that time alone. Payloads are
kept as the venue sent them and parsed only when a poll loop takes one, because
a busy book is replaced many times between two polls.

A reading is only ever replaced by a newer one. A REST resync is filed with the
time its request *started*, so a stream message that arrived while the request
was in flight is never overwritten by the older snapshot.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .candles import SUPPORTED_INTERVALS

CONTEXT = "activeAssetCtx"
BOOK = "l2Book"
CANDLE = "candle"
DATA_CHANNELS = (CONTEXT, BOOK, CANDLE)
WEBSOCKET = "websocket"
REST_RESYNC = "rest_resync"


@dataclass(frozen=True)
class Reading:
    received_ms: int
    data: Mapping[str, Any]
    source: str


def _finite(value: Any) -> float | None:
    """A finite number, whether the venue sent it as a number or as a numeric string."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class MarketStreamState:
    """The newest reading per coin for each channel, and the recent candles per coin and interval."""

    def __init__(self, coins: Iterable[str], candle_intervals: Iterable[str] = ("1m",), candle_keep: int = 300) -> None:
        self.coins = list(dict.fromkeys(coins))
        self.candle_intervals = tuple(candle_intervals)
        unsupported = [i for i in self.candle_intervals if i not in SUPPORTED_INTERVALS]
        if unsupported:
            raise ValueError(f"unsupported candle interval(s): {', '.join(unsupported)}")
        self.candle_keep = max(1, int(candle_keep))
        self._coin_set = set(self.coins)
        self._contexts: dict[str, Reading] = {}
        self._books: dict[str, Reading] = {}
        # (coin, interval) -> {open_ms: (received_ms, candle)}
        self._candles: dict[tuple[str, str], dict[int, tuple[int, Mapping[str, Any]]]] = {}
        self.last_message_ms: int | None = None
        self.counts: dict[str, int] = {}

    # --- websocket messages -------------------------------------------------

    def ingest(self, message: Any, received_ms: int) -> str | None:
        """File one decoded message. Returns its channel, or None when a data message was not usable."""
        if not isinstance(message, Mapping) or not isinstance(message.get("channel"), str):
            return None
        channel = message["channel"]
        self.last_message_ms = received_ms
        data = message.get("data")
        if channel == CONTEXT:
            filed = self._file_context(data, received_ms, WEBSOCKET)
        elif channel == BOOK:
            filed = self._file_book(data, received_ms, WEBSOCKET)
        elif channel == CANDLE:
            filed = self._file_candle(data, received_ms) is not None
        else:
            filed = True  # pong, subscriptionResponse, error: not data, returned for the transport to act on
        key = channel if filed else f"{channel}_unusable"
        self.counts[key] = self.counts.get(key, 0) + 1
        return channel if filed else None

    def _file_context(self, data: Any, received_ms: int, source: str) -> bool:
        if not isinstance(data, Mapping) or data.get("coin") not in self._coin_set:
            return False
        ctx = data.get("ctx")
        if not isinstance(ctx, Mapping) or _finite(ctx.get("markPx")) is None or _finite(ctx.get("oraclePx")) is None:
            return False
        return self._replace(self._contexts, data["coin"], Reading(received_ms, dict(ctx), source))

    def _file_book(self, data: Any, received_ms: int, source: str) -> bool:
        if not isinstance(data, Mapping) or data.get("coin") not in self._coin_set:
            return False
        levels = data.get("levels")
        if not isinstance(levels, list) or len(levels) != 2 or not all(isinstance(side, list) for side in levels):
            return False
        return self._replace(self._books, data["coin"], Reading(received_ms, dict(data), source))

    def _file_candle(self, data: Any, received_ms: int) -> int | None:
        if not isinstance(data, Mapping):
            return None
        coin, interval, open_ms = data.get("s"), data.get("i"), data.get("t")
        if coin not in self._coin_set or interval not in self.candle_intervals:
            return None
        if not isinstance(open_ms, int) or isinstance(open_ms, bool):
            return None
        if any(_finite(data.get(key)) is None for key in ("o", "h", "l", "c")):
            return None
        series = self._candles.setdefault((coin, interval), {})
        held = series.get(open_ms)
        if held is not None and held[0] > received_ms:
            return None
        series[open_ms] = (received_ms, dict(data))
        if len(series) > self.candle_keep:
            for old in sorted(series)[: len(series) - self.candle_keep]:
                del series[old]
        return open_ms

    @staticmethod
    def _replace(store: dict[str, Reading], coin: str, reading: Reading) -> bool:
        held = store.get(coin)
        if held is not None and held.received_ms > reading.received_ms:
            return False
        store[coin] = reading
        return True

    # --- REST resync ----------------------------------------------------------

    def seed_context(self, coin: str, ctx: Mapping[str, Any], requested_ms: int) -> bool:
        return self._file_context({"coin": coin, "ctx": ctx}, requested_ms, REST_RESYNC)

    def seed_book(self, coin: str, book: Mapping[str, Any], requested_ms: int) -> bool:
        return self._file_book({**book, "coin": coin}, requested_ms, REST_RESYNC)

    def seed_candles(self, coin: str, interval: str, rows: Iterable[Any], requested_ms: int) -> int:
        """File REST candles for a subscribed interval; returns how many were taken."""
        taken = 0
        for row in rows or ():
            if isinstance(row, Mapping) and self._file_candle({**row, "s": coin, "i": interval}, requested_ms) is not None:
                taken += 1
        return taken

    # --- readings -------------------------------------------------------------

    def context(self, coin: str, now_ms: int, fresh_ms: int) -> Reading | None:
        return self._fresh(self._contexts.get(coin), now_ms, fresh_ms)

    def book(self, coin: str, now_ms: int, fresh_ms: int) -> Reading | None:
        return self._fresh(self._books.get(coin), now_ms, fresh_ms)

    @staticmethod
    def _fresh(reading: Reading | None, now_ms: int, fresh_ms: int) -> Reading | None:
        return reading if reading is not None and now_ms - reading.received_ms <= fresh_ms else None

    def candles(self, coin: str, interval: str) -> list[Mapping[str, Any]]:
        series = self._candles.get((coin, interval), {})
        return [series[open_ms][1] for open_ms in sorted(series)]

    def newest_candle_open_ms(self, coin: str, interval: str) -> int | None:
        series = self._candles.get((coin, interval))
        return max(series) if series else None

    def candle_received_ms(self, coin: str, interval: str) -> int | None:
        series = self._candles.get((coin, interval))
        return max(received for received, _ in series.values()) if series else None

    # --- freshness ------------------------------------------------------------

    def freshness(self, now_ms: int, fresh_ms: int) -> dict[str, Any]:
        """Per channel: how many coins are fresh, which are stale or missing, and the newest and oldest ages."""

        def channel(received: Mapping[str, int], bound_ms: int) -> dict[str, Any]:
            ages = {coin: max(0, now_ms - ms) for coin, ms in received.items()}
            return {
                "fresh_after_ms": bound_ms,
                "fresh": sum(1 for age in ages.values() if age <= bound_ms),
                "stale": sorted(coin for coin, age in ages.items() if age > bound_ms),
                "missing": [coin for coin in self.coins if coin not in received],
                "newest_age_ms": min(ages.values(), default=None),
                "oldest_age_ms": max(ages.values(), default=None),
            }

        candle_received: dict[str, int] = {}
        for (coin, interval), series in self._candles.items():
            newest = max(received for received, _ in series.values())
            candle_received[coin] = max(candle_received.get(coin, newest), newest)
        # A candle is updated only when its market trades, so it is judged against its own interval, not the book bound.
        candle_bound = max([fresh_ms] + [SUPPORTED_INTERVALS[i] for i in self.candle_intervals])
        return {
            "last_message_age_ms": None if self.last_message_ms is None else max(0, now_ms - self.last_message_ms),
            "channels": {
                CONTEXT: channel({c: r.received_ms for c, r in self._contexts.items()}, fresh_ms),
                BOOK: channel({c: r.received_ms for c, r in self._books.items()}, fresh_ms),
                CANDLE: channel(candle_received, candle_bound),
            },
        }
