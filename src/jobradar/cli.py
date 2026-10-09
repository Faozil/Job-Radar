"""Command line: run the radar locally or on GitHub Actions, check boards, find a chat id."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from .config import load_config
from .filters import apply_filters
from .http import NotFoundError, get_json
from .notify import ConsoleNotifier, Notifier, TelegramNotifier
from .pipeline import run
from .sources import build_sources
from .store import FileStore, MemoryStore, SeenStore

TELEGRAM_UPDATES = "https://api.telegram.org/bot{token}/getUpdates"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobradar", description=__doc__)
    parser.add_argument("--config", help="path to job-radar.toml (default: config/job-radar.toml)")
    commands = parser.add_subparsers(dest="command", required=True)

    run_cmd = commands.add_parser("run", help="fetch, filter and send new jobs")
    run_cmd.add_argument(
        "--dry-run", action="store_true", help="print instead of sending; save nothing"
    )
    run_cmd.add_argument(
        "--state", default=".state/seen.json", help="file that remembers sent jobs"
    )
    run_cmd.add_argument("--all", action="store_true", help="ignore the state file (dry runs only)")

    commands.add_parser("check-boards", help="check that every configured board answers")
    commands.add_parser("telegram-chat-id", help="print chat ids that messaged your bot")

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "check-boards":
        return _check_boards(args)
    return _telegram_chat_id()


def _run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    store: SeenStore = FileStore(args.state)
    if args.dry_run:
        notifier: Notifier = ConsoleNotifier()
        if args.all:
            store = MemoryStore()
    else:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, or use --dry-run.", file=sys.stderr)
            return 2
        notifier = TelegramNotifier(token, chat_id)

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


def _telegram_chat_id() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN first (it stays out of your shell history that way).")
        return 2
    response = get_json(TELEGRAM_UPDATES.format(token=token), redact=True)
    chats = {}
    for update in response.get("result") or []:
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        if "id" in chat:
            name = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
            chats[chat["id"]] = f"{chat.get('type', 'chat')} {name}".strip()
    if not chats:
        print("No messages yet. Send your bot any message (for example 'hi') and run this again.")
        return 1
    for chat_id, description in chats.items():
        print(f"{chat_id}  ({description})")
    return 0
