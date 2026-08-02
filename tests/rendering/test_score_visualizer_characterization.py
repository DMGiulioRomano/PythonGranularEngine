# tests/rendering/test_score_visualizer_characterization.py
"""
Rete di caratterizzazione TEMPORANEA per la logica pura di ScoreVisualizer.

Congela i NUMERI che il visualizer calcola prima di disegnare — layout di
pagina, corsie e legenda, range di display, normalizzazioni, vertici dei grani,
target delle lenti — su config reali del progetto, costruite attraverso la
pipeline vera (Generator -> Stream), non su MagicMock.

E' il paracadute dell'estrazione dei quattro moduli puri (page_layout,
envelope_scaling, grain_visuals, magnifier_targets): mentre la logica esce
dalla classe, l'output osservabile non deve cambiare di una virgola.

Perche' i numeri e non il PDF: uno snapshot della figura sarebbe legato alla
versione di matplotlib e si romperebbe per ragioni che non c'entrano con il
refactor. I numeri che entrano nei comandi di disegno sono invece esattamente
cio' che il refactor sposta, quindi sono il livello giusto a cui congelare.

Perche' serve, visto che test_score_visualizer.py esiste gia': quella suite usa
MagicMock e verifica un metodo alla volta. Nessun test copre oggi la
combinazione reale — paginazione multi-stream + corsie envelope + range
data-driven + geometria dei grani — sullo stesso Generator costruito davvero
dal YAML.

Config scelte:
  PGE_visualizer_envelopes_test.yml  envelope ricchi (_mod_range, gate dephase,
                                     offset_range): range di display e
                                     normalizzazione
  PGE_testVoices.yml                 20 stream su 6 pagine, blocco voices:
                                     paginazione e curve per-voce
  PGE_grain_shape_window_demo.yml    grain_shape='window': silhouette delle
                                     finestre e window_table_map

Config sintetica per i casi che nessuna config del repo esercita: gli stream di
PGE_testVoices sono sequenziali e non si sovrappongono mai, quindi lo slot
verticale resta sempre 0 e max_concurrent sempre 1. Senza la config sintetica
la rete non coprirebbe ne' il greedy degli slot, ne' la sweep line dei
simultanei, ne' la pagina vuota, ne' lo stream a cavallo del confine di pagina.

Quello che la rete NON copre, e perche': il ramo "range degenere -> 0.5" di
_normalize_envelope_value e' irraggiungibile dal path di disegno.
_compute_display_ranges somma sempre un pad strettamente positivo
(max(|v_min| * pad_ratio, 1e-6) per gli envelope costanti), quindi
max_val == min_val non si verifica mai: 410 range nella baseline, zero
degeneri. Lo esercitano solo i test che impostano _current_display_ranges a
mano. Resta un contratto da coprire nella suite unitaria — dopo l'estrazione i
range diventano un argomento, e un chiamante potra' passarne uno degenere.

Rigenerare la baseline (solo se il cambiamento e' voluto):
    PGE_UPDATE_BASELINE=1 .venv/bin/python -m pytest \\
        tests/rendering/test_score_visualizer_characterization.py -k regenerate

DA CANCELLARE a refactor completato: la copertura definitiva sono
test_page_layout.py, test_envelope_scaling.py, test_grain_visuals.py e
test_magnifier_targets.py.
"""
import json
import os
import re

import numpy as np
import pytest

import matplotlib
matplotlib.use('Agg')  # backend non-interattivo obbligatorio nei test

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CONFIG_DIR = os.path.join(REPO_ROOT, 'configs')
BASELINE_PATH = os.path.join(
    os.path.dirname(__file__), 'fixtures', 'score_visualizer_baseline.json')

REPO_CONFIGS = (
    'PGE_visualizer_envelopes_test.yml',
    'PGE_testVoices.yml',
    'PGE_grain_shape_window_demo.yml',
)

