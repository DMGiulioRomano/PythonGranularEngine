# tests/rendering/test_sc_score_writer.py
"""
Suite TDD per SuperColliderScoreWriter (issue #228).

E' l'omologo di `ScoreWriter` per il backend SuperCollider: prende gli
stessi Stream e produce lo score che scsynth legge in NRT. Il contenuto
semantico e' lo stesso del `.sco` Csound -- tabelle prima, un evento per
grano poi -- in un formato diverso.

Cio' che questi test difendono e' la PARITA' con il renderer NumPy, che e'
il riferimento numerico del progetto: stessa lista di grani in ingresso,
stesse decisioni (soglia della finestra, onset relativi vs assoluti,
estensione del buffer) prima che il segnale esista.

Copertura:
1. TestSetupBundle         - SynthDef, buffer dei sample, buffer delle finestre
2. TestWindowBuffers       - i campioni vengono dalla registry NumPy, non da una copia
3. TestSetnChunking        - /b_setn spezzato: un pacchetto OSC non e' illimitato
4. TestGrainEvents         - un /s_new per grano, con gli argomenti giusti
5. TestWindowThreshold     - sotto WINDOW_MIN_SHAPE_SAMPLES la finestra non si applica
6. TestOnsetModes          - onset relativi (stems) vs assoluti (mix)
7. TestScoreEnd            - l'ultimo bundle dichiara la durata del render
8. TestWriteScore          - il file su disco e' rileggibile
"""

import struct

import numpy as np
import pytest

from pge.core.grain import Grain
from pge.rendering.numpy_window_registry import (
    NumpyWindowRegistry,
    WINDOW_MIN_SHAPE_SAMPLES,
)
from pge.rendering.sc_score_writer import SuperColliderScoreWriter

from tests.rendering.test_osc import decode_bundle, decode_nrt


# =============================================================================
# HELPERS
# =============================================================================

class FakeStream:
    """Stream minimale: il writer usa solo id, onset, duration, voices."""

    def __init__(self, stream_id, onset, duration, voices):
        self.stream_id = stream_id
        self.onset = onset
        self.duration = duration
        self.voices = voices


def grain(onset, duration=0.05, pointer_pos=0.0, pitch_ratio=1.0,
          volume=0.0, pan=45.0, sample_table=1, envelope_table=2):
    return Grain(
        onset=onset, duration=duration, pointer_pos=pointer_pos,
        pitch_ratio=pitch_ratio, volume=volume, pan=pan,
        sample_table=sample_table, envelope_table=envelope_table,
    )


TABLE_MAP = {1: ('sample', 'pino.wav'), 2: ('window', 'hanning')}


@pytest.fixture(autouse=True)
def sample_file(tmp_path):
    """Il sample di TABLE_MAP, su disco: il writer verifica che i sample
    esistano prima di metterne il path nello score."""
    path = tmp_path / "pino.wav"
    path.write_bytes(b'RIFF')
    return path


@pytest.fixture
def writer(tmp_path):
    return SuperColliderScoreWriter(
        table_map=TABLE_MAP,
        window_registry=NumpyWindowRegistry(),
        synthdef_bytes=b'SCgf-FAKE',
        samples_dir=str(tmp_path),
        output_sr=48000,
    )


def decoded_bundles(writer, streams, per_stream=False):
    """Bundle costruiti dal writer, gia' decodificati in (tempo, messaggi)."""
    return [decode_bundle(b)
            for b in writer.build_bundles(streams, per_stream=per_stream)]


def messages_named(bundles, address):
    """Tutti i messaggi con quell'address, appiattiti, col loro tempo."""
    return [(time, args)
            for time, elements in bundles
            for addr, args in elements
            if addr == address]


# =============================================================================
# 1. BUNDLE DI SETUP
# =============================================================================

