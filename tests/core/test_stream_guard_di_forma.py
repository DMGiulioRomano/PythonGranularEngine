"""
test_stream_guard_di_forma.py

La tabella di #211, riga per riga, attraverso lo Stream vero.

Lo stesso corpo malformato, scritto sotto chiavi diverse, deve rispondere
uguale: `InvalidFieldValueError` col nome YAML della chiave in `field` e lo
stream in `stream_id`. Prima di #211 cosi' rispondeva solo
`grain.read_direction`; sotto ogni altra chiave lo stesso corpo risaliva come
`ValueError` nudo o si rendeva in silenzio.

Il `field` e' la parte che il builder non sa: glielo passa chi conosce la
chiave. Per questo la tabella percorre gli ingressi, non le forme — ogni riga
di `CHIAVI` e' una strada diversa verso `EnvelopeBuilder` (parser via
orchestratore, range, gate di deviation_probability globale e per-parametro,
pitch, voices, kwarg di una strategy, curva delle finestre), e una strada che
dimenticasse di passare il campo farebbe cadere la sua riga.
"""

import numpy as np
import pytest
import soundfile as sf

from pge.core.stream import Stream
from pge.shared.exceptions import InvalidFieldValueError

SR = 48000
STREAM_ID = 'stream_guard'


@pytest.fixture
def build(tmp_path):
    """Stream vero attraverso __init__, con un sample silenzioso di 2 s."""
    sf.write(str(tmp_path / 'tone.wav'),
             np.zeros(int(SR * 2.0), dtype='float32'), SR)

    def _build(extra):
        params = {
            'stream_id': STREAM_ID,
            'onset': 0.0,
            'duration': 2.0,
            'sample': 'tone.wav',
            'grain': {'duration': 0.05, 'envelope': 'hanning'},
        }
        for chiave, valore in extra.items():
            if isinstance(valore, dict) and isinstance(params.get(chiave), dict):
                params[chiave] = {**params[chiave], **valore}
            else:
                params[chiave] = valore
        return Stream(params, samples_dir=str(tmp_path))

    return _build


# Ogni riga: il campo atteso, come si scrive il corpo sotto quella chiave, un
# valore y legale per la chiave e l'interp che la chiave ammette.
CHIAVI = {
    'density': (lambda c: {'density': c}, 10, 'linear'),
    'volume': (lambda c: {'volume': c}, -6, 'linear'),
    'grain.duration': (
        lambda c: {'grain': {'duration': c}}, 0.05, 'linear'),
    'grain.duration_range': (
        lambda c: {'grain': {'duration_range': c}}, 0.01, 'linear'),
    'pointer.speed_ratio': (
        lambda c: {'pointer': {'speed_ratio': c}}, 1, 'linear'),
    'grain.read_direction': (
        lambda c: {'grain': {'read_direction': c}}, 1, 'step'),
    'deviation_probability': (
        lambda c: {'deviation_probability': c}, 50, 'linear'),
    'deviation_probability.read_direction': (
        lambda c: {'grain': {'read_direction': 1},
                   'deviation_probability': {'read_direction': c}},
        50, 'linear'),
    'pitch.semitones': (
        lambda c: {'pitch': {'semitones': c}}, 0, 'linear'),
    'voices.num_voices': (
        lambda c: {'voices': {'num_voices': c}}, 2, 'linear'),
    'voices.scatter': (
        lambda c: {'voices': {'num_voices': 2, 'scatter': c}}, 0.5, 'linear'),
    'voices.pan.step': (
        lambda c: {'voices': {'num_voices': 2,
                              'pan': {'strategy': 'step', 'step': c}}},
        10, 'linear'),
    'grain.envelope.curve': (
        lambda c: {'grain': {'envelope': {
            'from': 'hanning', 'to': 'bartlett', 'curve': c}}},
        0.5, 'linear'),
}


def _corpi(y, interp):
    """Le righe della tabella di #211, un difetto per corpo."""
    return {
        'bp_group_un_punto': [[[[0, y]], interp], [1.0, y]],
        'n_reps_zero': [[[0, y], [100, y]], 1.0, 0],
        'n_reps_booleano': [[[0, y], [100, y]], 1.0, True],
        'end_time_booleano': [[[0, y], [100, y]], True, 2],
        'x_oltre_cento': [[[0, y], [150, y]], 1.0, 2],
        'x_indietro': [[[100, y], [0, y]], 1.0, 2],
        'y_non_numerica': [[[0, 'a'], [100, y]], 1.0, 2],
        'y_booleana': [[[0, True], [100, y]], 1.0, 2],
        'distribuzione_ignota': [[[0, y], [100, y]], 1.0, 2, interp, 'banana'],
        # Non e' un guard del builder ma di `Envelope._parse_segments`, che
        # alzava gia' InvalidFieldValueError su un campo cablato
        # (`envelope.point.type`): lo stesso campo passato dall'alto vale
        # anche li'.
        'interp_per_punto_ignoto': [[0, y, 'banana'], [1.0, y]],
    }