# Layout: sovrapposizioni, confini e buchi. Con page_duration=30 (default):
#   s_a/s_b/s_c   tre simultanei fra t=8 e t=10  -> sweep line e slot > 0
#   s_f           12-17, non si sovrappone a s_a -> riusa lo slot di s_a
#   s_d           20-30, finisce ESATTAMENTE sul confine di pagina -> non e'
#                 attivo nella pagina 30-60 (stream_end > page_start e' stretto)
#   s_e           25-37, a cavallo del confine -> attivo su due pagine
#   s_h/s_i       40-50 e 50-55: s_i inizia ESATTAMENTE quando s_h finisce.
#                 E' il caso che distingue `slot_end <= stream_start` da `<`
#                 (riuso dello slot) e l'ordinamento END-prima-di-START della
#                 sweep line (max_concurrent 1 e non 2). Senza questi due
#                 stream entrambe le regole restano non coperte: verificato
#                 perturbandole e vedendo la rete restare verde.
#   (buco 55-95)  la pagina 60-90 resta VUOTA
#   s_g           95-100 -> quarta pagina, durata totale non multipla di 30
LAYOUT_NAME = 'layout_edge_cases.yml'
LAYOUT_YAML = """
duration: 100

streams:
  - stream_id: "s_a"
    onset: 0
    duration: 10
    sample: voice.wav
    density: 20
    grain: {duration: 0.05, envelope: hanning}
    volume: [[0, -12], [10, -3]]
    pan: [[0, -90], [10, 90]]
    pointer: {speed_ratio: 1.0}

  - stream_id: "s_b"
    onset: 5
    duration: 10
    sample: voice.wav
    density: 15
    grain: {duration: 0.05, envelope: hanning}
    volume: -6
    pointer: {speed_ratio: [[0, 0.5], [10, 2.0]]}

  - stream_id: "s_c"
    onset: 8
    duration: 15
    sample: voice.wav
    density: 12
    grain: {duration: [[0, 0.02], [15, 0.08]], envelope: hanning}
    volume: -9
    pointer: {speed_ratio: 1.0, offset_range: [[0, 0.1], [15, 0.4]]}

  - stream_id: "s_d"
    onset: 20
    duration: 10
    sample: voice.wav
    density: 10
    grain: {duration: 0.05, envelope: hanning}
    volume: -6
    pointer: {speed_ratio: 1.0}

  - stream_id: "s_e"
    onset: 25
    duration: 12
    sample: voice.wav
    density: 10
    grain: {duration: 0.05, envelope: hanning}
    volume: [[0, -20], [12, -4]]
    pointer: {speed_ratio: 1.0}

  - stream_id: "s_f"
    onset: 12
    duration: 5
    sample: voice.wav
    density: 8
    grain: {duration: 0.05, envelope: hanning}
    volume: -6
    pointer: {speed_ratio: 1.0}

  - stream_id: "s_h"
    onset: 40
    duration: 10
    sample: voice.wav
    density: 8
    grain: {duration: 0.05, envelope: hanning}
    volume: -6
    pointer: {speed_ratio: 1.0}

  - stream_id: "s_i"
    onset: 50
    duration: 5
    sample: voice.wav
    density: 8
    grain: {duration: 0.05, envelope: hanning}
    volume: -6
    pointer: {speed_ratio: 1.0}

  - stream_id: "s_g"
    onset: 95
    duration: 5
    sample: voice.wav
    density: 8
    grain: {duration: 0.05, envelope: hanning}
    volume: -6
    pan: 45
    pointer: {speed_ratio: 1.0}
"""

CONFIG_NAMES = sorted(REPO_CONFIGS) + [LAYOUT_NAME]

# Le voice strategy stocastiche derivano l'offset da (seed, rng_id,
# voice_index): con un seed fissato lo snapshot e' riproducibile fra processi.
FIXED_SEED = 12345

SAMPLE_RATE = 48000
SAMPLE_SECONDS = 3.0

# Config del visualizer usata per lo snapshot. Accende cio' che i default
# lasciano spento (statici, offset per-voce, autozoom pitch, lente automatica),
# altrimenti quei path non verrebbero esercitati affatto.
SNAPSHOT_CONFIG = {
    'show_static_params': True,
    'show_voice_offsets': True,
    'magnify_auto': True,
    'magnify_targets': [
        {'t': 9.0, 'zoom': 6.0},                     # risolto sullo stream piu' denso
        {'t': 9.5, 'y': 1.25, 'zoom': 4.0, 'out': 0.2},
        {'t': 999.0},                                # fuori da ogni pagina: scartato
    ],
}

# Valori sonda per la normalizzazione: sotto il minimo, estremi, centro, sopra
# il massimo. Servono a congelare che il clamp esiste SOLO per pan.
PROBE_FRACTIONS = (-0.25, 0.0, 0.5, 1.0, 1.25)

# Quanti grani campionare per stream (i primi della voce 0): la geometria e'
# per-grano, bastano pochi grani per congelare la forma.
GRAINS_PER_STREAM = 3


def _round(value, digits=6):
    return round(float(value), digits)


def _vertices(points):
    return [[_round(x), _round(y)] for x, y in points]


