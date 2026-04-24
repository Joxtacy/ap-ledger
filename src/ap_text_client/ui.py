from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from rich.markup import escape as rich_escape
from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    RichLog,
    TabbedContent,
    TabPane,
)

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
from .names import Names, flag_prefix, hint_status_color, hint_status_label
from .suggester import CommandSuggester

if TYPE_CHECKING:
    from .protocol import ProtocolClient


def _fmt_ts(ts) -> str:
    return ts.strftime("%H:%M:%S")


def _item_color(flags: int) -> str:
    if flags & 0b100:
        return "salmon1"
    if flags & 0b001:
        return "plum2"
    if flags & 0b010:
        return "slate_blue1"
    return "cyan"


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
    #bottom { height: 16; }
    #hints { height: 1fr; }
    #status { height: 1fr; border: solid $primary; }
    #cmd { height: 3; border: tall $accent; }
    #cmd:focus-within { border: tall $success; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+l", "clear_focus", "Clear pane"),
        Binding("ctrl+p", "toggle_scroll", "Pause scroll"),
        Binding("f1", "show_tab('hints-tab')", "Hints"),
        Binding("f2", "show_tab('status-tab')", "Status"),
        Binding("slash", "focus_input", "Command"),
        Binding("escape", "blur_input", "Leave input"),
        Binding("h", "scroll('left')", "", show=False),
        Binding("j", "scroll('down')", "", show=False),
        Binding("k", "scroll('up')", "", show=False),
        Binding("l", "scroll('right')", "", show=False),
        Binding("g", "scroll('home')", "", show=False),
        Binding("G", "scroll('end')", "", show=False),
        Binding("ctrl+d", "scroll('half_down')", "", show=False),
        Binding("ctrl+u", "scroll('half_up')", "", show=False),
    ]

    def __init__(
        self,
        state: AppState,
        names: Names,
        slot_label: str,
        protocol: "ProtocolClient | None" = None,
    ) -> None:
        super().__init__()
        self.state = state
        self.names = names
        self.slot_label = slot_label
        self.protocol = protocol
        self._paused: dict[str, bool] = {
            "sent": False,
            "received": False,
            "status": False,
        }
        self._latest_hints: tuple[HintRow, ...] = ()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top"):
            yield RichLog(id="sent", highlight=False, markup=True, wrap=True)
            yield RichLog(id="received", highlight=False, markup=True, wrap=True)
        with TabbedContent(id="bottom", initial="hints-tab"):
            with TabPane("Hints", id="hints-tab"):
                yield DataTable(id="hints", zebra_stripes=True, cursor_type="row")
            with TabPane("Status", id="status-tab"):
                yield RichLog(id="status", highlight=False, markup=True, wrap=True)
        yield Input(
            placeholder="/ to focus  —  !hint <item>, !send <player> <item>, chat…",
            suggester=CommandSuggester(self.names),
            id="cmd",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sent", RichLog).border_title = "Sent"
        self.query_one("#received", RichLog).border_title = "Received"
        self.query_one(
            "#status", RichLog
        ).border_title = f"Status \u2014 {self.slot_label}"
        table = self.query_one("#hints", DataTable)
        table.add_column("Dir", width=3)
        table.add_column("Item", width=30)
        table.add_column("Other", width=28)
        table.add_column("Location", width=30)
        table.add_column("Status", width=14)
        self._pumps = [
            asyncio.create_task(self._pump_events()),
            asyncio.create_task(self._pump_status()),
        ]

    def on_unmount(self) -> None:
        for task in getattr(self, "_pumps", []):
            task.cancel()

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one("#bottom", TabbedContent).active = tab_id
        # Focus the content so hjkl / cursor keys act on it immediately
        if tab_id == "hints-tab":
            self.query_one("#hints", DataTable).focus()
        elif tab_id == "status-tab":
            self.query_one("#status", RichLog).focus()

    def action_focus_input(self) -> None:
        if not isinstance(self.focused, Input):
            self.query_one("#cmd", Input).focus()

    def action_blur_input(self) -> None:
        if isinstance(self.focused, Input):
            self.query_one("#sent", RichLog).focus()

    def action_scroll(self, direction: str) -> None:
        widget = self.focused
        if widget is None or isinstance(widget, Input):
            return
        if isinstance(widget, DataTable):
            # DataTable: move the row/column cursor instead of panning the view
            mapping = {
                "up": widget.action_cursor_up,
                "down": widget.action_cursor_down,
                "left": widget.action_cursor_left,
                "right": widget.action_cursor_right,
                "home": widget.action_scroll_home,
                "end": widget.action_scroll_end,
                "half_up": widget.action_page_up,
                "half_down": widget.action_page_down,
            }
            handler = mapping.get(direction)
            if handler:
                handler()
            return
        # RichLog: scroll the view
        half = max(1, widget.size.height // 2)
        handlers = {
            "up": lambda: widget.scroll_up(animate=False),
            "down": lambda: widget.scroll_down(animate=False),
            "left": lambda: widget.scroll_left(animate=False),
            "right": lambda: widget.scroll_right(animate=False),
            "home": lambda: widget.scroll_home(animate=False),
            "end": lambda: widget.scroll_end(animate=False),
            "half_up": lambda: widget.scroll_relative(y=-half, animate=False),
            "half_down": lambda: widget.scroll_relative(y=half, animate=False),
        }
        handler = handlers.get(direction)
        if handler:
            handler()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "cmd":
            return
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        if self.protocol is None:
            self._emit_local_status("error", "no protocol client attached")
            return
        self.run_worker(self._send_command(text), name="send", exclusive=False)

    async def _send_command(self, text: str) -> None:
        assert self.protocol is not None
        self._emit_local_status("sent", f"> {text}")
        ok = await self.protocol.send_say(text)
        if not ok:
            self._emit_local_status("error", "not connected; command dropped")

    def _emit_local_status(self, kind: str, text: str) -> None:
        self.state.status.put_nowait(
            StatusEvent(ts=datetime.now(), kind=kind, text=text)
        )

    async def _pump_events(self) -> None:
        while True:
            event = await self.state.events.get()
            try:
                self._write_event(event)
            except Exception as exc:
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
            log.write(
                f"[dim]{_fmt_ts(event.ts)}[/] {_fmt_item(event.item, self.names)}"
            )
            log.write(f"    \u2192 {_fmt_player(event.item.receiver_slot, self.names)}")
            log.write(f"    @ {_fmt_location(event.item, self.names)}")
        elif isinstance(event, ReceivedEvent):
            if self._paused["received"]:
                return
            log = self.query_one("#received", RichLog)
            log.write(
                f"[dim]{_fmt_ts(event.ts)}[/] {_fmt_item(event.item, self.names)}"
            )
            log.write(f"    \u2190 {_fmt_player(event.item.sender_slot, self.names)}")
            log.write(f"    @ {_fmt_location(event.item, self.names)}")
        elif isinstance(event, HintsUpdated):
            self._render_hints(event.hints)

    def _render_hints(self, hints: tuple[HintRow, ...]) -> None:
        self._latest_hints = hints
        table = self.query_one("#hints", DataTable)
        table.clear()
        my_slot = self.names.players.my_slot
        total = len(hints)
        found = sum(1 for h in hints if h.found)
        tab = self.query_one("#bottom", TabbedContent)
        try:
            tab.get_tab("hints-tab").label = f"Hints ({total - found}/{total})"
        except Exception:
            pass

        # pending first, then alphabetical by item name
        def sort_key(h: HintRow) -> tuple[int, str]:
            return (
                1 if h.found else 0,
                self.names.item_name(h.item_id, h.receiving_slot).lower(),
            )

        for hint in sorted(hints, key=sort_key):
            direction = "\u2190" if hint.receiving_slot == my_slot else "\u2192"
            item_name = rich_escape(
                self.names.item_name(hint.item_id, hint.receiving_slot)
            )
            item_markup = f"[{_item_color(hint.item_flags)}]{flag_prefix(hint.item_flags)}{item_name}[/]"
            if hint.found:
                item_markup = f"[strike dim]{item_markup}[/]"
            other_slot = (
                hint.finding_slot
                if hint.receiving_slot == my_slot
                else hint.receiving_slot
            )
            other_markup = _fmt_player(other_slot, self.names)
            location_markup = f"[green]{rich_escape(self.names.location_name(hint.location_id, hint.finding_slot))}[/]"
            status_label = hint_status_label(hint.status)
            status_markup = f"[{hint_status_color(hint.status)}]{status_label}[/]"
            if hint.found and hint.status != HintStatus.FOUND:
                status_markup += "  \u2713"
            table.add_row(
                Text.from_markup(direction),
                Text.from_markup(item_markup),
                Text.from_markup(other_markup),
                Text.from_markup(location_markup),
                Text.from_markup(status_markup),
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
            "disconnected": "red",
            "refused": "bold red",
            "retrying": "yellow",
            "connecting": "dim",
            "cmd": "cyan",
            "admincmd": "cyan",
            "sent": "bold blue",
            "error": "bold red",
        }.get(event.kind, "white")
        log.write(f"[dim]{_fmt_ts(event.ts)}[/] [{color}]{event.kind}[/] {event.text}")

    def action_clear_focus(self) -> None:
        focused = self.focused
        if isinstance(focused, RichLog):
            focused.clear()
        elif isinstance(focused, DataTable):
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
                rendered = self._render_event(event)
                if rendered:
                    print(rendered, flush=True)

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
        if isinstance(event, HintsUpdated):
            total = len(event.hints)
            found = sum(1 for h in event.hints if h.found)
            return f"[{_fmt_ts(event.ts)}] HINTS {total - found}/{total} pending"
        return ""

    def _render_status(self, event: StatusEvent) -> str:
        return f"[{_fmt_ts(event.ts)}] {event.kind.upper()} {event.text}"
