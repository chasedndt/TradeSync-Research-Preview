"""One macro headline: its shape, reading it from an RSS or Atom item, and its keyword sentiment.

Moved out of ``app/macro_feed.py`` unchanged. ``MacroHeadline`` lives here with
the parser that builds it, which is what lets the feed service import both
without the two modules importing each other; ``app.macro_feed`` re-exports it.
The sentiment is a deliberately simple keyword count, context for a reader and
never an input to scoring.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

# The feed's own logger name, so moving the parser changes no log line.
logger = logging.getLogger("app.macro_feed")


@dataclass
class MacroHeadline:
    """A single macro news headline."""
    title: str
    source: str
    category: str
    url: str
    published_at: Optional[str] = None
    summary: Optional[str] = None
    sentiment: Optional[str] = None  # "bullish", "bearish", "neutral", None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def parse_item(
    item: ET.Element,
    source: Dict[str, str]
) -> Optional[MacroHeadline]:
    """Parse an RSS item or Atom entry into a MacroHeadline."""
    try:
        # Try RSS 2.0 format first
        title = item.findtext("title")
        link = item.findtext("link")
        pub_date = item.findtext("pubDate")
        description = item.findtext("description")

        # Try Atom format if RSS didn't work
        if not title:
            title = item.findtext("{http://www.w3.org/2005/Atom}title")
        if not link:
            link_elem = item.find("{http://www.w3.org/2005/Atom}link")
            if link_elem is not None:
                link = link_elem.get("href")
        if not pub_date:
            pub_date = item.findtext("{http://www.w3.org/2005/Atom}published")
            if not pub_date:
                pub_date = item.findtext("{http://www.w3.org/2005/Atom}updated")
        if not description:
            description = item.findtext("{http://www.w3.org/2005/Atom}summary")

        if not title or not link:
            return None

        # Basic sentiment detection (very simple MVP)
        sentiment = detect_sentiment(title, description)

        return MacroHeadline(
            title=title.strip(),
            source=source["name"],
            category=source.get("category", "general"),
            url=link.strip(),
            published_at=pub_date,
            summary=description[:200] if description else None,
            sentiment=sentiment
        )

    except Exception as e:
        logger.debug(f"Failed to parse item: {e}")
        return None


def detect_sentiment(
    title: str,
    description: Optional[str] = None
) -> Optional[str]:
    """
    Very basic keyword-based sentiment detection.

    This is a simple MVP - could be enhanced with ML models later.
    """
    text = (title + " " + (description or "")).lower()

    bullish_keywords = [
        "surge", "rally", "bullish", "soar", "jump", "gain",
        "breakout", "all-time high", "ath", "pump", "moon",
        "adoption", "institutional", "approval", "etf approved"
    ]

    bearish_keywords = [
        "crash", "plunge", "bearish", "drop", "fall", "dump",
        "sell-off", "selloff", "collapse", "fear", "panic",
        "hack", "exploit", "scam", "fraud", "ban", "regulation"
    ]

    bullish_count = sum(1 for kw in bullish_keywords if kw in text)
    bearish_count = sum(1 for kw in bearish_keywords if kw in text)

    if bullish_count > bearish_count and bullish_count >= 1:
        return "bullish"
    elif bearish_count > bullish_count and bearish_count >= 1:
        return "bearish"
    else:
        return "neutral"
