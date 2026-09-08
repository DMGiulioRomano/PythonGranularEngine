# =============================================================================
# API programmatica del granular engine (Fase 1 refactor library/CLI).
#
# Contratto del modulo
# (docs/plans/done/2026-07-08-001-refactor-pge-library-cli-plan.md, sez. B.1):
# - nessun sys.exit, nessuna lettura di sys.argv;
# - errori -> eccezioni (EngineError e sottoclassi; ValueError per argomenti
#   API invalidi). Dalla #257 anche il file YAML che manca o non si parsa e'
#   un EngineError (ConfigFileNotFoundError, ConfigParseError,
#   ConfigReadError), che pero' eredita il builtin di prima per non rompere
#   chi lo cattura;
# - import lazy dei moduli pesanti dentro le funzioni (stesso stile di
#   main.py): mantiene mockabile via sys.modules e non paga matplotlib
#   all'import;
# - ogni default filesystem e' un parametro esplicito overridabile.
#
# Stdout: questo modulo non stampa -- nessuna funzione qui sotto contiene un
# print() -- ma la libreria NON e' silenziosa, e la differenza conta per chi
# la incorpora. Le funzioni orchestrano Generator, i renderer e
# ScoreVisualizer, e sono quei componenti a scrivere su stdout mentre
# lavorano. Il piano diceva "non stampa (nel proprio modulo)"; la parentesi
# si era persa strada facendo, e senza di essa la dichiarazione prometteva un
# silenzio che non c'e' mai stato (issue #189).
#
# --- righe su stdout (censimento verificato da tests/test_api_stdout.py) ---
#
#   da load_generator(), tutte da Generator:
#     `[SEED]`              create_elements, quando lo YAML non ha `seed:`
#     `🔇`                  _filter_solo_mute, quanti stream sono muted
#     `⚡ SOLO MODE`        _filter_solo_mute, in modalita' solo
#     `Creazione di`        _create_streams, quanti stream sta costruendo
#     `  → Stream`          _create_streams, una riga per stream
#     `⚠️  Warning: impossibile valutare`  espressione matematica nello YAML
#
#   da render(), solo con `cache_manifest_path` (senza manifest non c'e'
#   nessuna riga di cache):
#     `[CACHE]`             il renderer, DIRTY/clean per stream
#
#   da render(renderer='csound'), da ScoreWriter mentre scrive il .sco:
#     `✓ Score generato`    il path del .sco
#     `  - `                tre righe di riepilogo (tables, stream, grani)
#
#   da export_score_pdf(), da ScoreVisualizer:
#     `Analisi completata`  pagine e durata totale
#     `  Rendering pagina`  una riga per pagina
#     `Esportazione PDF`    inizio esportazione
#     `✓ PDF esportato`     fine esportazione
#     `⚠️  Impossibile caricare waveform`  sample illeggibile per la partitura
#
#   alla prima inizializzazione del clip logger, da qualunque percorso che
#   costruisca envelope (load_generator, render, export_score_pdf):
#     `📝 Clip log file`    il path del log, che il logger crea in ./logs
#
# --- fine censimento ---
#
# Perche' restano: fanno parte del contratto stdout della CLI, e almeno una
# e' interfaccia vera. `[CACHE] <id>: DIRTY|clean` la parsa PGE-ui
# (render_pipeline.py, _RE_CACHE_LINE) per costruirne gli eventi NDJSON
# `stream-start`/`stream-done`: spostarla al logger rompe l'avanzamento per
# stream nell'editor dell'altro repo. Le altre nessuno le parsa, per quanto
# se ne sa -- ma "per quanto se ne sa" e' esattamente cio' che la issue #178
# deve accertare (protocollo / diagnostica / interfaccia CLI) prima che le
# #187/#188 le portino al logger. Quando succedera', il censimento qui sopra
# va aggiornato: il test lo verifica in entrambe le direzioni (nessuna riga
# fuori elenco, nessuna voce in elenco che nessuno emette piu').
#
# --- e stderr, che il censimento qui sopra non copre ---
#
# L'elenco e' di stdout, e dirlo per intero fa parte del punto: letto come
# inventario completo rifarebbe l'errore della #189 un piano sotto. Sullo
# stderr scrivono gli avvisi del clip logger, da qualunque percorso che
# costruisca envelope:
#     `⚠️  CLIP: ...`   l'handler console del clip logger (attivo di default)
#     `CLIP: ...`       log_loop_unit_migration_warning, che stampa proprio
#                       quando la console del clip logger e' spenta (#222):
#                       spegnerla non zittisce quell'avviso, lo sposta
#
# Chi incorpora e ha bisogno di silenzio: contextlib.redirect_stdout NON
# basta -- copre l'elenco qui sopra e nient'altro. Servono anche
# redirect_stderr (da entrare PRIMA che il clip logger si costruisca:
# logging.StreamHandler() cattura sys.stderr alla costruzione, non alla
# scrittura) oppure configure_clip_logger(console_enabled=False), tenendo
# conto che l'avviso #222 resta. E configure_clip_logger /
# configure_engine_logger vanno chiamate PRIMA di load_generator --
# altrimenti il primo Stream inizializza il clip logger coi default di
# modulo, che scrivono in ./logs (docs/how-to/use-as-library.md).
#
# Divisione delle policy: l'API sceglie default deterministici e senza
# dipendenze esterne (jobs=1, renderer='numpy', path manifest esplicito);
# messaggi utente, derivazione dei nomi file e policy 'auto' restano in
# main.py.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from pge.shared.constants import DEFAULT_OUTPUT_SR
from pge.rendering.audio_format import DEFAULT_FORMAT, FORMATS
# Value Object leggero (dataclass frozen, nessuna dipendenza pesante):
# re-export a livello di modulo cosi' i consumer di parameter_bounds()
# tipizzano il risultato senza importare pge.parameters.
from pge.parameters.parameter_definitions import ParameterBounds  # noqa: F401


