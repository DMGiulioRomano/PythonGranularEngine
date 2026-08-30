# src/pge/rendering/sc_score_writer.py
"""
SuperColliderScoreWriter - Stream -> score NRT (.osc) per scsynth.

E' l'omologo di `ScoreWriter` per il backend SuperCollider: stessi Stream in
ingresso, stesso contenuto semantico in uscita (prima le tabelle, poi un
evento per grano), formato diverso. Dove il `.sco` scrive
`f 2 0 1024 20 2 1` e `i "Grain" 0.5 0.05 ...`, qui si scrivono
`/b_alloc` + `/b_setn` e `/s_new`.

Struttura dello score prodotto:

    t = 0.0    /d_recv <synthdef>              la SynthDef, inline nello score
               /b_allocReadChannel ...          un buffer mono per sample
               /b_alloc + /b_setn ...           un buffer per finestra
    t = onset  /s_new pgeGrain ...              un nodo per grano
    t = fine   /c_set 0 0                       marcatore di durata del render

Tre decisioni che vale la pena isolare qui invece che nella SynthDef:

1. **La finestra e' una tabella, non un UGen di inviluppo.** I campioni
   vengono da `NumpyWindowRegistry`, la stessa che usa il renderer NumPy: la
   parita' delle finestre e' per costruzione, non per reimplementazione. La
   tabella e' ad alta risoluzione e la SynthDef la percorre da 0 a N-1
   nell'arco del grano, che e' esattamente la parametrizzazione dei
   `linspace` con cui la registry genera ogni finestra del catalogo.

2. **Sotto `WINDOW_MIN_SHAPE_SAMPLES` la finestra non si applica** (issue
   #225). Il renderer NumPy lo decide dentro `get()`, perche' genera la
   finestra alla lunghezza del grano; qui la tabella e' a lunghezza fissa e
   la lunghezza del grano la conosce solo lo score, che punta il grano al
   buffer piatto.

3. **La conversione delle unita' avviene qui**, dove c'e' Python: dB ->
   ampiezza lineare e gradi -> radianti sono le stesse due righe di
   `GrainRenderer`, non due UGen in piu' nel grafo.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

from pge.rendering import osc
from pge.rendering.numpy_window_registry import WINDOW_MIN_SHAPE_SAMPLES
from pge.shared.constants import DEFAULT_OUTPUT_SR


# Nome della SynthDef definita in supercollider/pge_grain.scd. Lo score lo
# cita per nome in ogni /s_new: se cambia li', cambia qui.
SYNTH_NAME = 'pgeGrain'

# Risoluzione delle tabelle di finestra. Sopra i 4096 punti l'errore di
# interpolazione della lettura e' sotto il rumore di quantizzazione a 24 bit
# per ogni finestra del catalogo; sotto comincia a vedersi sui grani lunghi.
DEFAULT_WINDOW_TABLE_SIZE = 4096

# Valori per messaggio di /b_setn. Un pacchetto OSC troppo grosso non e'
# vietato dal formato ma lo e' dal buffer di ricezione di scsynth: 256 float
# fanno ~1 KB, con margine abbondante.
DEFAULT_SETN_CHUNK = 256

# Primo id di nodo. Sotto i 1000 stanno i nodi di servizio per convenzione
# SuperCollider (il RootNode e' 0), e sclang alloca da 1000 in su.
NODE_ID_START = 1000


class SuperColliderScoreWriter:
    """
    Costruisce lo score NRT per scsynth a partire dagli Stream.

    Args:
        table_map: {numero: ('sample'|'window', nome)} dal FtableManager. I
            numeri di tabella diventano numeri di buffer: lo score .osc e il
            .sco Csound si leggono uno accanto all'altro.
        window_registry: NumpyWindowRegistry, la stessa del renderer NumPy.
        synthdef_bytes: contenuto del file .scsyndef compilato, spedito
            inline con /d_recv. Inline e non /d_load: lo score resta un
            artefatto autosufficiente e non dipende da un path risolto
            dentro il server.
        samples_dir: directory dei sample; i path finiscono assoluti nello
            score perche' scsynth non condivide la working directory.
        output_sr: sample rate di render, usato per la soglia della finestra.
        window_table_size: risoluzione delle tabelle di finestra.
        setn_chunk: valori per messaggio di /b_setn.
        synth_name: nome della SynthDef.
    """

    def __init__(
        self,
        table_map: Dict[int, Tuple[str, str]],
        window_registry,
        synthdef_bytes: bytes,
        *,
        samples_dir: str = './refs/',
        output_sr: int = DEFAULT_OUTPUT_SR,
        window_table_size: int = DEFAULT_WINDOW_TABLE_SIZE,
        setn_chunk: int = DEFAULT_SETN_CHUNK,
        synth_name: str = SYNTH_NAME,
    ):
        self.table_map = dict(table_map)
        self.window_registry = window_registry
        self.synthdef_bytes = synthdef_bytes
        self.samples_dir = samples_dir
        self.output_sr = output_sr
        self.window_table_size = window_table_size
        self.setn_chunk = setn_chunk
        self.synth_name = synth_name

        # Il buffer piatto non sta nella table_map (non e' una finestra
        # dichiarata dallo YAML): prende il primo numero libero.
        self.flat_buffer_num = max(self.table_map, default=0) + 1

    # =========================================================================
    # API PUBBLICA
    # =========================================================================

    def write_score(
        self,
        filepath: str,
        streams: Sequence,
        per_stream: bool = False,
    ) -> str:
        """Scrive il file .osc. Ritorna il path scritto."""
        return osc.write_nrt_score(
            filepath, self.build_bundles(streams, per_stream=per_stream))

    def build_bundles(
        self,
        streams: Sequence,
        per_stream: bool = False,
    ) -> List[bytes]:
        """Costruisce i bundle dello score, in ordine di tempo.

        Args:
            streams: Stream con voices e grains gia' generati.
            per_stream: se True gli onset sono relativi allo stream (STEMS),
                altrimenti assoluti (MIX). Stessa semantica di ScoreWriter.

        Raises:
            ValueError: se un grano cade prima dello zero dello score.
        """
        bundles = [osc.bundle(0.0, self._setup_messages())]

        # Un bundle per istante: i grani simultanei (voci diverse, o la stessa
        # voce con onset coincidenti) condividono il timetag.
        events: Dict[float, List[bytes]] = {}
        node_id = NODE_ID_START
        for stream, grain in self._ordered_grains(streams, per_stream):
            onset = self._score_time(grain.onset, stream, per_stream)
            if onset < 0:
                raise ValueError(
                    f"Stream '{getattr(stream, 'stream_id', '?')}': grano con "
                    f"onset {onset:.6f}s, prima dell'inizio dello score. In "
                    f"NRT il tempo non puo' essere negativo."
                )
            events.setdefault(onset, []).append(
                self._grain_message(grain, node_id))
            node_id += 1

        for onset in sorted(events):
            bundles.append(osc.bundle(onset, events[onset]))

        # Marcatore finale: scsynth smette al timetag dell'ultimo bundle,
        # quindi senza questo la coda dell'ultimo grano non viene scritta.
        # /c_set su un bus di controllo inutilizzato e' l'idioma della classe
        # Score di SuperCollider: un messaggio senza effetti udibili.
        end = self._score_end(streams, per_stream)
        bundles.append(osc.bundle(end, [osc.message('/c_set', 0, 0)]))
        return bundles

    # =========================================================================
    # INTERNAL - setup
    # =========================================================================

    def _setup_messages(self) -> List[bytes]:
        """SynthDef + buffer, tutto nel bundle a tempo zero.

        In NRT i comandi asincroni di un bundle si completano in ordine prima
        che il bundle successivo venga eseguito: un solo bundle basta e non
        c'e' nessuna race da sincronizzare.
        """
        messages = [osc.message('/d_recv', self.synthdef_bytes)]

        for num, (ftype, name) in sorted(self.table_map.items()):
            if ftype == 'sample':
                messages.append(self._sample_message(num, name))
            elif ftype == 'window':
                messages.extend(self._window_messages(
                    num, self.window_registry.get(name, self.window_table_size)))

        # Buffer piatto per i grani sotto la soglia della finestra.
        messages.extend(self._window_messages(
            self.flat_buffer_num, [1.0] * self.window_table_size))
        return messages

    def _sample_message(self, bufnum: int, filename: str) -> bytes:
        """Carica un sample come buffer MONO.

        /b_allocReadChannel e non /b_allocRead: un file stereo darebbe un
        buffer a due canali, e `BufRd.ar(1, ...)` lo leggerebbe interlacciato.
        Il canale scelto e' il primo, come fa la GEN01 del backend Csound
        (`f N 0 0 1 "file" 0 0 1`). Il renderer NumPy invece media i canali:
        e' una divergenza che precede questo backend, non una che introduce.
        """
        path = os.path.abspath(os.path.join(self.samples_dir, filename))
        # Il ramo numpy verifica i sample caricandoli col SampleRegistry, e
        # csound esce non-zero su una GEN01 che non trova il file. Qui il
        # path finirebbe nello score senza mai toccare il filesystem, e
        # scsynth su /b_allocReadChannel fallito stampa e prosegue: un nome
        # sbagliato darebbe un file di puro silenzio, exit 0. Non serve
        # caricare i campioni per verificarli.
        if not os.path.exists(path):
            from pge.shared.exceptions import SampleNotFoundError
            raise SampleNotFoundError(filename=filename,
                                      search_path=self.samples_dir)
        return osc.message('/b_allocReadChannel', bufnum, path, 0, 0, 0)

    def _window_messages(self, bufnum: int, values: Sequence[float]) -> List[bytes]:
        """/b_alloc + /b_setn a blocchi per riempire una tabella."""
        messages = [osc.message('/b_alloc', bufnum, len(values), 1)]
        for start in range(0, len(values), self.setn_chunk):
            chunk = values[start:start + self.setn_chunk]
            messages.append(osc.message(
                '/b_setn', bufnum, start, len(chunk),
                *(float(v) for v in chunk)))
        return messages

    # =========================================================================
    # INTERNAL - grani
    # =========================================================================

    @staticmethod
    def _score_time(t: float, stream, per_stream: bool) -> float:
        """Istante assoluto -> istante dello score.

        L'unica regola di offset del writer: in STEMS lo stream parte da zero
        nel proprio file, in MIX i tempi restano assoluti. Era scritta in tre
        punti (ordinamento, bundle dei grani, fine dello score) e in due
        grafie diverse; la prossima modalita' di onset -- per-voice, gia'
        prevista in architecture.md -- si corregge qui.
        """
        return t - (stream.onset if per_stream else 0.0)

    @staticmethod
    def _ordered_grains(streams: Sequence, per_stream: bool):
        """Coppie (stream, grain) in ordine di onset di score.

        L'ordine di generazione e' stream-major/voice-major, e le voci sono
        liste parallele: la voce 1 puo' cominciare prima che la voce 0 sia
        finita. Uno score NRT invece deve essere monotono nel tempo.
        `sorted` e' stabile, quindi a parita' di onset l'ordine resta quello
        di generazione e gli id di nodo sono deterministici.
        """
        pairs = [
            (stream, grain)
            for stream in streams
            for voice in stream.voices
            for grain in voice
        ]
        return sorted(
            pairs,
            key=lambda pair: SuperColliderScoreWriter._score_time(
                pair[1].onset, pair[0], per_stream))

    def _grain_message(self, grain, node_id: int) -> bytes:
        """Un /s_new per grano.

        addAction 0 (in testa) su target 0 (RootNode): in NRT non gira
        sclang, quindi il gruppo di default 1 non esiste e il RootNode e'
        l'unico target garantito. L'ordine di esecuzione fra i nodi non conta:
        ogni grano somma sullo stesso bus e basta.
        """
        return osc.message(
            '/s_new', self.synth_name, node_id, 0, 0,
            'buf', int(grain.sample_table),
            'envBuf', self._envelope_buffer(grain),
            'dur', float(grain.duration),
            'startSec', float(grain.pointer_pos),
            'rate', float(grain.pitch_ratio),
            # dB -> lineare, come ampdb() in main.orc e 10**(v/20) in
            # GrainRenderer.
            'amp', float(10.0 ** (grain.volume / 20.0)),
            # gradi -> radianti, come irad in main.orc.
            'panRad', float(grain.pan * 3.141592653589793 / 180.0),
        )

    def _envelope_buffer(self, grain) -> int:
        """Buffer di finestra per il grano, o quello piatto sotto soglia.

        Stessa aritmetica del renderer NumPy: `round(dur * sr)` campioni, e
        sotto `WINDOW_MIN_SHAPE_SAMPLES` la finestra decima il grano invece
        di smussarlo (issue #225).
        """
        n_out = max(1, round(grain.duration * self.output_sr))
        if n_out < WINDOW_MIN_SHAPE_SAMPLES:
            return self.flat_buffer_num
        return int(grain.envelope_table)

    # =========================================================================
    # INTERNAL - estensione
    # =========================================================================

    def _score_end(self, streams: Sequence, per_stream: bool) -> float:
        """Istante finale dello score.

        Stessa regola di `NumpyAudioRenderer._relative_n_total` e del ramo
        MIX: il massimo fra la durata dichiarata degli stream e la fine
        dell'ultimo grano. Il renderer non ha opinioni sui bounds, si adatta
        al contenuto.
        """
        ends = [self._score_time(stream.onset + stream.duration,
                                 stream, per_stream)
                for stream in streams]
        ends.extend(
            self._score_time(grain.onset + grain.duration, stream, per_stream)
            for stream in streams
            for voice in stream.voices
            for grain in voice
        )
        return max(ends) if ends else 0.0
