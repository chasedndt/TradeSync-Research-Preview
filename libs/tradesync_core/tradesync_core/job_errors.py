"""Fleet job errors, made safe to store and plain to read.

A Hermes job's last error is whatever its script printed: a traceback, a
shell complaint, a delivery failure, sometimes the job's own report. Before
it leaves the host it is redacted (anything shaped like a token, key,
webhook or wallet recovery phrase) and cut to length. On the dashboard it is
reduced to one sentence naming the cause when the cause is recognisable.
"""

from __future__ import annotations

import re

from .bip39_words import WORD_SET as _BIP39_WORDS

MAX_ERROR_CHARS = 1500

_DISCORD_TOKEN = re.compile(r"[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,40}")
_PREFIXED_KEY = re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}")
_LABELLED = re.compile(r"(?i)\b(bearer|token|api[_-]?key|secret|password)(\s*[:=]\s*|\s+)([^\s\"',;]{8,})")
_WEBHOOK = re.compile(r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+")
_HEX_KEY = re.compile(r"\b0x[a-fA-F0-9]{64}\b")
_EXCEPTION_LINE = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Timeout)\b")

# A wallet recovery phrase: twelve or more BIP-39 words in a row. The shortest
# phrase a wallet issues is 12 words and the longest 24, so any run of 12 or more
# contains a whole phrase and the whole run goes. Between two words only what people
# write between them may appear: spaces, line breaks, commas, dashes, brackets,
# quotes, and numbering ("1." "2)" "#3"). A full stop or colon that is not part of
# numbering ends a sentence, and so does a run; so do a longer number and any word
# outside the list. A run must also hold at least nine different words: a random
# 12-word phrase repeats a word about three times in a hundred, while text such as
# "keep keep keep" is not a phrase at all.
SEED_PHRASE_MIN_WORDS = 12
SEED_PHRASE_MIN_DISTINCT = 9
_LETTERS = re.compile(r"[A-Za-z]+")
_SEPARATOR = r"[\s,;()\[\]'\"#*-]"
_WORD_GAP = re.compile(rf"{_SEPARATOR}*(?:\d{{1,2}}[.):]?{_SEPARATOR}*)?")


def _seed_phrase_spans(text: str) -> list[tuple[int, int]]:
    """Where runs that can hold a recovery phrase sit, first to last character."""
    spans: list[tuple[int, int]] = []
    start = end = 0
    run: list[str] = []

    def close() -> None:
        if len(run) >= SEED_PHRASE_MIN_WORDS and len(set(run)) >= SEED_PHRASE_MIN_DISTINCT:
            spans.append((start, end))

    for match in _LETTERS.finditer(text):
        word = match.group(0).lower()
        if word not in _BIP39_WORDS:
            close()
            run = []
            continue
        if run and _WORD_GAP.fullmatch(text, end, match.start()):
            run.append(word)
            end = match.end()
            continue
        close()
        start, end, run = match.start(), match.end(), [word]
    close()
    return spans


def redact_seed_phrases(text: str) -> str:
    """The text with every run of twelve or more BIP-39 words replaced by one ``[redacted]``.

    Known cost, as with the labelled secrets above: a written list of twelve words
    that all happen to be on the wordlist is redacted too. The list holds ordinary
    words ("market", "order", "long", "short") but none of "the", "a", "and", "of",
    "to", "is", so running prose breaks a run long before twelve.
    """
    for start, end in reversed(_seed_phrase_spans(text)):
        text = text[:start] + "[redacted]" + text[end:]
    return text


def redact(text: object, limit: int | None = MAX_ERROR_CHARS) -> str | None:
    """The text with secret-shaped substrings replaced, cut to ``limit`` characters (None: not cut); None when empty."""
    if text is None or text == "":
        return None
    out = str(text)
    out = _WEBHOOK.sub("https://discord.com/api/webhooks/[redacted]", out)
    out = _DISCORD_TOKEN.sub("[redacted]", out)
    out = _PREFIXED_KEY.sub("[redacted]", out)
    out = _LABELLED.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", out)
    out = _HEX_KEY.sub("[redacted]", out)
    out = redact_seed_phrases(out)
    return out if limit is None else out[:limit]


def diagnose(error: object) -> str | None:
    """One plain sentence on why a job failed, or the first meaningful line when the cause is unknown."""
    if error is None or error == "":
        return None
    text = str(error)
    if "\r" in text or "\\r'" in text or re.search(r"pipefail\s*:\s*invalid option", text):
        return "The script has Windows (CRLF) line endings, so bash cannot run it; it needs LF line endings."
    if "Temporary failure in name resolution" in text or "Name or service not known" in text:
        host = re.search(r"connect to host ([\w.-]+)", text)
        where = f" for {host.group(1)}" if host else ""
        return f"A network name lookup failed inside WSL{where}, so the job could not reach it."
    if "Quant Integrity Hold" in text:
        codes = re.findall(r"- `([a-z_]+)`", text)
        listed = ", ".join(codes) if codes else "see the health report"
        return f"Integrity hold ({listed}). The watchdog exits non-zero while any integrity issue stands."
    start = text.rfind("Traceback (most recent call last)")
    if start >= 0:
        lines = [line.strip() for line in text[start:].splitlines() if line.strip()]
        exception = next((line for line in reversed(lines) if _EXCEPTION_LINE.match(line)), None)
        if exception:
            return f"Python error: {exception[:200]}"
        files = re.findall(r'File "([^"]+)"', text)
        where = f" in {files[-1].rsplit('/', 1)[-1]}" if files else ""
        return f"Python error{where}; the recorded error was cut off before the exception line."
    code = re.search(r"exited with code (\d+)", text)
    if code and re.search(r'"ok"\s*:\s*true', text):
        return f"The script reported ok but exited with code {code.group(1)}."
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.lower().startswith(("script exited", "stdout:", "stderr:")):
            return stripped[:200]
    return text.strip()[:200] or None
