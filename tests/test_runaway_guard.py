"""Tests for the SPAR runaway kill switch (MAK-113).

Runs under either pytest or ``python -m unittest``. No network, no API, no SPAR run.
"""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runaway_guard import (  # noqa: E402
    GuardConfig,
    JudgeMonitor,
    StdoutMonitor,
    extract_not_met_gates,
    iter_judge_checkpoints,
    normalize_gate_label,
    replay_transcript,
    write_partial_transcript,
)

REPO = Path(__file__).resolve().parent.parent

# A JUDGE checkpoint in the saved-transcript (clean markdown) format.
CLEAN_CHECKPOINT = """JUDGE (Round {n}):
VERDICT: PROMISING

GATE CHECK (for STRONG):
- [x] Specific, named customer segment: **MET** — sharp and named
- [x] Business model with actual numbers: **MET** — numbers exist

GATE CHECK (for FUCKING BRILLIANT — for reference):
- [ ] CUSTOMER VALIDATION: **NOT MET — {ord} CONSECUTIVE FAILURE.** No human voice.
- [ ] Competitive moat stress-tested: **NOT MET** — every layer killed.
- [ ] Domain expert hiring plan concrete: **NOT MET** — VA mentioned once.
"""


def _clean(n, ordinal="FIRST"):
    return CLEAN_CHECKPOINT.format(n=n, ord=ordinal)


class ExtractionTests(unittest.TestCase):
    def test_extracts_not_met_only(self):
        gates = extract_not_met_gates(_clean(6))
        self.assertIn("CUSTOMER VALIDATION", gates)
        self.assertIn("COMPETITIVE MOAT STRESS-TESTED", gates)
        # MET gates must not appear.
        self.assertNotIn("SPECIFIC, NAMED CUSTOMER SEGMENT", gates)
        self.assertNotIn("BUSINESS MODEL WITH ACTUAL NUMBERS", gates)

    def test_document_order_preserved(self):
        gates = extract_not_met_gates(_clean(6))
        self.assertEqual(gates[0], "CUSTOMER VALIDATION")

    def test_normalize_is_stable(self):
        self.assertEqual(
            normalize_gate_label("  • [ ] **CUSTOMER VALIDATION** "),
            "CUSTOMER VALIDATION",
        )

    def test_double_hyphen_variant(self):
        text = "- [ ] CUSTOMER VALIDATION: **NOT MET -- SIXTH CONSECUTIVE FAILURE.**"
        self.assertEqual(extract_not_met_gates(text), ["CUSTOMER VALIDATION"])


class StreakTests(unittest.TestCase):
    def test_trips_on_third_consecutive(self):
        mon = JudgeMonitor(threshold=3)
        self.assertIsNone(mon.feed_checkpoint(_clean(6), 6))
        self.assertIsNone(mon.feed_checkpoint(_clean(8), 8))
        event = mon.feed_checkpoint(_clean(10), 10)
        self.assertIsNotNone(event)
        self.assertEqual(event.gate, "CUSTOMER VALIDATION")
        self.assertEqual(event.round, 10)
        self.assertEqual(event.streak_rounds, [6, 8, 10])
        self.assertIn("CUSTOMER VALIDATION", event.gates)

    def test_threshold_two_trips_earlier(self):
        mon = JudgeMonitor(threshold=2)
        self.assertIsNone(mon.feed_checkpoint(_clean(6), 6))
        event = mon.feed_checkpoint(_clean(8), 8)
        self.assertIsNotNone(event)
        self.assertEqual(event.round, 8)

    def test_gap_resets_streak(self):
        mon = JudgeMonitor(threshold=3)
        mon.feed_checkpoint(_clean(6), 6)
        # Checkpoint where CUSTOMER VALIDATION is MET (absent from NOT-MET set).
        mon.feed_checkpoint("- [x] CUSTOMER VALIDATION: **MET** — a real voice appeared", 8)
        mon.feed_checkpoint(_clean(10), 10)
        event = mon.feed_checkpoint(_clean(12), 12)
        # Only two consecutive (10, 12) after the reset → no trip yet.
        self.assertIsNone(event)

    def test_only_trips_once(self):
        mon = JudgeMonitor(threshold=3)
        for n in (6, 8, 10):
            ev = mon.feed_checkpoint(_clean(n), n)
        self.assertIsNotNone(ev)
        self.assertIsNone(mon.feed_checkpoint(_clean(12), 12))

    def test_gates_filter_restricts(self):
        mon = JudgeMonitor(threshold=3, gates_filter={"NONEXISTENT GATE"})
        for n in (6, 8, 10):
            ev = mon.feed_checkpoint(_clean(n), n)
        self.assertIsNone(ev)


