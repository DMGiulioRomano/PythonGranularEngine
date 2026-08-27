# tests/rendering/test_waveform_peaks.py
"""
TDD suite per rendering.waveform_peaks (issue #233).

Come si riduce un buffer audio a una curva disegnabile. La partitura mette la
waveform del sample su una colonna alta pochi centimetri: i campioni sono
centinaia di migliaia, i pixel qualche centinaio. Qualcosa va buttato, e la
domanda e' *che cosa*.

Il visualizer buttava a caso: `audio[::200]`, un campione ogni duecento. Tre
conseguenze, tutte verificate qui sotto come regressione:

1. i transienti sparivano — un picco largo meno di un bucket non veniva mai
   pescato, e la waveform disegnata mostrava un'ampiezza che il segnale non ha;
2. la normalizzazione dipendeva dal passo — si divideva per il massimo dei
   campioni *sopravvissuti*, quindi cambiare la manopola cambiava la scala
   verticale del disegno, non solo il suo dettaglio;
3. il numero di vertici cresceva col file — un sample lungo ne produceva
   decine di migliaia, uno corto poche centinaia.

Il rimedio e' l'inviluppo min/max: si legge *ogni* campione, e per ogni bucket
si tiene la coppia (minimo, massimo). Il costo della lettura resta lineare nei
campioni — deve esserlo, e' il prezzo per non perdere i picchi — ma quello che
arriva a matplotlib e' costante.
"""

import numpy as np
import pytest

from pge.rendering.waveform_peaks import (
    DEFAULT_BUCKETS,
    bucket_width,
    peak_envelope,
)


SR = 44100


