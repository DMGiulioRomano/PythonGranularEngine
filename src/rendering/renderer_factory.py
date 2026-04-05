# src/rendering/renderer_factory.py
"""
RendererFactory - Factory Method per la creazione di AudioRenderer.

Seleziona l'implementazione concreta di AudioRenderer in base al
flag CLI --renderer:
  - 'csound': CsoundRenderer (adapter su pipeline esistente)
  - 'numpy':  NumpyAudioRenderer (rendering NumPy overlap-add)

Usato da main.py per iniettare il renderer in Generator.
"""

from typing import Dict, Any

from rendering.audio_renderer import AudioRenderer


class RendererFactory:
    """
    Factory per la creazione di AudioRenderer.

    Uso:
        renderer = RendererFactory.create('numpy',
            sample_registry=...,
            window_registry=...,
            table_map=...,
            output_sr=48000,
        )

        renderer = RendererFactory.create('csound',
            score_writer=...,
            csound_config={...},
        )
    """

    _VALID_TYPES = {'numpy', 'csound'}

    @staticmethod
    def create(renderer_type: str, **kwargs) -> AudioRenderer:
        """
        Crea un AudioRenderer del tipo specificato.

        Args:
            renderer_type: 'numpy' o 'csound'
            **kwargs: argomenti passati al costruttore del renderer

        Returns:
            Istanza di AudioRenderer (NumpyAudioRenderer o CsoundRenderer)

        Raises:
            ValueError: se renderer_type non e' supportato
        """
        if renderer_type not in RendererFactory._VALID_TYPES:
            raise ValueError(
                f"Renderer '{renderer_type}' non supportato. "
                f"Tipi validi: {', '.join(sorted(RendererFactory._VALID_TYPES))}"
            )

        if renderer_type == 'numpy':
            from rendering.numpy_audio_renderer import NumpyAudioRenderer
            return NumpyAudioRenderer(
                sample_registry=kwargs['sample_registry'],
                window_registry=kwargs['window_registry'],
                table_map=kwargs['table_map'],
                output_sr=kwargs.get('output_sr', 48000),
                cache_manager=kwargs.get('cache_manager'),
                stream_data_map=kwargs.get('stream_data_map'),
            )

        if renderer_type == 'csound':
            from rendering.csound_renderer import CsoundRenderer
            return CsoundRenderer(
                score_writer=kwargs['score_writer'],
                csound_config=kwargs.get('csound_config', {}),
                cartridges=kwargs.get('cartridges'),
                cache_manager=kwargs.get('cache_manager'),
                stream_data_map=kwargs.get('stream_data_map'),
                sco_dir=kwargs.get('sco_dir'),
            )