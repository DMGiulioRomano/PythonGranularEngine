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
