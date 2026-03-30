# tests/e2e/test_reaper_export_e2e.py
"""
Test end-to-end per l'export Reaper (.rpp).

Invoca `make all REAPER=true RENDERER=numpy` come subprocess e verifica
che la pipeline YAML → .aif + .rpp produca un progetto Reaper valido.

Scenari:
1. TestReaperStemsExport  - STEMS=true: un TRACK per stream nel .rpp
2. TestReaperMixExport    - STEMS=false: un TRACK per il file mix
3. TestReaperCustomPath   - REAPER_PATH custom: il .rpp viene scritto nel path indicato

Non richiede csound (RENDERER=numpy).

Esegui con:
  make e2e-tests
  oppure: pytest tests/e2e/test_reaper_export_e2e.py -m e2e -v
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
  title: "e2e reaper test"

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
  title: "e2e reaper test"

streams:
  - stream_id: "alpha"
    onset: 0.0
    duration: 2.0
    sample: "pino.wav"
  - stream_id: "beta"
    onset: 2.0
    duration: 1.5
    sample: "pino.wav"
  - stream_id: "gamma"
    onset: 3.5
    duration: 1.0
    sample: "pino.wav"
"""


# =============================================================================
# HELPERS
# =============================================================================

def _write_yaml(tmp_path, content: str, name: str = "e2e_reaper_test"):
    """Scrive il YAML di test in <tmp_path>/configs/<name>.yml."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir(exist_ok=True)
    (configs_dir / f"{name}.yml").write_text(content)


def _make_build(tmp_path, stems: bool, extra_flags=None):
    """
    Invoca `make all REAPER=true RENDERER=numpy` con directory temporanee.

    Args:
        tmp_path: directory temporanea pytest
        stems: True per STEMS mode, False per MIX mode
        extra_flags: lista di flag aggiuntivi (es. ['REAPER_PATH=...'])

    Returns:
        tuple (CompletedProcess, str, Path) — processo, output combinato, path .rpp
    """
    sfdir  = tmp_path / "output"
    logdir = tmp_path / "logs"
    ymldir = tmp_path / "configs"
    rpp_out = tmp_path / "test_project.rpp"

    for d in (sfdir, logdir, ymldir):
        d.mkdir(exist_ok=True)

    cmd = [
        'make', 'all',
        'FILE=e2e_reaper_test',
        f'STEMS={"true" if stems else "false"}',
        'RENDERER=numpy',
        'REAPER=true',
        f'REAPER_PATH={rpp_out}',
        'AUTOKILL=false',
        'AUTOPEN=false',
        'AUTOVISUAL=false',
        'SHOWSTATIC=false',
        'PRECLEAN=false',
        f'SFDIR={sfdir}',
        f'LOGDIR={logdir}',
        f'YMLDIR={ymldir}',
    ]

    if extra_flags:
        cmd.extend(extra_flags)

    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return result, result.stdout + result.stderr, rpp_out


# =============================================================================
# 1. STEMS MODE
# =============================================================================

@pytest.mark.e2e
class TestReaperStemsExport:
    """STEMS=true REAPER=true: un TRACK per stream nel .rpp."""

    def test_build_succeeds(self, tmp_path):
        """La pipeline YAML → .aif + .rpp non fallisce."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output, _ = _make_build(tmp_path, stems=True)
        assert result.returncode == 0, f"make fallito:\n{output}"

    def test_rpp_file_created(self, tmp_path):
        """Il file .rpp viene creato al path indicato da REAPER_PATH."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output, rpp_out = _make_build(tmp_path, stems=True)
        assert result.returncode == 0, f"make fallito:\n{output}"
        assert rpp_out.exists(), f".rpp non trovato: {rpp_out}"

    def test_rpp_contains_reaper_project_header(self, tmp_path):
        """Il file .rpp inizia con il tag <REAPER_PROJECT."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output, rpp_out = _make_build(tmp_path, stems=True)
        assert result.returncode == 0, f"make fallito:\n{output}"
        content = rpp_out.read_text()
        assert "<REAPER_PROJECT" in content, \
            f"header Reaper mancante nel .rpp:\n{content[:200]}"

    def test_rpp_has_one_track_per_stream(self, tmp_path):
        """In STEMS mode il .rpp contiene un TRACK per ogni stream."""
        _write_yaml(tmp_path, _YAML_THREE_STREAMS)
        result, output, rpp_out = _make_build(tmp_path, stems=True)
        assert result.returncode == 0, f"make fallito:\n{output}"
        content = rpp_out.read_text()
        track_count = content.count("<TRACK")
        assert track_count == 3, \
            f"attesi 3 TRACK, trovati {track_count}:\n{content}"

    def test_rpp_track_names_match_stream_ids(self, tmp_path):
        """I nomi dei TRACK nel .rpp corrispondono agli stream_id del YAML."""
        _write_yaml(tmp_path, _YAML_THREE_STREAMS)
        result, output, rpp_out = _make_build(tmp_path, stems=True)
        assert result.returncode == 0, f"make fallito:\n{output}"
        content = rpp_out.read_text()
        for stream_id in ("alpha", "beta", "gamma"):
            assert f'NAME "{stream_id}"' in content, \
                f'TRACK NAME "{stream_id}" non trovato nel .rpp'

    def test_rpp_references_aif_files(self, tmp_path):
        """Il .rpp referenzia i file .aif generati."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output, rpp_out = _make_build(tmp_path, stems=True)
        assert result.returncode == 0, f"make fallito:\n{output}"
        content = rpp_out.read_text()
        assert 'FILE "' in content, \
            f"nessuna referenza FILE nel .rpp:\n{content}"
        assert ".aif" in content, \
            f"i file .aif non sono referenziati nel .rpp:\n{content}"

    def test_rpp_stream_positions_match_onsets(self, tmp_path):
        """Le posizioni POSITION nel .rpp corrispondono agli onset degli stream."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output, rpp_out = _make_build(tmp_path, stems=True)
        assert result.returncode == 0, f"make fallito:\n{output}"
        content = rpp_out.read_text()
        # s1: onset=0.0, s2: onset=1.0
        assert "POSITION 0.0" in content, \
            "POSITION 0.0 (onset s1) non trovato nel .rpp"
        assert "POSITION 1.0" in content, \
            "POSITION 1.0 (onset s2) non trovato nel .rpp"

    def test_aif_stems_also_created(self, tmp_path):
        """In STEMS mode i file .aif per-stream vengono creati insieme al .rpp."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output, _ = _make_build(tmp_path, stems=True)
        assert result.returncode == 0, f"make fallito:\n{output}"
        sfdir = tmp_path / "output"
        assert (sfdir / "e2e_reaper_test_s1.aif").exists(), "s1.aif non trovato"
        assert (sfdir / "e2e_reaper_test_s2.aif").exists(), "s2.aif non trovato"


# =============================================================================
# 2. MIX MODE
# =============================================================================

@pytest.mark.e2e
class TestReaperMixExport:
    """STEMS=false REAPER=true: un TRACK per il file mix."""

    def test_build_succeeds(self, tmp_path):
        """La pipeline MIX + REAPER non fallisce."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output, _ = _make_build(tmp_path, stems=False)
        assert result.returncode == 0, f"make fallito:\n{output}"

    def test_rpp_file_created(self, tmp_path):
        """Il file .rpp viene creato anche in MIX mode."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output, rpp_out = _make_build(tmp_path, stems=False)
        assert result.returncode == 0, f"make fallito:\n{output}"
        assert rpp_out.exists(), f".rpp non trovato: {rpp_out}"

    def test_rpp_contains_reaper_project_header(self, tmp_path):
        """Il file .rpp MIX contiene il tag <REAPER_PROJECT."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output, rpp_out = _make_build(tmp_path, stems=False)
        assert result.returncode == 0, f"make fallito:\n{output}"
        content = rpp_out.read_text()
        assert "<REAPER_PROJECT" in content

    def test_mix_aif_also_created(self, tmp_path):
        """In MIX mode il file .aif mix viene creato insieme al .rpp."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output, _ = _make_build(tmp_path, stems=False)
        assert result.returncode == 0, f"make fallito:\n{output}"
        assert (tmp_path / "output" / "e2e_reaper_test.aif").exists(), \
            "file mix .aif non trovato"


# =============================================================================
# 3. CUSTOM REAPER PATH
# =============================================================================

@pytest.mark.e2e
class TestReaperCustomPath:
    """REAPER_PATH custom: il .rpp viene scritto nel path indicato."""

    def test_custom_rpp_path_respected(self, tmp_path):
        """Il file .rpp viene scritto esattamente al path passato via REAPER_PATH."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        custom_rpp = tmp_path / "my_custom_project.rpp"

        sfdir  = tmp_path / "output"
        logdir = tmp_path / "logs"
        ymldir = tmp_path / "configs"
        for d in (sfdir, logdir, ymldir):
            d.mkdir(exist_ok=True)

        cmd = [
            'make', 'all',
            'FILE=e2e_reaper_test',
            'STEMS=true',
            'RENDERER=numpy',
            'REAPER=true',
            f'REAPER_PATH={custom_rpp}',
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
            cmd, cwd=PROJECT_ROOT, capture_output=True, text=True
        )
        output = result.stdout + result.stderr
        assert result.returncode == 0, f"make fallito:\n{output}"
        assert custom_rpp.exists(), \
            f".rpp non trovato al path custom {custom_rpp}"

    def test_default_rpp_path_without_reaper_path_flag(self, tmp_path):
        """Senza REAPER_PATH esplicito, il .rpp viene creato con il nome YAML."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)

        sfdir  = tmp_path / "output"
        logdir = tmp_path / "logs"
        ymldir = tmp_path / "configs"
        for d in (sfdir, logdir, ymldir):
            d.mkdir(exist_ok=True)

        # Non passiamo REAPER_PATH: il default e' il basename del YAML + .rpp
        cmd = [
            'make', 'all',
            'FILE=e2e_reaper_test',
            'STEMS=true',
            'RENDERER=numpy',
            'REAPER=true',
            'REAPER_PATH=',          # stringa vuota → main.py usa yaml_basename
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
            cmd, cwd=PROJECT_ROOT, capture_output=True, text=True
        )
        output = result.stdout + result.stderr
        assert result.returncode == 0, f"make fallito:\n{output}"
        # Con REAPER_PATH vuoto il flag --reaper-path non viene passato
        # e main.py usa yaml_basename: e2e_reaper_test.rpp nella cwd
        default_rpp = os.path.join(PROJECT_ROOT, "e2e_reaper_test.rpp")
        assert os.path.exists(default_rpp), \
            f".rpp default non trovato: {default_rpp}"
        # Cleanup
        if os.path.exists(default_rpp):
            os.unlink(default_rpp)
