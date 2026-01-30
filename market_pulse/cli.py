"""
CLI entrypoint for Market Pulse.

Usage:
    python -m market_pulse.cli collect [--page 1] [--what python]
    python -m market_pulse.cli ensure-db
    python -m market_pulse.cli ensure-roles
"""

import argparse
import sys


def _cmd_collect(args: argparse.Namespace) -> int:
    from market_pulse.scripts.collect_adzuna import main as collect_main
    # collect_adzuna parses sys.argv; set it so it gets --page and --what
    sys.argv = ["collect_adzuna", "--page", str(args.page), "--what", args.what]
    collect_main()
    return 0


def _cmd_ensure_db(_args: argparse.Namespace) -> int:
    from market_pulse.scripts.ensure_cloudant_db import main as ensure_main
    ensure_main()
    return 0


def _cmd_ensure_roles(_args: argparse.Namespace) -> int:
    from market_pulse.scripts.ensure_roles import main as ensure_main
    ensure_main()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Market Pulse: job market collection and tools",
        prog="python -m market_pulse.cli",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="Fetch jobs from Adzuna and store in Cloudant")
    collect_parser.add_argument("--page", type=int, default=1, help="Adzuna API page number")
    collect_parser.add_argument("--what", type=str, default="python", help="Adzuna search query")
    collect_parser.set_defaults(func=_cmd_collect)

    subparsers.add_parser("ensure-db", help="Create Cloudant database if missing").set_defaults(func=_cmd_ensure_db)
    subparsers.add_parser("ensure-roles", help="Upsert role documents in Cloudant").set_defaults(func=_cmd_ensure_roles)

    args = parser.parse_args()
    exit_code = args.func(args)
    if exit_code is not None:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