@dataclass(frozen=True)
class CsoundOptions:
    """Opzioni renderer Csound. I default replicano quelli odierni della CLI."""
    orc_path: str = 'csound/main.orc'
    incdir: str = 'src'
    ssdir: Optional[str] = None        # None -> samples dir di default ('refs')
    sfdir: str = 'output'
    log_dir: str = 'logs'
    message_level: int = 134
    sco_dir: Optional[str] = None      # None -> .sco temporanei (--keep-sco off)


@dataclass(frozen=True)
class SuperColliderOptions:
    """Opzioni renderer SuperCollider (issue #228).

    `synthdef_source` e' il sorgente .scd della SynthDef del grano --
    l'omologo di `orc_path` per Csound -- e `synthdef_dir` la directory dove
    sta (o viene scritto) il .scsyndef compilato, che e' un artefatto di
    build: sclang gira solo quando manca o quando il sorgente e' piu'
    recente, il rendering vero invoca solo scsynth.

    Tutti i default sono `None` = "il default del renderer", e i valori veri
    vivono in un posto solo (le costanti DEFAULT_* di
    supercollider_renderer). Ricopiarli qui e nella CLI faceva quattro valori
    in cinque posti, e tre default della stessa cosa che divergono sono tre
    comportamenti diversi a seconda di come si entra.
    """
    synthdef_source: Optional[str] = None   # -> DEFAULT_SYNTHDEF_SOURCE
    synthdef_dir: Optional[str] = None      # -> DEFAULT_SYNTHDEF_DIR (fuori da GENDIR)
    scsynth_bin: Optional[str] = None       # -> 'scsynth' dal PATH
    sclang_bin: Optional[str] = None        # -> 'sclang' dal PATH
    block_size: Optional[int] = None        # -> DEFAULT_BLOCK_SIZE (1, come ksmps=1)
    max_nodes: Optional[int] = None         # -> DEFAULT_MAX_NODES
    timeout: Optional[float] = None         # -> DEFAULT_TIMEOUT_SEC
    osc_dir: Optional[str] = None           # None -> .osc temporanei (--keep-osc off)


@dataclass(frozen=True)
class StreamGrainCount:
    """Quanti grani ha materializzato uno stream, e su quante voci (#250).

    Non e' uno stato mantenuto da nessuno: e' il risultato di una lettura di
    `voices` fatta a render finito. `voices` resta l'unica fonte di verita'
    (#201) e questo Value Object solo la fotografa.
    """
    grains: int
    voices: int


