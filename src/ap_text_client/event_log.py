from __future__ import annotations

import logging
from pathlib import Path

from .events import HintsUpdated, ReceivedEvent, SentEvent, StatusEvent
from .names import Names

LOGGER_NAME = "ap_text_client.events"
DEFAULT_LOG_FILE = Path.home() / ".local" / "state" / "ap-text-client" / "events.log"


def default_log_file() -> Path:
    return DEFAULT_LOG_FILE


def setup_event_logger(log_file: Path) -> logging.Logger:
    """Configure a dedicated logger that appends events to ``log_file``.
    Does not propagate to root, so its output never reaches the stderr handler
    (which Textual swallows in TUI mode anyway)."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for existing in logger.handlers:
        if (
            isinstance(existing, logging.FileHandler)
            and Path(existing.baseFilename) == log_file.resolve()
        ):
            return logger
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger


class EventLogger:
    """Formats domain events and writes them through the stdlib logger
    configured by :func:`setup_event_logger`."""

    def __init__(self, names: Names, logger: logging.Logger | None = None) -> None:
        self.names = names
        self._logger = logger or logging.getLogger(LOGGER_NAME)

    def sent(self, ev: SentEvent) -> None:
        item = self.names.item_name(ev.item.item_id, ev.item.receiver_slot)
        loc = self.names.location_name(ev.item.location_id, ev.item.sender_slot)
        receiver = self.names.players.alias(ev.item.receiver_slot)
        self._logger.info(
            "SENT     %s -> %s (slot %d) @ %s",
            item,
            receiver,
            ev.item.receiver_slot,
            loc,
        )

    def received(self, ev: ReceivedEvent) -> None:
        item = self.names.item_name(ev.item.item_id, ev.item.receiver_slot)
        loc = self.names.location_name(ev.item.location_id, ev.item.sender_slot)
        sender = self.names.players.alias(ev.item.sender_slot)
        self._logger.info(
            "RECEIVED %s <- %s (slot %d) @ %s",
            item,
            sender,
            ev.item.sender_slot,
            loc,
        )

    def hints(self, ev: HintsUpdated) -> None:
        total = len(ev.hints)
        found = sum(1 for h in ev.hints if h.found)
        self._logger.info("HINTS    %d entries (%d found)", total, found)

    def status(self, ev: StatusEvent) -> None:
        self._logger.info("STATUS   [%s] %s", ev.kind, ev.text)
