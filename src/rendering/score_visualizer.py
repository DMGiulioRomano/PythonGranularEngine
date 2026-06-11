# =============================================================================
# SCORE VISUALIZER - Partitura grafica per sintesi granulare
# =============================================================================

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.cm import ScalarMappable
from matplotlib.collections import PatchCollection
from matplotlib.colors import Normalize
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import soundfile as sf
from math import ceil

# Path samples (stesso del progetto)
PATHSAMPLES = './refs/'

# Colori di default degli envelope. A livello modulo perche' le sue chiavi
# sono l'universo dei nomi plottabili: main.py le usa per validare
# --plot-envelopes (issue #101).
ENVELOPE_COLORS = {
    # === OUTPUT ===
    'volume': '#e41a1c',          # rosso
    'volume_prob': '#fb9a99',     # rosso chiaro
    'pan': '#4daf4a',             # verde
    'pan_prob': '#b2df8a',        # verde chiaro

    # === GRAIN ===
    'grain_duration': '#377eb8',  # blu
    'grain_duration_prob': '#a6cee3',  # blu chiaro
    'reverse': '#999999',         # grigio
    'reverse_prob': '#cccccc',    # grigio chiarissimo

    # === POINTER ===
    'pointer_start': '#8dd3c7',   # celeste
    'pointer_speed': '#a65628',   # marrone
    'pointer_deviation': '#fb8072',  # salmone
    'pointer_deviation_prob': '#fdb462',  # arancione chiaro
    'loop_dur': '#bebada',        # lavanda

    # === PITCH ===
    'pitch': '#984ea3',           # viola (unit-driven, qualsiasi unità)

    # === DENSITY ===
    'density': '#ff7f00',         # arancio
    'fill_factor': '#f781bf',     # rosa
    'distribution': '#999999',    # grigio
    'effective_density': '#ffed6f',  # giallo

    # === VOICES ===
    'num_voices': '#e377c2',      # magenta
    'scatter': '#17becf',         # teal
    'voice_pitch_offset': '#c49c94',  # beige
    'voice_pointer_offset': '#f7b6d2', # rosa chiaro
    'voice_pointer_range': '#c7c7c7',  # grigio chiaro
}