@dataclass
class RenderResult:
    """Esito di un render: tutto cio' che serve alla CLI per i suoi print."""
    audio_paths: List[str]             # 1 file in MIX, N in STEMS
    elapsed_seconds: float             # durata della sola engine.render
    renderer_type: str                 # 'numpy' | 'csound' | 'supercollider'
    per_stream: bool
    jobs: Optional[int] = None         # jobs risolti (renderer.jobs); None per csound
    cache_manifest_path: Optional[str] = None
    gc_removed: List[str] = field(default_factory=list)  # stream orfani rimossi dal GC
    # Una voce per stream, nell'ordine di generator.streams; None = stream non
    # materializzato (saltato dalla cache), non "zero grani" (issue #250).
    grain_counts: Dict[str, Optional[StreamGrainCount]] = field(default_factory=dict)


def parameter_bounds(
    *,
    output_sr: Optional[int] = None,
    sample_dur_sec: Optional[float] = None,
):
    """Bounds di tutti i parametri registrati (issue #163).

    Ritorna un dict nuovo {nome: ParameterBounds} costruito dal registry
    GRANULAR_PARAMETERS via get_parameter_definition, cosi' i consumer
    esterni non importano il modulo interno parameter_definitions.

    Args:
        output_sr: sample rate di render; se fornito, grain_duration.min_val
            diventa 1 campione (1/output_sr).
        sample_dur_sec: durata del file audio in secondi; se fornita,
            max_val di loop_dur/loop_start/loop_end diventa la durata.

    Raises:
        ValueError: se output_sr o sample_dur_sec non sono positivi.
    """
    if output_sr is not None and output_sr <= 0:
        raise ValueError(
            f"output_sr deve essere positivo, ricevuto: {output_sr!r}")
    if sample_dur_sec is not None and sample_dur_sec <= 0:
        raise ValueError(
            f"sample_dur_sec deve essere positivo, ricevuto: {sample_dur_sec!r}")

    from pge.parameters.parameter_definitions import (
        GRANULAR_PARAMETERS,
        get_parameter_definition,
    )

    return {
        name: get_parameter_definition(
            name, sample_dur_sec=sample_dur_sec, output_sr=output_sr)
        for name in GRANULAR_PARAMETERS
    }


def renderer_types() -> List[str]:
    """Tipi di renderer accettati da build_renderer, ordinati.

    Passa da RendererFactory invece di tenerne una copia: e' cosi' che un
    backend nuovo diventa visibile a tutti i chiamanti -- CLI, editor,
    language server -- senza che ognuno aggiorni il proprio elenco.
    """
    from pge.rendering.renderer_factory import RendererFactory
    return list(RendererFactory.available_types())


def load_generator(yaml_path: str, *, samples_dir: Optional[str] = None):
    """Generator(yaml) + load_yaml() + create_elements().

    Args:
        samples_dir: directory dei sample audio; None -> default storico
            ('./refs/', via fallback PATHSAMPLES). Quando None la chiamata
            resta Generator(yaml): compatibile con firme Generator
            precedenti (submodule non ancora aggiornati).

    Raises:
        EngineError e sottoclassi -- fra cui ConfigFileNotFoundError (YAML
        inesistente), ConfigParseError (YAML malformato o non decodificabile)
        e ConfigReadError (il file c'e' ma il sistema operativo non lo apre:
        una directory al posto del file, permessi negati), che dalla #257
        sostituiscono i builtin nudi che questa docstring dichiarava. Tutte e
        tre ereditano il tipo che sostituiscono (FileNotFoundError,
        yaml.YAMLError, OSError): un `except FileNotFoundError` scritto contro
        le versioni precedenti continua a funzionare. E anche il tipo
        *concreto* della causa, quando ne ha uno: una directory al posto del
        file resta un IsADirectoryError, uno YAML con posizione resta un
        yaml.MarkedYAMLError, un file non decodificabile resta un
        UnicodeDecodeError -- e' cio' che saliva prima, e chi lo cattura per
        nome non deve cambiare niente. Restano anche SampleNotFoundError,
        ConfigError, ... Nessun print proprio (quelli interni di Generator
        restano).
    """
    from pge.engine.generator import Generator

    if samples_dir is not None:
        generator = Generator(yaml_path, samples_dir=samples_dir)
    else:
        generator = Generator(yaml_path)
    generator.load_yaml()
    generator.create_elements()
    return generator