def tone(seconds=1.0, freq=220.0, amp=0.5, sr=SR):
    t = np.arange(int(sr * seconds)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class TestBucketWidth:
    """Quanti campioni entrano in un bucket."""

    def test_long_signal_is_divided_into_the_requested_buckets(self):
        assert bucket_width(200_000, buckets=2000) == 100

    def test_the_division_rounds_up_so_nothing_falls_outside(self):
        """Con l'arrotondamento per difetto l'ultimo bucket resterebbe fuori:
        e' la coda del sample, ed e' proprio dove sta la fine di una nota."""
        assert bucket_width(2001, buckets=1000) == 3

    def test_signal_shorter_than_the_buckets_is_not_reduced(self):
        """Meno campioni che bucket: non c'e' niente da ridurre, il segnale si
        disegna intero. E' il caso dei sample brevi, che col passo fisso erano
        i piu' maltrattati."""
        assert bucket_width(500, buckets=2000) == 1

    def test_explicit_width_wins_over_the_bucket_count(self):
        """La manopola storica (`waveform_downsample`) fissa la risoluzione in
        campioni invece che in colonne: serve a confrontare due sample di
        lunghezza diversa allo stesso dettaglio."""
        assert bucket_width(200_000, buckets=2000, width=200) == 200

    def test_a_degenerate_request_still_yields_a_usable_width(self):
        """Lo schema di config non verifica i tipi (per scelta): uno zero non
        deve arrivare fino a una divisione per zero. Zero colonne si legge come
        una — l'intero segnale in un bucket solo: degenere ma coerente con cio'
        che la manopola dice, mentre scendere a un campione per bucket darebbe
        il *massimo* dettaglio a chi ne ha chiesto il minimo."""
        assert bucket_width(1000, buckets=0) == 1000
        assert bucket_width(1000, buckets=-5) == 1000
        assert bucket_width(1000, buckets=2000, width=0) == 1


class TestTransientSurvives:
    """Il difetto che apre la issue: un picco piu' stretto di un bucket."""

    def _signal_with_spike(self, sr=SR, seconds=5.0, spike_at=2.5, width=30):
        audio = tone(seconds, sr=sr).astype(np.float64)
        i = int(spike_at * sr)
        audio[i:i + width] = 1.0
        return audio

    def test_subsampling_loses_it(self):
        """La prova del difetto, non del rimedio: il vecchio `audio[::200]` non
        pesca mai un transiente di 30 campioni, e la waveform disegnata
        dichiara un picco di meta' scala su un segnale che arriva a fondo."""
        audio = self._signal_with_spike()
        assert np.max(np.abs(audio[::200])) < 0.9

    def test_the_min_max_envelope_keeps_it(self):
        audio = self._signal_with_spike()
        _, amplitude = peak_envelope(audio, SR, buckets=2000)
        assert np.max(np.abs(amplitude)) == pytest.approx(1.0)

    def test_the_spike_lands_in_its_own_bucket_not_smeared_over_the_curve(self):
        """Non basta che il picco compaia: deve comparire *dove sta*. Il bucket
        che copre l'istante del transiente e' l'unico a toccare fondo scala."""
        audio = self._signal_with_spike(spike_at=2.5)
        time_axis, amplitude = peak_envelope(audio, SR, buckets=2000)
        at_full_scale = time_axis[np.abs(amplitude) > 0.99]
        assert at_full_scale.size > 0
        assert np.all(np.abs(at_full_scale - 2.5) < 5.0 / 2000)


class TestMatplotlibLoadIsBounded:
    """Il secondo motivo del rimedio: quanto lavoro arriva al disegno."""

    @pytest.mark.parametrize('seconds', [1.0, 10.0, 120.0])
    def test_vertex_count_does_not_grow_with_the_file(self, seconds):
        audio = tone(seconds)
        time_axis, amplitude = peak_envelope(audio, SR, buckets=500)
        assert len(amplitude) <= 2 * 500
        assert len(time_axis) == len(amplitude)

    def test_the_old_stride_did_grow_with_it(self):
        """Regressione dichiarata: col passo fisso un sample di due minuti
        produceva 26mila vertici, uno di un secondo 220."""
        assert len(tone(120.0)[::200]) > 100 * len(tone(1.0)[::200])

    def test_a_short_sample_is_drawn_whole(self):
        """L'altra meta': sotto il numero di bucket non si butta niente, e i
        valori disegnati sono quelli del segnale."""
        audio = np.array([0.0, 0.5, -0.5, 1.0], dtype=np.float64)
        _, amplitude = peak_envelope(audio, sr=4, buckets=2000)
        assert len(amplitude) == 2 * len(audio)
        assert amplitude[0::2] == pytest.approx(amplitude[1::2])
        assert amplitude[1::2] == pytest.approx(audio)


class TestNormalization:
    """La scala verticale del disegno."""

    def test_the_curve_touches_full_scale(self):
        _, amplitude = peak_envelope(tone(1.0, amp=0.3), SR)
        assert np.max(np.abs(amplitude)) == pytest.approx(1.0)

    def test_the_scale_does_not_depend_on_the_resolution(self):
        """Il difetto silenzioso del vecchio codice: si normalizzava sul massimo
        dei campioni sopravvissuti al passo, quindi abbassare la manopola per
        avere piu' dettaglio *riscalava anche il disegno*. Chi confrontava due
        partiture generate con due risoluzioni confrontava due scale diverse."""
        audio = tone(2.0, amp=0.4).astype(np.float64)
        audio[10_020:10_040] = 0.9
        peaks = [np.max(np.abs(peak_envelope(audio, SR, buckets=b)[1]))
                 for b in (200, 2000, 20_000)]
        assert peaks == pytest.approx([1.0, 1.0, 1.0])

    def test_the_old_stride_did_depend_on_it(self):
        audio = tone(2.0, amp=0.4).astype(np.float64)
        audio[10_020:10_040] = 0.9
        assert np.max(np.abs(audio[::200])) != pytest.approx(
            np.max(np.abs(audio[::20])))

    def test_silence_stays_silent_instead_of_dividing_by_zero(self):
        time_axis, amplitude = peak_envelope(np.zeros(10_000), SR)
        assert np.all(amplitude == 0.0)
        assert np.all(np.isfinite(time_axis))

    def test_an_all_positive_signal_is_normalized_on_its_own_peak(self):
        """Un segnale senza parte negativa (una curva di inviluppo salvata come
        audio) ha il minimo sopra lo zero: il picco e' il massimo, non il
        maggiore fra i due in valore assoluto letto alla cieca."""
        audio = np.linspace(0.1, 0.8, 5000)
        _, amplitude = peak_envelope(audio, SR, buckets=100)
        assert np.max(amplitude) == pytest.approx(1.0)
        assert np.min(amplitude) > 0.0


class TestTimeAxis:
    """Dove cade, nel tempo del sample, ogni coppia min/max."""

    def test_time_and_amplitude_are_paired(self):
        """I due punti di un bucket condividono l'istante: la coppia disegna il
        segmento verticale che nella partitura e' la colonna della waveform."""
        time_axis, _ = peak_envelope(tone(3.0), SR, buckets=400)
        assert time_axis[0::2] == pytest.approx(time_axis[1::2])

    def test_it_is_non_decreasing(self):
        time_axis, _ = peak_envelope(tone(3.0), SR, buckets=400)
        assert np.all(np.diff(time_axis) >= 0)

    def test_it_covers_the_sample_without_overflowing_it(self):
        """L'asse deve stare dentro la durata vera: e' lo stesso asse su cui
        sono disegnati i grani, e una waveform stirata non ci si allinea."""
        seconds = 3.0
        time_axis, _ = peak_envelope(tone(seconds), SR, buckets=400)
        assert time_axis[0] >= 0.0
        assert time_axis[-1] <= seconds
        assert time_axis[0] < seconds / 400
        assert time_axis[-1] > seconds - seconds / 400

    def test_the_old_axis_overflowed_on_short_samples(self):
        """Regressione: `linspace(0, duration, len(audio[::ds]))` mappava
        l'ultimo campione *pescato* sulla fine del sample. Su un sample corto
        l'ultimo pescato e' lontano dalla fine, e la waveform veniva stirata."""
        n, ds, sr = 500, 200, SR
        drawn = np.linspace(0, n / sr, len(np.zeros(n)[::ds]))
        real_last = ((n - 1) // ds) * ds / sr
        assert drawn[-1] > real_last * 1.2

    def test_min_comes_before_max_in_each_bucket(self):
        _, amplitude = peak_envelope(tone(2.0), SR, buckets=300)
        assert np.all(amplitude[0::2] <= amplitude[1::2])


class TestInputShapes:
    """Che cosa accetta in ingresso."""

    def test_stereo_is_mixed_down_to_mono(self):
        left = tone(1.0, amp=1.0).astype(np.float64)
        stereo = np.stack([left, np.zeros_like(left)], axis=1)
        time_axis, amplitude = peak_envelope(stereo, SR, buckets=200)
        assert len(amplitude) <= 400
        assert time_axis[-1] <= 1.0

    def test_an_empty_buffer_yields_an_empty_curve(self):
        """Un file di lunghezza zero non deve far esplodere il disegno: torna
        una curva vuota, che matplotlib sa disegnare (niente)."""
        time_axis, amplitude = peak_envelope(np.zeros(0), SR)
        assert len(time_axis) == 0
        assert len(amplitude) == 0

    def test_integer_pcm_is_normalized_like_float(self):
        audio = np.array([-32768, 0, 16384, 32767], dtype=np.int16)
        _, amplitude = peak_envelope(audio, sr=4, buckets=2000)
        assert np.max(np.abs(amplitude)) == pytest.approx(1.0)

    def test_every_sample_is_covered_by_some_bucket(self):
        """La proprieta' che rende il rimedio un rimedio: i bucket partizionano
        il segnale, quindi il minimo e il massimo globali ci sono sempre."""
        rng = np.random.default_rng(0)
        audio = rng.normal(size=12_345)
        _, amplitude = peak_envelope(audio, SR, buckets=97)
        peak = np.max(np.abs(audio))
        assert np.max(amplitude) == pytest.approx(np.max(audio) / peak)
        assert np.min(amplitude) == pytest.approx(np.min(audio) / peak)


class TestDefaultBuckets:
    def test_the_default_is_generous_enough_for_print(self):
        """La colonna della waveform su una pagina A4 a 300 dpi e' alta al
        massimo un paio di migliaia di pixel: sotto quella soglia il dettaglio
        si vedrebbe mancare, sopra si pagherebbe per pixel che non ci sono."""
        assert DEFAULT_BUCKETS >= 1000


class TestDegenerateInput:
    """Due modi in cui un buffer reale non e' il buffer del test."""

    def test_a_bucket_wider_than_the_signal_is_the_signal(self):
        """La manopola storica e' una larghezza in campioni, e chi vuole una
        waveform grossolana la alza: niente le impedisce di superare la
        lunghezza del sample. Il bucket va allora tagliato sul segnale, perche'
        e' lui a dettare il padding: senza il taglio si allocano `width`
        campioni di riempimento per un file che ne ha mille, e la memoria
        finisce per dipendere dalla manopola invece che dall'audio."""
        assert bucket_width(1000, buckets=2000, width=10 ** 9) == 1000

    def test_a_single_nan_does_not_unnormalize_the_whole_curve(self):
        """Un NaN nel buffer avvelena min e max del suo bucket, e da li' il
        picco globale: la divisione salta e *tutta* la waveform resta in scala
        assoluta, cioe' schiacciata o fuori dai bordi. Col passo fisso un NaN
        isolato veniva quasi sempre saltato; ora si legge ogni campione, quindi
        il caso va gestito invece che evitato per fortuna."""
        audio = tone(1.0, amp=0.5).astype(np.float64)
        audio[1000] = np.nan
        _, amplitude = peak_envelope(audio, SR, buckets=200)
        assert np.nanmax(np.abs(amplitude)) == pytest.approx(1.0)
