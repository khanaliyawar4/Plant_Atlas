from __future__ import annotations

import datetime as _dt
import logging
import os
from pathlib import Path
from typing import Any

import orjson

log = logging.getLogger(__name__)

class ProgressFile:

    def __init__(self, tsv_path: Path):
        self.path = tsv_path.with_suffix(tsv_path.suffix + ".progress")
        self._seen: set[str] = set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                pmcid = line.strip()
                if pmcid:
                    self._seen.add(pmcid)
            log.info("resume: loaded %d previously-processed PMCIDs from %s",
                     len(self._seen), self.path)

    def has(self, pmcid: str) -> bool:
        return pmcid in self._seen

    def mark(self, pmcid: str) -> None:
        if pmcid in self._seen:
            return
        self._seen.add(pmcid)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(pmcid + "\n")
            f.flush()
            os.fsync(f.fileno())

    @property
    def count(self) -> int:
        return len(self._seen)

class JsonlLogger:

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._f = open(self.path, "ab")

    def event(self, kind: str, **fields: Any) -> None:
        rec = {
            "ts":   _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds"),
            "kind": kind,
            **fields,
        }
        self._f.write(orjson.dumps(rec))
        self._f.write(b"\n")

    def flush(self) -> None:
        self._f.flush()

    def close(self) -> None:
        try:
            self._f.flush()
            self._f.close()
        except Exception:
            pass

class TsvAppender:

    def __init__(self, path: Path, header: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        need_header = (not path.exists()) or path.stat().st_size == 0
        self._f = open(self.path, "a", encoding="utf-8", newline="")
        if need_header:
            self._f.write(header + "\n")
            self._f.flush()
            os.fsync(self._f.fileno())

    def append_block(self, text: str) -> None:
        if not text:
            return
        if not text.endswith("\n"):
            text = text + "\n"
        self._f.write(text)
        self._f.flush()
        os.fsync(self._f.fileno())

    def close(self) -> None:
        try:
            self._f.flush()
            self._f.close()
        except Exception:
            pass