class TestSetupBundle:
    """Tutto cio' che deve esistere prima del primo grano sta nel bundle a
    tempo 0: la SynthDef e i buffer. In NRT i comandi asincroni di un bundle
    si completano in ordine prima del bundle successivo, quindi un unico
    bundle e' sufficiente e non c'e' race da gestire."""

    def test_primo_bundle_e_a_tempo_zero(self, writer):
        bundles = decoded_bundles(writer, [FakeStream('s1', 0.0, 1.0, [[]])])
        assert bundles[0][0] == pytest.approx(0.0)

    def test_synthdef_arriva_come_blob(self, writer):
        bundles = decoded_bundles(writer, [FakeStream('s1', 0.0, 1.0, [[]])])
        recv = messages_named(bundles, '/d_recv')
        assert len(recv) == 1
        assert recv[0][1][0] == b'SCgf-FAKE'

    def test_synthdef_precede_i_grani(self, writer):
        """Un /s_new su una SynthDef non ancora ricevuta e' un nodo che non
        nasce: l'ordine qui non e' estetico."""
        stream = FakeStream('s1', 0.0, 1.0, [[grain(0.0)]])
        bundles = writer.build_bundles([stream])
        assert b'/d_recv' in bundles[0]
        assert b'/s_new' not in bundles[0]

    def test_sample_caricato_su_un_canale_solo(self, writer, tmp_path):
        """BufRd.ar(1, ...) legge un buffer mono. Con /b_allocRead un file
        stereo darebbe un buffer a due canali e la lettura sarebbe
        interlacciata, cioe' sbagliata."""
        bundles = decoded_bundles(writer, [FakeStream('s1', 0.0, 1.0, [[]])])
        alloc = messages_named(bundles, '/b_allocReadChannel')
        assert len(alloc) == 1
        _, args = alloc[0]
        assert args[0] == 1                       # bufnum = numero di tabella
        assert args[1].endswith('pino.wav')
        assert args[1] == str(tmp_path / 'pino.wav')
        assert args[2:5] == [0, 0, 0]             # da frame 0, tutto, canale 0

    def test_percorso_del_sample_e_assoluto(self, tmp_path):
        """scsynth non condivide la working directory del renderer."""
        writer = SuperColliderScoreWriter(
            table_map=TABLE_MAP,
            window_registry=NumpyWindowRegistry(),
            synthdef_bytes=b'X',
            samples_dir='refs',
        )
        bundles = decoded_bundles(writer, [FakeStream('s1', 0.0, 1.0, [[]])])
        path = messages_named(bundles, '/b_allocReadChannel')[0][1][1]
        assert path.startswith('/')

    def test_una_alloc_per_finestra(self, writer):
        bundles = decoded_bundles(writer, [FakeStream('s1', 0.0, 1.0, [[]])])
        allocs = messages_named(bundles, '/b_alloc')
        # hanning (tabella 2) + il buffer piatto per i grani sotto soglia
        assert len(allocs) == 2
        for _, args in allocs:
            assert args[1] == writer.window_table_size
            assert args[2] == 1                    # un canale

    def test_buffer_piatto_ha_un_numero_libero(self, writer):
        """Il buffer piatto non e' nella table_map: deve prendere un numero
        che nessuna tabella usa gia'."""
        assert writer.flat_buffer_num not in TABLE_MAP


# =============================================================================
# 2. CONTENUTO DEI BUFFER DI FINESTRA
# =============================================================================

class TestWindowBuffers:
    """I campioni della finestra vengono dalla stessa NumpyWindowRegistry che
    usa il renderer NumPy. La parita' e' per costruzione, non per
    reimplementazione: e' l'unico modo per non avere due cataloghi che
    divergono in silenzio."""

    def _setn_values(self, writer, bufnum):
        bundles = decoded_bundles(writer, [FakeStream('s1', 0.0, 1.0, [[]])])
        values = []
        for _, args in messages_named(bundles, '/b_setn'):
            if args[0] != bufnum:
                continue
            assert args[2] == len(args[3:]), "count e valori non concordano"
            values.extend(args[3:])
        return values

    def test_valori_identici_alla_registry_numpy(self, writer):
        expected = NumpyWindowRegistry().get('hanning', writer.window_table_size)
        got = self._setn_values(writer, 2)
        assert len(got) == writer.window_table_size
        assert np.allclose(got, expected, atol=1e-6)

    def test_buffer_piatto_e_tutto_uno(self, writer):
        got = self._setn_values(writer, writer.flat_buffer_num)
        assert len(got) == writer.window_table_size
        assert np.allclose(got, 1.0)

    def test_alias_risolto_dalla_registry(self, tmp_path):
        """'triangle' e' alias di 'bartlett': il writer non tiene un secondo
        elenco di nomi validi."""
        (tmp_path / "p.wav").write_bytes(b'RIFF')
        writer = SuperColliderScoreWriter(
            table_map={1: ('sample', 'p.wav'), 5: ('window', 'triangle')},
            window_registry=NumpyWindowRegistry(),
            synthdef_bytes=b'X',
            samples_dir=str(tmp_path),
        )
        expected = NumpyWindowRegistry().get('bartlett', writer.window_table_size)
        got = self._setn_values(writer, 5)
        assert np.allclose(got, expected, atol=1e-6)


