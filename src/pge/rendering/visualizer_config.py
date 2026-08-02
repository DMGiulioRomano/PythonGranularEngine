# src/pge/rendering/visualizer_config.py
"""
Lo schema della configurazione di ScoreVisualizer.

Quali chiavi esistono, che valore hanno di default, e come si combinano con
quelle passate dall'utente.

Prima erano 160 righe di dizionario dentro __init__. Il guadagno non e' la
lunghezza: un dizionario non dichiara niente, quindi una chiave sbagliata
passava in silenzio e un override parziale di un gruppo annidato ne cancellava
il resto.

Il risultato resta un dict. `ScoreVisualizer(generator, config={...})` e
`viz.config` sono superficie pubblica — api.py, la CLI e gli esempi del paper
li usano — e sostituirne il tipo costerebbe decine di modifiche per un
guadagno estetico. E' lo schema a essere dichiarato, non il tipo che circola.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass, replace
from typing import Optional

from pge.shared.constants import DEFAULT_OUTPUT_SR
from pge.rendering.envelope_extractor import ENVELOPE_COLORS


# =============================================================================
# GRUPPI ANNIDATI
# =============================================================================

@dataclass(frozen=True)
class PitchColorAutozoom:
    """Auto-zoom del range colore del pitch (issue #95).

    Normalizza sul min/max in cent dei grani visibili invece che sul range
    fisso: rende visibile il micro-detune di pochi cent.
    """
    enabled: bool = True
    pad_ratio: float = 0.1
    # Floor di un semitono. Senza, una manciata di cent di scarto reale
    # produrrebbe un gradiente esagerato — l'intera colormap — per una
    # differenza musicalmente trascurabile.
    min_span_cents: float = 50.0


@dataclass(frozen=True)
class EnvelopeDisplay:
    """Scaling data-driven delle curve envelope (issue #114)."""
    pad_ratio: float = 0.05     # margine sopra/sotto: 5% dell'escursione
    samples: int = 128          # densita' di campionamento (cattura l'overshoot cubic)


@dataclass(frozen=True)
class MagnifyDefaults:
    """Valori di partenza di ogni lente, sovrascrivibili per singolo target."""
    zoom: float = 8.0                    # ingrandimento del contenuto
    out: float = 0.12                    # raggio del cerchio di USCITA (frazione min figura)
    src: Optional[float] = None          # raggio del cerchio di PARTENZA; None = out/zoom
    corner: str = 'top-right'            # angolo del subplot dove proiettare


# Range fissi dei parametri. Dopo issue #114 (scaling data-driven) solo 'pan'
# e' ancora consultato per lo scaling delle curve, essendo ciclico; le altre
# entry restano per riferimento e retrocompatibilita'.
ENVELOPE_RANGES = {
    # === OUTPUT ===
    'volume': (-90, 0),                  # dB
    'volume_prob': (0, 100),             # probabilita' %
    'pan': (-180, 180),                  # gradi (ciclico)
    'pan_prob': (0, 100),

    # === GRAIN ===
    'grain_duration': (1.0 / DEFAULT_OUTPUT_SR, 1.0),   # secondi (min 1 campione)
    'grain_duration_prob': (0, 100),
    'reverse': (0, 1),
    'reverse_prob': (0, 100),

    # === POINTER ===
    'pointer_start': (0.0, 1.0),         # normalizzato
    'pointer_speed': (-4.0, 16.0),
    'pointer_deviation': (0.0, 1.0),     # normalizzato
    'pointer_deviation_prob': (0, 100),
    'loop_dur': (0.001, 10.0),           # secondi
    # NOTA: pitch e' unit-driven; i bounds vengono da
    # stream.pitch_unit.value_bounds(), non da un range statico qui.

    # === DENSITY ===
    'density': (1, 200),                 # grani/sec
    'fill_factor': (0.1, 20),
    'distribution': (0, 1),
    'effective_density': (1, 200),

    # === VOICES ===
    'num_voices': (1, 20),
    'scatter': (0.0, 1.0),               # normalizzato (cluster -> spread)
    'voice_pitch_offset': (-48, 48),     # semitoni
    'voice_pointer_offset': (-1.0, 1.0), # normalizzato
    'voice_pointer_range': (0.0, 1.0),   # normalizzato
}


# =============================================================================
# LO SCHEMA
# =============================================================================

@dataclass(frozen=True)
class VisualizerConfig:
    """La configurazione del visualizer, dichiarata.

    I campi sono raggruppati per natura: cosa mostrare, dove metterlo, che
    aspetto dargli. Nel dizionario stavano tutti mescolati.
    """

    # --- COSA MOSTRARE -------------------------------------------------------
    # Directory dei sample per waveform e durate; None -> fallback su PATHSAMPLES.
    samples_dir: Optional[str] = None
    show_static_params: bool = False      # include anche i valori costanti
    # Offset per-voce come curve separate (issue #90). Gating indipendente da
    # show_static_params.
    show_voice_offsets: bool = False
    # None = tutti gli envelope; altrimenti set/lista di nomi (issue #101).
    envelope_filter: Optional[object] = None

    # --- PAGINAZIONE ---------------------------------------------------------
    page_duration: float = 30.0           # secondi per pagina
    page_size: tuple = (420, 297)         # A3 in mm
    orientation: str = 'landscape'
    margins_mm: float = 20

    # --- GRANI ---------------------------------------------------------------
    grain_colormap: object = 'pitch_div'  # pitch_ratio -> colore (divergente)
    grain_alpha_range: tuple = (0.3, 1.0)         # volume -> alpha
    pitch_range: tuple = (0.5, 2.0)               # fallback senza autozoom
    pitch_color_autozoom: PitchColorAutozoom = PitchColorAutozoom()
    volume_range: tuple = (-60, 0)                # dB, per normalizzare l'alpha
    min_grain_width_pts: float = 1                # larghezza minima visibile
    # 'arrow' -> freccia direzionale (comportamento storico);
    # 'window' -> il bordo superiore traccia la curva della finestra del grano.
    # Senza, la finestra e' invisibile: due grani con envelope diversi hanno la
    # stessa freccia.
    grain_shape: str = 'arrow'
    # Punti con cui campionare la silhouette della finestra. La curva
    # normalizzata e' memoizzata per (nome, risoluzione): il costo per grano e'
    # solo una trasformazione affine dei vertici.
    window_shape_resolution: int = 32
    # Sotto questa larghezza in pixel la finestra non sarebbe leggibile e il
    # grano ripiega sulla freccia: e' il cap al costo vettoriale sugli score
    # densi.
    window_shape_min_px: float = 3

    # --- WAVEFORM E COLORBAR -------------------------------------------------
    waveform_alpha: float = 0.3
    waveform_color: str = 'steelblue'
    waveform_width_ratio: float = 0.06    # frazione della larghezza pagina
    waveform_downsample: int = 200        # 1 punto ogni N campioni
    # La colorbar del pitch vive in una colonna propria del GridSpec, cosi' i
    # subplot dei grani e quello degli envelope condividono la colonna centrale
    # e restano allineati sullo stesso bordo destro.
    colorbar_width_ratio: float = 0.02

    # --- LOOP MASK -----------------------------------------------------------
    loop_mask_color: str = '#f4a261'
    loop_mask_alpha: float = 0.18
    loop_mask_samples: int = 200          # punti del poligono

    # --- STILE ---------------------------------------------------------------
    stream_gap_ratio: float = 0.05        # gap fra stream (5% dell'altezza)
    label_fontsize: float = 8
    title_fontsize: float = 12
    breakpoint_fontsize: float = 6
    empty_fontsize: float = 14
    # Moltiplicatore applicato a TUTTE le fontsize (vedi ScoreVisualizer._fs).
    # 1.0 = invariato; alzarlo ingrandisce uniformemente assi, titolo, legenda e
    # annotazioni. Pensato per chi rigenera le figure per la stampa.
    font_scale: float = 1.0

    # --- ENVELOPE ------------------------------------------------------------
    envelope_ranges: dict = field(
        default_factory=lambda: deepcopy(ENVELOPE_RANGES))
    envelope_colors: dict = field(
        default_factory=lambda: dict(ENVELOPE_COLORS))
    # Frazione della banda di OGNI stream riservata alla sua riga envelope
    # (issue #113: un subplot envelope per stream, sotto i suoi grani).
    envelope_panel_ratio: float = 0.3
    envelope_display: EnvelopeDisplay = EnvelopeDisplay()

    # --- LENTE DI INGRANDIMENTO ----------------------------------------------
    # Spenta di default: a flag spenti la pagina e' identica a prima.
    magnify_auto: bool = False            # lente sul cluster piu' denso
    # Target espliciti: list[dict] con 't' obbligatorio e
    # y/zoom/out/src/stream/corner opzionali. Il corner per-target permette piu'
    # lenti non sovrapposte sullo stesso subplot.
    magnify_targets: list = field(default_factory=list)
    magnify_defaults: MagnifyDefaults = MagnifyDefaults()
    magnify_hist_bins: tuple = (40, 16)   # bin (tempo, posizione) per l'auto
    magnify_color: str = '#c1121f'        # marker sorgente e connettori

    # =========================================================================

    @classmethod
    def from_overrides(cls, overrides):
        """Configurazione con gli scarti dell'utente applicati sui default.

        I gruppi annidati si fondono campo per campo: un override parziale
        lascia in piedi il resto del gruppo. Con una sostituzione secca — che
        e' quello che fa dict.update — il primo che leggesse un campo non
        ridichiarato solleverebbe KeyError.
        """
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(overrides or {}) - known)
        if unknown:
            # Nominare le chiavi e' il punto: un errore generico lascerebbe a
            # cercarle fra le quaranta.
            raise ValueError(
                "chiavi di configurazione sconosciute per ScoreVisualizer: "
                + ", ".join(unknown))

        values = {}
        for name, value in (overrides or {}).items():
            default = getattr(cls, name, None)
            if is_dataclass(default) and isinstance(value, dict):
                value = replace(default, **value)
            elif isinstance(default, dict) and isinstance(value, dict):
                # Anche i dizionari-dato (envelope_ranges, envelope_colors) si
                # fondono: chi ne ritocca una entry non deve perdere le altre.
                merged = deepcopy(default)
                merged.update(value)
                value = merged
            values[name] = value
        return cls(**values)

    def as_dict(self):
        """La configurazione come dict, che e' cio' che il visualizer legge.

        Copia profonda: due visualizer non devono condividere strutture
        mutabili, e uno che ritocca i propri colori non deve cambiarli
        all'altro.
        """
        return {f.name: _as_plain(getattr(self, f.name)) for f in fields(self)}


def _as_plain(value):
    """Un gruppo dichiarato torna dict; i contenitori mutabili si copiano.

    Si copiano solo dict, list e set: sono quelli che due visualizer non devono
    condividere. Tutto il resto passa per riferimento — in particolare un
    oggetto Colormap passato dall'utente, che deve restare LO STESSO oggetto:
    copiarlo sarebbe sprecato e sorprendente.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _as_plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (dict, list, set)):
        return deepcopy(value)
    return value