def _with_trailing_sep(samples_dir):
    """Garantisce il separatore finale dove serve la concatenazione
    base + filename (SampleRegistry, config del visualizer)."""
    import os
    if samples_dir and not samples_dir.endswith(('/', os.sep)):
        return samples_dir + '/'
    return samples_dir


def _make_cache_manager(cache_manifest_path: Optional[str],
                        samples_dir: Optional[str] = None,
                        renderer_type: Optional[str] = None):
    """StreamCacheManager sul manifest esplicito; None = cache disattiva.

    `samples_dir` serve al fingerprint degli stream senza `duration` (#205),
    che risolve la durata dal file audio: senza, la risoluzione userebbe
    PATHSAMPLES anche quando i sample stanno altrove. `renderer_type` ci
    entra per lo stesso motivo (#228): lo stem dipende dal backend che lo
    rende, e il testo YAML non lo dice.
    """
    if cache_manifest_path is None:
        return None
    from pge.rendering.stream_cache_manager import StreamCacheManager
    return StreamCacheManager(cache_path=cache_manifest_path,
                              samples_dir=samples_dir,
                              renderer_type=renderer_type)


def build_renderer(
    renderer_type: str,                          # 'numpy' | 'csound' | 'supercollider'
    generator,
    *,
    output_sr: int = DEFAULT_OUTPUT_SR,
    jobs: Union[int, str] = 1,                   # 1 = default API; 'auto' e' policy CLI
    audio_format=DEFAULT_FORMAT,
    samples_dir: Optional[str] = None,           # -> SampleRegistry(base_path=...)/SSDIR
    cache_manifest_path: Optional[str] = None,   # None = cache disattiva
    csound: Optional[CsoundOptions] = None,      # None -> CsoundOptions() se serve
    supercollider: Optional[SuperColliderOptions] = None,  # idem
):
    """Compone l'AudioRenderer per il generator dato.

    Estrazione 1:1 di main._build_renderer, senza print: il path del
    manifest e' esplicito (la CLI lo compone da cache_dir+basename e lo
    stampa lei).

    Raises:
        InvalidRendererError: se renderer_type non e' supportato.
    """
    from pge.rendering.renderer_factory import RendererFactory

    if renderer_type == 'numpy':
        from pge.rendering.sample_registry import SampleRegistry
        from pge.rendering.numpy_window_registry import NumpyWindowRegistry

        table_map = generator.ftable_manager.get_all_tables()
        if samples_dir is not None:
            sample_reg = SampleRegistry(base_path=_with_trailing_sep(samples_dir))
        else:
            sample_reg = SampleRegistry()
        window_reg = NumpyWindowRegistry()

        for _, (ftype, name) in table_map.items():
            if ftype == 'sample':
                sample_reg.load(name)

        return RendererFactory.create(
            'numpy',
            sample_registry=sample_reg,
            window_registry=window_reg,
            table_map=table_map,
            output_sr=output_sr,
            cache_manager=_make_cache_manager(cache_manifest_path, samples_dir,
                                              renderer_type),
            stream_data_map=generator.stream_data_map,
            audio_format=audio_format,
            jobs=jobs,
        )

    if renderer_type == 'csound':
        opts = csound if csound is not None else CsoundOptions()
        # SSDIR: opzione esplicita > samples_dir (senza slash finale,
        # convenzione csound) > default storico 'refs'
        if opts.ssdir is not None:
            ssdir = opts.ssdir
        elif samples_dir is not None:
            ssdir = samples_dir.rstrip('/')
        else:
            ssdir = 'refs'
        csound_config = {
            'orc_path': opts.orc_path,
            'env_vars': {
                'INCDIR': opts.incdir,
                'SSDIR': ssdir,
                'SFDIR': opts.sfdir,
            },
            'log_dir': opts.log_dir,
            'message_level': opts.message_level,
        }

        return RendererFactory.create(
            'csound',
            score_writer=generator.score_writer,
            csound_config=csound_config,
            cache_manager=_make_cache_manager(cache_manifest_path, samples_dir,
                                              renderer_type),
            stream_data_map=generator.stream_data_map,
            sco_dir=opts.sco_dir,
        )

    if renderer_type == 'supercollider':
        opts = supercollider if supercollider is not None else SuperColliderOptions()
        from pge.rendering.numpy_window_registry import NumpyWindowRegistry

        # Nessun SampleRegistry: i sample li apre scsynth. Caricarli anche
        # qui sarebbe il doppio della RAM per un dato che non usiamo -- la
        # asimmetria col ramo numpy e' voluta.
        return RendererFactory.create(
            'supercollider',
            table_map=generator.ftable_manager.get_all_tables(),
            window_registry=NumpyWindowRegistry(),
            samples_dir=_with_trailing_sep(samples_dir) or './refs/',
            output_sr=output_sr,
            audio_format=audio_format,
            # Le chiavi None non entrano: il default e' quello del
            # renderer, che e' l'unico posto dove i valori sono scritti.
            sc_config={
                k: v for k, v in {
                    'synthdef_source': opts.synthdef_source,
                    'synthdef_dir': opts.synthdef_dir,
                    'scsynth_bin': opts.scsynth_bin,
                    'sclang_bin': opts.sclang_bin,
                    'block_size': opts.block_size,
                    'max_nodes': opts.max_nodes,
                    'timeout': opts.timeout,
                }.items() if v is not None
            },
            cache_manager=_make_cache_manager(cache_manifest_path, samples_dir,
                                              renderer_type),
            stream_data_map=generator.stream_data_map,
            osc_dir=opts.osc_dir,
        )

    from pge.shared.exceptions import InvalidRendererError
    raise InvalidRendererError(
        renderer_type=renderer_type,
        available=renderer_types(),
    )


