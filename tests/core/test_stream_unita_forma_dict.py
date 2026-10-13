"""
test_stream_unita_forma_dict.py

La forma dict `{type, points}` si legge nell'unita' dichiarata come la lista
nuda (issue #289), attraverso lo Stream vero.

`scale_raw_param_values` porta le y nell'unita' del motore prima che il corpo
arrivi al builder: `grain.duration_unit` su `grain.duration` e sul
`grain.duration_range` assoluto, `loop_unit: normalized` su `loop_start`,
`loop_end` e `loop_dur`. Sulla lista nuda riconosceva il compatto e il BP group
diretti; nella forma dict passava `points` a una scansione elemento per
elemento, dove il pattern del compatto, `end_time` e `n_reps` non sono
breakpoint e restavano com'erano. Il corpo arrivava al builder nell'unita'
dello YAML e il motore lo leggeva in secondi: sotto `loop_unit` il loop era un
altro, in silenzio; sotto `duration_unit` il render moriva su un bound violato
da valori legali nell'unita' dichiarata.

La domanda e' una sola, e si fa allo Stream: lo stesso corpo, scritto nudo o
dentro `{type: linear, points: ...}`, deve dare la stessa curva — e quella
curva deve essere nell'unita' del motore, non in quella del file.
"""

import numpy as np
import pytest
import soundfile as sf

from pge.core.stream import Stream
from pge.parameters.parameter_curve import VARYING

SR = 48000

# Due secondi e non uno: sotto `loop_unit: normalized` il fattore e' la durata
# del sample, e con un sample di un secondo la scala dimenticata e quella
# applicata danno gli stessi numeri.
DURATA_SAMPLE = 2.0


@pytest.fixture
def build(tmp_path):
    """Stream vero attraverso __init__, con un sample silenzioso di 2 s."""
    sf.write(str(tmp_path / 'tone.wav'),
             np.zeros(int(SR * DURATA_SAMPLE), dtype='float32'), SR)

    def _build(extra):
        params = {
            'stream_id': 'stream_unita',
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


# Ogni riga: come si scrive il corpo sotto la sua unita' non di default, quale
# faccia dello Stream lo legge, due y legali nell'unita' dichiarata e il fattore
# che le porta nell'unita' del motore.
CHIAVI = {
    'pointer.loop_start': (
        lambda c: {'pointer': {'loop_unit': 'normalized', 'loop_start': c,
                               'loop_dur': 0.1}},
        lambda s: s.loop_start.value_curve,
        (0.1, 0.2), DURATA_SAMPLE),
    'pointer.loop_end': (
        lambda c: {'pointer': {'loop_unit': 'normalized', 'loop_start': 0.0,
                               'loop_end': c}},
        lambda s: s.loop_end.value_curve,
        (0.5, 0.6), DURATA_SAMPLE),
    'pointer.loop_dur': (
        lambda c: {'pointer': {'loop_unit': 'normalized', 'loop_start': 0.0,
                               'loop_dur': c}},
        lambda s: s.loop_dur.value_curve,
        (0.2, 0.3), DURATA_SAMPLE),
    'grain.duration': (
        lambda c: {'grain': {'duration_unit': 'milliseconds', 'duration': c}},
        lambda s: s.grain_duration.value_curve,
        (50, 60), 1e-3),
    'grain.duration_range': (
        lambda c: {'grain': {'duration_unit': 'milliseconds', 'duration': 50,
                             'duration_range': c}},
        lambda s: s.grain_duration.range_curve,
        (5, 10), 1e-3),
}

# Le due forme dirette che la scansione elemento per elemento non vede: il
# compatto (due cicli in un secondo) e il BP group.
FORME = {
    'compatto': lambda a, b: [[[0, a], [100, b]], 1.0, 2],
    'bp_group': lambda a, b: [[[0, a], [1, b]], 'cubic'],
}

ISTANTI = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5)


def _curva(build, campo, corpo):
    scrivi, leggi, _, _ = CHIAVI[campo]
    curva = leggi(build(scrivi(corpo)))
    assert curva.kind == VARYING, f"{campo}: la curva non e' un envelope"
    return curva.envelope


@pytest.mark.parametrize("forma", list(FORME))
@pytest.mark.parametrize("campo", list(CHIAVI))
def test_la_forma_dict_si_legge_come_la_lista_nuda(build, campo, forma):
    _, _, (a, b), fattore = CHIAVI[campo]
    corpo = FORME[forma](a, b)

    nuda = _curva(build, campo, corpo)
    in_dict = _curva(build, campo, {'type': 'linear', 'points': corpo})

    for t in ISTANTI:
        assert in_dict.evaluate(t) == pytest.approx(nuda.evaluate(t)), (
            f"{campo} ({forma}) a t={t}: la forma dict vale "
            f"{in_dict.evaluate(t)}, la lista nuda {nuda.evaluate(t)}")
    # E la curva e' nell'unita' del motore: senza, le due forme potrebbero
    # concordare perche' nessuna delle due e' stata scalata.
    assert nuda.evaluate(0.0) == pytest.approx(a * fattore)
