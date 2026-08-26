"""
test_stream_read_direction.py

`grain.read_direction` end-to-end sullo Stream (issue #207).

L'osservabile e' il **segno di `Grain.pitch_ratio`**: e' l'unica grandezza che
decide il verso di lettura interno al grano (`pitch_controller.calculate()`
nega il ratio quando `grain_reverse=True`, e il renderer ne fa l'incremento di
fasore). Nessun test qui guarda flag interni: guarda i grani prodotti.

Organizzazione:
1. Regressione: i quattro casi di `grain.reverse` restano invariati
2. read_direction scalare
3. read_direction come envelope (il verso cambia ai breakpoint, e solo li')
4. Interpolazione: ogni interp diverso da `step` e' errore
5. Dominio dei valori
6. Exclusivity group con grain.reverse
7. deviation_probability: chiave dedicata
"""

import numpy as np
import pytest
import soundfile as sf

from pge.core.stream import Stream
from pge.shared.exceptions import InvalidFieldValueError
from conftest import flat_grains

SR = 48000


@pytest.fixture
def build(tmp_path):
    """Stream vero attraverso __init__, pronto a generare grani.

    Il sample e' un wav silenzioso di 2 s: la generazione dei grani e'
    simbolica, conta solo la durata dichiarata dall'header. I riferimenti
    Csound li assegna il Generator in produzione: qui vanno iniettati a mano.
    """
    sf.write(str(tmp_path / 'tone.wav'),
             np.zeros(int(SR * 2.0), dtype='float32'), SR)

    def _build(**overrides):
        grain = {'duration': 0.05, 'envelope': 'hanning'}
        grain.update(overrides.pop('grain', {}))
        params = {
            'stream_id': 'test_stream',
            'onset': 0.0,
            'duration': 2.0,
            'sample': 'tone.wav',
            'grain': grain,
        }
        params.update(overrides)
        stream = Stream(params, samples_dir=str(tmp_path))
        stream.sample_table_num = 1
        stream.window_table_map = {'hanning': 2}
        return stream

    return _build


def _segni(stream):
    """I segni di pitch_ratio dei grani generati, in ordine di onset."""
    return [g.pitch_ratio < 0 for g in flat_grains(stream)]


def _transizioni(stream):
    """Gli istanti in cui il verso cambia, come `[(onset, segno), ...]`.

    L'insieme dei segni dice *se* i due versi compaiono; questo dice *quando*.
    Serve per tutto cio' che governa i confini nel tempo — la distribuzione
    dei cicli, la posizione dei breakpoint — dove l'insieme resta identico
    anche quando il comportamento cambia del tutto.
    """
    out, precedente = [], None
    for grain in flat_grains(stream):
        segno = 1 if grain.pitch_ratio > 0 else -1
        if segno != precedente:
            out.append((round(grain.onset, 4), segno))
            precedente = segno
    return out


# =============================================================================
# 1. REGRESSIONE: i quattro casi di grain.reverse
# =============================================================================

class TestReverseInvariata:
    """La tabella della issue #207, riga per riga. `grain.reverse` non cambia:
    questa e' la garanzia di nessun breaking change."""

    def test_speed_negativo_senza_reverse_legge_indietro(self, build):
        """Modalita' 'auto': il verso base segue il segno di speed_ratio."""
        stream = build(pointer={'speed_ratio': -1})
        assert all(_segni(stream))

    def test_speed_negativo_con_reverse_identico(self, build):
        """La dichiarazione non cambia nulla rispetto al caso sopra."""
        stream = build(pointer={'speed_ratio': -1}, grain={'reverse': None})
        assert all(_segni(stream))

    def test_speed_positivo_con_reverse_legge_indietro(self, build):
        """Forzato: il verso base e' sempre indietro, comunque vada la testina."""
        stream = build(pointer={'speed_ratio': 1}, grain={'reverse': None})
        assert all(_segni(stream))

    def test_gate_saturato_ribalta_ogni_grano(self, build):
        """`deviation_probability: {reverse: 100}` flippa il verso di ogni
        grano: e' il caso deterministico ottenuto per via stocastica che ha
        generato la issue. Resta valido."""
        stream = build(pointer={'speed_ratio': -1}, grain={'reverse': None},
                       deviation_probability={'reverse': 100})
        assert not any(_segni(stream))

    def test_speed_positivo_senza_niente_legge_avanti(self, build):
        """Entrambe le chiavi assenti: comportamento 'auto' di sempre."""
        stream = build(pointer={'speed_ratio': 1})
        assert not any(_segni(stream))

    def test_reverse_con_valore_resta_un_errore(self, build):
        with pytest.raises(InvalidFieldValueError):
            build(grain={'reverse': True})


