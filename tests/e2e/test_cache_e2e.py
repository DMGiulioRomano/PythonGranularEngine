# tests/e2e/test_cache_e2e.py
"""
Test end-to-end per la pipeline STEMS + CACHE.

Invoca `make all STEMS=true CACHE=true` come subprocess e verifica
l'intero comportamento della catena: Make → Python → Csound → filesystem.

Scenari:
1. TestFirstBuild        - prima build: tutti gli stream compilati, manifest creato
2. TestIncrementalBuild  - build invariata: tutti clean, file .aif non riscritti
3. TestPartialRebuild    - modifica parziale YAML: solo stream modificato è DIRTY
4. TestGarbageCollection - stream rimosso dal YAML: .aif orfano e entry manifest rimossi
5. TestStreamFile        - stream importato con `file:` (#290): modificare il
                           file importato marca dirty solo quello stream

Requisiti:
  - csound, sox, make nel PATH
  - .venv già configurato (make venv-setup)

Esegui con:
  make e2e-tests
  oppure: pytest tests/e2e/ -m e2e -v
"""

import json
import os
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("csound") is None,
    reason="csound non disponibile (Fedora/RHEL: usa RENDERER=numpy)",
)

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)

# =============================================================================
# YAML FIXTURES
# =============================================================================

_YAML_TWO_STREAMS = """\
composition:
  title: "e2e cache test"

streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 1.0
    sample: "pino.wav"
  - stream_id: "s2"
    onset: 0.0
    duration: 1.0
    sample: "pino.wav"
"""

# s1 con duration modificata (fingerprint diverso)
_YAML_S1_MODIFIED = """\
composition:
  title: "e2e cache test"

streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 1.5
    sample: "pino.wav"
  - stream_id: "s2"
    onset: 0.0
    duration: 1.0
    sample: "pino.wav"
"""

# Solo s1 rimasto (s2 rimosso → orfano)
_YAML_ONE_STREAM = """\
composition:
  title: "e2e cache test"

streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 1.0
    sample: "pino.wav"
"""


# =============================================================================
# HELPERS
# =============================================================================

