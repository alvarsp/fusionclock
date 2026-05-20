#!/usr/bin/env python3
import argparse
import logging
import sys

from config import Config
from clock import OracleClock


def setup_logging(log_file: str):
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(log_file))
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def main():
    parser = argparse.ArgumentParser(
        description="Oracle Fusion automated clock in/out",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  setup      Export session from existing Chrome profile (or open browser for login).
             Run this once locally on your Mac, then copy session.json to the server.
  clock-in   Sleep a random delay then clock in.
  clock-out  Sleep a random delay then clock out.
  status     Check whether the saved session is still valid.
""",
    )
    parser.add_argument(
        "command",
        choices=["setup", "clock-in", "clock-out", "status", "discover"],
    )
    parser.add_argument(
        "--no-delay",
        action="store_true",
        help="Skip the randomized delay (useful for testing).",
    )
    args = parser.parse_args()

    try:
        config = Config()
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        sys.exit(1)

    setup_logging(config.log_file)
    clock = OracleClock(config)

    if args.command == "setup":
        clock.setup()
    elif args.command == "clock-in":
        clock.clock_in(no_delay=args.no_delay)
    elif args.command == "clock-out":
        clock.clock_out(no_delay=args.no_delay)
    elif args.command == "status":
        clock.status()
    elif args.command == "discover":
        clock.discover()


if __name__ == "__main__":
    main()