def collect_cache_orphans(
    generator,
    renderer,
    output_path: str,
    *,
    audio_format=DEFAULT_FORMAT,
) -> List[str]:
    """GC del manifest cache: rimuove stream orfani (rimossi/rinominati
    nel YAML).

    Usa TUTTI gli stream_id di generator.data (solo/mute non rende orfani
    gli esclusi), aif_dir = dirname(output_path), prefix = basename del
    riferimento yaml. No-op ([]) se renderer.cache_manager e' None.
    """
    import os

    cache_manager = getattr(renderer, 'cache_manager', None)
    if cache_manager is None:
        return []

    all_stream_dicts = (generator.data or {}).get('streams', [])
    current_ids = [
        s['stream_id'] for s in all_stream_dicts if 'stream_id' in s
    ]
    aif_prefix = os.path.splitext(os.path.basename(generator.yaml_path))[0]
    return cache_manager.garbage_collect(
        current_stream_ids=current_ids,
        aif_dir=os.path.dirname(os.path.abspath(output_path)),
        aif_prefix=aif_prefix,
        ext=audio_format.extension,
    )


def collect_grain_counts(
    generator,
) -> Dict[str, Optional[StreamGrainCount]]:
    """Quanti grani ha generato ogni stream: lettura PASSIVA, a valle
    (issue #250).

    Va chiamata DOPO il rendering, ed e' quello che la rende gratis: legge
    `voices` solo sugli stream che il render ha gia' materializzato
    (`generated` True), quindi costa O(voci) e non O(grani). Sugli altri non
    tocca `.voices`, che e' lazy (#117): leggerla li' rigenererebbe in fase di
    stampa esattamente i grani che la cache aveva fatto risparmiare -- ed e'
    il motivo per cui il conteggio non puo' tornare nel `__repr__` di Stream,
    che `Generator._create_streams` stampa a costruzione.

    Stesso schema di export_grain_json, stesso punto della pipeline. Ogni
    stream compare nella mappa: `None` per chi non e' materializzato, cosi'
    chi stampa non deve tornare a interrogare `generator.streams` per sapere
    chi manca.
    """
    counts: Dict[str, Optional[StreamGrainCount]] = {}
    for stream in generator.streams:
        # getattr: uno stream duck-typed di un consumer esterno che non
        # dichiara `generated` va assunto non materializzato -- la direzione
        # sicura, quella che non innesca niente.
        if not getattr(stream, 'generated', False):
            counts[stream.stream_id] = None
            continue
        voices = stream.voices
        counts[stream.stream_id] = StreamGrainCount(
            grains=sum(len(v) for v in voices),
            voices=len(voices),
        )
    return counts


