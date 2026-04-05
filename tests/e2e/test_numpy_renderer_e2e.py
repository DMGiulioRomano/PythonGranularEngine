# tests/e2e/test_numpy_renderer_e2e.py
"""
Test end-to-end per il renderer NumPy.

Invoca `make all RENDERER=numpy` come subprocess e verifica
che la pipeline YAML → NumPy → .aif produca i file corretti.

Scenari:
1. TestNumpyStems      - STEMS=true: un .aif per stream, naming corretto
2. TestNumpyMix        - STEMS=false: un .aif unico con tutti gli stream
3. TestNumpyStemsCache - STEMS=true CACHE=true: dirty/clean incrementale

Requisiti:
  - sox nel PATH (per audio trimming)
  - .venv già configurato (make venv-setup)
  - NON richiede csound

Esegui con:
  make e2e-tests
  oppure: pytest tests/e2e/ -m e2e -v
"""

import os
import subprocess

import pytest

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)

# =============================================================================
# YAML FIXTURES
# =============================================================================

_YAML_TWO_STREAMS = """\
composition:
  title: "e2e numpy test"

streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 1.0
    sample: "pino.wav"
  - stream_id: "s2"
    onset: 1.0
    duration: 1.0
    sample: "pino.wav"
"""

_YAML_THREE_STREAMS = """\
composition:
  title: "e2e numpy test"

streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 1.0
    sample: "pino.wav"
  - stream_id: "s2"
    onset: 1.0
    duration: 1.0
    sample: "pino.wav"
  - stream_id: "s3"
    onset: 2.0
    duration: 1.0
    sample: "pino.wav"
"""


# =============================================================================
# HELPERS
# =============================================================================

def _write_yaml(tmp_path, content: str):
    """Scrive il YAML di test in <tmp_path>/configs/e2e_numpy_test.yml."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir(exist_ok=True)
    (configs_dir / "e2e_numpy_test.yml").write_text(content)


def _load_manifest(tmp_path) -> dict:
    """Carica il manifest JSON dalla cache temporanea."""
    import json
    manifest_path = tmp_path / "cache" / "e2e_numpy_test.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text())


def _make_build_stems(tmp_path, cache=True):
    """
    Invoca `make all STEMS=true RENDERER=numpy` con directory temporanee.

    Args:
        cache: se True passa CACHE=true (abilita manifest incrementale)

    Returns:
        tuple (CompletedProcess, str) — processo e output combinato
    """
    sfdir    = tmp_path / "output"
    cachedir = tmp_path / "cache"
    logdir   = tmp_path / "logs"
    ymldir   = tmp_path / "configs"

    for d in (sfdir, logdir, ymldir):
        d.mkdir(exist_ok=True)

    cmd = [
        'make', 'all',
        'FILE=e2e_numpy_test',
        'STEMS=true',
        'RENDERER=numpy',
        f'CACHE={"true" if cache else "false"}',
        'AUTOKILL=false',
        'AUTOPEN=false',
        'AUTOVISUAL=false',
        'SHOWSTATIC=false',
        'PRECLEAN=false',
        f'SFDIR={sfdir}',
        f'CACHEDIR={cachedir}',
        f'LOGDIR={logdir}',
        f'YMLDIR={ymldir}',
    ]

    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return result, result.stdout + result.stderr


def _make_build_mix(tmp_path):
    """
    Invoca `make all STEMS=false RENDERER=numpy` con directory temporanee.

    Returns:
        tuple (CompletedProcess, str) — processo e output combinato
    """
    sfdir  = tmp_path / "output"
    logdir = tmp_path / "logs"
    ymldir = tmp_path / "configs"

    for d in (sfdir, logdir, ymldir):
        d.mkdir(exist_ok=True)

    cmd = [
        'make', 'all',
        'FILE=e2e_numpy_test',
        'STEMS=false',
        'RENDERER=numpy',
        'AUTOKILL=false',
        'AUTOPEN=false',
        'AUTOVISUAL=false',
        'SHOWSTATIC=false',
        'PRECLEAN=false',
        f'SFDIR={sfdir}',
        f'LOGDIR={logdir}',
        f'YMLDIR={ymldir}',
    ]

    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return result, result.stdout + result.stderr


# =============================================================================
# 1. STEMS MODE
# =============================================================================

@pytest.mark.e2e
class TestNumpyStems:
    """STEMS=true RENDERER=numpy: un .aif per stream."""

    def test_per_stream_files_created(self, tmp_path):
        """Un file .aif separato viene creato per ogni stream."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build_stems(tmp_path)

        assert result.returncode == 0, f"make fallito:\n{output}"

        sfdir = tmp_path / "output"
        assert (sfdir / "e2e_numpy_test_s1.aif").exists(), "s1.aif non trovato"
        assert (sfdir / "e2e_numpy_test_s2.aif").exists(), "s2.aif non trovato"

    def test_no_mix_file_created(self, tmp_path):
        """In STEMS mode non viene creato il file mix (senza suffisso stream)."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build_stems(tmp_path)

        assert result.returncode == 0, f"make fallito:\n{output}"

        # Il file mix non deve esistere
        assert not (tmp_path / "output" / "e2e_numpy_test.aif").exists(), \
            "file mix creato per errore in STEMS mode"

    def test_correct_number_of_files(self, tmp_path):
        """Il numero di .aif creati corrisponde al numero di stream nel YAML."""
        _write_yaml(tmp_path, _YAML_THREE_STREAMS)
        result, output = _make_build_stems(tmp_path)

        assert result.returncode == 0, f"make fallito:\n{output}"

        sfdir = tmp_path / "output"
        aif_files = list(sfdir.glob("e2e_numpy_test_*.aif"))
        assert len(aif_files) == 3, \
            f"attesi 3 file .aif, trovati {len(aif_files)}: {aif_files}"

    def test_no_cache_manifest_without_cache_flag(self, tmp_path):
        """Senza CACHE=true non viene creato alcun manifest JSON."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build_stems(tmp_path, cache=False)

        assert result.returncode == 0, f"make fallito:\n{output}"

        cache_dir = tmp_path / "cache"
        assert not cache_dir.exists() or not list(cache_dir.glob("*.json")), \
            "manifest JSON creato per errore senza CACHE=true"


