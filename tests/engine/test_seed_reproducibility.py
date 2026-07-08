# tests/engine/test_seed_reproducibility.py
"""
test_seed_reproducibility.py

Test di riproducibilità della chiave YAML `seed` (issue #81).

Due meccanismi stocastici, due livelli di verifica:

- Meccanismo 2 (random globale dei grani): con `distribution: 1.0` l'inter-onset
  per-grano usa `random.uniform` globale. Due render con `seed: 42` devono
  produrre la stessa sequenza di onset; senza seed le due materializzazioni
  divergono (il random globale non viene mai re-seminato). Verificato in-process:
  `random.seed()` è deterministico per costruzione, l'unico difetto era che non
  veniva mai chiamato.

- Meccanismo 1 (RNG locale delle voci): l'offset stocastico delle voci deve
  essere identico fra PROCESSI diversi quando il seed è fissato. Verificato via
  subprocess con `PYTHONHASHSEED` differenti: con seed → identico (derivazione
  hashlib), senza seed → diverso (hash() randomizzato per-processo).

Non richiede csound/sox né sample reali: il sample è mockato (`get_sample_duration`)
e i grani si confrontano simbolicamente (onset/pointer/pitch), senza rendering audio.
"""

import os
import subprocess
import sys
import textwrap

import pytest
import yaml
from unittest.mock import patch

from pge.engine.generator import Generator


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)


# =============================================================================
# MECCANISMO 2 — random globale dei grani (in-process)
# =============================================================================

def _yaml_async_stream(seed=None):
    """YAML con un singolo stream async (distribution: 1.0 → IOT stocastico)."""
    data = {
        'streams': [{
            'stream_id': 's1',
            'onset': 0.0,
            'duration': 8.0,
            'sample': 'test.wav',
            'density': 20,
            'distribution': 1.0,
            'grain': {'duration': 0.05},
        }],
    }
    if seed is not None:
        data['seed'] = seed
    return data


def _materialize_onsets(tmp_path, yaml_data):
    """Crea il Generator, semina (se seed presente) e materializza i grani.

    Ritorna la lista di onset dei grani (lo stocastico del meccanismo 2 vive
    nell'inter-onset async).
    """
    cfg = tmp_path / "seed_repro.yml"
    cfg.write_text(yaml.safe_dump(yaml_data))
    gen = Generator(str(cfg))
    gen.load_yaml()
    with patch('pge.core.stream.get_sample_duration', return_value=10.0):
        gen.create_elements()
        onsets = [round(g.onset, 9) for s in gen.streams for g in s.grains]
    return onsets


class TestGlobalRandomReproducibility:

    def test_same_seed_reproducible(self, tmp_path):
        """Due render con lo stesso seed → stessa sequenza di onset."""
        run1 = _materialize_onsets(tmp_path, _yaml_async_stream(seed=42))
        run2 = _materialize_onsets(tmp_path, _yaml_async_stream(seed=42))
        assert run1 == run2
        assert len(run1) > 10  # lo stream ha davvero generato grani stocastici

    def test_without_seed_not_reproducible(self, tmp_path):
        """Senza seed le due materializzazioni divergono (random globale mai re-seminato)."""
        run1 = _materialize_onsets(tmp_path, _yaml_async_stream(seed=None))
        run2 = _materialize_onsets(tmp_path, _yaml_async_stream(seed=None))
        assert run1 != run2

    def test_different_seeds_diverge(self, tmp_path):
        """Seed diversi → sequenze diverse."""
        run1 = _materialize_onsets(tmp_path, _yaml_async_stream(seed=1))
        run2 = _materialize_onsets(tmp_path, _yaml_async_stream(seed=2))
        assert run1 != run2

    def test_seed_zero_reproducible(self, tmp_path):
        """seed: 0 è valido e riproducibile (non confuso con assente)."""
        run1 = _materialize_onsets(tmp_path, _yaml_async_stream(seed=0))
        run2 = _materialize_onsets(tmp_path, _yaml_async_stream(seed=0))
        assert run1 == run2


# =============================================================================
# MECCANISMO 1 — RNG locale voci (cross-process via PYTHONHASHSEED)
# =============================================================================

_SNIPPET = textwrap.dedent("""
    import sys
    from pge.strategies.voice_pitch_strategy import StochasticPitchStrategy
    from pge.parameters.pitch_unit import EdoUnit
    seed = None if sys.argv[1] == 'none' else int(sys.argv[1])
    s = StochasticPitchStrategy(pitch_range=2.0, stream_id='s1', seed=seed)
    u = EdoUnit(12)
    vals = [s.get_pitch_factor(i, 6, 0.0, u) for i in range(1, 6)]
    print(','.join(f'{v:.12f}' for v in vals))
""")


def _run_with_hashseed(hashseed: str, seed_arg: str) -> str:
    """Esegue lo snippet in un processo separato con PYTHONHASHSEED fissato."""
    env = dict(os.environ)
    env['PYTHONHASHSEED'] = hashseed
    env['PYTHONPATH'] = 'src' + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run(
        [sys.executable, '-c', _SNIPPET, seed_arg],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class TestVoiceRngCrossProcess:

    def test_seed_reproducible_across_processes(self):
        """Con seed fissato l'offset è identico fra PYTHONHASHSEED diversi."""
        out1 = _run_with_hashseed('1', '42')
        out2 = _run_with_hashseed('2', '42')
        assert out1 == out2

    def test_without_seed_differs_across_processes(self):
        """Senza seed l'offset dipende da PYTHONHASHSEED (bug pre-#81)."""
        out1 = _run_with_hashseed('1', 'none')
        out2 = _run_with_hashseed('2', 'none')
        assert out1 != out2
