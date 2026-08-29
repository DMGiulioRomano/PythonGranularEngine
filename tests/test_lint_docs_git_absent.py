"""Il linter dei doc non deve dipendere dalla disponibilita' di git.

La drift detection su `last_synced_commit` interroga git. Se git non c'e'
(PATH ripulito) o la history non c'e' (sorgenti copiati senza .git), il check
va spento: prima di questa guardia il linter moriva con FileNotFoundError
oppure segnalava un falso "non risolve" su ogni doc.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LINTER = REPO_ROOT / "utils" / "lint_docs.py"


def test_passa_senza_git_nel_path():
    env = dict(os.environ, PATH="")
    out = subprocess.run(
        [sys.executable, str(LINTER)],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "non risolve" not in out.stdout


def test_history_non_interrogabile_spegne_il_check(monkeypatch):
    """git c'e' ma non ha history da interrogare (sorgenti senza .git)."""
    sys.path.insert(0, str(REPO_ROOT / "utils"))
    import lint_docs

    lint_docs.history_available.cache_clear()
    monkeypatch.setattr(
        lint_docs.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 128, "", ""),
    )
    try:
        assert lint_docs.history_available() is False
    finally:
        lint_docs.history_available.cache_clear()


def test_sha_di_sole_cifre_non_e_uno_sha_stantio(monkeypatch):
    """PyYAML consegna int uno SHA non quotato; l'ottale va nominato."""
    sys.path.insert(0, str(REPO_ROOT / "utils"))
    import lint_docs

    lint_docs.history_available.cache_clear()
    monkeypatch.setattr(lint_docs, "history_available", lambda: False)
    fm = {
        "slug": "x", "type": "reference", "status": "stable",
        "tags": ["t"], "sources": ["utils/"],
    }
    lint = lint_docs.Linter()
    lint.check_frontmatter(REPO_ROOT / "docs" / "x.md", {**fm, "last_synced_commit": 9764017})
    assert lint.errors == []

    lint = lint_docs.Linter()
    lint.check_frontmatter(REPO_ROOT / "docs" / "x.md", {**fm, "last_synced_commit": 42798})
    assert any("quotalo" in e for e in lint.errors)
