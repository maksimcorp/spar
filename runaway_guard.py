#!/usr/bin/env python3
"""Runaway-session kill switch for SPAR (MAK-113).

Add-only wrapper layer. This module never imports SPAR internals and never
edits ``spar.py`` or ``prompts/``. It runs ``spar.py`` as a subprocess, watches
its stdout for the JUDGE checkpoints, and terminates the run when the same
critical gate is marked ``NOT MET`` across N consecutive checkpoints.

Why stdout and not the transcript file: ``spar.py`` writes the transcript file
exactly once, at the very end of a run (``outfile.write_text(...)``). On an early
kill that write never happens, so the only live signal is the subprocess stdout.
``spar.py`` renders each agent block with ``rich`` at a fixed ``Console(width=100)``;
when stdout is piped (not a TTY) rich emits plain text (no ANSI colour) wrapped in
panel borders. The detector below normalises that and also accepts clean markdown,
so the same logic verifies offline against a saved transcript.

The detector is deliberately format-tolerant: it anchors on the ``[ ]`` checkbox
that every JUDGE gate line carries, so it matches both::

    - [ ] CUSTOMER VALIDATION: **NOT MET — ...**          (clean transcript markdown)
    | • [ ] CUSTOMER VALIDATION: NOT MET — ...        |   (rendered, piped stdout)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ─── Locations ────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
SPAR_PY = HERE / "spar.py"
OUTPUT_DIR = HERE / "sparring_sessions"

# ─── Env config ───────────────────────────────────────────────────────────────
ENV_ENABLED = "SPAR_KILLSWITCH"        # "0"/"off"/"false"/"no" disables; default on
ENV_THRESHOLD = "SPAR_KILL_THRESHOLD"  # int >= 1; default 3
ENV_GATES = "SPAR_KILL_GATES"          # empty=default gate; comma list=those gates; */all/any=any gate

DEFAULT_THRESHOLD = 3
# Only CUSTOMER VALIDATION is structurally unobtainable inside a session (the Drago
# lesson): a real human voice cannot be produced from a desk. The other BRILLIANT
# gates (competitive moat, 18-month model, hiring plan) are legitimately NOT MET for
# many checkpoints in a healthy STRONG idea, so killing on any-gate would guillotine a
# good session. The default kills on CUSTOMER VALIDATION only; opt into any-gate (or a
# different set) via SPAR_KILL_GATES.
DEFAULT_GATES = frozenset({"CUSTOMER VALIDATION"})
_FALSEY = {"0", "off", "false", "no", "n", ""}
_ANY_GATE_SENTINELS = {"*", "all", "any"}


@dataclass
class GuardConfig:
    """Resolved kill-switch configuration."""

    enabled: bool = True
    threshold: int = DEFAULT_THRESHOLD
    # Normalised gate labels to watch. Defaults to CUSTOMER VALIDATION only; None = any gate.
    gates_filter: frozenset[str] | None = DEFAULT_GATES

    @classmethod
    def from_env(cls, env: dict | None = None) -> "GuardConfig":
        env = os.environ if env is None else env
        enabled = str(env.get(ENV_ENABLED, "1")).strip().lower() not in _FALSEY
        try:
            threshold = max(1, int(str(env.get(ENV_THRESHOLD, DEFAULT_THRESHOLD)).strip()))
        except (ValueError, TypeError):
            threshold = DEFAULT_THRESHOLD
        raw_gates = str(env.get(ENV_GATES, "")).strip()
        if not raw_gates:
            gates_filter = DEFAULT_GATES
        elif raw_gates.lower() in _ANY_GATE_SENTINELS:
            gates_filter = None
        else:
            gates = frozenset(
                normalize_gate_label(g) for g in raw_gates.split(",") if g.strip()
            )
            gates_filter = gates or DEFAULT_GATES
        return cls(enabled=enabled, threshold=threshold, gates_filter=gates_filter)


# ─── Gate detection ───────────────────────────────────────────────────────────
# Anchor on the checkbox ([ ] / [x]) that prefixes every gate line, capture the
# label up to its colon, and require the literal NOT MET. Tolerates rich's bullet,
# stripped markdown bold, em-dash/double-hyphen, and reflow joined with spaces.
_GATE_RE = re.compile(
    r"\[\s*[xX]?\s*\]\s*([^:\n]{2,90}?)\s*:\s*\*{0,2}\s*NOT\s+MET\b",
    re.IGNORECASE,
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_BOX_CHARS = "│┃|╭╮╰╯─┄┈"
_BULLET_CHARS = "•‣◦*-"


def normalize_gate_label(label: str) -> str:
    """Canonical key for a gate so the same gate matches across checkpoints."""
    label = re.sub(r"\*+", "", label)
    label = label.lstrip("".join({*_BULLET_CHARS}) + " ")
    label = re.sub(r"^\[\s*[xX]?\s*\]\s*", "", label)  # drop a leading checkbox if present
    label = re.sub(r"\s+", " ", label).strip()
    label = label.strip(" .:-–—")
    return label.upper()


def extract_not_met_gates(text: str) -> list[str]:
    """Return normalised labels of gates marked NOT MET, in document order, deduped."""
    seen: dict[str, None] = {}
    for match in _GATE_RE.finditer(text):
        key = normalize_gate_label(match.group(1))
        if key:
            seen.setdefault(key, None)
    return list(seen)


# ─── Kill event ───────────────────────────────────────────────────────────────
@dataclass
class KillEvent:
    gate: str                      # primary tripping gate (highest streak, ties → first seen)
    gates: list[str]               # all gates at/above threshold this checkpoint
    threshold: int
    round: int | None              # round of the tripping checkpoint, if known
    streak_rounds: list[int | None]  # rounds where the primary gate was consecutively NOT MET
    checkpoints: int               # number of JUDGE checkpoints seen so far

    @property
    def reason(self) -> str:
        rounds = [r for r in self.streak_rounds if r is not None]
        where = f" (rounds {', '.join(str(r) for r in rounds)})" if rounds else ""
        return (
            f'critical gate "{self.gate}" marked NOT MET for {self.threshold} '
            f"consecutive JUDGE checkpoints{where}"
        )


# ─── Detector ─────────────────────────────────────────────────────────────────
class JudgeMonitor:
    """Tracks per-gate consecutive NOT-MET streaks across JUDGE checkpoints.

    Pure logic: feed it one checkpoint blob at a time via :meth:`feed_checkpoint`.
    Returns a :class:`KillEvent` the first time any gate's streak reaches threshold.
    """

    def __init__(self, threshold: int = DEFAULT_THRESHOLD, gates_filter=None):
        self.threshold = max(1, int(threshold))
        self.gates_filter = frozenset(gates_filter) if gates_filter else None
        self._streaks: dict[str, int] = {}
        self._streak_rounds: dict[str, list] = {}
        self.checkpoints = 0
        self.tripped = False

    def feed_checkpoint(self, text: str, round_num: int | None = None) -> KillEvent | None:
        gates = extract_not_met_gates(text)
        if self.gates_filter is not None:
            gates = [g for g in gates if g in self.gates_filter]

        # Rebuild streaks: a gate advances only if it was NOT MET in the immediately
        # previous checkpoint (i.e. present in the prior streak map). Absent gates reset.
        new_streaks: dict[str, int] = {}
        new_rounds: dict[str, list] = {}
        for g in gates:
            if g in self._streaks:
                new_streaks[g] = self._streaks[g] + 1
                new_rounds[g] = self._streak_rounds[g] + [round_num]
            else:
                new_streaks[g] = 1
                new_rounds[g] = [round_num]
        self._streaks = new_streaks
        self._streak_rounds = new_rounds
        self.checkpoints += 1

        if self.tripped:
            return None

        tripping = [g for g in gates if new_streaks[g] >= self.threshold]
        if not tripping:
            return None

        self.tripped = True
        # Primary: highest streak, ties broken by document order (gates is ordered).
        primary = max(tripping, key=lambda g: (new_streaks[g], -gates.index(g)))
        return KillEvent(
            gate=primary,
            gates=tripping,
            threshold=self.threshold,
            round=round_num,
            streak_rounds=new_rounds[primary],
            checkpoints=self.checkpoints,
        )


# ─── Live stdout state machine ────────────────────────────────────────────────
_ROUND_RULE_RE = re.compile(r"^[\s─┄┈=-]*Round\s+(\d+)[\s─┄┈=-]*$")


def _strip_borders(line: str) -> str:
    s = _ANSI_RE.sub("", line).strip()
    s = s.strip(_BOX_CHARS).strip()
    return s


class StdoutMonitor:
    """Consumes piped ``spar.py`` stdout line by line and drives a JudgeMonitor.

    Detects JUDGE panels (rich box panel whose title contains "JUDGE"), buffers the
    panel body, normalises the reflow, and feeds each completed panel as one
    checkpoint. Tracks the current round from ``console.rule`` "Round N" lines.
    """

    def __init__(self, threshold: int = DEFAULT_THRESHOLD, gates_filter=None):
        self.monitor = JudgeMonitor(threshold, gates_filter)
        self._in_judge = False
        self._buffer: list[str] = []
        self._round: int | None = None

    def process_line(self, raw: str) -> KillEvent | None:
        line = _ANSI_RE.sub("", raw.rstrip("\n"))
        stripped = line.strip()

        if self._in_judge:
            if stripped.startswith("╰") or stripped.startswith("┗"):
                # panel closed → evaluate the checkpoint
                self._in_judge = False
                blob = " ".join(self._buffer)
                self._buffer = []
                return self.monitor.feed_checkpoint(blob, self._round)
            inner = _strip_borders(line)
            if inner:
                self._buffer.append(inner)
            return None

        # Outside any JUDGE panel.
        m = _ROUND_RULE_RE.match(stripped)
        if m:
            self._round = int(m.group(1))
            return None
        if (stripped.startswith("╭") or stripped.startswith("┏")) and "JUDGE" in line:
            self._in_judge = True
            self._buffer = []
        return None


# ─── Partial transcript ───────────────────────────────────────────────────────
def _slug_from_args(spar_args: list[str]) -> str:
    skip_values = {"--rounds", "--min-verdict", "--vc-rounds", "--name", "--session"}
    skip_next = False
    for arg in spar_args:
        if skip_next:
            skip_next = False
            continue
        if arg in skip_values:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        slug = re.sub(r"[^a-z0-9]+", "_", arg[:40].lower()).strip("_")
        if slug:
            return slug
    return "session"


def write_partial_transcript(
    captured: list[str],
    event: KillEvent,
    spar_args: list[str] | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Write the captured run output plus an explicit stop-reason header."""
    output_dir = OUTPUT_DIR if output_dir is None else output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slug_from_args(spar_args or [])
    path = output_dir / f"spar_KILLED_{slug}_{ts}.txt"

    bar = "=" * 70
    killed_round = f"Round {event.round}" if event.round is not None else "unknown round"
    header = [
        bar,
        "SESSION TERMINATED EARLY — RUNAWAY KILL SWITCH (MAK-113)",
        bar,
        f"Stop reason: {event.reason}.",
        f"Repeated gate(s) at/above threshold: {', '.join(event.gates)}",
        f"Threshold: {event.threshold} consecutive JUDGE checkpoints | "
        f"Killed at: {killed_round} | JUDGE checkpoints seen: {event.checkpoints}",
        "The verdict was blocked on this gate far earlier than the round cap; "
        "the run was stopped instead of burning the remaining rounds.",
        bar,
        "",
        "── PARTIAL TRANSCRIPT (captured run output up to termination) ──",
        "",
    ]
    body = "".join(captured)
    path.write_text("\n".join(header) + body)
    return path


