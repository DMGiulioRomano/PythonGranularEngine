# src/rendering/audio_renderer.py
"""
AudioRenderer - Abstract Base Class per il rendering audio (ATOMICO).

Strategy pattern (OCP): definisce l'interfaccia comune per tutti i renderer.
Refactored per Strategy Composition Architecture.

Implementazioni concrete:
- CsoundRenderer: adapter su ScoreWriter + subprocess csound
- NumpyAudioRenderer: rendering NumPy puro con overlap-add

ATOMIC INTERFACE:
Il renderer sa solo renderizzare, non decide la logica di controllo
(stems vs mix, loop, naming). Questa responsabilità è di RenderMode + RenderingEngine.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple


class AudioRenderer(ABC):
    """
    Interfaccia atomica per il rendering audio.

    Contratto (ATOMICO):
    - render_single_stream(): renderizza UN stream in UN file (onset relativi)
    - render_merged_streams(): renderizza PIÙ stream in UN file (onset assoluti)
    - render_streams(): CONCRETO — renderizza N stream in N file; default =
      loop su render_single_stream, override possibile per parallelizzare

    Il renderer NON decide:
    - Se fare stems o mix (responsabilità di RenderMode)
    - Come nominare i file (responsabilità di NamingStrategy)
    - Loop su stream (responsabilità di RenderMode)

    Il renderer SA SOLO:
    - Renderizzare audio da grani
    - Gestire onset relativi (single) vs assoluti (merged)
    """

    @abstractmethod
    def render_single_stream(self, stream, output_path: str) -> str:
        """
        Renderizza UN stream in UN file (onset relativi).

        Usato per: STEMS mode (ogni stream in file separato)

        Comportamento:
        - Buffer dimensionato per stream.duration
        - Onset grani sono RELATIVI allo stream (onset - stream.onset)
        - Output parte da tempo 0 (non considera stream.onset)

        Args:
            stream: oggetto Stream con voices e grains già generati
            output_path: percorso file output (es. '/out/composition__stream1.aif')

        Returns:
            Il percorso del file prodotto

        Examples:
            # Stream con onset=5s, duration=10s
            renderer.render_single_stream(stream, '/out/s1.aif')
            # → file di 10 secondi che parte da 0 (ignora onset=5)
        """
        ...

    @abstractmethod
    def render_merged_streams(self, streams: List, output_path: str) -> str:
        """
        Renderizza PIÙ stream in UN file (onset assoluti).

        Usato per: MIX mode (tutti gli stream nello stesso file)

        Comportamento:
        - Buffer dimensionato per max(stream.onset + stream.duration)
        - Onset grani sono ASSOLUTI (rispetta stream.onset)
        - Output contiene tutti gli stream posizionati correttamente

        Args:
            streams: lista di Stream objects da mixare
            output_path: percorso file output (es. '/out/composition.aif')

        Returns:
            Il percorso del file prodotto

        Examples:
            # Stream1: onset=0s, duration=5s
            # Stream2: onset=10s, duration=5s
            renderer.render_merged_streams([s1, s2], '/out/mix.aif')
            # → file di 15 secondi: s1 a 0-5s, silenzio 5-10s, s2 a 10-15s
        """
        ...

    def render_streams(self, pairs: List[Tuple[object, str]]) -> List[str]:
        """
        Renderizza N stream in N file (onset relativi), un file per coppia.

        Usato per: STEMS mode (StemsRenderMode delega qui il loop).

        Metodo CONCRETO, non astratto: il default itera le coppie in ordine
        e delega a render_single_stream — comportamento identico al loop
        storico di StemsRenderMode. Le sottoclassi possono fare override per
        cambiare il COME (es. NumpyAudioRenderer: un task per stream a un
        pool di processi) senza toccare RenderMode, che continua a decidere
        il COSA (OCP).

        Args:
            pairs: coppie (stream, output_path), una per stem

        Returns:
            Lista dei path prodotti, nell'ordine delle coppie
        """
        return [self.render_single_stream(stream, path) for stream, path in pairs]
