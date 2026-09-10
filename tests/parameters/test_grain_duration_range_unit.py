# tests/parameters/test_grain_duration_range_unit.py
"""
test_grain_duration_range_unit.py

La chiave YAML `grain.duration_range_unit` (issue #267), dallo schema fino al
Parameter costruito.

Catena: ParameterSpec.range_unit_path -> ParameterOrchestrator -> GranularParser
-> Parameter(range_relative=...).

Il meccanismo e' dichiarativo e generico (qualunque spec puo' dichiarare un
`range_unit_path`); oggi l'unico cablato e' `grain_duration`, che e' il
parametro per cui l'issue nasce — su volume, pan e pitch una banda relativa non
avrebbe lo stesso senso musicale, e resta assoluta finche' non la si chiede.
"""

import pytest

from pge.core.stream_config import StreamConfig, StreamContext
from pge.parameters.parameter_definitions import (
    RANGE_UNIT_RELATIVE,
    RELATIVE_RANGE_BOUNDS,
)
from pge.parameters.parameter_orchestrator import ParameterOrchestrator
from pge.parameters.parameter_schema import (
    STREAM_PARAMETER_SCHEMA,
    get_parameter_spec,
)
from pge.shared.exceptions import InvalidFieldValueError, MissingFieldError
from pge.shared.probability_gate import AlwaysGate


def _orchestrator():
    ctx = StreamContext(stream_id='s1', onset=0.0, duration=10.0,
                        sample='x.wav', sample_dur_sec=5.0)
    return ParameterOrchestrator(StreamConfig(context=ctx))


def _grain_duration(grain: dict):
    spec = get_parameter_spec('grain_duration')
    return _orchestrator().create_parameter_with_gate({'grain': grain}, spec)


class TestSchema:

    def test_grain_duration_dichiara_il_path_dell_unita(self):
        assert get_parameter_spec('grain_duration').range_unit_path == (
            'grain.duration_range_unit')

    def test_nessun_altro_parametro_lo_dichiara_oggi(self):
        con_unita = [s.name for s in STREAM_PARAMETER_SCHEMA if s.range_unit_path]

        assert con_unita == ['grain_duration']

    def test_uno_spec_senza_range_non_puo_avere_un_unita(self):
        """Un'unita' senza il range che governa non vuol dire niente."""
        for spec in STREAM_PARAMETER_SCHEMA:
            if spec.range_unit_path:
                assert spec.range_path, spec.name


class TestCablaggioDalloYaml:

    def test_senza_la_chiave_la_banda_resta_assoluta(self):
        p = _grain_duration({'duration': 0.5, 'duration_range': 0.5})
        p.set_probability_gate(AlwaysGate())

        draws = [p.get_value(0.0) for _ in range(300)]

        assert min(draws) >= 0.25 - 1e-9
        assert max(draws) <= 0.75 + 1e-9

    def test_con_relative_la_banda_e_una_frazione(self):
        p = _grain_duration({
            'duration': 0.5,
            'duration_range': 0.5,
            'duration_range_unit': RANGE_UNIT_RELATIVE,
        })
        p.set_probability_gate(AlwaysGate())

        draws = [p.get_value(0.0) for _ in range(300)]

        # banda = 0.5 * 0.5 = 0.25 centrata su 0.5
        assert min(draws) >= 0.375 - 1e-9
        assert max(draws) <= 0.625 + 1e-9

    def test_absolute_esplicito_e_il_comportamento_storico(self):
        p = _grain_duration({
            'duration': 0.5,
            'duration_range': 0.5,
            'duration_range_unit': 'absolute',
        })
        p.set_probability_gate(AlwaysGate())

        assert max(p.get_value(0.0) for _ in range(300)) <= 0.75 + 1e-9

    def test_una_grafia_ignota_nomina_la_chiave_per_esteso(self):
        with pytest.raises(InvalidFieldValueError) as exc:
            _grain_duration({
                'duration': 0.5,
                'duration_range': 0.5,
                'duration_range_unit': 'percentuale',
            })

        assert 'grain.duration_range_unit' in str(exc.value)
        assert exc.value.stream_id == 's1'


class TestUnitaSenzaRange:
    """`duration_range_unit: relative` senza `duration_range` e' la stessa
    trappola di `duration_unit: samples` senza `duration`: chi la scrive crede
    di aver attivato la banda relativa e invece prende il jitter implicito, che
    e' assoluto (0.01 s) — cioe' esattamente la patologia dell'issue sui grani
    da un campione. Meglio dirlo una volta, prima di renderizzare."""

    def test_relative_pretende_il_range(self):
        with pytest.raises(MissingFieldError) as exc:
            _grain_duration({'duration': 0.5,
                             'duration_range_unit': RANGE_UNIT_RELATIVE})

        assert 'grain.duration_range' in str(exc.value)
        assert exc.value.stream_id == 's1'

    def test_un_range_a_zero_e_una_dichiarazione(self):
        """Zero e' una banda degenere ma dichiarata: nessun errore."""
        p = _grain_duration({'duration': 0.5, 'duration_range': 0,
                             'duration_range_unit': RANGE_UNIT_RELATIVE})

        assert p.has_explicit_range is True

    def test_absolute_senza_range_non_pretende_niente(self):
        """`absolute` e' il default: dichiararlo non cambia nulla."""
        p = _grain_duration({'duration': 0.5, 'duration_range_unit': 'absolute'})

        assert p.has_explicit_range is False


class TestDominio:

    def test_la_frazione_e_validata_contro_il_dominio_relativo(self):
        from pge.shared.exceptions import ParameterBoundError

        oltre = RELATIVE_RANGE_BOUNDS[1] + 0.5
        with pytest.raises(ParameterBoundError):
            _grain_duration({'duration': 0.5, 'duration_range': oltre,
                             'duration_range_unit': RANGE_UNIT_RELATIVE})