# ─── Subprocess runner ────────────────────────────────────────────────────────
@dataclass
class GuardResult:
    killed: bool
    event: KillEvent | None = None
    transcript_path: Path | None = None
    returncode: int | None = None
    captured: list[str] = field(default_factory=list)


def _terminate(proc: subprocess.Popen, timeout: float = 10.0) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def run_guarded(
    spar_args: list[str],
    *,
    notify=None,
    sink=None,
    config: GuardConfig | None = None,
    spar_py: Path | None = None,
    output_dir: Path | None = None,
) -> GuardResult:
    """Run ``spar.py`` under the kill switch.

    Streams the subprocess stdout to ``sink`` (default ``sys.stdout``) unchanged so
    the live UX is identical, while the monitor watches for the runaway condition.
    On a trip: terminates the subprocess, writes a partial transcript, calls
    ``notify(event, transcript_path)``, and returns ``GuardResult(killed=True)``.
    """
    config = GuardConfig.from_env() if config is None else config
    sink = sys.stdout if sink is None else sink
    spar_py = SPAR_PY if spar_py is None else spar_py

    cmd = [sys.executable, str(spar_py), *spar_args]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    monitor = (
        StdoutMonitor(config.threshold, config.gates_filter) if config.enabled else None
    )

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env
    )
    captured: list[str] = []
    event: KillEvent | None = None
    assert proc.stdout is not None
    for line in proc.stdout:
        sink.write(line)
        sink.flush()
        captured.append(line)
        if monitor is not None:
            event = monitor.process_line(line)
            if event is not None:
                break

    if event is not None:
        _terminate(proc)
        path = write_partial_transcript(captured, event, spar_args, output_dir)
        if notify is not None:
            notify(event, path)
        return GuardResult(True, event, path, None, captured)

    returncode = proc.wait()
    return GuardResult(False, None, None, returncode, captured)