# =============================================================================
# 2. READ_DIRECTION SCALARE
# =============================================================================

class TestScalare:
    """Il verso e' dichiarato, e non dipende dal segno della velocita'."""

    @pytest.mark.parametrize("speed", [1, -1])
    def test_meno_uno_legge_indietro(self, build, speed):
        stream = build(pointer={'speed_ratio': speed},
                       grain={'read_direction': -1})
        assert all(_segni(stream))

    @pytest.mark.parametrize("speed", [1, -1])
    def test_piu_uno_legge_avanti(self, build, speed):
        stream = build(pointer={'speed_ratio': speed},
                       grain={'read_direction': 1})
        assert not any(_segni(stream))

    def test_testina_indietro_grani_avanti(self, build):
        """Il caso della issue, senza saturare nessun gate."""
        stream = build(pointer={'speed_ratio': -1},
                       grain={'read_direction': 1})
        assert not any(_segni(stream))

    def test_il_modulo_del_pitch_non_cambia(self, build):
        """La chiave governa il verso, non la trasposizione."""
        stream = build(grain={'read_direction': -1})
        assert {abs(g.pitch_ratio) for g in flat_grains(stream)} == {1.0}


# =============================================================================
# 3. READ_DIRECTION COME ENVELOPE
# =============================================================================

