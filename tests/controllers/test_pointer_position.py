"""
`pointer.position`: la posizione di lettura dalla mappa (issue #312, mappe
caotiche 4/7).

    maps:
      m1: {type: logistic, r: 3.2}
    pointer:
      position: (m1)
      loop_start: 0.2
      loop_dur: 0.1
      loop_unit: normalized

Oggi la legge di moto del puntatore e' una sola, `start + integrale di
speed_ratio`; il resto di `PointerController.calculate` e' confinamento.
`position` e' una seconda legge di moto: la posizione **nella finestra
attiva**, da 0 a 1 — la finestra di loop se c'e', altrimenti il file intero.
Il confinamento resta quello di oggi.

Tutto dall'interfaccia dello Stream, sui grani: e' li' che una posizione di
lettura si misura.
"""
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from pge.core.stream import Stream
from pge.envelopes.envelope import Envelope
from pge.expressions.expression import Expression
from pge.shared.exceptions import (
    ExpressionError,
    InvalidFieldValueError,
    MissingFieldError,
)

_SAMPLE = 'due_secondi.wav'
DURATA_SAMPLE = 2.0


@pytest.fixture(scope='module')
def samples_dir(tmp_path_factory):
    cartella = tmp_path_factory.mktemp('samples')
    sf.write(str(cartella / _SAMPLE), np.zeros(96000, dtype='float32'), 48000)
    return str(cartella)


@pytest.fixture
def stream(samples_dir):
    def costruisci(pointer, maps=None, duration=2.0, **extra):
        params = {
            'stream_id': 's1',
            'onset': 0.0,
            'duration': duration,
            'sample': _SAMPLE,
            'density': 25,
            'grain': {'envelope': 'hanning', 'duration': 0.05},
            'pointer': pointer,
        }
        if maps is not None:
            params['maps'] = maps
        params.update(extra)
        s = Stream(params, seed=1441, samples_dir=samples_dir)
        s.sample_table_num = 1
        s.window_table_map = {'hanning': 2}
        return s
    return costruisci


def _posizioni(s, voce=0):
    return [g.pointer_pos for g in s.voices[voce]]


# =============================================================================
# 1. LO YAML DELLA ISSUE
# =============================================================================

class TestLoYamlDellaIssue:

    @pytest.fixture
    def grani(self, stream):
        s = stream(
            {'position': '(m1)', 'loop_start': 0.2, 'loop_dur': 0.1,
             'loop_unit': 'normalized'},
            maps={'m1': {'type': 'logistic', 'r': 3.2}})
        return s.voices[0]

    def test_due_sole_posizioni(self, grani):
        """Con r = 3.2 la logistica ha un ciclo di due valori."""
        assert len(grani) > 20
        assert len({round(g.pointer_pos, 9) for g in grani}) == 2

    def test_a_0513_e_0799_della_finestra(self, grani):
        """La finestra va da 0.2 a 0.3 del file, cioe' da 0.4 a 0.6 s."""
        frazioni = {round((g.pointer_pos - 0.4) / 0.2, 3) for g in grani}
        assert frazioni == {0.513, 0.799}

    def test_si_alternano(self, grani):
        posizioni = [round(g.pointer_pos, 9) for g in grani]
        assert all(a != b for a, b in zip(posizioni, posizioni[1:]))


# =============================================================================
# 2. LA FINESTRA ATTIVA
# =============================================================================

