# src/export/sv_exporter.py
"""
SVExporter — terzo renderer della IR (issue #150).

Esporta una sessione Sonic Visualiser (.sv) dagli stream granulari: gli envelope
della IR diventano layer visuali (timevalues) sincronizzati frame-per-frame con
la waveform dell'audio renderizzato. Il file si apre direttamente in SV, con
pannelli gia' configurati, senza import manuale.

Responsabilita':
- build():    costruisce l'albero XML SV (ElementTree) — single point of truth
- generate(): serializza in XML + comprime bzip2 (formato .sv)
- export():   scrive il .sv su disco

Formato .sv: XML bzip2, <sv><data>(model/dataset/layer)</data><display>(view)</display></sv>.
Struttura validata contro sessioni reali prodotte da Sonic Visualiser.

Punti chiave (vs. il prototipo granulation-studies):
- Gli Envelope arrivano dalla IR viva via envelope_extractor.get_stream_envelopes
  (semantica dei parametri preservata), non riparsando lo YAML.
- I breakpoint sono RELATIVI allo stream: il frame e' assoluto sul timeline
  globale, `round((stream.onset + t_rel) * sample_rate)`. L'offset onset e'
  obbligatorio in MIX (un audio per N stream).
- I colori dei layer vengono da ENVELOPE_COLORS (palette dell'engine).
- Il sample rate e la durata si leggono dall'header dell'audio renderizzato.

Scope v1: MIX (un file audio -> un .sv). STEMS multi-file: follow-up.
"""
from __future__ import annotations

import bz2
import os
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

from rendering.envelope_extractor import (
    ENVELOPE_COLORS,
    base_param_name,
    get_stream_envelopes,
)

# plotStyle SV per tipo di interpolazione dell'Envelope. I valori sono gli
# interi dell'enum PlotStyle di TimeValueLayer (svgui), serializzati come stringa
# nell'attributo plotStyle del layer:
#   "3" = PlotLines        -> spezzata di segmenti retti tra i breakpoint
#   "7" = PlotCubicHermite -> curva cubica monotona (Fritsch-Carlson)
# 'step' non ha uno stile nativo in SV (nessun hold del valore fino al
# breakpoint successivo): fallback su Lines finche' la visualizzazione a gradini
# non viene aggiunta a TimeValueLayer.
_PLOT_STYLE_BY_TYPE = {"linear": "3", "cubic": "7", "step": "3"}
_PLOT_STYLE_DEFAULT = "3"


def _envelope_plot_style(envelope) -> str:
    """plotStyle SV dal tipo di interpolazione dell'Envelope.

    Legge `envelope.type` (sempre presente, default 'linear'). SV ha un
    plotStyle per-layer, quindi il tipo globale dell'envelope e' la giusta
    granularita'; eventuali override per-segmento non sono rappresentabili.
    """
    return _PLOT_STYLE_BY_TYPE.get(getattr(envelope, "type", "linear"),
                                   _PLOT_STYLE_DEFAULT)

# Colore di fallback per chiavi senza voce in ENVELOPE_COLORS (non dovrebbe
# accadere: l'universo dei nomi e' PLOT_ENVELOPE_KEYS).
_FALLBACK_COLOUR = "#cccccc"

# Geometria della finestra/pannelli (costanti dal layout validato in SV).
_WINDOW_W, _WINDOW_H = 1728, 1057
_PANE_AREA = 912
_PANE_MIN = 150

_VIEW_ATTRS = {
    "centre": "0", "zoom": "1024", "deepZoom": "1",
    "followPan": "1", "followZoom": "1", "tracking": "page",
    "type": "pane", "centreLineVisible": "1",
}


def _fmt_value(v) -> str:
    """Formatta un valore Y: intero senza '.0', altrimenti float pieno."""
    f = float(v)
    return str(int(f)) if f == int(f) else repr(f)


