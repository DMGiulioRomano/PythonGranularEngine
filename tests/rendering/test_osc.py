# tests/rendering/test_osc.py
"""
Suite TDD per il layer OSC (issue #228).

`pge.rendering.osc` e' l'equivalente, per il backend SuperCollider, di cio'
che `ScoreWriter` fa per Csound: serializza. La differenza e' che il formato
e' binario, quindi la sola verifica possibile senza scsynth installato e'
sui byte. Qui si fissano proprio quelli.

Riferimenti di formato:
- OSC 1.0: stringhe null-terminated e paddate a multipli di 4, int32/float32
  big-endian, blob = int32 di lunghezza + dati paddati.
- Bundle: "#bundle\\0" + timetag NTP a 64 bit + elementi, ognuno preceduto
  dalla propria lunghezza int32.
- File NRT di scsynth: sequenza di bundle, ognuno preceduto dalla propria
  lunghezza int32 (big-endian). Nessun header di file.

Copertura:
1. TestEncodeStrings        - padding e terminatore delle stringhe OSC
2. TestEncodeNumbers        - int32/float32 big-endian
3. TestEncodeBlob           - blob = size + dati paddati
4. TestOscMessage           - address + type tag + argomenti
5. TestTimetag              - NTP a 64 bit, tempo relativo allo zero
6. TestOscBundle            - "#bundle" + timetag + elementi size-prefixed
7. TestNrtScoreFile         - prefisso di lunghezza per bundle, ordine
8. TestRoundTrip            - un decoder minimale rilegge cio' che scriviamo
"""

import struct

import pytest

from pge.rendering import osc


# =============================================================================
# DECODER MINIMALE (solo per i test: se il decoder e' d'accordo con
# l'encoder e i byte attesi sono quelli, il formato e' quello giusto)
# =============================================================================

def _read_string(data, pos):
    end = data.index(b'\x00', pos)
    value = data[pos:end].decode('utf-8')
    pos = end + 1
    while pos % 4 != 0:
        assert data[pos] == 0, "padding non nullo"
        pos += 1
    return value, pos


def decode_message(data):
    """Decodifica un messaggio OSC in (address, [args])."""
    address, pos = _read_string(data, 0)
    tags, pos = _read_string(data, pos)
    assert tags.startswith(','), f"type tag string malformata: {tags!r}"
    args = []
    for tag in tags[1:]:
        if tag == 'i':
            args.append(struct.unpack_from('>i', data, pos)[0])
            pos += 4
        elif tag == 'f':
            args.append(struct.unpack_from('>f', data, pos)[0])
            pos += 4
        elif tag == 's':
            value, pos = _read_string(data, pos)
            args.append(value)
        elif tag == 'b':
            size = struct.unpack_from('>i', data, pos)[0]
            pos += 4
            args.append(data[pos:pos + size])
            pos += size
            while pos % 4 != 0:
                pos += 1
        else:
            raise AssertionError(f"tag non gestito: {tag!r}")
    assert pos == len(data), "byte residui dopo gli argomenti"
    return address, args


def decode_bundle(data):
    """Decodifica un bundle OSC in (tempo_secondi, [messaggi_decodificati])."""
    assert data[:8] == b'#bundle\x00'
    seconds, fraction = struct.unpack_from('>II', data, 8)
    time = seconds + fraction / 2 ** 32
    pos = 16
    elements = []
    while pos < len(data):
        size = struct.unpack_from('>i', data, pos)[0]
        pos += 4
        elements.append(decode_message(data[pos:pos + size]))
        pos += size
    return time, elements


def decode_nrt(data):
    """Decodifica un file NRT in una lista di bundle decodificati."""
    pos = 0
    bundles = []
    while pos < len(data):
        size = struct.unpack_from('>i', data, pos)[0]
        pos += 4
        bundles.append(decode_bundle(data[pos:pos + size]))
        pos += size
    return bundles


# =============================================================================
# 1. STRINGHE
# =============================================================================

class TestEncodeStrings:
    """Una stringa OSC e' null-terminated e paddata a multipli di 4."""

    @pytest.mark.parametrize("value, expected", [
        ("", b'\x00\x00\x00\x00'),
        ("a", b'a\x00\x00\x00'),
        ("ab", b'ab\x00\x00'),
        ("abc", b'abc\x00'),
        # 4 caratteri: il terminatore obbliga a un blocco intero di padding
        ("abcd", b'abcd\x00\x00\x00\x00'),
        ("/s_new", b'/s_new\x00\x00'),
    ])
    def test_padding(self, value, expected):
        assert osc.encode_string(value) == expected

    def test_lunghezza_sempre_multiplo_di_quattro(self):
        for n in range(0, 32):
            assert len(osc.encode_string("x" * n)) % 4 == 0

    def test_utf8(self):
        """Nello score finiscono path di file, assoluti: dipendono anche da
        dove sta il checkout, non solo dai nomi in refs/. Un accento faceva
        UnicodeEncodeError dentro l'encoder, senza dire quale file
        (review PR #240, punto 4). scsynth accetta UTF-8."""
        encoded = osc.encode_string("/musica/però/tromba.wav")
        assert len(encoded) % 4 == 0
        assert encoded.rstrip(b'\x00').decode('utf-8') == "/musica/però/tromba.wav"

    def test_percorso_non_ascii_sopravvive_al_round_trip(self):
        _, args = decode_message(
            osc.message('/b_allocReadChannel', 1, "/rèfs/ottavìno.wav", 0, 0, 0))
        assert args[1] == "/rèfs/ottavìno.wav"


