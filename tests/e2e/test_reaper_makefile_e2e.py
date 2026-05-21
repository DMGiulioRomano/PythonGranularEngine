# tests/e2e/test_reaper_makefile_e2e.py
"""
Test end-to-end per integrazione Makefile ↔ REAPER (target reaper-stop,
flag AUTOKILL_REAPER, default REAPER_PATH).

Issue: #17 — fix(reaper): progetto .rpp non si aggiorna se Reaper aperto
Plan:  docs/plans/2026-05-15-001-fix-reaper-autokill-multitab-plan.md

Scenari:
1. TestReaperStopTarget       - target `make reaper-stop` esiste e si comporta correttamente
2. TestAutokillReaperWiring   - flag AUTOKILL_REAPER aggiunge reaper-stop a prereq di `all`
3. TestReaperPathDefault      - default REAPER_PATH = $(FILE).rpp (era Project.rpp)

Esegui con:
  make e2e-tests
  oppure: pytest tests/e2e/test_reaper_makefile_e2e.py -m e2e -v
"""

import os
import subprocess

import pytest

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)


def _run_make(args, cwd=PROJECT_ROOT):
    """Esegue make con args; ritorna CompletedProcess."""
    return subprocess.run(
        ['make'] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


@pytest.mark.e2e
class TestReaperStopTarget:
    """Target `make reaper-stop` esiste e gestisce stato REAPER no-op."""

    def test_reaper_stop_target_exists(self):
        """`make -n reaper-stop` non deve fallire con 'No rule to make target'."""
        result = _run_make(['-n', 'reaper-stop'])
        assert result.returncode == 0, (
            f"`make -n reaper-stop` fallito (exit {result.returncode}).\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "No rule to make target" not in result.stderr, (
            f"Target reaper-stop non definito.\nstderr: {result.stderr}"
        )

    def test_reaper_stop_no_op_when_not_running(self):
        """
        Quando REAPER non e' in esecuzione, `make reaper-stop` esce 0 e stampa
        'Nothing to be done' (comportamento speculare a rx-stop).

        NB: il test assume che REAPER NON sia in esecuzione durante CI. Se lo
        fosse, il test verrebbe skippato.
        """
        check = subprocess.run(
            ['pgrep', '-x', 'REAPER'],
            capture_output=True,
            text=True,
        )
        if check.returncode == 0:
            pytest.skip("REAPER in esecuzione: test skippato per non disturbare l'utente")

        result = _run_make(['reaper-stop'])
        assert result.returncode == 0, (
            f"`make reaper-stop` fallito.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "Nothing to be done" in result.stdout or "nothing to be done" in result.stdout.lower(), (
            f"Output atteso 'Nothing to be done', got: {result.stdout}"
        )


@pytest.mark.e2e
class TestAutokillReaperWiring:
    """Flag AUTOKILL_REAPER aggancia reaper-stop come prereq di `all`."""

    def test_autokill_reaper_true_adds_reaper_stop_prereq(self):
        """
        Con AUTOKILL_REAPER=true REAPER=true, il dry-run di `make all` deve
        invocare reaper-stop prima del build.
        """
        result = _run_make([
            '-n', 'all',
            'AUTOKILL_REAPER=true',
            'REAPER=true',
            'AUTOPEN=false',
            'PRECLEAN=false',
        ])
        assert result.returncode == 0, (
            f"`make -n all` fallito.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "reaper-stop" in result.stdout, (
            f"AUTOKILL_REAPER=true non aggancia reaper-stop.\nstdout: {result.stdout}"
        )

    def test_autokill_reaper_false_does_not_add_reaper_stop(self):
        """
        Con AUTOKILL_REAPER=false (default), il dry-run di `make all` NON deve
        invocare reaper-stop.
        """
        result = _run_make([
            '-n', 'all',
            'AUTOKILL_REAPER=false',
            'REAPER=true',
            'AUTOPEN=false',
            'PRECLEAN=false',
        ])
        assert result.returncode == 0
        assert "reaper-stop" not in result.stdout, (
            f"AUTOKILL_REAPER=false non deve aggiungere reaper-stop.\nstdout: {result.stdout}"
        )

    def test_autokill_reaper_requires_reaper_true(self):
        """
        Con REAPER=false, anche AUTOKILL_REAPER=true non deve agganciare
        reaper-stop (no senso chiudere REAPER se non si esporta .rpp).
        """
        result = _run_make([
            '-n', 'all',
            'AUTOKILL_REAPER=true',
            'REAPER=false',
            'AUTOPEN=false',
            'PRECLEAN=false',
        ])
        assert result.returncode == 0
        assert "reaper-stop" not in result.stdout, (
            f"AUTOKILL_REAPER=true ma REAPER=false: reaper-stop non deve apparire.\n"
            f"stdout: {result.stdout}"
        )


@pytest.mark.e2e
class TestReaperPathDefault:
    """Default REAPER_PATH = $(FILE).rpp per multi-tab per YAML."""

    def test_default_reaper_path_matches_file_basename(self):
        """
        Con FILE=foo e nessun REAPER_PATH esplicito, `--reaper-path foo.rpp`
        deve apparire nel comando python (visibile via dry-run).
        """
        result = _run_make([
            '-n', 'all',
            'FILE=foo',
            'REAPER=true',
            'AUTOPEN=false',
            'PRECLEAN=false',
        ])
        assert result.returncode == 0, (
            f"`make -n all` fallito.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "--reaper-path foo.rpp" in result.stdout, (
            f"Default REAPER_PATH atteso 'foo.rpp', non trovato.\nstdout: {result.stdout}"
        )
        assert "Project.rpp" not in result.stdout, (
            f"Vecchio default 'Project.rpp' ancora presente.\nstdout: {result.stdout}"
        )
