# tests/engine/test_seed_component_isolation.py
"""
test_seed_component_isolation.py

Test dell'isolamento per-componente del random dei grani (issue #154).

Il meccanismo 2 dell'issue #81 (random.seed globale) rendeva il valore di ogni
grano dipendente dalla posizione del suo draw nella sequenza globale: solo/mute
e la materializzazione lazy (cache stems) cambiavano i grani degli stream
superstiti anche a seed fissato. Qui si verifica il modello per-componente:

- INVARIANZA SOLO/MUTE: con seed fissato, i grani di uno stream sono identici
  fra render completo, render in solo e render con altri stream muted.
- INVARIANZA D'ORDINE (lazy/cache): l'ordine di materializzazione dei grani
  non cambia i valori (gli stream cache-clean non consumano draw altrui).
- INIEZIONE RNG: DistributionStrategy, ProbabilityGate, window strategy,
  DensityController e detune implicito accettano un RNG locale iniettato.
- SESSION SEED: senza `seed:` nello YAML il Generator genera un seed di
  sessione, lo logga, e il run resta ricostruibile a posteriori.

Non richiede csound/sox né sample reali (get_sample_duration mockato).
"""

import random

import pytest
import yaml
from unittest.mock import patch

from pge.engine.generator import Generator
from pge.core.stream_config import StreamConfig, StreamContext
from pge.shared.distribution_strategy import DistributionFactory
from pge.shared.probability_gate import AlwaysGate, RandomGate, EnvelopeGate
from pge.controllers.density_controller import DensityController
from pge.controllers.window_selection_strategy import (
    RandomWindowStrategy,
    TransitionWindowStrategy,
    MultiStateWindowStrategy,
)
from pge.envelopes.envelope import Envelope
from pge.parameters.parser import GranularParser


# =============================================================================
# HELPERS
# =============================================================================

def _stream_dict(stream_id, mark=None):
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
    if mark is not None:
        d[mark] = None  # 'solo:' / 'mute:' — chiave presente, valore vuoto
    return d


def _yaml_data(streams, seed=42):
    data = {'streams': streams}
    if seed is not None:
        data['seed'] = seed
    return data


def _render_streams(tmp_path, yaml_data, filename='iso.yml'):
    """Crea il Generator e materializza i grani nell'ordine degli stream."""
    cfg = tmp_path / filename
    cfg.write_text(yaml.safe_dump(yaml_data))
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
# 1. INVARIANZA SOLO/MUTE (fix del punto 1 dell'issue #154)
# =============================================================================

class TestSoloMuteInvariance:

    def test_solo_does_not_change_surviving_stream(self, tmp_path):
        """Con seed fissato, mettere s2 in solo NON cambia i suoi grani
        rispetto al render completo."""
        full = _render_streams(
            tmp_path, _yaml_data([_stream_dict('s1'), _stream_dict('s2')])
        )
        solo = _render_streams(
            tmp_path,
            _yaml_data([_stream_dict('s1'), _stream_dict('s2', mark='solo')]),
        )
        sig_full = _signature_of(full, 's2')
        sig_solo = _signature_of(solo, 's2')
        assert len(sig_full) > 10
        assert sig_full == sig_solo

    def test_mute_does_not_change_surviving_stream(self, tmp_path):
        """Con seed fissato, mutare s1 NON cambia i grani di s2."""
        full = _render_streams(
            tmp_path, _yaml_data([_stream_dict('s1'), _stream_dict('s2')])
        )
        muted = _render_streams(
            tmp_path,
            _yaml_data([_stream_dict('s1', mark='mute'), _stream_dict('s2')]),
        )
        assert _signature_of(full, 's2') == _signature_of(muted, 's2')

    def test_adding_stream_does_not_change_existing_one(self, tmp_path):
        """Aggiungere uno stream allo YAML non altera i grani degli altri
        (robustezza compositiva: i componenti non condividono draw)."""
        only_s2 = _render_streams(tmp_path, _yaml_data([_stream_dict('s2')]))
        both = _render_streams(
            tmp_path, _yaml_data([_stream_dict('s1'), _stream_dict('s2')])
        )
        assert _signature_of(only_s2, 's2') == _signature_of(both, 's2')


