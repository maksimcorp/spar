# SPAR

This repo runs under the autonomous development protocol defined in the global
`~/.claude/CLAUDE.md`. Read that protocol first. This file records only what is
specific to this repository and does not restate the protocol.

## Identity and boundary

This repository is SPAR and only SPAR. It describes no other project. Any
change that references, embeds, or exposes another venture is a cross project
boundary violation (global hard stop 3).

SPAR is a CLI tool that runs five AI agents (EMBER, RAZOR, JUDGE, VIPER,
SCOUT/PITCH) against a user-submitted idea — startup, career, or otherwise —
in adversarial rounds, producing a one-page verdict. Jira project key: MAK
(maksimcorp org). No parent repo — git history starts at initial release with
no fork lineage.

## Stack

Python 3.10+, single-file CLI (`spar.py`, ~820 lines). Dependencies:
`claude-agent-sdk`, `rich`. No manifest file exists (no `requirements.txt`,
`pyproject.toml`, or `setup.py`) — the README installs deps directly via
`pip install claude-agent-sdk rich`. Agent behavior lives in `prompts/*.md`
(edited directly, no code changes needed for prompt tuning). Auth via Claude
Code OAuth (Max subscription) or `ANTHROPIC_API_KEY`. No hosting target —
this is a local CLI, not a deployed service.

## Environments

No deploy environments. SPAR is a local CLI tool the user runs directly
(`python spar.py`); there is no dev, staging, or prod hosting target and
nothing to deploy.

## Branch model and review

`main` plus `staging`, confirmed in use (`feature/MAK-*` branches target
`staging`). Feature branches target `staging`. Never push directly to `main`
or `staging`.

There is no human PR review gate. Code verifies locally, self reviews against
the global self review checklist, confirms CI is green, and self merges per
the autonomous protocol. The founder is interrupted only by the global hard
stop set. Do not add a review, approval, or sign off requirement here. If this
repo ever needs one as a deliberate, reasoned exception, it gets written
explicitly as an exception with the reason, not left implicit or copied from a
template by habit.

## Changelog and release

Unreleased changes are per-ticket fragments in `changelog.d/<TICKET-KEY>.md`
(category-tagged, Keep a Changelog categories), never edits to a shared
`[Unreleased]` list — this is what lets parallel sessions add entries without
colliding. At release, `python scripts/assemble_changelog.py <version>`
concatenates fragments into `CHANGELOG.md` under a dated heading and deletes
the consumed fragments. See `changelog.d/README.md`.

## Enforcement gate

No CI or deploy gate is wired yet. There is no `.github/workflows` directory
and no `ci-deploy.yml` or equivalent anywhere in this repo. Verification today
is local only: run the script, smoke-test the CLI paths described in the
README.

Promotion beyond staging requires the founder's explicit green light. Never
automatic on a passing gate. (Not currently applicable — see Environments:
there is no promotion target beyond the branch itself.)

## Secrets

`.env` (gitignored) holds `CLAUDE_CODE_OAUTH_TOKEN` as the name only; the real
token lives on the host, never in code, config, docs, logs, chat, or commits.
A committed credential is a global hard stop.