CASI = [
    pytest.param(campo, corpo, id=f'{campo}-{corpo}')
    for campo in CHIAVI
    for corpo in _corpi(0, 'linear')
]


@pytest.mark.parametrize("campo, corpo", CASI)
def test_stessa_risposta_sotto_ogni_chiave(build, campo, corpo):
    scrivi, y, interp = CHIAVI[campo]

    with pytest.raises(InvalidFieldValueError) as exc:
        build(scrivi(_corpi(y, interp)[corpo]))

    assert exc.value.field == campo
    assert exc.value.stream_id == STREAM_ID


@pytest.mark.parametrize("campo", list(CHIAVI))
def test_il_corpo_ben_formato_resta_valido(build, campo):
    """La controprova: la stessa forma, scritta bene, si costruisce. Senza,
    una riga potrebbe cadere per una ragione che non e' il guard."""
    scrivi, y, interp = CHIAVI[campo]
    build(scrivi([[[0, y], [50, y], [100, y]], 1.0, 2, interp, 'exponential']))


@pytest.mark.parametrize("campo", ['density', 'deviation_probability'])
def test_il_booleano_sopravvive_alla_scala_normalized(build, campo):
    """Con `time_mode: normalized` l'`end_time` del compatto viene moltiplicato
    per la durata dello stream prima di arrivare al builder: `True * 2.0` e'
    `2.0`, un numero legittimo. La scala non deve convertire cio' che non e'
    un numero, o il guard sul `bool` vale solo sui tempi assoluti."""
    scrivi, y, interp = CHIAVI[campo]
    extra = scrivi([[[0, y], [100, y]], True, 2])
    extra['time_mode'] = 'normalized'

    with pytest.raises(InvalidFieldValueError) as exc:
        build(extra)

    assert exc.value.field == campo
    assert exc.value.value is True


# La scala delle y avviene prima del builder, come quella del tempo: un'unita'
# che non e' quella dello YAML moltiplica ogni y del corpo per un fattore.
# Ogni riga: la chiave, il corpo sotto la sua unita' non di default, una y
# legale in quell'unita'.
SCALE_DELLE_Y = {
    'grain.duration': (
        lambda c: {'grain': {'duration': c, 'duration_unit': 'milliseconds'}},
        50),
    'pointer.loop_start': (
        lambda c: {'pointer': {'loop_unit': 'normalized', 'loop_start': c,
                               'loop_dur': 0.2}},
        0.5),
}


def _punti_non_piatti(y):
    """Il punto malformato e il corpo che lo porta."""
    gruppo = [[[0, y], [50, y]], 'linear']
    return {
        'macro_forma_nel_pattern': (gruppo, [[gruppo, [100, y]], 1.0, 2]),
        'y_non_numerica': ([0, 'a'], [[[0, 'a'], [100, y]], 1.0, 2]),
        'y_booleana': ([0, True], [[[0, True], [100, y]], 1.0, 2]),
        'dict_v_non_numerica': (
            {'t': 0, 'v': 'a'}, [{'t': 0, 'v': 'a'}, [1.0, y]]),
    }


@pytest.mark.parametrize("difetto", list(_punti_non_piatti(0)))
@pytest.mark.parametrize("campo", list(SCALE_DELLE_Y))
def test_la_forma_sopravvive_alla_scala_delle_y(build, campo, difetto):
    """Stessa trappola della scala `normalized` sull'`end_time`: la scala delle
    y non deve moltiplicare cio' che non e' un numero. Una stringa o una lista
    per un float sono un TypeError nudo, che risale prima che il builder veda
    il corpo e ne nomini il campo; `True * 0.001` e' un float legittimo, e il
    guard sul `bool` varrebbe solo nell'unita' di default."""
    scrivi, y = SCALE_DELLE_Y[campo]
    punto, corpo = _punti_non_piatti(y)[difetto]

    with pytest.raises(InvalidFieldValueError) as exc:
        build(scrivi(corpo))

    assert exc.value.field == campo
    assert exc.value.stream_id == STREAM_ID
    assert exc.value.value == punto


# Le due scale che precedono il builder, con l'asse che scalano: `time_mode:
# normalized` moltiplica i tempi per la durata dello stream
# (`_scale_time_recursive`), `grain.duration_unit` e `pointer.loop_unit` i
# valori (`scale_raw_param_values`). Ogni riga: la chiave, il corpo sotto la
# scala, una y legale per la chiave.
SCALE = {
    'tempo-density': (
        'density', lambda c: {'time_mode': 'normalized', 'density': c}, 10),
    'tempo-deviation_probability': (
        'deviation_probability',
        lambda c: {'time_mode': 'normalized', 'deviation_probability': c}, 50),
    'valore-grain.duration': (
        'grain.duration',
        lambda c: {'grain': {'duration_unit': 'milliseconds', 'duration': c}},
        50),
    'valore-pointer.loop_dur': (
        'pointer.loop_dur',
        lambda c: {'pointer': {'loop_unit': 'normalized', 'loop_start': 0.1,
                               'loop_dur': c}},
        0.5),
}