class TestLaFinestra:

    def test_senza_loop_e_il_file_intero(self, stream):
        s = stream({'position': 0.25})
        assert len(_posizioni(s)) > 20
        assert set(_posizioni(s)) == {0.25 * DURATA_SAMPLE}

    def test_col_loop_e_la_finestra_di_loop(self, stream):
        s = stream({'position': 0.5, 'loop_start': 0.4, 'loop_end': 0.9})
        assert set(np.round(_posizioni(s), 12)) == {0.65}

    def test_la_finestra_vale_da_subito(self, stream):
        """Con `speed_ratio` il puntatore entra nel loop quando ci arriva;
        con `position` non c'e' un viaggio: il primo grano e' gia' dentro."""
        s = stream({'position': 0.0, 'loop_start': 1.5, 'loop_dur': 0.2})
        assert _posizioni(s)[0] == pytest.approx(1.5)

    def test_loop_unit_non_riscala_la_posizione(self, stream):
        """`position` e' sempre una frazione della finestra: `loop_unit`
        dice in che unita' sono scritti i bordi, non lei."""
        in_secondi = stream(
            {'position': 0.5, 'loop_start': 0.4, 'loop_dur': 0.2})
        normalizzato = stream(
            {'position': 0.5, 'loop_start': 0.2, 'loop_dur': 0.1,
             'loop_unit': 'normalized'})
        assert _posizioni(in_secondi) == pytest.approx(_posizioni(normalizzato))
        assert _posizioni(in_secondi)[0] == pytest.approx(0.5)

    def test_a_cavallo_della_fine_del_file(self, stream):
        """La finestra 1.8 - 2.3 s esce da un file di 2 s: l'80% della
        finestra e' a 2.2 s, cioe' a 0.2 s."""
        s = stream({'position': 0.8, 'loop_start': 1.8, 'loop_dur': 0.5})
        assert set(np.round(_posizioni(s), 9)) == {0.2}

    def test_la_finestra_che_si_muove(self, stream):
        """Con una finestra a envelope la posizione resta dentro la finestra
        di quell'istante."""
        inizio = [[0, 0.1], [2, 1.2]]
        durata = [[0, 0.3], [2, 0.1]]
        s = stream(
            {'position': '(m1)', 'loop_start': inizio, 'loop_dur': durata},
            maps={'m1': {'type': 'logistic', 'r': 3.9}})
        env_inizio, env_durata = Envelope(inizio), Envelope(durata)
        grani = s.voices[0]
        assert len(grani) > 20
        frazioni = []
        for g in grani:
            t = g.onset
            a, l = env_inizio.evaluate(t), env_durata.evaluate(t)
            assert a - 1e-9 <= g.pointer_pos < a + l + 1e-9
            frazioni.append((g.pointer_pos - a) / l)
        # la mappa usa la finestra, non un punto solo
        assert max(frazioni) - min(frazioni) > 0.5


# =============================================================================
# 3. FUORI DA 0-1: IL WRAP DI OGGI
# =============================================================================

class TestFuoriDaZeroUno:

    @pytest.mark.parametrize('fuori, dentro', [
        (1.25, 0.25), (-0.25, 0.75), (2.5, 0.5), (1.0, 0.0),
    ])
    def test_rientra_a_capo_della_finestra(self, stream, fuori, dentro):
        loop = {'loop_start': 0.4, 'loop_dur': 0.8}
        a = stream({'position': fuori, **loop})
        b = stream({'position': dentro, **loop})
        assert _posizioni(a) == pytest.approx(_posizioni(b), abs=1e-9)

    def test_un_envelope_che_supera_uno_ripassa_la_finestra(self, stream):
        """Da 0 a 3 in 2 secondi: tre passate sulla finestra."""
        s = stream({'position': [[0, 0], [2, 3]]})
        for g in s.voices[0]:
            attesa = (g.onset * 1.5 % 1.0) * DURATA_SAMPLE
            assert g.pointer_pos == pytest.approx(attesa, abs=1e-9)

    def test_non_e_un_errore_al_parse(self, stream):
        """Un numero o un envelope fuori da 0-1 non sono fuori bounds: la
        posizione rientra, non si taglia."""
        stream({'position': 7.5})
        stream({'position': [[0, -2], [2, 5]]})

    def test_un_espressione_fuori_non_scrive_sul_clip_log(self, stream):
        with patch('pge.parameters.parameter.log_clip_warning') as clip:
            s = stream({'position': '(2*m1 - 0.5)'},
                       maps={'m1': {'type': 'logistic', 'r': 3.9}})
            posizioni = _posizioni(s)
        assert clip.call_count == 0
        assert all(0 <= p < DURATA_SAMPLE for p in posizioni)


# =============================================================================
# 4. AL POSTO DI speed_ratio E start
# =============================================================================