def _write_yaml(tmp_path, content: str):
    """Scrive il YAML di test in <tmp_path>/configs/e2e_test.yml."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir(exist_ok=True)
    (configs_dir / "e2e_test.yml").write_text(content)


def _make_build(tmp_path):
    """
    Invoca `make all STEMS=true CACHE=true` con directory temporanee.

    Tutte le directory di output vengono reindirizzate in tmp_path per
    isolare la build dal progetto reale e garantire side-effect zero.

    Returns:
        tuple (CompletedProcess, str) — processo e output combinato (stdout+stderr)
    """
    sfdir    = tmp_path / "output"
    cachedir = tmp_path / "cache"
    logdir   = tmp_path / "logs"
    ymldir   = tmp_path / "configs"

    for d in (sfdir, cachedir, logdir, ymldir):
        d.mkdir(exist_ok=True)

    cmd = [
        'make', 'all',
        'FILE=e2e_test',
        'STEMS=true',
        'CACHE=true',
        'RENDERER=csound',
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
    output = result.stdout + result.stderr
    return result, output


def _manifest_path(tmp_path, renderer: str = "csound"):
    """Path del manifest: uno per progetto, non per backend.

    A separare i backend e' il fingerprint, che include il `renderer` (#228).
    Il parametro resta nella firma perche' i chiamanti dicono con quale
    backend hanno reso, ma il path non ne dipende.
    """
    return tmp_path / "cache" / "e2e_test.json"


def _load_manifest(tmp_path, renderer: str = "csound") -> dict:
    """Carica il manifest JSON dalla cache temporanea."""
    manifest_path = _manifest_path(tmp_path, renderer)
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text())


# =============================================================================
# 1. PRIMA BUILD
# =============================================================================

@pytest.mark.e2e
class TestFirstBuild:
    """Prima build: tutti gli stream compilati, manifest popolato."""

    def test_aif_files_created(self, tmp_path):
        """I file .aif per s1 e s2 vengono creati in SFDIR."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build(tmp_path)

        assert result.returncode == 0, f"make fallito:\n{output}"

        sfdir = tmp_path / "output"
        assert (sfdir / "e2e_test__s1.aif").exists(), "s1.aif non trovato"
        assert (sfdir / "e2e_test__s2.aif").exists(), "s2.aif non trovato"

    def test_manifest_created_with_both_streams(self, tmp_path):
        """Il manifest JSON contiene le entry per s1 e s2."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build(tmp_path)

        assert result.returncode == 0, f"make fallito:\n{output}"

        manifest = _load_manifest(tmp_path)
        assert "s1" in manifest, "s1 mancante nel manifest"
        assert "s2" in manifest, "s2 mancante nel manifest"

    def test_un_solo_manifest_per_progetto(self, tmp_path):
        """Il nome del file sul disco, non solo quello che la CLI annuncia.

        La separazione fra backend (#228) sta nel fingerprint, non nel nome:
        il manifest resta uno, cosi' il GC continua a vedere tutti gli stem.
        """
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build(tmp_path)
        assert result.returncode == 0, f"make fallito:\n{output}"

        assert (tmp_path / "cache" / "e2e_test.json").exists()
        assert list((tmp_path / "cache").glob("e2e_test*.json")) == [
            tmp_path / "cache" / "e2e_test.json"]

    def test_both_streams_reported_dirty(self, tmp_path):
        """Stdout riporta entrambi gli stream come DIRTY alla prima build."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build(tmp_path)

        assert result.returncode == 0, f"make fallito:\n{output}"
        assert "[CACHE] s1: DIRTY" in output
        assert "[CACHE] s2: DIRTY" in output

    def test_manifest_fingerprints_are_strings(self, tmp_path):
        """I fingerprint nel manifest sono stringhe SHA-256 di 64 caratteri."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build(tmp_path)

        assert result.returncode == 0, f"make fallito:\n{output}"

        manifest = _load_manifest(tmp_path)
        for sid in ("s1", "s2"):
            fp = manifest.get(sid, "")
            assert len(fp) == 64, f"fingerprint {sid} non SHA-256: {fp!r}"


# =============================================================================
# 2. BUILD INCREMENTALE (nessuna modifica)
# =============================================================================

@pytest.mark.e2e
class TestIncrementalBuild:
    """Build senza modifiche: tutti gli stream skipati."""

    def test_second_build_reports_all_clean(self, tmp_path):
        """Seconda build identica: stdout riporta tutti gli stream come clean."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build(tmp_path)
        assert r1.returncode == 0

        r2, output2 = _make_build(tmp_path)
        assert r2.returncode == 0

        assert "[CACHE] s1: clean" in output2
        assert "[CACHE] s2: clean" in output2

    def test_second_build_no_dirty_streams(self, tmp_path):
        """Seconda build: nessuno stream riportato come DIRTY."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build(tmp_path)
        assert r1.returncode == 0

        r2, output2 = _make_build(tmp_path)
        assert r2.returncode == 0
        assert "[CACHE] s1: DIRTY" not in output2
        assert "[CACHE] s2: DIRTY" not in output2

    def test_manifest_unchanged_after_second_build(self, tmp_path):
        """I fingerprint nel manifest non cambiano alla seconda build."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build(tmp_path)
        assert r1.returncode == 0
        manifest_after_first = _load_manifest(tmp_path)

        r2, _ = _make_build(tmp_path)
        assert r2.returncode == 0
        manifest_after_second = _load_manifest(tmp_path)

        assert manifest_after_first == manifest_after_second


# =============================================================================
# 3. REBUILD PARZIALE (solo stream modificato)
# =============================================================================

@pytest.mark.e2e
class TestPartialRebuild:
    """Modifica parziale del YAML: solo lo stream cambiato è DIRTY."""

    def test_modified_stream_is_dirty(self, tmp_path):
        """s1 (duration modificata) è DIRTY; s2 (invariato) è clean."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build(tmp_path)
        assert r1.returncode == 0

        _write_yaml(tmp_path, _YAML_S1_MODIFIED)
        r2, output2 = _make_build(tmp_path)
        assert r2.returncode == 0

        assert "[CACHE] s1: DIRTY" in output2
        assert "[CACHE] s2: clean" in output2

    def test_unchanged_stream_not_dirty(self, tmp_path):
        """s2 (invariato) non appare mai come DIRTY nella seconda build."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build(tmp_path)
        assert r1.returncode == 0

        _write_yaml(tmp_path, _YAML_S1_MODIFIED)
        r2, output2 = _make_build(tmp_path)
        assert r2.returncode == 0

        assert "[CACHE] s2: DIRTY" not in output2

    def test_manifest_fingerprint_updated_for_modified_stream(self, tmp_path):
        """Il fingerprint di s1 cambia nel manifest; quello di s2 rimane invariato."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build(tmp_path)
        assert r1.returncode == 0
        manifest_before = _load_manifest(tmp_path)

        _write_yaml(tmp_path, _YAML_S1_MODIFIED)
        r2, _ = _make_build(tmp_path)
        assert r2.returncode == 0
        manifest_after = _load_manifest(tmp_path)

        assert manifest_before["s1"] != manifest_after["s1"], "fingerprint s1 non aggiornato"
        assert manifest_before["s2"] == manifest_after["s2"], "fingerprint s2 non doveva cambiare"


# =============================================================================
# 4. GARBAGE COLLECTION (stream rimosso dal YAML)
# =============================================================================

@pytest.mark.e2e
class TestGarbageCollection:
    """Stream rimosso dal YAML: .aif orfano cancellato, entry manifest rimossa."""

    def test_orphan_aif_deleted(self, tmp_path):
        """Il file .aif di s2 (rimosso dal YAML) viene cancellato dalla GC."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build(tmp_path)
        assert r1.returncode == 0
        assert (tmp_path / "output" / "e2e_test__s2.aif").exists()

        _write_yaml(tmp_path, _YAML_ONE_STREAM)
        r2, output2 = _make_build(tmp_path)
        assert r2.returncode == 0

        assert not (tmp_path / "output" / "e2e_test__s2.aif").exists(), \
            "s2.aif orfano non cancellato"

    def test_orphan_manifest_entry_removed(self, tmp_path):
        """L'entry di s2 viene rimossa dal manifest dopo la GC."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build(tmp_path)
        assert r1.returncode == 0
        assert "s2" in _load_manifest(tmp_path)

        _write_yaml(tmp_path, _YAML_ONE_STREAM)
        r2, _ = _make_build(tmp_path)
        assert r2.returncode == 0

        assert "s2" not in _load_manifest(tmp_path), "s2 ancora nel manifest dopo GC"

    def test_gc_reported_in_stdout(self, tmp_path):
        """Stdout riporta la rimozione dello stream orfano (messaggio GC)."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build(tmp_path)
        assert r1.returncode == 0

        _write_yaml(tmp_path, _YAML_ONE_STREAM)
        r2, output2 = _make_build(tmp_path)
        assert r2.returncode == 0

        assert "GC" in output2, "nessun messaggio GC nello stdout"
        assert "s2" in output2, "stream orfano non menzionato nell'output GC"

    def test_surviving_stream_is_clean_after_gc(self, tmp_path):
        """s1 (rimasto nel YAML e invariato) non viene ricompilato durante la GC."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build(tmp_path)
        assert r1.returncode == 0

        _write_yaml(tmp_path, _YAML_ONE_STREAM)
        r2, output2 = _make_build(tmp_path)
        assert r2.returncode == 0

        assert "[CACHE] s1: clean" in output2

    def test_surviving_stream_aif_still_exists(self, tmp_path):
        """Il file .aif di s1 (sopravvissuto) non viene cancellato dalla GC."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        r1, _ = _make_build(tmp_path)
        assert r1.returncode == 0

        _write_yaml(tmp_path, _YAML_ONE_STREAM)
        r2, _ = _make_build(tmp_path)
        assert r2.returncode == 0

        assert (tmp_path / "output" / "e2e_test__s1.aif").exists(), \
            "s1.aif cancellato per errore dalla GC"


# =============================================================================
# 5. STREAM COME FILE (issue #290)
# =============================================================================
#
# Il master importa `s1` da un documento a se' (`- file: streams/s1.yml`) e
# scrive `s2` per intero. La cache lavora sullo stream gia' risolto, quindi
# il file importato e' una parte del brano come le altre: cambiarlo rifa' il
# suo stem e nient'altro, e il GC -- che legge gli id dal documento risolto --
# non scambia lo stream importato per un orfano.

_YAML_MASTER_IMPORTA = """\
streams:
  - file: streams/s1.yml
    onset: 0.0
  - stream_id: "s2"
    onset: 0.0
    duration: 1.0
    sample: "pino.wav"
"""

# Un documento del laboratorio: si rende anche da solo, quindi porta i suoi
# top-level, `onset: 0` e il proprio `stream_id`. Nel brano decide il master.
_YAML_S1_IMPORTATO = """\
seed: 7
duration: 1.0
bpm: 60
streams:
  - stream_id: "stream1"
    onset: 0.0
    duration: 1.0
    sample: "pino.wav"
"""


def _write_imported(tmp_path, content: str):
    """Il file importato, relativo alla cartella del master (`configs/`)."""
    streams_dir = tmp_path / "configs" / "streams"
    streams_dir.mkdir(parents=True, exist_ok=True)
    (streams_dir / "s1.yml").write_text(content)


@pytest.mark.e2e
class TestStreamFile:
    """`file:` negli stream del master, sotto `STEMS=true CACHE=true`."""

    def _prima_build(self, tmp_path):
        _write_yaml(tmp_path, _YAML_MASTER_IMPORTA)
        _write_imported(tmp_path, _YAML_S1_IMPORTATO)
        result, output = _make_build(tmp_path)
        assert result.returncode == 0, f"make fallito:\n{output}"
        return output

    def test_lo_stream_importato_ha_il_suo_stem(self, tmp_path):
        """L'id e' il nome del file, non lo `stream_id` del laboratorio."""
        output = self._prima_build(tmp_path)

        assert "[CACHE] s1: DIRTY" in output
        assert "[CACHE] s2: DIRTY" in output
        assert (tmp_path / "output" / "e2e_test__s1.aif").exists()
        assert not (tmp_path / "output" / "e2e_test__stream1.aif").exists()

    def test_modificare_il_file_importato_marca_dirty_solo_quello_stream(
            self, tmp_path):
        self._prima_build(tmp_path)
        manifest_prima = _load_manifest(tmp_path)

        _write_imported(tmp_path, _YAML_S1_IMPORTATO.replace(
            "    duration: 1.0", "    duration: 1.5"))
        r2, output2 = _make_build(tmp_path)
        assert r2.returncode == 0, f"make fallito:\n{output2}"
        manifest_dopo = _load_manifest(tmp_path)

        assert "[CACHE] s1: DIRTY" in output2
        assert "[CACHE] s2: clean" in output2
        assert manifest_prima["s1"] != manifest_dopo["s1"]
        assert manifest_prima["s2"] == manifest_dopo["s2"]

    def test_i_top_level_del_file_importato_non_toccano_la_cache(
            self, tmp_path):
        """`seed`, `duration`, `bpm` top-level del file sono ignorati: non
        sono nello stream risolto, quindi nemmeno nel suo fingerprint."""
        self._prima_build(tmp_path)

        _write_imported(tmp_path, _YAML_S1_IMPORTATO
                        .replace("seed: 7", "seed: 8")
                        .replace("bpm: 60", "bpm: 90"))
        r2, output2 = _make_build(tmp_path)
        assert r2.returncode == 0, f"make fallito:\n{output2}"

        assert "[CACHE] s1: clean" in output2
        assert "[CACHE] s2: clean" in output2

    def test_il_gc_non_scambia_lo_stream_importato_per_un_orfano(
            self, tmp_path):
        self._prima_build(tmp_path)

        r2, output2 = _make_build(tmp_path)
        assert r2.returncode == 0, f"make fallito:\n{output2}"

        assert "[CACHE] GC:" not in output2
        assert "s1" in _load_manifest(tmp_path)
        assert (tmp_path / "output" / "e2e_test__s1.aif").exists()
