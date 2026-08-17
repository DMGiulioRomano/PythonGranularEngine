# =============================================================================
# tests/parameters/test_gate_factory_errors.py
# =============================================================================
"""
Issue #38, PR2 — GateFactory solleva InvalidParameterError per deviation_probability
malformato (tipo non supportato o valore non parsabile).

Issue #209 — anche l'envelope che non si costruisce e' un errore: il ramo
envelope non torna piu' `AlwaysGate` con un log, e i due percorsi che portano
a costruirlo rispondono uguale.
"""
import logging

import pytest

from pge.parameters.gate_factory import GateFactory
from pge.shared.exceptions import (
    ConfigError,
    InvalidFieldValueError,
    InvalidParameterError,
)


def test_classify_deviation_probability_invalid_type_raises_invalid_parameter_error():
    """deviation_probability di tipo non supportato → InvalidParameterError."""
    with pytest.raises(InvalidParameterError) as exc_info:
        GateFactory._classify_deviation_probability(object())

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert "deviation_probability" in err.param_name


def _create_gate(raw_value):
    """Il gate per una chiave del dict per-parametro, come lo crea lo Stream."""
    return GateFactory.create_gate(
        deviation_probability={'volume': raw_value},
        param_key='volume',
        default_prob=1.0,
        has_explicit_range=False,
        duration=1.0,
        time_mode='absolute',
    )


@pytest.mark.parametrize("raw_value", [
    # Supera `_is_envelope_like`: prima di #209 arrivava a
    # `create_scaled_envelope` senza rete e ne risaliva il ValueError nudo.
    {'points': []},
    {'type': 'linear', 'points': []},
    # Non lo supera: prima di #209 finiva nel ramo con `except Exception`,
    # che tornava AlwaysGate e loggava. Piu' l'errore era grossolano, meno il
    # sistema lo segnalava.
    [],
    ['x'],
    {'punti': [[0, 50]]},
])
def test_envelope_malformato_alza_invalid_field_value_error(raw_value):
    """I due percorsi verso l'envelope rispondono uguale (issue #209).

    La forma dell'errore non dipende piu' da quanto il corpo somigliasse a un
    envelope: stessa classe, stesso campo, in entrambi i casi dentro la
    gerarchia `EngineError` — cioe' attribuibile allo stream da chi la
    intercetta risalendo.
    """
    with pytest.raises(InvalidFieldValueError) as exc_info:
        _create_gate(raw_value)

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert err.field == 'deviation_probability.volume'
    assert err.value == raw_value
    assert err.hint


def test_envelope_malformato_non_e_piu_un_fallback_da_loggare(caplog):
    """Il `logger.error` sparisce: non c'e' piu' nessun fallback da tracciare.

    Il log serviva a rendere visibile una scelta presa in silenzio. Ora la
    scelta non c'e' — il valore non viene interpretato in un altro modo, viene
    rifiutato — e un log di errore accanto a un'eccezione dice la stessa cosa
    due volte.
    """
    with caplog.at_level(logging.ERROR):
        with pytest.raises(InvalidFieldValueError):
            _create_gate([])

    assert not [
        r for r in caplog.records
        if 'deviation_probability' in r.getMessage()
    ]


def test_envelope_globale_malformato_alza_lo_stesso_errore():
    """Anche l'envelope globale, non solo quello per-chiave (issue #209).

    `deviation_probability: {points: []}` e' envelope-like, quindi finiva
    nell'unico altro punto del file che costruiva senza rete: stesso ValueError
    nudo, fuori dalla gerarchia. Restava l'ultima delle asimmetrie.
    """
    with pytest.raises(InvalidFieldValueError) as exc_info:
        GateFactory.create_gate(
            deviation_probability={'points': []},
            param_key='volume',
            default_prob=1.0,
            has_explicit_range=False,
            duration=1.0,
            time_mode='absolute',
        )

    assert exc_info.value.field == 'deviation_probability'


def test_parse_raw_value_invalid_type_raises_invalid_parameter_error():
    """Valore deviation_probability per chiave specifica con tipo invalido → InvalidParameterError."""
    with pytest.raises(InvalidParameterError) as exc_info:
        GateFactory._parse_raw_value(object(), duration=1.0, time_mode='absolute')

    err = exc_info.value
    assert isinstance(err, ConfigError)
    assert "deviation_probability" in err.param_name
