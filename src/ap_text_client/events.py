from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ItemRef:
    item_id: int
    location_id: int
    sender_slot: int     # world the location lives in
    receiver_slot: int   # world the item lives in
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
class HintEvent:
    ts: datetime
    item: ItemRef
    found: bool


@dataclass(frozen=True)
class StatusEvent:
    ts: datetime
    kind: str
    text: str


Event = SentEvent | ReceivedEvent | HintEvent | StatusEvent
