# tests/engine/test_rng_group.py
"""
test_rng_group.py

Test della condivisione della sequenza RNG fra stream (issue #169).

`rng_group` è una chiave YAML per-stream opzionale che sostituisce lo
`stream_id` come identità nella derivazione degli RNG locali
(shared/seeding.py): due stream con lo stesso `rng_group` — e stessi
parametri stocastici — pescano le stesse sequenze pseudo-casuali su tutti
i componenti (iot, variazioni `_range`, gate, window, detune) e sulle
voice strategy stocastiche.

Garanzie verificate:

- CONDIVISIONE: stesso `rng_group` + stessi parametri → grani identici
  fra stream con `stream_id` diversi (era impossibile prima di #169).
- ISOLAMENTO DI DEFAULT: senza `rng_group` il comportamento resta quello
  dell'issue #154 — stream diversi, sequenze diverse.
- RETROCOMPATIBILITÀ: aggiungere `rng_group: <stesso stream_id>` o non
  aggiungerlo affatto produce grani bit-per-bit identici (l'identità di
  derivazione non cambia).
- VOICE STRATEGY: le voci stocastiche condividono i draw dentro il gruppo.

Non richiede csound/sox né sample reali (get_sample_duration mockato).
"""

import yaml
from unittest.mock import patch

from pge.engine.generator import Generator


# =============================================================================
# HELPERS (stesso schema di test_seed_component_isolation.py)
# =============================================================================

def _stream_dict(stream_id, rng_group=None, voices=False):
    """Stream con più componenti stocastici attivi (iot, range, window, pitch)."""
    d = {
        'stream_id': stream_id,
        'onset': 0.0,
        'duration': 4.0,
        'sample': 'test.wav',
        'density': 30,
        'distribution': 1.0,
        'volume': -6.0,
        'volume_range': 4.0,
        'grain': {
            'duration': 0.05,
            'duration_range': 0.03,
            'envelope': ['hanning', 'expodec'],
        },
        'pitch': {'semitones': 0, 'range': 2},
    }
    if rng_group is not None:
        d['rng_group'] = rng_group
    if voices:
        d['voices'] = {
            'pitch': {'strategy': 'stochastic', 'pitch_range': 3.0},
            'pan': {'strategy': 'stochastic', 'spread': 60.0},
        }
    return d


def _render_streams(tmp_path, streams, seed=42, filename='rng_group.yml'):
    data = {'streams': streams, 'seed': seed}
    cfg = tmp_path / filename
    cfg.write_text(yaml.safe_dump(data))
    gen = Generator(str(cfg))
    gen.load_yaml()
    with patch('pge.core.stream.get_sample_duration', return_value=10.0):
        gen.create_elements()
        for s in gen.streams:
            _ = s.grains  # materializza (lazy)
    return gen


def _grain_signature(stream):
    """Firma simbolica dei grani, indipendente dalla numerazione ftable."""
    inv_windows = {v: k for k, v in stream.window_table_map.items()}
    return [
        (
            round(g.onset, 9),
            round(g.duration, 9),
            round(g.pointer_pos, 9),
            round(g.pitch_ratio, 9),
            round(g.volume, 9),
            round(g.pan, 9),
            inv_windows[g.envelope_table],
        )
        for g in stream.grains
    ]


def _signature_of(gen, stream_id):
    for s in gen.streams:
        if s.stream_id == stream_id:
            return _grain_signature(s)
    raise AssertionError(f"stream {stream_id} non trovato")


# =============================================================================
# 1. CONDIVISIONE — stesso rng_group → stessa sequenza
# =============================================================================

class TestSharedSequence:

    def test_same_rng_group_same_grains(self, tmp_path):
        """Due stream identici nei parametri ma con stream_id diversi:
        con lo stesso rng_group i grani coincidono."""
        gen = _render_streams(tmp_path, [
            _stream_dict('cugini_1', rng_group='cugini'),
            _stream_dict('cugini_2', rng_group='cugini'),
        ])
        sig1 = _signature_of(gen, 'cugini_1')
        sig2 = _signature_of(gen, 'cugini_2')
        assert len(sig1) > 10
        assert sig1 == sig2

    def test_same_rng_group_shared_voice_draws(self, tmp_path):
        """Le voice strategy stocastiche condividono i draw nel gruppo."""
        gen = _render_streams(tmp_path, [
            _stream_dict('cugini_1', rng_group='cugini', voices=True),
            _stream_dict('cugini_2', rng_group='cugini', voices=True),
        ])
        assert _signature_of(gen, 'cugini_1') == _signature_of(gen, 'cugini_2')

    def test_different_rng_group_different_grains(self, tmp_path):
        """Gruppi diversi → sequenze indipendenti."""
        gen = _render_streams(tmp_path, [
            _stream_dict('s1', rng_group='gruppo_a'),
            _stream_dict('s2', rng_group='gruppo_b'),
        ])
        assert _signature_of(gen, 's1') != _signature_of(gen, 's2')


# =============================================================================
# 2. ISOLAMENTO DI DEFAULT — senza rng_group nulla cambia
# =============================================================================

class TestDefaultIsolation:

    def test_without_rng_group_streams_stay_isolated(self, tmp_path):
        """Senza rng_group due stream a parametri identici restano
        indipendenti (contratto issue #154)."""
        gen = _render_streams(tmp_path, [
            _stream_dict('s1'),
            _stream_dict('s2'),
        ])
        assert _signature_of(gen, 's1') != _signature_of(gen, 's2')


# =============================================================================
# 3. RETROCOMPATIBILITÀ — default None → hash identico a prima
# =============================================================================

class TestBackwardCompatibility:

    def test_rng_group_equal_to_stream_id_is_identity(self, tmp_path):
        """rng_group uguale allo stream_id → grani bit-per-bit identici al
        render senza rng_group: l'identità di derivazione è la stessa."""
        plain = _render_streams(tmp_path, [_stream_dict('s1')])
        grouped = _render_streams(
            tmp_path, [_stream_dict('s1', rng_group='s1')],
            filename='rng_group_b.yml',
        )
        assert _signature_of(plain, 's1') == _signature_of(grouped, 's1')

    def test_rng_group_on_one_stream_does_not_move_others(self, tmp_path):
        """Aggiungere rng_group a uno stream non sposta i draw degli altri
        (l'isolamento per-componente di #154 resta intatto)."""
        before = _render_streams(tmp_path, [
            _stream_dict('s1'),
            _stream_dict('s2'),
        ])
        after = _render_streams(tmp_path, [
            _stream_dict('s1', rng_group='cugini'),
            _stream_dict('s2'),
        ], filename='rng_group_c.yml')
        assert _signature_of(before, 's2') == _signature_of(after, 's2')
