# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Runaway-session kill switch (MAK-113): add-only wrapper layer that runs `spar.py`
  as a subprocess and terminates a run when the same critical JUDGE gate is `NOT MET`
  across N consecutive checkpoints (default 3). Writes a partial transcript naming the
  stop reason and repeated gate, and surfaces the early kill in the CLI and Telegram.
  New files only — `runaway_guard.py` (detector + subprocess runner), `spar_guard.py`
  (guarded CLI front end, with `--replay` for offline verification), `telegram_bot.py`
  (minimal Telegram runner), and `tests/test_runaway_guard.py`. Configurable via env
  (`SPAR_KILLSWITCH`, `SPAR_KILL_THRESHOLD`, `SPAR_KILL_GATES`); default on. No changes
  to `spar.py` or `prompts/`.
- MAKSIMCORP development-protocol conformance baseline (MAK-110): `main`+`staging`
  branch model (renamed from `master`), canonical `ci-deploy.yml` gate
  (`verify` + `audit` gating `deploy-staging` via `needs`), thin `CLAUDE.md`, and
  `.env.example`.

### Notes
- Follow-ups: clear the `ruff` lint debt in `spar.py` and add a test suite, then make
  `ruff` and `pytest` blocking steps in the gate; add a dependency manifest.
