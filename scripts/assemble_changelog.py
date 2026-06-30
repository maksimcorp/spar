#!/usr/bin/env python3
"""Assemble per-ticket changelog fragments into CHANGELOG.md at release time.

SPAR is a single-file CLI with no dependency manifest, so this assembler is a
self-contained, zero-dependency implementation of the towncrier/scriv pattern:
each ticket drops a fragment at ``changelog.d/<TICKET-KEY>.md`` and this script
concatenates them, grouped by category, under a dated version heading in
CHANGELOG.md, then deletes the consumed fragments.

This is the release step. Run it from a release branch:

    python scripts/assemble_changelog.py 1.2.0

Fragment format (Keep a Changelog categories):

    ### Added
    - Short, user-facing summary of the change (MAK-123)

A fragment may carry more than one category section. Standard categories
(Added, Changed, Deprecated, Removed, Fixed, Security) are emitted in Keep a
Changelog order; any other section (e.g. Notes) is appended after them in the
order first seen.

``changelog.d/README.md`` and dotfiles are ignored, never consumed.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

# Keep a Changelog category order. Sections outside this set are kept and
# appended after the known ones, in first-seen order, so nothing is lost.
CANONICAL_ORDER = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]

_HEADING_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$")
_VERSION_HEADING_RE = re.compile(r"^## \[")


def parse_fragment(text: str) -> dict[str, list[str]]:
    """Parse one fragment into {category: [entry lines]}.

    Recognizes ``### Category`` (or ``## Category``) headings followed by
    bullet lines. Bullets keep their original text (leading ``- `` stripped).
    """
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        heading = _HEADING_RE.match(line)
        if heading:
            current = heading.group(1).strip()
            sections.setdefault(current, [])
            continue
        stripped = line.lstrip()
        if stripped.startswith(("- ", "* ")):
            if current is None:
                raise ValueError("bullet found before any '### Category' heading")
            sections[current].append(stripped[2:].strip())
        elif stripped and current is not None:
            # Continuation line of the previous bullet (e.g. wrapped text).
            if not sections[current]:
                raise ValueError("text found before any bullet under a heading")
            sections[current][-1] += " " + stripped
    return {cat: entries for cat, entries in sections.items() if entries}


def collect_fragments(fragments_dir: Path) -> tuple[dict[str, list[str]], list[Path]]:
    """Merge every fragment file into one {category: [entries]} mapping.

    Returns the merged mapping and the list of consumed fragment paths (sorted
    for deterministic ordering). README and dotfiles are skipped.
    """
    merged: dict[str, list[str]] = {}
    consumed: list[Path] = []
    for path in sorted(fragments_dir.glob("*.md")):
        if path.name.lower() == "readme.md" or path.name.startswith("."):
            continue
        sections = parse_fragment(path.read_text(encoding="utf-8"))
        if not sections:
            continue
        for category, entries in sections.items():
            merged.setdefault(category, []).extend(entries)
        consumed.append(path)
    return merged, consumed


def render_section(version: str, date: str, merged: dict[str, list[str]]) -> str:
    """Render the dated version section body for CHANGELOG.md."""
    ordered = [c for c in CANONICAL_ORDER if c in merged]
    ordered += [c for c in merged if c not in CANONICAL_ORDER]
    out = [f"## [{version}] - {date}", ""]
    for category in ordered:
        out.append(f"### {category}")
        for entry in merged[category]:
            out.append(f"- {entry}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def splice_into_changelog(changelog: str, section: str) -> str:
    """Insert ``section`` above the first existing ``## [`` version heading.

    If no version heading exists yet, append after the file's preamble.
    """
    lines = changelog.splitlines()
    insert_at = next(
        (i for i, line in enumerate(lines) if _VERSION_HEADING_RE.match(line)),
        None,
    )
    block = section.rstrip("\n").splitlines()
    if insert_at is None:
        body = "\n".join(lines).rstrip("\n")
        return f"{body}\n\n" + "\n".join(block) + "\n"
    head = lines[:insert_at]
    tail = lines[insert_at:]
    return "\n".join(head + block + [""] + tail).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="Release version, e.g. 1.2.0")
    parser.add_argument(
        "--date",
        default=datetime.date.today().isoformat(),
        help="Release date YYYY-MM-DD (defaults to today)",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="Path to CHANGELOG.md (default: ./CHANGELOG.md)",
    )
    parser.add_argument(
        "--fragments",
        type=Path,
        default=Path("changelog.d"),
        help="Fragments directory (default: ./changelog.d)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the assembled CHANGELOG.md without writing or deleting fragments",
    )
    args = parser.parse_args(argv)

    if not args.changelog.exists():
        print(f"error: {args.changelog} not found", file=sys.stderr)
        return 1
    if not args.fragments.is_dir():
        print(f"error: {args.fragments} not found", file=sys.stderr)
        return 1

    merged, consumed = collect_fragments(args.fragments)
    if not consumed:
        print(
            f"error: no changelog fragments in {args.fragments}/ — nothing to release",
            file=sys.stderr,
        )
        return 1

    section = render_section(args.version, args.date, merged)
    updated = splice_into_changelog(args.changelog.read_text(encoding="utf-8"), section)

    if args.dry_run:
        sys.stdout.write(updated)
        print(
            f"\n--- dry-run: would consume {len(consumed)} fragment(s): "
            f"{', '.join(p.name for p in consumed)}",
            file=sys.stderr,
        )
        return 0

    args.changelog.write_text(updated, encoding="utf-8")
    for path in consumed:
        path.unlink()
    print(
        f"Assembled {len(consumed)} fragment(s) into {args.changelog} "
        f"under [{args.version}] - {args.date} and removed them."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
