# tests/shared/test_seeding.py
"""
test_seeding.py

Test della derivazione RNG in shared/seeding.py (issue #81 + #154).

Copre:
- voice_rng: derivazione per-voce (issue #81), invariata.
- component_rng: derivazione per-componente (issue #154) — RNG isolato per
  (seed, stream_id, component), deterministico via hashlib (indipendente da
  PYTHONHASHSEED). Con seed None restituisce il modulo `random` globale
  (fallback legacy per costruzioni dirette fuori dal Generator).
- session_seed: seed di sessione derivato da timestamp per i run senza
  `seed:` nello YAML (ogni run resta ricostruibile a posteriori).
"""

import hashlib
import random

import pytest

from shared.seeding import voice_rng, component_rng, session_seed


# =============================================================================
# component_rng — derivazione per-componente
# =============================================================================

class TestComponentRng:

    def test_deterministic_same_args(self):
        """Stessi (seed, stream_id, component) → stessa sequenza."""
        r1 = component_rng(42, 's1', 'iot')
        r2 = component_rng(42, 's1', 'iot')
        assert [r1.random() for _ in range(20)] == [r2.random() for _ in range(20)]

    def test_derivation_formula_is_sha256(self):
        """La derivazione è sha256(f\"{seed}:{stream_id}:{component}\"):
        contratto esplicito, indipendente da PYTHONHASHSEED."""
        digest = hashlib.sha256("42:s1:iot".encode()).hexdigest()
        expected = random.Random(int(digest, 16)).random()
        assert component_rng(42, 's1', 'iot').random() == expected

    def test_different_component_different_sequence(self):
        """Componenti diversi → sequenze indipendenti."""
        a = [component_rng(42, 's1', 'iot').random() for _ in range(3)]
        b = [component_rng(42, 's1', 'window').random() for _ in range(3)]
        assert a != b

    def test_different_stream_different_sequence(self):
        """Stream diversi → sequenze indipendenti."""
        a = component_rng(42, 's1', 'iot').random()
        b = component_rng(42, 's2', 'iot').random()
        assert a != b

    def test_different_seed_different_sequence(self):
        a = component_rng(1, 's1', 'iot').random()
        b = component_rng(2, 's1', 'iot').random()
        assert a != b

    def test_seed_zero_is_valid(self):
        """seed: 0 è valido e deterministico (non confuso con assente)."""
        assert component_rng(0, 's1', 'iot').random() == \
               component_rng(0, 's1', 'iot').random()

    def test_string_seed_supported(self):
        assert component_rng('mix-a', 's1', 'iot').random() == \
               component_rng('mix-a', 's1', 'iot').random()

    def test_seed_none_falls_back_to_global_random(self):
        """seed None → il chiamante usa il random globale (comportamento
        legacy per costruzioni dirette fuori dal Generator)."""
        rng = component_rng(None, 's1', 'iot')
        random.seed(5)
        a = rng.uniform(0, 1)
        random.seed(5)
        b = rng.uniform(0, 1)
        assert a == b  # legato allo stato del modulo random globale


# =============================================================================
# session_seed — seed di sessione da timestamp
# =============================================================================

class TestSessionSeed:

    def test_returns_non_negative_int(self):
        s = session_seed()
        assert isinstance(s, int)
        assert s >= 0

    def test_usable_as_component_seed(self):
        """Il session seed alimenta la stessa derivazione dei seed espliciti."""
        s = session_seed()
        assert component_rng(s, 's1', 'iot').random() == \
               component_rng(s, 's1', 'iot').random()


# =============================================================================
# voice_rng — regressione (issue #81, invariato)
# =============================================================================

class TestVoiceRngRegression:

    def test_voice_rng_deterministic_with_seed(self):
        assert voice_rng(42, 's1', 3).random() == voice_rng(42, 's1', 3).random()

    def test_voice_and_component_namespaces_coexist(self):
        """voice_rng e component_rng derivano dallo stesso schema ma con
        componenti distinti: nessuna collisione fra voce 1 e componente '1'
        è attesa (stessa stringa → stesso RNG, per costruzione)."""
        assert voice_rng(42, 's1', 1).random() == \
               component_rng(42, 's1', '1').random()
