"""
Test detection Python in make/test.mk.

Verifica che la detection multi-versione risolva correttamente PYTHON_CMD
in scenari diversi (binario versionato, fallback python3 generico, errore).

Strategia:
- monkeypatch PATH con tmp_path che contiene fake script bash python3.X
- invoca `make -n check-python` (o target dummy) e parsa output
- non esegue codice Python reale: i fake rispondono solo a --version e -c
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path
import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_fake_python(tmp_path: Path, name: str, version: str) -> Path:
    """
    Crea fake binario `name` in tmp_path che simula `python --version` e `python -c`.

    --version → stampa "Python <version>" su stdout (Python reale stampa su stdout dalla 3.4+)
    -c <code> → esegue il codice ma rimpiazza sys.version_info con version (best-effort)
                Per semplicità: parsa version (es. "3.14.0") e fornisce un sys mock minimo.
    Altre invocazioni → exit 1.
    """
    parts = version.split(".")
    major, minor, patch = parts[0], parts[1], parts[2] if len(parts) > 2 else "0"
    script = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        if [ "$1" = "--version" ]; then
            echo "Python {version}"
            exit 0
        fi
        if [ "$1" = "-c" ]; then
            # Esegui un python3 reale del sistema ma con sys.version_info patchato.
            # Cerchiamo un python3 reale fuori dal PATH ristretto del test.
            REAL_PY=""
            for cand in /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
                if [ -x "$cand" ]; then REAL_PY="$cand"; break; fi
            done
            if [ -z "$REAL_PY" ]; then
                echo "no real python available" >&2
                exit 99
            fi
            # Patcha sys.version_info via prelude (tuple plain — supporta indexing e comparison)
            PRELUDE="import sys; sys.version_info = ({major},{minor},{patch},'final',0)"
            "$REAL_PY" -c "$PRELUDE; $2"
            exit $?
        fi
        exit 1
    """)
    bin_path = tmp_path / name
    bin_path.write_text(script)
    bin_path.chmod(0o755)
    return bin_path


def _make_fake_which(tmp_path: Path) -> None:
    """
    Crea un `which` falso in tmp_path che cerca solo in tmp_path.

    Previene che `$(shell which pythonX.Y)` nel Makefile trovi binari di sistema
    (es. /usr/bin/python3.12) quando il test vuole un PATH isolato.
    """
    script = textwrap.dedent(f"""\
        #!/bin/sh
        if [ -x "{tmp_path}/$1" ]; then
            echo "{tmp_path}/$1"
            exit 0
        fi
        exit 1
    """)
    bin_path = tmp_path / "which"
    bin_path.write_text(script)
    bin_path.chmod(0o755)


def _make_python3_sentinel(tmp_path: Path) -> None:
    """
    Crea un python3 sentinel in tmp_path che fallisce sempre.

    Blocca il fallback `$(shell python3 -c ...)` del Makefile dal trovare
    python3 di sistema quando il test simula assenza di Python valido.
    Solo creato se python3 non è già presente in tmp_path.
    """
    script = textwrap.dedent("""\
        #!/bin/sh
        exit 1
    """)
    bin_path = tmp_path / "python3"
    bin_path.write_text(script)
    bin_path.chmod(0o755)


