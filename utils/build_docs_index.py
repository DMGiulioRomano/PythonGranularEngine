#!/usr/bin/env python3
"""Generate docs/INDEX.md from frontmatter of docs/{reference,explanation,how-to}/*.md.

Output is deterministic: scan order sorted, types in fixed order.
Run via `make docs-index`.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"
TYPES_ORDER = ["reference", "explanation", "how-to"]
TYPE_LABELS = {
    "reference": "Reference",
    "explanation": "Explanation",
    "how-to": "How-to",
}
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict | None:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    return yaml.safe_load(m.group(1))


def collect() -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for t in TYPES_ORDER:
        type_dir = DOCS / t
        if not type_dir.exists():
            continue
        for md in sorted(type_dir.glob("*.md")):
            text = md.read_text()
            fm = parse_frontmatter(text)
            if not fm:
                continue
            grouped[t].append(
                {
                    "slug": fm.get("slug", md.stem),
                    "status": fm.get("status", "?"),
                    "tags": fm.get("tags", []) or [],
                    "entry_for": fm.get("entry_for", []) or [],
                    "rel": md.relative_to(DOCS).as_posix(),
                }
            )
    return grouped


def render(grouped: dict[str, list[dict]]) -> str:
    lines: list[str] = [
        "# Docs Index",
        "",
        "> **Auto-generato.** Non editare a mano. Rigenera con `make docs-index`.",
        "",
    ]
    for t in TYPES_ORDER:
        items = grouped.get(t, [])
        if not items:
            continue
        lines.append(f"## {TYPE_LABELS[t]}")
        lines.append("")
        lines.append("| Slug | Status | Tags |")
        lines.append("|------|--------|------|")
        for it in items:
            tags = ", ".join(it["tags"])
            lines.append(f"| [{it['slug']}]({it['rel']}) | {it['status']} | {tags} |")
        lines.append("")

    entries: dict[str, list[str]] = defaultdict(list)
    for items in grouped.values():
        for it in items:
            for task in it["entry_for"]:
                entries[task].append(it["slug"])
    if entries:
        lines.append("## Entry points per task")
        lines.append("")
        lines.append("| Task | Doc |")
        lines.append("|------|-----|")
        for task in sorted(entries):
            slugs = ", ".join(sorted(entries[task]))
            lines.append(f"| {task} | {slugs} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    grouped = collect()
    out = render(grouped)
    target = DOCS / "INDEX.md"
    if "--check" in sys.argv:
        current = target.read_text() if target.exists() else ""
        if current.strip() != out.strip():
            print("docs/INDEX.md is stale. Run `make docs-index`.", file=sys.stderr)
            return 1
        return 0
    target.write_text(out + "\n")
    print(f"wrote {target.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
