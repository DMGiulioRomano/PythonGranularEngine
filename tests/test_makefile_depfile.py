# tests/test_makefile_depfile.py
"""
Le depfile in `make/build.mk` (issue #290), lette con `make -n`.

L'e2e `TestNumpyMixStreamFile` (tests/e2e/test_numpy_renderer_e2e.py)
misura il giro intero con numpy: render, depfile, file importato modificato,
render rifatto. Il ramo csound non ha un e2e in MIX, e csound non c'e'
dappertutto; qui si legge cio' che make *farebbe*, per entrambi i renderer,
senza eseguire niente: la ricetta passa `--depfile`, e la depfile inclusa
porta i file importati fra i prerequisiti.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which('make') is None,
                                reason='make non disponibile')


@pytest.fixture
def progetto(tmp_path):
    """Un master in `configs/`, il suo file importato e il mix gia' reso."""
    configs = tmp_path / 'configs'
    (configs / 'streams').mkdir(parents=True)
    (configs / 'brano.yml').write_text(
        'streams:\n  - file: streams/s1.yml\n', encoding='utf-8')
    (configs / 'streams' / 's1.yml').write_text(
        'streams:\n  - stream_id: s1\n    sample: pino.wav\n',
        encoding='utf-8')
    (tmp_path / 'out').mkdir()
    (tmp_path / 'gen').mkdir()
    (tmp_path / 'logs').mkdir()
    return tmp_path


def _make_n(progetto, renderer, stems='false'):
    """`make -n all`: le ricette che make lancerebbe, senza lanciarle."""
    result = subprocess.run(
        ['make', '-n', 'all', 'FILE=brano', f'STEMS={stems}', 'CACHE=false',
         f'RENDERER={renderer}', 'PRECLEAN=false', 'REAPER=false',
         'AUTOKILL=false', 'AUTOPEN=false', 'AUTOVISUAL=false',
         f'YMLDIR={progetto / "configs"}', f'SFDIR={progetto / "out"}',
         f'GENDIR={progetto / "gen"}', f'LOGDIR={progetto / "logs"}'],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return [riga for riga in result.stdout.splitlines() if 'main.py' in riga]


def _mix_reso(progetto, mtime_importato_dopo):
    """Il mix esiste, piu' recente del master; il file importato prima o
    dopo di lui."""
    mix = progetto / 'out' / 'brano.aif'
    mix.write_bytes(b'')
    t = os.path.getmtime(mix)
    os.utime(progetto / 'configs' / 'brano.yml', (t - 200, t - 200))
    dopo = t + 100 if mtime_importato_dopo else t - 100
    os.utime(progetto / 'configs' / 'streams' / 's1.yml', (dopo, dopo))
    return mix


@pytest.mark.parametrize('renderer', ['numpy', 'csound'])
def test_la_ricetta_mix_passa_la_depfile(progetto, renderer):
    ricette = _make_n(progetto, renderer)

    assert len(ricette) == 1, ricette
    attesa = f"--depfile {progetto / 'gen'}/brano.aif.d"
    assert attesa in ricette[0], ricette[0]


@pytest.mark.parametrize('renderer', ['numpy', 'csound'])
def test_in_stems_niente_depfile(progetto, renderer):
    """In STEMS il target e' phony: il motore gira a ogni make, e la cache
    per stream fa il resto."""
    ricette = _make_n(progetto, renderer, stems='true')

    assert ricette, "la ricetta STEMS non lancia main.py?"
    assert not any('--depfile' in r for r in ricette), ricette


@pytest.mark.parametrize('renderer', ['numpy', 'csound'])
def test_la_depfile_inclusa_porta_il_file_importato(progetto, renderer):
    """Senza depfile make non vede il file importato; con la depfile in
    $(GENDIR), lo stesso file modificato dopo il mix fa rifare il mix."""
    mix = _mix_reso(progetto, mtime_importato_dopo=True)

    assert _make_n(progetto, renderer) == [], (
        "senza depfile make non ha modo di vedere il file importato: se "
        "rende qui, la premessa del test e' cambiata")

    from pge.export.depfile_writer import write_depfile
    write_depfile(str(progetto / 'gen' / 'brano.aif.d'), str(mix), [
        str(progetto / 'configs' / 'brano.yml'),
        str(progetto / 'configs' / 'streams' / 's1.yml')])

    assert len(_make_n(progetto, renderer)) == 1


@pytest.mark.parametrize('renderer', ['numpy', 'csound'])
def test_con_la_depfile_un_mix_aggiornato_resta_com_e(progetto, renderer):
    mix = _mix_reso(progetto, mtime_importato_dopo=False)
    from pge.export.depfile_writer import write_depfile
    write_depfile(str(progetto / 'gen' / 'brano.aif.d'), str(mix), [
        str(progetto / 'configs' / 'brano.yml'),
        str(progetto / 'configs' / 'streams' / 's1.yml')])

    assert _make_n(progetto, renderer) == []