class TestAlPostoDiVelocitaEPartenza:

    @pytest.mark.parametrize('altra, valore', [
        ('speed_ratio', 1.0), ('speed_ratio', [[0, 1], [2, 2]]),
        ('start', 0.5), ('start', 0),
    ])
    def test_insieme_e_un_errore(self, stream, altra, valore):
        with pytest.raises(InvalidFieldValueError) as exc:
            stream({'position': 0.5, altra: valore})
        err = exc.value
        assert err.field == 'pointer.position'
        assert err.stream_id == 's1'
        assert altra in err.hint

    def test_l_errore_mostra_il_valore_scritto(self, stream):
        with pytest.raises(InvalidFieldValueError) as exc:
            stream({'position': '(m1)', 'speed_ratio': 2},
                   maps={'m1': {'type': 'logistic', 'r': 3.2}})
        assert exc.value.value == '(m1)'

    def test_vuota_e_un_errore(self, stream):
        with pytest.raises(MissingFieldError) as exc:
            stream({'position': None})
        assert exc.value.fields == ['pointer.position']
        assert exc.value.stream_id == 's1'

    def test_senza_parentesi_e_un_errore_che_le_propone(self, stream):
        with pytest.raises(ExpressionError) as exc:
            stream({'position': 'm1'},
                   maps={'m1': {'type': 'logistic', 'r': 3.2}})
        assert exc.value.field == 'pointer.position'
        assert '(m1)' in exc.value.hint

    def test_una_mappa_non_dichiarata(self, stream):
        with pytest.raises(ExpressionError) as exc:
            stream({'position': '(m2)'},
                   maps={'m1': {'type': 'logistic', 'r': 3.2}})
        assert exc.value.field == 'pointer.position'
        assert 'm2' in exc.value.reason


# =============================================================================
# 5. OFFSET_RANGE E OFFSET DI VOCE: COME OGGI
# =============================================================================

class TestSiSommanoComeOggi:
    """Il confronto e' con la legge di oggi a velocita' zero: un puntatore
    fermo a meta' della finestra e' `position: 0.5`, e tutto cio' che gli si
    somma sopra — la deviazione per grano, l'offset della voce — deve dare
    gli stessi grani."""

    LOOP = {'loop_start': 0.4, 'loop_dur': 0.8}
    FERMO = {'speed_ratio': 0.0, 'start': 0.8, **LOOP}
    POSIZIONE = {'position': 0.5, **LOOP}

    def test_offset_range(self, stream):
        extra = {'deviation_probability': {'pointer': 100}}
        oggi = stream({**self.FERMO, 'offset_range': 0.3}, **extra)
        nuovo = stream({**self.POSIZIONE, 'offset_range': 0.3}, **extra)
        assert len(set(np.round(_posizioni(oggi), 6))) > 20
        assert _posizioni(nuovo) == pytest.approx(_posizioni(oggi), abs=1e-9)

    def test_offset_range_e_una_frazione_della_finestra(self, stream):
        """Stesso seed, stessi sorteggi: in una finestra larga la meta' gli
        scarti dal centro sono la meta'."""
        # Il gate del solo pointer: `deviation_probability: 100` da solo
        # ribalta anche il verso di ogni grano, che sposta la lettura di
        # una durata.
        extra = {'deviation_probability': {'pointer': 100}}
        larga = stream({'position': 0.5, 'offset_range': 0.3,
                        'loop_start': 0.4, 'loop_dur': 0.8}, **extra)
        stretta = stream({'position': 0.5, 'offset_range': 0.3,
                          'loop_start': 0.4, 'loop_dur': 0.4}, **extra)
        scarti_larga = [p - 0.8 for p in _posizioni(larga)]
        scarti_stretta = [p - 0.6 for p in _posizioni(stretta)]
        assert max(abs(x) for x in scarti_larga) > 0.05
        assert scarti_larga == pytest.approx(
            [2 * x for x in scarti_stretta], abs=1e-9)

    def test_gli_offset_di_pointer_delle_voci(self, stream):
        voci = {'voices': {'num_voices': 3,
                           'pointer': {'strategy': 'linear', 'step': 0.1}}}
        oggi = stream(self.FERMO, **voci)
        nuovo = stream(self.POSIZIONE, **voci)
        for v in range(3):
            assert _posizioni(nuovo, v) == pytest.approx(
                _posizioni(oggi, v), abs=1e-9)
        assert _posizioni(nuovo, 1)[0] == pytest.approx(0.9)
        assert _posizioni(nuovo, 2)[0] == pytest.approx(1.0)

    def test_l_offset_di_voce_resta_dentro_la_finestra(self, stream):
        voci = {'voices': {'num_voices': 4,
                           'pointer': {'strategy': 'linear', 'step': 0.3}}}
        s = stream(self.POSIZIONE, **voci)
        for v in range(4):
            assert all(0.4 - 1e-9 <= p < 1.2 + 1e-9 for p in _posizioni(s, v))


# =============================================================================
# 6. IL VERSO
# =============================================================================

