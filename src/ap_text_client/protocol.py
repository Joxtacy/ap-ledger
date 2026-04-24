from __future__ import annotations

import asyncio
import json
import logging
import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from .events import (
    Event,
    HintRow,
    HintStatus,
    HintsUpdated,
    ItemRef,
    ReceivedEvent,
    SentEvent,
    StatusEvent,
)
from .filters import is_self_status, is_sent_by_me, item_ref_from_packet
from .names import Names

logger = logging.getLogger("ap_text_client.protocol")

DEFAULT_PORT = 38281
UUID_FILE = Path.home() / ".config" / "ap-text-client" / "uuid"
LAST_SERVER_FILE = Path.home() / ".config" / "ap-text-client" / "last_server"


@dataclass
class ConnectionState:
    server_address: str
    slot_name: str
    password: str | None = None
    team: int = 0
    my_slot: int = -1
    seed_name: str = ""
    received_count: int = 0  # total items already rendered


def normalize_url(address: str) -> str:
    if address.startswith("archipelago://"):
        address = "ws://" + address[len("archipelago://") :]
    if "://" not in address:
        address = "ws://" + address
    parsed = urlparse(address)
    if not parsed.port:
        address = f"{parsed.scheme}://{parsed.hostname}:{DEFAULT_PORT}"
        if parsed.path:
            address += parsed.path
    return address


def stable_uuid() -> str:
    UUID_FILE.parent.mkdir(parents=True, exist_ok=True)
    if UUID_FILE.is_file():
        return UUID_FILE.read_text().strip()
    new = uuid.uuid4().hex
    UUID_FILE.write_text(new)
    return new


def persist_last_server(address: str) -> None:
    LAST_SERVER_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        LAST_SERVER_FILE.write_text(address)
    except OSError:
        pass


