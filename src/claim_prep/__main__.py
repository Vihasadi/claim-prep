"""Run the server: `claim-prep [--port 8100]` or `python -m claim_prep`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

from claim_prep.api import create_app
from claim_prep.config import ConfigError, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claim-prep", description="Serve pre-call briefs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        settings = load_settings(args.env_file)
    except ConfigError as exc:
        print(f"Configuration error: {exc}\nSee .env.example.", file=sys.stderr)
        return 2
    uvicorn.run(create_app(settings), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
