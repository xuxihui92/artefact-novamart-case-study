"""NovaMart's local return-desk demo. Requires Python 3.9 or later."""
import argparse
import os
import sys
from pathlib import Path

# Allow `python3 demo/app.py` from the repository root without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from return_desk import ReturnDesk
from return_desk.config import ROOT
from return_desk.server import create_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--openai",
        action="store_true",
        help="Enable optional OpenAI routing with synthetic inputs.",
    )
    args = parser.parse_args()
    key = os.getenv("OPENAI_API_KEY", "") if args.openai else ""
    if args.openai and not key:
        parser.error("--openai requires OPENAI_API_KEY in your shell environment.")
    desk = ReturnDesk(ROOT / "data" / "novamart.sqlite3", key, os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    with create_server(desk, args.port) as server:
        print(f"NovaMart Return Desk · http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