def render(
    generator,
    output_path: str,
    *,
    renderer='numpy',                            # str | AudioRenderer
    per_stream: bool = False,
    audio_format=DEFAULT_FORMAT,
    run_cache_gc: bool = True,                   # GC prima del render (STEMS+cache)
    # forward a build_renderer quando renderer e' una stringa:
    output_sr: int = DEFAULT_OUTPUT_SR,
    jobs: Union[int, str] = 1,
    samples_dir: Optional[str] = None,
    cache_manifest_path: Optional[str] = None,
    csound: Optional[CsoundOptions] = None,
    supercollider: Optional[SuperColliderOptions] = None,
) -> RenderResult:
    """Renderizza gli stream del generator in output_path, cronometrato.

    `renderer` accetta un'istanza gia' costruita (escape hatch: la CLI la
    costruisce prima per poter stampare jobs/manifest) oppure il tipo come
    stringa, nel qual caso viene composta via build_renderer.
    """
    import time

    if isinstance(renderer, str):
        renderer_type = renderer
        renderer_obj = build_renderer(
            renderer, generator,
            output_sr=output_sr,
            jobs=jobs,
            audio_format=audio_format,
            samples_dir=samples_dir,
            cache_manifest_path=cache_manifest_path,
            csound=csound,
            supercollider=supercollider,
        )
    else:
        renderer_obj = renderer
        # I renderer del progetto dichiarano `renderer_type` come attributo
        # di classe (AudioRenderer); per istanze esterne che non lo fanno il
        # campo informativo resta 'unknown', niente etichette inventate.
        declared = getattr(renderer_obj, 'renderer_type', None)
        renderer_type = declared if isinstance(declared, str) else 'unknown'

    gc_removed: List[str] = []
    if run_cache_gc and per_stream:
        gc_removed = collect_cache_orphans(
            generator, renderer_obj, output_path, audio_format=audio_format)

    from pge.rendering.rendering_engine import RenderingEngine
    from pge.rendering.render_mode import StemsRenderMode, MixRenderMode
    from pge.rendering.naming_strategy import DefaultNamingStrategy

    engine = RenderingEngine(
        renderer_obj,
        naming_strategy=DefaultNamingStrategy(ext=audio_format.extension),
    )
    mode = StemsRenderMode() if per_stream else MixRenderMode()

    t0 = time.perf_counter()
    generated = engine.render(
        streams=generator.streams,
        output_path=output_path,
        mode=mode,
    )
    elapsed = time.perf_counter() - t0

    return RenderResult(
        audio_paths=list(generated),
        elapsed_seconds=elapsed,
        renderer_type=renderer_type,
        per_stream=per_stream,
        jobs=getattr(renderer_obj, 'jobs', None),
        cache_manifest_path=cache_manifest_path,
        gc_removed=gc_removed,
        # Dopo engine.render: a quel punto i grani degli stream dirty sono
        # materializzati nel processo padre (anche con jobs > 1: i task del
        # pool si costruiscono qui), quindi la lettura non genera nulla.
        grain_counts=collect_grain_counts(generator),
    )


