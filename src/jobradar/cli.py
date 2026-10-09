"""Run the radar locally or on GitHub Actions, check the boards, or send a test email."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from .config import load_config
from .filters import apply_filters
from .http import NotFoundError
from .notify import ConsoleNotifier, EmailNotifier, Notifier, NotifyError
from .pipeline import run
from .sources import build_sources
from .store import FileStore, MemoryStore, SeenStore


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobradar", description=__doc__)
    parser.add_argument("--config", help="path to job-radar.toml (default: config/job-radar.toml)")
    commands = parser.add_subparsers(dest="command", required=True)

    run_cmd = commands.add_parser("run", help="fetch, filter and email new jobs")
    run_cmd.add_argument(
        "--dry-run", action="store_true", help="print instead of sending; save nothing"
    )
    run_cmd.add_argument(
        "--state", default=".state/seen.json", help="file that remembers sent jobs"
    )
    run_cmd.add_argument("--all", action="store_true", help="ignore the state file (dry runs only)")

    commands.add_parser("check-boards", help="check that every configured board answers")
    commands.add_parser("test-email", help="send a test email with your settings")

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "check-boards":
        return _check_boards(args)
    return _test_email()


def _email_notifier() -> EmailNotifier | None:
    address = os.environ.get("EMAIL_ADDRESS", "")
    password = os.environ.get("EMAIL_APP_PASSWORD", "")
    if not address or not password:
        print("Set EMAIL_ADDRESS and EMAIL_APP_PASSWORD first (see the README).", file=sys.stderr)
        return None
    return EmailNotifier(address, password)


def _run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    store: SeenStore = FileStore(args.state)
    if args.dry_run:
        notifier: Notifier | None = ConsoleNotifier()
        if args.all:
            store = MemoryStore()
    else:
        notifier = _email_notifier()
    if notifier is None:
        return 2

    result = run(
        build_sources(config),
        config.filters,
        store,
        notifier,
        max_per_run=config.max_per_run,
        save=not args.dry_run,
    )
    print(
        f"\nBoards read: {result.boards_ok}, jobs: {result.fetched}, matches: {result.matched}, "
        f"new: {result.new}, sent: {result.notified}"
    )
    for label, reason in sorted(result.errors.items()):
        print(f"  failed {label}: {reason}", file=sys.stderr)
    return 0


def _check_boards(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    now = datetime.now(UTC)
    problems = 0
    for source in build_sources(config):
        try:
            jobs = source.fetch()
        except NotFoundError:
            print(f"NOT FOUND  {source.label}")
            problems += 1
            continue
        except Exception as exc:
            print(f"ERROR      {source.label}: {exc}")
            problems += 1
            continue
        matches = apply_filters(jobs, config.filters, now=now)
        print(f"OK         {source.label:<32} {len(jobs):>4} jobs {len(matches):>3} matches")
    print(f"\n{problems} board(s) need attention" if problems else "\nAll boards answered")
    return 1 if problems else 0


def _test_email() -> int:
    notifier = _email_notifier()
    if notifier is None:
        return 2
    try:
        notifier.send_test()
    except NotifyError as exc:
        print(exc, file=sys.stderr)
        return 1
    print("Test email sent. Check your inbox.")
    return 0