@pytest.fixture(scope='module')
def samples_dir(tmp_path_factory):
    """Sample silenziosi in tmpdir: refs/ e' vuoto in locale (la CI genera i
    wav con sox solo nel job e2e) e la logica pura non legge l'audio, solo la
    durata del file."""
    import soundfile as sf

    directory = tmp_path_factory.mktemp('refs')
    names = {'voice.wav'}
    for config_name in REPO_CONFIGS:
        text = open(os.path.join(CONFIG_DIR, config_name)).read()
        names.update(re.findall(r'sample:\s*["\']?([\w.\-]+\.wav)', text))
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
    paths = {name: os.path.join(CONFIG_DIR, name) for name in REPO_CONFIGS}
    directory = tmp_path_factory.mktemp('configs')
    layout_path = directory / LAYOUT_NAME
    layout_path.write_text(LAYOUT_YAML)
    paths[LAYOUT_NAME] = str(layout_path)
    return paths


def _make_viz(config_path, samples_dir):
    """Generator reale + ScoreVisualizer analizzato."""
    from pge.engine.generator import Generator
    from pge.rendering.score_visualizer import ScoreVisualizer

    generator = Generator(config_path, samples_dir=samples_dir)
    generator.load_yaml()
    generator.seed = FIXED_SEED
    generator.create_elements()

    config = dict(SNAPSHOT_CONFIG)
    config['samples_dir'] = samples_dir + '/'
    viz = ScoreVisualizer(generator, config=config)
    viz.analyze()
    return viz


def _snapshot_pages(viz):
    """Paginazione, sweep line dei simultanei e slot verticali."""
    return [
        {
            'page_idx': layout['page_idx'],
            'time_range': [_round(t) for t in layout['time_range']],
            'active_streams': [s.stream_id for s in layout['active_streams']],
            'max_concurrent': layout['max_concurrent'],
            # lista di coppie, non dict: sensibile anche all'ordine
            'slot_assignments': sorted(
                [sid, slot] for sid, slot in layout['slot_assignments'].items()
            ),
        }
        for layout in viz.page_layouts
    ]


def _snapshot_lanes(viz):
    """Corsie envelope e voci di legenda, per pagina."""
    out = []
    for layout in viz.page_layouts:
        lanes, entries = viz._compute_env_legend_layout(layout['active_streams'])
        out.append({
            'page_idx': layout['page_idx'],
            'lanes': [
                {
                    'stream_id': lane['stream_id'],
                    'y_base': _round(lane['y_base']),
                    'y_height': _round(lane['y_height']),
                    'env_types': list(lane['env_types']),
                }
                for lane in lanes
            ],
            'legend_entries': [
                [name, _round(y), sid] for name, y, sid in entries
            ],
        })
    return out


def _snapshot_envelope_scaling(viz):
    """Range di display data-driven e normalizzazione dei valori sonda.

    La normalizzazione legge lo stato mutabile _current_display_ranges, che
    _draw_envelopes popola: qui lo impostiamo esplicitamente, cosi' la rete
    congela anche l'accoppiamento temporale che l'estrazione dovra' sciogliere.
    """
    out = []
    for layout in viz.page_layouts:
        t_start, t_end = layout['time_range']
        for stream in layout['active_streams']:
            envelopes = viz._get_stream_envelopes(stream)
            if not envelopes:
                continue
            ranges = viz._compute_display_ranges(
                envelopes, stream, t_start, t_end)
            viz._current_display_ranges = ranges

            probes = []
            for param_name in sorted(envelopes):
                lo, hi = ranges.get(param_name, (0.0, 1.0))
                span = hi - lo
                for fraction in PROBE_FRACTIONS:
                    value = lo + span * fraction
                    probes.append([
                        param_name,
                        fraction,
                        _round(viz._normalize_envelope_value(param_name, value)),
                    ])

            out.append({
                'page_idx': layout['page_idx'],
                'stream_id': stream.stream_id,
                'display_ranges': sorted(
                    [name, _round(lo), _round(hi)]
                    for name, (lo, hi) in ranges.items()
                ),
                'heterogeneous': sorted(
                    name for name, env in envelopes.items()
                    if viz._is_per_segment_heterogeneous(env)
                ),
                'segment_strategies': sorted(
                    [name, [viz._segment_strategy_name(s)
                            for s in getattr(env, 'segments', [])]]
                    for name, env in envelopes.items()
                ),
                'normalized_probes': probes,
            })
            viz._current_display_ranges = {}
    return out


def _sample_grains(stream):
    """I primi grani della prima voce non vuota: campione deterministico."""
    for voice_grains in stream.voices:
        if voice_grains:
            return list(voice_grains)[:GRAINS_PER_STREAM]
    return []


