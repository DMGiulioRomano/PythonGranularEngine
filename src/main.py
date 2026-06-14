# =============================================================================
# MAIN
# =============================================================================

import traceback

from shared.logger import (
    configure_clip_logger, get_clip_log_path,
    configure_engine_logger, get_engine_logger, get_engine_log_path,
)
from shared.exceptions import EngineError
from engine.generator import Generator
from rendering.score_visualizer import ScoreVisualizer, PLOT_ENVELOPE_KEYS


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
    Crea il renderer appropriato in base al tipo.

    Lazy imports per evitare dipendenze al caricamento del modulo
    e per consentire il mocking nei test.

    Args:
        renderer_type: 'csound' o 'numpy'
        generator: istanza di Generator con streams gia' creati
        **kwargs: argomenti specifici per ogni renderer

    Returns:
        Istanza di AudioRenderer configurata

    Raises:
        ValueError: se renderer_type non e' supportato
    """
    from rendering.renderer_factory import RendererFactory

    if renderer_type == 'numpy':
        from rendering.sample_registry import SampleRegistry
        from rendering.numpy_window_registry import NumpyWindowRegistry

        table_map = generator.ftable_manager.get_all_tables()
        sample_reg = SampleRegistry()
        window_reg = NumpyWindowRegistry()

        for _, (ftype, name) in table_map.items():
            if ftype == 'sample':
                sample_reg.load(name)

        cache_manager = None
        if kwargs.get('use_cache'):
            import os as _os
            from rendering.stream_cache_manager import StreamCacheManager
            yaml_basename = kwargs['yaml_basename']
            cache_dir = kwargs.get('cache_dir', 'cache')
            cache_path = _os.path.join(cache_dir, f"{yaml_basename}.json")
            cache_manager = StreamCacheManager(cache_path=cache_path)
            print(f"[CACHE] Manifest: {cache_path}")

        from rendering.audio_format import DEFAULT_FORMAT
        return RendererFactory.create(
            'numpy',
            sample_registry=sample_reg,
            window_registry=window_reg,
            table_map=table_map,
            output_sr=kwargs.get('output_sr', 48000),
            cache_manager=cache_manager,
            stream_data_map=generator.stream_data_map,
            audio_format=kwargs.get('audio_format', DEFAULT_FORMAT),
        )

    if renderer_type == 'csound':
        csound_config = {
            'orc_path': kwargs.get('orc_path', 'csound/main.orc'),
            'env_vars': {
                'INCDIR': kwargs.get('incdir', 'src'),
                'SSDIR': kwargs.get('ssdir', 'refs'),
                'SFDIR': kwargs.get('sfdir', 'output'),
            },
            'log_dir': kwargs.get('log_dir', 'logs'),
            'message_level': kwargs.get('message_level', 134),
        }

        cache_manager = None
        if kwargs.get('use_cache'):
            import os as _os
            from rendering.stream_cache_manager import StreamCacheManager
            yaml_basename = kwargs['yaml_basename']
            cache_dir = kwargs.get('cache_dir', 'cache')
            cache_path = _os.path.join(cache_dir, f"{yaml_basename}.json")
            cache_manager = StreamCacheManager(cache_path=cache_path)
            print(f"[CACHE] Manifest: {cache_path}")

        return RendererFactory.create(
            'csound',
            score_writer=generator.score_writer,
            csound_config=csound_config,
            cache_manager=cache_manager,
            stream_data_map=generator.stream_data_map,
            sco_dir=kwargs.get('sco_dir'),
        )

    from shared.exceptions import InvalidRendererError
    raise InvalidRendererError(
        renderer_type=renderer_type,
        available=["csound", "numpy"],
    )


def main():
    import sys
    import os

    if len(sys.argv) < 2:
        print(
            "Uso: python main.py <file.yml> [output.aif] "
            "[--visualize] [--show-static] [--show-voice-offsets] "
            "[--plot-envelopes nomi,csv] "
            "[--page-duration SECONDI] "
            "[--per-stream] "
            "[--renderer csound|numpy] "
            "[--format aiff|wav|flac] "
            "[--orc-path PATH] [--incdir DIR] [--ssdir DIR] [--sfdir DIR] "
            "[--log-dir DIR] [--message-level N] "
            "[--keep-sco] [--sco-dir DIR] "
            "[--cache] [--cache-dir DIR] "
            "[--reaper] [--reaper-path FILE] "
            "[--grain-json]"
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
    per_stream = '--per-stream' in sys.argv or '-p' in sys.argv
    use_cache = '--cache' in sys.argv
    reaper_export = '--reaper' in sys.argv
    grain_json = '--grain-json' in sys.argv

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
    from rendering.audio_format import FORMATS, DEFAULT_FORMAT
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

        from rendering.rendering_engine import RenderingEngine
        from rendering.render_mode import StemsRenderMode, MixRenderMode

        renderer = _build_renderer(
            renderer_type,
            generator,
            output_sr=48000,
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
        # Solo in STEMS+CACHE mode: è l'unico caso con build incrementale per stream.
        if per_stream and use_cache:
            cache_manager = getattr(renderer, 'cache_manager', None)
            if cache_manager is not None:
                current_ids = [s.stream_id for s in generator.streams]
                removed = cache_manager.garbage_collect(
                    current_stream_ids=current_ids,
                    aif_dir=os.path.dirname(os.path.abspath(output_file)),
                    aif_prefix=yaml_basename,
                    ext=audio_format.extension,
                )
                if removed:
                    print(f"[CACHE] GC: rimossi {len(removed)} stream orfani: {removed}")

        from rendering.naming_strategy import DefaultNamingStrategy
        engine = RenderingEngine(renderer, naming_strategy=DefaultNamingStrategy(ext=audio_format.extension))
        mode = StemsRenderMode() if per_stream else MixRenderMode()
        generated = engine.render(
            streams=generator.streams,
            output_path=output_file,
            mode=mode,
        )

        print(f"\n Generazione completata! {len(generated)} file generati:")
        for path in generated:
            print(f"    {path}")

        if reaper_export:
            from export.reaper_project_writer import ReaperProjectWriter
            rpp_out = reaper_path if reaper_path else f"{yaml_basename}.rpp"
            # In MIX mode generated contiene 1 solo file per N stream:
            # ogni TRACK punta al mix con onset/duration del proprio stream.
            n = len(generator.streams)
            aif_paths = generated if len(generated) == n else [generated[0]] * n
            ReaperProjectWriter().write(
                streams=generator.streams,
                aif_paths=aif_paths,
                output_path=rpp_out,
            )
            print(f"Reaper project: {rpp_out}")

        if grain_json:
            if not per_stream:
                print("[grain-json] ignorato: richiede --per-stream")
            else:
                from export.grain_json_writer import GrainJsonWriter
                # Sidecar accanto agli stem .aif: PGE-ui trova grain JSON e
                # audio nella stessa directory dell'output STEMS.
                grain_json_dir = os.path.dirname(os.path.abspath(output_file))
                writer = GrainJsonWriter()
                for stream in generator.streams:
                    json_path = writer.write(stream, grain_json_dir, yaml_basename)
                    print(f"Grain JSON: {json_path}")

        if do_visualize:
            print("\nGenerazione partitura grafica...")
            pdf_file = output_file.rsplit('.', 1)[0] + '.pdf'
            viz = ScoreVisualizer(generator, config={
                'page_duration': page_duration,
                'show_static_params': show_static,
                'show_voice_offsets': show_voice_offsets,
                'envelope_filter': plot_envelopes,
            })
            viz.export_pdf(pdf_file)

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
