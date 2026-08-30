# src/rendering/renderer_factory.py
"""
RendererFactory - Factory Method per la creazione di AudioRenderer.

Seleziona l'implementazione concreta di AudioRenderer in base al
flag CLI --renderer:
  - 'csound':        CsoundRenderer (adapter su pipeline esistente)
  - 'numpy':         NumpyAudioRenderer (rendering NumPy overlap-add)
  - 'supercollider': SuperColliderRenderer (score NRT + scsynth)

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

        renderer = RendererFactory.create('supercollider',
            table_map=...,
            window_registry=...,
            samples_dir=...,
        )
    """

    _VALID_TYPES = {'numpy', 'csound', 'supercollider'}

    @classmethod
    def available_types(cls) -> list:
        """Tipi di renderer accettati, ordinati.

        E' l'unico elenco: i messaggi d'errore (InvalidRendererError) e i
        chiamanti che vogliono sapere cosa esiste lo chiedono qui invece di
        tenerne una copia, che e' esattamente il modo in cui un terzo
        renderer resta invisibile a meta' del progetto.
        """
        return sorted(cls._VALID_TYPES)

    @staticmethod
    def create(renderer_type: str, **kwargs) -> AudioRenderer:
        """
        Crea un AudioRenderer del tipo specificato.

        Args:
            renderer_type: 'numpy', 'csound' o 'supercollider'
            **kwargs: argomenti passati al costruttore del renderer

        Returns:
            Istanza di AudioRenderer

        Raises:
            ValueError: se renderer_type non e' supportato
        """
        if renderer_type not in RendererFactory._VALID_TYPES:
            raise InvalidRendererError(
                renderer_type=renderer_type,
                available=RendererFactory.available_types(),
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

        if renderer_type == 'supercollider':
            from pge.rendering.supercollider_renderer import SuperColliderRenderer
            from pge.rendering.audio_format import DEFAULT_FORMAT
            from pge.rendering.numpy_window_registry import NumpyWindowRegistry
            return SuperColliderRenderer(
                table_map=kwargs['table_map'],
                window_registry=kwargs.get('window_registry') or NumpyWindowRegistry(),
                samples_dir=kwargs.get('samples_dir', './refs/'),
                output_sr=kwargs.get('output_sr', DEFAULT_OUTPUT_SR),
                audio_format=kwargs.get('audio_format', DEFAULT_FORMAT),
                sc_config=kwargs.get('sc_config', {}),
                cache_manager=kwargs.get('cache_manager'),
                stream_data_map=kwargs.get('stream_data_map'),
                osc_dir=kwargs.get('osc_dir'),
            )