def _run_make(target: str, env_path: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """
    Esegue `make -n <target>` con PATH controllato.

    Include /usr/bin:/bin in PATH per permettere a make stesso di trovare shell/sed/awk.
    Aggiunge tmp_path in testa con `which` falso per isolare la detection Python
    dai binari di sistema (es. /usr/bin/python3.12 su Fedora).
    """
    env_path_obj = Path(env_path)
    _make_fake_which(env_path_obj)
    if not (env_path_obj / "python3").exists():
        _make_python3_sentinel(env_path_obj)

    env = os.environ.copy()
    env["PATH"] = f"{env_path}:/usr/bin:/bin"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["make", "-n", target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def _resolved_python_cmd(make_output: str) -> str | None:
    """
    Estrae il PYTHON_CMD effettivo dall'output di `make -n check-python`.

    Cerca pattern `pythonX.Y` o `python3` nei comandi shell stampati da make.
    """
    import re
    # check-python esegue: $(PYTHON_CMD) -c "..."
    match = re.search(r"\b(python3(?:\.\d+)?)\s+-c", make_output)
    return match.group(1) if match else None


class TestMakeLevelDetection:
    """Detection Make-level: fake binari nel PATH, verifica selezione PYTHON_CMD."""

    def test_python3_9_versioned_selected(self, tmp_path):
        """Nuovo minimo supportato: python3.9 versionato → PYTHON_CMD := python3.9."""
        _make_fake_python(tmp_path, "python3.9", "3.9.18")
        result = _run_make("check-python", str(tmp_path))
        assert result.returncode == 0, f"make failed: {result.stderr}"
        assert _resolved_python_cmd(result.stdout) == "python3.9", \
            f"expected python3.9, got output:\n{result.stdout}"

    def test_python3_12_versioned_selected(self, tmp_path):
        """Happy path classico: python3.12 versionato → PYTHON_CMD := python3.12."""
        _make_fake_python(tmp_path, "python3.12", "3.12.7")
        result = _run_make("check-python", str(tmp_path))
        assert result.returncode == 0, f"make failed: {result.stderr}"
        assert _resolved_python_cmd(result.stdout) == "python3.12", \
            f"expected python3.12, got output:\n{result.stdout}"

    def test_python3_14_only_arch_manjaro_scenario(self, tmp_path):
        """Scenario Arch/Manjaro: solo python3.14 versionato → PYTHON_CMD := python3.14."""
        _make_fake_python(tmp_path, "python3.14", "3.14.0")
        result = _run_make("check-python", str(tmp_path))
        assert result.returncode == 0, f"make failed: {result.stderr}"
        assert _resolved_python_cmd(result.stdout) == "python3.14", \
            f"expected python3.14, got output:\n{result.stdout}"

    def test_python3_generic_fallback(self, tmp_path):
        """Edge case: solo `python3` generico (versione >= 3.9) → fallback."""
        _make_fake_python(tmp_path, "python3", "3.13.2")
        result = _run_make("check-python", str(tmp_path))
        assert result.returncode == 0, f"make failed: {result.stderr}"
        assert _resolved_python_cmd(result.stdout) == "python3", \
            f"expected python3 fallback, got output:\n{result.stdout}"

    def test_python3_generic_fallback_at_minimum(self, tmp_path):
        """Boundary: `python3` generico a 3.9.0 (minimo esatto) → accettato via fallback."""
        _make_fake_python(tmp_path, "python3", "3.9.0")
        result = _run_make("check-python", str(tmp_path))
        assert result.returncode == 0, f"make failed: {result.stderr}"
        assert _resolved_python_cmd(result.stdout) == "python3", \
            f"expected python3 fallback, got output:\n{result.stdout}"

    def test_python3_8_generic_rejected(self, tmp_path):
        """Boundary: `python3` generico a 3.8.x (sotto il minimo) → make $(error)."""
        _make_fake_python(tmp_path, "python3", "3.8.18")
        result = _run_make("check-python", str(tmp_path))
        assert result.returncode != 0, \
            f"expected failure for python3.8 (< 3.9), got success:\n{result.stdout}"

    def test_no_python_in_path_fails(self, tmp_path):
        """Error path: nessun binario Python nel PATH ristretto → make $(error)."""
        result = _run_make("check-python", str(tmp_path))
        assert result.returncode != 0, \
            f"expected failure with no python, got success:\n{result.stdout}"


class TestCheckSystemDeps:
    """check-system-deps deve riusare PYTHON_CMD di test.mk (no command -v python3.12)."""

    def test_check_system_deps_uses_python_cmd(self, tmp_path):
        """check-system-deps non deve hardcodare python3.12: usa $(PYTHON_CMD)."""
        _make_fake_python(tmp_path, "python3.14", "3.14.0")
        result = _run_make("check-system-deps", str(tmp_path))
        # Post-fix: deve passare con python3.14 (no symlink python3 necessario)
        assert result.returncode == 0, \
            f"check-system-deps failed on Arch-like setup:\n{result.stderr}\n{result.stdout}"
        # Verifica che NON ci sia riferimento hardcoded a python3.12
        assert "command -v python3.12" not in result.stdout, \
            "check-system-deps still hardcodes python3.12"
