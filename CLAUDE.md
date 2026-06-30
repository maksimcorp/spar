# SPAR — repo guide

SPAR is a single-file Python CLI: several AI agents stress-test an idea over multiple
rounds, then a VC-style agent tries to kill it. Run `python spar.py "your idea"`.

## Stack
- Python 3.10+, single script `spar.py`.
- Dependencies: `claude-agent-sdk`, `rich` (no dependency manifest yet — tracked follow-up).
- No build step and no test suite yet.

## Branch model
- `main` (default) + `staging`. Feature branches `feature/<KEY-NNN>` squash-merge into `staging`.
- No hosted deploy: SPAR runs locally, so `ci-deploy.yml`'s `deploy-staging` is a no-op gate skeleton.

## Changelog & release
- Per-ticket fragments in `changelog.d/<TICKET-KEY>.md` (category-tagged), not a shared `[Unreleased]` list. See `changelog.d/README.md`.
- Release step assembles them: `python scripts/assemble_changelog.py <version>` writes `CHANGELOG.md` and deletes the fragments.

## Standard
This repo follows the MAKSIMCORP engineering standard (the design-first Development Protocol
plus the Autonomous Development and Self-Review Protocol). The full protocol lives in the
global `~/.claude/CLAUDE.md`; this file holds only SPAR-specific details. Do not duplicate the
protocol here.
