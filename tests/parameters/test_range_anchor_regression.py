"""
test_range_anchor_regression.py

Prova che il default `range_anchor: center` non ha spostato un bit.

I valori attesi in `tests/fixtures/range_anchor_center_golden.json` sono stati
generati eseguendo lo stesso percorso di codice sul commit 9ce7976, cioe' PRIMA
che `range_anchor` esistesse. Non sono un'istantanea del comportamento
corrente: sono il comportamento storico, e il test fallisce se il refactoring
lo tocca — anche di un ulp.

Il percorso coperto e' quello modificato (YAML → GranularParser → Parameter →
DistributionStrategy) su tutte le forme che il cablaggio attraversa:

- range esplicito scalare, uniform e gaussian;
- range esplicito come Envelope;
- jitter implicito (nessun range dichiarato);
- valori che finiscono nel safety clamp.

Tutto cio' che sta a monte (Stream, controller, renderer) non e' stato toccato:
se questi valori coincidono, i grani coincidono e quindi l'audio coincide.
"""

import json
from pathlib import Path

import pytest

from pge.core.stream_config import StreamConfig, StreamContext
from pge.parameters.parser import GranularParser
from pge.shared.distribution_strategy import ANCHOR_CENTER
from pge.shared.probability_gate import AlwaysGate

GOLDEN_PATH = (
    Path(__file__).resolve().parents[1] / 'fixtures'
    / 'range_anchor_center_golden.json'
)

# Stesse costanti dello script che ha generato il golden su 9ce7976.
GOLDEN_SEED = 20260729
GOLDEN_SAMPLES = 40

CASES = {
    'volume': ('volume', -6.0, 12.0),
    'pan': ('pan', 0.0, 1.5),
    'grain_duration': ('grain_duration', 0.05, 0.04),
    'pan_env_range': ('pan', 0.0, [[0.0, 5.0], [8.0, 25.0]]),
    'volume_jitter': ('volume', -6.0, None),
    'grain_duration_jitter': ('grain_duration', 0.05, None),
}


@pytest.fixture(scope='module')
def golden():
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def _series(distribution, case, anchor=ANCHOR_CENTER):
    """Rigenera una serie di valori come lo script del golden."""
    context = StreamContext(
        stream_id='golden_stream', onset=0.0, duration=8.0,
        sample='golden.wav', sample_dur_sec=4.0,
    )
    config = StreamConfig.from_yaml(
        {'distribution_mode': distribution,
         'time_mode': 'absolute',
         'range_anchor': anchor},
        context, seed=GOLDEN_SEED,
    )
    name, value, range_spec = CASES[case]
    param = GranularParser(config).parse_parameter(name, value, range_spec)
    param.set_probability_gate(AlwaysGate())

    return [param.get_value(t / 40.0) for t in range(GOLDEN_SAMPLES)]


class TestDefaultIsBitIdenticalToPreFeatureEngine:
    """Il default riproduce il motore pre-feature, valore per valore."""

    @pytest.mark.parametrize('distribution', ['uniform', 'gaussian'])
    @pytest.mark.parametrize('case', sorted(CASES))
    def test_series_matches_golden(self, golden, distribution, case):
        expected = golden[f'{distribution}/{case}']
        got = _series(distribution, case)

        assert got == expected, (
            f"il default ha cambiato {distribution}/{case}: "
            f"il rendering non e' piu' identico al motore pre-range_anchor"
        )

    def test_golden_covers_every_case(self, golden):
        """Il golden non deve perdere serie per strada."""
        expected_keys = {
            f'{dist}/{case}'
            for dist in ('uniform', 'gaussian')
            for case in CASES
        }

        assert set(golden) == expected_keys

    def test_absent_key_behaves_like_explicit_center(self, golden):
        """Uno YAML che non nomina range_anchor e' identico a uno che
        dichiara 'center': e' il caso di ogni config gia' scritta."""
        context = StreamContext(
            stream_id='golden_stream', onset=0.0, duration=8.0,
            sample='golden.wav', sample_dur_sec=4.0,
        )
        config = StreamConfig.from_yaml(
            {'distribution_mode': 'uniform', 'time_mode': 'absolute'},
            context, seed=GOLDEN_SEED,
        )
        param = GranularParser(config).parse_parameter('volume', -6.0, 12.0)
        param.set_probability_gate(AlwaysGate())
        got = [param.get_value(t / 40.0) for t in range(GOLDEN_SAMPLES)]

        assert got == golden['uniform/volume']


class TestMinModeActuallyDiffers:
    """Contro-prova: il golden non passa per inerzia.

    Se la modalita' 'min' producesse gli stessi valori del default, i test
    sopra sarebbero verdi anche con la feature rotta.
    """

    def test_min_mode_diverges_from_golden(self, golden):
        got = _series('uniform', 'volume', anchor='min')

        assert got != golden['uniform/volume']

    def test_min_mode_shifts_band_upward(self, golden):
        """Lo scarto e' esattamente range/2 (volume_range = 12)."""
        centered = golden['uniform/volume']
        anchored = _series('uniform', 'volume', anchor='min')

        for got, expected in zip(anchored, centered):
            assert got == pytest.approx(expected + 6.0)