def _snapshot_grain_visuals(viz):
    """Vertici, colori e alpha dei grani campione, piu' il range colore pitch."""
    out = []
    for layout in viz.page_layouts:
        t_start, t_end = layout['time_range']
        cents_range = viz._compute_pitch_color_range(
            layout['active_streams'], t_start, t_end)
        page = {
            'page_idx': layout['page_idx'],
            'cents_range': (None if cents_range is None
                            else [_round(c) for c in cents_range]),
            'streams': [],
        }
        for stream in layout['active_streams']:
            grains = _sample_grains(stream)
            if not grains:
                continue
            entry = {
                'stream_id': stream.stream_id,
                'window_name_map': sorted(
                    [num, name]
                    for num, name in viz._window_name_map(stream).items()
                ),
                'grains': [],
            }
            for grain in grains:
                record = {
                    'onset': _round(grain.onset),
                    'arrow': _vertices(viz._grain_arrow_vertices(grain)),
                    'alpha': _round(viz._volume_to_alpha(grain.volume)),
                    'color': [_round(c, 4)
                              for c in viz._pitch_to_color(grain.pitch_ratio)],
                    'color_zoomed': [
                        _round(c, 4)
                        for c in viz._pitch_to_color(grain.pitch_ratio,
                                                     cents_range)
                    ],
                }
                # Silhouette della finestra: risolta dalla mappa table_num ->
                # nome, come fa _draw_grains_full con grain_shape='window'.
                name_map = viz._window_name_map(stream)
                window_name = name_map.get(
                    getattr(grain, 'envelope_table', None))
                if window_name:
                    xs, w = viz._window_silhouette(window_name, 16)
                    record['window'] = {
                        'name': window_name,
                        'vertices': _vertices(
                            viz._grain_window_vertices(grain, xs, w)),
                    }
                entry['grains'].append(record)
            page['streams'].append(entry)
        out.append(page)
    return out


def _snapshot_magnifiers(viz):
    """Target delle lenti risolti per pagina (auto + espliciti)."""
    out = []
    for layout in viz.page_layouts:
        t_start, t_end = layout['time_range']
        entries = [
            {'stream': stream,
             'sample_duration': viz._get_sample_duration(stream.sample)}
            for stream in layout['active_streams']
        ]
        resolved = viz._resolve_magnify_targets(t_start, t_end, entries)
        densest = viz._densest_stream_entry(t_start, t_end, entries)
        out.append({
            'page_idx': layout['page_idx'],
            'targets': [
                {
                    'stream_id': r['entry']['stream'].stream_id,
                    't': _round(r['t']),
                    'y': _round(r['y']),
                    'zoom': _round(r['zoom']),
                    'out': _round(r['out']),
                    # src=None e' il default significativo ("out/zoom"), non un
                    # valore mancante: va congelato com'e'.
                    'src': None if r['src'] is None else _round(r['src']),
                    'corner': r['corner'],
                }
                for r in resolved
            ],
            'densest': None if densest is None else densest['stream'].stream_id,
        })
    return out


def _snapshot(config_path, samples_dir):
    viz = _make_viz(config_path, samples_dir)
    return {
        'pages': _snapshot_pages(viz),
        'lanes': _snapshot_lanes(viz),
        'envelope_scaling': _snapshot_envelope_scaling(viz),
        'grain_visuals': _snapshot_grain_visuals(viz),
        'magnifiers': _snapshot_magnifiers(viz),
    }


def _load_baseline():
    if not os.path.exists(BASELINE_PATH):
        pytest.fail(
            f"baseline assente: {BASELINE_PATH}\n"
            "Rigenerala con: PGE_UPDATE_BASELINE=1 .venv/bin/python -m pytest "
            f"{os.path.relpath(__file__, REPO_ROOT)} -k regenerate"
        )
    with open(BASELINE_PATH) as handle:
        return json.load(handle)


# =============================================================================
# LA RETE
# =============================================================================

@pytest.mark.parametrize('config_name', CONFIG_NAMES)
def test_pure_logic_matches_baseline(config_name, config_paths, samples_dir):
    """I numeri calcolati su config reali sono identici alla baseline."""
    baseline = _load_baseline()
    assert config_name in baseline, (
        f"'{config_name}' non e' nella baseline: rigenerala")
    actual = _snapshot(config_paths[config_name], samples_dir)
    for section in sorted(actual):
        assert actual[section] == baseline[config_name][section], (
            f"divergenza nella sezione '{section}' di {config_name}")


