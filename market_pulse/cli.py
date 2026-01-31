"""
CLI entrypoint for Market Pulse.

Usage:
    python -m market_pulse.cli collect [--page 1] [--what python]
    python -m market_pulse.cli collect-muse [--batch tech-all] [--max-pages 2]
    python -m market_pulse.cli collect-arbeitnow [--max-pages 2] [--dry-run]
    python -m market_pulse.cli ensure-db
    python -m market_pulse.cli ensure-roles
"""

import argparse
import sys


def _cmd_collect(args: argparse.Namespace) -> int:
    from market_pulse.scripts.collect_adzuna import main as collect_main
    sys.argv = ["collect_adzuna", "--page", str(args.page), "--what", args.what]
    collect_main()
    return 0


def _cmd_collect_muse(args: argparse.Namespace) -> int:
    from market_pulse.scripts.collect_muse import main as collect_main
    sys.argv = ["collect_muse"]
    if args.batch:
        sys.argv += ["--batch", args.batch]
    if args.max_pages is not None:
        sys.argv += ["--max-pages", str(args.max_pages)]
    if args.dry_run:
        sys.argv += ["--dry-run"]
    collect_main()
    return 0


def _cmd_collect_arbeitnow(args: argparse.Namespace) -> int:
    from market_pulse.scripts.collect_arbeitnow import main as collect_main
    sys.argv = ["collect_arbeitnow"]
    if args.max_pages is not None:
        sys.argv += ["--max-pages", str(args.max_pages)]
    if args.page != 1:
        sys.argv += ["--page", str(args.page)]
    if args.dry_run:
        sys.argv += ["--dry-run"]
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

    muse_parser = subparsers.add_parser("collect-muse", help="Fetch jobs from The Muse and store in Cloudant")
    muse_parser.add_argument("--batch", choices=["tech-all", "tech-us"], default="tech-all", help="Preset (default: tech-all)")
    muse_parser.add_argument("--max-pages", type=int, default=None, help="Cap pages per combo")
    muse_parser.add_argument("--dry-run", action="store_true", help="Preview only")
    muse_parser.set_defaults(func=_cmd_collect_muse)

    arbeitnow_parser = subparsers.add_parser("collect-arbeitnow", help="Fetch jobs from Arbeitnow and store in Cloudant")
    arbeitnow_parser.add_argument("--max-pages", type=int, default=None, help="Cap number of pages to fetch")
    arbeitnow_parser.add_argument("--page", type=int, default=1, help="Starting page (default 1)")
    arbeitnow_parser.add_argument("--dry-run", action="store_true", help="Preview only")
    arbeitnow_parser.set_defaults(func=_cmd_collect_arbeitnow)

    subparsers.add_parser("ensure-db", help="Create Cloudant database if missing").set_defaults(func=_cmd_ensure_db)
    subparsers.add_parser("ensure-roles", help="Upsert role documents in Cloudant").set_defaults(func=_cmd_ensure_roles)

    args = parser.parse_args()
    exit_code = args.func(args)
    if exit_code is not None:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
