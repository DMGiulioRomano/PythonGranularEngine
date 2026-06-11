# src/export/grain_json_writer.py
"""
GrainJsonWriter

Esporta i grani di uno stream in JSON, consumabile da un client di
visualizzazione (PGE-ui) per disegnare i rettangoli dei grani nella clip
timeline di ogni stream.

Responsabilita':
- build():    produce la struttura dati (dict) per uno stream
- generate(): serializza la struttura in JSON compatto (stringa)
- write():    scrive il file JSON su disco (un file per stream)

Schema JSON prodotto (compatto, senza whitespace):
  {
    "stream_id": "stream1",
    "duration": 8.0,
    "num_voices": 4,
    "grains": [
      {"t": 0.0, "dur": 0.08, "vol": -6.0, "ptr": 0.34, "v": 0},
      ...
    ]
  }

Campi grano:
  t   = grain.onset - stream.onset  (onset relativo all'inizio dello stream;
        puo' essere < 0 con onset offset per-voce: dato valido)
  dur = grain.duration
  vol = grain.volume
  ptr = grain.pointer_pos  (unita' variabile per stream: secondi o frazione)
  v   = indice voce (da stream.voices)

I grani sono ordinati per t crescente. num_voices riflette il numero di voci
effettivamente generate (len(stream.voices)).
"""

import json
import os
from pathlib import Path


class GrainJsonWriter:
    """
    Esporta i grani di uno stream in un file JSON.

    Itera stream.voices (List[List[Grain]]) per preservare l'indice voce,
    che il flat stream.grains perderebbe.
    """

    def build(self, stream) -> dict:
        """
        Produce la struttura dati JSON-serializzabile per uno stream.

        Args:
            stream: Stream con stream_id, onset, duration, voices

        Returns:
            dict con stream_id, duration, num_voices, grains (ordinati per t)
        """
        grains = []
        for voice_index, voice in enumerate(stream.voices):
            for grain in voice:
                grains.append({
                    "t": grain.onset - stream.onset,
                    "dur": grain.duration,
                    "vol": grain.volume,
                    "ptr": grain.pointer_pos,
                    "v": voice_index,
                })

        grains.sort(key=lambda g: g["t"])

        return {
            "stream_id": stream.stream_id,
            "duration": stream.duration,
            "num_voices": len(stream.voices),
            "grains": grains,
        }

    def generate(self, stream) -> str:
        """Serializza la struttura di build() in JSON compatto (no whitespace)."""
        return json.dumps(self.build(stream), separators=(",", ":"))

    def write(self, stream, output_dir: str, yaml_basename: str) -> Path:
        """
        Scrive il file JSON dei grani su disco.

        Args:
            stream: Stream da esportare
            output_dir: directory di output (creata se assente)
            yaml_basename: basename del file YAML, usato nel nome file

        Returns:
            Path del file JSON scritto:
            {output_dir}/{yaml_basename}__{stream_id}__grains.json
        """
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{yaml_basename}__{stream.stream_id}__grains.json"
        path = Path(output_dir) / filename
        with open(path, "w") as f:
            f.write(self.generate(stream))
        return path