class TestEnvelope:
    """Il verso cambia nel tempo ai breakpoint, e SOLO li'."""

    def test_il_verso_cambia_al_breakpoint(self, build):
        stream = build(grain={'read_direction': [[0, 1], [1.0, -1]]})

        prima = [g.pitch_ratio for g in flat_grains(stream) if g.onset < 1.0]
        dopo = [g.pitch_ratio for g in flat_grains(stream) if g.onset >= 1.0]

        assert prima and dopo
        assert all(r > 0 for r in prima)
        assert all(r < 0 for r in dopo)

    def test_nessun_valore_intermedio(self, build):
        """`step` imposto: fra i due stati non c'e' rampa, quindi i grani
        portano solo i valori dichiarati."""
        stream = build(grain={'read_direction': [[0, 1], [1.0, -1]]})
        assert {g.pitch_ratio for g in flat_grains(stream)} == {1.0, -1.0}

    def test_step_esplicito_stessa_semantica(self, build):
        nudo = build(grain={'read_direction': [[0, 1], [1.0, -1]]})
        esplicito = build(grain={'read_direction': {
            'type': 'step', 'points': [[0, 1], [1.0, -1]]}})
        assert _segni(nudo) == _segni(esplicito)

    def test_tre_zone(self, build):
        stream = build(grain={'read_direction': [[0, 1], [0.6, -1], [1.4, 1]]})

        def verso(t0, t1):
            return {g.pitch_ratio for g in flat_grains(stream)
                    if t0 <= g.onset < t1}

        assert verso(0.0, 0.6) == {1.0}
        assert verso(0.6, 1.4) == {-1.0}
        assert verso(1.4, 2.0) == {1.0}

    def test_macro_forme_dentro_il_dict_renderizzano(self, build):
        """Le forme che il dict accetta devono anche renderizzare.

        `Envelope` costruisce un formato compatto e un BP group dentro
        `points`, quindi il validatore li accetta: qui si verifica che sia
        davvero cosi' fino ai grani, e non solo un permesso concesso a monte.
        """
        compatto = build(grain={'read_direction': {
            'points': [[[0, 1], [50, -1]], 2.0, 2]}})
        gruppo = build(grain={'read_direction': {
            'points': [[[0, 1], [1.0, -1]], 'step']}})

        assert {g.pitch_ratio for g in flat_grains(compatto)} == {1.0, -1.0}
        assert {g.pitch_ratio for g in flat_grains(gruppo)} == {1.0, -1.0}

    def test_punto_del_pattern_senza_interp_renderizza(self, build):
        """`[x%, y, None]` dentro il pattern di un ciclo: il validatore lo
        accetta come punto piatto con l'interp lasciato al default, e qui si
        verifica che il builder lo espanda davvero invece di romperci sopra.

        Il punto porta un `y` **diverso** da quello che lo precede: con lo
        stesso valore il grafico sarebbe identico a quello senza il punto, e
        il test passerebbe senza osservare cio' che dichiara di pinnare.
        """
        con = build(grain={'read_direction':
                           [[[0, 1], [50, -1, None], [100, 1]], 2.0, 2]})
        senza = build(grain={'read_direction':
                             [[[0, 1], [100, 1]], 2.0, 2]})

        assert {g.pitch_ratio for g in flat_grains(con)} == {1.0, -1.0}
        assert _transizioni(con) != _transizioni(senza)

    def test_time_unit_del_dict_resta_onorato(self, build):
        """La normalizzazione preserva le altre chiavi del dict: con
        `time_unit: normalized` il breakpoint a 0.5 cade a meta' stream."""
        stream = build(grain={'read_direction': {
            'points': [[0, 1], [0.5, -1]], 'time_unit': 'normalized'}})

        prima = [g.pitch_ratio for g in flat_grains(stream) if g.onset < 1.0]
        dopo = [g.pitch_ratio for g in flat_grains(stream) if g.onset >= 1.0]
        assert prima and dopo
        assert all(r > 0 for r in prima)
        assert all(r < 0 for r in dopo)

    def test_envelope_indipendente_dalla_velocita(self, build):
        """Il verso dichiarato non e' corretto dal segno di speed_ratio."""
        avanti = build(pointer={'speed_ratio': 1},
                       grain={'read_direction': [[0, 1], [1.0, -1]]})
        indietro = build(pointer={'speed_ratio': -1},
                         grain={'read_direction': [[0, 1], [1.0, -1]]})
        assert _segni(avanti) == _segni(indietro)


# =============================================================================
# 4. INTERPOLAZIONE
# =============================================================================

class TestInterpolazione:
    """Ogni interp diverso da `step` e' un errore esplicito, in tutte e tre le
    forme in cui e' dichiarabile. Mai un avviso, mai una correzione silenziosa."""

    @pytest.mark.parametrize("interp", ['linear', 'cubic'])
    def test_forma_dict(self, build, interp):
        with pytest.raises(InvalidFieldValueError) as exc:
            build(grain={'read_direction': {
                'type': interp, 'points': [[0, 1], [1.0, -1]]}})
        assert exc.value.field == 'grain.read_direction'

    @pytest.mark.parametrize("interp", ['linear', 'cubic'])
    def test_tag_per_punto(self, build, interp):
        with pytest.raises(InvalidFieldValueError):
            build(grain={'read_direction': [[0, 1, interp], [1.0, -1]]})

    @pytest.mark.parametrize("interp", ['linear', 'cubic'])
    def test_bp_group(self, build, interp):
        with pytest.raises(InvalidFieldValueError):
            build(grain={'read_direction': [[[0, 1], [1.0, -1]], interp]})

    def test_hint_leggibile(self, build):
        with pytest.raises(InvalidFieldValueError) as exc:
            build(grain={'read_direction': {
                'type': 'linear', 'points': [[0, 1], [1.0, -1]]}})
        assert 'due stati' in exc.value.hint.lower()

    def test_errore_attribuito_allo_stream(self, build):
        """L'errore dice QUALE stream lo contiene."""
        with pytest.raises(InvalidFieldValueError) as exc:
            build(grain={'read_direction': {
                'type': 'linear', 'points': [[0, 1], [1.0, -1]]}})
        assert exc.value.stream_id == 'test_stream'


