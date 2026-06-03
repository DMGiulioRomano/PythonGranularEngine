# =============================================================================
# SCORE VISUALIZER - Partitura grafica per sintesi granulare
# =============================================================================

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import soundfile as sf
from math import ceil

# Path samples (stesso del progetto)
PATHSAMPLES = './refs/'


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
            # Paginazione
            'page_duration': 30.0,           # secondi per pagina
            'page_size': (420, 297),         # A3 in mm
            'orientation': 'landscape',
            'margins_mm': 20,
            
            # Grani
            'grain_colormap': 'coolwarm',    # pitch_ratio → colore
            'grain_alpha_range': (0.3, 1.0), # volume → alpha
            'pitch_range': (0.5, 2.0),       # range per normalizzare colori
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
                'voice_pitch_offset': (-48, 48),  # semitoni
                'voice_pointer_offset': (-1.0, 1.0),  # normalizzato
                'voice_pointer_range': (0.0, 1.0),    # normalizzato
            },

            'envelope_colors': {
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
                'voice_pitch_offset': '#c49c94',  # beige
                'voice_pointer_offset': '#f7b6d2', # rosa chiaro
                'voice_pointer_range': '#c7c7c7',  # grigio chiaro
            },
            'envelope_panel_ratio': 0.3,      # 30% altezza per envelope
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
    
    def _pitch_to_color(self, pitch_ratio):
        """Mappa pitch_ratio → colore dal colormap."""
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
        all_envelope_types = set()
        
        for i, (sample_path, streams) in enumerate(samples_dict.items()):
            # Crea subplot per questo sample
            ax_wave = fig.add_subplot(gs[i, 0])
            ax_grain = fig.add_subplot(gs[i, 1])
            
            # Ottieni durata sample
            sample_duration = self._get_sample_duration(sample_path)
            
            # Disegna waveform UNA VOLTA (usa il primo stream solo per il path)
            self._draw_waveform_full(ax_wave, streams[0], sample_duration)
            
            # Disegna grani di TUTTI gli stream che usano questo sample
            for stream in streams:
                self._draw_loop_mask(ax_grain, stream, page_start, page_end, sample_duration)
                self._draw_grains_full(ax_grain, stream, sample_duration, 
                                    page_start, page_end)
                self._draw_stream_label_full(ax_grain, stream, page_start, sample_duration)
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
            
            # Calcola altezze per ogni stream nel subplot envelope
            n_streams_with_env = len([s for s in active_streams if self._get_stream_envelopes(s)])
            
            if n_streams_with_env > 0:
                gap_ratio = 0.02  # piccolo gap tra stream
                total_gap = gap_ratio * 2 * (n_streams_with_env)
                env_slot_height = (1.0 - total_gap) / n_streams_with_env
                
                slot_idx = 0
                for stream in active_streams:
                    if self._get_stream_envelopes(stream):
                        # Calcola y_base e y_height per questo stream

                        y_single_stream_with_gap=gap_ratio*2+(env_slot_height)
                        y_that_stream=y_single_stream_with_gap*slot_idx
                        
                        y_base=y_that_stream + gap_ratio
                        y_height= env_slot_height
                        # Disegna envelope in questa "corsia"
                        env_types = self._draw_envelopes(ax_env, stream, y_base, y_height,
                                                        page_start, page_end)
                        all_envelope_types.update(env_types)
                        
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
                            ax_env.axhline(y=y_that_stream, color='darkgray', 
                                        linewidth=1, alpha=0.4, linestyle='-')
                        
                        slot_idx += 1
            
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


            # Legenda envelope
            if all_envelope_types:
                ax_legend = fig.add_subplot(gs[n_samples, 0])
                self._draw_envelope_legend(ax_legend, all_envelope_types)
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


    def _draw_grains_full(self, ax, stream, sample_duration, page_start, page_end):
        """Disegna grani con coordinate Y assolute nel sample."""
        
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
            color = list(self._pitch_to_color(abs(grain.pitch_ratio)))
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
            
            # Se il parametro ha un dephase_key E è un Parameter object
            if spec.dephase_key and isinstance(param, Parameter):
                mod_prob = getattr(param, '_mod_prob', None)
                
                if mod_prob is not None:
                    # CHIAVE: Usa spec.name + "_prob" come nome nell'envelope
                    prob_key = f"{spec.name}_prob"
                    
                    if isinstance(mod_prob, Envelope):
                        # Solo envelope dinamici
                        if len(mod_prob.breakpoints) > 1:
                            envelopes[prob_key] = mod_prob
                        # Envelope statici (solo se richiesto)
                        elif show_static and len(mod_prob.breakpoints) == 1:
                            val = mod_prob.breakpoints[0][1]
                            envelopes[prob_key] = Envelope([[0, val], [stream.duration, val]])
                    
                    # Probabilita statiche (numero)
                    elif isinstance(mod_prob, (int, float)) and show_static:
                        envelopes[prob_key] = Envelope([[0, mod_prob], [stream.duration, mod_prob]])

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

        return envelopes

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

    def _draw_envelope_legend(self, ax, envelope_types):
        """
        Disegna la legenda degli envelope nel subplot dedicato.
        """
        ax.axis('off')
        
        colors = self.config['envelope_colors']
        
        # Ordina per nome
        sorted_types = sorted(envelope_types)
        
        # Posiziona verticalmente
        n = len(sorted_types)
        y_positions = np.linspace(0.85, 0.15, n) if n > 1 else [0.5]
        
        for i, param_name in enumerate(sorted_types):
            color = colors.get(param_name, '#333333')
            
            # Linea di esempio
            ax.plot([0.1, 0.15], [y_positions[i], y_positions[i]], 
                   color=color, linewidth=2)
            
            # Label
            ax.text(0.4, y_positions[i], param_name.replace('_', ' '),
                   fontsize=self.config['label_fontsize'] - 2,
                   verticalalignment='center',
                   color=color)
        
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


