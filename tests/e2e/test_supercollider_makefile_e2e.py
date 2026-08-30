# tests/e2e/test_supercollider_makefile_e2e.py
"""
Test sul Makefile per il backend SuperCollider (issue #228, review PR #240).

Non richiedono SuperCollider: girano su `make -n`, che stampa i comandi senza
eseguirli. Coprono la combinazione dei DEFAULT, che e' proprio quella che
nessun altro test vedeva -- l'e2e vero passa `PRECLEAN=false` e un
`SC_SYNTHDEF_DIR` tutto suo, quindi non poteva accorgersi di come si
comportano i valori che un utente si trova senza chiedere niente.

Scenari:
1. TestSynthDefSopravviveAClean - il .scsyndef non sta dove `clean` passa
2. TestFlagVuoti               - una variabile svuotata non produce un flag nudo
"""

import os
import re
import subprocess

import pytest

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)


def _make_n(*args):
    """`make -n` (dry run): stampa i comandi senza eseguirli."""
    result = subprocess.run(
        ['make', '-n', 'all', *args],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    return (result.stdout or '') + (result.stderr or '')


def _flag_value(output, flag):
    """Valore che il comando passa a `flag`, o None se il flag non c'e'."""
    m = re.search(rf'{re.escape(flag)}\s+(\S+)', output)
    return m.group(1) if m else None


# =============================================================================
# 1. LA SYNTHDEF SOPRAVVIVE A CLEAN
# =============================================================================

@pytest.mark.e2e
class TestSynthDefSopravviveAClean:
    """Il `.scsyndef` e' un artefatto persistente: se sta dove `make clean`
    passa, ogni build lo cancella e sclang riparte -- con l'avvio di Qt in
    mezzo. Non e' un guasto (il renderer lo ricompila) ma trasforma sclang da
    dipendenza di build a dipendenza di runtime, che e' l'opposto della
    premessa su cui il backend e' progettato.
    """

    def test_clean_svuota_gendir(self):
        """Premessa del test successivo: se un giorno `clean` smettesse di
        svuotare GENDIR, il vincolo qui sotto perderebbe la sua ragione e
        varrebbe la pena saperlo."""
        result = subprocess.run(
            ['make', '-n', 'clean'],
            cwd=PROJECT_ROOT, capture_output=True, text=True)
        assert 'rm -rf generated/' in (result.stdout or '')

    def test_default_fuori_da_gendir(self):
        dir_synthdef = _flag_value(
            _make_n('RENDERER=supercollider'), '--sc-synthdef-dir')
        assert dir_synthdef is not None
        assert not dir_synthdef.rstrip('/').endswith('generated')

    def test_clean_e_prerequisito_con_cache_false(self):
        """La configurazione in cui il difetto si manifestava: CACHE=false
        rimette `clean` fra i prerequisiti di `all`."""
        assert 'rm -rf generated/' in _make_n(
            'RENDERER=supercollider', 'CACHE=false')

    def test_la_synthdef_non_e_nel_mirino_nemmeno_li(self):
        output = _make_n('RENDERER=supercollider', 'CACHE=false')
        dir_synthdef = _flag_value(output, '--sc-synthdef-dir')
        assert 'rm -rf generated/' in output, "il clean deve esserci davvero"
        assert not dir_synthdef.rstrip('/').endswith('generated')


# =============================================================================
# 2. FLAG VUOTI
# =============================================================================

@pytest.mark.e2e
class TestFlagVuoti:
    """Una variabile Make svuotata a mano non deve produrre un flag nudo: il
    parsing della CLI legge `sys.argv[idx+1]` senza controllare il prefisso
    `--`, quindi si mangerebbe il flag successivo come valore.
    """

    @pytest.mark.parametrize("var, flag", [
        ("SC_SYNTHDEF_SOURCE", "--sc-synthdef-source"),
        ("SC_SYNTHDEF_DIR", "--sc-synthdef-dir"),
        ("SC_BLOCK_SIZE", "--sc-block-size"),
        ("SC_MAX_NODES", "--sc-max-nodes"),
    ])
    def test_variabile_vuota_non_emette_il_flag(self, var, flag):
        output = _make_n('RENDERER=supercollider', f'{var}=')
        comando = [r for r in output.splitlines() if 'main.py' in r]
        assert comando, "nessun comando di render nell'output di make -n"
        assert flag not in comando[0]

    def test_i_flag_valorizzati_ci_sono(self):
        """Controprova: il guard non deve zittire anche i valori veri."""
        output = _make_n('RENDERER=supercollider',
                         'SC_BLOCK_SIZE=64', 'SC_MAX_NODES=4096')
        assert _flag_value(output, '--sc-block-size') == '64'
        assert _flag_value(output, '--sc-max-nodes') == '4096'