# =============================================================================
# 5. DOMINIO
# =============================================================================

class TestDominio:

    @pytest.mark.parametrize("value", [0, 0.5, -0.5, 2])
    def test_scalare_fuori_dominio(self, build, value):
        with pytest.raises(InvalidFieldValueError):
            build(grain={'read_direction': value})

    def test_breakpoint_fuori_dominio(self, build):
        with pytest.raises(InvalidFieldValueError):
            build(grain={'read_direction': [[0, 1], [1.0, 0]]})

    def test_chiave_vuota(self, build):
        """`read_direction:` senza valore non dichiara nessun verso."""
        with pytest.raises(InvalidFieldValueError):
            build(grain={'read_direction': None})


# =============================================================================
# 6. EXCLUSIVITY GROUP
# =============================================================================

class TestExclusivity:
    """Le due chiavi insieme sono un errore, non una priorita'."""

    def test_entrambe_presenti_e_errore(self, build):
        with pytest.raises(InvalidFieldValueError) as exc:
            build(grain={'reverse': None, 'read_direction': 1})
        assert exc.value.field == 'grain.read_direction'

    def test_hint_nomina_entrambe(self, build):
        with pytest.raises(InvalidFieldValueError) as exc:
            build(grain={'reverse': None, 'read_direction': 1})
        assert 'grain.reverse' in exc.value.hint

    def test_errore_prima_di_ogni_altra_validazione(self, build):
        """Anche con un read_direction a sua volta invalido, l'errore
        segnalato e' quello che l'utente deve risolvere per primo."""
        with pytest.raises(InvalidFieldValueError) as exc:
            build(grain={'reverse': None, 'read_direction': 0.5})
        assert 'grain.reverse' in exc.value.hint

    def test_solo_read_direction_annulla_il_parametro_reverse(self, build):
        stream = build(grain={'read_direction': 1})
        assert stream.reverse is None
        assert stream.read_direction is not None

    def test_solo_reverse_annulla_il_parametro_read_direction(self, build):
        stream = build(grain={'reverse': None})
        assert stream.read_direction is None
        assert stream.reverse is not None

    def test_nessuna_delle_due_lascia_reverse(self, build):
        """Con entrambe assenti vince reverse: la modalita' 'auto' di sempre."""
        stream = build()
        assert stream.read_direction is None
        assert stream.grain_reverse_mode == 'auto'


# =============================================================================
# 7. DEVIATION_PROBABILITY
# =============================================================================

