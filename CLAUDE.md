# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependencies are managed by [uv](https://docs.astral.sh/uv/). Python 3.11+ is required.

```sh
uv sync                                          # install deps (incl. dev: pyinstaller)
uv run ap-text-client <host[:port]> <slot> ...   # run the TUI client
uv run ap-text-client ... --no-tui               # plain-stdout renderer (pipe-friendly)
uv run ap-text-client ... --log-level DEBUG      # stdlib logging level

# Lint & format with ruff (pinned as a dev dependency):
uv run ruff check .                              # lint
uv run ruff check --fix .                        # lint + autofix
uv run ruff format .                             # format
uv run ruff format --check .                     # format-check only (CI-style)

# Build a single-file binary (used by CI, reproducible locally):
uv run pyinstaller --onefile --noconfirm --name ap-text-client \
    --collect-all textual --collect-all rich entry.py
```

No test suite is configured. The `ap-text-client.spec` file mirrors the CI PyInstaller invocation and is kept for reference; CI invokes pyinstaller with explicit flags rather than the spec.

CI (`.github/workflows/build.yml`) builds a PyInstaller binary on ubuntu/macos/windows `-latest` runners for every push and PR; tags matching `v*` additionally publish a GitHub Release with the packaged archives.

## Architecture

A single long-lived `asyncio` event loop drives two decoupled halves connected by two queues:

```
websockets ──► ProtocolClient ──► AppState.events  ──► TextClientApp  (or StdoutRenderer)
                              └─► AppState.status ──┘
                              ◄── send_say() ◄──── command Input
```

`ProtocolClient` (`protocol.py`) owns the websocket, reconnect/backoff, and the Archipelago handshake (`RoomInfo` → optional `GetDataPackage` → `Connect` → `Connected` → `Get`/`SetNotify` on the hints key `_read_hints_<team>_<slot>`). It never touches the UI — it drops filtered domain events onto `AppState.events` and status strings onto `AppState.status`. The UI is a pure consumer of those queues plus a one-way `protocol.send_say(text)` call for outgoing `!`-commands and chat.

Two renderers consume the same queues: `TextClientApp` (Textual TUI with Sent/Received RichLogs, a Hints DataTable, a Status RichLog, and the command Input) and `StdoutRenderer` (one line per event, used with `--no-tui`). Both live in `ui.py`; `__main__.py` picks between them and only installs its own SIGINT/SIGTERM handler in `--no-tui` mode because Textual installs its own.

### The "only my slot" filter

`filters.py` is the core value proposition — every inbound `PrintJSON`/`ReceivedItems` packet is tested against `my_slot` and silently dropped unless it's a `SentEvent` (I sent an item out), a `ReceivedEvent` (I received one), a self-`Goal`/`Release`/`Collect`, or a command result. Other players' chat and room noise are never surfaced. Hints are sourced from the server-side datastore key, not from `PrintJSON`, so `HintsUpdated` carries the full authoritative list on every change (a `SetReply` notification) and the UI re-renders the whole DataTable each time.

### Name resolution has a tricky asymmetry

`names.py` resolves IDs using the DataPackage, and **the scoping is not symmetric**:

- Item IDs live in the **receiver's** game namespace → `names.item_name(item_id, receiver_slot)`
- Location IDs live in the **sender's / finding** game namespace → `names.location_name(location_id, sender_slot)`

Getting this wrong silently produces `Item #12345` placeholders or, worse, names looked up in the wrong game. When formatting `HintRow`s this means: item uses `receiving_slot`, location uses `finding_slot`.

DataPackage responses are cached at `~/.cache/ap-text-client/datapackage/<game>-<checksum>.json`. On `RoomInfo` the client only requests games whose checksum isn't already on disk, so reconnects to the same seed are cheap.

### PyInstaller entry point

PyInstaller freezes `entry.py`, not `src/ap_text_client/__main__.py`. Running `__main__.py` directly through the frozen bootloader would break the package's relative imports — `entry.py` exists solely to do `from ap_text_client.__main__ import main` from the top level. Preserve this indirection if touching the build.

### State persisted outside the cache

- `~/.config/ap-text-client/uuid` — stable client UUID, generated once on first connect (the server uses it for reconnection identity).
- `~/.config/ap-text-client/last_server` — last successful server address, written on every successful websocket open.
- `~/.local/state/ap-text-client/events.log` — append-only log of `Sent`/`Received`/`Hints`/`Status` events, written by `event_log.EventLogger` (a non-propagating stdlib logger with a `FileHandler`). `ProtocolClient` accepts an optional `event_log` and calls it next to each `events.put` / `status.put`. Disable with `--no-event-log`; relocate with `--log-file PATH`.

## Version control

A `.jj/` directory is present — per the user's global preference, use `jj` (`jj new`, `jj commit`, `jj log`, `jj diff`, `jj bookmark set`) rather than `git` for day-to-day VCS operations. The repo is also a git colocated repo, so `git` still works for operations `jj` doesn't cover (e.g. `gh` PR workflows).