class SVExporter:
    """Esporta stream granulari in una sessione Sonic Visualiser (.sv)."""

    def export(self, streams: List, audio_path: str, out_path: str,
               layout: str = "multi", sample_rate: Optional[int] = None,
               duration_sec: Optional[float] = None) -> str:
        """
        Scrive il file .sv su disco.

        Args:
            streams: lista di Stream con la IR popolata.
            audio_path: path dell'audio renderizzato (referenziato dal .sv).
            out_path: path del file .sv da creare.
            layout: 'multi' (un pannello per envelope) o 'single' (tutti in uno).
            sample_rate / duration_sec: se None, letti dall'header dell'audio.

        Returns:
            out_path.
        """
        blob = self.generate(streams, audio_path, layout=layout,
                             sample_rate=sample_rate, duration_sec=duration_sec)
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "wb") as fh:
            fh.write(blob)
        return out_path

    def generate(self, streams: List, audio_path: str, layout: str = "multi",
                 sample_rate: Optional[int] = None,
                 duration_sec: Optional[float] = None) -> bytes:
        """Serializza l'albero SV in XML + bzip2 (contenuto del .sv)."""
        root = self.build(streams, audio_path, sample_rate=sample_rate,
                          duration_sec=duration_sec, layout=layout)
        xml = b'<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += b'<!DOCTYPE sonic-visualiser>\n'
        xml += ET.tostring(root, encoding="unicode").encode("utf-8")
        return bz2.compress(xml)

    def build(self, streams: List, audio_path: str,
              sample_rate: Optional[int] = None,
              duration_sec: Optional[float] = None,
              layout: str = "multi") -> ET.Element:
        """Costruisce l'albero XML SV (ElementTree.Element root <sv>)."""
        if sample_rate is None or duration_sec is None:
            sample_rate, duration_sec = self._read_audio_info(audio_path)

        # Raccogli gli envelope di tutti gli stream (MIX): per ogni curva il
        # nome (disambiguato per stream se >1), la chiave engine (per il colore)
        # e i punti gia' in frame assoluti.
        layers = self._collect_layers(streams, sample_rate)

        root = ET.Element("sv")
        data = ET.SubElement(root, "data")
        end_frame = round(duration_sec * sample_rate)

        # --- Modello audio + chrome fisso (ruler + waveform) ---
        ET.SubElement(data, "model", {
            "id": "0", "name": os.path.basename(audio_path),
            "sampleRate": str(sample_rate), "start": "0", "end": str(end_frame),
            "type": "wavefile", "file": os.path.abspath(audio_path),
            "mainModel": "true",
        })
        ET.SubElement(data, "playparameters", {
            "mute": "false", "pan": "0", "gain": "1", "clipId": "", "model": "0",
        })
        ET.SubElement(data, "layer", {
            "id": "1", "type": "timeruler", "name": "Ruler", "model": "0",
            "colourName": "White", "colour": "#ffffff", "darkBackground": "true",
        })
        ET.SubElement(data, "layer", {
            "id": "2", "type": "waveform", "name": "Waveform", "model": "0",
            "gain": "1", "showMeans": "1", "greyscale": "1", "channelMode": "0",
            "channel": "-1", "scale": "0", "middleLineHeight": "0.5",
            "aggressive": "0", "autoNormalize": "0", "oversampling": "1",
            "colourName": "Bright Blue", "colour": "#1e96ff",
            "darkBackground": "true",
        })

        # --- Un modello + dataset + layer per ogni envelope ---
        layer_records: List[Tuple[str, str, str]] = []  # (layer_id, model_id, name)
        next_id = 3
        for name, key, points, plot_style in layers:
            model_id = str(next_id); next_id += 1
            dataset_id = str(next_id); next_id += 1
            layer_id = str(next_id); next_id += 1

            ET.SubElement(data, "model", {
                "id": model_id, "name": name, "sampleRate": str(sample_rate),
                "type": "sparse", "dimensions": "2", "resolution": "1",
                "notifyOnAdd": "true", "dataset": dataset_id,
            })
            ds = ET.SubElement(data, "dataset", {"id": dataset_id, "dimensions": "2"})
            for frame, value in points:
                ET.SubElement(ds, "point", {
                    "frame": str(frame), "value": _fmt_value(value), "label": "",
                })

            # Colore dalla CHIAVE engine (non dal nome, che con piu' stream e'
            # prefissato '<stream_id>/'): altrimenti il lookup fallirebbe e ogni
            # layer cadrebbe sul fallback.
            colour = ENVELOPE_COLORS.get(base_param_name(key), _FALLBACK_COLOUR)
            ET.SubElement(data, "layer", {
                "id": layer_id, "type": "timevalues", "name": name,
                "model": model_id, "plotStyle": plot_style, "verticalScale": "0",
                "colourName": name, "colour": colour, "darkBackground": "true",
            })
            layer_records.append((layer_id, model_id, name))

        # --- Display: pannelli (view) ---
        self._build_display(root, layer_records, layout)

        ET.SubElement(root, "selections")
        return root

    # =========================================================================
    # INTERNAL
    # =========================================================================

    def _read_audio_info(self, audio_path: str) -> Tuple[int, float]:
        """Sample rate e durata dall'header dell'audio (soundfile, no decode)."""
        import soundfile as sf
        info = sf.info(audio_path)
        return info.samplerate, info.frames / float(info.samplerate)

    def _collect_layers(self, streams: List, sample_rate: int
                        ) -> List[Tuple[str, str, List[Tuple[int, float]], str]]:
        """
        Per ogni stream estrae gli envelope dinamici e converte i breakpoint in
        frame assoluti: frame = round((stream.onset + t_rel) * sample_rate).

        Ritorna tuple (name, key, points, plot_style): `key` e' la chiave engine
        (es. 'density', per il colore); `name` e' il nome del layer, disambiguato
        col prefisso '<stream_id>/' quando c'e' piu' di uno stream (evita
        collisioni); `plot_style` e' lo stile SV dal tipo di interpolazione.
        """
        multi_stream = len(streams) > 1
        layers: List[Tuple[str, str, List[Tuple[int, float]], str]] = []
        for stream in streams:
            onset = float(getattr(stream, "onset", 0.0) or 0.0)
            envelopes = get_stream_envelopes(stream)
            for key, envelope in envelopes.items():
                name = f"{stream.stream_id}/{key}" if multi_stream else key
                points = [
                    (round((onset + t_rel) * sample_rate), value)
                    for t_rel, value in envelope.breakpoints
                ]
                layers.append((name, key, points, _envelope_plot_style(envelope)))
        return layers

    def _build_display(self, root: ET.Element,
                       layer_records: List[Tuple[str, str, str]],
                       layout: str) -> None:
        display = ET.SubElement(root, "display")
        ET.SubElement(display, "window",
                      {"width": str(_WINDOW_W), "height": str(_WINDOW_H)})

        n_env = len(layer_records)
        n_panes = 1 + (1 if layout == "single" else n_env)
        pane_height = str(max(_PANE_MIN, _PANE_AREA // n_panes))

        def _pane() -> ET.Element:
            return ET.SubElement(display, "view",
                                 {**_VIEW_ATTRS, "height": pane_height})

        def _ruler(pane: ET.Element) -> None:
            ET.SubElement(pane, "layer", {
                "id": "1", "type": "timeruler", "name": "Ruler",
                "model": "0", "visible": "true",
            })

        # Pannello waveform
        wf_pane = _pane()
        _ruler(wf_pane)
        ET.SubElement(wf_pane, "layer", {
            "id": "2", "type": "waveform", "name": "Waveform",
            "model": "0", "visible": "true",
        })

        def _env_layer(pane: ET.Element, rec: Tuple[str, str, str]) -> None:
            layer_id, model_id, name = rec
            ET.SubElement(pane, "layer", {
                "id": layer_id, "type": "timevalues", "name": name,
                "model": model_id, "visible": "true",
            })

        if layout == "single":
            env_pane = _pane()
            _ruler(env_pane)
            for rec in layer_records:
                _env_layer(env_pane, rec)
        else:  # multi: un pannello per envelope
            for rec in layer_records:
                pane = _pane()
                _ruler(pane)
                _env_layer(pane, rec)