# ─── Offline replay (verification / tooling) ──────────────────────────────────
_JUDGE_HEADER_RE = re.compile(r"^JUDGE \(Round (\d+)\):", re.MULTILINE)
_BLOCK_END_RE = re.compile(r"^(── ROUND |VIPER |={10,}|FINAL PITCH|JUDGE \(Round )")


def iter_judge_checkpoints(transcript: str):
    """Yield ``(round_num, block_text)`` for each JUDGE checkpoint in a saved transcript."""
    lines = transcript.splitlines()
    headers = [
        (i, int(m.group(1)))
        for i, ln in enumerate(lines)
        if (m := re.match(r"^JUDGE \(Round (\d+)\):", ln))
    ]
    for idx, (start, round_num) in enumerate(headers):
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if _BLOCK_END_RE.match(lines[j]):
                end = j
                break
        yield round_num, "\n".join(lines[start:end])


def replay_transcript(path: str | Path, config: GuardConfig | None = None) -> KillEvent | None:
    """Replay a saved transcript offline; return the KillEvent if it would trip."""
    config = GuardConfig.from_env() if config is None else config
    monitor = JudgeMonitor(config.threshold, config.gates_filter)
    text = Path(path).read_text(errors="replace")
    for round_num, block in iter_judge_checkpoints(text):
        event = monitor.feed_checkpoint(block, round_num)
        if event is not None:
            return event
    return None


# ─── CLI notify ───────────────────────────────────────────────────────────────
def cli_notify(event: KillEvent, transcript_path: Path) -> None:
    """Print a prominent early-kill banner to stdout (no colour codes needed)."""
    bar = "=" * 70
    killed_round = f"Round {event.round}" if event.round is not None else "an early round"
    print(
        "\n".join(
            [
                "",
                bar,
                "⛔ SPAR RUNAWAY KILL SWITCH — SESSION TERMINATED EARLY",
                bar,
                f"  Reason : {event.reason}.",
                f"  Gate(s): {', '.join(event.gates)}",
                f"  Killed : {killed_round} (threshold {event.threshold} consecutive checkpoints)",
                f"  Partial transcript: {transcript_path}",
                bar,
                "",
            ]
        ),
        flush=True,
    )
