# tests/rendering/test_envelope_extractor_characterization.py
"""
Rete di caratterizzazione TEMPORANEA per rendering.envelope_extractor.

Congela l'output di get_stream_envelopes su config reali del progetto,
costruite attraverso la pipeline vera (Generator -> Stream), non su MagicMock.
E' il paracadute del refactor ParameterCurve (docs/explanation/parameter-curve.md):
mentre il seam si sposta da "leggere i privati di Parameter" a "chiedere una
ParameterCurve", l'output osservabile non deve cambiare di una virgola.

Perche' serve, visto che test_envelope_extractor.py esiste gia': quella suite
usa MagicMock e verifica un parametro alla volta. Nessun test copre oggi la
combinazione reale — schema + pitch unit-driven + stream._pointer.deviation +
offset per-voce — sullo stesso Stream costruito davvero dal YAML.

Config scelte:
  PGE_visualizer_envelopes_test.yml  nata per la issue #96: _mod_range, gate
                                     dephase, pointer.offset_range
  PGE_pitch_units_showcase.yml       pitch unit-driven, tutte le unita'
  PGE_testVoices.yml                 blocco voices / offset per-voce

Lo snapshot e' una LISTA di coppie [chiave, breakpoint], non un dict: cosi' il
confronto e' sensibile anche all'ORDINE delle chiavi, da cui dipende l'ordine
dei layer nelle sessioni Sonic Visualiser.

Rigenerare la baseline (solo se il cambiamento e' voluto):
    PGE_UPDATE_BASELINE=1 python -m pytest \\
        tests/rendering/test_envelope_extractor_characterization.py -k regenerate

DA CANCELLARE a refactor completato: la copertura definitiva sono
test_parameter_curve.py, test_voice_manager_curves.py e test_envelope_extractor.py.
"""
import json
import os

import numpy as np
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CONFIG_DIR = os.path.join(REPO_ROOT, 'configs')
BASELINE_PATH = os.path.join(
    os.path.dirname(__file__), 'fixtures', 'envelope_extractor_baseline.json')

# config del repo -> sample referenziati dal YAML (creati vuoti nella tmpdir).
REPO_CONFIGS = {
    'PGE_visualizer_envelopes_test.yml': ('001-0_0-3_0.wav',),
    'PGE_pitch_units_showcase.yml': ('voice.wav',),
    'PGE_testVoices.yml': ('voice.wav',),
}

# Config sintetica per i casi DEGENERI, che nessuna config del repo esercita:
# un Envelope con tutti i breakpoint uguali e' una costante travestita, e va
# trattato come uno scalare. E' la regola oggi duplicata sei volte
# nell'estrattore e il cuore di quello che ParameterCurve deve assorbire —
# senza questi stream la rete non la copre, verificato rompendo apposta
# `is_static` in PARTE 1 e vedendo la suite restare verde.
EDGE_CASES_NAME = 'edge_cases_flat_curves.yml'
EDGE_CASES_YAML = """
duration: 20

streams:
  # Valore base: Envelope piatto a due e a tre breakpoint.
  - stream_id: "flat_value_envelope"
    onset: 0
    duration: 10
    sample: voice.wav
    density: 20
    grain: {duration: 0.05, envelope: hanning}
    volume: [[0, -6], [10, -6]]
    pan: [[0, 30], [5, 30], [10, 30]]
    pointer: {speed_ratio: 1.0}

  # Range e gate piatti: _mod_range costante, EnvelopeGate costante,
  # RandomGate (probabilita' scalare), offset_range costante.
  - stream_id: "flat_range_and_gate"
    onset: 10
    duration: 10
    sample: voice.wav
    density: 20
    grain: {duration: 0.05, envelope: hanning}
    volume: -6
    volume_range: [[0, 3], [10, 3]]
    pan: 0
    pan_range: 20
    pointer:
      speed_ratio: 1.0
      offset_range: [[0, 0.5], [10, 0.5]]
    dephase:
      volume: [[0, 40], [10, 40]]
      pan: 25
"""

CONFIG_NAMES = sorted(REPO_CONFIGS) + [EDGE_CASES_NAME]

# Seed esplicito: le voice strategy stocastiche derivano l'offset per voce da
# (seed, rng_id, voice_index) via hashlib e lo memorizzano in cache. Con un
# seed fissato lo snapshot e' riproducibile fra processi e stabile fra
# campionamenti ripetuti dello stesso stream.
FIXED_SEED = 12345

SAMPLE_RATE = 48000
SAMPLE_SECONDS = 3.0

# I tre assi di gating dell'estrattore. envelope_filter non ha una variante
# propria: e' un filtro sulle chiavi del risultato, gia' coperto dalla suite
# unitaria e senza interazione con l'estrazione.
VARIANTS = {
    'default': {},
    'show_static': {'show_static': True},
    'voice_offsets': {'show_voice_offsets': True},
}


@pytest.fixture(scope='module')
def samples_dir(tmp_path_factory):
    """Sample silenziosi in tmpdir: refs/ e' vuoto in locale (la CI genera
    refs/pino.wav con sox solo nel job e2e) e l'estrattore non legge l'audio,
    solo la durata del file."""
    import soundfile as sf

    directory = tmp_path_factory.mktemp('refs')
    names = {name for names in REPO_CONFIGS.values() for name in names}
    names.add('voice.wav')  # usato dalla config sintetica
    for name in names:
        sf.write(
            str(directory / name),
            np.zeros(int(SAMPLE_RATE * SAMPLE_SECONDS), dtype='float32'),
            SAMPLE_RATE,
        )
    return str(directory)


