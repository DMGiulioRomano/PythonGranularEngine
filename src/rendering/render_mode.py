# src/rendering/render_mode.py
"""
RenderMode - Strategy Pattern per modalità di rendering.

Open/Closed Principle: aggiungere nuove modalità (per-voice, per-effect, etc.)
senza modificare codice esistente.

Modalità supportate:
- StemsRenderMode: un file separato per ogni stream
- MixRenderMode: un file unico con tutti gli stream mixati
"""

from abc import ABC, abstractmethod
from typing import List


class RenderMode(ABC):
    """
    Strategy per modalità di rendering.

    Responsabilità:
    - Decidere COME renderizzare (stems vs mix vs altro)
    - Coordinare renderer + naming per eseguire il rendering
    - Ritornare lista di path file generati
    """

    @abstractmethod
    def execute(
        self,
        renderer,  # AudioRenderer atomico
        naming,    # NamingStrategy
        streams: List,
        output_path: str
    ) -> List[str]:
        """
        Esegue il rendering secondo questa modalità.

        Args:
            renderer: AudioRenderer atomico (render_single_stream, render_merged_streams)
            naming: NamingStrategy per generare path output
            streams: lista di Stream objects da renderizzare
            output_path: percorso base output

        Returns:
            Lista di path file audio generati

        Examples:
            # STEMS mode
            mode = StemsRenderMode()
            paths = mode.execute(renderer, naming, [s1, s2], '/out/base.aif')
            → ['/out/base_s1.aif', '/out/base_s2.aif']

            # MIX mode
            mode = MixRenderMode()
            paths = mode.execute(renderer, naming, [s1, s2], '/out/mix.aif')
            → ['/out/mix.aif']
        """
        pass


class StemsRenderMode(RenderMode):
    """
    STEMS mode: renderizza ogni stream in un file separato.

    Comportamento:
    - Un file per stream
    - Ogni stream parte da onset=0 nel proprio file (onset relativi)
    - Naming: {base}_{stream_id}.aif
    """

    def execute(
        self,
        renderer,
        naming,
        streams: List,
        output_path: str
    ) -> List[str]:
        """
        Renderizza ogni stream separatamente.

        Delega a:
        - naming.generate_paths() per ottenere path
        - renderer.render_single_stream() per ogni stream
        """
        # Genera path per ogni stream
        paths_map = naming.generate_paths(output_path, streams, mode='stems')

        # Renderizza ogni stream separatamente
        generated = []
        for stream, path in paths_map:
            renderer.render_single_stream(stream, path)
            generated.append(path)

        return generated


class MixRenderMode(RenderMode):
    """
    MIX mode: renderizza tutti gli stream in un file unico.

    Comportamento:
    - Un file con tutti gli stream
    - Rispetta onset assoluti (stream.onset determina posizione nel mix)
    - Naming: {base}.aif (invariato)
    """

    def execute(
        self,
        renderer,
        naming,
        streams: List,
        output_path: str
    ) -> List[str]:
        """
        Renderizza tutti gli stream in un file unico.

        Delega a:
        - naming.generate_paths() per ottenere path (unico)
        - renderer.render_merged_streams() con tutti gli stream
        """
        # Genera path per mix (unico path, tutti gli stream)
        paths_map = naming.generate_paths(output_path, streams, mode='mix')

        # Estrai (lista_stream, path)
        all_streams, mix_path = paths_map[0]

        # Renderizza mix
        renderer.render_merged_streams(all_streams, mix_path)

        return [mix_path]
