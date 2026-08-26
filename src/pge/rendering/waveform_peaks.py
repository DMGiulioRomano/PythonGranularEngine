# src/pge/rendering/waveform_peaks.py
"""
Riduzione di un buffer audio a una curva disegnabile (issue #233).

La partitura mette la waveform del sample su una colonna alta pochi
centimetri. I campioni sono centinaia di migliaia, i pixel qualche centinaio:
qualcosa va buttato, e la domanda non e' *quanto* ma *che cosa*.

Il visualizer buttava a caso — `audio[::200]`, un campione ogni duecento — e
questo modulo esiste per smettere. Il passo fisso ha tre difetti, e sono tre
difetti diversi:

**Perde i transienti.** Un attacco largo meno del passo non viene mai pescato.
Su un sample con un picco di 30 campioni a fondo scala, la waveform disegnata
dichiarava un'ampiezza di meta' scala: non era una versione approssimata del
segnale, era un segnale che non esiste.

**Aliasa.** Sottocampionare senza filtrare ripiega le frequenze alte su quelle
basse. Una sinusoide a 220 Hz letta ogni 200 campioni (cioe' a 220.5 Hz)
diventa un'onda lentissima a 0.4 Hz: la forma disegnata non e' una
semplificazione di quella vera, e' un artefatto della griglia di lettura.

**Costa in proporzione al file.** Il numero di vertici che arrivano a
matplotlib e' `len(audio) / passo`: un sample di due minuti ne produceva
ventiseimila, uno di un secondo duecento. Il primo e' lento da disegnare, il
secondo e' illeggibile.

Il rimedio e' l'inviluppo min/max, che e' come disegna la waveform qualunque
editor audio: si legge **ogni** campione, si divide il segnale in bucket, e di
ogni bucket si tiene la coppia (minimo, massimo). Il picco c'e' sempre, perche'
i bucket partizionano il segnale e ogni campione cade in uno. La lettura resta
lineare nei campioni — deve esserlo, e' il prezzo per non perderli — ma cio'
che arriva al disegno e' limitato dal numero di bucket, non dalla durata.

Il modulo e' puro: numpy e basta, niente matplotlib e niente I/O. Il file lo
apre `ScoreVisualizer._load_waveform`, che resta l'adapter (legge la config e
tiene la cache); qui vive solo la regola.
"""
from __future__ import annotations

import numpy as np


# Quante colonne min/max disegnare per default. La colonna della waveform su
# una pagina A4 stampata a 300 dpi e' alta al massimo un paio di migliaia di
# pixel: sotto questa soglia il dettaglio si vedrebbe mancare, sopra si
# pagherebbero vertici per pixel che non ci sono.
DEFAULT_BUCKETS = 2000


def bucket_width(n_samples, buckets, width=None):
    """Quanti campioni entrano in un bucket.

    Due modi di chiedere la risoluzione, e uno vince sull'altro:

    - `buckets` fissa il **numero di colonne**, e la larghezza si deriva dalla
      durata. E' il modo giusto per una pagina: il costo del disegno non
      dipende da quanto e' lungo il sample.
    - `width` fissa la **larghezza in campioni**, ignorando il conteggio. E' la
      semantica storica di `waveform_downsample` ("un punto ogni N campioni"),
      e serve quando due sample di lunghezza diversa vanno confrontati allo
      stesso dettaglio temporale.

    L'arrotondamento e' per eccesso: per difetto l'ultimo bucket resterebbe
    fuori, e l'ultimo bucket e' la coda del sample.

    Sotto il numero di bucket richiesti non c'e' niente da ridurre e la
    larghezza scende a 1: il segnale si disegna intero. E' il caso dei sample
    brevi, che col passo fisso erano i piu' maltrattati.
    """
    if width is not None:
        return max(1, int(width))
    buckets = max(1, int(buckets))
    return max(1, -(-int(n_samples) // buckets))


def peak_envelope(audio, sr, *, buckets=DEFAULT_BUCKETS, width=None):
    """L'inviluppo min/max di `audio`, normalizzato, pronto per il disegno.

    Ritorna `(time_axis, amplitude)`, due array della stessa lunghezza: per
    ogni bucket una coppia di punti che condividono l'istante (il centro del
    bucket) e portano il minimo e il massimo dei campioni che contiene. La
    polilinea che ne esce e' la waveform; riempita fino allo zero e' la colonna
    della partitura.

    L'ampiezza e' normalizzata sul **picco vero del segnale intero**, non su
    quello dei campioni sopravvissuti alla riduzione. Non e' un dettaglio: col
    passo fisso si divideva per il massimo del sottoinsieme pescato, quindi
    cambiare la manopola della risoluzione cambiava anche la scala verticale
    del disegno. Qui la manopola cambia il dettaglio e basta — due partiture
    generate a risoluzioni diverse restano confrontabili.

    Args:
        audio: campioni; mono o multicanale (i canali si mixano a mono).
        sr: sample rate, per convertire gli indici in secondi.
        buckets: numero di colonne min/max da produrre.
        width: larghezza del bucket in campioni; se data, vince su `buckets`.

    Returns:
        (time_axis, amplitude): secondi e ampiezza in [-1, 1]. Vuoti se il
        buffer e' vuoto — un file di lunghezza zero non deve far esplodere il
        disegno.
    """
    audio = np.asarray(audio)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    n = audio.size
    if n == 0:
        return np.zeros(0), np.zeros(0)

    w = bucket_width(n, buckets, width)
    n_buckets = -(-n // w)

    pad = n_buckets * w - n
    if pad:
        # Riempito con l'ultimo campione, che appartiene *gia'* all'ultimo
        # bucket: min e max di quel bucket non si spostano di un capello.
        # Con degli zeri, invece, la coda di un sample che finisce forte
        # guadagnerebbe uno zero che il segnale non ha.
        audio = np.concatenate(
            [audio, np.full(pad, audio[-1], dtype=audio.dtype)])

    blocks = audio.reshape(n_buckets, w)
    mins = blocks.min(axis=1).astype(np.float64)
    maxs = blocks.max(axis=1).astype(np.float64)

    # I bucket partizionano il segnale, quindi il picco globale e' gia' qui:
    # nessuna seconda passata sui campioni (su un sample lungo sarebbero
    # milioni di letture per un numero che abbiamo in mano).
    peak = max(maxs.max(), -mins.min())
    if peak > 0:
        mins /= peak
        maxs /= peak

    # Centro del bucket, calcolato sui bordi reali: l'ultimo bucket puo' essere
    # parziale, e il suo centro deve dirlo. Il vecchio asse era un linspace
    # fino alla durata, che mappava l'ultimo campione *pescato* sulla fine del
    # sample e stirava la waveform — su un sample corto anche di un quarto.
    edges = np.minimum(np.arange(n_buckets + 1) * w, n)
    centers = (edges[:-1] + edges[1:]) / (2.0 * sr)

    amplitude = np.empty(2 * n_buckets, dtype=np.float64)
    amplitude[0::2] = mins
    amplitude[1::2] = maxs
    return np.repeat(centers, 2), amplitude
