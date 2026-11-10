# tests/controllers/test_voices_controller.py
"""
Il controller del blocco YAML `voices:` (issue #284).

Lo `Stream` gli passa il sotto-blocco e la config, come a `PointerController`
il blocco `pointer:`: questi test lo costruiscono allo stesso modo, senza uno
`Stream` intorno. Il comportamento del blocco — strategy, unita', chiavi di
blocco, envelope nei kwarg — lo pinna la suite di #186
(`tests/core/test_stream_voices_yaml.py`), che passa dallo YAML di uno
`Stream` vero; qui si guarda il confine: il controller si costruisce con
`(blocco, config)` e da `config` legge tutto quel che prima leggeva dallo
`Stream` — `duration`, `seed`, `stream_id`.
"""

import pytest

from pge.controllers.voices_controller import VoicesController
from pge.core.stream_config import StreamConfig, StreamContext


def _config(stream_id='s1', duration=10.0, time_mode='absolute', seed=None,
            rng_group=None):
    context = StreamContext(
        stream_id=stream_id,
        onset=0.0,
        duration=duration,
        sample='x.wav',
        sample_dur_sec=5.0,
        rng_group=rng_group,
    )
    return StreamConfig(context=context, time_mode=time_mode, seed=seed)


class TestSenzaBlocco:

    @pytest.mark.parametrize('blocco', [{}, None], ids=['vuoto', 'null'])
    def test_una_voce_senza_dispersione_e_pointer_in_secondi(self, blocco):
        """Senza blocco i default di sempre: una voce, scatter 0, offset di
        pointer in secondi. `voices:` lasciato vuoto nello YAML arriva come
        None, e vale come assente."""
        c = VoicesController(blocco, _config())

        assert c.voice_manager.max_voices == 1
        assert c.num_voices.get_value(0.0) == pytest.approx(1.0)
        assert c.scatter.get_value(0.0) == pytest.approx(0.0)
        assert c.pointer_normalized is False


class TestTuttoDallaConfig:
    """I tre valori che il wiring leggeva dallo `Stream` stanno in `config`.

    Lo `Stream` qui non c'e': se il controller li cercasse ancora altrove, questi
    test non si costruirebbero. Ognuno porta un valore che nessun default puo'
    indovinare, cosi' un ripiego su `'unknown'`, su `None` o sulla durata di un
    altro stream si vede."""

    @pytest.mark.parametrize('blocco,campo', [
        ({'pitch': {'strategy': 'range', 'semitone_range': 12.0}},
         'voices.pitch.semitone_range'),
        ({'pitch': {'strategy': 'chord', 'chord': 'maj', 'unit': 'cents'}},
         'voices.pitch.unit'),
        ({'pointer': {'strategy': 'linear', 'step': 0.1, 'normalized': 'si'}},
         'voices.pointer.normalized'),
        ({'pan': {'strategy': 'step', 'step': [1, 2]}}, 'voices.pan.step'),
    ], ids=['semitone_range', 'unit', 'normalized', 'kwarg-non-envelope'])
    def test_gli_errori_nominano_lo_stream_della_config(self, blocco, campo):
        from pge.shared.exceptions import ConfigError
        with pytest.raises(ConfigError) as ei:
            VoicesController({'num_voices': 2, **blocco},
                             _config(stream_id='dalla_config'))
        assert ei.value.field == campo
        assert ei.value.stream_id == 'dalla_config'

    def test_le_stocastiche_ricevono_seed_e_rng_id_della_config(self):
        blocco = {
            'num_voices': 3,
            'pitch': {'strategy': 'stochastic', 'pitch_range': 3.0},
            'onset_offset': {'strategy': 'stochastic', 'max_offset': 0.2},
            'pointer': {'strategy': 'stochastic', 'pointer_range': 0.1},
            'pan': {'strategy': 'stochastic', 'spread': 60.0},
        }
        vm = VoicesController(
            blocco, _config(stream_id='solista', rng_group='coro', seed=1441),
        ).voice_manager

        for strategia in (vm._pitch_strategy, vm._onset_strategy,
                          vm._pointer_strategy, vm._pan_strategy):
            assert strategia.stream_id == 'coro'
            assert strategia.seed == 1441

    def test_la_durata_della_config_scala_i_tempi_normalizzati(self):
        """Sotto `time_mode: normalized` la progressione degli accordi e gli
        envelope dei kwarg si scalano sulla durata dello stream: quella del
        contesto."""
        blocco = {
            'num_voices': 2,
            'pitch': {'strategy': 'chord_progression',
                      'progression': [[0.0, 'maj7'], [1.0, 'min7']]},
            'pointer': {'strategy': 'linear', 'step': [[0.0, 0.0], [1.0, 0.1]]},
        }
        vm = VoicesController(
            blocco, _config(duration=20.0, time_mode='normalized'),
        ).voice_manager

        assert vm._pitch_strategy._times == [0.0, 20.0]
        assert vm._pointer_strategy.step.breakpoints[-1][0] == pytest.approx(20.0)