# =============================================================================
# 3. CHUNKING DI /b_setn
# =============================================================================

class TestSetnChunking:

    def test_nessun_messaggio_supera_il_chunk(self, writer):
        bundles = decoded_bundles(writer, [FakeStream('s1', 0.0, 1.0, [[]])])
        for _, args in messages_named(bundles, '/b_setn'):
            assert args[2] <= writer.setn_chunk

    def test_gli_offset_coprono_la_tabella_senza_buchi(self, writer):
        bundles = decoded_bundles(writer, [FakeStream('s1', 0.0, 1.0, [[]])])
        offsets = [args[1] for _, args in messages_named(bundles, '/b_setn')
                   if args[0] == 2]
        counts = [args[2] for _, args in messages_named(bundles, '/b_setn')
                  if args[0] == 2]
        cursor = 0
        for offset, count in zip(offsets, counts):
            assert offset == cursor
            cursor += count
        assert cursor == writer.window_table_size

    def test_ultimo_chunk_puo_essere_corto(self, tmp_path):
        writer = SuperColliderScoreWriter(
            table_map=TABLE_MAP,
            window_registry=NumpyWindowRegistry(),
            synthdef_bytes=b'X',
            samples_dir=str(tmp_path),
            window_table_size=100,
            setn_chunk=30,
        )
        bundles = decoded_bundles(writer, [FakeStream('s1', 0.0, 1.0, [[]])])
        counts = [args[2] for _, args in messages_named(bundles, '/b_setn')
                  if args[0] == 2]
        assert counts == [30, 30, 30, 10]


# =============================================================================
# 4. EVENTI GRANO
# =============================================================================

class TestGrainEvents:

    def test_un_s_new_per_grano(self, writer):
        stream = FakeStream('s1', 0.0, 1.0, [
            [grain(0.0), grain(0.1)],
            [grain(0.2)],
        ])
        assert len(messages_named(decoded_bundles(writer, [stream]), '/s_new')) == 3

    def test_tempo_del_bundle_e_l_onset_del_grano(self, writer):
        stream = FakeStream('s1', 0.0, 2.0, [[grain(0.25), grain(1.5)]])
        times = [t for t, _ in
                 messages_named(decoded_bundles(writer, [stream]), '/s_new')]
        assert times == [pytest.approx(0.25), pytest.approx(1.5)]

    def test_argomenti_del_grano(self, writer):
        g = grain(0.5, duration=0.04, pointer_pos=1.25, pitch_ratio=-2.0,
                  volume=-6.0, pan=30.0)
        stream = FakeStream('s1', 0.0, 2.0, [[g]])
        _, args = messages_named(decoded_bundles(writer, [stream]), '/s_new')[0]

        assert args[0] == writer.synth_name
        assert args[2] == 0 and args[3] == 0      # addAction=head, target=root
        controls = dict(zip(args[4::2], args[5::2]))
        assert controls['buf'] == 1
        assert controls['envBuf'] == 2
        assert controls['dur'] == pytest.approx(0.04)
        assert controls['startSec'] == pytest.approx(1.25)
        assert controls['rate'] == pytest.approx(-2.0)
        # volume in dB -> ampiezza lineare, come 10**(dB/20) del NumPy
        assert controls['amp'] == pytest.approx(10.0 ** (-6.0 / 20.0), rel=1e-6)
        # pan in gradi -> radianti, come irad in main.orc
        assert controls['panRad'] == pytest.approx(np.pi / 6, rel=1e-6)

    def test_node_id_unico_e_crescente(self, writer):
        stream = FakeStream('s1', 0.0, 1.0, [[grain(0.0), grain(0.1), grain(0.2)]])
        ids = [args[1] for _, args in
               messages_named(decoded_bundles(writer, [stream]), '/s_new')]
        assert ids == sorted(ids)
        assert len(set(ids)) == 3
        assert min(ids) >= 1000

    def test_node_id_riparte_a_ogni_score(self, writer):
        """Ogni score e' una sessione scsynth a se': gli id non devono
        crescere fra un render e l'altro (con molti stem sarebbe una perdita
        lenta, e rende gli score non confrontabili)."""
        stream = FakeStream('s1', 0.0, 1.0, [[grain(0.0)]])
        first = messages_named(decoded_bundles(writer, [stream]), '/s_new')
        second = messages_named(decoded_bundles(writer, [stream]), '/s_new')
        assert first[0][1][1] == second[0][1][1]

    def test_grani_ordinati_per_tempo_anche_fra_voci(self, writer):
        """Le voci sono liste parallele: la voce 1 puo' cominciare prima che
        la voce 0 sia finita. Uno score NRT deve essere monotono nel tempo."""
        stream = FakeStream('s1', 0.0, 1.0, [
            [grain(0.0), grain(0.8)],
            [grain(0.4)],
        ])
        bundles = decoded_bundles(writer, [stream])
        times = [t for t, _ in bundles]
        assert times == sorted(times)

    def test_grani_simultanei_stanno_nello_stesso_bundle(self, writer):
        stream = FakeStream('s1', 0.0, 1.0, [[grain(0.5)], [grain(0.5)]])
        bundles = decoded_bundles(writer, [stream])
        a_mezzo = [b for b in bundles if b[0] == pytest.approx(0.5)]
        assert len(a_mezzo) == 1
        assert len(a_mezzo[0][1]) == 2


