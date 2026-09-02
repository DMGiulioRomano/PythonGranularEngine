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

from pge.shared.constants import DEFAULT_OUTPUT_SR

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

# La stessa mappa per la carta in bianco e nero (issue #248), scelta dal preset
# `bw`. I due bracci di PITCH_DIVERGING hanno la STESSA chiarezza: convertita
# in grigio, un grano a +300 cent e uno a -300 cent diventano lo stesso grigio
# e il segno del detune sparisce. Il grigio ha un solo asse percettivo, la
# luminanza: qui e' speso tutto sul detune, monotono dal grave all'acuto.
#
# Compressa a circa 0.15-0.85 invece che a tutto il dominio: col braccio alto
# sul bianco i grani acuti sparirebbero sulla pagina, col basso sul nero si
# confonderebbero con assi e griglia. Il centro e' il grigio medio, come il
# #777777 della mappa a colori: nessun detune = nessuno scarto dal mezzo.
#
# Quelli sono i valori della MAPPA. Sulla pagina il grano e' composito su
# fondo bianco all'alpha del preset (`a*g + (1-a)`, alpha 0.9), quindi la
# banda diventa 0.23-0.87 e lo zero cade a 0.55: piu' chiara di mezzo tono,
# non centrata. E' la barra a doversi adeguare al grano, non viceversa —
# _add_pitch_colorbar le passa la stessa alpha, cosi' la chiave di lettura
# mostra il grigio che il lettore ha davanti invece del colore nudo.
#
# La rampa e' lineare nel valore sRGB, non in L*: l'obiettivo e' stare dentro
# i due estremi utili in stampa, non l'uniformita' percettiva.
PITCH_DIVERGING_BW = LinearSegmentedColormap.from_list(
    'pitch_div_bw', ['#262626', '#535353', '#808080', '#acacac', '#d9d9d9']
)


def _register_colormap(cmap):
    """Registra una colormap col suo nome, una volta sola.

    Con guardia: idempotente anche su re-import del modulo.
    """
    try:
        plt.get_cmap(cmap.name)
    except (ValueError, KeyError):
        try:
            import matplotlib as mpl
            mpl.colormaps.register(cmap)
        except (AttributeError, ImportError):
            plt.register_cmap(cmap=cmap)


_register_colormap(PITCH_DIVERGING)
_register_colormap(PITCH_DIVERGING_BW)

# Colori di default e universo dei nomi plottabili. Definiti nel modulo
# matplotlib-free rendering.envelope_extractor (issue #150) e ri-esportati qui
# per retro-compatibilita': main.py importa PLOT_ENVELOPE_KEYS da qui, i test
# importano ENVELOPE_COLORS da qui.
from pge.rendering.envelope_extractor import (  # noqa: F401,E402
    ENVELOPE_COLORS, ENVELOPE_STYLE_DEFAULT, PLOT_ENVELOPE_KEYS)