class TestDeviationProbability:
    """Il verso stocastico si dichiara sulla chiave che governa il verso."""

    def test_default_deterministico(self, build):
        """Senza deviation_probability il verso dichiarato e' quello reso: non
        serve saturare nessun gate."""
        stream = build(grain={'read_direction': 1})
        assert not any(_segni(stream))

    def test_gate_saturato_ribalta(self, build):
        stream = build(grain={'read_direction': 1},
                       deviation_probability={'read_direction': 100})
        assert all(_segni(stream))

    def test_gate_a_zero_non_tocca_nulla(self, build):
        stream = build(grain={'read_direction': -1},
                       deviation_probability={'read_direction': 0})
        assert all(_segni(stream))

    def test_la_chiave_reverse_non_governa_read_direction(self, build):
        """Un vecchio `reverse: 100` rimasto nello YAML non ribalta in
        silenzio il verso appena dichiarato."""
        stream = build(grain={'read_direction': 1},
                       deviation_probability={'reverse': 100})
        assert not any(_segni(stream))

    def test_gate_intermedio_mescola_i_due_versi(self, build):
        """A probabilita' intermedia i grani portano entrambi i versi: e' la
        via dichiarativa del verso stocastico."""
        stream = build(grain={'read_direction': 1},
                       deviation_probability={'read_direction': 50},
                       seed=1234)
        segni = _segni(stream)
        assert any(segni) and not all(segni)

    def test_gate_globale_come_ogni_altro_parametro(self, build):
        """Un numero globale vale per tutte le chiavi dello schema, questa
        compresa: nessuna eccezione inventata."""
        stream = build(grain={'read_direction': 1},
                       deviation_probability=100)
        assert all(_segni(stream))


# =============================================================================
# 8. NIENTE ERRORI FUORI DALLA GERARCHIA
# =============================================================================

class TestNienteValueErrorNudo:
    """Un `read_direction` che `Stream` accetta non deve morire piu' in la'
    con un errore che non porta il campo.

    L'osservabile e' il tipo di cio' che risale dal costruttore: dentro la
    gerarchia `EngineError` (campo, hint, stream_id) oppure fuori, dove
    l'utente perde la riga di contesto e PGE-ls perde il messaggio che parsa.
    """

    @pytest.mark.parametrize("dist", [
        'bogus',                                   # nome ignoto, stringa
        {'type': 'bogus'},                         # nome ignoto, dict
        {'type': 'geometric', 'ratio': 0},         # parametro fuori dominio
        {'type': 'logarithmic', 'base': 1},        # parametro fuori dominio
        {'ratio': 1.5},                            # parametro estraneo al tipo
        {'type': 5},                               # il tipo non e' un nome
        {'type': 'exponential', 'rate': 0},        # bound: alza ParameterBoundError
        {'type': 'power', 'exponent': 'x'},        # validato dal costruttore
    ])
    def test_distribuzione_temporale_non_costruibile(self, build, dist):
        """Il quinto elemento del formato compatto e' la distribuzione
        temporale: `is_compact_format` accetta li' qualunque `str` o `dict`,
        e cio' che ne esce non e' sempre una distribuzione."""
        with pytest.raises(InvalidFieldValueError) as exc:
            build(grain={'read_direction':
                         [[[0, 1], [100, -1]], 2.0, 2, 'step', dist]})
        assert exc.value.field == 'grain.read_direction'
        assert exc.value.stream_id == 'test_stream'

    def test_distribuzione_valida_renderizza(self, build):
        """Il guard non chiude la porta: la distribuzione dichiarata passa
        **e si vede**.

        L'insieme dei segni non basta a osservarla: veniva identico con
        `linear`, con `geometric` e senza alcun quinto elemento. Cio' che la
        distribuzione governa sono i confini dei cicli, quindi l'osservabile
        e' l'istante in cui il verso cambia. Il pattern flippa a meta' ciclo
        proprio per rendere quei confini leggibili.
        """
        pattern = [[0, 1], [50, -1]]
        geometrica = build(grain={'read_direction':
                                  [pattern, 2.0, 2, 'step',
                                   {'type': 'geometric', 'ratio': 2.0}]})
        uniforme = build(grain={'read_direction':
                                [pattern, 2.0, 2, 'step', 'linear']})

        assert _transizioni(geometrica) != _transizioni(uniforme)
        # ratio 2: il secondo ciclo dura il doppio del primo, quindi comincia
        # a ~1/3 dello stream invece che a meta'.
        assert _transizioni(geometrica)[2][0] < 0.8
        assert _transizioni(uniforme)[2][0] == pytest.approx(1.0, abs=0.05)
