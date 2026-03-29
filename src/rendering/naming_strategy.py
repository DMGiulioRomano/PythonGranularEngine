# src/rendering/naming_strategy.py
"""
NamingStrategy - Strategy Pattern per generazione path output.

Open/Closed Principle: aggiungere nuove strategie di naming
senza modificare codice esistente.

Esempi:
- DefaultNamingStrategy: {base}_{stream_id}.aif
- DashNamingStrategy: {base}-{stream_id}.aif
- TimestampNamingStrategy: {base}_{stream_id}_{timestamp}.aif
"""

import os
from abc import ABC, abstractmethod
from typing import List, Tuple, Any


class NamingStrategy(ABC):
    """
    Strategy per generazione path output file.

    Responsabilità:
    - Generare path output da base_path + streams + mode
    - Supportare diverse modalità (stems, mix, per-voice, etc.)
    """

    @abstractmethod
    def generate_paths(
        self,
        base_path: str,
        streams: List,
        mode: str
    ) -> List[Tuple[Any, str]]:
        """
        Genera lista di (item, output_path).

        Args:
            base_path: percorso base (es. 'output/composition.aif')
            streams: lista di Stream objects
            mode: modalità rendering ('stems', 'mix', 'per-voice', etc.)

        Returns:
            Lista di tuple (item, path) dove:
            - item: Stream singolo (per stems) o lista stream (per mix)
            - path: percorso file output

        Raises:
            ValueError: se mode non è supportato

        Examples:
            # STEMS mode
            generate_paths('/out/base.aif', [s1, s2], 'stems')
            → [(s1, '/out/base_s1.aif'), (s2, '/out/base_s2.aif')]

            # MIX mode
            generate_paths('/out/base.aif', [s1, s2], 'mix')
            → [([s1, s2], '/out/base.aif')]
        """
        pass


class DefaultNamingStrategy(NamingStrategy):
    """
    Naming strategy di default.

    Formato:
    - STEMS: {base}_{stream_id}.aif
    - MIX: {base}.aif (invariato)
    """

    def generate_paths(
        self,
        base_path: str,
        streams: List,
        mode: str
    ) -> List[Tuple[Any, str]]:
        """
        Genera path con formato default.

        Supporta:
        - 'stems': un file per stream
        - 'mix': un file con tutti gli stream
        """
        # Estrai base senza estensione
        base = os.path.splitext(base_path)[0]

        if mode == 'stems':
            # STEMS: {base}_{stream_id}.aif
            return [
                (stream, f"{base}_{stream.stream_id}.aif")
                for stream in streams
            ]

        elif mode == 'mix':
            # MIX: tutti gli stream → un path
            return [(streams, base_path)]

        else:
            raise ValueError(
                f"Mode '{mode}' not supported by DefaultNamingStrategy. "
                f"Supported: 'stems', 'mix'"
            )