from pge.rendering import envelope_display  # noqa: E402
from pge.rendering import grain_visuals  # noqa: E402
from pge.rendering import magnifier_projection  # noqa: E402
from pge.rendering import magnifier_targets  # noqa: E402
from pge.rendering import page_layout  # noqa: E402
from pge.rendering import waveform_peaks  # noqa: E402
from pge.rendering.visualizer_config import VisualizerConfig  # noqa: E402


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
        # Lo schema vive in rendering.visualizer_config: dichiarato, con merge
        # profondo dei gruppi annidati e rifiuto delle chiavi sconosciute.
        # Il risultato resta un dict perche' viz.config e il parametro config=
        # sono superficie pubblica.
        self.config = VisualizerConfig.from_overrides(config).as_dict()

        # Directory sample effettiva: config esplicita o fallback globale
        # (deprecato, mantenuto per compatibilita' coi monkey-patch esterni).
        self.samples_dir = self.config['samples_dir'] or PATHSAMPLES

        # Cache waveform
        self.waveform_cache = {}

        # Dati calcolati
        self.total_duration = None
        self.page_count = None
        self.page_layouts = []
        # Se la partitura, in QUALCHE pagina, ha una colorbar da mostrare:
        # decide la colonna del GridSpec per tutte (vedi
        # _score_has_pitch_variation). None = non ancora calcolato.
        self._score_pitch_variation = None
        
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

        self.total_duration = page_layout.total_duration(self.streams)
        self.page_layouts = page_layout.paginate(
            self.streams, self.config['page_duration'])
        self.page_count = len(self.page_layouts)
        # Le pagine sono cambiate: la risposta sulla colorbar va rifatta.
        self._score_pitch_variation = None

        print(f"Analisi completata: {self.page_count} pagine, "
              f"durata totale {self.total_duration:.2f}s")

    # =========================================================================
    # CARICAMENTO WAVEFORM
    # =========================================================================

    def _load_waveform(self, sample_path):
        """Carica il sample e lo riduce alla curva che si disegna.

        Qui vive l'I/O e la cache; la riduzione e' di
        rendering.waveform_peaks, che e' puro. Il risultato e'
        `(time_axis, amplitude, duration)`: due array della stessa lunghezza
        piu' la durata vera del file, con l'ampiezza normalizzata sul picco
        del segnale intero.

        La curva e' un inviluppo min/max, non un sottocampionamento a passo
        fisso (issue #233): due punti per bucket, il minimo e il massimo dei
        campioni che contiene. Il passo fisso perdeva i transienti piu'
        stretti del passo, aliasava, e produceva un numero di vertici
        proporzionale alla durata del file.
        """
        if sample_path in self.waveform_cache:
            return self.waveform_cache[sample_path]

        # Costruisci path completo (samples_dir iniettato o fallback globale)
        full_path = self.samples_dir + sample_path

        # Il try copre l'apertura, non la riduzione: un guasto di quest'ultima
        # (memoria, manopola fuori scala) non e' un file che non si apre, e
        # travestirlo da tale lo renderebbe silenzioso — messo in cache, non
        # ristampato piu'. Meglio che salga.
        try:
            audio, sr = sf.read(full_path)
            if len(audio) == 0:
                # La riduzione qui non solleva (torna curve vuote), ma una
                # durata nulla schiaccerebbe l'intero subplot dello stream su
                # un asse degenere: meglio il placeholder, che si legge.
                raise ValueError('file audio di lunghezza zero')
        except Exception as e:
            print(f"⚠️  Impossibile caricare waveform {sample_path}: {e}")
            # Waveform fittizia: piatta, lunga un secondo. Va in cache come le
            # altre, altrimenti ogni subplot di ogni pagina ritenterebbe
            # l'apertura di un file che non si apre e ristamperebbe l'avviso.
            result = (np.array([0.0, 1.0]), np.array([0.0, 0.0]), 1.0)
        else:
            time_axis, amplitude = waveform_peaks.peak_envelope(
                audio, sr,
                buckets=self.config['waveform_buckets'],
                width=self.config['waveform_downsample'])
            result = (time_axis, amplitude, len(audio) / sr)

        self.waveform_cache[sample_path] = result
        return result
    
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
        return grain_visuals.pitch_cents_range(
            streams, page_start, page_end,
            min_span_cents=az['min_span_cents'], pad_ratio=az['pad_ratio'])

    def _score_has_pitch_variation(self):
        """True se in almeno una pagina almeno uno stream ha un'escursione di
        altezza, cioe' se da qualche parte una colorbar verra' disegnata.

        E' la domanda che decide la COLONNA del GridSpec, e si pone una volta
        sola sull'intera partitura invece che pagina per pagina. Deciderla per
        pagina faceva variare la larghezza dell'area dati da una pagina
        all'altra dello stesso brano: stessa finestra temporale, due scale
        mm/secondo diverse, e l'asse dei tempi non piu' confrontabile a occhio.
        La geometria della pagina e' una proprieta' della partitura; quale
        stream mostra la barra resta una proprieta' dello stream.

        Memoizzata: la risposta dipende dai grani e dalle finestre di pagina,
        che dopo `analyze` non cambiano piu' (ed e' `analyze` a invalidarla).
        """
        if self._score_pitch_variation is None:
            self._score_pitch_variation = any(
                grain_visuals.has_pitch_variation(
                    [s], layout.t_start, layout.t_end)
                for layout in self.page_layouts
                for s in layout.streams
            )
        return self._score_pitch_variation

    def _add_pitch_colorbar(self, fig, cax_spec, cents_range, has_variation):
        """
        Colorbar compatta con la scala colore pitch del subplot, disegnata in una
        cella dedicata del GridSpec (cax_spec). Con un asse colorbar esplicito
        (cax=) invece di ax=, non viene rubata larghezza al subplot dei grani:
        grani ed envelope restano allineati sullo stesso bordo destro.

        has_variation: se le altezze dei grani di questo subplot variano
        davvero, calcolato una volta da chi disegna (grain_visuals
        .has_pitch_variation). Niente colorbar dove non variano (issue #217):
        l'autozoom allarga comunque al floor di mezzo semitono, quindi la scala
        mostrerebbe un gradiente pieno sopra grani tutti dello stesso colore.
        Vale anche col range fisso, dove il colore unico resta unico — e copre
        il caso zero grani, che di variazione non ne ha. Se non c'e' nulla da
        disegnare la cella resta vuota (nessun asse creato).

        Con cents_range (auto-zoom attivo): scala in cents zoomata. Senza:
        scala fissa pitch_range in ratio.
        """
        if not has_variation:
            return

        if cents_range is not None:
            norm = Normalize(cents_range[0], cents_range[1])
            label = 'pitch (cents)'
        else:
            p_min, p_max = self.config['pitch_range']
            norm = Normalize(p_min, p_max)
            label = 'pitch (ratio)'

        cax = fig.add_subplot(cax_spec)
        mappable = ScalarMappable(norm=norm, cmap=self.cmap)
        # La barra e' la CHIAVE di lettura dei grani, quindi deve mostrare il
        # grigio che i grani hanno davvero: composito su fondo bianco, non il
        # colore nudo della mappa. Con l'alpha guidata dal volume non c'e' un
        # valore solo da mostrare e la barra resta opaca, come e' sempre stata;
        # quando l'alpha e' FISSATA (preset B&W) la corrispondenza e'
        # esprimibile esattamente, e allora tacerla sarebbe un bias
        # sistematico: ogni grano si leggerebbe piu' acuto di quanto e'.
        # L'alpha si passa alla colorbar e non si cuoce dentro la mappa: cosi'
        # barra e grani compongono sullo stesso fondo, qualunque esso sia,
        # invece di dare per scontato il bianco.
        alpha_lo, alpha_hi = self.config['grain_alpha_range']
        alpha = float(alpha_lo) if alpha_lo == alpha_hi else None
        cbar = fig.colorbar(mappable, cax=cax, alpha=alpha)
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
        return self.cmap(grain_visuals.pitch_position(
            pitch_ratio, cents_range, pitch_range=self.config['pitch_range']))
    
    def _envelope_style(self, param_name):
        """(linestyle, linewidth) di una curva envelope.

        L'altro canale del colore, e con la stessa regola di chi lo risolve:
        le curve per-voce '__vN' prendono lo stile della base (issue #90), o
        una voce sarebbe l'unica linea piena della corsia.

        Con `envelope_styles` vuota — cioe' senza preset B&W — ogni chiave
        risolve a ENVELOPE_STYLE_DEFAULT, che e' il disegno storico: la
        partitura a colori non cambia di un punto.
        """
        styles = self.config.get('envelope_styles') or {}
        return tuple(styles.get(self._base_param_name(param_name),
                                ENVELOPE_STYLE_DEFAULT))

    def _projection_marker_edge(self):
        """(colore, spessore) dell'anello del marker di proiezione.

        Il colore ricade sull'accento della lente quando la config non ne
        dichiara uno proprio: e' il comportamento storico. La chiave esiste
        perche' l'anello e' l'unico pezzo della lente che atterra SULLA CURVA
        invece che sui grani, e col preset B&W curva e accento sono due neri —
        li' l'anello si spegne e il marker diventa un breakpoint qualunque.
        """
        cfg = self.config['magnify_projection']
        return (cfg['marker_edge'] or self.config['magnify_color'],
                cfg['markeredgewidth'])

    def _volume_to_alpha(self, volume_db):
        """Mappa volume (dB) → alpha/opacità."""
        return grain_visuals.volume_alpha(
            volume_db,
            volume_range=self.config['volume_range'],
            alpha_range=self.config['grain_alpha_range'])
    
    # =========================================================================
    # RENDERING
    # =========================================================================

    def render_page(self, page_idx):
        """Renderizza pagina con subplot separati per ogni STREAM (non per sample).

        issue #109: ogni stream ottiene il proprio subplot anche quando piu'
        stream condividono lo stesso sample (la waveform viene ridisegnata in
        ciascuno). Cosi' 4 stream producono 4 subplot anche se due puntano allo
        stesso file, e le label non collidono piu' su un asse condiviso.

        issue #113: la stessa simmetria vale per gli envelope — ogni stream ha
        la propria riga envelope subito sotto i suoi grani (stessa colonna,
        stesso asse temporale), anche se non ha envelope dinamici (lane vuota
        con label). Il vecchio pannello unico condiviso in fondo alla pagina
        non esiste piu'.
        """
        
        layout = self.page_layouts[page_idx]
        page_start, page_end = layout.t_start, layout.t_end
        active_streams = layout.streams
        
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
        # La colonna della colorbar si riserva solo se la partitura ha, da
        # qualche parte, un'escursione di altezza da mostrare (issue #217). La
        # domanda e' sull'intero score e non su questa pagina: cosi' tutte le
        # pagine hanno la stessa geometria e la stessa scala mm/secondo. Se
        # nessuna pagina varia, la larghezza torna all'area dati invece di
        # restare una cella vuota. La decisione va presa qui e non dentro
        # _add_pitch_colorbar: dopo il GridSpec la colonna c'e' gia'.
        colorbar_ratio = (self.config['colorbar_width_ratio']
                          if self._score_has_pitch_variation() else 0.0)
        envelope_ratio = self.config['envelope_panel_ratio'] if has_envelopes else 0.0

        # Altezza banda per stream (divisa equamente). Con envelope attivi ogni
        # banda si sdoppia in due righe contigue: grani sopra, envelope sotto
        # (issue #113) — la riga envelope prende envelope_panel_ratio della
        # banda del suo stream, cosi' ogni stream ha il proprio subplot
        # envelope allineato verticalmente ai suoi grani (simmetria 1:1 con
        # #109), anche quando non ha envelope dinamici (lane vuota).
        stream_band = 1.0 / n_streams

        if has_envelopes:
            height_ratios = []
            for _ in range(n_streams):
                height_ratios += [stream_band * (1.0 - envelope_ratio),
                                  stream_band * envelope_ratio]
            n_rows = 2 * n_streams
        else:
            height_ratios = [stream_band] * n_streams
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
            # Riga dei grani: con envelope attivi le bande sono sdoppiate
            # (grani=2i, envelope=2i+1); senza envelope una riga per stream.
            grain_row = 2 * i if has_envelopes else i

            # Crea subplot per questo stream
            ax_wave = fig.add_subplot(gs[grain_row, 0])
            ax_grain = fig.add_subplot(gs[grain_row, 1])

            # Sample e durata dello stream corrente
            sample_path = stream.sample
            sample_duration = self._get_sample_duration(sample_path)

            # Disegna waveform del sample dello stream (ridisegnata per ogni
            # subplot anche se il sample e' condiviso; _load_waveform fa cache).
            self._draw_waveform_full(ax_wave, stream, sample_duration)

            # Range colore pitch auto-zoomato sui grani di questo stream, e se
            # quei grani un'escursione ce l'hanno davvero (una volta sola: la
            # risposta serve alla colorbar piu' sotto).
            cents_range = self._compute_pitch_color_range(
                [stream], page_start, page_end)
            stream_pitch_varies = grain_visuals.has_pitch_variation(
                [stream], page_start, page_end)

            # Disegna grani, loop mask e label dello stream
            self._draw_loop_mask(ax_grain, stream, page_start, page_end, sample_duration)
            self._draw_grains_full(ax_grain, stream, sample_duration,
                                   page_start, page_end, cents_range)
            self._draw_stream_label_full(ax_grain, stream, page_start, sample_duration)

            entry = {
                'stream': stream,
                'ax': ax_grain,
                'sample_duration': sample_duration,
                'cents_range': cents_range,
                # Corsia envelope dello stream: riempite piu' sotto, quando la
                # riga envelope viene creata. La lente le usa per proiettare il
                # proprio istante sulle curve (issue #214); restano None per
                # una pagina senza envelope, e il record resta vuoto per uno
                # stream tutto statico (corsia presente ma senza curve).
                'ax_env': None,
                'env_render': magnifier_projection.EnvelopeLaneRender(),
            }
            stream_entries.append(entry)

            # Legenda della scala colore pitch (auto-zoomata o fissa) nella
            # colonna dedicata della riga grani: non ruba larghezza al subplot.
            self._add_pitch_colorbar(fig, gs[grain_row, 2], cents_range,
                                     stream_pitch_varies)
            # Configura assi waveform
            ax_wave.set_ylim(-0.02, sample_duration+0.02)
            ax_wave.set_xlim(-1.1, 1.1)
            ax_wave.set_ylabel(f"{self._read_position_label()}\n{sample_path}",
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

            # =====================================================================
            # RIGA ENVELOPE DELLO STREAM (issue #113)
            # =====================================================================
            # Un subplot envelope per stream, subito sotto i suoi grani, nella
            # stessa colonna centrale: stesso bordo destro/sinistro e stesso
            # asse temporale. Presente anche per stream senza envelope dinamici
            # (lane vuota), cosi' il conteggio resta 1:1 coi subplot dei grani.
            if has_envelopes:
                ax_env = fig.add_subplot(gs[grain_row + 1, 1],
                                         label=f'env:{stream.stream_id}')
                entry['ax_env'] = ax_env

                # Layout condiviso lane/legenda (issue #91), ora calcolato per
                # il singolo stream: 0 lane (stream tutto statico) o 1 lane.
                lanes, legend_entries = self._compute_env_legend_layout([stream])

                for lane in lanes:
                    entry['env_render'] = self._draw_envelopes(
                        ax_env, lane.stream, lane.y_base,
                        lane.y_height, page_start, page_end)

                # Label stream nella lane envelope: presente anche a lane
                # vuota, cosi' la corsia resta attribuibile al suo stream.
                ax_env.text(
                    0.01, 0.5, stream.stream_id,
                    transform=ax_env.transAxes,
                    fontsize=self._fs(self.config['label_fontsize'] - 2),
                    verticalalignment='center',
                    color='gray',
                    alpha=0.6
                )

                # Configura assi envelope
                ax_env.set_xlim(page_start, page_end)
                ax_env.set_ylim(0, 1)
                ax_env.set_yticklabels([])
                ax_env.tick_params(axis='y', length=0)
                ax_env.grid(True, alpha=0.3, linestyle='--', axis='x')

                # Asse tempo descritto una sola volta, sull'ultima riga della
                # pagina (l'envelope dell'ultimo stream).
                if i == n_streams - 1:
                    ax_env.set_xlabel("Time (s)",
                                      fontsize=self._fs(self.config['label_fontsize']))
                else:
                    ax_env.set_xticklabels([])

                # Legenda envelope (per-lane, allineata alle curve — issue #91)
                # nella colonna sinistra della riga envelope dello stream.
                if legend_entries:
                    ax_legend = fig.add_subplot(gs[grain_row + 1, 0])
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
        """Target risolti (MagnifyTarget) per la pagina.
        Delega a rendering.magnifier_targets.resolve."""
        return magnifier_targets.resolve(
            stream_entries, page_start, page_end,
            auto=self.config.get('magnify_auto'),
            specs=self.config.get('magnify_targets'),
            hist_bins=self.config['magnify_hist_bins'],
            defaults=self.config['magnify_defaults'])

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
        entry = resolved.entry
        ax_grain = entry['ax']
        stream = entry['stream']
        sample_dur = entry['sample_duration']
        cents_range = entry['cents_range']
        tc, yc = float(resolved.t), float(resolved.y)
        zoom = max(float(resolved.zoom), 1e-6)

        W, H = fig.get_size_inches() * fig.dpi
        min_dim = min(W, H)
        out_r_px = float(resolved.out) * min_dim
        src = resolved.src
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
        corner = resolved.corner or \
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

        # Proiezione dell'istante sulle curve dello stream (issue #214).
        self._draw_poc_projection(resolved)

    def _draw_poc_projection(self, resolved):
        """Proietta l'istante della lente sulla corsia envelope del suo stream:
        una verticale tratteggiata a x = t e, su ogni curva che incrocia, un
        marker col valore reale (issue #214).

        Senza, la lente dice DOVE guardare ma non con quali parametri: il
        collegamento fra il grumo di grani ingrandito e i valori che lo
        producono va ricostruito allineando a occhio la X del cerchio sorgente
        con le curve sottostanti.

        Nessun artista se la proiezione e' spenta, se lo stream non ha corsia
        envelope (pagina tutta statica), se la sua corsia e' vuota o se
        l'istante cade fuori dall'estensione dello stream: e' lo stesso
        invariante di retrocompatibilita' del resto della lente.
        """
        cfg = self.config['magnify_projection']
        if not cfg['enabled']:
            return

        entry = resolved.entry
        ax_env = entry.get('ax_env')
        render = entry.get('env_render')
        if ax_env is None or render is None:
            return

        stream = entry['stream']
        points = magnifier_projection.project(
            render, float(resolved.t), stream.onset, stream.duration,
            pan_range=self.config['envelope_ranges']['pan'])
        if not points:
            return

        # Stesso accento della lente (anello sorgente e connettori): la
        # proiezione e' un pezzo della lente, non un elemento a se'. La
        # verticale e' tratteggiata perche' resti distinguibile dalle curve
        # anche in stampa; col preset B&W anche le curve sono tratteggiate, e
        # li' a separarla e' l'orientamento — nessun envelope corre verticale.
        accent = self.config['magnify_color']
        marker_edge, marker_edge_width = self._projection_marker_edge()
        tc = float(resolved.t)
        line = ax_env.axvline(x=tc, color=accent, linestyle=cfg['linestyle'],
                              linewidth=cfg['linewidth'], alpha=cfg['alpha'],
                              zorder=3)
        line.set_gid('poc-projection')

        page_start, page_end = ax_env.get_xlim()
        colors = self.config['envelope_colors']
        # Le etichette cadono tutte sulla stessa verticale: alternare il lato
        # salendo lungo la corsia tiene separate quelle di due curve vicine,
        # che altrimenti si sovrascriverebbero (una corsia affollata ne ha
        # cinque o sei a poche frazioni di corsia l'una dall'altra).
        for order, point in enumerate(sorted(points, key=lambda p: p.y)):
            color = colors.get(self._base_param_name(point.param), '#333333')
            # Faccia del colore della curva (dice a quale valore appartiene),
            # anello della lente (dice da dove viene il marker): quel che
            # separa questo marker dai pallini dei breakpoint e' l'anello,
            # quindi deve staccare dalla faccia. Vedi _projection_marker_edge:
            # col preset B&W la faccia e' nera come ogni curva e l'anello
            # diventa chiaro, invece di essere il nero quasi uguale
            # dell'accento.
            marker, = ax_env.plot(
                [tc], [point.y], 'o', color=color,
                markersize=cfg['markersize'], markeredgecolor=marker_edge,
                markeredgewidth=marker_edge_width, zorder=4)
            marker.set_gid('poc-projection-marker')

            if not cfg['labels']:
                continue
            label = self._envelope_value_label(
                point.param, point.value, pitch_unit=render.pitch_unit)
            annotation = self._annotate_envelope_value(
                ax_env, tc, point.y, label, color, page_start, page_end,
                side='right' if order % 2 == 0 else 'left')
            annotation.set_gid('poc-projection-label')

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


    def _grain_height_mode(self):
        """Che cosa misura l'altezza del grano sull'asse del buffer.

        Config `grain_height`: 'duration' (storico) o 'read_span' (la porzione
        che il grano percorre davvero). Vedi grain_visuals.grain_height."""
        return self.config.get(
            'grain_height', grain_visuals.GRAIN_HEIGHT_DURATION)

    def _read_position_label(self):
        """Etichetta dell'asse del buffer, che dichiara la propria geometria.

        Con l'altezza fedele alla porzione letta la stessa figura racconta
        un'altra cosa: due partiture della stessa composizione, una per modo,
        sarebbero indistinguibili se l'asse non lo dicesse."""
        if self._grain_height_mode() == grain_visuals.GRAIN_HEIGHT_READ_SPAN:
            return "Read position (s)\n(grain height = read span)"
        return "Read position (s)"

    def _grain_arrow_vertices(self, grain, height_mode=None):
        """Vertici della freccia direzionale (forma storica del grano).
        Delega a rendering.grain_visuals.arrow_vertices."""
        return grain_visuals.arrow_vertices(
            grain, height_mode=height_mode or self._grain_height_mode())

    def _grain_window_vertices(self, grain, xs, w, height_mode=None):
        """Vertici della silhouette "testa/bordo": base piatta sul pointer, il
        bordo superiore segue la curva della finestra w.
        Delega a rendering.grain_visuals.window_vertices."""
        return grain_visuals.window_vertices(
            grain, xs, w, height_mode=height_mode or self._grain_height_mode())

    def _window_silhouette(self, name, resolution):
        """Curva finestra normalizzata su [0,1] in ampiezza e dominio.
        Delega a rendering.grain_visuals.window_silhouette, che la memoizza per
        (name, resolution) — la cache vive nel modulo, non nell'istanza, perche'
        la forma di una finestra non dipende da quale visualizer la chiede."""
        return grain_visuals.window_silhouette(name, resolution)

    def _window_name_map(self, stream):
        """Mappa table_num -> nome finestra.
        Delega a rendering.grain_visuals.window_name_map."""
        return grain_visuals.window_name_map(stream)

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
        
        visible_grains = grain_visuals.visible_grains(
            stream, page_start, page_end)

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
        # Letto una volta per chiamata e non per grano: il modo e' una
        # proprieta' della figura, non del singolo grano. Un modo ignoto
        # solleva al primo grano, dentro grain_visuals.grain_height.
        height_mode = self._grain_height_mode()
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
                vertices = self._grain_window_vertices(
                    grain, xs, w, height_mode)
            else:
                vertices = self._grain_arrow_vertices(grain, height_mode)

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
            color=self.config['stream_label_color'],
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
        from pge.parameters.parameter import Parameter

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
        from pge.rendering.envelope_extractor import get_stream_envelopes
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
        from pge.rendering.envelope_extractor import base_param_name
        return base_param_name(key)

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
        return envelope_display.display_ranges(
            envelopes, stream.onset, t_start, t_end,
            pad_ratio=cfg['pad_ratio'], samples=cfg['samples'])

    def _normalize_envelope_value(self, param_name, value):
        """
        Normalizza un valore di envelope a 0-1 sul range di display data-driven
        attivo (issue #114). Nessun clamp ai range fissi tranne per pan.

        Delega a rendering.envelope_display.normalize. I range sono lo
        scratchpad che _draw_envelopes riempie per la corsia in corso: qui
        restano un attributo perche' i sei chiamanti interni non se li passano,
        ma la REGOLA non li legge piu' da self.

        Args:
            param_name: nome del parametro
            value: valore da normalizzare

        Returns:
            float: valore normalizzato (tipicamente 0-1; pan è clippato).
        """
        return envelope_display.normalize(
            param_name, value,
            getattr(self, '_current_display_ranges', None) or {},
            pan_range=self.config['envelope_ranges']['pan'])

    @staticmethod
    def _segment_strategy_name(segment) -> str:
        """Mappa strategy del segmento al nome canonico ('step'/'linear'/'cubic').
        Delega a rendering.envelope_display.segment_strategy_name."""
        return envelope_display.segment_strategy_name(segment)

    @staticmethod
    def _is_per_segment_heterogeneous(envelope) -> bool:
        """
        True se envelope ha segmenti con strategie diverse (es. step+linear).
        Delega a rendering.envelope_display.is_per_segment_heterogeneous.
        """
        return envelope_display.is_per_segment_heterogeneous(envelope)

    def _draw_envelopes(self, ax, stream, y_base, y_height, page_start, page_end):
        """
        Disegna tutti gli envelope dello stream nella sua corsia.
        Annota i breakpoint con i valori reali.

        Returns:
            EnvelopeLaneRender: cosa e' finito nella corsia — le curve
            disegnate, i range di display con cui sono state scalate e la
            geometria della corsia. Il record esce di qui perche' la lente ci
            proietta sopra molto dopo (issue #214), quando lo scratchpad
            `_current_display_ranges` di questa corsia e' gia' stato
            sovrascritto da quello dello stream successivo.
        """
        envelopes = self._get_stream_envelopes(stream)

        # Unità pitch dello stream corrente: serve a _normalize_envelope_value e
        # _annotate_breakpoints per scalare/etichettare la curva 'pitch' (i bounds
        # dipendono dall'unità, non sono statici come gli altri parametri).
        pitch_unit = getattr(stream, 'pitch_unit', None)
        self._current_pitch_unit = pitch_unit
        self._current_display_ranges = {}

        def lane_render(curves=None, ranges=None):
            return magnifier_projection.EnvelopeLaneRender(
                curves=curves or {}, display_ranges=ranges or {},
                y_base=y_base, y_height=y_height, pitch_unit=pitch_unit)

        if not envelopes:
            return lane_render()

        drawn = {}
        colors = self.config['envelope_colors']
        
        # Tempo relativo allo stream
        stream_start = stream.onset
        stream_end = stream.onset + stream.duration
        
        # Calcola i tempi da campionare (visibili nella pagina)
        t_start = max(page_start, stream_start)
        t_end = min(page_end, stream_end)
        
        if t_start >= t_end:
            return lane_render()

        # Auto-zoom: range di display ristretti per i parametri a range ampio.
        self._current_display_ranges = self._compute_display_ranges(
            envelopes, stream, t_start, t_end)

        for param_name, envelope in envelopes.items():
            # Colore (curve per-voce '__vN' usano il colore del base, #90)
            color = colors.get(self._base_param_name(param_name), '#333333')
            # Tratto: senza preset B&W e' ('-', 1.1), cioe' il disegno storico.
            linestyle, linewidth = self._envelope_style(param_name)

            # Envelope per-segmento eterogeneo (issue #68): rendering per-segmento
            if self._is_per_segment_heterogeneous(envelope):
                self._draw_envelope_per_segment(
                    ax, envelope, param_name, color,
                    stream_start, y_base, y_height, t_start, t_end,
                    style=(linestyle, linewidth),
                )
                self._annotate_breakpoints(ax, envelope, param_name, color,
                                           stream_start, y_base, y_height,
                                           page_start, page_end)
                drawn[param_name] = envelope
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
                    ax.plot(times, values, color=color, linewidth=linewidth,
                        linestyle=linestyle,
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
                ax.plot(times, y_values, color=color, linewidth=linewidth,
                    linestyle=linestyle, alpha=0.8, label=param_name)
            
            # === ANNOTAZIONE BREAKPOINT ===
            self._annotate_breakpoints(ax, envelope, param_name, color,
                                    stream_start, y_base, y_height,
                                    page_start, page_end)
            
            drawn[param_name] = envelope

        # Reset: le lane successive ricalcolano i propri display range. I range
        # di QUESTA corsia escono nel record, che e' l'unico modo per ritrovarli
        # quando la lente proietta (dopo il giro su tutti gli stream).
        ranges = self._current_display_ranges
        self._current_display_ranges = {}

        return lane_render(drawn, ranges)

    def _draw_envelope_per_segment(
        self, ax, envelope, param_name, color,
        stream_start, y_base, y_height, t_start, t_end,
        style=None,
    ):
        """
        Disegna envelope eterogeneo segmento per segmento (issue #68).

        Ogni segmento usa drawstyle adattato alla propria strategy:
        - step: drawstyle='steps-post' (gradini netti)
        - linear: linea retta tra estremi
        - cubic: campionamento denso del segmento

        style: la coppia (linestyle, linewidth) della curva (issue #248).
        None = la risolve da se', cosi' chi chiama questo metodo direttamente
        non deve conoscerla.
        """
        linestyle, linewidth = style or self._envelope_style(param_name)
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
                ax.plot([a, b], [y_left, y_left], color=color,
                        linewidth=linewidth, linestyle=linestyle, alpha=0.8)
                # Salto verticale a fine segmento (se b == seg_t1)
                if b >= seg_t1:
                    ax.plot([b, b], [y_left, y_right], color=color,
                            linewidth=linewidth, linestyle=linestyle, alpha=0.8)

            elif strategy_name == 'linear':
                # Usa seg.evaluate() per evitare bug precisione float al boundary
                # tra segmenti (envelope.evaluate cerca per tempo e può cadere
                # nel segmento precedente, restituendo valore sbagliato).
                v_a = seg.evaluate(a - stream_start)
                v_b = seg.evaluate(b - stream_start)
                y_a = y_base + self._normalize_envelope_value(param_name, v_a) * y_height
                y_b = y_base + self._normalize_envelope_value(param_name, v_b) * y_height
                ax.plot([a, b], [y_a, y_b], color=color,
                        linewidth=linewidth, linestyle=linestyle, alpha=0.8)

            else:  # cubic
                import numpy as np
                n = max(20, int(50 * (b - a) / max(seg_t1 - seg_t0, 1e-9)))
                ts = np.linspace(a, b, n)
                ys = []
                for t in ts:
                    v = seg.evaluate(t - stream_start)
                    ys.append(y_base + self._normalize_envelope_value(param_name, v) * y_height)
                ax.plot(ts, ys, color=color,
                        linewidth=linewidth, linestyle=linestyle, alpha=0.8)

    def _annotate_breakpoints(self, ax, envelope, param_name, color,
                               stream_start, y_base, y_height,
                               page_start, page_end):
        """
        Annota i breakpoint dell'envelope con i valori reali.
        """
        for t_rel, value in envelope.breakpoints:
            # Tempo assoluto
            t_abs = stream_start + t_rel

            # Salta breakpoint fuori dalla pagina
            if t_abs < page_start or t_abs > page_end:
                continue

            # Posizione Y normalizzata
            val_norm = self._normalize_envelope_value(param_name, value)
            y_pos = y_base + val_norm * y_height

            label = self._envelope_value_label(
                param_name, value,
                pitch_unit=getattr(self, '_current_pitch_unit', None))

            # Disegna punto
            ax.plot(t_abs, y_pos, 'o', color=color, markersize=4, alpha=0.9)

            self._annotate_envelope_value(ax, t_abs, y_pos, label, color,
                                          page_start, page_end)

    def _envelope_value_label(self, param_name, value, pitch_unit=None):
        """Etichetta col valore reale di un parametro.
        Delega a rendering.envelope_display.value_label."""
        return envelope_display.value_label(param_name, value,
                                            pitch_unit=pitch_unit)

    def _annotate_envelope_value(self, ax, t_abs, y_pos, label, color,
                                 page_start, page_end, side='right'):
        """Scrive un valore accanto al punto in cui e' stato letto.

        Lato dell'etichetta scelto dinamicamente in base alla posizione nel
        subplot, cosi' il testo resta SEMPRE dentro il plot dedicato
        all'envelope (prima un offset fisso in alto-a-destra faceva sforare i
        breakpoint vicini al bordo destro o al tetto della corsia).

        Usata dai breakpoint e dalla proiezione della lente (issue #214): le
        due annotazioni devono stare nel plot con la stessa regola, o la
        seconda sforerebbe dove la prima non sfora.

        `side` e' la preferenza del chiamante ('right' = a destra del punto,
        come i breakpoint): la proiezione la alterna fra i suoi valori, che
        cadono tutti sulla stessa verticale. I bordi hanno comunque l'ultima
        parola — restare dentro il plot viene prima del non sovrapporsi.
        """
        x_span = page_end - page_start
        x_frac = (t_abs - page_start) / x_span if x_span > 0 else 0.5
        # ylim del subplot envelope e' (0, 1): y_pos e' gia' la frazione
        # verticale dentro l'asse.
        y_frac = y_pos

        # Vicino a un bordo il lato lo decide il bordo.
        if x_frac > 0.85:
            side = 'left'
        elif x_frac < 0.15:
            side = 'right'

        if side == 'left':
            dx, ha = -3, 'right'
        else:
            dx, ha = 3, 'left'
        # Vicino al tetto del subplot -> etichetta sotto il punto.
        if y_frac > 0.9:
            dy, va = -3, 'top'
        else:
            dy, va = 3, 'bottom'

        # Disegna etichetta (offset dinamico per restare dentro il plot)
        return ax.annotate(
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
        """Geometria condivisa fra corsie envelope e legenda (issue #91).

        Delega a rendering.page_layout.envelope_lanes. L'estrazione delle curve
        resta qui perche' dipende dai flag di config (show_static_params,
        show_voice_offsets, envelope_filter): la geometria delle corsie non
        deve saperne niente.

        Returns:
            (lanes, legend_entries) — lanes sono EnvelopeLane, legend_entries
            triple (param_name, y, stream_id).
        """
        return page_layout.envelope_lanes(
            [(s, self._get_stream_envelopes(s)) for s in active_streams])

    def _legend_display_name(self, param_name):
        """Nome corto per la legenda.
        Delega a rendering.page_layout.legend_display_name."""
        return page_layout.legend_display_name(param_name)

    def _draw_envelope_legend(self, ax, legend_entries):
        """
        Disegna la legenda degli envelope nel subplot dedicato.

        legend_entries: list[(param_name, y, stream_id)] gia' posizionati
        per-lane da _compute_env_legend_layout (issue #91), allineati alle
        curve nelle corsie.
        """
        ax.axis('off')
        colors = self.config['envelope_colors']

        # Con gli stili in gioco il tratto della chiave e' un CAMPIONE della
        # curva, non un simbolo: stesso pattern e stesso spessore, su tutta la
        # larghezza utile della colonna (il testo comincia a 0.4). Le due cose
        # sono necessarie entrambe. Il tratto storico e' il 5% della colonna,
        # cioe' qualche punto: meno di un ciclo di tratteggio, che ci si
        # leggerebbe pieno. E matplotlib scala il pattern per lo spessore,
        # quindi un tratto ingrossato per farsi vedere allungherebbe anche il
        # ciclo, riportando la chiave a leggersi piena. Lo spessore, poi, e'
        # meta' dell'informazione: e' li' che una probabilita' si distingue
        # dalla sua base.
        #
        # La misura e' la stessa per tutte le voci, comprese quelle a tratto
        # pieno: una colonna con due lunghezze di chiave fa leggere lo stub
        # corto come un altro tratteggio.
        styled = bool(self.config.get('envelope_styles'))

        for param_name, y, stream_id in legend_entries:
            color = colors.get(self._base_param_name(param_name), '#333333')
            linestyle, linewidth = self._envelope_style(param_name)
            if styled:
                x0, x1, key_width = 0.02, 0.38, linewidth
            else:
                x0, x1, key_width = 0.1, 0.15, 2
            ax.plot([x0, x1], [y, y], color=color,
                    linestyle=linestyle, linewidth=key_width)
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


