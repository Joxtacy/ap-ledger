from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, RichLog

from rich.markup import escape as rich_escape

from .events import Event, HintEvent, ItemRef, ReceivedEvent, SentEvent, StatusEvent
from .names import Names, flag_prefix


def _fmt_ts(ts) -> str:
    return ts.strftime("%H:%M:%S")


def _item_color(flags: int) -> str:
    if flags & 0b100:
        return "salmon1"   # trap
    if flags & 0b001:
        return "plum2"     # progression
    if flags & 0b010:
        return "slate_blue1"  # useful
    return "cyan"          # filler


def _fmt_item(ref: ItemRef, names: Names) -> str:
    prefix = flag_prefix(ref.flags)
    name = rich_escape(names.item_name(ref.item_id, ref.receiver_slot))
    return f"[{_item_color(ref.flags)}]{prefix}{name}[/]"


def _fmt_location(ref: ItemRef, names: Names) -> str:
    name = rich_escape(names.location_name(ref.location_id, ref.sender_slot))
    return f"[green]{name}[/]"


def _fmt_player(slot: int, names: Names) -> str:
    alias = rich_escape(names.players.alias(slot))
    game = rich_escape(names.players.game(slot))
    color = "magenta" if slot == names.players.my_slot else "yellow"
    return f"[{color}]{alias}[/] [dim]({game})[/]"


class AppState:
    def __init__(self) -> None:
        self.events: asyncio.Queue[Event] = asyncio.Queue()
        self.status: asyncio.Queue[StatusEvent] = asyncio.Queue()


class TextClientApp(App):
    CSS = """
    Screen { layout: vertical; }
    #top { height: 1fr; layout: horizontal; }
    #sent, #received { width: 1fr; height: 100%; border: solid $accent; }
    #status { height: 12; border: solid $primary; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("c", "clear_focus", "Clear pane"),
        Binding("p", "toggle_scroll", "Pause scroll"),
    ]

    footer_text: reactive[str] = reactive("")

    def __init__(self, state: AppState, names: Names, slot_label: str) -> None:
        super().__init__()
        self.state = state
        self.names = names
        self.slot_label = slot_label
        self._paused: dict[str, bool] = {"sent": False, "received": False, "status": False}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top"):
            yield RichLog(id="sent", highlight=False, markup=True, wrap=True)
            yield RichLog(id="received", highlight=False, markup=True, wrap=True)
        yield RichLog(id="status", highlight=False, markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sent", RichLog).border_title = "Sent"
        self.query_one("#received", RichLog).border_title = "Received"
        self.query_one("#status", RichLog).border_title = f"Status \u2014 {self.slot_label}"
        self._pumps = [
            asyncio.create_task(self._pump_events()),
            asyncio.create_task(self._pump_status()),
        ]

    def on_unmount(self) -> None:
        for task in getattr(self, "_pumps", []):
            task.cancel()

    async def _pump_events(self) -> None:
        while True:
            event = await self.state.events.get()
            try:
                self._write_event(event)
            except Exception as exc:  # don't let a render error kill the pump
                self.log.error(f"event render failed: {exc!r}")

    async def _pump_status(self) -> None:
        while True:
            event = await self.state.status.get()
            try:
                self._write_status(event)
            except Exception as exc:
                self.log.error(f"status render failed: {exc!r}")

    def _write_event(self, event: Event) -> None:
        if isinstance(event, SentEvent):
            if self._paused["sent"]:
                return
            log = self.query_one("#sent", RichLog)
            log.write(f"[dim]{_fmt_ts(event.ts)}[/] {_fmt_item(event.item, self.names)}")
            log.write(f"    \u2192 {_fmt_player(event.item.receiver_slot, self.names)}")
            log.write(f"    @ {_fmt_location(event.item, self.names)}")
        elif isinstance(event, ReceivedEvent):
            if self._paused["received"]:
                return
            log = self.query_one("#received", RichLog)
            log.write(f"[dim]{_fmt_ts(event.ts)}[/] {_fmt_item(event.item, self.names)}")
            log.write(f"    \u2190 {_fmt_player(event.item.sender_slot, self.names)}")
            log.write(f"    @ {_fmt_location(event.item, self.names)}")
        elif isinstance(event, HintEvent):
            self._write_status(
                StatusEvent(
                    ts=event.ts,
                    kind="hint",
                    text=self._hint_text(event),
                )
            )

    def _write_status(self, event: StatusEvent) -> None:
        if self._paused["status"]:
            return
        log = self.query_one("#status", RichLog)
        color = {
            "connected": "green",
            "goal": "bold magenta",
            "release": "yellow",
            "collect": "yellow",
            "hint": "blue",
            "disconnected": "red",
            "refused": "bold red",
        }.get(event.kind, "white")
        log.write(f"[dim]{_fmt_ts(event.ts)}[/] [{color}]{event.kind}[/] {event.text}")

    def _hint_text(self, event: HintEvent) -> str:
        item = _fmt_item(event.item, self.names)
        location = _fmt_location(event.item, self.names)
        finder = _fmt_player(event.item.sender_slot, self.names)
        receiver = _fmt_player(event.item.receiver_slot, self.names)
        state = "found" if event.found else "not found"
        return f"{finder} \u2192 {receiver}: {item} @ {location} ({state})"

    def action_clear_focus(self) -> None:
        focused = self.focused
        if isinstance(focused, RichLog):
            focused.clear()

    def action_toggle_scroll(self) -> None:
        focused = self.focused
        if isinstance(focused, RichLog):
            pane_id = focused.id or ""
            if pane_id in self._paused:
                self._paused[pane_id] = not self._paused[pane_id]
                focused.border_subtitle = "paused" if self._paused[pane_id] else ""


class StdoutRenderer:
    """Fallback --no-tui renderer. Plain stdout, one line per event."""

    def __init__(self, names: Names) -> None:
        self.names = names

    async def run(self, state: AppState) -> None:
        async def pump_events():
            while True:
                event = await state.events.get()
                print(self._render_event(event), flush=True)

        async def pump_status():
            while True:
                event = await state.status.get()
                print(self._render_status(event), flush=True)

        await asyncio.gather(pump_events(), pump_status())

    def _render_event(self, event: Event) -> str:
        if isinstance(event, SentEvent):
            return (
                f"[{_fmt_ts(event.ts)}] SENT {_fmt_item(event.item, self.names)} "
                f"-> {_fmt_player(event.item.receiver_slot, self.names)} "
                f"@ {_fmt_location(event.item, self.names)}"
            )
        if isinstance(event, ReceivedEvent):
            return (
                f"[{_fmt_ts(event.ts)}] RECV {_fmt_item(event.item, self.names)} "
                f"<- {_fmt_player(event.item.sender_slot, self.names)} "
                f"@ {_fmt_location(event.item, self.names)}"
            )
        if isinstance(event, HintEvent):
            state_str = "found" if event.found else "not found"
            return (
                f"[{_fmt_ts(event.ts)}] HINT "
                f"{_fmt_player(event.item.sender_slot, self.names)} -> "
                f"{_fmt_player(event.item.receiver_slot, self.names)}: "
                f"{_fmt_item(event.item, self.names)} "
                f"@ {_fmt_location(event.item, self.names)} ({state_str})"
            )
        return ""

    def _render_status(self, event: StatusEvent) -> str:
        return f"[{_fmt_ts(event.ts)}] {event.kind.upper()} {event.text}"