def _breakpoint_malformati(y):
    """Breakpoint di una lista con un difetto, e il `value` che l'errore deve
    riportare: l'elemento com'e' scritto, non con l'altra coordinata scalata.
    E' la regola che `parse` si da' da solo (`scritto`), e una scala che
    moltiplica prima la aggira."""
    return {
        't_booleano': [True, y],
        't_booleano_dict': {'t': True, 'v': y},
        't_stringa_dict': {'t': 'x', 'v': y},
        'marcatore': [[0, y], 'marker'],
        'v_booleana_dict': {'t': 0.5, 'v': True},
        'v_stringa_dict': {'t': 0.5, 'v': 'a'},
    }


CASI_SCALATI = [
    pytest.param(ingresso, difetto, id=f'{ingresso}-{difetto}')
    for ingresso in SCALE
    for difetto in _breakpoint_malformati(0)
]


@pytest.mark.parametrize("ingresso, difetto", CASI_SCALATI)
def test_la_scala_tocca_solo_cio_che_il_builder_accetta(build, ingresso, difetto):
    """La regola di `_scale_compact` e di `_scale_y`, estesa all'elemento: una
    scala tocca un breakpoint solo se il builder lo accettera', e il resto gli
    arriva com'e' scritto. Sotto `normalized` i tempi si moltiplicavano a
    prescindere: `[true, v]` e `{t: true, v}` diventavano breakpoint legittimi
    e si rendevano, `{t: 'x', v}` e un marcatore `[[t, v], 'x']` risalivano
    come TypeError nudo. E dove la scala non esplodeva, il `value` dell'errore
    portava l'altra coordinata gia' scalata, cioe' un elemento che nel file
    non c'e'."""
    campo, scrivi, y = SCALE[ingresso]
    elemento = _breakpoint_malformati(y)[difetto]

    with pytest.raises(InvalidFieldValueError) as exc:
        build(scrivi([[0, y], elemento, [1.0, y]]))

    assert exc.value.field == campo
    assert exc.value.stream_id == STREAM_ID
    # `repr`, non `==`: `True == 1`, e `{'t': True} == {'t': 1.0}`.
    assert repr(exc.value.value) == repr(elemento)


def _gruppi_rifiutati(y):
    """Un BP group che il builder rifiutera' per arita', nelle due forme, e i
    punti come sono scritti: sono il `value` del suo errore."""
    punti = [[0.5, y]]
    gruppo = [punti, 'linear']
    return {
        'diretto': (gruppo, punti),
        'in_lista': ([[0, y], gruppo, [1.0, y]], punti),
    }


@pytest.mark.parametrize("forma", list(_gruppi_rifiutati(0)))
@pytest.mark.parametrize("ingresso", list(SCALE))
def test_la_scala_non_tocca_il_gruppo_che_il_builder_rifiuta(build, ingresso, forma):
    """La stessa regola per il BP group: l'errore di arita' riporta i punti del
    gruppo, e una scala che li moltiplicava prima faceva dire all'errore
    `[[1.0, 10]]` dove nel file c'e' `[[0.5, 10]]` (tempi sotto `normalized`),
    o `[[0.5, 0.05]]` dove c'e' `[[0.5, 50]]` (valori sotto
    `duration_unit: milliseconds`). Un gruppo con meno di 2 punti il builder
    lo rifiuta comunque: la scala non ha niente da preparargli."""
    campo, scrivi, y = SCALE[ingresso]
    corpo, punti = _gruppi_rifiutati(y)[forma]

    with pytest.raises(InvalidFieldValueError) as exc:
        build(scrivi(corpo))

    assert exc.value.field == campo
    assert exc.value.stream_id == STREAM_ID
    assert repr(exc.value.value) == repr(punti)


def test_end_time_sotto_normalized_dice_l_unita(build):
    """`end_time` contro l'istante di partenza e' l'unico confronto che non si
    puo' fare sul valore scritto: in una lista mista la partenza e' l'offset
    accumulato dagli elementi che precedono, e il builder li riceve gia'
    scalati. Con `time_mode: normalized` l'errore riporta quindi i due istanti
    in secondi — `0.6` e `1.0` su una durata di 2 s, dove nel file ci sono
    `0.3` e `0.5` — e l'hint deve dirlo, o sembrano numeri che il file non ha.
    """
    with pytest.raises(InvalidFieldValueError) as exc:
        build({'time_mode': 'normalized',
               'density': [[0, 10], [0.5, 10], [[[0, 1], [100, 2]], 0.3, 2]]})

    assert exc.value.field == 'density'
    assert exc.value.value == pytest.approx(0.6)
    assert 'time_mode: normalized' in exc.value.hint
