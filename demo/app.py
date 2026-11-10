"""NovaMart's local return-desk demo. Requires Python 3.9 or later."""
import argparse
import sys
from pathlib import Path

# Allow `python3 demo/app.py` from the repository root without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from return_desk import ReturnDesk
from return_desk.config import ROOT
from return_desk.model import resolve_settings
from return_desk.server import create_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--openai",
        action="store_true",
        help="Enable the model. Uses OpenAI unless --provider or PROVIDER selects Gemini.",
    )
    parser.add_argument(
        "--provider",
        choices=("openai", "gemini"),
        help="Model provider. Passing this enables the model. Gemini reads GEMINI_API_KEY.",
    )
    args = parser.parse_args()
    enabled = bool(args.openai or args.provider)
    if not enabled:
        desk = ReturnDesk(ROOT / "data" / "novamart.sqlite3")
    else:
        try:
            settings = resolve_settings(args.provider)
        except ValueError as error:
            parser.error("Unknown provider: {0}.".format(error))
        needed = "GEMINI_API_KEY" if settings["provider"] == "gemini" else "OPENAI_API_KEY"
        if not settings["api_key"]:
            parser.error(
                "The {0} provider requires {1} in the environment.".format(settings["provider"], needed)
            )
        desk = ReturnDesk(
            ROOT / "data" / "novamart.sqlite3",
            settings["api_key"],
            settings["model"],
            base_url=settings["base_url"],
            provider=settings["provider"],
        )
    with create_server(desk, args.port) as server:
        mode = "local rules" if desk.client is None else "{0} {1}".format(desk.provider, desk.model)
        print("NovaMart Return Desk · http://127.0.0.1:{0} · {1}".format(server.server_port, mode), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