# =============================================================================
# 2. INVARIANZA D'ORDINE DI MATERIALIZZAZIONE (fix del punto 2 — cache stems)
# =============================================================================

class TestLazyOrderInvariance:

    def test_materialization_order_is_irrelevant(self, tmp_path):
        """I grani non dipendono dall'ordine di lettura di .grains: uno
        stream cache-clean saltato non shifta i draw degli stream dirty."""
        data = _yaml_data([_stream_dict('s1'), _stream_dict('s2')])

        cfg = tmp_path / 'order_a.yml'
        cfg.write_text(yaml.safe_dump(data))
        gen_a = Generator(str(cfg))
        gen_a.load_yaml()
        with patch('pge.core.stream.get_sample_duration', return_value=10.0):
            gen_a.create_elements()
            _ = gen_a.streams[0].grains  # s1 prima
            _ = gen_a.streams[1].grains

        cfg_b = tmp_path / 'order_b.yml'
        cfg_b.write_text(yaml.safe_dump(data))
        gen_b = Generator(str(cfg_b))
        gen_b.load_yaml()
        with patch('pge.core.stream.get_sample_duration', return_value=10.0):
            gen_b.create_elements()
            _ = gen_b.streams[1].grains  # s2 prima (come con s1 cache-clean)
            _ = gen_b.streams[0].grains

        assert _signature_of(gen_a, 's2') == _signature_of(gen_b, 's2')
        assert _signature_of(gen_a, 's1') == _signature_of(gen_b, 's1')


# =============================================================================
# 3. INIEZIONE RNG NEI COMPONENTI
# =============================================================================

class TestDistributionRngInjection:

    def test_uniform_deterministic_with_injected_rng(self):
        d1 = DistributionFactory.create('uniform', rng=random.Random(7))
        d2 = DistributionFactory.create('uniform', rng=random.Random(7))
        assert [d1.sample(1.0, 0.5) for _ in range(20)] == \
               [d2.sample(1.0, 0.5) for _ in range(20)]

    def test_gaussian_deterministic_with_injected_rng(self):
        d1 = DistributionFactory.create('gaussian', rng=random.Random(7))
        d2 = DistributionFactory.create('gaussian', rng=random.Random(7))
        assert [d1.sample(0.0, 1.0) for _ in range(20)] == \
               [d2.sample(0.0, 1.0) for _ in range(20)]

    def test_injected_rngs_are_isolated(self):
        """Consumare draw da una strategy non shifta l'altra."""
        d1 = DistributionFactory.create('uniform', rng=random.Random(7))
        d2 = DistributionFactory.create('uniform', rng=random.Random(7))
        _ = [d1.sample(0.0, 1.0) for _ in range(50)]  # draw extra su d1
        d1_next = DistributionFactory.create('uniform', rng=random.Random(7))
        assert d2.sample(0.0, 1.0) == d1_next.sample(0.0, 1.0)


class TestGateRngInjection:

    def test_random_gate_deterministic_with_injected_rng(self):
        g1 = RandomGate(50.0, rng=random.Random(11))
        g2 = RandomGate(50.0, rng=random.Random(11))
        seq1 = [g1.should_apply(0.0) for _ in range(50)]
        seq2 = [g2.should_apply(0.0) for _ in range(50)]
        assert seq1 == seq2
        assert True in seq1 and False in seq1  # gate davvero stocastico

    def test_envelope_gate_deterministic_with_injected_rng(self):
        env = Envelope([[0, 50], [10, 50]])
        g1 = EnvelopeGate(env, rng=random.Random(11))
        g2 = EnvelopeGate(env, rng=random.Random(11))
        assert [g1.should_apply(5.0) for _ in range(50)] == \
               [g2.should_apply(5.0) for _ in range(50)]


