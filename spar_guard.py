#!/usr/bin/env python3
"""Guarded CLI runner for SPAR (MAK-113).

Drop-in front end for ``spar.py`` that adds the runaway-session kill switch.
Run it exactly like ``spar.py`` — all arguments pass straight through::

    python spar_guard.py "your idea here" --rounds 20
    python spar_guard.py --scout "constraints here"

The kill switch is on by default and configured via env (see runaway_guard):
    SPAR_KILLSWITCH=0          disable
    SPAR_KILL_THRESHOLD=3      consecutive NOT-MET checkpoints to trip
    SPAR_KILL_GATES="..."      restrict to specific gate labels (comma list)

Offline verification (no API, replays a saved transcript through the detector)::

    python spar_guard.py --replay sparring_sessions/<file>.txt
"""

import sys

from runaway_guard import GuardConfig, cli_notify, replay_transcript, run_guarded


def _do_replay(path: str) -> int:
    config = GuardConfig.from_env()
    if not config.enabled:
        print("Kill switch disabled (SPAR_KILLSWITCH); nothing to replay.")
        return 0
    event = replay_transcript(path, config)
    if event is None:
        print(
            f"No runaway condition found in {path} "
            f"(threshold {config.threshold} consecutive NOT-MET checkpoints)."
        )
        return 1
    print(f"WOULD TERMINATE at Round {event.round}:")
    print(f"  Reason : {event.reason}.")
    print(f"  Gate(s): {', '.join(event.gates)}")
    print(f"  Checkpoints seen: {event.checkpoints}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--replay":
        if len(argv) < 2:
            print("usage: spar_guard.py --replay <transcript.txt>", file=sys.stderr)
            return 2
        return _do_replay(argv[1])

    result = run_guarded(argv, notify=cli_notify)
    # An early kill is a clean, intended stop — exit 0.
    if result.killed:
        return 0
    return result.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
