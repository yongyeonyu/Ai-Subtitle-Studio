# Version: 04.00.10
# Phase: PHASE2
"""Lightweight queue state model shared by table and sidebar views."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


QUEUE_SNAPSHOT_KEYS = ("row", "status", "file", "info", "duration", "eta")


def normalize_queue_row_snapshot(row: int, payload: dict | None = None) -> dict[str, object]:
    data = dict({} if payload is None else payload)
    row_idx = int(data.get("row", row) if data.get("row", row) is not None else row)
    return {
        "row": row_idx,
        "status": str(data.get("status", data.get("statusRaw", "")) or ""),
        "file": str(data.get("file", data.get("fileRaw", "")) or ""),
        "info": str(data.get("info", data.get("infoRaw", "")) or ""),
        "duration": str(data.get("duration", "") or ""),
        "eta": str(data.get("eta", data.get("etaRaw", "")) or ""),
    }


@dataclass(frozen=True)
class QueueStateModel:
    header: str = ""
    rows: tuple[dict[str, object], ...] = field(default_factory=tuple)

    @classmethod
    def empty(cls, header: str = "") -> "QueueStateModel":
        return cls(header=str(header or ""), rows=())

    @classmethod
    def from_snapshots(cls, rows: Iterable[dict] | None, *, header: str = "") -> "QueueStateModel":
        source_rows = [] if rows is None else rows
        normalized = [
            normalize_queue_row_snapshot(idx, row)
            for idx, row in enumerate(source_rows)
        ]
        return cls(header=str(header or ""), rows=tuple(normalized))

    def with_header(self, header: str) -> "QueueStateModel":
        return QueueStateModel(header=str(header or ""), rows=self.rows)

    def with_row(self, row: int, payload: dict | None) -> "QueueStateModel":
        row_idx = max(0, int(row))
        rows = [dict(item) for item in self.rows]
        while len(rows) <= row_idx:
            rows.append(normalize_queue_row_snapshot(len(rows), None))
        rows[row_idx] = normalize_queue_row_snapshot(row_idx, payload)
        return QueueStateModel(header=self.header, rows=tuple(rows))

    def row_snapshot(self, row: int) -> dict[str, object]:
        row_idx = int(row)
        if row_idx < 0 or row_idx >= len(self.rows):
            return {}
        return dict(self.rows[row_idx])

    def row_count(self) -> int:
        return len(self.rows)

    def snapshots(self) -> list[dict[str, object]]:
        return [dict(row) for row in self.rows]


__all__ = [
    "QUEUE_SNAPSHOT_KEYS",
    "QueueStateModel",
    "normalize_queue_row_snapshot",
]
