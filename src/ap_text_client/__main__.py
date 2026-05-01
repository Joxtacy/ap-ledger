from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from getpass import getpass
from pathlib import Path

from . import event_log
from .names import Names
from .protocol import LAST_SERVER_FILE, ConnectionState, ProtocolClient
from .ui import AppState, StdoutRenderer, TextClientApp


def _last_server() -> str | None:
    try:
        value = LAST_SERVER_FILE.read_text().strip()
    except OSError:
        return None
    return value or None


def _prompt_for_missing(args: argparse.Namespace) -> None:
    """Fill in any missing connection details from a TTY.

    Lets a user double-click the binary (via the bundled launcher scripts)
    and type the connection in instead of needing CLI args. Caller is
    responsible for falling back to argparse's required-arg error when
    stdin isn't a TTY (CI, pipes), so non-interactive usage still fails
    fast with a clear message.
    """
    print("Connection details (Ctrl+C to cancel):")
    if not args.server:
        last = _last_server()
        prompt = f"Server [{last}]: " if last else "Server (host[:port]): "
        entry = input(prompt).strip()
        chosen = entry or last
        if not chosen:
            sys.exit("server is required")
        args.server = chosen
    if not args.slot:
        entry = input("Slot name: ").strip()
        if not entry:
            sys.exit("slot is required")
        args.slot = entry
    if args.password is None:
        # Empty (just Enter) keeps password=None; a typed value is used as-is.
        # getpass keeps it off the screen and out of shell history.
        pw = getpass("Password (leave blank for none): ")
        args.password = pw or None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ap-text-client",
        description="Minimal Archipelago text client (items concerning your slot only).",
    )
    parser.add_argument(
        "server",
        nargs="?",
        default=None,
        help="host[:port], ws://host:port, wss://host:port, or archipelago://host:port "
        "(bare and archipelago:// default to wss; use ws:// for plain WebSocket). "
        "Prompted interactively if omitted.",
    )
    parser.add_argument(
        "slot",
        nargs="?",
        default=None,
        help="slot name to connect as (prompted interactively if omitted)",
    )
    parser.add_argument("--password", default=None, help="optional server password")
    parser.add_argument("--team", type=int, default=0, help="team number (default 0)")
    parser.add_argument(
        "--no-tui", action="store_true", help="plain stdout renderer (pipe-friendly)"
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=None, help="override DataPackage cache dir"
    )
    parser.add_argument("--log-level", default="WARNING", help="python logging level")
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help=f"event log file (default: {event_log.default_log_file()})",
    )
    parser.add_argument(
        "--no-event-log",
        action="store_true",
        help="disable the persistent event log",
    )
    args = parser.parse_args(argv)
    if not args.server or not args.slot:
        if sys.stdin.isatty():
            _prompt_for_missing(args)
        else:
            parser.error("the following arguments are required: server, slot")
    return args


async def run(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=args.log_level.upper(), format="%(levelname)s %(name)s: %(message)s"
    )

    names = Names(cache_dir=args.cache_dir)
    elog: event_log.EventLogger | None = None
    if not args.no_event_log:
        log_path = args.log_file or event_log.default_log_file()
        event_log.setup_event_logger(log_path)
        elog = event_log.EventLogger(names)
    app_state = AppState()
    conn_state = ConnectionState(
        server_address=args.server,
        slot_name=args.slot,
        password=args.password,
        team=args.team,
    )
    client = ProtocolClient(
        state=conn_state,
        names=names,
        event_queue=app_state.events,
        status_queue=app_state.status,
        event_log=elog,
    )

    loop = asyncio.get_running_loop()
    installed_signals: list[int] = []
    if args.no_tui:
        # Textual installs its own SIGINT/SIGTERM handlers, so only hook them
        # in stdout mode.
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, client.stop)
                installed_signals.append(sig)
            except (NotImplementedError, RuntimeError):
                pass

    protocol_task = asyncio.create_task(client.run(), name="protocol")

    try:
        if args.no_tui:
            renderer = StdoutRenderer(names)
            render_task = asyncio.create_task(renderer.run(app_state), name="renderer")
            done, _ = await asyncio.wait(
                {protocol_task, render_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                exc = task.exception()
                if exc:
                    raise exc
        else:
            tui = TextClientApp(
                app_state, names, slot_label=f"{args.slot}", protocol=client
            )
            await tui.run_async()
    finally:
        for sig in installed_signals:
            try:
                loop.remove_signal_handler(sig)
            except (NotImplementedError, RuntimeError):
                pass
        if not protocol_task.done():
            client.stop()
            try:
                await asyncio.wait_for(protocol_task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                protocol_task.cancel()
                try:
                    await protocol_task
                except (asyncio.CancelledError, Exception):
                    pass

    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