class ConfigTests(unittest.TestCase):
    def test_default_on(self):
        cfg = GuardConfig.from_env({})
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.threshold, 3)
        self.assertIsNone(cfg.gates_filter)

    def test_disable(self):
        for v in ("0", "off", "false", "no"):
            self.assertFalse(GuardConfig.from_env({"SPAR_KILLSWITCH": v}).enabled)

    def test_threshold_and_gates(self):
        cfg = GuardConfig.from_env(
            {"SPAR_KILL_THRESHOLD": "2", "SPAR_KILL_GATES": "customer validation, moat"}
        )
        self.assertEqual(cfg.threshold, 2)
        self.assertEqual(cfg.gates_filter, frozenset({"CUSTOMER VALIDATION", "MOAT"}))

    def test_bad_threshold_falls_back(self):
        self.assertEqual(GuardConfig.from_env({"SPAR_KILL_THRESHOLD": "x"}).threshold, 3)


class PartialTranscriptTests(unittest.TestCase):
    def test_writes_header_with_gate_and_round(self):
        mon = JudgeMonitor(threshold=3)
        for n in (6, 8, 10):
            ev = mon.feed_checkpoint(_clean(n), n)
        captured = ["round 6 output\n", "round 10 output\n"]
        out_dir = REPO / "tests" / "_tmp_out"
        path = write_partial_transcript(captured, ev, ["my idea", "--rounds", "20"], out_dir)
        try:
            body = path.read_text()
            self.assertIn("RUNAWAY KILL SWITCH", body)
            self.assertIn("CUSTOMER VALIDATION", body)
            self.assertIn("Round 10", body)
            self.assertIn("Threshold: 3", body)
            self.assertIn("round 10 output", body)
            self.assertTrue(path.name.startswith("spar_KILLED_my_idea_"))
        finally:
            path.unlink(missing_ok=True)
            out_dir.rmdir()


class RenderRoundTripTests(unittest.TestCase):
    """De-risks the LIVE path: render a JUDGE block exactly like spar.py
    (Console(width=100) + Panel(Markdown)) to a pipe, then confirm StdoutMonitor
    recovers the gate and trips. This is the rendered-stdout format, not clean markdown.
    """

    def _render(self, markdown_text, round_num):
        try:
            from rich.console import Console
            from rich.markdown import Markdown
            from rich.panel import Panel
        except ImportError:  # pragma: no cover
            self.skipTest("rich not installed")
        buf = io.StringIO()
        # force_terminal=False / no_color=True mirrors a piped (non-TTY) stdout.
        console = Console(width=100, file=buf, force_terminal=False, no_color=True)
        console.rule(f"[bold]Round {round_num}[/bold]", style="dim")
        console.print(
            Panel(
                Markdown(markdown_text),
                title="⚖️  JUDGE",
                title_align="left",
                border_style="cyan",
                padding=(1, 2),
            )
        )
        return buf.getvalue()

    def _body(self, ordinal):
        # Strip the "JUDGE (Round n):" header line — render_agent gets only the body.
        return "\n".join(_clean(0, ordinal).splitlines()[1:])

    def test_rendered_panel_is_parsed_and_trips(self):
        sm = StdoutMonitor(threshold=3)
        event = None
        for n, ordinal in [(6, "FIRST"), (8, "SECOND"), (10, "THIRD")]:
            rendered = self._render(self._body(ordinal), n)
            for line in rendered.splitlines(keepends=True):
                ev = sm.process_line(line)
                if ev is not None:
                    event = ev
        self.assertIsNotNone(event, "monitor failed to parse rendered rich panels")
        self.assertEqual(event.gate, "CUSTOMER VALIDATION")
        self.assertEqual(event.round, 10)


class TranscriptSplitTests(unittest.TestCase):
    def test_iter_checkpoints(self):
        transcript = (
            "── ROUND 6 ──\nEMBER: stuff\nRAZOR: stuff\n"
            + _clean(6)
            + "\n── ROUND 7 ──\nEMBER: more\n"
            + _clean(8)
            + "\n======================================================================\n"
        )
        cps = list(iter_judge_checkpoints(transcript))
        self.assertEqual([r for r, _ in cps], [6, 8])
        self.assertIn("CUSTOMER VALIDATION", cps[0][1])
        # Block must not bleed into the next round's EMBER text.
        self.assertNotIn("EMBER: more", cps[0][1])


class RealTranscriptReplayTests(unittest.TestCase):
    """Step-3 verification against the real Drago session, when present.

    The transcript lives under the gitignored sparring_sessions/, so this test
    skips in CI (file absent) and asserts locally where the file exists.
    """

    def _find_drago(self):
        candidates = list((REPO / "sparring_sessions").glob("spar_*multi-tenant_installer*"))
        if not candidates:
            # Fall back to the main clone if running from a worktree.
            main = REPO.parents[2] if len(REPO.parents) >= 3 else REPO
            candidates = list((main / "sparring_sessions").glob("spar_*multi-tenant_installer*"))
        return candidates[0] if candidates else None

    def test_drago_trips_at_round_10(self):
        path = self._find_drago()
        if path is None:
            self.skipTest("Drago transcript not present (gitignored)")
        event = replay_transcript(path, GuardConfig(enabled=True, threshold=3))
        self.assertIsNotNone(event, "expected a runaway trip in the Drago transcript")
        self.assertEqual(event.gate, "CUSTOMER VALIDATION")
        self.assertEqual(event.round, 10)
        self.assertEqual(event.streak_rounds, [6, 8, 10])


if __name__ == "__main__":
    unittest.main(verbosity=2)
