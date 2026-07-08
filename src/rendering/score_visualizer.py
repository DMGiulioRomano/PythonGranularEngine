# =============================================================================
# SCORE VISUALIZER - Partitura grafica per sintesi granulare
# =============================================================================

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.cm import ScalarMappable
from matplotlib.collections import PatchCollection
from matplotlib.colors import Normalize, Colormap, LinearSegmentedColormap
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import soundfile as sf
import re
from math import ceil

from shared.constants import DEFAULT_OUTPUT_SR

# Path samples (stesso del progetto)
PATHSAMPLES = './refs/'

# Colormap divergente per il pitch dei grani. Il pitch in cents e' una grandezza
# con segno centrata sullo zero (nessun detune = 0 cents): serve una mappa
# divergente con punto neutro al centro, non una sequenziale come turbo.
#   - centro (0 cents): grigio medio #777777 — NON bianco, perche' lo sfondo del
#     plot e' bianco e un grano neutro col centro bianco sparirebbe;
#   - braccio freddo (detune negativo): indaco -> blu;
#   - braccio caldo (detune positivo): arancio -> giallo.
# Bracci a due tinte (non un solo blu/rosso secco) per dare piu' gradazione
# cromatica all'escursione, mantenendo la lettura intuitiva freddo=cala /
# caldo=sale. L'autozoom (pitch_color_autozoom) riscala questa mappa
# sull'escursione reale dei cents: la normalizzazione resta invariata, cambia
# solo la mappa di colore.
PITCH_DIVERGING = LinearSegmentedColormap.from_list(
    'pitch_div', ['#3b1f8b', '#3a8fd6', '#777777', '#f08c00', '#f2d024']
)

# Registrazione con guardia: idempotente anche su re-import del modulo.
try:
    plt.get_cmap('pitch_div')
except (ValueError, KeyError):
    try:
        import matplotlib as mpl
        mpl.colormaps.register(PITCH_DIVERGING)
    except (AttributeError, ImportError):
        plt.register_cmap(cmap=PITCH_DIVERGING)

# Colori di default e universo dei nomi plottabili. Definiti nel modulo
# matplotlib-free rendering.envelope_extractor (issue #150) e ri-esportati qui
# per retro-compatibilita': main.py importa PLOT_ENVELOPE_KEYS da qui, i test
# importano ENVELOPE_COLORS da qui.
from rendering.envelope_extractor import ENVELOPE_COLORS, PLOT_ENVELOPE_KEYS  # noqa: F401,E402


