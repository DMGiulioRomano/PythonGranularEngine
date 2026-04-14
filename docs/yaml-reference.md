# YAML Reference — PythonGranularEngine

## Minimal Stream

```yaml
streams:
  - stream_id: "stream1"
    onset: 0.0
    duration: 30
    sample: "sample.wav"
    grain:
      duration: 0.05
```

## Parameter Syntax

- Static value: `density: 10`
- Envelope (linear): `density: [[0, 10], [1, 50]]`
- Nested envelope: `density: [[[0, 5], [10, 50]], 1.0, 5]` (envelope of envelopes)
- Variation: `grain: {duration: 0.05, duration_range: 0.01}` (±0.01 randomization)
- Math expressions: `onset: (pi)`, `duration: (10/2)` — evaluated via safe_eval

## Special Stream Flags

- `solo`: only streams with this flag are rendered (if any stream has it)
- `mute`: stream is skipped (unless solo mode is active)
- `time_mode: normalized`: use 0.0–1.0 time range instead of seconds

## Multi-Voice Block

```yaml
voices:
  num_voices: 4
  pitch:
    strategy: chord   # step | range | chord | stochastic
    chord: "dom7"
  onset_offset:
    strategy: linear  # linear | geometric | stochastic
    step: 0.08
  pointer:
    strategy: linear  # linear | stochastic
    step: 0.1
  pan:
    strategy: linear  # linear | additive
    spread: 120.0
```

See `docs/multi-voice.md` for full strategy reference and examples.