# =============================================================================
# 2. MIX MODE
# =============================================================================

@pytest.mark.e2e
class TestNumpyMix:
    """STEMS=false RENDERER=numpy: un .aif unico con tutti gli stream."""

    def test_single_mix_file_created(self, tmp_path):
        """Un solo file .aif viene creato con tutti gli stream mixati."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build_mix(tmp_path)

        assert result.returncode == 0, f"make fallito:\n{output}"

        assert (tmp_path / "output" / "e2e_numpy_test.aif").exists(), \
            "file mix non trovato"

    def test_no_per_stream_files_created(self, tmp_path):
        """In MIX mode non vengono creati file per-stream."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build_mix(tmp_path)

        assert result.returncode == 0, f"make fallito:\n{output}"

        sfdir = tmp_path / "output"
        per_stream_files = list(sfdir.glob("e2e_numpy_test_*.aif"))
        assert len(per_stream_files) == 0, \
            f"file per-stream creati per errore in MIX mode: {per_stream_files}"


# =============================================================================
# 3. STEMS + CACHE (numpy incrementale)
# =============================================================================

_YAML_S1_MODIFIED = """\
composition:
  title: "e2e numpy test"

streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 1.5
    sample: "pino.wav"
  - stream_id: "s2"
    onset: 1.0
    duration: 1.0
    sample: "pino.wav"
"""


@pytest.mark.e2e
class TestNumpyStemsCache:
    """STEMS=true RENDERER=numpy CACHE=true: build incrementale."""

    def test_first_build_both_dirty(self, tmp_path):
        """Prima build: entrambi gli stream DIRTY."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build_stems(tmp_path, cache=True)

        assert result.returncode == 0, f"make fallito:\n{output}"
        assert "[CACHE] s1: DIRTY" in output
        assert "[CACHE] s2: DIRTY" in output

    def test_manifest_created_after_first_build(self, tmp_path):
        """Prima build: manifest JSON creato con fingerprint per s1 e s2."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build_stems(tmp_path, cache=True)

        assert result.returncode == 0, f"make fallito:\n{output}"

        manifest = _load_manifest(tmp_path)
        assert "s1" in manifest
        assert "s2" in manifest

    def test_second_build_both_clean(self, tmp_path):
        """Seconda build invariata: entrambi gli stream clean."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build_stems(tmp_path, cache=True)
        assert r1.returncode == 0

        r2, output2 = _make_build_stems(tmp_path, cache=True)
        assert r2.returncode == 0
        assert "[CACHE] s1: clean" in output2
        assert "[CACHE] s2: clean" in output2

    def test_partial_rebuild_only_modified_stream_dirty(self, tmp_path):
        """Modifica s1: solo s1 DIRTY, s2 clean."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build_stems(tmp_path, cache=True)
        assert r1.returncode == 0

        _write_yaml(tmp_path, _YAML_S1_MODIFIED)
        r2, output2 = _make_build_stems(tmp_path, cache=True)
        assert r2.returncode == 0

        assert "[CACHE] s1: DIRTY" in output2
        assert "[CACHE] s2: clean" in output2
