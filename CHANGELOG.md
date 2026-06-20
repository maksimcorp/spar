# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- MAKSIMCORP development-protocol conformance baseline (MAK-110): `main`+`staging`
  branch model (renamed from `master`), canonical `ci-deploy.yml` gate
  (`verify` + `audit` gating `deploy-staging` via `needs`), thin `CLAUDE.md`, and
  `.env.example`.

### Notes
- Follow-ups: clear the `ruff` lint debt in `spar.py` and add a test suite, then make
  `ruff` and `pytest` blocking steps in the gate; add a dependency manifest.