# Nomi validi per il filtro --plot-envelopes / envelope_filter (issue #101)
PLOT_ENVELOPE_KEYS = frozenset(ENVELOPE_COLORS)


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
            # Se True, mostra anche i valori costanti
            'show_static_params': False,
            # Filtro selettivo: None = tutti gli envelope; altrimenti set/lista
            # di nomi — solo quelli elencati vengono plottati (issue #101)
            'envelope_filter': None,
            # Paginazione
            'page_duration': 30.0,           # secondi per pagina
            'page_size': (420, 297),         # A3 in mm
            'orientation': 'landscape',
            'margins_mm': 20,
            
            # Grani
            'grain_colormap': 'turbo',       # pitch_ratio → colore
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
            
            # Waveform
            'waveform_alpha': 0.3,
            'waveform_color': 'steelblue',
            'waveform_width_ratio': 0.06,    # 3% della larghezza pagina
            'waveform_downsample': 200,      # 1 punto ogni N campioni
            # Loop mask
            'loop_mask_color': '#f4a261',    # arancio caldo
            'loop_mask_alpha': 0.18,
            'loop_mask_samples': 200,        # punti di campionamento del poligono

            # Stile
            'stream_gap_ratio': 0.05,        # gap tra stream (5% dell'altezza)
            'label_fontsize': 8,
            'title_fontsize': 12,
            # Envelope ranges (per normalizzazione)
            'envelope_ranges': {
                # === OUTPUT ===
                'volume': (-90, 0),           # dB
                'volume_prob': (0, 100),      # probabilità %
                'pan': (-180, 180),           # gradi (ciclico)
                'pan_prob': (0, 100),         # probabilità %
                
                # === GRAIN ===
                'grain_duration': (0.001, 1.0),  # secondi
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

            # Auto-zoom degli envelope a range ampio: se il movimento reale
            # occupa una banda stretta del range fisso, restringe il range di
            # display a `factor` x l'escursione reale (centrato), clampato al
            # range pieno. floor = min_span_ratio x range pieno (evita zoom
            # estremo su micro-movimenti). pan sempre escluso (ciclico).
            'envelope_autozoom': {
                'enabled': True,
                'factor': 2.0,
                'min_span_ratio': 0.04,
                'params': {
                    'pointer_speed', 'volume', 'density', 'loop_dur',
                    'grain_duration', 'pitch', 'voice_pitch_offset',
                },
            },
        }
        
        self.config = default_config
        if config:
            self.config.update(config)
        
        # Cache waveform
        self.waveform_cache = {}
        
        # Dati calcolati
        self.total_duration = None
        self.page_count = None
        self.page_layouts = []
        
        # Colormap
        self.cmap = plt.get_cmap(self.config['grain_colormap'])
    
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
        
        # Costruisci path completo
        full_path = PATHSAMPLES + sample_path
        
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

    def _add_pitch_colorbar(self, fig, ax, cents_range, streams,
                            page_start, page_end):
        """
        Colorbar compatta con la scala colore pitch del subplot.

        Con cents_range (auto-zoom attivo): scala in cents zoomata.
        Senza: scala fissa pitch_range in ratio, solo se il subplot ha grani
        visibili (cents_range None copre anche il caso zero grani).
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

        cbar = fig.colorbar(
            ScalarMappable(norm=norm, cmap=self.cmap),
            ax=ax, fraction=0.03, pad=0.01
        )
        cbar.set_label(label, fontsize=self.config['label_fontsize'] - 1)
        cbar.ax.tick_params(labelsize=self.config['label_fontsize'] - 2)

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
        """Renderizza pagina con subplot separati per ogni SAMPLE (non per stream)."""
        
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
        # RAGGRUPPA STREAM PER SAMPLE_PATH
        # =========================================================================
        samples_dict = {}
        for stream in active_streams:
            path = stream.sample
            if path not in samples_dict:
                samples_dict[path] = []
            samples_dict[path].append(stream)
        
        # Numero subplot = numero di sample unici
        n_samples = len(samples_dict)
        
        if n_samples == 0:
            # Pagina vuota
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "Nessuno stream attivo",
                    ha='center', va='center', fontsize=14, color='gray')
            ax.axis('off')
            
            title = f"Pagina {page_idx + 1}/{self.page_count} — " \
                    f"[{page_start:.1f}s - {page_end:.1f}s]"
            fig.suptitle(title, fontsize=self.config['title_fontsize'])
            return fig
        
        # =========================================================================
        # SETUP GRIDSPEC
        # =========================================================================
        waveform_ratio = self.config['waveform_width_ratio']
        envelope_ratio = self.config['envelope_panel_ratio'] if has_envelopes else 0.0
        
        # Altezza per sample (divisa equamente)
        stream_total_ratio = 1.0 - envelope_ratio
        sample_row_height = stream_total_ratio / n_samples
        
        # Crea height_ratios
        if has_envelopes:
            height_ratios = [sample_row_height] * n_samples + [envelope_ratio]
            n_rows = n_samples + 1
        else:
            height_ratios = [sample_row_height] * n_samples
            n_rows = n_samples
        
        # GridSpec: n_rows righe × 2 colonne
        gs = fig.add_gridspec(
            n_rows, 2,
            width_ratios=[waveform_ratio, 1 - waveform_ratio],
            height_ratios=height_ratios,
            wspace=0.02,
            hspace=0.0  # gap verticale tra sample
        )
        
        # Margini
        margin_ratio = margin_mm / page_w_mm
        fig.subplots_adjust(
            left=margin_ratio,
            right=1 - margin_ratio,
            bottom=margin_ratio + 0.02,
            top=1 - margin_ratio - 0.03
        )
        
        # =========================================================================
        # DISEGNA SUBPLOT PER OGNI SAMPLE
        # =========================================================================
        for i, (sample_path, streams) in enumerate(samples_dict.items()):
            # Crea subplot per questo sample
            ax_wave = fig.add_subplot(gs[i, 0])
            ax_grain = fig.add_subplot(gs[i, 1])
            
            # Ottieni durata sample
            sample_duration = self._get_sample_duration(sample_path)
            
            # Disegna waveform UNA VOLTA (usa il primo stream solo per il path)
            self._draw_waveform_full(ax_wave, streams[0], sample_duration)
            
            # Range colore pitch auto-zoomato sul subplot (tutti gli stream)
            cents_range = self._compute_pitch_color_range(
                streams, page_start, page_end)

            # Disegna grani di TUTTI gli stream che usano questo sample
            for stream in streams:
                self._draw_loop_mask(ax_grain, stream, page_start, page_end, sample_duration)
                self._draw_grains_full(ax_grain, stream, sample_duration,
                                    page_start, page_end, cents_range)
                self._draw_stream_label_full(ax_grain, stream, page_start, sample_duration)

            # Legenda della scala colore pitch (auto-zoomata o fissa)
            self._add_pitch_colorbar(fig, ax_grain, cents_range,
                                     streams, page_start, page_end)
            # Configura assi waveform
            ax_wave.set_ylim(-0.02, sample_duration+0.02)
            ax_wave.set_xlim(-1.1, 1.1)
            ax_wave.set_ylabel(f"Sample (s)\n{sample_path}", 
                            fontsize=self.config['label_fontsize'])
            ax_wave.set_xticks([])
            ax_wave.tick_params(axis='y', labelsize=self.config['label_fontsize'] - 1)
            ax_wave.axvline(x=0, color='gray', linewidth=0.5, alpha=0.5, linestyle=':')
            ax_wave.grid(True, alpha=0.2, linestyle=':', axis='y')
            
            # Configura assi grani
            ax_grain.set_xlim(page_start, page_end)
            ax_grain.set_ylim(-0.02, sample_duration+0.02)
            ax_grain.set_ylabel("")  # label già nella waveform
            ax_grain.tick_params(axis='y', labelsize=self.config['label_fontsize'] - 1)
            ax_grain.grid(True, alpha=0.3, linestyle='--')
            
            # X label solo sull'ultimo sample (se non ci sono envelope)
            if i == n_samples - 1 and not has_envelopes:
                ax_grain.set_xlabel("Tempo (s)", fontsize=self.config['label_fontsize'])
            else:
                ax_grain.set_xticklabels([])
        
        # =========================================================================
        # SUBPLOT ENVELOPE (se presenti)
        # =========================================================================
        if has_envelopes:
            ax_env = fig.add_subplot(gs[n_samples, 1])

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
                    fontsize=self.config['label_fontsize'] - 2,
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
            ax_env.set_xlabel("Tempo (s)", fontsize=self.config['label_fontsize'])
            ax_env.set_ylabel("", fontsize=self.config['label_fontsize'])
            ax_env.set_yticklabels([])
            ax_env.tick_params(axis='y', length=0)
            ax_env.grid(True, alpha=0.3, linestyle='--', axis='x')

            ax_env.spines['top'].set_position(('axes', 1))     
            ax_env.spines['bottom'].set_position(('axes', 0))  


            # Legenda envelope (per-lane, allineata alle curve — issue #91)
            if legend_entries:
                ax_legend = fig.add_subplot(gs[n_samples, 0])
                self._draw_envelope_legend(ax_legend, legend_entries)
        # =========================================================================
        # TITOLO
        # =========================================================================
        title = f"Pagina {page_idx + 1}/{self.page_count} — " \
                f"[{page_start:.1f}s - {page_end:.1f}s]"
        fig.suptitle(title, fontsize=self.config['title_fontsize'])
        
        return fig

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
        
        for grain in visible_grains:
            # X: tempo partitura
            x = grain.onset
            width = grain.duration
            
            # Y: posizione assoluta nel sample (in secondi)
            pointer_y = grain.pointer_pos
            
            # Altezza: sample consumato (in secondi)
            # Considerando durata
            height = grain.duration # * abs(grain.pitch_ratio)

            # Dimensione punta freccia (% della larghezza)
            arrow_head_width = width * 0.5  # 30% della larghezza del grano

            # Direzione
            if grain.pitch_ratio < 0:
                y_top = pointer_y
                y_bottom = pointer_y - height

                # 7 punti: rettangolo con punta triangolare in basso
                vertices = [
                    (x, y_top),                           # alto sinistra
                    (x + width, y_top),                   # alto destra
                    (x + width, y_bottom + arrow_head_width),  # prima della punta destra
                    (x + width/2, y_bottom),              # punta centrale (GIÙ)
                    (x, y_bottom + arrow_head_width),     # prima della punta sinistra
                ]
            else:
                # FRECCIA SU (forward)
                y_bottom = pointer_y
                y_top = pointer_y + height
                
                # 7 punti: rettangolo con punta triangolare in alto
                vertices = [
                    (x, y_bottom),                        # basso sinistra
                    (x + width, y_bottom),                # basso destra
                    (x + width, y_top - arrow_head_width),  # prima della punta destra
                    (x + width/2, y_top),                 # punta centrale (SU)
                    (x, y_top - arrow_head_width),        # prima della punta sinistra
                ]
            
            # Crea poligono
            poly = mpatches.Polygon(vertices, closed=True)
            polygons.append(poly)
            
            # Colore
            color = list(self._pitch_to_color(abs(grain.pitch_ratio),
                                              cents_range))
            color[3] = self._volume_to_alpha(grain.volume)
            colors.append(color)
        
        # Collection
        collection = PatchCollection(
            polygons,
            facecolors=colors,
            edgecolors='black',
            linewidths=0.02,
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
            fontsize=self.config['label_fontsize'] - 1,
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
        """
        Estrae tutti i parametri che sono Envelope dallo stream.
        
        Soluzione C: usa gli schema come single source of truth.
        Suffisso "_prob" per le probabilità dephase.
        
        Returns:
            dict: {nome_parametro: Envelope}
        """
        from envelopes.envelope import Envelope
        from parameters.parameter import Parameter
        from shared.probability_gate import EnvelopeGate, RandomGate
        from parameters.parameter_schema import (
            STREAM_PARAMETER_SCHEMA, 
            POINTER_PARAMETER_SCHEMA, 
            PITCH_PARAMETER_SCHEMA,
            DENSITY_PARAMETER_SCHEMA,
        )
        
        envelopes = {}
        show_static = self.config.get('show_static_params', False)
        
        # Combina tutti gli schema disponibili
        all_schemas = (
            STREAM_PARAMETER_SCHEMA + 
            POINTER_PARAMETER_SCHEMA + 
            PITCH_PARAMETER_SCHEMA + 
            DENSITY_PARAMETER_SCHEMA        )
        
        # Itera su tutte le specifiche dei parametri
        for spec in all_schemas:
            # Salta se l'attributo non esiste nello stream
            if not hasattr(stream, spec.name):
                continue
            
            param = getattr(stream, spec.name)
            
            # =====================================================================
            # PARTE 1: ESTRAZIONE VALORE PRINCIPALE
            # =====================================================================
            
            # Determina il valore effettivo (raw o da Parameter)
            if isinstance(param, Parameter):
                value = param._value
            else:
                value = param
            
            # Aggiungi envelope del valore principale
            if isinstance(value, Envelope):
                bp_values = [bp[1] for bp in value.breakpoints]
                is_static = len(set(bp_values)) == 1
                if len(value.breakpoints) > 1 and not is_static:
                    envelopes[spec.name] = value
                elif show_static:
                    val = bp_values[0]
                    envelopes[spec.name] = Envelope([[0, val], [stream.duration, val]])
            
            # Valori statici (numero)
            elif isinstance(value, (int, float)) and show_static:
                if value is not None:
                    envelopes[spec.name] = Envelope([[0, value], [stream.duration, value]])
            
            # =====================================================================
            # PARTE 2: ESTRAZIONE DEPHASE (PROBABILITA) CON SUFFISSO "_prob"
            # =====================================================================
            # Il dephase oggi e' un ProbabilityGate iniettato in
            # param._probability_gate (issue #96): EnvelopeGate per curve nel
            # tempo, RandomGate per probabilita' costante. Never/Always: nessuna
            # curva da disegnare.
            if spec.dephase_key and isinstance(param, Parameter):
                gate = getattr(param, '_probability_gate', None)
                prob_key = f"{spec.name}_prob"

                if isinstance(gate, EnvelopeGate):
                    env = gate.envelope
                    bp_values = [bp[1] for bp in env.breakpoints]
                    is_static = len(set(bp_values)) == 1
                    if len(env.breakpoints) > 1 and not is_static:
                        envelopes[prob_key] = env
                    elif show_static:
                        val = bp_values[0]
                        envelopes[prob_key] = Envelope([[0, val], [stream.duration, val]])

                elif isinstance(gate, RandomGate) and show_static:
                    prob = gate.probability
                    envelopes[prob_key] = Envelope([[0, prob], [stream.duration, prob]])

            # =====================================================================
            # PARTE 3: ESTRAZIONE RANGE (_mod_range) PER SPEC CON range_path
            # =====================================================================
            # Per parametri come pointer_deviation il valore base e' un dummy 0
            # costante (yaml_path='_dummy_fixed_zero_'); la deviazione reale vive
            # in param._mod_range (issue #96). Chiave = spec.name: sovrascrive il
            # dummy-0 eventualmente emesso da PARTE 1.
            if spec.range_path and isinstance(param, Parameter):
                mod_range = getattr(param, '_mod_range', None)

                if isinstance(mod_range, Envelope):
                    bp_values = [bp[1] for bp in mod_range.breakpoints]
                    is_static = len(set(bp_values)) == 1
                    if len(mod_range.breakpoints) > 1 and not is_static:
                        envelopes[spec.name] = mod_range
                    elif show_static:
                        val = bp_values[0]
                        envelopes[spec.name] = Envelope([[0, val], [stream.duration, val]])

                elif isinstance(mod_range, (int, float)) and show_static:
                    envelopes[spec.name] = Envelope([[0, mod_range], [stream.duration, mod_range]])

        # =====================================================================
        # PITCH: unit-driven, non più in PITCH_PARAMETER_SCHEMA. Raccolto da
        # stream.pitch_value (Envelope o scalare) sotto la chiave 'pitch';
        # range e simbolo derivano da stream.pitch_unit alla normalizzazione.
        # =====================================================================
        pitch_value = getattr(stream, 'pitch_value', None)
        if isinstance(pitch_value, Envelope):
            bp_values = [bp[1] for bp in pitch_value.breakpoints]
            is_static = len(set(bp_values)) == 1
            if len(pitch_value.breakpoints) > 1 and not is_static:
                envelopes['pitch'] = pitch_value
            elif show_static:
                envelopes['pitch'] = Envelope([[0, bp_values[0]], [stream.duration, bp_values[0]]])
        elif isinstance(pitch_value, (int, float)) and show_static:
            envelopes['pitch'] = Envelope([[0, pitch_value], [stream.duration, pitch_value]])

        # =====================================================================
        # ESTRAZIONE PER NOME ESPLICITO (issue #88). Parametri non raggiungibili
        # dal ciclo sugli schemi:
        #   - num_voices / scatter: Parameter privati dello Stream, fuori da ogni
        #     *_PARAMETER_SCHEMA.
        #   - pointer_speed: lo schema lo definisce come `pointer_speed_ratio`, ma
        #     lo Stream espone la property `pointer_speed` → hasattr sul nome di
        #     schema e' falso e il ciclo lo salta.
        # Stessa logica del valore principale (PART 1): Parameter → _value; solo
        # Envelope dinamici, statici solo con show_static.
        # =====================================================================
        for name in ('num_voices', 'scatter', 'pointer_speed'):
            if not hasattr(stream, name):
                continue
            param = getattr(stream, name)
            value = param._value if isinstance(param, Parameter) else param
            if isinstance(value, Envelope):
                bp_values = [bp[1] for bp in value.breakpoints]
                is_static = len(set(bp_values)) == 1
                if len(value.breakpoints) > 1 and not is_static:
                    envelopes[name] = value
                elif show_static:
                    val = bp_values[0]
                    envelopes[name] = Envelope([[0, val], [stream.duration, val]])
            elif isinstance(value, (int, float)) and show_static:
                envelopes[name] = Envelope([[0, value], [stream.duration, value]])

        # =====================================================================
        # POINTER DEVIATION (issue #96). pointer_deviation NON e' esposto sullo
        # Stream: il Parameter vive in stream._pointer.deviation (PointerController)
        # e hasattr(stream,'pointer_deviation') e' False, quindi il ciclo sugli
        # schemi lo salta. offset_range sta in _mod_range (chiave
        # 'pointer_deviation'), il dephase nel _probability_gate (chiave
        # 'pointer_deviation_prob'). Stessa logica di PARTE 2 e PARTE 3.
        # =====================================================================
        pointer = getattr(stream, '_pointer', None)
        deviation = getattr(pointer, 'deviation', None)
        if isinstance(deviation, Parameter):
            # offset_range -> chiave 'pointer_deviation'
            mod_range = deviation._mod_range
            if isinstance(mod_range, Envelope):
                bp_values = [bp[1] for bp in mod_range.breakpoints]
                is_static = len(set(bp_values)) == 1
                if len(mod_range.breakpoints) > 1 and not is_static:
                    envelopes['pointer_deviation'] = mod_range
                elif show_static:
                    val = bp_values[0]
                    envelopes['pointer_deviation'] = Envelope([[0, val], [stream.duration, val]])
            elif isinstance(mod_range, (int, float)) and show_static:
                envelopes['pointer_deviation'] = Envelope([[0, mod_range], [stream.duration, mod_range]])

            # dephase -> chiave 'pointer_deviation_prob'
            gate = deviation._probability_gate
            if isinstance(gate, EnvelopeGate):
                env = gate.envelope
                bp_values = [bp[1] for bp in env.breakpoints]
                is_static = len(set(bp_values)) == 1
                if len(env.breakpoints) > 1 and not is_static:
                    envelopes['pointer_deviation_prob'] = env
                elif show_static:
                    val = bp_values[0]
                    envelopes['pointer_deviation_prob'] = Envelope([[0, val], [stream.duration, val]])
            elif isinstance(gate, RandomGate) and show_static:
                prob = gate.probability
                envelopes['pointer_deviation_prob'] = Envelope([[0, prob], [stream.duration, prob]])

        # =====================================================================
        # FILTRO SELETTIVO (issue #101). Applicato sulle chiavi del dict finale
        # cosi' copre ogni path di estrazione (main, _prob, _mod_range, pitch,
        # nomi espliciti). Il filtro interseca: non forza la visibilita' degli
        # statici, che restano governati da show_static_params.
        # =====================================================================
        env_filter = self.config.get('envelope_filter')
        if env_filter is not None:
            envelopes = {k: v for k, v in envelopes.items() if k in env_filter}

        return envelopes

    def _full_range(self, param_name):
        """
        Range pieno (min, max) di un parametro, o None se non disponibile.

        pitch è unit-driven (bounds dall'unità attiva); gli altri vengono da
        config['envelope_ranges'].
        """
        if param_name == 'pitch':
            unit = getattr(self, '_current_pitch_unit', None)
            if unit is not None:
                b = unit.value_bounds()
                if b.max_val is not None and b.max_val != b.min_val:
                    return (b.min_val, b.max_val)
            return None
        rng = self.config['envelope_ranges'].get(param_name)
        if rng is None or rng[0] == rng[1]:
            return None
        return (rng[0], rng[1])

    def _compute_display_ranges(self, envelopes, stream, t_start, t_end):
        """
        Calcola, per ogni envelope a range ampio, un range di display ristretto
        all'escursione reale (auto-zoom). Vedi config['envelope_autozoom'].

        Returns:
            dict {param_name: (disp_min, disp_max)} solo per i parametri zoomati.
        """
        cfg = self.config.get('envelope_autozoom', {})
        if not cfg.get('enabled', False):
            return {}

        params = cfg.get('params', set())
        factor = cfg.get('factor', 2.0)
        min_span_ratio = cfg.get('min_span_ratio', 0.04)
        stream_start = stream.onset

        result = {}
        for param_name, envelope in envelopes.items():
            if param_name == 'pan' or param_name not in params:
                continue
            full = self._full_range(param_name)
            if full is None:
                continue
            full_min, full_max = full
            full_span = full_max - full_min

            # Escursione reale nella finestra visibile: campiona densamente la
            # curva (cattura overshoot cubic) e includi i breakpoint.
            t_rel0 = max(0.0, t_start - stream_start)
            t_rel1 = max(t_rel0, t_end - stream_start)
            samples = [envelope.evaluate(t) for t in np.linspace(t_rel0, t_rel1, 64)]
            samples += [v for t, v in envelope.breakpoints if t_rel0 <= t <= t_rel1]
            if not samples:
                continue
            v_min, v_max = min(samples), max(samples)
            span_real = v_max - v_min
            center = (v_min + v_max) / 2.0

            floor = min_span_ratio * full_span
            disp_span = min(max(factor * span_real, floor), full_span)
            if disp_span >= full_span:
                continue  # no-op: il movimento riempie già il range pieno

            half = disp_span / 2.0
            disp_min = center - half
            disp_max = center + half
            # Trasla dentro [full_min, full_max] mantenendo l'ampiezza.
            if disp_min < full_min:
                disp_min, disp_max = full_min, full_min + disp_span
            elif disp_max > full_max:
                disp_min, disp_max = full_max - disp_span, full_max

            result[param_name] = (disp_min, disp_max)

        return result

    def _normalize_envelope_value(self, param_name, value):
        """
        Normalizza un valore di envelope a 0-1 usando i range fissi.
        
        Args:
            param_name: nome del parametro
            value: valore da normalizzare
            
        Returns:
            float: valore normalizzato 0-1
        """
        # PITCH unit-driven: i bounds vengono dall'unità attiva, non dai range statici.
        if param_name == 'pitch':
            unit = getattr(self, '_current_pitch_unit', None)
            if unit is not None:
                b = unit.value_bounds()
                if b.max_val is not None and b.max_val != b.min_val:
                    return np.clip((value - b.min_val) / (b.max_val - b.min_val), 0, 1)
            return np.clip(value, 0, 1)

        # Auto-zoom: se è attivo un display range per questo parametro, usalo al
        # posto del range fisso (la curva sfrutta tutta l'altezza della lane).
        display_ranges = getattr(self, '_current_display_ranges', None) or {}
        if param_name in display_ranges:
            min_val, max_val = display_ranges[param_name]
            if param_name == 'pan':
                value = ((value + 180) % 360) - 180
            if max_val != min_val:
                return np.clip((value - min_val) / (max_val - min_val), 0, 1)
            return np.clip(value, 0, 1)

        ranges = self.config['envelope_ranges']

        if param_name in ranges:
            min_val, max_val = ranges[param_name]

            # Pan è ciclico: gestisci valori fuori range
            if param_name == 'pan':
                # Normalizza a -180..180 usando modulo
                value = ((value + 180) % 360) - 180

            # Normalizza
            normalized = (value - min_val) / (max_val - min_val)
            return np.clip(normalized, 0, 1)
        else:
            # Fallback: assume già normalizzato
            return np.clip(value, 0, 1)

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
            # Colore
            color = colors.get(param_name, '#333333')

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
            'num_voices': ' voci',
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
            
            # Disegna etichetta (offset per evitare sovrapposizione)
            ax.annotate(
                label,
                xy=(t_abs, y_pos),
                xytext=(3, 3),
                textcoords='offset points',
                fontsize=6,
                color=color,
                alpha=0.9,
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

            env_types = sorted(envelopes.keys())
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
    }

    def _legend_display_name(self, param_name):
        """Nome corto per la legenda. Suffisso '_prob' → ' %' (probabilita')."""
        if param_name.endswith('_prob'):
            base = param_name[:-len('_prob')]
            return f"{self._legend_display_name(base)} %"
        return self._ENV_LEGEND_SHORT.get(param_name, param_name.replace('_', ' '))

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
            color = colors.get(param_name, '#333333')
            ax.plot([0.1, 0.15], [y, y], color=color, linewidth=2)
            # clip_on=True: anche un nome inatteso non sfora mai nel plot,
            # viene tagliato al bordo della colonna legenda (issue #96).
            ax.text(0.4, y, self._legend_display_name(param_name),
                    fontsize=self.config['label_fontsize'] - 2,
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
        
        with PdfPages(output_path) as pdf:
            for fig in figures:
                pdf.savefig(fig, dpi=150)
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


