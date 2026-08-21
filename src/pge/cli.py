# =============================================================================
# MAIN
# =============================================================================

from __future__ import annotations

import traceback

from pge.shared.logger import (
    configure_clip_logger, get_clip_log_path,
    configure_engine_logger, get_engine_logger, get_engine_log_path,
)
from pge.shared.exceptions import EngineError
from pge.shared.constants import DEFAULT_OUTPUT_SR
from pge.engine.generator import Generator
from pge.rendering.score_visualizer import ScoreVisualizer, PLOT_ENVELOPE_KEYS

from pge import api


def _handle_engine_error(err: EngineError) -> None:
    """Stampa user_message su stdout e persiste traceback nel file engine log."""
    log_path = get_engine_log_path()
    print(err.user_message())
    if log_path:
        print(f"  Dettagli:     {log_path}")
    logger = get_engine_logger()
    logger.error("%s\n%s", err, traceback.format_exc())


def _build_renderer(renderer_type: str, generator, **kwargs):
    """
    Crea il renderer appropriato in base al tipo, delegando ad api.build_renderer.

    Adapter CLI -> API (Fase 1 refactor library/CLI): mappa i kwargs storici
    della CLI (use_cache/cache_dir/yaml_basename, orc_path/incdir/...) sulla
    firma keyword-only dell'API e conserva qui il print `[CACHE] Manifest:`
    (i print sono policy CLI, l'API non stampa).

    Args:
        renderer_type: 'csound' o 'numpy'
        generator: istanza di Generator con streams gia' creati
        **kwargs: argomenti specifici per ogni renderer

    Returns:
        Istanza di AudioRenderer configurata

    Raises:
        InvalidRendererError: se renderer_type non e' supportato
    """
    from pge.rendering.audio_format import DEFAULT_FORMAT

    # Il print del manifest avveniva dentro i rami numpy/csound: per un tipo
    # ignoto l'errore arrivava senza print. Parita' preservata col guard.
    cache_manifest_path = None
    if renderer_type in ('numpy', 'csound') and kwargs.get('use_cache'):
        import os as _os
        yaml_basename = kwargs['yaml_basename']
        cache_dir = kwargs.get('cache_dir', 'cache')
        cache_manifest_path = _os.path.join(cache_dir, f"{yaml_basename}.json")
        print(f"[CACHE] Manifest: {cache_manifest_path}")

    csound_options = None
    if renderer_type == 'csound':
        csound_options = api.CsoundOptions(
            orc_path=kwargs.get('orc_path', 'csound/main.orc'),
            incdir=kwargs.get('incdir', 'src'),
            ssdir=kwargs.get('ssdir', 'refs'),
            sfdir=kwargs.get('sfdir', 'output'),
            log_dir=kwargs.get('log_dir', 'logs'),
            message_level=kwargs.get('message_level', 134),
            sco_dir=kwargs.get('sco_dir'),
        )

    return api.build_renderer(
        renderer_type,
        generator,
        output_sr=kwargs.get('output_sr', DEFAULT_OUTPUT_SR),
        jobs=kwargs.get('jobs', 'auto'),
        audio_format=kwargs.get('audio_format', DEFAULT_FORMAT),
        cache_manifest_path=cache_manifest_path,
        csound=csound_options,
    )


def _parse_jobs(argv):
    """Parsa --jobs per il rendering NumPy multi-processo.

    Ritorna 'auto' (default: core disponibili - 1, min 1) oppure un intero
    >= 1. La risoluzione di 'auto' avviene nel renderer via
    numpy_parallel.resolve_jobs. Come gli altri flag di main: valore
    mancante → default; valore non valido → messaggio + exit(1).
    Con --jobs 1 l'output resta byte-identico al rendering sequenziale.
    Ignorato dal renderer csound.
    """
    import sys
    if '--jobs' not in argv:
        return 'auto'
    idx = argv.index('--jobs')
    if idx + 1 >= len(argv):
        return 'auto'
    raw = argv[idx + 1]
    if raw.lower() == 'auto':
        return 'auto'
    try:
        value = int(raw)
    except ValueError:
        print(f"--jobs non valido: '{raw}'. Usa un intero >= 1 oppure 'auto'.")
        sys.exit(1)
    if value < 1:
        print(f"--jobs deve essere >= 1, ricevuto: {value}. Usa 1 per il rendering sequenziale.")
        sys.exit(1)
    return value


