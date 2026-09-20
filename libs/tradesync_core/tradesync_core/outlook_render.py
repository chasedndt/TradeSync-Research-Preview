"""The outlook as written text and as spoken lines, for an edition.

Every sentence comes from the outlook object, which comes from measurements.
"""

from __future__ import annotations

from typing import Any, Mapping


def _when(minutes: int) -> str:
    if minutes < 0:
        return "under way"
    if minutes < 60:
        return f"in {minutes}m"
    if minutes < 48 * 60:
        return f"in {minutes // 60}h {minutes % 60}m"
    return f"in {minutes // 1440}d"


def outlook_text(outlook: Mapping[str, Any] | None) -> list[str]:
    if not outlook:
        return []
    lines = ["## Market outlook", "", outlook["breadth"]["summary"], ""]
    for note in (outlook.get("notes") or [])[1:]:
        lines.append(f"- {note}")
    events = outlook.get("key_events") or []
    if events:
        lines += ["", "### Scheduled this week"]
        for e in events:
            lines.append(f"- **{e['title']}** ({e.get('country') or ''}, {e.get('impact') or ''}) {_when(e['minutes_until'])}")
            for g in (e.get("guidance") or [])[:2]:
                lines.append(f"  - {g}")
            for a in (e.get("articles") or [])[:2]:
                lines.append(f"  - [{a.get('title')}]({a.get('url')}) · {a.get('domain')}")
    lines.append("")
    return lines


def outlook_narration(outlook: Mapping[str, Any] | None) -> list[str]:
    if not outlook:
        return []
    out = [outlook["breadth"]["summary"]]
    for e in (outlook.get("key_events") or [])[:3]:
        if e["minutes_until"] > 48 * 60:
            continue
        out.append(f"{e['title']}, {_when(e['minutes_until'])}.")
        if e.get("guidance"):
            out.append(e["guidance"][0])
    return out


def _horizon(context: Mapping[str, Any], symbol: str, key: str) -> Mapping[str, Any]:
    rows = ((context.get(symbol) or {}).get("outlook") or {}).get("horizons") or []
    return next((row for row in rows if row.get("key") == key), {})


