#!/usr/bin/env python3
"""Minimal Telegram runner for SPAR with the runaway kill switch (MAK-113).

Thin wrapper layer: runs ``spar.py`` as a subprocess under the shared guard and
surfaces the early kill to Telegram. It does NOT import SPAR internals and does
NOT edit ``spar.py`` or ``prompts/``.

This is a deliberately small runner (one guarded session per invocation), not a
full long-polling bot, so it stays testable and add-only. Credentials come from
the environment only — never hardcode a token:

    TELEGRAM_BOT_TOKEN   bot token from @BotFather
    TELEGRAM_CHAT_ID     destination chat id

If either is unset the kill is logged to stderr instead of sent, so the runner
works in CI and local smoke tests without secrets.

Usage:
    python telegram_bot.py "your idea here" --rounds 20
"""

import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from runaway_guard import KillEvent, run_guarded

ENV_TOKEN = "TELEGRAM_BOT_TOKEN"
ENV_CHAT = "TELEGRAM_CHAT_ID"


def send_telegram_message(token: str, chat_id: str, text: str, *, timeout: float = 10.0) -> bool:
    """POST a message to the Telegram Bot API. Returns True on HTTP 200."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:  # pragma: no cover
        print(f"[telegram_bot] send failed: {exc}", file=sys.stderr)
        return False


def format_kill_message(event: KillEvent, transcript_path: Path) -> str:
    killed_round = f"Round {event.round}" if event.round is not None else "an early round"
    return (
        "⛔ SPAR runaway kill switch — session terminated early\n"
        f"Reason: {event.reason}.\n"
        f"Gate(s): {', '.join(event.gates)}\n"
        f"Killed at: {killed_round} "
        f"(threshold {event.threshold} consecutive JUDGE checkpoints)\n"
        f"Partial transcript: {transcript_path.name}"
    )


def make_telegram_notify(token: str | None, chat_id: str | None):
    """Return a ``notify(event, path)`` callback that posts the kill to Telegram."""

    def notify(event: KillEvent, transcript_path: Path) -> None:
        text = format_kill_message(event, transcript_path)
        if token and chat_id:
            ok = send_telegram_message(token, chat_id, text)
            if ok:
                print("[telegram_bot] kill notification sent.", file=sys.stderr)
        else:
            print(
                "[telegram_bot] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID unset — "
                "kill not sent. Message would have been:\n" + text,
                file=sys.stderr,
            )

    return notify


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print('usage: python telegram_bot.py "your idea" [spar flags]', file=sys.stderr)
        return 2

    token = os.environ.get(ENV_TOKEN)
    chat_id = os.environ.get(ENV_CHAT)
    notify = make_telegram_notify(token, chat_id)

    result = run_guarded(argv, notify=notify)
    return 0 if result.killed else (result.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
