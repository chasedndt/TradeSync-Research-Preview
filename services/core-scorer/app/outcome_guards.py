"""Which candle interval a window may be measured at, and when a result is refused.

Moved out of ``outcome_job.py`` unchanged. The measuring intervals live here
with the guards because the guards exist entirely to protect the difference
between them:

- ``guard_unrequested`` keeps "no candles" from being written as a final
  ``insufficient_candles`` when the window was never actually asked for — a gap
  in our own request is not a gap in the venue's history;
- ``guard_coarse`` labels a result measured on 5-minute candles, and refuses it
  outright for horizons short enough that a late entry would change the answer;
- ``fall_back_per_window`` takes the coarse result only for the windows the fine
  series could not cover, window by window rather than batch by batch.

``outcome_job`` re-exports every name here, so existing imports keep working.
"""

from __future__ import annotations

import os
from dataclasses import replace

from tradesync_core.outcomes import HorizonOutcome

from .outcome_windows import FetchRange, window_was_requested

# The candle interval used to measure. One minute keeps the shortest horizon
# meaningful; a coarser interval would round a 15 minute window badly.
OUTCOME_CANDLE_INTERVAL = os.getenv("OUTCOME_CANDLE_INTERVAL", "1m")
# Hyperliquid stops serving 1-minute candles after a few days but keeps 5-minute
# ones. A window older than that is measured at 5m if its horizon is long enough
# for the coarser entry not to matter; the row says so.
COARSE_CANDLE_INTERVAL = os.getenv("OUTCOME_COARSE_CANDLE_INTERVAL", "5m")
INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
CANDLE_SECONDS = INTERVAL_SECONDS[OUTCOME_CANDLE_INTERVAL]
COARSE_SECONDS = INTERVAL_SECONDS[COARSE_CANDLE_INTERVAL]
# Entry is the first candle at or after the signal, so a 5m candle can place it
# up to five minutes late. On a 60m window that is at most 8% of the horizon;
# on a 15m window it is a third, which is not the same measurement.
MIN_HORIZON_FOR_COARSE = 60

NOT_FETCHED = "candles were not fetched for this window on this pass"
NO_FINE_HISTORY = (
    f"venue no longer serves {OUTCOME_CANDLE_INTERVAL} candles for this window "
    f"and {COARSE_CANDLE_INTERVAL} is too coarse for a {{horizon}}m horizon"
)
MEASURED_COARSE = (
    f"measured at {COARSE_CANDLE_INTERVAL} candles: venue no longer serves "
    f"{OUTCOME_CANDLE_INTERVAL} history for this window"
)

EMPTY_AT_FINE = "no candles cover this window"


def guard_unrequested(
    horizons: list[HorizonOutcome], fetched: list[FetchRange], opened_at_s: int
) -> list[HorizonOutcome]:
    """Turn "no candles" into "not fetched" wherever the window was not asked for.

    ``insufficient_candles`` is final. It may only be written when the venue
    was asked for the whole window and answered; otherwise the row stays
    pending and is retried, which is the difference between a gap in the
    venue's history and a gap in our own request.
    """
    out = []
    for horizon in horizons:
        if horizon.status == "insufficient_candles" and not window_was_requested(
            fetched, opened_at_s, horizon.horizon_minutes
        ):
            horizon = replace(horizon, status="pending", reason=NOT_FETCHED, candles_used=0)
        out.append(horizon)
    return out


def guard_coarse(horizons: list[HorizonOutcome], interval: str) -> list[HorizonOutcome]:
    """Say when a measurement came from coarse candles, and refuse it when it matters.

    A horizon measured at the coarse interval carries that fact in its reason,
    so nobody later averages a 5m-entry result with a 1m-entry one without
    knowing. A horizon shorter than ``MIN_HORIZON_FOR_COARSE`` is not measured
    coarsely at all: the entry could be a third of the window late.
    """
    if interval == OUTCOME_CANDLE_INTERVAL:
        return horizons
    out = []
    for horizon in horizons:
        if horizon.horizon_minutes < MIN_HORIZON_FOR_COARSE and horizon.status != "pending":
            horizon = HorizonOutcome(
                horizon_minutes=horizon.horizon_minutes,
                status="insufficient_candles",
                reason=NO_FINE_HISTORY.format(horizon=horizon.horizon_minutes),
            )
        elif horizon.status == "measured":
            horizon = replace(horizon, reason=MEASURED_COARSE)
        out.append(horizon)
    return out


def fall_back_per_window(
    fine: list[HorizonOutcome], coarse: list[HorizonOutcome] | None
) -> list[HorizonOutcome]:
    """Use the coarse result only for horizons the fine series could not cover.

    A horizon that measured at 1m keeps its 1m result. One that found no 1m
    candles takes the 5m result if there is one — after ``guard_coarse`` has
    labelled it or refused it. With no coarse series the fine verdict stands.
    """
    if coarse is None:
        return fine
    by_horizon = {h.horizon_minutes: h for h in guard_coarse(coarse, COARSE_CANDLE_INTERVAL)}
    out = []
    for horizon in fine:
        empty = horizon.status == "insufficient_candles" and horizon.reason == EMPTY_AT_FINE
        out.append(by_horizon.get(horizon.horizon_minutes, horizon) if empty else horizon)
    return out
