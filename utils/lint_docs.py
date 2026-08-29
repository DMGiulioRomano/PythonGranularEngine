#!/usr/bin/env python3
"""Lint docs/ for frontmatter completeness, schema compliance, and link integrity.

Rules (see docs/SCHEMAS.md — transitorio fino a Step 6, poi spostato in CLAUDE.md):
- Frontmatter presente con: slug, type, status, tags, sources, last_synced_commit
- slug uguale al basename del file (no .md)
- type ∈ {reference, explanation, how-to}, status ∈ {stable, draft, deprecated}
- sources path esistenti
- last_synced_commit risolvibile a un oggetto git
- Sezioni obbligatorie per tipo presenti, nell'ordine atteso
- Wikilink [[slug]] risolvibili a uno slug noto
- Nessun doc orfano (linkato da INDEX o da almeno un altro doc, esclusi i reference)

Exit code 0 se pulito, 1 altrimenti.
"""
from __future__ import annotations

import re
import subprocess
import sys
from functools import cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"
TYPES = {"reference", "explanation", "how-to"}
STATUSES = {"stable", "draft", "deprecated"}
SHA_RE = re.compile(r"[0-9a-f]{7,40}")
REQUIRED_FM_KEYS = {"slug", "type", "status", "tags", "sources", "last_synced_commit"}

REQUIRED_SECTIONS = {
    "reference": ["Scope", "Sintassi", "Bounds", "Esempi", "Versionato da"],
    "explanation": [
        "Problema",
        "Modello",
        "Trade-off",
        "Implicazioni codice",
        "Vedi anche",
    ],
    "how-to": [
        "Quando usarlo",
        "Prerequisiti",
        "Passi",
        "File toccati",
        "Test da aggiornare",
        "Verifica",
    ],
}

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
H2_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)


INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def strip_code_blocks(text: str) -> str:
    out = []
    in_code = False
    for line in text.split("\n"):
        if line.startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            out.append(INLINE_CODE_RE.sub("", line))
    return "\n".join(out)


@cache
def history_available() -> bool:
    """True se git puo' rispondere sulla history di questo albero.

    False su un clone shallow (non risolve niente per costruzione), ma anche
    dove git non c'e' o .git non c'e': sorgenti copiati, vendoring, archivio.
    In tutti quei casi il check sugli SHA va spento, non fallito.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
    except (OSError, FileNotFoundError):
        return False
    if out.returncode:
        return False
    return out.stdout.strip() != "true"


class Linter:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.docs: dict[str, dict] = {}

    def err(self, path: Path, msg: str) -> None:
        rel = path.relative_to(REPO_ROOT)
        self.errors.append(f"{rel}: {msg}")

    def parse(self, path: Path) -> tuple[dict | None, str]:
        text = path.read_text()
        m = FRONTMATTER_RE.match(text)
        if not m:
            return None, text
        try:
            fm = yaml.safe_load(m.group(1))
        except yaml.YAMLError as e:
            self.err(path, f"frontmatter YAML parse: {e}")
            return None, text
        body = text[m.end():]
        return fm, body

    def check_frontmatter(self, path: Path, fm: dict) -> None:
        missing = REQUIRED_FM_KEYS - set(fm.keys())
        if missing:
            self.err(path, f"frontmatter missing keys: {sorted(missing)}")
            return
        if fm["slug"] != path.stem:
            self.err(path, f"slug '{fm['slug']}' != basename '{path.stem}'")
        if fm["type"] not in TYPES:
            self.err(path, f"type '{fm['type']}' invalid (expected one of {TYPES})")
        if fm["status"] not in STATUSES:
            self.err(path, f"status '{fm['status']}' invalid")
        if not isinstance(fm["tags"], list) or not fm["tags"]:
            self.err(path, "tags must be non-empty list")
        if not isinstance(fm["sources"], list) or not fm["sources"]:
            self.err(path, "sources must be non-empty list")
        else:
            for src in fm["sources"]:
                p = REPO_ROOT / src
                if not p.exists():
                    self.err(path, f"sources path does not exist: {src}")
        # Uno SHA breve di sole cifre non e' quotato per convenzione (lo sono
        # tutti nei doc), quindi PyYAML lo consegna int: str() lo rende, e
        # 9764017 resta 9764017. Irrecuperabile e' solo lo zero iniziale, che
        # YAML 1.1 legge ottale (0123456 -> 42798): li' l'informazione e'
        # persa, e il messaggio deve nominare il quoting invece di far
        # sembrare stantio un doc che non lo e'.
        sha = str(fm["last_synced_commit"]).strip()
        if not SHA_RE.fullmatch(sha):
            self.err(
                path,
                f"last_synced_commit non e' uno SHA breve: {sha} "
                "(se e' di sole cifre con lo zero iniziale, quotalo: "
                "YAML lo legge come ottale)",
            )
            return
        # Senza questo, la drift detection e' decorativa: uno SHA che non
        # risolve non e' un riferimento, e' una stringa. Dove la history non
        # e' interrogabile il check si spegne invece di segnalare venti falsi
        # positivi (in CI il job docs fa fetch-depth: 0 apposta per tenerlo
        # acceso).
        if history_available() and subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode:
            self.err(path, f"last_synced_commit non risolve a un commit: {sha}")

    def check_sections(self, path: Path, fm: dict, body: str) -> None:
        type_ = fm.get("type")
        required = REQUIRED_SECTIONS.get(type_, [])
        if not required:
            return
        found = {m.group(1).strip() for m in H2_RE.finditer(body)}
        for needed in required:
            if needed not in found:
                self.err(path, f"missing section '## {needed}'")

    def collect_doc_dir(self, type_: str) -> list[Path]:
        d = DOCS / type_
        if not d.exists():
            return []
        return sorted(d.glob("*.md"))

    def run(self) -> int:
        all_paths: list[Path] = []
        for t in TYPES:
            all_paths.extend(self.collect_doc_dir(t))

        for p in all_paths:
            fm, body = self.parse(p)
            if fm is None:
                self.err(p, "missing frontmatter block")
                continue
            self.check_frontmatter(p, fm)
            self.check_sections(p, fm, body)
            slug = fm.get("slug", p.stem)
            self.docs[slug] = {"path": p, "fm": fm, "body": body}

        for slug, info in self.docs.items():
            body_no_code = strip_code_blocks(info["body"])
            for m in WIKILINK_RE.finditer(body_no_code):
                target = m.group(1).strip()
                if target == "INDEX":
                    continue
                if target not in self.docs:
                    self.err(info["path"], f"unresolved wikilink [[{target}]]")

        rogue = sorted(
            p for p in DOCS.glob("*.md") if p.name not in {"INDEX.md", "SCHEMAS.md"}
        )
        for p in rogue:
            self.err(p, "doc in docs/ root — must live under reference/explanation/how-to")

        if self.errors:
            print("docs-lint: FAIL", file=sys.stderr)
            for e in self.errors:
                print(f"  {e}", file=sys.stderr)
            return 1
        print(f"docs-lint: OK ({len(self.docs)} docs)")
        return 0


if __name__ == "__main__":
    raise SystemExit(Linter().run())
