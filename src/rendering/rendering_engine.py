# src/rendering/rendering_engine.py
"""
RenderingEngine - Facade che coordina renderer + naming + mode.

Design Pattern: Facade + Dependency Injection
- OCP puro: ogni componente è iniettabile/sostituibile
- main.py non conosce dettagli implementativi

Responsabilità:
- Coordinare AudioRenderer + NamingStrategy + RenderMode
- Fornire interfaccia semplice per main.py
"""

from typing import List
from rendering.naming_strategy import NamingStrategy, DefaultNamingStrategy


class RenderingEngine:
    """
    Facade per il sistema di rendering.

    Coordina:
    - AudioRenderer (atomico): esegue rendering effettivo
    - NamingStrategy: genera path output
    - RenderMode: decide come renderizzare (stems/mix/altro)

    Open/Closed Principle:
    - Aggiungere nuovo renderer → passa istanza diversa
    - Cambiare naming → passa naming_strategy diversa
    - Aggiungere modalità → crea nuovo RenderMode, passa come mode
    - main.py rimane INVARIATO

    Examples:
        # Setup
        renderer = NumpyAudioRenderer(...)
        engine = RenderingEngine(renderer)

        # STEMS mode
        from rendering.render_mode import StemsRenderMode
        generated = engine.render(streams, '/out/base.aif', mode=StemsRenderMode())
        → ['/out/base_s1.aif', '/out/base_s2.aif', ...]

        # MIX mode
        from rendering.render_mode import MixRenderMode
        generated = engine.render(streams, '/out/mix.aif', mode=MixRenderMode())
        → ['/out/mix.aif']

        # Custom naming
        custom_naming = DashNamingStrategy()
        engine = RenderingEngine(renderer, naming_strategy=custom_naming)
        generated = engine.render(streams, '/out/base.aif', mode=StemsRenderMode())
        → ['/out/base-s1.aif', '/out/base-s2.aif', ...]
    """

    def __init__(
        self,
        renderer,  # AudioRenderer atomico
        naming_strategy: NamingStrategy = None
    ):
        """
        Inizializza RenderingEngine.

        Args:
            renderer: AudioRenderer atomico (deve implementare
                      render_single_stream() e render_merged_streams())
            naming_strategy: NamingStrategy opzionale (default: DefaultNamingStrategy)
        """
        self.renderer = renderer
        self.naming = naming_strategy or DefaultNamingStrategy()

    def render(
        self,
        streams: List,
        output_path: str,
        mode  # RenderMode instance
    ) -> List[str]:
        """
        Renderizza stream(s) secondo la modalità specificata.

        Delega completamente a RenderMode.execute(), che coordina
        renderer + naming per eseguire il rendering.

        Args:
            streams: lista di Stream objects da renderizzare
            output_path: percorso base output
            mode: istanza di RenderMode (StemsRenderMode, MixRenderMode, etc.)

        Returns:
            Lista di path file audio generati

        Examples:
            # STEMS
            paths = engine.render(streams, '/out/base.aif', StemsRenderMode())

            # MIX
            paths = engine.render(streams, '/out/mix.aif', MixRenderMode())
        """
        # Delega tutto al RenderMode
        return mode.execute(
            renderer=self.renderer,
            naming=self.naming,
            streams=streams,
            output_path=output_path
        )