# =============================================================================
# 5. SOGLIA DELLA FINESTRA
# =============================================================================

class TestWindowThreshold:
    """Sotto WINDOW_MIN_SHAPE_SAMPLES la finestra non ha una forma da
    rappresentare: decima il grano invece di smussarlo (issue #225). Il
    renderer NumPy lo sa perche' genera la finestra alla lunghezza del grano;
    qui la tabella e' a lunghezza fissa, quindi la decisione la prende lo
    score, puntando il grano al buffer piatto."""

    def test_grano_corto_usa_il_buffer_piatto(self, writer):
        corto = (WINDOW_MIN_SHAPE_SAMPLES - 1) / 48000.0
        stream = FakeStream('s1', 0.0, 1.0, [[grain(0.0, duration=corto)]])
        _, args = messages_named(decoded_bundles(writer, [stream]), '/s_new')[0]
        controls = dict(zip(args[4::2], args[5::2]))
        assert controls['envBuf'] == writer.flat_buffer_num

    def test_grano_alla_soglia_usa_la_finestra(self, writer):
        alla_soglia = WINDOW_MIN_SHAPE_SAMPLES / 48000.0
        stream = FakeStream('s1', 0.0, 1.0, [[grain(0.0, duration=alla_soglia)]])
        _, args = messages_named(decoded_bundles(writer, [stream]), '/s_new')[0]
        controls = dict(zip(args[4::2], args[5::2]))
        assert controls['envBuf'] == 2

    def test_la_soglia_segue_il_sample_rate_di_render(self, tmp_path):
        """La soglia e' in campioni, non in secondi: la stessa durata puo'
        stare sopra a 96 kHz e sotto a 48 kHz."""
        durata = (WINDOW_MIN_SHAPE_SAMPLES - 1) / 48000.0
        alto = SuperColliderScoreWriter(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            synthdef_bytes=b'X', samples_dir=str(tmp_path), output_sr=96000,
        )
        stream = FakeStream('s1', 0.0, 1.0, [[grain(0.0, duration=durata)]])
        _, args = messages_named(decoded_bundles(alto, [stream]), '/s_new')[0]
        controls = dict(zip(args[4::2], args[5::2]))
        assert controls['envBuf'] == 2


# =============================================================================
# 6. ONSET RELATIVI E ASSOLUTI
# =============================================================================

class TestOnsetModes:

    def test_mix_usa_onset_assoluti(self, writer):
        stream = FakeStream('s1', 5.0, 2.0, [[grain(5.5)]])
        times = [t for t, _ in
                 messages_named(decoded_bundles(writer, [stream]), '/s_new')]
        assert times == [pytest.approx(5.5)]

    def test_stems_sottrae_l_onset_dello_stream(self, writer):
        stream = FakeStream('s1', 5.0, 2.0, [[grain(5.5)]])
        times = [t for t, _ in
                 messages_named(decoded_bundles(writer, [stream], per_stream=True),
                                '/s_new')]
        assert times == [pytest.approx(0.5)]

    def test_mix_di_piu_stream(self, writer):
        s1 = FakeStream('s1', 0.0, 1.0, [[grain(0.5)]])
        s2 = FakeStream('s2', 10.0, 1.0, [[grain(10.5)]])
        times = [t for t, _ in
                 messages_named(decoded_bundles(writer, [s1, s2]), '/s_new')]
        assert times == [pytest.approx(0.5), pytest.approx(10.5)]

    def test_onset_negativo_dopo_lo_sfasamento_e_un_errore_leggibile(self, writer):
        """Un grano che in STEMS cade prima dello zero non e' scrivibile in
        uno score NRT. Il NumPy lo taglia (CLAMP 1); qui deve almeno dirlo,
        non produrre un timetag che va in wrap alla fine del render."""
        stream = FakeStream('s1', 5.0, 2.0, [[grain(4.9)]])
        with pytest.raises(ValueError):
            writer.build_bundles([stream], per_stream=True)