# =============================================================================
# 2. NUMERI
# =============================================================================

class TestEncodeNumbers:
    """int32 e float32, big-endian."""

    def test_int32_big_endian(self):
        assert osc.encode_int32(1) == b'\x00\x00\x00\x01'
        assert osc.encode_int32(-1) == b'\xff\xff\xff\xff'
        assert osc.encode_int32(48000) == struct.pack('>i', 48000)

    def test_float32_big_endian(self):
        assert osc.encode_float32(1.0) == struct.pack('>f', 1.0)
        assert osc.encode_float32(-0.5) == struct.pack('>f', -0.5)

    def test_float32_tronca_a_singola_precisione(self):
        """float64 -> float32: la precisione persa e' quella del formato,
        non un bug nostro. Il valore riletto e' il float32 piu' vicino."""
        encoded = osc.encode_float32(0.1)
        assert struct.unpack('>f', encoded)[0] == pytest.approx(0.1, abs=1e-7)


# =============================================================================
# 3. BLOB
# =============================================================================

class TestEncodeBlob:
    """Il blob e' int32 di lunghezza + dati, paddati a multipli di 4."""

    def test_blob_vuoto(self):
        assert osc.encode_blob(b'') == b'\x00\x00\x00\x00'

    def test_blob_paddato(self):
        assert osc.encode_blob(b'ab') == b'\x00\x00\x00\x02ab\x00\x00'

    def test_blob_gia_allineato_non_riceve_padding(self):
        assert osc.encode_blob(b'abcd') == b'\x00\x00\x00\x04abcd'

    def test_lunghezza_dichiarata_e_quella_dei_dati_non_del_padding(self):
        blob = osc.encode_blob(b'abcde')
        assert struct.unpack_from('>i', blob, 0)[0] == 5
        assert len(blob) % 4 == 0


# =============================================================================
# 4. MESSAGGI
# =============================================================================

class TestOscMessage:
    """address + type tag string + argomenti, nell'ordine."""

    def test_messaggio_senza_argomenti(self):
        data = osc.message('/status')
        assert decode_message(data) == ('/status', [])

    def test_type_tag_string_inizia_con_virgola(self):
        data = osc.message('/x', 1, 2.0, 'tre')
        _, pos = _read_string(data, 0)
        tags, _ = _read_string(data, pos)
        assert tags == ',ifs'

    def test_int_bool_e_float_non_si_confondono(self):
        """bool e' sottoclasse di int in Python: se passasse per 'i' senza
        essere convertito il type tag sarebbe giusto per caso. Qui si fissa
        che un bool viaggia come intero 0/1."""
        _, args = decode_message(osc.message('/x', True, False))
        assert args == [1, 0]

    def test_argomenti_misti_round_trip(self):
        data = osc.message('/s_new', 'pgeGrain', 1000, 0, 0, 'amp', 0.5)
        address, args = decode_message(data)
        assert address == '/s_new'
        assert args[:5] == ['pgeGrain', 1000, 0, 0, 'amp']
        assert args[5] == pytest.approx(0.5)

    def test_blob_come_argomento(self):
        data = osc.message('/d_recv', b'\x01\x02\x03')
        address, args = decode_message(data)
        assert address == '/d_recv'
        assert args == [b'\x01\x02\x03']

    def test_tipo_non_supportato_e_un_errore_esplicito(self):
        with pytest.raises(TypeError):
            osc.message('/x', {'non': 'serializzabile'})

    def test_lunghezza_sempre_multiplo_di_quattro(self):
        for args in ([], [1], [1.5], ['ab'], [b'abc'], [1, 'ab', 2.5, b'x']):
            assert len(osc.message('/addr', *args)) % 4 == 0


# =============================================================================
# 5. TIMETAG
# =============================================================================