# Valori di --grain-height, e il modo di grain_visuals a cui corrispondono.
# Sulla CLI il valore composto si scrive col trattino, come i flag; nella
# config del visualizer resta snake_case, come ogni altra chiave. Un dict e non
# una coppia di frozenset: la traduzione fra le due grafie e' proprio il dato.
_GRAIN_HEIGHT_CLI_MODES = {
    'duration': 'duration',
    'read-span': 'read_span',
}


# Chiavi ammesse in un target di --magnify-at. Numeriche (float) e stringa.
_MAGNIFY_NUMERIC_KEYS = frozenset({'t', 'y', 'zoom', 'out', 'src'})
_MAGNIFY_STR_KEYS = frozenset({'stream'})
_MAGNIFY_KEYS = _MAGNIFY_NUMERIC_KEYS | _MAGNIFY_STR_KEYS


def _parse_magnify_spec(spec):
    """Parsa lo SPEC di --magnify-at in una lista di target dict.

    SPEC = target separati da ';'; ogni target = coppie chiave=valore separate
    da ','. La chiave 't' (tempo in secondi) e' obbligatoria; opzionali y, zoom,
    out, src (float) e stream (stringa). Come --plot-envelopes, la validazione
    e' sempre attiva: token malformato, chiave ignota, valore non numerico o 't'
    mancante stampano un messaggio su stdout ed escono con codice 1.
    """
    import sys
    targets = []
    for raw in spec.split(';'):
        raw = raw.strip()
        if not raw:
            continue
        target = {}
        for pair in raw.split(','):
            pair = pair.strip()
            if not pair:
                continue
            if '=' not in pair:
                print(f"--magnify-at: token non valido '{pair}'. "
                      f"Usa chiave=valore (es. t=14,zoom=10).")
                sys.exit(1)
            key, _, value = pair.partition('=')
            key, value = key.strip(), value.strip()
            if key not in _MAGNIFY_KEYS:
                print(f"--magnify-at: chiave ignota '{key}'. "
                      f"Valide: {', '.join(sorted(_MAGNIFY_KEYS))}.")
                sys.exit(1)
            if key in _MAGNIFY_NUMERIC_KEYS:
                try:
                    target[key] = float(value)
                except ValueError:
                    print(f"--magnify-at: valore non numerico per '{key}': '{value}'.")
                    sys.exit(1)
            else:
                target[key] = value
        if 't' not in target:
            print("--magnify-at: ogni target richiede la chiave 't' (tempo in secondi).")
            sys.exit(1)
        targets.append(target)
    if not targets:
        print("--magnify-at: nessun target valido nello SPEC.")
        sys.exit(1)
    return targets


