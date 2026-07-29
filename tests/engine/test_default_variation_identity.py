# tests/engine/test_default_variation_identity.py
"""
test_default_variation_identity.py

Golden test dell'identita' bit-per-bit della variazione di default.

`range_anchor` (issue range-anchor-mode) introduce una lettura alternativa dei
`_range`: `base` diventa il minimo della banda invece del centro. Il default
resta `center`, e il contratto e' che con il default NIENTE cambia — non "quasi
niente", non "statisticamente equivalente": gli stessi identici float.

Il test congela i grani prodotti da uno YAML che esercita tutti i `_range` che
passano da `Parameter` (volume, pan, grain.duration, pointer.offset_range,
pitch.range) piu' il jitter implicito sotto dephase, con `distribution_mode:
uniform` e seed fisso. Il digest e' stato calcolato PRIMA dell'introduzione di
`range_anchor` ed e' il riferimento immutabile.

Nota di scope: il golden copre `uniform`, non `gaussian`. La gaussiana cambia
semantica per decisione esplicita (`range` diventa la larghezza della banda
invece della sigma), quindi un golden sulla gaussiana sarebbe un golden su un
comportamento che stiamo deliberatamente sostituendo. La copertura della nuova
gaussiana sta in tests/shared/test_distribution_strategy.py.

Non richiede csound/sox ne' sample reali: la durata del sample e' mockata e i
grani si confrontano simbolicamente.
"""

import hashlib
import json

import pytest
import yaml
from unittest.mock import patch

from pge.engine.generator import Generator


# =============================================================================
# YAML DI RIFERIMENTO
# =============================================================================

def _golden_yaml():
    """YAML che esercita ogni `_range` che passa da Parameter.

    - stream `explicit`: tutti i range dichiarati esplicitamente, dephase off
      (con `range_always_active` i range espliciti valgono al 100% dei grani).
    - stream `implicit`: nessun range dichiarato + dephase attivo, cioe' il
      path del jitter implicito (`ParameterBounds.default_jitter`) e del detune
      implicito EDO.
    """
    return {
        'seed': 20260729,
        'streams': [
            {
                'stream_id': 'explicit',
                'onset': 0.0,
                'duration': 4.0,
                'sample': 'test.wav',
                'density': 12,
                'distribution_mode': 'uniform',
                'range_always_active': True,
                'volume': -6.0,
                'volume_range': 8.0,
                'pan': 0.0,
                'pan_range': 90.0,
                'grain': {'duration': 0.05, 'duration_range': 0.02},
                'pointer': {'start': 1.0, 'offset_range': 0.3},
                'pitch': {'semitones': 3, 'range': 4},
            },
            {
                'stream_id': 'implicit',
                'onset': 0.0,
                'duration': 4.0,
                'sample': 'test.wav',
                'density': 12,
                'distribution_mode': 'uniform',
                'dephase': True,
                'volume': -6.0,
                'pan': 0.0,
                'grain': {'duration': 0.05},
                'pointer': {'start': 1.0},
                'pitch': {'semitones': 3},
            },
        ],
    }


def _materialize(tmp_path):
    """Materializza i grani dello YAML golden. Ritorna la lista dei campi."""
    cfg = tmp_path / "golden_variation.yml"
    cfg.write_text(yaml.safe_dump(_golden_yaml()))
    gen = Generator(str(cfg))
    gen.load_yaml()
    with patch('pge.core.stream.get_sample_duration', return_value=10.0):
        gen.create_elements()
        rows = [
            [
                s.stream_id,
                repr(g.onset), repr(g.duration), repr(g.pointer_pos),
                repr(g.pitch_ratio), repr(g.volume), repr(g.pan),
            ]
            for s in gen.streams for g in s.grains
        ]
    return rows


def _digest(rows):
    """SHA-256 stabile della materializzazione (repr float = esatto)."""
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True).encode('utf-8')
    ).hexdigest()


# Digest congelato sul comportamento PRE range_anchor.
# Se questo test diventa rosso, il default e' cambiato: e' un bug, non un
# aggiornamento da fare al valore atteso.
GOLDEN_DIGEST = "727d4c843e3a900724e5bf0021b5e186ca8e89082d754556c5bbfcc0f923473a"

GOLDEN_GRAIN_COUNT = 96


class TestDefaultVariationIdentity:
    """Il default `range_anchor: center` non cambia un solo float."""

    def test_golden_digest_unchanged(self, tmp_path):
        """La materializzazione dei grani e' identica al riferimento."""
        rows = _materialize(tmp_path)

        assert _digest(rows) == GOLDEN_DIGEST, (
            "Il comportamento di default e' cambiato. Il golden congela la "
            "variazione stocastica con distribution_mode=uniform e "
            "range_anchor=center (default): nessuna modifica deve alterarlo."
        )

    def test_golden_is_not_empty(self, tmp_path):
        """Guardia: il golden deve esercitare grani veri, non una lista vuota."""
        rows = _materialize(tmp_path)

        assert len(rows) == GOLDEN_GRAIN_COUNT
        assert GOLDEN_GRAIN_COUNT > 0

    def test_materialization_is_deterministic(self, tmp_path):
        """Due materializzazioni dello stesso YAML seedato coincidono."""
        assert _materialize(tmp_path) == _materialize(tmp_path)