class ScoreVisualizer:
    """
    Visualizzatore di partitura grafica per stream granulari.
    
    Genera una rappresentazione visiva dove:
    - Asse X: tempo della partitura
    - Asse Y: posizione nel sample (waveform verticale come riferimento)
    - Grani: rettangoli posizionati in base a onset/pointer_pos
    - Altezza grano: sample consumato (duration × pitch_ratio)
    - Larghezza grano: durata temporale
    - Colore: pitch_ratio (gradiente)
    - Opacità: volume
    """
    
    def __init__(self, generator, config=None):
        """
        Args:
            generator: oggetto Generator già processato (con streams popolati)
            config: dict di configurazione (opzionale)
        """
        self.generator = generator
        self.streams = generator.streams
        
        # Configurazione con defaults
        default_config = {
            # Directory dei sample audio per waveform/durate (Fase 2 refactor
            # library/CLI). None -> fallback sul globale PATHSAMPLES.
            'samples_dir': None,
            # Se True, mostra anche i valori costanti
            'show_static_params': False,
            # Se True, disegna gli offset per-voce (voice_pitch_offset /
            # voice_pointer_offset come una curva per voce, voice_pointer_range
            # come curva singola dello spread). Fase 3 issue #90. Gating
            # indipendente da show_static_params.
            'show_voice_offsets': False,
            # Filtro selettivo: None = tutti gli envelope; altrimenti set/lista
            # di nomi — solo quelli elencati vengono plottati (issue #101)
            'envelope_filter': None,
            # Paginazione
            'page_duration': 30.0,           # secondi per pagina
            'page_size': (420, 297),         # A3 in mm
            'orientation': 'landscape',
            'margins_mm': 20,
            
            # Grani
            'grain_colormap': 'pitch_div',   # pitch_ratio → colore (divergente)
            'grain_alpha_range': (0.3, 1.0), # volume → alpha
            'pitch_range': (0.5, 2.0),       # range fisso (fallback senza autozoom)
            # Auto-zoom del range colore pitch: normalizza sul min/max in cents
            # dei grani visibili nel subplot (sample+pagina) invece del range
            # fisso — rende visibile il micro-detune ±6 cents (issue #95).
            'pitch_color_autozoom': {
                'enabled': True,
                'pad_ratio': 0.1,        # margine per lato: 10% dello span
                # floor: 1 semitono. Senza questo minimo, una manciata di
                # cents di scarto reale produrrebbe uno span quasi nullo e
                # quindi un gradiente di colore esagerato (l'intera colormap)
                # per una differenza musicalmente trascurabile.
                'min_span_cents': 50.0,
            },
            'volume_range': (-60, 0),        # dB range per normalizzare alpha
            'min_grain_width_pts': 1,        # larghezza minima visibile
            # Forma del grano nella partitura:
            #   'arrow'  -> freccia direzionale (default, comportamento storico);
            #   'window' -> il bordo superiore ("testa") traccia la curva della
            #               finestra/envelope del grano, base piatta sul pointer.
            # La finestra e' altrimenti invisibile nella partitura: due grani con
            # envelope diversi (hanning vs expodec) hanno la stessa freccia.
            'grain_shape': 'arrow',
            # Numero di punti con cui campionare la curva della finestra per la
            # silhouette (solo grain_shape='window'). La silhouette normalizzata
            # e' precalcolata e cachata per (nome, risoluzione): il costo per
            # grano e' solo una trasformazione affine dei vertici.
            'window_shape_resolution': 32,
            # Soglia adattiva: se la larghezza del grano sulla pagina e' sotto
            # questo numero di pixel, la finestra non sarebbe leggibile e il
            # grano ripiega sulla freccia a 5 vertici (cap al costo vettoriale
            # sugli score densi).
            'window_shape_min_px': 3,
            
            # Waveform
            'waveform_alpha': 0.3,
            'waveform_color': 'steelblue',
            'waveform_width_ratio': 0.06,    # 3% della larghezza pagina
            'waveform_downsample': 200,      # 1 punto ogni N campioni
            # Larghezza (frazione della pagina) della colonna dedicata alla
            # colorbar del pitch. Vive in una colonna propria del GridSpec cosi'
            # i subplot dei grani e quello degli envelope condividono la colonna
            # centrale -> stesso bordo destro, niente piu' disallineamento (la
            # colorbar non ruba larghezza ai soli stream).
            'colorbar_width_ratio': 0.02,
            # Loop mask
            'loop_mask_color': '#f4a261',    # arancio caldo
            'loop_mask_alpha': 0.18,
            'loop_mask_samples': 200,        # punti di campionamento del poligono

            # Stile
            'stream_gap_ratio': 0.05,        # gap tra stream (5% dell'altezza)
            'label_fontsize': 8,
            'title_fontsize': 12,
            # Dimensioni font prima hardcoded, ora configurabili: annotazione
            # dei breakpoint envelope e testo della pagina vuota.
            'breakpoint_fontsize': 6,
            'empty_fontsize': 14,
            # Moltiplicatore globale applicato a TUTTE le fontsize del
            # visualizer (vedi _fs): 1.0 = comportamento invariato; alzarlo
            # ingrandisce uniformemente assi, titolo, legenda, annotazioni.
            # Pensato per chi rigenera le figure per la stampa (es. il paper).
            'font_scale': 1.0,
            # Envelope ranges. Dopo issue #114 (scaling data-driven) solo 'pan'
            # è ancora consultato per lo scaling delle curve (ciclico, ±180);
            # le altre entry restano per riferimento/back-compat, non più usate.
            'envelope_ranges': {
                # === OUTPUT ===
                'volume': (-90, 0),           # dB
                'volume_prob': (0, 100),      # probabilità %
                'pan': (-180, 180),           # gradi (ciclico)
                'pan_prob': (0, 100),         # probabilità %
                
                # === GRAIN ===
                'grain_duration': (1.0 / DEFAULT_OUTPUT_SR, 1.0),  # secondi (min 1 campione)
                'grain_duration_prob': (0, 100),  # probabilità %
                'reverse': (0, 1),            # boolean
                'reverse_prob': (0, 100),     # probabilità %
                
                # === POINTER ===
                'pointer_start': (0.0, 1.0),  # normalizzato
                'pointer_speed': (-4.0, 16.0),
                'pointer_deviation': (0.0, 1.0),  # normalizzato
                'pointer_deviation_prob': (0, 100),  # probabilità %
                'loop_dur': (0.001, 10.0),    # secondi
                # NOTA: pitch è unit-driven (chiave 'pitch'); i bounds vengono da
                # stream.pitch_unit.value_bounds(), non da range statici qui.

                # === DENSITY ===
                'density': (1, 200),          # grani/sec
                'fill_factor': (0.1, 20),
                'distribution': (0, 1),
                'effective_density': (1, 200),
                
                # === VOICES ===
                'num_voices': (1, 20),
                'scatter': (0.0, 1.0),        # normalizzato (cluster→spread)
                'voice_pitch_offset': (-48, 48),  # semitoni
                'voice_pointer_offset': (-1.0, 1.0),  # normalizzato
                'voice_pointer_range': (0.0, 1.0),    # normalizzato
            },

            'envelope_colors': dict(ENVELOPE_COLORS),
            'envelope_panel_ratio': 0.3,      # 30% altezza per envelope

            # Scaling data-driven puro delle curve envelope (issue #114): ogni
            # curva scala sull'escursione reale dei suoi valori nella finestra
            # visibile (min/max + padding), senza alcun clamp ai range fissi.
            # Si applica a tutti i parametri; pan resta ciclico (escluso).
            'envelope_display': {
                'pad_ratio': 0.05,      # margine sopra/sotto: 5% dell'escursione
                'samples': 128,         # densità campionamento (cattura overshoot cubic)
            },

            # === LENTE DI INGRANDIMENTO (magnify) ===
            # Proietta un cerchio che ingrandisce una regione del piano
            # tempo×posizione di lettura, con connettori verso la sorgente.
            # Default disattivata: a flag spenti render_page è identico a prima.
            'magnify_auto': False,        # lente automatica sul cluster più denso
            'magnify_targets': [],        # target espliciti: list[dict]
                                          # (t obbligatorio; y/zoom/out/src/stream/corner opz.)
                                          # corner per-target -> piu' lenti non
                                          # sovrapposte sullo stesso subplot
            'magnify_defaults': {
                'zoom': 8.0,              # fattore di ingrandimento del contenuto
                'out': 0.12,              # raggio cerchio di USCITA (frazione min figura)
                'src': None,              # raggio cerchio di PARTENZA; None = out/zoom
                'corner': 'top-right',    # angolo del subplot dove proiettare la lente
            },
            'magnify_hist_bins': (40, 16),  # bin (tempo, posizione) per auto-densest
            'magnify_color': '#c1121f',   # colore marker sorgente + connettori
        }

        self.config = default_config
        if config:
            self.config.update(config)

        # Directory sample effettiva: config esplicita o fallback globale
        # (deprecato, mantenuto per compatibilita' coi monkey-patch esterni).
        self.samples_dir = self.config['samples_dir'] or PATHSAMPLES

        # Cache waveform
        self.waveform_cache = {}

        # Cache silhouette finestra normalizzata, chiave (nome, risoluzione).
        # Popolata lazy da _window_silhouette; il registry NumPy e' creato al
        # primo uso (solo con grain_shape='window').
        self._window_silhouette_cache = {}
        self._window_registry = None
        
        # Dati calcolati
        self.total_duration = None
        self.page_count = None
        self.page_layouts = []
        
        # Colormap. grain_colormap accetta sia una stringa (nome registrato,
        # incluso 'pitch_div') sia un oggetto Colormap gia' costruito.
        cmap_cfg = self.config['grain_colormap']
        self.cmap = cmap_cfg if isinstance(cmap_cfg, Colormap) else plt.get_cmap(cmap_cfg)

    def _fs(self, base):
        """Scala una dimensione font base per il moltiplicatore globale
        font_scale. Tutte le fontsize del visualizer passano di qui, così un
        unico parametro le ingrandisce in modo coerente (default 1.0 =
        invariato)."""
        return base * self.config['font_scale']

    # =========================================================================
    # ANALISI STRUTTURA
    # =========================================================================
    
    def analyze(self):
        """Analizza la struttura temporale di tutti gli stream."""
        
        if not self.streams:
            raise ValueError("Nessuno stream da visualizzare")
        
        # 1. Calcola durata totale
        self.total_duration = max(
            s.onset + s.duration for s in self.streams
        )
    
        # 2. Calcola numero pagine
        page_dur = self.config['page_duration']
        self.page_count = ceil(self.total_duration / page_dur)
        
        # 3. Per ogni pagina, calcola layout
        self.page_layouts = []
        
        for page_idx in range(self.page_count):
            page_start = page_idx * page_dur
            page_end = page_start + page_dur
            
            # Stream attivi in questa pagina
            active_streams = self._find_active_streams(page_start, page_end)
            
            if not active_streams:
                # Pagina vuota (possibile se ci sono buchi)
                self.page_layouts.append({
                    'page_idx': page_idx,
                    'time_range': (page_start, page_end),
                    'active_streams': [],
                    'max_concurrent': 0,
                    'slot_assignments': {},
                })
                continue
            
            # Calcola max simultanei
            max_concurrent = self._calculate_max_concurrent(
                active_streams, page_start, page_end
            )
            
            # Assegna slot verticali
            slot_assignments = self._assign_vertical_slots(
                active_streams, page_start, page_end
            )
            
            self.page_layouts.append({
                'page_idx': page_idx,
                'time_range': (page_start, page_end),
                'active_streams': active_streams,
                'max_concurrent': max(max_concurrent, len(set(slot_assignments.values()))),
                'slot_assignments': slot_assignments,
            })
        
        print(f"Analisi completata: {self.page_count} pagine, "
              f"durata totale {self.total_duration:.2f}s")
    
    def _find_active_streams(self, page_start, page_end):
        """Trova stream che intersecano l'intervallo della pagina."""
        active = []
        for stream in self.streams:
            stream_start = stream.onset
            stream_end = stream.onset + stream.duration
            
            # Intersezione?
            if stream_start < page_end and stream_end > page_start:
                active.append(stream)
        
        return active
    
    def _calculate_max_concurrent(self, streams, page_start, page_end):
        """Sweep line per trovare max stream simultanei."""
        events = []
        for stream in streams:
            start = max(stream.onset, page_start)
            end = min(stream.onset + stream.duration, page_end)
            events.append((start, 1))   # START
            events.append((end, -1))    # END
        
        # Ordina: per tempo, poi END (-1) prima di START (+1)
        events.sort(key=lambda x: (x[0], x[1]))
        
        max_count = 0
        current_count = 0
        for time, delta in events:
            current_count += delta
            max_count = max(max_count, current_count)
        
        return max_count
    
    def _assign_vertical_slots(self, active_streams, page_start, page_end):
        """
        Assegna slot verticali agli stream usando algoritmo greedy.
        Gli stream che non si sovrappongono possono condividere lo stesso slot.
        """
        # Ordina per onset
        sorted_streams = sorted(active_streams, key=lambda s: s.onset)
        
        # slots[i] = tempo di fine dell'ultimo stream in quello slot
        slots = []
        assignments = {}
        
        for stream in sorted_streams:
            stream_start = stream.onset
            stream_end = stream.onset + stream.duration
            
            # Trova slot libero (il primo che termina prima dell'inizio di questo stream)
            assigned_slot = None
            for i, slot_end in enumerate(slots):
                if slot_end <= stream_start:
                    assigned_slot = i
                    slots[i] = stream_end
                    break
            
            # Se nessuno slot libero, creane uno nuovo
            if assigned_slot is None:
                assigned_slot = len(slots)
                slots.append(stream_end)
            
            assignments[stream.stream_id] = assigned_slot
        
        return assignments
    
    # =========================================================================
    # CARICAMENTO WAVEFORM
    # =========================================================================
    
    def _load_waveform(self, sample_path):
        """Carica e processa waveform per visualizzazione."""
        
        if sample_path in self.waveform_cache:
            return self.waveform_cache[sample_path]
        
        # Costruisci path completo (samples_dir iniettato o fallback globale)
        full_path = self.samples_dir + sample_path
        
        try:
            # Carica audio
            audio, sr = sf.read(full_path)
            
            # Mono mix se stereo
            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)
            
            # Downsample per visualizzazione
            ds = self.config['waveform_downsample']
            audio_ds = audio[::ds]
            
            # Asse temporale
            duration = len(audio) / sr
            time_axis = np.linspace(0, duration, len(audio_ds))
            
            # Normalizza ampiezza
            max_amp = np.max(np.abs(audio_ds))
            if max_amp > 0:
                amplitude = audio_ds / max_amp
            else:
                amplitude = audio_ds
            
            result = (time_axis, amplitude, duration)
            self.waveform_cache[sample_path] = result
            return result
            
        except Exception as e:
            print(f"⚠️  Impossibile caricare waveform {sample_path}: {e}")
            # Ritorna waveform fittizia
            return (np.array([0, 1]), np.array([0, 0]), 1.0)
    
    def _get_sample_duration(self, sample_path):
        """Ottiene la durata del sample."""
        _, _, duration = self._load_waveform(sample_path)
        return duration
    
    # =========================================================================
    # MAPPING VISUALI
    # =========================================================================
    
    def _compute_pitch_color_range(self, streams, page_start, page_end):
        """
        Range colore pitch auto-zoomato per il subplot: (lo, hi) in cents
        calcolato sui grani visibili nella finestra di pagina di TUTTI gli
        stream del subplot. None se autozoom disabilitato o nessun grano
        (fallback al range fisso pitch_range).
        """
        az = self.config['pitch_color_autozoom']
        if not az.get('enabled', False):
            return None

        cents = []
        for stream in streams:
            for voice_grains in stream.voices:
                for g in voice_grains:
                    if not (g.onset < page_end and (g.onset + g.duration) > page_start):
                        continue
                    ratio = abs(g.pitch_ratio)
                    if ratio <= 0:
                        continue
                    cents.append(1200.0 * np.log2(ratio))

        if not cents:
            return None

        c_min, c_max = min(cents), max(cents)
        span = max(c_max - c_min, az['min_span_cents'])
        center = (c_min + c_max) / 2.0
        half = span / 2.0 + az['pad_ratio'] * span
        return (center - half, center + half)

    def _add_pitch_colorbar(self, fig, cax_spec, cents_range, streams,
                            page_start, page_end):
        """
        Colorbar compatta con la scala colore pitch del subplot, disegnata in una
        cella dedicata del GridSpec (cax_spec). Con un asse colorbar esplicito
        (cax=) invece di ax=, non viene rubata larghezza al subplot dei grani:
        grani ed envelope restano allineati sullo stesso bordo destro.

        Con cents_range (auto-zoom attivo): scala in cents zoomata.
        Senza: scala fissa pitch_range in ratio, solo se il subplot ha grani
        visibili (cents_range None copre anche il caso zero grani). Se non c'e'
        nulla da disegnare la cella resta vuota (nessun asse creato).
        """
        if cents_range is not None:
            norm = Normalize(cents_range[0], cents_range[1])
            label = 'pitch (cents)'
        else:
            has_grains = any(
                g.onset < page_end and (g.onset + g.duration) > page_start
                for s in streams
                for voice_grains in s.voices
                for g in voice_grains
            )
            if not has_grains:
                return
            p_min, p_max = self.config['pitch_range']
            norm = Normalize(p_min, p_max)
            label = 'pitch (ratio)'

        cax = fig.add_subplot(cax_spec)
        cbar = fig.colorbar(
            ScalarMappable(norm=norm, cmap=self.cmap), cax=cax
        )
        # Scarta i tick troppo vicini agli estremi del range: con colorbar
        # impilate (una per stream, hspace=0) il tick di fondo della colorbar
        # sopra e quello di testa della colorbar sotto cadono sullo stesso bordo
        # condiviso e si sovrappongono (es. '-30' e '30' -> '3030').
        span = norm.vmax - norm.vmin
        if span > 0:
            inner = [t for t in cbar.get_ticks()
                     if norm.vmin + 0.04 * span < t < norm.vmax - 0.04 * span]
            cbar.set_ticks(inner)
        cbar.set_label(label, fontsize=self._fs(self.config['label_fontsize'] - 1))
        cbar.ax.tick_params(labelsize=self._fs(self.config['label_fontsize'] - 2))
        # '<colorbar>' e' la convenzione matplotlib per gli assi colorbar (la
        # imposta make_axes con ax=...). Con cax= esplicito va messa a mano, cosi'
        # chi filtra gli assi colorbar (test, consumatori) continua a trovarli.
        cax.set_label('<colorbar>')

    def _pitch_to_color(self, pitch_ratio, cents_range=None):
        """
        Mappa pitch_ratio → colore dal colormap.

        cents_range=(lo, hi): normalizza 1200*log2(ratio) nel range zoomato
        (auto-zoom per-subplot). None: fallback sul range fisso pitch_range.
        """
        if cents_range is not None and pitch_ratio > 0:
            lo, hi = cents_range
            cents = 1200.0 * np.log2(pitch_ratio)
            normalized = (cents - lo) / (hi - lo)
        else:
            p_min, p_max = self.config['pitch_range']
            normalized = (pitch_ratio - p_min) / (p_max - p_min)
        normalized = np.clip(normalized, 0, 1)
        return self.cmap(normalized)
    
    def _volume_to_alpha(self, volume_db):
        """Mappa volume (dB) → alpha/opacità."""
        v_min, v_max = self.config['volume_range']
        normalized = (volume_db - v_min) / (v_max - v_min)
        normalized = np.clip(normalized, 0, 1)
        
        a_min, a_max = self.config['grain_alpha_range']
        return a_min + normalized * (a_max - a_min)
    
    # =========================================================================
    # RENDERING
    # =========================================================================

    def render_page(self, page_idx):
        """Renderizza pagina con subplot separati per ogni STREAM (non per sample).

        issue #109: ogni stream ottiene il proprio subplot anche quando piu'
        stream condividono lo stesso sample (la waveform viene ridisegnata in
        ciascuno). Cosi' 4 stream producono 4 subplot anche se due puntano allo
        stesso file, e le label non collidono piu' su un asse condiviso.
        """
        
        layout = self.page_layouts[page_idx]
        page_start, page_end = layout['time_range']
        active_streams = layout['active_streams']
        
        # Dimensioni figura (mm → inches)
        page_w_mm, page_h_mm = self.config['page_size']
        margin_mm = self.config['margins_mm']
        
        fig_w = page_w_mm / 25.4  # mm to inches
        fig_h = page_h_mm / 25.4
        
        # Crea figura
        fig = plt.figure(figsize=(fig_w, fig_h))
        
        # Verifica se ci sono envelope da mostrare
        has_envelopes = any(self._get_stream_envelopes(s) for s in active_streams)
        
        # =========================================================================
        # UN SUBPLOT PER STREAM (issue #109)
        # =========================================================================
        # Niente raggruppamento per sample: ogni stream ha il proprio subplot.
        # Stream che condividono lo stesso sample ottengono subplot separati e la
        # waveform viene ridisegnata in ciascuno (ridondanza accettabile per
        # leggibilita'); _load_waveform fa cache, quindi nessun re-read del file.
        n_streams = len(active_streams)

        if n_streams == 0:
            # Pagina vuota
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No active stream",
                    ha='center', va='center',
                    fontsize=self._fs(self.config['empty_fontsize']), color='gray')
            ax.axis('off')

            title = f"Page {page_idx + 1}/{self.page_count} — " \
                    f"[{page_start:.1f}s - {page_end:.1f}s]"
            fig.suptitle(title, fontsize=self._fs(self.config['title_fontsize']))
            return fig
        
        # =========================================================================
        # SETUP GRIDSPEC
        # =========================================================================
        # La colonna waveform ospita la y-label ruotata + i tick e (nella riga
        # envelope) la legenda con clip al bordo colonna: scala con font_scale
        # cosi' un testo piu' grande non viene croppato. A fs=1.0 e' identita'.
        fs = self.config['font_scale']
        waveform_ratio = self.config['waveform_width_ratio'] * fs
        colorbar_ratio = self.config['colorbar_width_ratio']
        envelope_ratio = self.config['envelope_panel_ratio'] if has_envelopes else 0.0

        # Altezza per stream (divisa equamente)
        stream_total_ratio = 1.0 - envelope_ratio
        stream_row_height = stream_total_ratio / n_streams

        # Crea height_ratios
        if has_envelopes:
            height_ratios = [stream_row_height] * n_streams + [envelope_ratio]
            n_rows = n_streams + 1
        else:
            height_ratios = [stream_row_height] * n_streams
            n_rows = n_streams

        # GridSpec: n_rows righe × 3 colonne [waveform, contenuto, colorbar].
        # La colorbar del pitch ha una colonna propria: i subplot dei grani e
        # quello degli envelope condividono la colonna centrale (stesso bordo
        # destro). Prima, fig.colorbar(ax=...) rubava larghezza ai soli grani e
        # il pannello envelope restava piu' largo, disallineato a destra.
        #
        # wspace=0: niente striscia di stacco verticale tra le colonne. La
        # waveform fa da righello attaccato al fianco sinistro della tela dei
        # grani (condividono l'asse Y = posizione di lettura) e la colorbar del
        # pitch e' attaccata al fianco destro.
        # Clamp difensivo: con font_scale estremi le colonne laterali non devono
        # fagocitare i grani. min_main = (3/7)*side tiene la quota del plot
        # centrale >= 30% della larghezza utile.
        side_ratio = waveform_ratio + colorbar_ratio
        main_ratio = max(1 - side_ratio, (3.0 / 7.0) * side_ratio)
        gs = fig.add_gridspec(
            n_rows, 3,
            width_ratios=[waveform_ratio, main_ratio, colorbar_ratio],
            height_ratios=height_ratios,
            wspace=0.0,
            hspace=0.0  # gap verticale tra stream
        )

        # Margini: il titolo sta appena sopra il plot (stacco quasi nullo). Lo
        # spazio vuoto residuo attorno alle parole (sinistra/destra/basso e sopra
        # il titolo) lo rifila bbox_inches='tight' in fase di export. Riservo in
        # alto solo l'altezza del titolo (in frazione di figura) + un gap minimo.
        fig_h_in = page_h_mm / 25.4
        title_h = (self._fs(self.config['title_fontsize']) / 72.0) / fig_h_in
        title_gap = 0.006  # stacco titolo-plot quasi nullo
        margin_ratio = margin_mm / page_w_mm
        fig.subplots_adjust(
            left=margin_ratio,
            right=1 - margin_ratio,
            bottom=margin_ratio,
            top=1.0 - title_h - 2 * title_gap
        )
        
        # =========================================================================
        # DISEGNA UN SUBPLOT PER OGNI STREAM
        # =========================================================================
        # Entry per stream raccolte per la lente di ingrandimento (magnify):
        # l'asse dei grani, la durata del sample e il range colore servono a
        # ridisegnare il contenuto zoomato nell'inset. Vuoto/inutilizzato quando
        # magnify è spenta.
        stream_entries = []
        for i, stream in enumerate(active_streams):
            # Crea subplot per questo stream
            ax_wave = fig.add_subplot(gs[i, 0])
            ax_grain = fig.add_subplot(gs[i, 1])

            # Sample e durata dello stream corrente
            sample_path = stream.sample
            sample_duration = self._get_sample_duration(sample_path)

            # Disegna waveform del sample dello stream (ridisegnata per ogni
            # subplot anche se il sample e' condiviso; _load_waveform fa cache).
            self._draw_waveform_full(ax_wave, stream, sample_duration)

            # Range colore pitch auto-zoomato sui grani di questo stream
            cents_range = self._compute_pitch_color_range(
                [stream], page_start, page_end)

            # Disegna grani, loop mask e label dello stream
            self._draw_loop_mask(ax_grain, stream, page_start, page_end, sample_duration)
            self._draw_grains_full(ax_grain, stream, sample_duration,
                                   page_start, page_end, cents_range)
            self._draw_stream_label_full(ax_grain, stream, page_start, sample_duration)

            stream_entries.append({
                'stream': stream,
                'ax': ax_grain,
                'sample_duration': sample_duration,
                'cents_range': cents_range,
            })

            # Legenda della scala colore pitch (auto-zoomata o fissa) nella
            # colonna dedicata gs[i, 2]: non ruba larghezza al subplot dei grani.
            self._add_pitch_colorbar(fig, gs[i, 2], cents_range,
                                     [stream], page_start, page_end)
            # Configura assi waveform
            ax_wave.set_ylim(-0.02, sample_duration+0.02)
            ax_wave.set_xlim(-1.1, 1.1)
            ax_wave.set_ylabel(f"Read position (s)\n{sample_path}",
                            fontsize=self._fs(self.config['label_fontsize']))
            ax_wave.set_xticks([])
            # Scarta i tick estremi dell'asse buffer: con le righe impilate
            # (hspace=0) l'inizio (0 s) di una riga e la fine dell'altra cadono
            # sul bordo condiviso e si sovrappongono. Tieni solo i tick interni.
            y_lo, y_hi = -0.02, sample_duration + 0.02
            y_span = y_hi - y_lo
            inner_yt = [t for t in ax_wave.get_yticks()
                        if y_lo + 0.04 * y_span < t < y_hi - 0.04 * y_span]
            ax_wave.set_yticks(inner_yt)
            ax_wave.set_ylim(-0.02, sample_duration+0.02)  # set_yticks puo' allargare l'ylim
            ax_wave.tick_params(axis='y', labelsize=self._fs(self.config['label_fontsize'] - 1))
            ax_wave.axvline(x=0, color='gray', linewidth=0.5, alpha=0.5, linestyle=':')
            ax_wave.grid(True, alpha=0.2, linestyle=':', axis='y')
            
            # Configura assi grani
            ax_grain.set_xlim(page_start, page_end)
            ax_grain.set_ylim(-0.02, sample_duration+0.02)
            ax_grain.set_ylabel("")  # label già nella waveform
            # L'asse del tempo del buffer e' descritto una sola volta, sulla
            # waveform a sinistra. Il subplot dei grani condivide lo stesso ylim
            # ma non ripete le etichette y (ridondanti): restano solo le tacche
            # di griglia, niente testo.
            ax_grain.tick_params(axis='y', labelleft=False, length=0)
            ax_grain.grid(True, alpha=0.3, linestyle='--')
            
            # X label solo sull'ultimo stream (se non ci sono envelope)
            if i == n_streams - 1 and not has_envelopes:
                ax_grain.set_xlabel("Time (s)", fontsize=self._fs(self.config['label_fontsize']))
            else:
                ax_grain.set_xticklabels([])
        
        # =========================================================================
        # SUBPLOT ENVELOPE (se presenti)
        # =========================================================================
        if has_envelopes:
            ax_env = fig.add_subplot(gs[n_streams, 1])

            # Layout condiviso lane/legenda (issue #91): stesso ordinamento e
            # stesse y, cosi' la legenda non appare mirrorata rispetto alle curve.
            lanes, legend_entries = self._compute_env_legend_layout(active_streams)

            for slot_idx, lane in enumerate(lanes):
                stream = lane['stream']
                y_base = lane['y_base']
                y_height = lane['y_height']

                # Disegna envelope in questa "corsia"
                self._draw_envelopes(ax_env, stream, y_base, y_height,
                                     page_start, page_end)

                # Label stream nella corsia envelope
                ax_env.text(
                    page_start + 0.3,
                    y_base + y_height * 0.5,
                    stream.stream_id,
                    fontsize=self._fs(self.config['label_fontsize'] - 2),
                    verticalalignment='center',
                    color='gray',
                    alpha=0.6
                )
                # ========== LINEE DIVISORIE ==========
                # Linea sopra questa corsia (non sulla prima)
                if slot_idx > 0:
                    ax_env.axhline(y=y_base - 0.02, color='darkgray',
                                   linewidth=1, alpha=0.4, linestyle='-')

            # Configura assi envelope
            ax_env.set_xlim(page_start, page_end)
            ax_env.set_ylim(0, 1)
            ax_env.set_xlabel("Time (s)", fontsize=self._fs(self.config['label_fontsize']))
            ax_env.set_ylabel("", fontsize=self._fs(self.config['label_fontsize']))
            ax_env.set_yticklabels([])
            ax_env.tick_params(axis='y', length=0)
            ax_env.grid(True, alpha=0.3, linestyle='--', axis='x')

            ax_env.spines['top'].set_position(('axes', 1))     
            ax_env.spines['bottom'].set_position(('axes', 0))  


            # Legenda envelope (per-lane, allineata alle curve — issue #91)
            if legend_entries:
                ax_legend = fig.add_subplot(gs[n_streams, 0])
                self._draw_envelope_legend(ax_legend, legend_entries)
        # =========================================================================
        # LENTE DI INGRANDIMENTO (magnify)
        # =========================================================================
        # Disegnata per ultima, sopra i subplot: l'overlay e gli inset non
        # alterano il GridSpec. Se magnify è spenta o non ci sono target per la
        # pagina, non viene creato alcun asse (back-compat).
        self._render_magnifiers(fig, page_start, page_end, stream_entries)

        # =========================================================================
        # TITOLO
        # =========================================================================
        title = f"Page {page_idx + 1}/{self.page_count} — " \
                f"[{page_start:.1f}s - {page_end:.1f}s]"
        # Titolo centrato nella striscia riservata in alto, appena sopra il plot:
        # bordo inferiore del testo a title_gap dal plot (stacco quasi nullo).
        top_pos = 1.0 - title_h - 2 * title_gap
        fig.suptitle(title, y=top_pos + title_gap + title_h * 0.5, va='center',
                     fontsize=self._fs(self.config['title_fontsize']))

        return fig

    # =========================================================================
    # LENTE DI INGRANDIMENTO (magnify)
    # =========================================================================

    def _render_magnifiers(self, fig, page_start, page_end, stream_entries):
        """Disegna le lenti attive per questa pagina.

        Risolve i target (auto sul cluster più denso + espliciti che cadono nella
        finestra di pagina), poi proietta per ciascuno un cerchio zoomato con
        marker sorgente e connettori. Nessun asse creato se magnify è spenta o
        non ci sono target (invariante back-compat)."""
        if not stream_entries:
            return
        targets = self._resolve_magnify_targets(
            page_start, page_end, stream_entries)
        if not targets:
            return
        overlay = self._make_magnify_overlay(fig)
        for resolved in targets:
            self._draw_one_magnifier(fig, overlay, resolved)

    def _resolve_magnify_targets(self, page_start, page_end, stream_entries):
        """Target risolti (concreti) per la pagina: {entry, t, y, zoom, out, src}.

        L'auto (se abilitato) aggiunge la lente sul cluster più denso; gli
        espliciti la cui 't' cade in [page_start, page_end) vengono risolti su
        stream e y concreti."""
        resolved = []
        if self.config.get('magnify_auto'):
            auto = self._auto_magnify_target(
                page_start, page_end, stream_entries)
            if auto is not None:
                resolved.append(auto)
        for target in (self.config.get('magnify_targets') or []):
            r = self._resolve_explicit_target(
                target, page_start, page_end, stream_entries)
            if r is not None:
                resolved.append(r)
        return resolved

    def _page_grain_points(self, stream, page_start, page_end):
        """(onset, pointer_pos) dei grani dello stream visibili nella pagina."""
        return [
            (g.onset, g.pointer_pos)
            for voice_grains in stream.voices
            for g in voice_grains
            if g.onset < page_end and (g.onset + g.duration) > page_start
        ]

    def _auto_magnify_target(self, page_start, page_end, stream_entries):
        """Target automatico: centroide del bin più denso (tempo×posizione) fra
        gli stream attivi. None se nessuno stream ha grani in pagina."""
        nt, ny = self.config['magnify_hist_bins']
        best = None  # (count, entry, tc, yc)
        for entry in stream_entries:
            pts = self._page_grain_points(entry['stream'], page_start, page_end)
            if not pts:
                continue
            ts = np.array([p[0] for p in pts])
            ys = np.array([p[1] for p in pts])
            y_hi = max(entry['sample_duration'], 1e-6)
            H, te, ye = np.histogram2d(
                ts, ys, bins=[nt, ny],
                range=[[page_start, page_end], [0.0, y_hi]])
            i, j = np.unravel_index(int(np.argmax(H)), H.shape)
            count = H[i, j]
            if count <= 0:
                continue
            # Centro sul centroide dei grani del bin: cade su grani reali, così
            # la finestra (stretta per via dello zoom) li contiene davvero.
            in_bin = [(t, y) for t, y in pts
                      if te[i] <= t <= te[i + 1] and ye[j] <= y <= ye[j + 1]]
            if not in_bin:
                continue
            tc = float(np.mean([t for t, _ in in_bin]))
            yc = float(np.mean([y for _, y in in_bin]))
            if best is None or count > best[0]:
                best = (count, entry, tc, yc)
        if best is None:
            return None
        _, entry, tc, yc = best
        d = self.config['magnify_defaults']
        return {'entry': entry, 't': tc, 'y': yc,
                'zoom': d['zoom'], 'out': d['out'], 'src': d['src'],
                'corner': d.get('corner', 'top-right')}

    def _resolve_explicit_target(self, target, page_start, page_end,
                                 stream_entries):
        """Risolve un target esplicito {t, y?, zoom?, out?, src?, stream?}.

        None se 't' non cade nella pagina. Stream: la chiave 'stream' (per
        stream_id) o, in mancanza, lo stream più denso in pagina. y: la chiave
        'y' o il centroide dei pointer_pos vicino a 't' (o metà sample)."""
        t = target.get('t')
        if t is None or not (page_start <= t < page_end):
            return None
        entry = None
        sid = target.get('stream')
        if sid is not None:
            entry = next((e for e in stream_entries
                          if e['stream'].stream_id == sid), None)
        if entry is None:
            entry = self._densest_stream_entry(
                page_start, page_end, stream_entries)
        if entry is None:
            return None
        d = self.config['magnify_defaults']
        y = target.get('y')
        if y is None:
            y = self._auto_y_at(entry['stream'], t, page_start, page_end)
            if y is None:
                y = entry['sample_duration'] * 0.5
        return {'entry': entry, 't': float(t), 'y': float(y),
                'zoom': target.get('zoom', d['zoom']),
                'out': target.get('out', d['out']),
                'src': target.get('src', d['src']),
                'corner': target.get('corner', d.get('corner', 'top-right'))}

    def _densest_stream_entry(self, page_start, page_end, stream_entries):
        """Entry dello stream con più grani visibili in pagina (fallback: primo)."""
        best, best_n = None, 0
        for entry in stream_entries:
            n = len(self._page_grain_points(
                entry['stream'], page_start, page_end))
            if n > best_n:
                best, best_n = entry, n
        return best or (stream_entries[0] if stream_entries else None)

    def _auto_y_at(self, stream, t, page_start, page_end):
        """Centroide dei pointer_pos dei grani vicini a 't' (None se nessuno)."""
        pts = self._page_grain_points(stream, page_start, page_end)
        if not pts:
            return None
        w = 0.05 * (page_end - page_start)  # finestra locale ±5% pagina
        near = [y for (gt, y) in pts if abs(gt - t) <= w] or [y for _, y in pts]
        return float(np.mean(near))

    def _make_magnify_overlay(self, fig):
        """Asse a tutta figura in coordinate pixel: cerchi tondi e linee dritte
        nonostante l'asse-dato sia anisotropo (X tempo, Y posizione). Etichettato
        '<magnifier-overlay>' come '<colorbar>', così i consumatori lo filtrano."""
        W, H = fig.get_size_inches() * fig.dpi
        ov = fig.add_axes([0, 0, 1, 1], zorder=10)
        ov.set_label('<magnifier-overlay>')
        ov.set_xlim(0, W)
        ov.set_ylim(0, H)
        ov.set_aspect('equal')
        ov.axis('off')
        return ov

    def _draw_one_magnifier(self, fig, overlay, resolved):
        """Proietta una lente: inset circolare zoomato + marker sorgente +
        connettori. I quattro controlli (center, zoom, out, src) sono
        indipendenti; src=None usa il valore fedele out/zoom."""
        entry = resolved['entry']
        ax_grain = entry['ax']
        stream = entry['stream']
        sample_dur = entry['sample_duration']
        cents_range = entry['cents_range']
        tc, yc = float(resolved['t']), float(resolved['y'])
        zoom = max(float(resolved['zoom']), 1e-6)

        W, H = fig.get_size_inches() * fig.dpi
        min_dim = min(W, H)
        out_r_px = float(resolved['out']) * min_dim
        src = resolved.get('src')
        src_r_px = (float(src) * min_dim) if src is not None else out_r_px / zoom

        # Scala px/dato dell'asse principale al centro (asse lineare).
        base = ax_grain.transData.transform((tc, yc))
        px_per_t = ax_grain.transData.transform((tc + 1.0, yc))[0] - base[0]
        px_per_y = ax_grain.transData.transform((tc, yc + 1.0))[1] - base[1]
        px_per_t = px_per_t if abs(px_per_t) > 1e-9 else 1.0
        px_per_y = px_per_y if abs(px_per_y) > 1e-9 else 1.0

        # Finestra dati mostrata: derivata da (zoom, out) → contenuto × zoom.
        hwx = out_r_px / (zoom * abs(px_per_t))
        hwy = out_r_px / (zoom * abs(px_per_y))
        t0, t1 = tc - hwx, tc + hwx
        y0, y1 = yc - hwy, yc + hwy

        # Posizione del cerchio di uscita: angolo del subplot (frazione figura).
        pos = ax_grain.get_position()
        r_fx, r_fy = out_r_px / W, out_r_px / H
        corner = resolved.get('corner') or \
            self.config['magnify_defaults'].get('corner', 'top-right')
        pad = 0.012
        cy = (pos.y1 - r_fy - pad) if 'top' in corner else (pos.y0 + r_fy + pad)
        cx = (pos.x1 - r_fx - pad) if 'right' in corner else (pos.x0 + r_fx + pad)

        # Inset lente: quadrato in pixel (cerchio tondo), clip a cerchio.
        lens_ax = fig.add_axes([cx - r_fx, cy - r_fy, 2 * r_fx, 2 * r_fy])
        lens_ax.set_label('<magnifier>')
        lens_ax.add_patch(mpatches.Circle(
            (0.5, 0.5), 0.5, transform=lens_ax.transAxes,
            facecolor='white', edgecolor='none', zorder=0))
        self._draw_loop_mask(lens_ax, stream, t0, t1, sample_dur)
        self._draw_grains_full(lens_ax, stream, sample_dur, t0, t1, cents_range)
        lens_ax.set_xlim(t0, t1)
        lens_ax.set_ylim(y0, y1)
        lens_ax.set_xticks([])
        lens_ax.set_yticks([])
        clip = mpatches.Circle((0.5, 0.5), 0.5, transform=lens_ax.transAxes)
        for art in (list(lens_ax.collections) + list(lens_ax.patches)
                    + list(lens_ax.lines)):
            art.set_clip_path(clip)
        lens_ax.patch.set_visible(False)
        for sp in lens_ax.spines.values():
            sp.set_visible(False)

        # Marker sorgente, connettori e anello lente sull'overlay (pixel).
        lpx, lpy = cx * W, cy * H
        accent = self.config['magnify_color']
        direction = np.array([lpx - base[0], lpy - base[1]], float)
        direction /= (np.hypot(*direction) + 1e-9)
        perp = np.array([-direction[1], direction[0]])
        for s in (+1.0, -1.0):
            a = np.array(base) + s * src_r_px * perp
            b = np.array([lpx, lpy]) + s * out_r_px * perp
            line, = overlay.plot([a[0], b[0]], [a[1], b[1]],
                                 color=accent, lw=1.2, alpha=0.55, zorder=4)
            line.set_gid('magnify-connector')
        src_ring = mpatches.Circle((base[0], base[1]), src_r_px, fill=False,
                                   ec=accent, lw=1.4, zorder=5)
        src_ring.set_gid('magnify-source')
        overlay.add_patch(src_ring)
        lens_ring = mpatches.Circle((lpx, lpy), out_r_px, fill=False,
                                    ec='#222222', lw=2.2, zorder=6)
        lens_ring.set_gid('magnify-lens')
        overlay.add_patch(lens_ring)

    def _draw_waveform_full(self, ax, stream, sample_duration):
        """Disegna waveform usando tutto lo spazio verticale dello subplot."""
        
        time_axis, amplitude, _ = self._load_waveform(stream.sample)
        
        # Y = tempo nel sample (da 0 a sample_duration)
        # X = ampiezza normalizzata (-1 a +1)
        
        # Disegna linea
        ax.plot(
            amplitude, time_axis,
            color=self.config['waveform_color'],
            alpha=self.config['waveform_alpha'] + 0.3,
            linewidth=0.5
        )
        
        # Fill dallo zero
        ax.fill_betweenx(
            time_axis,
            0,
            amplitude,
            alpha=self.config['waveform_alpha'],
            color=self.config['waveform_color'],
            linewidth=0
        )


    def _grain_arrow_vertices(self, grain):
        """Vertici della freccia direzionale (forma storica del grano).

        5 vertici: rettangolo [onset, onset+duration] x [pointer, pointer+dur]
        con punta triangolare verso l'alto (forward) o il basso (reverse)."""
        x = grain.onset
        width = grain.duration
        pointer_y = grain.pointer_pos
        height = grain.duration
        arrow_head_width = width * 0.5

        if grain.pitch_ratio < 0:
            y_top = pointer_y
            y_bottom = pointer_y - height
            return [
                (x, y_top),                               # alto sinistra
                (x + width, y_top),                       # alto destra
                (x + width, y_bottom + arrow_head_width), # prima della punta destra
                (x + width / 2, y_bottom),                # punta centrale (GIU')
                (x, y_bottom + arrow_head_width),         # prima della punta sinistra
            ]
        y_bottom = pointer_y
        y_top = pointer_y + height
        return [
            (x, y_bottom),                                # basso sinistra
            (x + width, y_bottom),                        # basso destra
            (x + width, y_top - arrow_head_width),        # prima della punta destra
            (x + width / 2, y_top),                       # punta centrale (SU)
            (x, y_top - arrow_head_width),                # prima della punta sinistra
        ]

    def _grain_window_vertices(self, grain, xs, w):
        """Vertici della silhouette "testa/bordo": base piatta sul pointer, il
        bordo superiore segue la curva della finestra w (normalizzata su [0,1]).

        xs, w: arrays normalizzati su [0,1] (vedi _window_silhouette). La
        direzione (sopra/sotto il pointer) segue il segno di pitch_ratio come
        per la freccia."""
        x = grain.onset
        width = grain.duration
        pointer_y = grain.pointer_pos
        height = grain.duration

        xs_abs = x + xs * width
        if grain.pitch_ratio < 0:
            edge = pointer_y - height * w
        else:
            edge = pointer_y + height * w

        vertices = [(x, pointer_y)]
        vertices.extend((float(xi), float(yi)) for xi, yi in zip(xs_abs, edge))
        vertices.append((x + width, pointer_y))
        return vertices

    def _window_registry_lazy(self):
        """Istanzia il NumpyWindowRegistry al primo uso (solo grain_shape='window')."""
        if self._window_registry is None:
            from rendering.numpy_window_registry import NumpyWindowRegistry
            self._window_registry = NumpyWindowRegistry()
        return self._window_registry

    def _window_silhouette(self, name, resolution):
        """Curva finestra normalizzata su [0,1] in ampiezza e dominio.

        Ritorna (xs, w) con xs = linspace(0,1,resolution) e w la finestra
        riscalata a picco unitario. Cachata per (name, resolution): la forma di
        una finestra dato il nome e' sempre la stessa, cambia solo la scala
        applicata per grano."""
        key = (name, resolution)
        cached = self._window_silhouette_cache.get(key)
        if cached is not None:
            return cached

        w = self._window_registry_lazy().get(name, resolution)
        w = np.clip(np.asarray(w, dtype=float), 0.0, None)
        peak = float(w.max())
        if peak > 0:
            w = w / peak
        xs = np.linspace(0.0, 1.0, resolution)
        result = (xs, w)
        self._window_silhouette_cache[key] = result
        return result

    def _window_name_map(self, stream):
        """Mappa table_num -> nome finestra invertendo stream.window_table_map.

        Ritorna {} se la mappa non e' disponibile (fallback alla freccia)."""
        wtm = getattr(stream, 'window_table_map', None)
        if not wtm:
            return {}
        return {num: name for name, num in wtm.items()}

    def _grain_page_width_px(self, ax, grain):
        """Larghezza del grano sulla pagina in pixel display.

        Usata per il fallback adattivo: grani sub-pixel non mostrano la finestra
        in modo leggibile. Se la trasformazione non e' disponibile (axes non
        ancora disegnato) ritorna +inf -> nessun fallback."""
        try:
            t = ax.transData
            x0 = t.transform((grain.onset, 0.0))[0]
            x1 = t.transform((grain.onset + grain.duration, 0.0))[0]
            return abs(x1 - x0)
        except Exception:
            return float('inf')

    def _draw_grains_full(self, ax, stream, sample_duration, page_start,
                          page_end, cents_range=None):
        """Disegna grani con coordinate Y assolute nel sample.

        cents_range: range colore auto-zoomato del subplot (vedi
        _compute_pitch_color_range); None = range fisso."""
        
        all_grains = [grain for voice_grains in stream.voices for grain in voice_grains]

        # Filtra grani visibili
        visible_grains = [
            g for g in all_grains
            if g.onset < page_end and (g.onset + g.duration) > page_start
        ]
        
        if not visible_grains:
            return

        polygons = []
        #rectangles = []
        colors = []

        # Modalita' forma del grano. In 'window' il bordo superiore traccia la
        # curva della finestra; serve la mappa table_num -> nome finestra (una
        # volta per stream) e la risoluzione di campionamento.
        grain_shape = self.config.get('grain_shape', 'arrow')
        window_mode = grain_shape == 'window'
        if window_mode:
            name_map = self._window_name_map(stream)
            resolution = self.config['window_shape_resolution']
            min_px = self.config['window_shape_min_px']
            # name_map vuota (window_table_map assente) -> niente nomi da
            # risolvere: si ripiega interamente sulla freccia.
            if not name_map:
                window_mode = False

        for grain in visible_grains:
            # window_mode con grano abbastanza largo sulla pagina e finestra
            # risolvibile -> silhouette della finestra; altrimenti freccia.
            use_window = (
                window_mode
                and self._grain_page_width_px(ax, grain) >= min_px
                and grain.envelope_table in name_map
            )
            if use_window:
                xs, w = self._window_silhouette(
                    name_map[grain.envelope_table], resolution)
                vertices = self._grain_window_vertices(grain, xs, w)
            else:
                vertices = self._grain_arrow_vertices(grain)

            # Crea poligono
            poly = mpatches.Polygon(vertices, closed=True)
            polygons.append(poly)

            # Colore
            color = list(self._pitch_to_color(abs(grain.pitch_ratio),
                                              cents_range))
            color[3] = self._volume_to_alpha(grain.volume)
            colors.append(color)
        
        # Collection
        # Contorno sottile per ogni grano: i grani prossimi al neutro (grigio
        # chiaro della mappa divergente) restano leggibili come forme sul fondo
        # bianco. Solo il bordo cambia: facecolor e alpha (guidato dal volume)
        # restano invariati.
        collection = PatchCollection(
            polygons,
            facecolors=colors,
            edgecolors='#555555',
            linewidths=0.01,
            clip_on=True,
            zorder=2
        )
        ax.add_collection(collection)

    def _draw_stream_label_full(self, ax, stream, page_start, sample_duration):
        """Label stream nell'angolo in alto a sinistra del subplot."""
        label_x = max(stream.onset, page_start) + 0.5        
        ax.text(
            label_x, 
            sample_duration * 0.95,  # posizione relativa all'altezza del sample
            stream.stream_id,
            fontsize=self._fs(self.config['label_fontsize'] - 1),
            verticalalignment='top',
            horizontalalignment='left',
            color='darkblue',
            alpha=0.8,
            bbox=dict(boxstyle='round,pad=0.2', facecolor='white', 
                    alpha=0.7, edgecolor='none')
        )
    def _draw_loop_mask(self, ax, stream, page_start, page_end, sample_duration):
        """
        Disegna la maschera di tendenza del loop direttamente nel piano dei grani.

        La banda colorata mostra la regione [loop_start, loop_start+loop_dur]
        (o [loop_start, loop_end]) nel sample, per ogni istante di tempo.
        Se i parametri sono Envelope, la banda si deforma nel tempo.
        Se loop_start + loop_dur supera sample_duration, la regione wrappa
        attorno al file e viene disegnata come due bande separate.
        Viene disegnata sotto i grani (chiamare prima di _draw_grains_full).
        """
        from parameters.parameter import Parameter

        # Recupera i parametri loop dallo stream (via property proxy)
        loop_start = stream.loop_start
        loop_end   = stream.loop_end
        loop_dur   = stream.loop_dur

        # Se non c'e' loop, esci subito
        if loop_start is None:
            return

        # Limiti temporali visibili per questo stream nella pagina
        stream_onset = stream.onset
        stream_end   = stream.onset + stream.duration
        t_start = max(page_start, stream_onset)
        t_end   = min(page_end,   stream_end)

        if t_start >= t_end:
            return

        # Helper: valuta un parametro loop a un dato elapsed time
        def eval_param(param, elapsed):
            if param is None:
                return None
            if isinstance(param, Parameter):
                return param.get_value(elapsed)
            if isinstance(param, (int, float)):
                return float(param)
            return None

        # Campiona il tempo a intervalli regolari
        n_samples = self.config['loop_mask_samples']
        times = np.linspace(t_start, t_end, n_samples)

        y_bottoms = []
        y_tops    = []
        y_bottoms2 = []   # banda wraparound: parte iniziale del file
        y_tops2    = []   # banda wraparound: parte iniziale del file

        for t in times:
            elapsed = t - stream_onset

            y_bot = eval_param(loop_start, elapsed)
            if y_bot is None:
                y_bottoms.append(np.nan)
                y_tops.append(np.nan)
                y_bottoms2.append(np.nan)
                y_tops2.append(np.nan)
                continue

            if loop_dur is not None:
                dur = eval_param(loop_dur, elapsed)
                y_top_raw = y_bot + dur if dur is not None else np.nan
            elif loop_end is not None:
                y_top_raw = eval_param(loop_end, elapsed)
                if y_top_raw is None:
                    y_top_raw = np.nan
            else:
                y_top_raw = np.nan

            # Rileva wraparound: loop_end supera la fine del file
            if not np.isnan(y_top_raw) and y_top_raw > sample_duration:
                # Banda 1: da loop_start fino a fine file
                y_bottoms.append(y_bot)
                y_tops.append(sample_duration)
                # Banda 2: da inizio file fino alla parte wrappata
                y_bottoms2.append(0.0)
                y_tops2.append(y_top_raw - sample_duration)
            else:
                # Caso normale: nessun wrap
                y_bottoms.append(y_bot)
                y_tops.append(y_top_raw)
                y_bottoms2.append(np.nan)
                y_tops2.append(np.nan)


        y_bottoms = np.array(y_bottoms, dtype=float)
        y_tops    = np.array(y_tops,    dtype=float)
        y_bottoms2 = np.array(y_bottoms2, dtype=float)
        y_tops2    = np.array(y_tops2,    dtype=float)

        # Disegna la banda
        ax.fill_between(
            times,
            y_bottoms,
            y_tops,
            color=self.config['loop_mask_color'],
            alpha=self.config['loop_mask_alpha'],
            zorder=1   # sotto i grani (PatchCollection usa zorder default ~2)
        )

        # Disegna banda wraparound solo se esiste almeno un campione valido
        if not np.all(np.isnan(y_tops2)):
            ax.fill_between(
                times,
                y_bottoms2,
                y_tops2,
                color=self.config['loop_mask_color'],
                alpha=self.config['loop_mask_alpha'],
                zorder=0
            )


    # =========================================================================
    # ENVELOPE
    # =========================================================================

    def _get_stream_envelopes(self, stream):
        """Estrae gli Envelope della IR dello stream.

        Delega a rendering.envelope_extractor (single source of truth condivisa
        con SVExporter, issue #150). I flag di config governano il gating come
        prima: show_static_params, show_voice_offsets, envelope_filter.
        """
        from rendering.envelope_extractor import get_stream_envelopes
        return get_stream_envelopes(
            stream,
            show_static=self.config.get('show_static_params', False),
            show_voice_offsets=self.config.get('show_voice_offsets', False),
            envelope_filter=self.config.get('envelope_filter'),
        )

    @staticmethod
    def _base_param_name(key):
        """Nome base di una chiave envelope (strip suffisso per-voce '__vN').
        Delega a rendering.envelope_extractor.base_param_name (issue #150)."""
        from rendering.envelope_extractor import base_param_name
        return base_param_name(key)

    def _get_voice_offset_envelopes(self, stream):
        """Curve per-voce degli offset (issue #90, Fase 3).
        Delega a rendering.envelope_extractor.get_voice_offset_envelopes."""
        from rendering.envelope_extractor import get_voice_offset_envelopes
        return get_voice_offset_envelopes(stream)

    def _compute_display_ranges(self, envelopes, stream, t_start, t_end):
        """
        Calcola, per ogni envelope (tranne pan), il range di display data-driven:
        l'escursione reale (min/max) dei valori nella finestra visibile, più un
        padding (config['envelope_display']['pad_ratio']). Issue #114.

        Nessun clamp ai range fissi: ogni curva scala sulla propria escursione.
        pan resta ciclico (escluso, usa il range fisso ±180).

        Returns:
            dict {param_name: (disp_min, disp_max)} per ogni parametro non-pan.
        """
        cfg = self.config['envelope_display']
        pad_ratio = cfg['pad_ratio']
        n = cfg['samples']
        stream_start = stream.onset

        result = {}
        for param_name, envelope in envelopes.items():
            # Le chiavi per-voce ('__vN', #90) ereditano dal parametro base.
            if self._base_param_name(param_name) == 'pan':
                continue  # pan ciclico: range fisso (-180, 180)

            # Escursione reale nella finestra visibile: campiona densamente la
            # curva (cattura overshoot cubic) e includi i breakpoint interni.
            t_rel0 = max(0.0, t_start - stream_start)
            t_rel1 = max(t_rel0, t_end - stream_start)
            samples = [envelope.evaluate(t) for t in np.linspace(t_rel0, t_rel1, n)]
            samples += [v for t, v in envelope.breakpoints if t_rel0 <= t <= t_rel1]
            if not samples:
                continue
            v_min, v_max = min(samples), max(samples)
            span = v_max - v_min
            if span <= 1e-12:
                pad = max(abs(v_min) * pad_ratio, 1e-6)  # envelope costante: centra
            else:
                pad = span * pad_ratio
            result[param_name] = (v_min - pad, v_max + pad)

        return result

    def _normalize_envelope_value(self, param_name, value):
        """
        Normalizza un valore di envelope a 0-1 sul range di display data-driven
        attivo (issue #114). Nessun clamp ai range fissi tranne per pan.

        Args:
            param_name: nome del parametro
            value: valore da normalizzare

        Returns:
            float: valore normalizzato (tipicamente 0-1; pan è clippato).
        """
        # Le curve per-voce ('__vN', #90) si normalizzano col base.
        base = self._base_param_name(param_name)

        # pan resta ciclico: wrap modulo su ±180 e clamp (range fisso).
        if base == 'pan':
            min_val, max_val = self.config['envelope_ranges']['pan']
            value = ((value + 180) % 360) - 180
            return np.clip((value - min_val) / (max_val - min_val), 0, 1)

        # Range di display data-driven (popolato da _draw_envelopes per tutti i
        # parametri tranne pan). Nessun clip: la curva scala sulla sua escursione.
        display_ranges = getattr(self, '_current_display_ranges', None) or {}
        if param_name in display_ranges:
            min_val, max_val = display_ranges[param_name]
            if max_val != min_val:
                return (value - min_val) / (max_val - min_val)   # NESSUN clip
            return 0.5                                            # costante: centro corsia
        return 0.5  # fallback difensivo (draw imposta sempre i display range)

    @staticmethod
    def _segment_strategy_name(segment) -> str:
        """Mappa strategy del segmento al nome canonico ('step'/'linear'/'cubic')."""
        cls_name = segment.strategy.__class__.__name__
        if 'Step' in cls_name:
            return 'step'
        if 'Cubic' in cls_name:
            return 'cubic'
        return 'linear'

    @staticmethod
    def _is_per_segment_heterogeneous(envelope) -> bool:
        """
        True se envelope ha segmenti con strategie diverse (es. step+linear).

        Envelope uniformi (1 segmento o tutti stessa strategy) → False.
        """
        segs = getattr(envelope, 'segments', None)
        if not segs or len(segs) < 2:
            return False
        names = {ScoreVisualizer._segment_strategy_name(s) for s in segs}
        return len(names) > 1

    def _draw_envelopes(self, ax, stream, y_base, y_height, page_start, page_end):
        """
        Disegna tutti gli envelope dello stream nella sua corsia.
        Annota i breakpoint con i valori reali.
        
        Returns:
            set: nomi dei tipi di envelope disegnati
        """
        envelopes = self._get_stream_envelopes(stream)

        # Unità pitch dello stream corrente: serve a _normalize_envelope_value e
        # _annotate_breakpoints per scalare/etichettare la curva 'pitch' (i bounds
        # dipendono dall'unità, non sono statici come gli altri parametri).
        self._current_pitch_unit = getattr(stream, 'pitch_unit', None)
        self._current_display_ranges = {}

        if not envelopes:
            return set()

        drawn_types = set()
        colors = self.config['envelope_colors']
        
        # Tempo relativo allo stream
        stream_start = stream.onset
        stream_end = stream.onset + stream.duration
        
        # Calcola i tempi da campionare (visibili nella pagina)
        t_start = max(page_start, stream_start)
        t_end = min(page_end, stream_end)
        
        if t_start >= t_end:
            return set()

        # Auto-zoom: range di display ristretti per i parametri a range ampio.
        self._current_display_ranges = self._compute_display_ranges(
            envelopes, stream, t_start, t_end)

        for param_name, envelope in envelopes.items():
            # Colore (curve per-voce '__vN' usano il colore del base, #90)
            color = colors.get(self._base_param_name(param_name), '#333333')

            # Envelope per-segmento eterogeneo (issue #68): rendering per-segmento
            if self._is_per_segment_heterogeneous(envelope):
                self._draw_envelope_per_segment(
                    ax, envelope, param_name, color,
                    stream_start, y_base, y_height, t_start, t_end,
                )
                self._annotate_breakpoints(ax, envelope, param_name, color,
                                           stream_start, y_base, y_height,
                                           page_start, page_end)
                drawn_types.add(param_name)
                continue

            # ========== GESTIONE DIFFERENZIATA PER TIPO ==========
            if envelope.type == 'step':
                # Per envelope STEP: disegna segmenti orizzontali espliciti
                times = []
                values = []
                
                # Costruisci i punti per creare gradini visibili
                for i, (t_rel, v) in enumerate(envelope.breakpoints):
                    t_abs = stream_start + t_rel
                    
                    # Salta breakpoint prima della pagina
                    if t_abs < t_start:
                        continue
                    
                    # Se abbiamo superato la fine, aggiungi punto finale e ferma
                    if t_abs > t_end:
                        # Ultimo segmento fino a t_end
                        if i > 0:
                            last_value = envelope.breakpoints[i-1][1]
                            val_norm = self._normalize_envelope_value(param_name, last_value)
                            y_val = y_base + val_norm * y_height
                            times.append(t_end)
                            values.append(y_val)
                        break
                    
                    # Aggiungi punto PRIMA del breakpoint (se non è il primo)
                    if i > 0:
                        t_prev_rel, v_prev = envelope.breakpoints[i-1]
                        val_norm = self._normalize_envelope_value(param_name, v_prev)
                        y_val = y_base + val_norm * y_height
                        times.append(t_abs)
                        values.append(y_val)
                    
                    # Aggiungi punto AL breakpoint (con nuovo valore)
                    val_norm = self._normalize_envelope_value(param_name, v)
                    y_val = y_base + val_norm * y_height
                    times.append(t_abs)
                    values.append(y_val)
                
                # Aggiungi ultimo segmento fino a t_end (se necessario)
                if len(times) > 0 and times[-1] < t_end:
                    times.append(t_end)
                    values.append(values[-1])
                
                # Aggiungi primo segmento da t_start (se necessario)
                if len(times) > 0 and times[0] > t_start:
                    # Valuta il valore all'inizio della pagina
                    t_rel_start = t_start - stream_start
                    v_start = envelope.evaluate(t_rel_start)
                    val_norm = self._normalize_envelope_value(param_name, v_start)
                    y_start = y_base + val_norm * y_height
                    times.insert(0, t_start)
                    values.insert(0, y_start)
                
                # Disegna con drawstyle='steps-post' per gradini
                if len(times) > 0:
                    ax.plot(times, values, color=color, linewidth=1.1, 
                        alpha=0.8, label=param_name, drawstyle='steps-post')
            
            else:
                # Per envelope LINEAR e CUBIC: campionamento denso
                num_samples = 500
                times = np.linspace(t_start, t_end, num_samples)
                
                # Calcola valori
                values = []
                for t in times:
                    # Tempo relativo all'onset dello stream
                    t_rel = t - stream_start
                    val = envelope.evaluate(t_rel)
                    # Normalizza al range
                    val_norm = self._normalize_envelope_value(param_name, val)
                    values.append(val_norm)
                
                values = np.array(values)
                
                # Scala Y alla corsia dello stream
                y_values = y_base + values * y_height
                
                # Disegna curva
                ax.plot(times, y_values, color=color, linewidth=1.1, 
                    alpha=0.8, label=param_name)
            
            # === ANNOTAZIONE BREAKPOINT ===
            self._annotate_breakpoints(ax, envelope, param_name, color,
                                    stream_start, y_base, y_height,
                                    page_start, page_end)
            
            drawn_types.add(param_name)

        # Reset: le lane successive ricalcolano i propri display range.
        self._current_display_ranges = {}

        return drawn_types

    def _draw_envelope_per_segment(
        self, ax, envelope, param_name, color,
        stream_start, y_base, y_height, t_start, t_end,
    ):
        """
        Disegna envelope eterogeneo segmento per segmento (issue #68).

        Ogni segmento usa drawstyle adattato alla propria strategy:
        - step: drawstyle='steps-post' (gradini netti)
        - linear: linea retta tra estremi
        - cubic: campionamento denso del segmento
        """
        for seg in envelope.segments:
            seg_t0 = stream_start + seg.start_time
            seg_t1 = stream_start + seg.end_time
            # Clipping alla pagina
            a = max(seg_t0, t_start)
            b = min(seg_t1, t_end)
            if a >= b:
                continue

            strategy_name = self._segment_strategy_name(seg)

            if strategy_name == 'step':
                # Hold left value: linea orizzontale poi salto a fine
                v_left = seg.breakpoints[0][1]
                v_right = seg.breakpoints[-1][1]
                y_left = y_base + self._normalize_envelope_value(param_name, v_left) * y_height
                y_right = y_base + self._normalize_envelope_value(param_name, v_right) * y_height
                ax.plot([a, b], [y_left, y_left], color=color, linewidth=1.1, alpha=0.8)
                # Salto verticale a fine segmento (se b == seg_t1)
                if b >= seg_t1:
                    ax.plot([b, b], [y_left, y_right], color=color, linewidth=1.1, alpha=0.8)

            elif strategy_name == 'linear':
                # Usa seg.evaluate() per evitare bug precisione float al boundary
                # tra segmenti (envelope.evaluate cerca per tempo e può cadere
                # nel segmento precedente, restituendo valore sbagliato).
                v_a = seg.evaluate(a - stream_start)
                v_b = seg.evaluate(b - stream_start)
                y_a = y_base + self._normalize_envelope_value(param_name, v_a) * y_height
                y_b = y_base + self._normalize_envelope_value(param_name, v_b) * y_height
                ax.plot([a, b], [y_a, y_b], color=color, linewidth=1.1, alpha=0.8)

            else:  # cubic
                import numpy as np
                n = max(20, int(50 * (b - a) / max(seg_t1 - seg_t0, 1e-9)))
                ts = np.linspace(a, b, n)
                ys = []
                for t in ts:
                    v = seg.evaluate(t - stream_start)
                    ys.append(y_base + self._normalize_envelope_value(param_name, v) * y_height)
                ax.plot(ts, ys, color=color, linewidth=1.1, alpha=0.8)

    def _annotate_breakpoints(self, ax, envelope, param_name, color,
                               stream_start, y_base, y_height,
                               page_start, page_end):
        """
        Annota i breakpoint dell'envelope con i valori reali.
        """
        # Unità di misura per ogni parametro
        units = {
            'volume': 'dB',
            'grain_duration': 'ms',
            'pan': '°',
            # pitch: il simbolo (st/c/qt/et/edoN/x) viene da pu.symbol, vedi sotto
            'density': 'g/s',
            'pointer_speed': 'x',
            'fill_factor': '',
            'distribution': '',
            'num_voices': ' voices',
            'scatter': '',  # normalizzato 0-1, adimensionale
            'scatter': '',  # normalizzato 0-1, adimensionale
            'pc_rand_reverse': '%',
        }
        
        # Moltiplicatori per visualizzazione leggibile
        multipliers = {
            'grain_duration': 1000,  # secondi → millisecondi
        }
        
        unit = units.get(param_name, '')
        # PITCH unit-driven: il simbolo (st/c/qt/et/edoN/x) viene dall'unità attiva.
        if param_name == 'pitch':
            pu = getattr(self, '_current_pitch_unit', None)
            if pu is not None:
                unit = pu.symbol
        mult = multipliers.get(param_name, 1)
        
        for t_rel, value in envelope.breakpoints:
            # Tempo assoluto
            t_abs = stream_start + t_rel
            
            # Salta breakpoint fuori dalla pagina
            if t_abs < page_start or t_abs > page_end:
                continue
            
            # Posizione Y normalizzata
            val_norm = self._normalize_envelope_value(param_name, value)
            y_pos = y_base + val_norm * y_height
            
            # Valore da mostrare (con unità)
            display_value = value * mult
            
            # Formatta il numero
            if abs(display_value) >= 100:
                label = f"{display_value:.0f}{unit}"
            elif abs(display_value) >= 10:
                label = f"{display_value:.1f}{unit}"
            else:
                label = f"{display_value:.2f}{unit}"
            
            # Disegna punto
            ax.plot(t_abs, y_pos, 'o', color=color, markersize=4, alpha=0.9)

            # Lato dell'etichetta scelto dinamicamente in base alla posizione del
            # breakpoint nel subplot, cosi' il testo resta SEMPRE dentro il plot
            # dedicato all'envelope (prima un offset fisso in alto-a-destra faceva
            # sforare i breakpoint vicini al bordo destro o al tetto della corsia).
            x_span = page_end - page_start
            x_frac = (t_abs - page_start) / x_span if x_span > 0 else 0.5
            # ylim del subplot envelope e' (0, 1): y_pos e' gia' la frazione
            # verticale dentro l'asse.
            y_frac = y_pos

            # Vicino al bordo destro -> etichetta a sinistra del punto.
            if x_frac > 0.85:
                dx, ha = -3, 'right'
            else:
                dx, ha = 3, 'left'
            # Vicino al tetto del subplot -> etichetta sotto il punto.
            if y_frac > 0.9:
                dy, va = -3, 'top'
            else:
                dy, va = 3, 'bottom'

            # Disegna etichetta (offset dinamico per restare dentro il plot)
            ax.annotate(
                label,
                xy=(t_abs, y_pos),
                xytext=(dx, dy),
                textcoords='offset points',
                fontsize=self._fs(self.config['breakpoint_fontsize']),
                color=color,
                alpha=0.9,
                ha=ha,
                va=va,
                bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                         alpha=0.7, edgecolor='none')
            )

    def _compute_env_legend_layout(self, active_streams):
        """
        Calcola la geometria condivisa tra lane envelope e legenda (issue #91).

        Lane e legenda devono usare lo stesso ordinamento e le stesse y,
        altrimenti la legenda appare mirrorata rispetto alle curve.

        Returns:
            (lanes, legend_entries)
            lanes: list[dict] con {stream, stream_id, y_base, y_height,
                   env_types}, ordine = impilamento (slot_idx crescente, dal
                   basso verso l'alto come in render_page).
            legend_entries: list[(param_name, y, stream_id)], con y interna
                   alla lane dello stream proprietario.
        """
        streams_with_env = [
            (s, self._get_stream_envelopes(s)) for s in active_streams
        ]
        streams_with_env = [(s, e) for s, e in streams_with_env if e]

        lanes = []
        legend_entries = []
        n = len(streams_with_env)
        if n == 0:
            return lanes, legend_entries

        gap_ratio = 0.02  # coerente con render_page
        total_gap = gap_ratio * 2 * n
        env_slot_height = (1.0 - total_gap) / n

        for slot_idx, (stream, envelopes) in enumerate(streams_with_env):
            y_single_stream_with_gap = gap_ratio * 2 + env_slot_height
            y_that_stream = y_single_stream_with_gap * slot_idx
            y_base = y_that_stream + gap_ratio
            y_height = env_slot_height

            # Le curve per-voce ('__vN', #90) collassano a una sola voce di
            # legenda per parametro base: N tracce, una etichetta.
            env_types = sorted(
                dict.fromkeys(self._base_param_name(k) for k in envelopes)
            )
            lanes.append({
                'stream': stream,
                'stream_id': stream.stream_id,
                'y_base': y_base,
                'y_height': y_height,
                'env_types': env_types,
            })

            m = len(env_types)
            if m == 1:
                ys = [y_base + y_height * 0.5]
            else:
                ys = np.linspace(y_base + y_height * 0.85,
                                 y_base + y_height * 0.15, m)
            for param_name, y in zip(env_types, ys):
                legend_entries.append((param_name, float(y), stream.stream_id))

        return lanes, legend_entries

    # Nomi corti per la legenda: la colonna e' stretta (~6% pagina), i nomi
    # lunghi sforavano nel plot (issue #96). Mappa solo i nomi lunghi; gli altri
    # usano replace('_', ' ').
    _ENV_LEGEND_SHORT = {
        'pointer_deviation': 'ptr dev',
        'pointer_speed': 'ptr spd',
        'pointer_start': 'ptr start',
        'grain_duration': 'grain dur',
        'num_voices': 'voices',
        'voice_pitch_offset': 'v pitch off',
        'voice_pointer_offset': 'v ptr off',
        'voice_pointer_range': 'v ptr rng',
        'effective_density': 'eff density',
        'distribution': 'distrib',
        'fill_factor': 'fill',
        # Override compatto: 'grain dur rng' (13) sforerebbe la colonna (issue #141)
        'grain_duration_range': 'gr dur rng',
    }

    def _legend_display_name(self, param_name):
        """Nome corto per la legenda. Un override esplicito in _ENV_LEGEND_SHORT
        ha precedenza; altrimenti suffisso '_prob' → ' %' (probabilita') e
        '_range' → ' rng' (deviazione per-grano, issue #141)."""
        if param_name in self._ENV_LEGEND_SHORT:
            return self._ENV_LEGEND_SHORT[param_name]
        if param_name.endswith('_prob'):
            base = param_name[:-len('_prob')]
            return f"{self._legend_display_name(base)} %"
        if param_name.endswith('_range'):
            base = param_name[:-len('_range')]
            return f"{self._legend_display_name(base)} rng"
        return param_name.replace('_', ' ')

    def _draw_envelope_legend(self, ax, legend_entries):
        """
        Disegna la legenda degli envelope nel subplot dedicato.

        legend_entries: list[(param_name, y, stream_id)] gia' posizionati
        per-lane da _compute_env_legend_layout (issue #91), allineati alle
        curve nelle corsie.
        """
        ax.axis('off')
        colors = self.config['envelope_colors']

        for param_name, y, stream_id in legend_entries:
            color = colors.get(self._base_param_name(param_name), '#333333')
            ax.plot([0.1, 0.15], [y, y], color=color, linewidth=2)
            # clip_on=True: anche un nome inatteso non sfora mai nel plot,
            # viene tagliato al bordo della colonna legenda (issue #96).
            ax.text(0.4, y, self._legend_display_name(param_name),
                    fontsize=self._fs(self.config['label_fontsize'] - 2),
                    verticalalignment='center',
                    color=color,
                    clip_on=True)

        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)



    # =========================================================================
    # OUTPUT
    # =========================================================================
    
    def render_all(self):
        """Renderizza tutte le pagine."""
        if not self.page_layouts:
            self.analyze()
        
        figures = []
        for page_idx in range(self.page_count):
            print(f"  Rendering pagina {page_idx + 1}/{self.page_count}...")
            fig = self.render_page(page_idx)
            figures.append(fig)
        
        return figures
    
    def export_pdf(self, output_path):
        """Esporta tutto in un PDF multipagina."""
        print(f"Esportazione PDF: {output_path}")
        
        figures = self.render_all()
        
        # bbox_inches='tight' rifila la tela al contenuto reale: niente bordo
        # vuoto tra la fine delle parole (y-label, "Tempo (s)", titolo, label
        # colorbar) e il margine pagina, e nessun crop quando font_scale cresce.
        with PdfPages(output_path) as pdf:
            for fig in figures:
                pdf.savefig(fig, dpi=150, bbox_inches='tight', pad_inches=0.02)
                plt.close(fig)
        
        print(f"✓ PDF esportato: {output_path}")
    
    def export_png(self, output_dir, prefix="page"):
        """Esporta ogni pagina come PNG separato."""
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"Esportazione PNG in: {output_dir}")
        
        figures = self.render_all()
        
        for idx, fig in enumerate(figures):
            path = f"{output_dir}/{prefix}_{idx:03d}.png"
            fig.savefig(path, dpi=300, bbox_inches='tight')
            plt.close(fig)
            print(f"  ✓ {path}")
    
    def show(self, page_idx=0):
        """Mostra una pagina interattivamente."""
        if not self.page_layouts:
            self.analyze()
        
        fig = self.render_page(page_idx)
        plt.show()
        return fig