class ProtocolClient:
    """Runs the Archipelago WebSocket handshake and streams filtered events."""

    def __init__(
        self,
        state: ConnectionState,
        names: Names,
        event_queue: asyncio.Queue[Event],
        status_queue: asyncio.Queue[StatusEvent],
    ) -> None:
        self.state = state
        self.names = names
        self.events = event_queue
        self.status = status_queue
        self._ws: ClientConnection | None = None
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()
        ws = self._ws
        if ws is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            loop.create_task(ws.close())

    async def send_say(self, text: str) -> bool:
        """Send a Say packet (chat line or ``!command``). Returns False if the
        socket isn't currently open — the caller can surface that to the user."""
        ws = self._ws
        if ws is None or self.state.my_slot < 0:
            return False
        await self._send(ws, [{"cmd": "Say", "text": text}])
        return True

    async def run(self) -> None:
        url = normalize_url(self.state.server_address)
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._emit_status("connecting", f"connecting to {url}")
                ssl_ctx = (
                    ssl.create_default_context() if url.startswith("wss://") else None
                )
                async with connect(
                    url,
                    ssl=ssl_ctx,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=None,
                ) as ws:
                    self._ws = ws
                    persist_last_server(self.state.server_address)
                    backoff = 1.0
                    await self._session(ws)
            except (OSError, WebSocketException) as exc:
                await self._emit_status("disconnected", f"connection lost: {exc}")
            finally:
                self._ws = None

            if self._stop.is_set():
                return
            await self._emit_status("retrying", f"reconnecting in {backoff:.0f}s")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                return
            except TimeoutError:
                pass
            backoff = min(backoff * 2, 30.0)

    async def _session(self, ws: ClientConnection) -> None:
        stop_task = asyncio.create_task(self._stop.wait())
        try:
            while not self._stop.is_set():
                recv_task = asyncio.create_task(ws.recv())
                done, _ = await asyncio.wait(
                    {recv_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if stop_task in done:
                    recv_task.cancel()
                    return
                raw = recv_task.result()
                for packet in json.loads(raw):
                    await self._handle(packet, ws)
        finally:
            if not stop_task.done():
                stop_task.cancel()

    async def _handle(self, packet: dict, ws: ClientConnection) -> None:
        cmd = packet.get("cmd")
        logger.debug("<- %s", cmd)
        if cmd == "RoomInfo":
            await self._handle_room_info(packet, ws)
        elif cmd == "DataPackage":
            await self._handle_data_package(packet, ws)
        elif cmd == "Connected":
            await self._handle_connected(packet, ws)
        elif cmd == "ConnectionRefused":
            errors = ", ".join(packet.get("errors", [])) or "unknown error"
            await self._emit_status("refused", f"connection refused: {errors}")
            self._stop.set()
            await ws.close()
        elif cmd == "ReceivedItems":
            await self._handle_received_items(packet)
        elif cmd == "RoomUpdate":
            if "players" in packet:
                self.names.consume_players(packet["players"])
        elif cmd == "PrintJSON":
            await self._handle_print_json(packet)
        elif cmd == "Retrieved":
            await self._handle_retrieved(packet)
        elif cmd == "SetReply":
            await self._handle_set_reply(packet)

    async def _handle_room_info(self, packet: dict, ws: ClientConnection) -> None:
        self.state.seed_name = packet.get("seed_name", "")
        checksums: dict[str, str] = packet.get("datapackage_checksums", {}) or {}
        missing = self.names.missing_games(checksums)
        if missing:
            await self._send(ws, [{"cmd": "GetDataPackage", "games": missing}])
        else:
            await self._send_connect(ws)

    async def _handle_data_package(self, packet: dict, ws: ClientConnection) -> None:
        games = packet.get("data", {}).get("games", {})
        for game, game_data in games.items():
            self.names.store(game, game_data)
        await self._send_connect(ws)

    async def _send_connect(self, ws: ClientConnection) -> None:
        connect_packet = {
            "cmd": "Connect",
            "name": self.state.slot_name,
            "game": "",
            "password": self.state.password,
            "uuid": stable_uuid(),
            "version": {"major": 0, "minor": 6, "build": 6, "class": "Version"},
            "tags": ["AP", "TextOnly"],
            "items_handling": 0b111,
            "slot_data": False,
        }
        await self._send(ws, [connect_packet])

    async def _handle_connected(self, packet: dict, ws: ClientConnection) -> None:
        self.state.team = packet.get("team", 0)
        self.state.my_slot = packet.get("slot", -1)
        self.names.players.my_slot = self.state.my_slot
        self.names.consume_slot_info(packet.get("slot_info", {}))
        self.names.consume_players(packet.get("players", []))
        alias = self.names.players.alias(self.state.my_slot)
        await self._emit_status(
            "connected",
            f"connected as {alias} (team {self.state.team}, slot {self.state.my_slot}) "
            f"on seed {self.state.seed_name or '?'}",
        )
        # subscribe to the server-side hints list for this (team, slot)
        hints_key = self._hints_key()
        await self._send(
            ws,
            [
                {"cmd": "Get", "keys": [hints_key]},
                {"cmd": "SetNotify", "keys": [hints_key]},
            ],
        )

    def _hints_key(self) -> str:
        return f"_read_hints_{self.state.team}_{self.state.my_slot}"

    async def _handle_retrieved(self, packet: dict) -> None:
        keys = packet.get("keys") or {}
        hints_key = self._hints_key()
        if hints_key in keys:
            await self._process_hints(keys[hints_key] or [])

    async def _handle_set_reply(self, packet: dict) -> None:
        if packet.get("key") != self._hints_key():
            return
        await self._process_hints(packet.get("value") or [])

    async def _process_hints(self, raw_list: list) -> None:
        rows: list[HintRow] = []
        for raw in raw_list:
            row = _parse_hint(raw)
            if row is not None:
                rows.append(row)
        await self.events.put(HintsUpdated(ts=datetime.now(), hints=tuple(rows)))

    async def _handle_received_items(self, packet: dict) -> None:
        start_index = int(packet.get("index", 0))
        items = packet.get("items", [])
        shown = self.state.received_count
        for i, item in enumerate(items):
            server_pos = start_index + i
            if server_pos < shown:
                continue  # server replayed something we already rendered
            norm = item_ref_from_packet(item)
            ref = ItemRef(
                item_id=int(norm["item"]),
                location_id=int(norm["location"]),
                sender_slot=int(norm["player"]),
                receiver_slot=self.state.my_slot,
                flags=int(norm.get("flags", 0)),
            )
            await self.events.put(ReceivedEvent(ts=datetime.now(), item=ref))
            self.state.received_count = server_pos + 1

    async def _handle_print_json(self, packet: dict) -> None:
        my_slot = self.state.my_slot
        if my_slot < 0:
            return

        if is_sent_by_me(packet, my_slot):
            norm = item_ref_from_packet(packet["item"])
            ref = ItemRef(
                item_id=int(norm["item"]),
                location_id=int(norm["location"]),
                sender_slot=my_slot,
                receiver_slot=int(packet["receiving"]),
                flags=int(norm.get("flags", 0)),
            )
            await self.events.put(SentEvent(ts=datetime.now(), item=ref))
            return

        if is_self_status(packet, my_slot):
            kind = packet.get("type", "").lower()
            text = _flatten_data(packet.get("data", []))
            await self._emit_status(kind, text)
            return

        ptype = packet.get("type", "")
        if ptype in ("CommandResult", "AdminCommandResult"):
            text = _flatten_data(packet.get("data", []))
            if text:
                await self._emit_status(
                    ptype.replace("CommandResult", "cmd").lower(), text
                )

    async def _emit_status(self, kind: str, text: str) -> None:
        event = StatusEvent(ts=datetime.now(), kind=kind, text=text)
        await self.status.put(event)

    async def _send(self, ws: ClientConnection, msgs: list[dict]) -> None:
        await ws.send(json.dumps(msgs))


def _flatten_data(parts: list[dict]) -> str:
    return "".join(part.get("text", "") for part in parts if isinstance(part, dict))


def _parse_hint(raw: object) -> HintRow | None:
    """Accept either the dict serialization Archipelago uses for NamedTuples
    (with a ``class`` marker) or a plain 8-element tuple fallback."""
    if isinstance(raw, dict):
        try:
            return HintRow(
                finding_slot=int(raw["finding_player"]),
                receiving_slot=int(raw["receiving_player"]),
                item_id=int(raw["item"]),
                location_id=int(raw["location"]),
                found=bool(raw.get("found", False)),
                entrance=str(raw.get("entrance", "")),
                item_flags=int(raw.get("item_flags", 0)),
                status=HintStatus.coerce(raw.get("status", 0)),
            )
        except (KeyError, ValueError, TypeError):
            return None
    if isinstance(raw, (list, tuple)) and len(raw) >= 5:
        padded = list(raw) + [None] * (8 - len(raw))
        receiving, finding, location, item, found, entrance, item_flags, status = (
            padded[:8]
        )
        try:
            return HintRow(
                finding_slot=int(finding),
                receiving_slot=int(receiving),
                item_id=int(item),
                location_id=int(location),
                found=bool(found),
                entrance=str(entrance or ""),
                item_flags=int(item_flags or 0),
                status=HintStatus.coerce(status or 0),
            )
        except (ValueError, TypeError):
            return None
    return None