def main():
    import sys
    import os

    if len(sys.argv) < 2:
        print(
            "Uso: python main.py <file.yml> [output.aif] "
            "[--visualize] [--show-static] [--show-voice-offsets] "
            "[--plot-envelopes nomi,csv] "
            "[--magnify] [--magnify-at SPEC] "
            "[--page-duration SECONDI] "
            "[--grain-height duration|read-span] "
            "[--per-stream] "
            "[--renderer csound|numpy] "
            "[--jobs N|auto] "
            "[--format aiff|wav|flac] "
            "[--orc-path PATH] [--incdir DIR] [--ssdir DIR] [--sfdir DIR] "
            "[--log-dir DIR] [--message-level N] "
            "[--keep-sco] [--sco-dir DIR] "
            "[--cache] [--cache-dir DIR] "
            "[--reaper] [--reaper-path FILE] "
            "[--grain-json] "
            "[--export-sv] [--sv-path FILE] [--sv-layout multi|single]"
        )
        sys.exit(1)

    yaml_file = sys.argv[1]
    # Il secondo argomento posizionale e' l'output .aif (default: output.aif)
    output_file = (
        sys.argv[2]
        if len(sys.argv) > 2 and not sys.argv[2].startswith('--')
        else 'output.aif'
    )

    do_visualize = '--visualize' in sys.argv or '-v' in sys.argv
    show_static = '--show-static' in sys.argv or '-s' in sys.argv
    # --show-voice-offsets: disegna gli offset per-voce (una curva per voce)
    # nella partitura. Issue #90, Fase 3. Ha effetto solo con --visualize.
    show_voice_offsets = '--show-voice-offsets' in sys.argv

    # --page-duration SECONDI: durata (secondi) di una pagina della partitura.
    page_duration = 15.0
    if '--page-duration' in sys.argv:
        idx = sys.argv.index('--page-duration')
        if idx + 1 < len(sys.argv):
            try:
                page_duration = float(sys.argv[idx + 1])
            except ValueError:
                print(f"--page-duration non valido: '{sys.argv[idx + 1]}'. Deve essere un numero.")
                sys.exit(1)
            if page_duration <= 0:
                print(f"--page-duration deve essere positivo, ricevuto: {page_duration}")
                sys.exit(1)

    # --plot-envelopes nomi,comma-separated (issue #101): filtro selettivo
    # degli envelope nella partitura. None = tutti (default).
    plot_envelopes = None
    if '--plot-envelopes' in sys.argv:
        idx = sys.argv.index('--plot-envelopes')
        if idx + 1 < len(sys.argv):
            plot_envelopes = {
                name.strip()
                for name in sys.argv[idx + 1].split(',')
                if name.strip()
            }
            unknown = plot_envelopes - PLOT_ENVELOPE_KEYS
            if unknown:
                print(
                    f"Envelope non validi: {', '.join(sorted(unknown))}. "
                    f"Validi: {', '.join(sorted(PLOT_ENVELOPE_KEYS))}"
                )
                sys.exit(1)
    # --grain-height duration|read-span (issue #223): che cosa misura
    # l'altezza del grano sull'asse del buffer nella partitura. 'duration' e'
    # la geometria storica (la porzione che il grano percorrerebbe a velocita'
    # 1), 'read-span' quella che percorre davvero (durata x |pitch_ratio|).
    # Come --plot-envelopes la validazione e' sempre attiva: il refuso non
    # resta muto solo perche' manca --visualize.
    grain_height = _GRAIN_HEIGHT_CLI_MODES['duration']
    if '--grain-height' in sys.argv:
        idx = sys.argv.index('--grain-height')
        if idx + 1 < len(sys.argv):
            raw = sys.argv[idx + 1]
            if raw not in _GRAIN_HEIGHT_CLI_MODES:
                print(f"--grain-height non valido: '{raw}'. "
                      f"Valori: {', '.join(_GRAIN_HEIGHT_CLI_MODES)}")
                sys.exit(1)
            grain_height = _GRAIN_HEIGHT_CLI_MODES[raw]

    # --magnify: lente automatica sul cluster piu' denso (una per pagina).
    # Effetto solo con --visualize, come --show-static. Token esatto: '--magnify'
    # non collide con '--magnify-at' (sono elementi distinti di sys.argv).
    magnify_auto = '--magnify' in sys.argv

    # --magnify-at "SPEC": target espliciti della lente (vedi _parse_magnify_spec).
    # Validazione sempre attiva; effetto sul rendering solo con --visualize.
    magnify_targets = []
    if '--magnify-at' in sys.argv:
        idx = sys.argv.index('--magnify-at')
        if idx + 1 < len(sys.argv):
            magnify_targets = _parse_magnify_spec(sys.argv[idx + 1])

    per_stream = '--per-stream' in sys.argv or '-p' in sys.argv
    use_cache = '--cache' in sys.argv
    reaper_export = '--reaper' in sys.argv
    grain_json = '--grain-json' in sys.argv

    # --export-sv: esporta una sessione Sonic Visualiser (.sv) accanto all'audio
    # (issue #150). Modalita' MIX (un audio -> un .sv); ignorato in --per-stream.
    export_sv = '--export-sv' in sys.argv

    # --sv-path PATH (default: {output_basename}.sv)
    sv_path = None
    if '--sv-path' in sys.argv:
        idx = sys.argv.index('--sv-path')
        if idx + 1 < len(sys.argv):
            sv_path = sys.argv[idx + 1]

    # --sv-layout multi|single (default: multi)
    sv_layout = 'multi'
    if '--sv-layout' in sys.argv:
        idx = sys.argv.index('--sv-layout')
        if idx + 1 < len(sys.argv):
            sv_layout = sys.argv[idx + 1]
        if sv_layout not in ('multi', 'single'):
            print(f"--sv-layout non valido: '{sv_layout}'. Valori: multi, single")
            sys.exit(1)

    # --reaper-path PATH (default: {yaml_basename}.rpp)
    reaper_path = None
    if '--reaper-path' in sys.argv:
        idx = sys.argv.index('--reaper-path')
        if idx + 1 < len(sys.argv):
            reaper_path = sys.argv[idx + 1]

    # --renderer (default: csound)
    renderer_type = 'csound'
    if '--renderer' in sys.argv:
        idx = sys.argv.index('--renderer')
        if idx + 1 < len(sys.argv):
            renderer_type = sys.argv[idx + 1]

    # --jobs N|auto (default: auto = core-1). Solo renderer numpy.
    jobs = _parse_jobs(sys.argv)

    # --cache-dir DIR
    cache_dir = 'cache'
    if '--cache-dir' in sys.argv:
        idx = sys.argv.index('--cache-dir')
        if idx + 1 < len(sys.argv):
            cache_dir = sys.argv[idx + 1]

    # --- Csound config args ---

    orc_path = 'csound/main.orc'
    if '--orc-path' in sys.argv:
        idx = sys.argv.index('--orc-path')
        if idx + 1 < len(sys.argv):
            orc_path = sys.argv[idx + 1]

    incdir = 'src'
    if '--incdir' in sys.argv:
        idx = sys.argv.index('--incdir')
        if idx + 1 < len(sys.argv):
            incdir = sys.argv[idx + 1]

    ssdir = 'refs'
    if '--ssdir' in sys.argv:
        idx = sys.argv.index('--ssdir')
        if idx + 1 < len(sys.argv):
            ssdir = sys.argv[idx + 1]

    sfdir = 'output'
    if '--sfdir' in sys.argv:
        idx = sys.argv.index('--sfdir')
        if idx + 1 < len(sys.argv):
            sfdir = sys.argv[idx + 1]

    log_dir = 'logs'
    if '--log-dir' in sys.argv:
        idx = sys.argv.index('--log-dir')
        if idx + 1 < len(sys.argv):
            log_dir = sys.argv[idx + 1]

    message_level = 134
    if '--message-level' in sys.argv:
        idx = sys.argv.index('--message-level')
        if idx + 1 < len(sys.argv):
            message_level = int(sys.argv[idx + 1])

    # --keep-sco: salva file .sco intermedi per debug
    sco_dir = None
    if '--keep-sco' in sys.argv:
        sco_dir = 'generated'
        if '--sco-dir' in sys.argv:
            idx = sys.argv.index('--sco-dir')
            if idx + 1 < len(sys.argv):
                sco_dir = sys.argv[idx + 1]

    # --format aiff|wav|flac (default: aiff)
    from pge.rendering.audio_format import FORMATS, DEFAULT_FORMAT
    audio_format = DEFAULT_FORMAT
    if '--format' in sys.argv:
        idx = sys.argv.index('--format')
        if idx + 1 < len(sys.argv):
            fmt_label = sys.argv[idx + 1].lower()
            if fmt_label not in FORMATS:
                print(f"Formato non supportato: '{fmt_label}'. Usa: aiff, wav, flac")
                sys.exit(1)
            audio_format = FORMATS[fmt_label]

    # Adatta il default output_file all'estensione del formato scelto
    if output_file == 'output.aif' and audio_format.extension != '.aif':
        output_file = f'output{audio_format.extension}'

    yaml_basename = os.path.splitext(os.path.basename(yaml_file))[0]
    configure_clip_logger(
        console_enabled=False,
        file_enabled=True,
        log_dir='./logs',
        yaml_name=yaml_basename,
        log_transformations=False
    )
    configure_engine_logger(yaml_name=yaml_basename, log_dir='./logs')

    try:
        generator = Generator(yaml_file)

        print(f"Caricamento {yaml_file}...")
        generator.load_yaml()

        print("Generazione streams...")
        generator.create_elements()

        renderer = _build_renderer(
            renderer_type,
            generator,
            output_sr=DEFAULT_OUTPUT_SR,
            jobs=jobs,
            orc_path=orc_path,
            incdir=incdir,
            ssdir=ssdir,
            sfdir=sfdir,
            log_dir=log_dir,
            message_level=message_level,
            use_cache=use_cache,
            cache_dir=cache_dir,
            yaml_basename=yaml_basename,
            sco_dir=sco_dir,
            audio_format=audio_format,
        )

        # Garbage collection: rimuove stream orfani (rimossi/rinominati nel YAML)
        # Solo in STEMS+CACHE mode: è l'unico caso con build incrementale per
        # stream. Il GC va eseguito PRIMA del render (e stampato qui, prima
        # dei print del render): per questo la CLI lo chiama esplicitamente
        # e passa run_cache_gc=False ad api.render.
        if per_stream and use_cache:
            removed = api.collect_cache_orphans(
                generator, renderer, output_file, audio_format=audio_format)
            if removed:
                print(f"[CACHE] GC: rimossi {len(removed)} stream orfani: {removed}")

        result = api.render(
            generator,
            output_file,
            renderer=renderer,
            per_stream=per_stream,
            audio_format=audio_format,
            run_cache_gc=False,
        )
        generated = result.audio_paths
        jobs_note = f" (jobs={renderer.jobs})" if renderer_type == 'numpy' else ""
        print(f"\n Rendering completato in {result.elapsed_seconds:.2f}s{jobs_note}")

        print(f"\n Generazione completata! {len(generated)} file generati:")
        for path in generated:
            print(f"    {path}")

        if reaper_export:
            rpp_out = reaper_path if reaper_path else f"{yaml_basename}.rpp"
            api.export_reaper(generator, generated, rpp_out)
            print(f"Reaper project: {rpp_out}")

        if export_sv:
            if per_stream:
                # v1 esporta contro un singolo audio (MIX). Lo split STEMS
                # (un .sv per stem) e' un follow-up.
                print("[export-sv] ignorato in modalità --per-stream (STEMS): "
                      "v1 supporta solo MIX")
            else:
                sv_out = sv_path if sv_path else output_file.rsplit('.', 1)[0] + '.sv'
                audio_for_sv = generated[0] if generated else output_file
                api.export_sv(generator, audio_for_sv, sv_out, layout=sv_layout)
                print(f"Sonic Visualiser session: {sv_out}")

        if grain_json:
            if not per_stream:
                print("[grain-json] ignorato: richiede --per-stream")
            else:
                # Sidecar accanto agli stem .aif: PGE-ui trova grain JSON e
                # audio nella stessa directory dell'output STEMS.
                grain_json_dir = os.path.dirname(os.path.abspath(output_file))
                for json_path in api.export_grain_json(
                        generator, grain_json_dir, yaml_basename):
                    print(f"Grain JSON: {json_path}")

        if do_visualize:
            print("\nGenerazione partitura grafica...")
            pdf_file = output_file.rsplit('.', 1)[0] + '.pdf'
            api.export_score_pdf(generator, pdf_file, config={
                'page_duration': page_duration,
                'show_static_params': show_static,
                'show_voice_offsets': show_voice_offsets,
                'envelope_filter': plot_envelopes,
                'magnify_auto': magnify_auto,
                'magnify_targets': magnify_targets,
                'grain_height': grain_height,
            })

        print(f"Log: {get_clip_log_path()}")

    except FileNotFoundError:
        print(f" Errore: file '{yaml_file}' non trovato")
        sys.exit(1)
    except EngineError as e:
        _handle_engine_error(e)
        sys.exit(1)
    except Exception as e:
        print(f" Errore: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
