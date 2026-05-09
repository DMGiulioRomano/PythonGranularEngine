# =============================================================================
# tests/engine/test_generator_config_error_context.py
# =============================================================================
"""
Generator.create_elements arricchisce config_file su tutti i ConfigError
(issue #38, PR1) — non solo SampleNotFoundError.
"""
import pytest

from engine.generator import Generator
from shared.exceptions import MissingFieldError


YAML_MISSING_SAMPLE_FIELD = """\
composition:
  title: "test"
streams:
  - stream_id: "drone_a"
    time_mode: normalized
    onset: 0.0
    duration: 1.0
    sample: null
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


def test_generator_enriches_missing_field_error_with_config_file(tmp_path):
    yaml_file = tmp_path / "broken.yml"
    yaml_file.write_text(YAML_MISSING_SAMPLE_FIELD)

    gen = Generator(str(yaml_file))
    gen.load_yaml()

    with pytest.raises(MissingFieldError) as exc_info:
        gen.create_elements()

    err = exc_info.value
    assert err.config_file == str(yaml_file)
    assert err.stream_id == 'drone_a'
    assert 'sample' in err.fields
