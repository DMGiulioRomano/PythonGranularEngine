# src/rendering/renderer_factory.py
"""
RendererFactory - Factory Method per la creazione di AudioRenderer.

Seleziona l'implementazione concreta di AudioRenderer in base al
flag CLI --renderer:
  - 'csound': CsoundRenderer (adapter su pipeline esistente)
  - 'numpy':  NumpyAudioRenderer (rendering NumPy overlap-add)

Usato da main.py per iniettare il renderer in Generator.
"""
from __future__ import annotations

from typing import Dict, Any

from pge.rendering.audio_renderer import AudioRenderer
from pge.shared.constants import DEFAULT_OUTPUT_SR
from pge.shared.exceptions import InvalidRendererError


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
            raise InvalidRendererError(
                renderer_type=renderer_type,
                available=sorted(RendererFactory._VALID_TYPES),
            )

        if renderer_type == 'numpy':
            from pge.rendering.numpy_audio_renderer import NumpyAudioRenderer
            from pge.rendering.audio_format import DEFAULT_FORMAT
            return NumpyAudioRenderer(
                sample_registry=kwargs['sample_registry'],
                window_registry=kwargs['window_registry'],
                table_map=kwargs['table_map'],
                output_sr=kwargs.get('output_sr', DEFAULT_OUTPUT_SR),
                cache_manager=kwargs.get('cache_manager'),
                stream_data_map=kwargs.get('stream_data_map'),
                audio_format=kwargs.get('audio_format', DEFAULT_FORMAT),
                jobs=kwargs.get('jobs', 1),
            )

        if renderer_type == 'csound':
            from pge.rendering.csound_renderer import CsoundRenderer
            return CsoundRenderer(
                score_writer=kwargs['score_writer'],
                csound_config=kwargs.get('csound_config', {}),
                cache_manager=kwargs.get('cache_manager'),
                stream_data_map=kwargs.get('stream_data_map'),
                sco_dir=kwargs.get('sco_dir'),
            )
