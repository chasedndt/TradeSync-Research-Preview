"""An append-only journal whose every record is on disk before ``append`` returns.

The signer has no database, and neither does exec-hl-svc. Both still need a few
facts to outlive a restart: which approvals have already been signed against,
the highest nonce ever handed out, and which orders were sent without a
definite answer. A fact that is only in memory is forgotten by exactly the crash
that makes it matter, so each is written here first and acted on second.

**Durable before acknowledged.** ``append`` writes one JSON line, then
``os.fsync``s the file, and only then returns. A caller that acts on a record
after ``append`` returned can rely on it surviving a power cut. On POSIX the
directory is also synced when the file is first created, so the file itself is
not lost; Windows has no directory sync and none is attempted there.

**A torn tail was never acknowledged.** A crash in the middle of ``append`` can
leave a partial last line. Nobody acted on it, because ``append`` did not return,
so ``records`` ignores it and the next ``append`` cuts it off before writing.
A malformed line anywhere *before* the tail is different: something other than
this class wrote to the file, and ``records`` raises rather than guessing which
lines to believe.

**One writer.** A lock serialises appends within a process. The services that
use a journal run a single worker, and a journal must never be shared between
processes or containers: each gets its own volume.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Mapping

# One record is a small fact, never a payload. A bound keeps a caller from
# turning a journal into a store for something it should not hold.
MAX_RECORD_BYTES = 4096


class JournalError(RuntimeError):
    """The journal cannot be written or cannot be trusted; the caller must refuse, not continue."""


class DurableJournal:
    """Append-only JSON lines at ``path``, synced to disk on every append."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def append(self, record: Mapping[str, Any]) -> None:
        """Write one record and return only once it is on disk."""
        try:
            line = json.dumps(dict(record), sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        except (TypeError, ValueError) as exc:
            raise JournalError(f"record is not plain JSON: {type(exc).__name__}") from exc
        encoded = line.encode("utf-8")
        if len(encoded) > MAX_RECORD_BYTES:
            raise JournalError(f"record is {len(encoded)} bytes; a journal record is at most {MAX_RECORD_BYTES}")
        with self._lock:
            try:
                created = not self.path.exists()
                flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
                fd = os.open(self.path, flags, 0o600)
                try:
                    self._cut_torn_tail(fd)
                    os.lseek(fd, 0, os.SEEK_END)
                    view = memoryview(encoded)
                    while view:
                        view = view[os.write(fd, view):]
                    os.fsync(fd)
                finally:
                    os.close(fd)
                if created:
                    _sync_directory(self.path.parent)
            except OSError as exc:
                raise JournalError(f"journal at {self.path.name} could not be written: {type(exc).__name__}") from exc

    def records(self) -> list[dict[str, Any]]:
        """Every acknowledged record, oldest first; an absent file holds none."""
        with self._lock:
            try:
                data = self.path.read_bytes()
            except FileNotFoundError:
                return []
            except OSError as exc:
                raise JournalError(f"journal at {self.path.name} could not be read: {type(exc).__name__}") from exc
        lines = data.split(b"\n")
        # The piece after the last newline is empty for a clean file, or a torn
        # append that never returned.
        complete = lines[:-1]
        out: list[dict[str, Any]] = []
        for number, raw in enumerate(complete, start=1):
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise JournalError(f"journal line {number} is not a record this journal wrote") from exc
            if not isinstance(value, dict):
                raise JournalError(f"journal line {number} is not a record this journal wrote")
            out.append(value)
        return out

    @staticmethod
    def _cut_torn_tail(fd: int) -> None:
        """Truncate a partial last line left by an append that never returned."""
        size = os.lseek(fd, 0, os.SEEK_END)
        if size == 0:
            return
        os.lseek(fd, size - 1, os.SEEK_SET)
        if os.read(fd, 1) == b"\n":
            return
        # Walk back to the last newline; everything after it was never acknowledged.
        position = size
        chunk = 4096
        keep = 0
        while position > 0:
            start = max(0, position - chunk)
            os.lseek(fd, start, os.SEEK_SET)
            block = os.read(fd, position - start)
            index = block.rfind(b"\n")
            if index >= 0:
                keep = start + index + 1
                break
            position = start
        os.ftruncate(fd, keep)
        os.fsync(fd)


def _sync_directory(directory: Path) -> None:
    """Make a new file's directory entry durable where the platform allows it."""
    if os.name == "nt":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