@pytest.fixture(scope='module')
def config_paths(tmp_path_factory):
    """{nome: path} per le config del repo piu' quella sintetica, scritta in
    tmpdir per non aggiungere un file di test dentro configs/."""
    paths = {
        name: os.path.join(CONFIG_DIR, name) for name in REPO_CONFIGS
    }
    directory = tmp_path_factory.mktemp('configs')
    edge_path = directory / EDGE_CASES_NAME
    edge_path.write_text(EDGE_CASES_YAML)
    paths[EDGE_CASES_NAME] = str(edge_path)
    return paths


def _breakpoints(envelope):
    """Breakpoint arrotondati e in tipi JSON-serializzabili."""
    return [[round(float(t), 6), round(float(v), 6)]
            for t, v in envelope.breakpoints]


def _snapshot(config_path, samples_dir):
    """{stream_id: {variante: [[chiave, breakpoint], ...]}} per una config."""
    from pge.engine.generator import Generator
    from pge.rendering.envelope_extractor import get_stream_envelopes

    generator = Generator(config_path, samples_dir=samples_dir)
    generator.load_yaml()
    generator.seed = FIXED_SEED
    generator.create_elements()

    snapshot = {}
    for stream in generator.streams:
        per_variant = {}
        for variant, kwargs in VARIANTS.items():
            envelopes = get_stream_envelopes(stream, **kwargs)
            per_variant[variant] = [
                [key, _breakpoints(env)] for key, env in envelopes.items()
            ]
        snapshot[stream.stream_id] = per_variant
    return snapshot


def _load_baseline():
    if not os.path.exists(BASELINE_PATH):
        pytest.fail(
            f"baseline assente: {BASELINE_PATH}\n"
            "Rigenerala con: PGE_UPDATE_BASELINE=1 python -m pytest "
            f"{os.path.relpath(__file__, REPO_ROOT)} -k regenerate"
        )
    with open(BASELINE_PATH) as handle:
        return json.load(handle)


@pytest.mark.parametrize('config_name', CONFIG_NAMES)
def test_extraction_matches_baseline(config_name, config_paths, samples_dir):
    """L'estrazione su config reali e' identica alla baseline congelata."""
    baseline = _load_baseline()
    assert config_name in baseline, (
        f"'{config_name}' non e' nella baseline: rigenerala")
    actual = _snapshot(config_paths[config_name], samples_dir)
    assert actual == baseline[config_name]


def test_baseline_covers_flat_envelope_as_constant(config_paths, samples_dir):
    """La costante travestita e' davvero esercitata.

    Un Envelope con tutti i breakpoint uguali non deve comparire in 'default'
    (e' una costante) e deve comparire in 'show_static'. E' la regola che
    ParameterCurve assorbe: se la baseline non la coprisse, il refactor
    potrebbe perderla restando verde.
    """
    snapshot = _snapshot(config_paths[EDGE_CASES_NAME], samples_dir)
    stream = snapshot['flat_value_envelope']

    default_keys = {key for key, _ in stream['default']}
    static_keys = {key for key, _ in stream['show_static']}

    assert 'volume' not in default_keys
    assert 'pan' not in default_keys
    assert {'volume', 'pan'} <= static_keys


def test_baseline_covers_every_extraction_path(config_paths, samples_dir):
    """La baseline esercita davvero tutti i path dell'estrattore.

    Senza questo, una baseline che copre solo il ciclo sugli schemi passerebbe
    verde mentre il refactor rompe pointer_deviation o gli offset per-voce.
    """
    keys = set()
    for config_name in CONFIG_NAMES:
        for per_variant in _snapshot(config_paths[config_name],
                                     samples_dir).values():
            for pairs in per_variant.values():
                keys.update(key for key, _ in pairs)

    # PARTE 1 (valore da schema), PARTE 2 (_prob dal gate), PARTE 3 (_range da
    # _mod_range), pitch unit-driven, nomi espliciti fuori schema,
    # stream._pointer.deviation, offset per-voce campionati.
    for expected in ('volume', 'volume_prob', 'pan_range', 'grain_duration',
                     'pitch', 'num_voices', 'pointer_deviation',
                     'pointer_deviation_prob'):
        assert expected in keys, f"path non esercitato dalla baseline: {expected}"

    assert any(key.startswith('voice_') for key in keys), (
        "nessun offset per-voce nella baseline")


@pytest.mark.skipif(
    not os.environ.get('PGE_UPDATE_BASELINE'),
    reason="rigenerazione esplicita: PGE_UPDATE_BASELINE=1 ... -k regenerate")
def test_regenerate_baseline(config_paths, samples_dir):
    """Non e' un test: riscrive la baseline con il comportamento corrente.

    Da usare solo quando il cambiamento e' voluto e revisionato nel diff.
    """
    data = {
        name: _snapshot(config_paths[name], samples_dir)
        for name in CONFIG_NAMES
    }
    os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
    with open(BASELINE_PATH, 'w') as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write('\n')