class TestWindowStrategyRngInjection:

    def test_random_window_strategy_deterministic(self):
        s1 = RandomWindowStrategy(['a', 'b', 'c'], AlwaysGate(), rng=random.Random(3))
        s2 = RandomWindowStrategy(['a', 'b', 'c'], AlwaysGate(), rng=random.Random(3))
        assert [s1.select(0.0) for _ in range(50)] == \
               [s2.select(0.0) for _ in range(50)]

    def test_transition_window_strategy_deterministic(self):
        def make():
            return TransitionWindowStrategy(
                from_window='a', to_window='b',
                curve=Envelope([[0, 0], [10, 1]]),
                duration=10.0, rng=random.Random(3),
            )
        s1, s2 = make(), make()
        assert [s1.select(5.0) for _ in range(50)] == \
               [s2.select(5.0) for _ in range(50)]

    def test_multistate_window_strategy_deterministic(self):
        def make():
            return MultiStateWindowStrategy(
                states=[(0.0, 'a'), (0.5, 'b'), (1.0, 'c')],
                curve=Envelope([[0, 0], [10, 1]]),
                duration=10.0, rng=random.Random(3),
            )
        s1, s2 = make(), make()
        assert [s1.select(2.5) for _ in range(50)] == \
               [s2.select(2.5) for _ in range(50)]


class TestDensityControllerRng:

    def _make_config(self, seed):
        ctx = StreamContext(
            stream_id='s1', onset=0.0, duration=10.0,
            sample='test.wav', sample_dur_sec=10.0,
        )
        return StreamConfig(context=ctx, seed=seed)

    def test_async_iot_deterministic_with_config_seed(self):
        """Due controller identici con lo stesso config.seed producono la
        stessa sequenza di IOT async (componente 'iot' isolato)."""
        params = {'density': 20, 'distribution': 1.0}
        dc1 = DensityController(dict(params), self._make_config(seed=42))
        dc2 = DensityController(dict(params), self._make_config(seed=42))
        seq1 = [dc1.calculate_inter_onset(0.0, 0.05) for _ in range(50)]
        seq2 = [dc2.calculate_inter_onset(0.0, 0.05) for _ in range(50)]
        assert seq1 == seq2
        assert max(seq1) > min(seq1)  # davvero async

    def test_async_iot_differs_with_different_seed(self):
        params = {'density': 20, 'distribution': 1.0}
        dc1 = DensityController(dict(params), self._make_config(seed=1))
        dc2 = DensityController(dict(params), self._make_config(seed=2))
        seq1 = [dc1.calculate_inter_onset(0.0, 0.05) for _ in range(20)]
        seq2 = [dc2.calculate_inter_onset(0.0, 0.05) for _ in range(20)]
        assert seq1 != seq2


class TestImplicitDetuneRng:

    def test_detune_deterministic_with_injected_rng(self):
        """Il detune implicito EDO (issue #95) usa l'RNG iniettato."""
        from pge.strategies.strategie import UnitPitchStrategy
        from pge.parameters.pitch_unit import make_pitch_unit
        from pge.parameters.parameter import Parameter

        unit = make_pitch_unit({'edo': 12})

        def make_strategy(rng):
            param = Parameter(
                name='pitch_edo12', value=7.0, bounds=unit.value_bounds(),
                owner_id='s1',
            )
            param.set_probability_gate(AlwaysGate())
            return UnitPitchStrategy(param, unit, 'edo12', rng=rng)

        s1 = make_strategy(random.Random(9))
        s2 = make_strategy(random.Random(9))
        seq1 = [s1.calculate(0.0) for _ in range(30)]
        seq2 = [s2.calculate(0.0) for _ in range(30)]
        assert seq1 == seq2
        assert len(set(seq1)) > 1  # il detune varia davvero