def test_baseline_covers_slot_reuse_and_concurrency(config_paths, samples_dir):
    """Il greedy degli slot e la sweep line sono davvero esercitati.

    Le config del repo hanno stream sequenziali: senza la config sintetica ogni
    stream finirebbe nello slot 0 con max_concurrent 1, e un refactor potrebbe
    rompere l'assegnazione restando verde.
    """
    pages = _snapshot(config_paths[LAYOUT_NAME], samples_dir)['pages']
    first = pages[0]

    assert first['max_concurrent'] >= 3, (
        "nessuna pagina con tre stream simultanei")
    slots = dict(first['slot_assignments'])
    assert max(slots.values()) >= 2, "nessuno slot oltre il primo assegnato"
    # s_f (12-17) non si sovrappone a s_a (0-10): deve riusarne lo slot.
    assert slots['s_f'] == slots['s_a'], "slot non riusato da stream disgiunti"

    # Contatto esatto: s_i (50-55) inizia quando s_h (40-50) finisce.
    second = dict(pages[1]['slot_assignments'])
    assert second['s_i'] == second['s_h'], (
        "slot non riusato al contatto esatto: `slot_end <= stream_start` "
        "e' degradato a `<`")
    assert pages[1]['max_concurrent'] == 1, (
        "il contatto esatto conta come due simultanei: la sweep line non "
        "ordina END prima di START")


def test_baseline_covers_page_boundaries_and_gaps(config_paths, samples_dir):
    """Confine di pagina stretto, stream a cavallo e pagina vuota."""
    pages = _snapshot(config_paths[LAYOUT_NAME], samples_dir)['pages']
    by_idx = {p['page_idx']: p for p in pages}

    assert len(pages) == 4, "la durata non multipla non produce 4 pagine"
    # s_d finisce esattamente a 30: non e' attivo nella pagina che inizia a 30.
    assert 's_d' in by_idx[0]['active_streams']
    assert 's_d' not in by_idx[1]['active_streams'], (
        "confine di pagina non stretto: stream_end > page_start")
    # s_e (25-37) sta a cavallo.
    assert 's_e' in by_idx[0]['active_streams']
    assert 's_e' in by_idx[1]['active_streams']
    # il buco 37-95 lascia vuota la pagina 60-90.
    assert by_idx[2]['active_streams'] == [], "nessuna pagina vuota nella rete"
    assert by_idx[2]['max_concurrent'] == 0


def test_baseline_covers_every_pure_path(config_paths, samples_dir):
    """Ogni cluster puro compare davvero nella baseline.

    Senza questo, una baseline che copre solo la paginazione passerebbe verde
    mentre il refactor rompe la geometria dei grani o le lenti.
    """
    snapshots = {
        name: _snapshot(config_paths[name], samples_dir)
        for name in CONFIG_NAMES
    }

    # Corsie e legenda
    assert any(page['lanes'] for snap in snapshots.values()
               for page in snap['lanes']), "nessuna corsia envelope"
    assert any(page['legend_entries'] for snap in snapshots.values()
               for page in snap['lanes']), "nessuna voce di legenda"

    # Range di display e normalizzazione
    scaling = [row for snap in snapshots.values()
               for row in snap['envelope_scaling']]
    assert scaling, "nessun range di display"
    assert any(row['display_ranges'] for row in scaling)
    # pan e' l'unico clampato: la sonda a 1.25 deve restare <= 1.
    pan_probes = [p for row in scaling for p in row['normalized_probes']
                  if p[0] == 'pan']
    assert pan_probes, "pan non esercitato: il clamp ciclico non e' coperto"
    assert all(p[2] <= 1.0 for p in pan_probes if p[1] == 1.25)
    # gli altri no: almeno una sonda sopra il massimo deve uscire da [0,1].
    assert any(p[2] > 1.0 for row in scaling for p in row['normalized_probes']
               if p[0] != 'pan' and p[1] == 1.25), (
        "nessun parametro non-pan fuori da [0,1]: il 'niente clamp' non e' coperto")

    # Geometria dei grani
    grains = [g for snap in snapshots.values() for page in snap['grain_visuals']
              for entry in page['streams'] for g in entry['grains']]
    assert grains, "nessun grano campionato"
    assert all(len(g['arrow']) == 5 for g in grains)
    assert any('window' in g for g in grains), (
        "nessuna silhouette di finestra: grain_shape='window' non coperto")
    # autozoom pitch: almeno una pagina deve produrre un range in cents.
    assert any(page['cents_range'] is not None for snap in snapshots.values()
               for page in snap['grain_visuals']), "autozoom pitch non coperto"

    # Lenti
    targets = [t for snap in snapshots.values() for page in snap['magnifiers']
               for t in page['targets']]
    assert targets, "nessun target di lente risolto"
    assert any(t['zoom'] == 6.0 for t in targets), "target esplicito non risolto"


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
