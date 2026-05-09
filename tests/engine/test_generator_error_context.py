# =============================================================================
# tests/engine/test_generator_error_context.py
# =============================================================================
"""
Test per l'arricchimento del context su SampleNotFoundError nel layer Generator
(issue #33, step 4).

Generator.create_elements deve catturare SampleNotFoundError e arricchirlo
con config_file (yaml_path) prima del re-raise.
"""
import pytest

from engine.generator import Generator
from shared.exceptions import SampleNotFoundError


MINIMAL_YAML_WITH_MISSING_SAMPLE = """\
composition:
  title: "test"
streams:
  - stream_id: "drone_a"
    time_mode: normalized
    onset: 0.0
    duration: 1.0
    sample: "__missing_test_sample_xyz__.wav"
    distribution_mode: 'gaussian'
    density:
      type: cubic
      points: [[0,10],[1,10]]
    distribution: [[0,1],[1,1]]
    pointer:
      speed_ratio: 1.0
    grain:
      duration: 0.05
      duration_range: 0.01
"""


def test_generator_create_elements_enriches_with_config_file(tmp_path):
    """Generator aggiunge config_file (yaml_path) all'errore."""
    yaml_file = tmp_path / "broken.yml"
    yaml_file.write_text(MINIMAL_YAML_WITH_MISSING_SAMPLE)

    gen = Generator(str(yaml_file))
    gen.load_yaml()

    with pytest.raises(SampleNotFoundError) as exc_info:
        gen.create_elements()

    err = exc_info.value
    assert err.config_file == str(yaml_file)
    assert err.stream_id == 'drone_a'  # propagato da Stream
    assert err.filename == '__missing_test_sample_xyz__.wav'