def render_file(
    yaml_path: str,
    output_path: str,
    *,
    renderer: str = 'numpy',
    per_stream: bool = False,
    run_cache_gc: bool = True,
    output_sr: int = DEFAULT_OUTPUT_SR,
    jobs: Union[int, str] = 1,
    audio_format=DEFAULT_FORMAT,                 # AudioFormat | str (lookup FORMATS)
    samples_dir: Optional[str] = None,
    cache_manifest_path: Optional[str] = None,
    csound: Optional[CsoundOptions] = None,
    supercollider: Optional[SuperColliderOptions] = None,
) -> RenderResult:
    """One-shot YAML -> audio: load_generator + render.

    `audio_format` come stringa viene risolto via FORMATS; una stringa
    ignota solleva ValueError con l'elenco dei formati validi.
    `run_cache_gc=False` disattiva il GC degli stem orfani in STEMS+cache
    (il GC cancella file: il chiamante deve poterlo rifiutare anche dalla
    one-shot API).
    """
    if isinstance(audio_format, str):
        if audio_format not in FORMATS:
            raise ValueError(
                f"Formato audio non supportato: {audio_format!r}. "
                f"Validi: {', '.join(sorted(FORMATS))}."
            )
        audio_format = FORMATS[audio_format]

    generator = load_generator(yaml_path, samples_dir=samples_dir)
    return render(
        generator,
        output_path,
        renderer=renderer,
        per_stream=per_stream,
        run_cache_gc=run_cache_gc,
        audio_format=audio_format,
        output_sr=output_sr,
        jobs=jobs,
        samples_dir=samples_dir,
        cache_manifest_path=cache_manifest_path,
        csound=csound,
        supercollider=supercollider,
    )


def export_score_pdf(
    generator,
    pdf_path: str,
    *,
    config: Optional[dict] = None,     # merge sui default equivalenti alla CLI
    samples_dir: Optional[str] = None, # -> config['samples_dir'] del visualizer
) -> str:
    """Esporta la partitura grafica in PDF; ritorna pdf_path.

    I default di config sono identici a quelli della CLI (main.py).
    samples_dir, se dato, entra come chiave config del visualizer (il cui
    default None mantiene il fallback storico su PATHSAMPLES).
    """
    merged = {
        'page_duration': 15.0,
        'show_static_params': False,
        'show_voice_offsets': False,
        'envelope_filter': None,
        'magnify_auto': False,
        'magnify_targets': [],
        'grain_height': 'duration',
        'bw': False,
    }
    if config:
        merged.update(config)
    if samples_dir is not None:
        merged['samples_dir'] = _with_trailing_sep(samples_dir)

    from pge.rendering.score_visualizer import ScoreVisualizer

    viz = ScoreVisualizer(generator, config=merged)
    viz.export_pdf(pdf_path)
    return pdf_path


def export_reaper(
    generator,
    audio_paths: List[str],
    output_path: str,
) -> str:
    """Scrive il progetto Reaper (.rpp); ritorna output_path.

    Replica del blocco --reaper della CLI incluso il padding MIX: se
    len(audio_paths) != len(streams), ogni TRACK punta al mix
    (audio_paths[0]) con onset/duration del proprio stream.
    """
    from pge.export.reaper_project_writer import ReaperProjectWriter

    n = len(generator.streams)
    aif_paths = (
        audio_paths if len(audio_paths) == n else [audio_paths[0]] * n
    )
    ReaperProjectWriter().write(
        streams=generator.streams,
        aif_paths=aif_paths,
        output_path=output_path,
    )
    return output_path


def export_sv(
    generator,
    audio_path: str,
    output_path: str,
    *,
    layout: str = 'multi',
) -> str:
    """Esporta una sessione Sonic Visualiser (.sv); ritorna output_path.

    Solo MIX: la policy 'ignora in STEMS' resta nella CLI (e' un
    messaggio utente).
    """
    from pge.export.sv_exporter import SVExporter

    SVExporter().export(
        generator.streams,
        audio_path=audio_path,
        out_path=output_path,
        layout=layout,
    )
    return output_path


def export_grain_json(
    generator,
    output_dir: str,
    base_name: str,
) -> List[str]:
    """Scrive il grain JSON per i soli stream con .generated True
    (generazione lazy, issue #117). Ritorna i path scritti."""
    from pge.export.grain_json_writer import GrainJsonWriter

    writer = GrainJsonWriter()
    paths = []
    for stream in generator.streams:
        if not stream.generated:
            continue
        paths.append(writer.write(stream, output_dir, base_name))
    return paths
