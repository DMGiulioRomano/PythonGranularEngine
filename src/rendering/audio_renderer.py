# src/rendering/audio_renderer.py
"""
AudioRenderer - Abstract Base Class per il rendering audio.

Strategy pattern (OCP): definisce l'interfaccia comune per tutti i renderer.
Le implementazioni concrete sono:
- CsoundRenderer: adapter su ScoreWriter + subprocess csound
- NumpyAudioRenderer: rendering NumPy puro con overlap-add

Ogni renderer sa produrre un file audio (.aif) a partire da
uno Stream (sintesi granulare) o una Cartridge (tape recorder).
"""

from abc import ABC, abstractmethod


class AudioRenderer(ABC):
    """
    Interfaccia astratta per il rendering audio.

    Contratto:
    - render_stream(): riceve uno Stream e un output_path, produce un file audio,
      ritorna il path del file prodotto.
    - render_cartridge(): riceve una Cartridge e un output_path, produce un file audio,
      ritorna il path del file prodotto.
    """

    @abstractmethod
    def render_stream(self, stream, output_path: str) -> str:
        """
        Renderizza uno stream granulare in un file audio.

        Args:
            stream: oggetto Stream con voices e grains gia' generati
            output_path: percorso del file audio di output (es. 'output/stream_01.aif')

        Returns:
            Il percorso del file audio prodotto.
        """
        ...

    @abstractmethod
    def render_cartridge(self, cartridge, output_path: str) -> str:
        """
        Renderizza una cartridge (tape recorder) in un file audio.

        Args:
            cartridge: oggetto Cartridge con parametri di playback
            output_path: percorso del file audio di output (es. 'output/cart_01.aif')

        Returns:
            Il percorso del file audio prodotto.
        """
        ...