class TestParameterComponentIsolation:

    def _make_config(self, seed):
        ctx = StreamContext(
            stream_id='s1', onset=0.0, duration=10.0,
            sample='test.wav', sample_dur_sec=10.0,
        )
        return StreamConfig(context=ctx, seed=seed)

    def test_same_parameter_same_sequence(self):
        """Due Parameter identici (stesso stream, stesso nome, stesso seed)
        producono la stessa sequenza di valori: testabilità in isolamento
        con i numeri reali del render (punto 4 dell'issue)."""
        cfg = self._make_config(seed=42)
        parser = GranularParser(cfg)

        def make_param():
            p = parser.parse_parameter('grain_duration', 0.05, range_raw=0.03)
            p.set_probability_gate(AlwaysGate())
            return p

        p1, p2 = make_param(), make_param()
        seq1 = [p1.get_value(0.1 * i) for i in range(30)]
        seq2 = [p2.get_value(0.1 * i) for i in range(30)]
        assert seq1 == seq2
        assert len(set(seq1)) > 1

    def test_parameters_do_not_share_draws(self):
        """I draw di un parametro non shiftano quelli di un altro."""
        cfg = self._make_config(seed=42)

        parser_a = GranularParser(cfg)
        vol_a = parser_a.parse_parameter('volume', 0.0, range_raw=6.0)
        vol_a.set_probability_gate(AlwaysGate())
        seq_isolated = [vol_a.get_value(0.1 * i) for i in range(20)]

        parser_b = GranularParser(cfg)
        vol_b = parser_b.parse_parameter('volume', 0.0, range_raw=6.0)
        vol_b.set_probability_gate(AlwaysGate())
        pan_b = parser_b.parse_parameter('pan', 0.0, range_raw=30.0)
        pan_b.set_probability_gate(AlwaysGate())
        seq_interleaved = []
        for i in range(20):
            seq_interleaved.append(vol_b.get_value(0.1 * i))
            _ = pan_b.get_value(0.1 * i)  # draw interleaved sull'altro componente

        assert seq_isolated == seq_interleaved


# =============================================================================
# 4. SESSION SEED (seed assente → seed di sessione loggato)
# =============================================================================

class TestSessionSeedGenerator:

    def _make_generator(self, tmp_path, yaml_data, filename='session.yml'):
        cfg = tmp_path / filename
        cfg.write_text(yaml.safe_dump(yaml_data))
        gen = Generator(str(cfg))
        gen.load_yaml()
        return gen

    def test_no_seed_generates_session_seed(self, tmp_path, capsys):
        """Senza `seed:` il Generator genera un seed di sessione e lo logga."""
        gen = self._make_generator(tmp_path, _yaml_data([_stream_dict('s1')], seed=None))
        with patch('pge.core.stream.get_sample_duration', return_value=10.0):
            gen.create_elements()
        assert isinstance(gen.seed, int)
        assert gen.seed_is_session is True
        out = capsys.readouterr().out
        assert '[SEED]' in out
        assert str(gen.seed) in out

    def test_explicit_seed_is_not_session(self, tmp_path, capsys):
        """Con `seed:` esplicito nessun session seed viene generato."""
        gen = self._make_generator(tmp_path, _yaml_data([_stream_dict('s1')], seed=42))
        with patch('pge.core.stream.get_sample_duration', return_value=10.0):
            gen.create_elements()
        assert gen.seed == 42
        assert gen.seed_is_session is False
        assert '[SEED]' not in capsys.readouterr().out

    def test_session_run_is_reconstructable(self, tmp_path):
        """Un run senza seed è riproducibile aggiungendo allo YAML il session
        seed loggato (`ogni run resta ricostruibile a posteriori`)."""
        gen1 = self._make_generator(
            tmp_path, _yaml_data([_stream_dict('s1')], seed=None), 'run1.yml'
        )
        with patch('pge.core.stream.get_sample_duration', return_value=10.0):
            gen1.create_elements()
            sig1 = _signature_of(gen1, 's1')

        gen2 = self._make_generator(
            tmp_path, _yaml_data([_stream_dict('s1')], seed=gen1.seed), 'run2.yml'
        )
        with patch('pge.core.stream.get_sample_duration', return_value=10.0):
            gen2.create_elements()
            sig2 = _signature_of(gen2, 's1')

        assert sig1 == sig2
