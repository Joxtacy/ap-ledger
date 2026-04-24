from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class HintStatus(IntEnum):
    UNSPECIFIED = 0
    NO_PRIORITY = 10
    AVOID = 20
    PRIORITY = 30
    FOUND = 40

    @classmethod
    def coerce(cls, value: object) -> "HintStatus":
        if isinstance(value, cls):
            return value
        try:
            return cls(int(value))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return cls.UNSPECIFIED


@dataclass(frozen=True)
class ItemRef:
    item_id: int
    location_id: int
    sender_slot: int
    receiver_slot: int
    flags: int


@dataclass(frozen=True)
class SentEvent:
    ts: datetime
    item: ItemRef


@dataclass(frozen=True)
class ReceivedEvent:
    ts: datetime
    item: ItemRef


@dataclass(frozen=True)
class HintRow:
    finding_slot: int
    receiving_slot: int
    item_id: int
    location_id: int
    found: bool
    entrance: str
    item_flags: int
    status: HintStatus

    @property
    def key(self) -> tuple[int, int]:
        return (self.finding_slot, self.location_id)


@dataclass(frozen=True)
class HintsUpdated:
    ts: datetime
    hints: tuple[HintRow, ...]


@dataclass(frozen=True)
class StatusEvent:
    ts: datetime
    kind: str
    text: str


Event = SentEvent | ReceivedEvent | HintsUpdated | StatusEvent
