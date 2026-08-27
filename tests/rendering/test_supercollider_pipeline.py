# tests/rendering/test_supercollider_pipeline.py
"""
Test di integrazione del backend SuperCollider (issue #228): YAML vero ->
Generator vero -> score .osc vero, con il solo subprocess scsynth sostituito.

I test unitari verificano i pezzi in isolamento con Stream finti; qui si
verifica che i pezzi siano collegati -- che i numeri di tabella del
FtableManager arrivino davvero ai buffer, che i grani generati dallo Stream
finiscano davvero nello score, che il path del sample sia quello risolto dal
Generator. E' l'unica prova possibile senza SuperCollider installato che la
pipeline sia intera, e non richiede scsynth ne' sclang.
"""

import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import soundfile as sf

from pge import api
from tests.rendering.test_osc import decode_nrt


YAML = """\
composition:
  title: "integrazione supercollider"

seed: 7

streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 1.0
    sample: "tono.wav"
    density: 20
    grain:
      duration: 0.05
      envelope: "hanning"
  - stream_id: "s2"
    onset: 1.0
    duration: 1.0
    sample: "tono.wav"
    density: 10
    grain:
      duration: 0.08
      envelope: "blackman"
"""


@pytest.fixture
def progetto(tmp_path):
    """Un progetto minimo su disco: sample, YAML, SynthDef gia' compilata."""
    refs = tmp_path / "refs"
    refs.mkdir()
    sf.write(str(refs / "tono.wav"),
             np.sin(2 * np.pi * 440 * np.arange(48000) / 48000).astype('float32'),
             48000)

    yaml_path = tmp_path / "brano.yml"
    yaml_path.write_text(YAML)

    defs = tmp_path / "generated"
    defs.mkdir()
    (defs / "pgeGrain.scsyndef").write_bytes(b'SCgf-FINTA')

    return {
        'yaml': str(yaml_path),
        'refs': str(refs),
        'defs': str(defs),
        'out': str(tmp_path / "out.aif"),
    }


def _render(progetto, **kwargs):
    """Esegue render_file col backend SuperCollider, catturando lo score."""
    catturato = {}

    def spia(cmd, **_):
        with open(cmd[cmd.index('-N') + 1], 'rb') as f:
            catturato.setdefault('score', []).append(decode_nrt(f.read()))
        catturato.setdefault('cmd', []).append(cmd)
        return MagicMock(returncode=0, stdout='', stderr='')

    with patch('pge.rendering.supercollider_renderer.subprocess.run',
               side_effect=spia):
        result = api.render_file(
            progetto['yaml'], progetto['out'],
            renderer='supercollider',
            samples_dir=progetto['refs'],
            supercollider=api.SuperColliderOptions(
                synthdef_dir=progetto['defs']),
            **kwargs,
        )
    return result, catturato


def _messaggi(score, address):
    return [(t, args) for t, elements in score
            for addr, args in elements if addr == address]


# =============================================================================
# MIX
# =============================================================================

class TestPipelineMix:

    def test_render_result_dichiara_il_backend(self, progetto):
        result, _ = _render(progetto)
        assert result.renderer_type == 'supercollider'
        assert result.audio_paths == [progetto['out']]

    def test_un_solo_score_per_il_mix(self, progetto):
        _, catturato = _render(progetto)
        assert len(catturato['score']) == 1

    def test_il_sample_del_generator_finisce_nei_buffer(self, progetto):
        _, catturato = _render(progetto)
        alloc = _messaggi(catturato['score'][0], '/b_allocReadChannel')
        assert len(alloc) == 1
        assert alloc[0][1][1] == os.path.abspath(
            os.path.join(progetto['refs'], 'tono.wav'))

    def test_una_finestra_per_envelope_dichiarato(self, progetto):
        """Lo YAML dichiara hanning e blackman: due tabelle dal
        FtableManager, piu' il buffer piatto del writer."""
        _, catturato = _render(progetto)
        allocs = _messaggi(catturato['score'][0], '/b_alloc')
        assert len(allocs) == 3

    def test_un_s_new_per_grano_generato(self, progetto):
        result, catturato = _render(progetto)
        # La lista dei grani e' la stessa che vedrebbe qualunque altro
        # consumatore: il confronto e' con il Generator, non con un numero
        # scritto a mano.
        generator = api.load_generator(progetto['yaml'],
                                       samples_dir=progetto['refs'])
        attesi = sum(len(voice)
                     for stream in generator.streams
                     for voice in stream.voices)
        assert len(_messaggi(catturato['score'][0], '/s_new')) == attesi
        assert attesi > 0

    def test_onset_assoluti_coprono_i_due_stream(self, progetto):
        _, catturato = _render(progetto)
        tempi = [t for t, _ in _messaggi(catturato['score'][0], '/s_new')]
        assert min(tempi) < 1.0, "il primo stream parte da zero"
        assert max(tempi) >= 1.0, "il secondo stream sta dopo il suo onset"

    def test_lo_score_finisce_dopo_l_ultimo_grano(self, progetto):
        _, catturato = _render(progetto)
        score = catturato['score'][0]
        ultimo_grano = max(t for t, _ in _messaggi(score, '/s_new'))
        assert score[-1][0] >= ultimo_grano

    def test_output_e_formato_sulla_riga_di_comando(self, progetto):
        _, catturato = _render(progetto)
        cmd = catturato['cmd'][0]
        i = cmd.index('-N')
        assert cmd[i + 3] == progetto['out']
        assert cmd[i + 4] == '48000'
        assert cmd[i + 5] == 'AIFF'


