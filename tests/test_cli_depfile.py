# tests/test_cli_depfile.py
"""
Il flag CLI `--depfile FILE` (issue #290): una depfile di make con le
dipendenze del render, cioe' il master e ogni file importato con `file:`.

Senza, `make all STEMS=false` non vedeva i file importati: la regola
`$(SFDIR)/%.aif: $(YMLDIR)/%.yml` dipende dal solo master, e modificare
soltanto lo stream importato lasciava l'audio di prima. Il Makefile passa il
flag nelle regole non-STEMS e include le depfile (`make/build.mk`); qui si
verifica il lato del motore, invocando `pge.cli.main()` per davvero.
"""
import sys

import numpy as np
import pytest
import soundfile as sf
from unittest.mock import patch

from pge.export.depfile_writer import make_depfile


_MASTER = """\
seed: 42
streams:
  - file: streams/s1.yml
    onset: 0.25
"""

_IMPORTATO = """\
seed: 42
streams:
  - stream_id: s1
    onset: 0
    duration: 0.3
    sample: {sample}
    density: 10
    grain:
      duration: 0.05
"""


@pytest.fixture
def brano(tmp_path, monkeypatch):
    """Un cwd con il master, `streams/s1.yml` e una cartella di sample."""
    samples = tmp_path / 'wavs'
    samples.mkdir()
    sr = 44100
    t = np.linspace(0, 1.0, sr, endpoint=False)
    sf.write(str(samples / 'pino.wav'),
             (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr)

    work = tmp_path / 'work'
    (work / 'streams').mkdir(parents=True)
    # La cartella dell'output la crea make (`| $(SFDIR)`), non la CLI.
    (work / 'out').mkdir()
    (work / 'brano.yml').write_text(_MASTER, encoding='utf-8')
    monkeypatch.chdir(work)

    def importato(sample='pino.wav'):
        (work / 'streams' / 's1.yml').write_text(
            _IMPORTATO.format(sample=sample), encoding='utf-8')

    importato()

    class Brano:
        root = work
        samples_dir = str(samples) + '/'
    b = Brano()
    b.importato = importato
    return b


def _argv(brano, *extra):
    return ['main.py', 'brano.yml', 'out/brano.wav', '--renderer', 'numpy',
            '--jobs', '1', '--format', 'wav',
            '--samples-dir', brano.samples_dir, *extra]


def _run(argv, codice=None):
    from pge.cli import main
    with patch.object(sys, 'argv', argv):
        if codice is None:
            main()
            return
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == codice


def test_la_depfile_nomina_il_target_il_master_e_i_file_importati(brano):
    """Il target e' l'output come la CLI l'ha ricevuto: e' il `$@` della
    regola di make, e make confronta i nomi come stringhe."""
    _run(_argv(brano, '--depfile', 'generated/brano.wav.d'))

    assert (brano.root / 'out' / 'brano.wav').exists()
    assert (brano.root / 'generated' / 'brano.wav.d').read_text(
        encoding='utf-8') == make_depfile(
            'out/brano.wav', ['brano.yml', 'streams/s1.yml'])


def test_e_scritta_anche_se_il_render_muore_dopo_il_caricamento(brano):
    """La depfile dice che cosa il master importa, e lo si sa appena il
    master e' caricato: un sample mancante nel file importato non toglie che
    quel file sia una dipendenza -- e' anzi quello da correggere."""
    brano.importato(sample='assente.wav')

    _run(_argv(brano, '--depfile', 'generated/brano.wav.d'), codice=1)

    assert not (brano.root / 'out' / 'brano.wav').exists()
    depfile = brano.root / 'generated' / 'brano.wav.d'
    assert 'streams/s1.yml' in depfile.read_text(encoding='utf-8')


def test_senza_il_flag_nessuna_depfile(brano):
    _run(_argv(brano))

    assert (brano.root / 'out' / 'brano.wav').exists()
    assert not list(brano.root.rglob('*.d'))


def test_il_flag_senza_valore_e_un_errore(brano, capsys):
    """Come `--samples-dir` e `--log-dir`: ignorarlo renderebbe senza
    depfile, e make continuerebbe a non vedere i file importati -- un
    fallimento che somiglia al successo."""
    _run(_argv(brano, '--depfile'), codice=1)

    assert capsys.readouterr().out == (
        "--depfile richiede un file. "
        "Esempio: --depfile generated/brano.aif.d\n")
    assert not (brano.root / 'out' / 'brano.wav').exists()
