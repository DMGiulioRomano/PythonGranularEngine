# tests/e2e/test_grain_json_e2e.py
"""
Test end-to-end per la flag Make GRAIN_JSON (issue #99).

Invoca `make all STEMS=true RENDERER=numpy` come subprocess e verifica
che GRAIN_JSON=true produca i sidecar JSON dei grani in SFDIR (uno per
stream, naming {FILE}__{stream_id}__grains.json) e che GRAIN_JSON=false
(default) non li produca.

Requisiti:
  - .venv già configurato (make venv-setup)
  - refs/pino.wav presente
  - NON richiede csound

Esegui con:
  make e2e-tests
  oppure: pytest tests/e2e/ -m e2e -v
"""

import json
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
  title: "e2e grain json test"

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


# =============================================================================
# HELPERS
# =============================================================================

def _write_yaml(tmp_path, content: str):
    """Scrive il YAML di test in <tmp_path>/configs/e2e_grain_json_test.yml."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir(exist_ok=True)
    (configs_dir / "e2e_grain_json_test.yml").write_text(content)


def _make_build_stems(tmp_path, grain_json=None):
    """
    Invoca `make all STEMS=true RENDERER=numpy` con directory temporanee.

    Args:
        grain_json: valore della variabile GRAIN_JSON ("true"/"false");
                    se None la variabile non viene passata (default Makefile)

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
        'FILE=e2e_grain_json_test',
        'STEMS=true',
        'RENDERER=numpy',
        'CACHE=false',
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
    if grain_json is not None:
        cmd.append(f'GRAIN_JSON={grain_json}')

    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return result, result.stdout + result.stderr


# =============================================================================
# FLAG GRAIN_JSON
# =============================================================================

@pytest.mark.e2e
class TestGrainJsonFlag:
    """STEMS=true RENDERER=numpy: flag GRAIN_JSON del Makefile."""

    def test_grain_json_files_created(self, tmp_path):
        """GRAIN_JSON=true: un sidecar __grains.json per ogni stream in SFDIR."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build_stems(tmp_path, grain_json='true')

        assert result.returncode == 0, f"make fallito:\n{output}"

        sfdir = tmp_path / "output"
        s1 = sfdir / "e2e_grain_json_test__s1__grains.json"
        s2 = sfdir / "e2e_grain_json_test__s2__grains.json"
        assert s1.exists(), f"sidecar s1 non trovato:\n{output}"
        assert s2.exists(), f"sidecar s2 non trovato:\n{output}"

        data = json.loads(s1.read_text())
        assert data["stream_id"] == "s1"

    @pytest.mark.parametrize("grain_json", [None, "false"],
                             ids=["default", "explicit-false"])
    def test_no_grain_json_by_default(self, tmp_path, grain_json):
        """GRAIN_JSON=false (default): nessun sidecar __grains.json prodotto."""
        _write_yaml(tmp_path, _YAML_TWO_STREAMS)
        result, output = _make_build_stems(tmp_path, grain_json=grain_json)

        assert result.returncode == 0, f"make fallito:\n{output}"

        sfdir = tmp_path / "output"
        sidecars = list(sfdir.glob("*__grains.json"))
        assert sidecars == [], \
            f"sidecar creati senza GRAIN_JSON=true: {sidecars}"
