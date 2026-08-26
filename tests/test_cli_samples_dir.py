# tests/test_cli_samples_dir.py
"""
Test di integrazione del flag CLI --samples-dir (issue #235).

Niente mock: si invoca `pge.cli.main()` per davvero, da un cwd che **non**
contiene `refs/`, con il sample scritto altrove. E' la verifica chiesta
dalla issue, e l'unica che dimostra la cosa che conta — che `./refs/`
smetta di essere un vincolo sulla directory di lavoro.

Copre anche la premessa sbagliata della issue: `--ssdir` non basta al
renderer csound. SSDIR dice a csound dove cercare i soundfile in fase di
render, ma la durata del sample la risolve `Stream.__init__` molto prima,
via `get_sample_duration` -> PATHSAMPLES. Il run muore li', identico al
caso numpy, e per questo la prova non ha bisogno di csound installato.
"""

import sys

import numpy as np
import pytest
import soundfile as sf
from unittest.mock import patch


_YAML = """\
seed: 42
streams:
  - stream_id: s1
    onset: 0
    duration: 0.5
    sample: pino.wav
    time_mode: normalized
    distribution_mode: uniform
    density: 10
    distribution: 0
    grain:
      duration: 0.05
      envelope: hanning
    pointer:
      start: 0
      speed_ratio: 1
    pitch:
      semitones: 0
    pan: 0
    volume: -6
"""


@pytest.fixture
def altrove(tmp_path, monkeypatch):
    """Un cwd senza `refs/` e una directory sample da tutt'altra parte.

    Ritorna (work_dir, samples_dir): il processo gira dentro work_dir, dove
    c'e' solo lo YAML.
    """
    samples_dir = tmp_path / "media" / "wavs"
    samples_dir.mkdir(parents=True)
    sr = 44100
    t = np.linspace(0, 1.0, sr, endpoint=False)
    sf.write(str(samples_dir / "pino.wav"),
             (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr)

    work = tmp_path / "work"
    (work / "output").mkdir(parents=True)
    (work / "mini.yml").write_text(_YAML)

    assert not (work / "refs").exists()
    monkeypatch.chdir(work)
    return work, samples_dir


def _run(argv):
    """Invoca la CLI reale con argv dato."""
    from pge.cli import main
    with patch.object(sys, 'argv', argv):
        main()


class TestNumpyRendersFromAnywhere:
    """La verifica della issue, renderer numpy."""

    def test_render_succeeds_with_samples_dir(self, altrove):
        work, samples_dir = altrove
        _run(['main.py', 'mini.yml', 'output/mini.wav',
              '--renderer', 'numpy', '--format', 'wav', '--jobs', '1',
              '--samples-dir', str(samples_dir)])
        out = work / "output" / "mini.wav"
        assert out.exists(), "nessun audio prodotto con --samples-dir"
        audio, _ = sf.read(str(out))
        assert np.any(audio != 0), "audio prodotto ma silenzioso"

    def test_without_the_flag_still_fails_on_refs(self, altrove, capsys):
        """Assente -> comportamento storico invariato: SampleNotFoundError
        su './refs/', exit 1."""
        with pytest.raises(SystemExit) as exc:
            _run(['main.py', 'mini.yml', 'output/mini.wav',
                  '--renderer', 'numpy', '--format', 'wav', '--jobs', '1'])
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Sample non trovato" in out
        assert "./refs/pino.wav" in out

    def test_trailing_separator_is_not_required(self, altrove):
        """`--samples-dir /dir` e `/dir/` sono la stessa directory: il
        separatore lo mette l'API (SampleRegistry e get_sample_duration
        concatenano base + filename)."""
        work, samples_dir = altrove
        _run(['main.py', 'mini.yml', 'output/mini.wav',
              '--renderer', 'numpy', '--format', 'wav', '--jobs', '1',
              '--samples-dir', str(samples_dir) + '/'])
        assert (work / "output" / "mini.wav").exists()


class TestSsdirIsNotEnoughForCsound:
    """La premessa che la issue da' per buona — «con csound il caso e' gia'
    coperto da --ssdir» — non regge: il run non arriva nemmeno al renderer.

    Nessuno di questi test richiede csound installato: e' esattamente il
    punto.
    """

    def test_ssdir_alone_dies_in_the_generator(self, altrove, capsys):
        _, samples_dir = altrove
        with pytest.raises(SystemExit) as exc:
            _run(['main.py', 'mini.yml', 'output/mini.aif',
                  '--renderer', 'csound', '--ssdir', str(samples_dir)])
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Sample non trovato" in out
        # Il path cercato e' PATHSAMPLES, non SSDIR: la lettura non e'
        # passata dal renderer.
        assert "./refs/pino.wav" in out

    def test_samples_dir_gets_csound_past_the_generator(self, altrove, capsys):
        """Con --samples-dir il Generator risolve, e il run prosegue: qui si
        ferma sul csound assente (o produce audio, se c'e'), non piu' sul
        sample."""
        _, samples_dir = altrove
        try:
            _run(['main.py', 'mini.yml', 'output/mini.aif',
                  '--renderer', 'csound', '--samples-dir', str(samples_dir)])
        except SystemExit:
            pass
        assert "Sample non trovato" not in capsys.readouterr().out
