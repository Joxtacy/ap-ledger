# ap-text-client

A minimal Archipelago text client. Subscribes to a multiworld as a read-only
spectator and shows **only** events that concern your slot:

- Items you send to other players (Sent pane)
- Items you receive (Received pane)
- Hints where you are the finder or receiver (Status pane)
- Your goal / release / collect notifications (Status pane)

Everything else — chat, join/part, deathlink, admin noise — is dropped.

## Install

Managed with [uv](https://docs.astral.sh/uv/). Requires Python 3.11+.

```sh
uv sync
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

Default port is `38281`. `archipelago://` and bare `host:port` are accepted.

## Key bindings (TUI)

| Key | Action |
|---|---|
| `q` | Quit |
| `c` | Clear the focused pane |
| `p` | Pause / resume auto-scroll in the focused pane |

## Cache

DataPackage responses are cached in `~/.cache/ap-text-client/datapackage/` by
checksum so reconnects are cheap. The last server address is saved in
`~/.config/ap-text-client/last_server`.