def _price(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "an unconfirmed level"
    if abs(float(value)) >= 1000:
        return f"{float(value):,.0f} dollars"
    return f"{float(value):,.3f}".rstrip("0").rstrip(".") + " dollars"


def _trend_words(row: Mapping[str, Any], subject: str) -> str:
    if not row or not row.get("available") or not row.get("trend"):
        return f"{subject} does not yet have enough retained history for a reliable description"
    state = str((row.get("trend") or {}).get("state") or "unknown")
    phrases = {
        "above_rising": f"{subject} is above an average that is still climbing",
        "above_falling": f"{subject} has recovered above its average, although that average is still falling",
        "below_rising": f"{subject} has slipped below an average that is still climbing",
        "below_falling": f"{subject} remains below a falling average",
    }
    return phrases.get(state, f"{subject} has a mixed technical picture")


def _level(row: Mapping[str, Any], key: str, fallback: Any = None) -> Any:
    value = (row.get("levels") or {}).get(key) if row else None
    return fallback if value is None else value


def _lead(outlook: Mapping[str, Any], symbol: str) -> Mapping[str, Any]:
    return next((row for row in (outlook.get("leads") or []) if row.get("symbol") == symbol), {})


def _direction_agreement(day: Mapping[str, Any], four_hour: Mapping[str, Any]) -> str:
    if day.get("lean") == "up" and four_hour.get("lean") == "up":
        return "The daily and four-hour charts are improving together, so a pullback can be watched for support instead of chased after a large candle."
    if day.get("lean") == "down" and four_hour.get("lean") == "down":
        return "The daily and four-hour charts are weakening together, so rallies remain suspect until price can reclaim resistance."
    return "The daily and four-hour charts do not yet agree, which favours patience near the edges of the range rather than a directional trade through its middle."


def _relative_strength(btc_day: Mapping[str, Any], eth_day: Mapping[str, Any]) -> str:
    btc_change = (btc_day.get("momentum") or {}).get("change_pct")
    eth_change = (eth_day.get("momentum") or {}).get("change_pct")
    if not isinstance(btc_change, (int, float)) or not isinstance(eth_change, (int, float)):
        return "The present evidence cannot make a reliable Ethereum-versus-Bitcoin comparison."
    if abs(float(eth_change) - float(btc_change)) < 0.25:
        return "Ethereum and Bitcoin are moving at a similar pace, so there is no clear rotation signal between them."
    if eth_change > btc_change:
        return "Ethereum is recovering faster than Bitcoin today. That is an early sign of improving risk appetite, but it is not enough on its own to call a broad altcoin run."
    return "Bitcoin is holding up better than Ethereum today. That keeps the market defensive and makes broad altcoin exposure less convincing."


def integrated_narration(outlook: Mapping[str, Any], theses: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Six evidence-bound chapters for the interactive edition player.

    This deliberately replaces the old one-card-per-symbol spoken list. It
    speaks the market in the order a trader needs it and keeps scenario
    geometry until the final chapter. No missing feed is silently invented.
    """
    context = outlook.get("horizon_context") or {}
    btc_month, btc_week = _horizon(context, "BTC-PERP", "1m"), _horizon(context, "BTC-PERP", "1w")
    btc_day, btc_four = _horizon(context, "BTC-PERP", "1d"), _horizon(context, "BTC-PERP", "4h")
    eth_week, eth_day = (_horizon(context, "ETH-PERP", key) for key in ("1w", "1d"))
    btc_lead, eth_lead = _lead(outlook, "BTC-PERP"), _lead(outlook, "ETH-PERP")
    btc_thesis, eth_thesis = theses.get("BTC-PERP") or {}, theses.get("ETH-PERP") or {}
    btc_anchors, eth_anchors = btc_thesis.get("anchors") or {}, eth_thesis.get("anchors") or {}
    btc_last = ((context.get("BTC-PERP") or {}).get("outlook") or {}).get("last_close") or btc_lead.get("last") or btc_anchors.get("last_close")
    support = _level(btc_day, "recent_low", btc_lead.get("low_24h") or btc_anchors.get("low_24h"))
    resistance = _level(btc_day, "recent_high", btc_lead.get("high_24h") or btc_anchors.get("high_24h"))
    pivot = _level(btc_day, "trend_flips_at", support)
    month_above = str((btc_month.get("trend") or {}).get("state") or "").startswith("above")
    week_above = str((btc_week.get("trend") or {}).get("state") or "").startswith("above")
    alignment = (
        "The larger trend and the current week are telling a broadly consistent story."
        if month_above == week_above else
        "The larger trend and the current week are not yet telling the same story, so this market should not be reduced to a one-word bullish or bearish label."
    )
    lines = [
        f"Start with the larger picture. Bitcoin is trading near {_price(btc_last)}. "
        f"On the monthly chart, {_trend_words(btc_month, 'price')}. On the weekly chart, {_trend_words(btc_week, 'price')}. {alignment}",
        f"Bitcoin this week. The important decision area runs from support near {_price(support)} to resistance near {_price(resistance)}. "
        f"Holding above {_price(pivot)} keeps the recovery credible, while a sustained break above {_price(resistance)} would show that buyers have accepted higher prices. "
        f"A return below {_price(support)} would damage that recovery. {_direction_agreement(btc_day, btc_four)}",
        f"Ethereum and the rest of the market. {_trend_words(eth_week, 'Ethereum on the weekly chart')}. "
        f"{_relative_strength(btc_day, eth_day)} Ethereum is trading near {_price(eth_lead.get('last') or eth_anchors.get('last_close'))}.",
    ]
    alts = [(symbol, (thesis.get("structure") or {}).get("direction") or "NONE") for symbol, thesis in theses.items()
            if symbol not in ("BTC-PERP", "ETH-PERP")]
    longs = [symbol.replace("-PERP", "") for symbol, direction in alts if direction == "LONG"]
    shorts = [symbol.replace("-PERP", "") for symbol, direction in alts if direction == "SHORT"]
    if len(longs) > len(shorts):
        alt_tone = "More tracked altcoins are improving than weakening"
    elif len(shorts) > len(longs):
        alt_tone = "More tracked altcoins are weakening than improving"
    else:
        alt_tone = "The tracked altcoin group is evenly split"
    leaders = ", ".join(longs[:4]) if longs else "none"
    laggards = ", ".join(shorts[:4]) if shorts else "none"
    lines.append(f"Altcoin context. {alt_tone}. The clearest improving paper reads are {leaders}; the clearest weakening reads are {laggards}. "
                 "This is a breadth check, not an alt-season declaration, and none of these reads has earned permission to become a live trade.")
    events = outlook.get("key_events") or []
    if events:
        first = events[0]
        forecast = first.get("forecast") or "not supplied"
        previous = first.get("previous") or "not recorded"
        later = "; ".join(f"{event.get('title')}, {_when(int(event.get('minutes_until') or 0))}" for event in events[1:3])
        event_words = (f"The next scheduled event is {first.get('title')}, {_when(int(first.get('minutes_until') or 0))}. "
                       f"Its forecast is {forecast}, compared with a previous value of {previous}. "
                       "The result is not known in advance, so the plan is to watch whether Bitcoin holds support or clears resistance after the release rather than guess the number.")
        if later:
            event_words += f" Also on the calendar: {later}."
    else:
        event_words = "No scheduled market-moving event was retained in this edition. Unscheduled headlines can still move the market."
    lines.append("Catalysts and evidence limits. " + event_words
                 + " TradeSync does not yet hold authoritative ETF flow, Fear and Greed, total market cap, or volume-at-price value-area evidence, so the thesis does not pretend those inputs are present.")
    lines.append(f"The scenario map comes last. Strength is confirmed only if Bitcoin holds {_price(pivot)} and closes through {_price(resistance)} with the daily and four-hour charts improving together. "
                 f"If price remains between {_price(support)} and {_price(resistance)}, the market is still deciding and the middle of the range offers poor reward for directional risk. "
                 f"A sustained move below {_price(support)} proves the recovery idea wrong. The position drawing that now appears is explanatory paper geometry, not an order or a profitability claim.")
    return lines