# =============================================================================
# STEMS
# =============================================================================

class TestPipelineStems:

    def test_uno_score_e_un_file_per_stream(self, progetto):
        result, catturato = _render(progetto, per_stream=True)
        assert len(result.audio_paths) == 2
        assert len(catturato['score']) == 2

    def test_ogni_stem_parte_da_zero(self, progetto):
        """Il secondo stream ha onset 1.0: nel proprio file deve partire da
        zero, come fanno gli altri due backend."""
        _, catturato = _render(progetto, per_stream=True)
        for score in catturato['score']:
            tempi = [t for t, _ in _messaggi(score, '/s_new')]
            assert min(tempi) < 0.2

    def test_i_grani_si_dividono_fra_gli_stem(self, progetto):
        _, catturato = _render(progetto, per_stream=True)
        _, mix = _render(progetto)
        divisi = sum(len(_messaggi(s, '/s_new')) for s in catturato['score'])
        assert divisi == len(_messaggi(mix['score'][0], '/s_new'))

    def test_naming_degli_stem(self, progetto):
        result, _ = _render(progetto, per_stream=True)
        assert [os.path.basename(p) for p in result.audio_paths] == [
            'out__s1.aif', 'out__s2.aif']


# =============================================================================
# PARITA' CON IL RENDERER NUMPY
# =============================================================================

class TestParitaConNumpy:
    """La lista dei grani e' identica per costruzione (stesso Generator,
    stesso seed). Cio' che si puo' confrontare senza scsynth e' che i due
    backend leggano quella lista allo stesso modo."""

    def _numpy_grains(self, progetto):
        generator = api.load_generator(progetto['yaml'],
                                       samples_dir=progetto['refs'])
        return [g for stream in generator.streams
                for voice in stream.voices for g in voice]

    def test_stesso_numero_di_grani(self, progetto):
        _, catturato = _render(progetto)
        assert len(_messaggi(catturato['score'][0], '/s_new')) == \
            len(self._numpy_grains(progetto))

    def test_stessi_onset(self, progetto):
        _, catturato = _render(progetto)
        score = sorted(t for t, _ in _messaggi(catturato['score'][0], '/s_new'))
        # Il timetag OSC ha 32 bit di frazione: ~2e-10 s di risoluzione,
        # tre ordini di grandezza sotto il campione.
        atteso = sorted(g.onset for g in self._numpy_grains(progetto))
        assert np.allclose(score, atteso, atol=1e-9)

    def test_stessa_ampiezza_lineare(self, progetto):
        """Il volume in dB diventa ampiezza nello score, non nel grafo:
        deve dare lo stesso numero di 10**(v/20) del GrainRenderer."""
        _, catturato = _render(progetto)
        ampiezze = sorted(
            dict(zip(args[4::2], args[5::2]))['amp']
            for _, args in _messaggi(catturato['score'][0], '/s_new'))
        attese = sorted(10.0 ** (g.volume / 20.0)
                        for g in self._numpy_grains(progetto))
        assert np.allclose(ampiezze, attese, rtol=1e-6)

    def test_stessa_finestra_per_gli_stessi_grani(self, progetto):
        """Il buffer di finestra di ogni grano e' il suo envelope_table,
        salvo la sostituzione sotto soglia (#225)."""
        from pge.rendering.numpy_window_registry import WINDOW_MIN_SHAPE_SAMPLES

        _, catturato = _render(progetto)
        grani = self._numpy_grains(progetto)
        assert all(round(g.duration * 48000) >= WINDOW_MIN_SHAPE_SAMPLES
                   for g in grani), "fixture senza grani sotto soglia"

        buffer_usati = {dict(zip(args[4::2], args[5::2]))['envBuf']
                        for _, args in _messaggi(catturato['score'][0], '/s_new')}
        assert buffer_usati == {g.envelope_table for g in grani}
