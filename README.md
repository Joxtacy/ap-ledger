# ap-ledger

A minimal Archipelago text client. Subscribes to a multiworld and shows **only**
events that concern your slot:

- Items you send to other players (Sent pane)
- Items you receive (Received pane)
- Hints involving you, live-updated when items are found (Hints tab)
- Your goal / release / collect notifications, connection state, command output (Status tab)

Everything else — other players' chat, join/part, deathlink, room noise — is dropped.
Type `!hint`, `!send`, `!getitem`, … in the command field at the bottom; item and
location names autocomplete inline.

## Download

Pre-built binaries for each tagged release are attached to the GitHub Release:

| Platform | File | Requirement |
|---|---|---|
| Linux x86_64 | `ap-text-client-linux.tar.gz` | glibc ≥ 2.39 (Ubuntu 24.04+, Debian 13+, Fedora 40+) |
| macOS arm64 | `ap-text-client-macos.tar.gz` | macOS 14 Sonoma or newer, Apple Silicon |
| Windows x86_64 | `ap-text-client-windows.zip` | Windows 10 or newer |

Older distros or Intel Macs: build from source (below). Static binaries aren't
a goal here; the release builds come straight off GitHub Actions `*-latest` runners.

## Install from source

Managed with [uv](https://docs.astral.sh/uv/). Requires Python 3.11+.

```sh
uv sync
uv run ap-text-client --help
```

## Run

```sh
uv run ap-text-client <host[:port]> <slot> [--password PW] [--team 0] [--no-tui]
```

Examples:

```sh
uv run ap-text-client archipelago.gg:38281 JoxSlot
uv run ap-text-client localhost:38281 JoxSlot --password secret
uv run ap-text-client localhost:38281 JoxSlot --no-tui   # plain stdout, pipe-friendly
```

Default port is `38281`. `archipelago://host:port` and bare `host:port` are accepted.

## Key bindings (TUI)

| Key | Action |
|---|---|
| `/` | Focus the command input |
| `Esc` | Leave the command input |
| `Enter` | Submit the command / chat line |
| `→` / `End` | Accept the inline autocomplete suggestion |
| `F1` | Switch to the Hints tab |
| `F2` | Switch to the Status tab |
| `h` `j` `k` `l` | Pan the focused pane (or move the DataTable cursor) |
| `g` / `G` | Jump to top / bottom of the focused pane |
| `Ctrl+D` / `Ctrl+U` | Half-page down / up |
| `Ctrl+L` | Clear the focused pane |
| `Ctrl+P` | Pause / resume auto-scroll on the focused pane |
| `Ctrl+Q` | Quit |

Hjkl only fires when a pane has focus; while the command input is focused the
keys just type into it. Press `Esc` to leave the input first.

## Autocomplete

Inline grey suggestions appear while typing the following commands. Accept with
`→` or `End`:

| Command | Completes |
|---|---|
| `!hint <item>` | items in your game |
| `!hint_location <location>` | locations in your game |
| `!getitem <item>` | items in your game |
| `!send <player> <item>` | player aliases, then that player's items |

## Cache

DataPackage responses are cached in `~/.cache/ap-text-client/datapackage/` by
checksum so reconnects are cheap. The last server address is saved in
`~/.config/ap-text-client/last_server`.