# =============================================================================
# 7. FINE DELLO SCORE
# =============================================================================

class TestScoreEnd:
    """scsynth in NRT smette al timetag dell'ultimo bundle: senza un evento
    finale la coda dell'ultimo grano viene tagliata."""

    def test_ultimo_bundle_oltre_l_ultimo_grano(self, writer):
        stream = FakeStream('s1', 0.0, 1.0, [[grain(0.9, duration=0.2)]])
        bundles = decoded_bundles(writer, [stream])
        assert bundles[-1][0] == pytest.approx(1.1)

    def test_la_durata_dello_stream_e_un_minimo(self, writer):
        """Come in NumPy (_relative_n_total): l'estensione e' il massimo fra
        la durata dichiarata e la fine dell'ultimo grano."""
        stream = FakeStream('s1', 0.0, 3.0, [[grain(0.0, duration=0.1)]])
        bundles = decoded_bundles(writer, [stream])
        assert bundles[-1][0] == pytest.approx(3.0)

    def test_mix_prende_l_estensione_di_tutti(self, writer):
        s1 = FakeStream('s1', 0.0, 1.0, [[grain(0.0)]])
        s2 = FakeStream('s2', 10.0, 2.0, [[grain(10.0)]])
        bundles = decoded_bundles(writer, [s1, s2])
        assert bundles[-1][0] == pytest.approx(12.0)

    def test_stream_senza_grani_ha_comunque_una_durata(self, writer):
        stream = FakeStream('s1', 0.0, 4.0, [[]])
        bundles = decoded_bundles(writer, [stream])
        assert bundles[-1][0] == pytest.approx(4.0)
        assert len(bundles) >= 2


# =============================================================================
# 8. SCRITTURA SU FILE
# =============================================================================

class TestWriteScore:

    def test_file_rileggibile(self, writer, tmp_path):
        stream = FakeStream('s1', 0.0, 1.0, [[grain(0.5)]])
        path = tmp_path / "score.osc"
        writer.write_score(str(path), [stream])

        bundles = decode_nrt(path.read_bytes())
        addresses = [addr for _, elements in bundles for addr, _ in elements]
        assert '/d_recv' in addresses
        assert '/s_new' in addresses

    def test_ritorna_il_path(self, writer, tmp_path):
        path = tmp_path / "score.osc"
        stream = FakeStream('s1', 0.0, 1.0, [[]])
        assert writer.write_score(str(path), [stream]) == str(path)

    def test_bundle_size_coerenti(self, writer, tmp_path):
        """Ogni bundle e' preceduto dalla propria lunghezza: se il conteggio
        sbaglia, scsynth legge spazzatura dal bundle successivo."""
        stream = FakeStream('s1', 0.0, 1.0, [[grain(0.1), grain(0.2)]])
        path = tmp_path / "score.osc"
        writer.write_score(str(path), [stream])

        data = path.read_bytes()
        pos = 0
        while pos < len(data):
            size = struct.unpack_from('>i', data, pos)[0]
            assert size > 0
            assert data[pos + 4:pos + 12] == b'#bundle\x00'
            pos += 4 + size
        assert pos == len(data)


class TestSampleMancante:
    """Il ramo numpy verifica i sample col SampleRegistry e csound esce
    non-zero su una GEN01 che non trova il file. Senza controllo qui, il path
    finirebbe nello score senza mai toccare il filesystem e scsynth su
    /b_allocReadChannel fallito stampa e prosegue: un nome sbagliato darebbe
    un file di puro silenzio, exit 0."""

    def test_e_un_errore_col_nome_del_file(self, tmp_path):
        from pge.shared.exceptions import SampleNotFoundError

        writer = SuperColliderScoreWriter(
            table_map={1: ('sample', 'pinoo.wav')},
            window_registry=NumpyWindowRegistry(),
            synthdef_bytes=b'SCgf-FAKE',
            samples_dir=str(tmp_path),
            output_sr=48000,
        )
        with pytest.raises(SampleNotFoundError) as exc:
            writer.build_bundles([FakeStream('s1', 0.0, 1.0, [[]])])
        assert 'pinoo.wav' in str(exc.value)
