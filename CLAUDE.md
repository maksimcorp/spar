# SPAR — repo guide

SPAR is a single-file Python CLI: several AI agents stress-test an idea over multiple
rounds, then a VC-style agent tries to kill it. Run `python spar.py "your idea"`.

## Stack
- Python 3.10+, single script `spar.py`.
- Dependencies: `claude-agent-sdk`, `rich` (no dependency manifest yet — tracked follow-up).
- No build step. Tests cover the add-only wrapper layer (`python -m unittest discover tests`);
  `spar.py` itself still has no test suite (tracked follow-up).

## Wrapper layer (add-only)
- `spar.py` and everything in `prompts/` are upstream — keep `git diff` against upstream clean
  for those paths. New behaviour lives in sibling files that run `spar.py` as a subprocess and
  parse its stdout (never import SPAR internals).
- Runaway kill switch (MAK-113): `runaway_guard.py` (detector + runner), `spar_guard.py`
  (guarded CLI; use it like `spar.py`), `telegram_bot.py` (Telegram runner). Env:
  `SPAR_KILLSWITCH`, `SPAR_KILL_THRESHOLD` (default 3), `SPAR_KILL_GATES`. Offline check:
  `python spar_guard.py --replay sparring_sessions/<file>.txt`.

## Branch model
- `main` (default) + `staging`. Feature branches `feature/<KEY-NNN>` squash-merge into `staging`.
- No hosted deploy: SPAR runs locally, so `ci-deploy.yml`'s `deploy-staging` is a no-op gate skeleton.

## Standard
This repo follows the MAKSIMCORP engineering standard (the design-first Development Protocol
plus the Autonomous Development and Self-Review Protocol). The full protocol lives in the
global `~/.claude/CLAUDE.md`; this file holds only SPAR-specific details. Do not duplicate the
protocol here.
