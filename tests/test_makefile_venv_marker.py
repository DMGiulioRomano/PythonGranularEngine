"""
Il venv si rifa' solo quando serve.

`venv-setup` dipende da un marker (`$(VENV_DIR)/.installed`) che deve
risultare aggiornato finche' `pyproject.toml` e `requirements.txt` non
cambiano. Con `check-python` — un target `.PHONY` — fra i prerequisiti
normali del marker, make lo considerava sempre piu' nuovo, e ogni target
appeso a `venv-setup` (`make all`, `make tests`, ogni e2e) rilanciava
`python -m venv` e due `pip install`: circa 5 s su una build che ne
rendeva 0.03.

Il test guarda il piano di make (`-n`) su un `VENV_DIR` temporaneo, quindi
non tocca il venv del checkout. Le due meta' contano: un marker fresco non
rifa' niente, ma uno assente o piu' vecchio delle dipendenze si'.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _piano(venv_dir: Path) -> str:
    result = subprocess.run(
        ["make", "-n", "venv-setup", f"VENV_DIR={venv_dir}"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _rifa_il_venv(piano: str) -> bool:
    return "-m venv" in piano or "pip install" in piano


def test_marker_fresco_non_rifa_il_venv(tmp_path):
    (tmp_path / ".installed").touch()
    assert not _rifa_il_venv(_piano(tmp_path)), _piano(tmp_path)


def test_marker_fresco_controlla_comunque_la_versione_di_python(tmp_path):
    (tmp_path / ".installed").touch()
    assert "Verifica versione" in _piano(tmp_path)


def test_marker_assente_rifa_il_venv(tmp_path):
    assert _rifa_il_venv(_piano(tmp_path))


def test_marker_piu_vecchio_delle_dipendenze_rifa_il_venv(tmp_path):
    marker = tmp_path / ".installed"
    marker.touch()
    os.utime(marker, (0, 0))
    assert _rifa_il_venv(_piano(tmp_path))