class TestIlVerso:

    def test_auto_e_avanti(self, stream):
        """Senza una velocita' dichiarata `auto` non ha un segno da
        seguire: il grano si legge in avanti, anche se la posizione
        scende."""
        s = stream({'position': [[0, 1], [2, 0]]})
        assert all(g.pitch_ratio > 0 for g in s.voices[0])

    def test_auto_e_avanti_anche_su_una_mappa(self, stream):
        s = stream({'position': '(m1)'},
                   maps={'m1': {'type': 'logistic', 'r': 3.9}})
        assert all(g.pitch_ratio > 0 for g in s.voices[0])

    def test_il_verso_si_dichiara_con_read_direction(self, stream):
        s = stream({'position': 0.5},
                   grain={'envelope': 'hanning', 'duration': 0.05,
                          'read_direction': -1})
        assert all(g.pitch_ratio < 0 for g in s.voices[0])

    def test_o_con_reverse(self, stream):
        s = stream({'position': 0.5},
                   grain={'envelope': 'hanning', 'duration': 0.05,
                          'reverse': None})
        assert all(g.pitch_ratio < 0 for g in s.voices[0])

    def test_all_indietro_la_lettura_parte_dalla_fine_del_grano(self, stream):
        """Come oggi: un grano letto all'indietro parte una durata piu'
        avanti."""
        avanti = stream({'position': 0.5})
        indietro = stream({'position': 0.5},
                          grain={'envelope': 'hanning', 'duration': 0.05,
                                 'read_direction': -1})
        assert _posizioni(indietro)[0] == pytest.approx(
            _posizioni(avanti)[0] + 0.05)


# =============================================================================
# 7. NUMERO, ENVELOPE, ESPRESSIONE
# =============================================================================

class TestLeTreForme:

    def test_un_numero_e_una_lettura_ferma(self, stream):
        s = stream({'position': 0.3})
        assert set(np.round(_posizioni(s), 12)) == {0.6}

    def test_un_envelope_e_uno_scrub(self, stream):
        s = stream({'position': [[0, 0.2], [2, 0.7]]})
        for g in s.voices[0]:
            attesa = (0.2 + 0.25 * g.onset) * DURATA_SAMPLE
            assert g.pointer_pos == pytest.approx(attesa, abs=1e-9)

    def test_l_envelope_segue_il_time_mode(self, stream):
        s = stream({'position': [[0, 0], [1, 0.5]]}, time_mode='normalized')
        ultimo = s.voices[0][-1]
        assert ultimo.pointer_pos == pytest.approx(
            0.5 * (ultimo.onset / 2.0) * DURATA_SAMPLE, abs=1e-9)

    def test_un_espressione_legge_la_mappa(self, stream):
        s = stream({'position': '(0.25 + 0.5*m1)'},
                   maps={'m1': {'type': 'logistic', 'r': 3.5}})
        frazioni = sorted({round(p / DURATA_SAMPLE, 3) for p in _posizioni(s)})
        # 0.25 + 0.5 * {0.383, 0.501, 0.827, 0.875}
        assert frazioni == [0.441, 0.5, 0.663, 0.687]

    def test_e_un_parametro_con_un_espressione(self, stream):
        s = stream({'position': '(m1)'},
                   maps={'m1': {'type': 'logistic', 'r': 3.2}})
        assert isinstance(s.pointer_position.value, Expression)

    def test_il_tempo_in_un_espressione(self, stream):
        s = stream({'position': '(t/4)'})
        for g in s.voices[0]:
            assert g.pointer_pos == pytest.approx(
                g.onset / 4 * DURATA_SAMPLE, abs=1e-9)


# =============================================================================
# 8. UN VALORE NON FINITO
# =============================================================================

class TestNonFinito:

    def test_va_all_inizio_della_finestra(self, stream):
        s = stream({'position': '(sqrt(0 - 1))', 'loop_start': 0.4,
                    'loop_dur': 0.8})
        assert set(_posizioni(s)) == {0.4}

    def test_e_lo_scrive_sul_clip_log(self, stream):
        with patch('pge.parameters.parameter.log_clip_warning') as clip:
            s = stream({'position': '(1/0)'})
            posizioni = _posizioni(s)
        assert set(posizioni) == {0.0}
        assert clip.call_count >= 1
        riga = clip.call_args_list[0].kwargs
        assert riga['param_name'] == 'pointer_position'
        assert riga['source'] == 'EXP'
        assert riga['clipped_value'] == 0.0
