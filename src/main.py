# =============================================================================
# MAIN
# =============================================================================

from shared.logger import configure_clip_logger, get_clip_log_path
from engine.generator import Generator
from rendering.score_visualizer import ScoreVisualizer


def _build_renderer(renderer_type: str, generator, **kwargs):
    """
    Crea il renderer appropriato in base al tipo.

    Lazy imports per evitare dipendenze al caricamento del modulo
    e per consentire il mocking nei test.

    Args:
        renderer_type: 'csound' o 'numpy'
        generator: istanza di Generator con streams/cartridges gia' creati
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

        return RendererFactory.create(
            'numpy',
            sample_registry=sample_reg,
            window_registry=window_reg,
            table_map=table_map,
            output_sr=kwargs.get('output_sr', 48000),
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
            cartridges=generator.cartridges,
            cache_manager=cache_manager,
            stream_data_map=generator.stream_data_map,
            sco_dir=kwargs.get('sco_dir'),
        )

    raise ValueError(
        f"Renderer '{renderer_type}' non supportato. Tipi validi: csound, numpy"
    )


def main():
    import sys
    import os

    if len(sys.argv) < 2:
        print(
            "Uso: python main.py <file.yml> [output.aif] "
            "[--visualize] [--show-static] [--per-stream] "
            "[--renderer csound|numpy] "
            "[--orc-path PATH] [--incdir DIR] [--ssdir DIR] [--sfdir DIR] "
            "[--log-dir DIR] [--message-level N] "
            "[--keep-sco] [--sco-dir DIR] "
            "[--cache] [--cache-dir DIR]"
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
    per_stream = '--per-stream' in sys.argv or '-p' in sys.argv
    use_cache = '--cache' in sys.argv

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

    yaml_basename = os.path.splitext(os.path.basename(yaml_file))[0]
    configure_clip_logger(
        console_enabled=False,
        file_enabled=True,
        log_dir='./logs',
        yaml_name=yaml_basename,
        log_transformations=False
    )

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
        )

        engine = RenderingEngine(renderer)
        mode = StemsRenderMode() if per_stream else MixRenderMode()
        generated = engine.render(
            streams=generator.streams,
            output_path=output_file,
            mode=mode,
        )

        print(f"\n Generazione completata! {len(generated)} file generati:")
        for path in generated:
            print(f"    {path}")

        if do_visualize:
            print("\nGenerazione partitura grafica...")
            pdf_file = output_file.rsplit('.', 1)[0] + '.pdf'
            viz = ScoreVisualizer(generator, config={
                'page_duration': 15.0,
                'show_static_params': show_static,
            })
            viz.export_pdf(pdf_file)

        print(f"Log: {get_clip_log_path()}")

    except FileNotFoundError:
        print(f" Errore: file '{yaml_file}' non trovato")
        sys.exit(1)
    except Exception as e:
        print(f" Errore: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
