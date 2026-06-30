# changelog.d — per-ticket changelog fragments

Unreleased changes live here as one fragment per ticket, not as a shared
`[Unreleased]` list in `CHANGELOG.md`. This is what lets parallel sessions add
changelog entries without colliding: each ticket writes its own file, so two
branches never edit the same lines.

## Adding an entry

When a ticket changes behavior, drop a fragment named for the ticket key:

    changelog.d/MAK-123.md

with one category-tagged entry (Keep a Changelog categories):

    ### Added
    - Short, user-facing summary of the change (MAK-123)

Categories: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
A fragment may carry more than one category section if a ticket genuinely spans
them. Keep it to the user-facing summary; details belong in the PR and the
ticket.

## Release (assembling fragments)

At release time the assembler concatenates every fragment into `CHANGELOG.md`
under a dated version heading and deletes the consumed fragments:

    python scripts/assemble_changelog.py 1.2.0          # writes CHANGELOG.md
    python scripts/assemble_changelog.py 1.2.0 --dry-run  # preview, no changes

`README.md` (this file) and dotfiles are never consumed.
