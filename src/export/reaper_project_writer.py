# src/export/reaper_project_writer.py
"""
ReaperProjectWriter

Esporta stream granulari in un progetto Reaper (.rpp).

Responsabilità:
- generate(): produce il contenuto .rpp come stringa
- write(): scrive il file .rpp su disco

Formato prodotto:
  <REAPER_PROJECT 0.1 "6.0"
    <TRACK
      NAME "stream_id"
      <ITEM
        POSITION <onset>
        LENGTH   <duration>
        <SOURCE WAVE
          FILE "path/to/file.aif"
        >
      >
    >
  >

I file .aif sono referenziati per path (non embedded).
Un TRACK per stream, un ITEM per TRACK.
"""

from typing import List


class ReaperProjectWriter:
    """
    Esporta una lista di stream in un progetto Reaper (.rpp).

    Ogni stream diventa un TRACK posizionato sul timeline secondo
    stream.onset e stream.duration. Il file .aif corrispondente
    viene referenziato nel blocco SOURCE WAVE.
    """

    REAPER_VERSION = '0.1 "6.0"'

    def generate(self, streams: List, aif_paths: List[str]) -> str:
        """
        Genera il contenuto .rpp come stringa.

        Args:
            streams: lista di Stream (con stream_id, onset, duration)
            aif_paths: lista di path .aif, uno per stream (stesso ordine)

        Returns:
            Stringa con il contenuto del file .rpp

        Raises:
            ValueError: se len(streams) != len(aif_paths)
        """
        if len(streams) != len(aif_paths):
            raise ValueError(
                f"streams ({len(streams)}) e aif_paths ({len(aif_paths)}) "
                "devono avere la stessa lunghezza"
            )

        lines = [f"<REAPER_PROJECT {self.REAPER_VERSION}"]

        for stream, aif_path in zip(streams, aif_paths):
            lines += self._track_lines(stream, aif_path)

        lines.append(">")
        return "\n".join(lines) + "\n"

    def write(self, streams: List, aif_paths: List[str], output_path: str) -> None:
        """
        Scrive il file .rpp su disco.

        Args:
            streams: lista di Stream
            aif_paths: lista di path .aif, uno per stream
            output_path: path del file .rpp da creare
        """
        content = self.generate(streams, aif_paths)
        with open(output_path, 'w') as f:
            f.write(content)

    # =========================================================================
    # INTERNAL
    # =========================================================================

    def _track_lines(self, stream, aif_path: str) -> List[str]:
        """Genera le righe per un singolo TRACK."""
        return [
            "  <TRACK",
            f'    NAME "{stream.stream_id}"',
            "    <ITEM",
            f"      POSITION {stream.onset}",
            f"      LENGTH {stream.duration}",
            "      <SOURCE WAVE",
            f'        FILE "{aif_path}"',
            "      >",
            "    >",
            "  >",
        ]
