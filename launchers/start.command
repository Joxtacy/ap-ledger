#!/usr/bin/env bash
# macOS launcher. Double-click in Finder to open Terminal.app and run the
# ap-text-client binary that lives next to this script. If the binary
# exits with a non-zero status (e.g. you cancelled at the prompt or hit a
# connection error), wait for Enter so you can read the message before
# Terminal closes the window.
set -u
cd "$(dirname "$0")"
./ap-text-client
status=$?
if [ "$status" -ne 0 ]; then
  printf '\nap-text-client exited with status %d. Press Enter to close.\n' "$status"
  read -r _ || true
fi
