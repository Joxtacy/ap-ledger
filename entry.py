"""PyInstaller entry point. Keeps relative imports inside the package intact."""

from ap_text_client.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
