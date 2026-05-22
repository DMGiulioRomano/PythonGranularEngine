# tests/e2e/test_clean_rpp_e2e.py
"""
Test end-to-end per target `clean-rpp` e flag `CLEAN_RPP` in `make clean`.

Issue: #65 — feat(reaper): spostare .rpp in output/ + clean-rpp con flag CLEAN_RPP
Plan:  docs/plans/2026-05-22-002-rpp-output-dir-plan.md

Scenari:
1. TestCleanRppTarget       - `make clean-rpp` esiste e rimuove .rpp in $(SFDIR) + root
2. TestCleanDefaultPreserve - `make clean` default (CLEAN_RPP=false) preserva .rpp
3. TestCleanWithFlag        - `make clean CLEAN_RPP=true` rimuove anche .rpp

Esegui con:
  pytest tests/e2e/test_clean_rpp_e2e.py -m e2e -v
"""

import os
import subprocess

import pytest

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)


def _run_make(args, cwd=PROJECT_ROOT):
    return subprocess.run(
        ['make'] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


@pytest.mark.e2e
class TestCleanRppTarget:
    """Target `make clean-rpp` esiste e ha le rm corrette."""

    def test_clean_rpp_target_exists(self):
        """`make -n clean-rpp` non fallisce con 'No rule to make target'."""
        result = _run_make(['-n', 'clean-rpp'])
        assert result.returncode == 0, (
            f"`make -n clean-rpp` fallito.\nstderr: {result.stderr}"
        )
        assert "No rule to make target" not in result.stderr

    def test_clean_rpp_removes_rpp_in_sfdir(self):
        """`clean-rpp` rimuove .rpp in $(SFDIR) (output/)."""
        result = _run_make(['-n', 'clean-rpp'])
        assert "rm -f output/*.rpp" in result.stdout or \
               "rm -f output/*.rpp " in result.stdout, (
            f"clean-rpp non rimuove output/*.rpp.\nstdout: {result.stdout}"
        )

    def test_clean_rpp_removes_rpp_in_root(self):
        """`clean-rpp` rimuove .rpp legacy in root."""
        result = _run_make(['-n', 'clean-rpp'])
        assert "rm -f *.rpp" in result.stdout, (
            f"clean-rpp non rimuove *.rpp in root.\nstdout: {result.stdout}"
        )


@pytest.mark.e2e
class TestCleanDefaultPreserveRpp:
    """`make clean` default (CLEAN_RPP=false) preserva .rpp."""

    def test_clean_default_does_not_wipe_sfdir_blindly(self):
        """
        `make -n clean` default NON deve contenere `rm -rf output/*` (wipe totale).
        Deve invece usare `find` con esclusione .rpp.
        """
        result = _run_make(['-n', 'clean'])
        assert result.returncode == 0
        # Default-safe: no wipe totale di SFDIR
        assert "rm -rf generated/* output/* logs/*" not in result.stdout, (
            f"clean default fa wipe totale SFDIR (perde .rpp).\nstdout: {result.stdout}"
        )

    def test_clean_default_preserves_rpp_via_find(self):
        """`clean` default usa `find` con `-not -name '*.rpp'` per preservare .rpp."""
        result = _run_make(['-n', 'clean'])
        assert "find output" in result.stdout, (
            f"clean default non usa find su output/.\nstdout: {result.stdout}"
        )
        assert "*.rpp" in result.stdout, (
            f"clean default non menziona pattern *.rpp.\nstdout: {result.stdout}"
        )


@pytest.mark.e2e
class TestCleanWithFlag:
    """`make clean CLEAN_RPP=true` rimuove anche .rpp."""

    def test_clean_with_flag_wipes_sfdir(self):
        """Con CLEAN_RPP=true, `clean` fa wipe totale incluso .rpp."""
        result = _run_make(['-n', 'clean', 'CLEAN_RPP=true'])
        assert result.returncode == 0
        assert "rm -rf generated/* output/* logs/*" in result.stdout, (
            f"clean CLEAN_RPP=true non fa wipe totale.\nstdout: {result.stdout}"
        )
