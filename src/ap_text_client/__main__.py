from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from .names import Names
from .protocol import ConnectionState, ProtocolClient
from .ui import AppState, StdoutRenderer, TextClientApp


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ap-text-client",
        description="Minimal Archipelago text client (items concerning your slot only).",
    )
    parser.add_argument("server", help="host[:port] or ws://host:port or archipelago://host:port")
    parser.add_argument("slot", help="slot name to connect as")
    parser.add_argument("--password", default=None, help="optional server password")
    parser.add_argument("--team", type=int, default=0, help="team number (default 0)")
    parser.add_argument("--no-tui", action="store_true", help="plain stdout renderer (pipe-friendly)")
    parser.add_argument("--cache-dir", type=Path, default=None, help="override DataPackage cache dir")
    parser.add_argument("--log-level", default="WARNING", help="python logging level")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(name)s: %(message)s")

    names = Names(cache_dir=args.cache_dir)
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
            tui = TextClientApp(app_state, names, slot_label=f"{args.slot}", protocol=client)
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
            except (asyncio.TimeoutError, asyncio.CancelledError):
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