class TestTimetag:
    """Timetag NTP a 64 bit. In NRT il tempo e' relativo all'inizio del
    render, non all'epoca NTP: 0.0 e' l'istante zero."""

    def test_zero(self):
        assert osc.encode_timetag(0.0) == b'\x00' * 8

    def test_secondi_interi(self):
        assert osc.encode_timetag(3.0) == struct.pack('>II', 3, 0)

    def test_frazione(self):
        seconds, fraction = struct.unpack('>II', osc.encode_timetag(0.5))
        assert seconds == 0
        assert fraction == 2 ** 31

    def test_frazione_non_trabocca_nel_campo_dei_secondi(self):
        """Un tempo appena sotto il secondo intero non deve arrotondare a
        2**32 nel campo frazionario: sarebbe un secondo in piu' scritto nel
        posto sbagliato."""
        seconds, fraction = struct.unpack(
            '>II', osc.encode_timetag(1 - 1e-12))
        assert seconds == 0
        assert fraction == 2 ** 32 - 1

    def test_tempo_negativo_rifiutato(self):
        with pytest.raises(ValueError):
            osc.encode_timetag(-0.001)


# =============================================================================
# 6. BUNDLE
# =============================================================================

class TestOscBundle:

    def test_header_e_timetag(self):
        data = osc.bundle(2.5, [osc.message('/x')])
        assert data[:8] == b'#bundle\x00'
        assert data[8:16] == osc.encode_timetag(2.5)

    def test_elementi_preceduti_dalla_loro_lunghezza(self):
        m1 = osc.message('/uno', 1)
        m2 = osc.message('/due', 2)
        data = osc.bundle(0.0, [m1, m2])
        assert struct.unpack_from('>i', data, 16)[0] == len(m1)
        assert data[20:20 + len(m1)] == m1

    def test_round_trip(self):
        time, elements = decode_bundle(osc.bundle(1.25, [
            osc.message('/uno', 1),
            osc.message('/due', 'x'),
        ]))
        assert time == pytest.approx(1.25)
        assert elements == [('/uno', [1]), ('/due', ['x'])]

    def test_bundle_vuoto_e_legale(self):
        """Un bundle senza messaggi resta un marcatore di tempo valido: e'
        cosi' che si dichiara la fine del render."""
        time, elements = decode_bundle(osc.bundle(9.0, []))
        assert time == pytest.approx(9.0)
        assert elements == []


# =============================================================================
# 7. FILE NRT
# =============================================================================

class TestNrtScoreFile:
    """Il file letto da `scsynth -N` e' una sequenza di bundle, ognuno
    preceduto dalla propria lunghezza int32. Nessun header di file."""

    def test_scrive_prefisso_di_lunghezza_per_bundle(self, tmp_path):
        path = tmp_path / "score.osc"
        b0 = osc.bundle(0.0, [osc.message('/x')])
        osc.write_nrt_score(str(path), [b0])

        data = path.read_bytes()
        assert struct.unpack_from('>i', data, 0)[0] == len(b0)
        assert data[4:] == b0

    def test_nessun_header_di_file(self, tmp_path):
        path = tmp_path / "score.osc"
        osc.write_nrt_score(str(path), [osc.bundle(0.0, [])])
        # Il primo campo del file e' gia' la lunghezza del primo bundle.
        assert path.read_bytes()[4:12] == b'#bundle\x00'

    def test_ordine_preservato(self, tmp_path):
        path = tmp_path / "score.osc"
        osc.write_nrt_score(str(path), [
            osc.bundle(0.0, [osc.message('/primo')]),
            osc.bundle(1.0, [osc.message('/secondo')]),
        ])
        bundles = decode_nrt(path.read_bytes())
        assert [b[1][0][0] for b in bundles] == ['/primo', '/secondo']

    def test_file_vuoto_se_nessun_bundle(self, tmp_path):
        path = tmp_path / "score.osc"
        osc.write_nrt_score(str(path), [])
        assert path.read_bytes() == b''


# =============================================================================
# 8. ROUND TRIP COMPLETO
# =============================================================================

class TestRoundTrip:

    def test_score_completo(self, tmp_path):
        path = tmp_path / "score.osc"
        osc.write_nrt_score(str(path), [
            osc.bundle(0.0, [
                osc.message('/d_recv', b'DEF'),
                osc.message('/b_allocRead', 1, '/refs/pino.wav', 0, 0),
            ]),
            osc.bundle(0.5, [
                osc.message('/s_new', 'pgeGrain', 1000, 0, 0, 'dur', 0.05),
            ]),
            osc.bundle(3.0, [osc.message('/c_set', 0, 0)]),
        ])

        bundles = decode_nrt(path.read_bytes())
        assert [round(t, 6) for t, _ in bundles] == [0.0, 0.5, 3.0]
        assert bundles[0][1][0] == ('/d_recv', [b'DEF'])
        assert bundles[0][1][1][0] == '/b_allocRead'
        assert bundles[1][1][0][0] == '/s_new'
        assert bundles[2][1][0] == ('/c_set', [0, 0])
