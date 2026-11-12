"""
Gli stream senza mappe di cui `fixtures/curve_senza_mappe.json` fissa le
curve (issue #314): li usano il test che confronta e lo script che ha preso
l'istantanea. Non e' un file di test: non comincia con `test_`.
"""
import numpy as np
import soundfile as sf

from pge.core.stream import Stream
from pge.rendering.envelope_extractor import get_stream_envelopes

SAMPLE = 'due_secondi.wav'

CASI = {
    'envelope_ovunque': {
        'density': [[0, 5], [2, 20]],
        'distribution': [[0, 0], [2, 1]],
        'volume': [[0, -12], [2, -3]], 'volume_range': [[0, 0], [2, 6]],
        'pan': [[0, -45], [2, 45]], 'pan_range': 20,
        'deviation_probability': [[0, 10], [2, 80]],
        'pitch': {'semitones': [[0, 0], [2, 12]], 'range': [[0, 0], [2, 2]]},
        'grain': {'duration': [[0, 0.02], [2, 0.08]],
                  'duration_range': [[0, 0], [2, 0.01]],
                  'envelope': 'hanning'},
        'pointer': {'speed_ratio': [[0, 0.5], [2, 2]],
                    'offset_range': [[0, 0], [2, 0.3]],
                    'loop_start': [[0, 0.1], [2, 0.6]],
                    'loop_dur': [[0, 0.3], [2, 0.1]]},
    },
    'fill_factor_e_voci': {
        'fill_factor': [[0, 1], [2, 6]],
        'grain': {'duration': [[0, 0.03], [2, 0.09]], 'envelope': 'hanning',
                  'read_direction': [[0, 1], [1, -1]]},
        'deviation_probability': {'read_direction': [[0, 0], [2, 50]]},
        'voices': {'num_voices': [[0, 1], [2, 3]],
                   'scatter': [[0, 0], [2, 1]],
                   'pitch': {'strategy': 'step', 'step': [[0, 0], [2, 7]]},
                   'pointer': {'strategy': 'linear',
                               'step': [[0, 0], [2, 0.2]]}},
    },
    'tutto_statico': {
        'density': 12, 'volume': -6, 'pan': 10,
        'pitch': {'ratio': 1.5},
        'pointer': {'speed_ratio': 0.7, 'loop_start': 0.2, 'loop_end': 0.9},
    },
}


def scrivi_sample(cartella):
    sf.write(f'{cartella}/{SAMPLE}', np.zeros(96000, dtype='float32'), 48000)


def stream(nome, samples_dir):
    params = {'stream_id': 's1', 'onset': 0.5, 'duration': 2.0,
              'sample': SAMPLE,
              'grain': {'duration': 0.05, 'envelope': 'hanning'}}
    params.update(CASI[nome])
    s = Stream(params, seed=1441, samples_dir=samples_dir)
    s.sample_table_num = 1
    s.window_table_map = {'hanning': 2}
    return s


def curve(nome, samples_dir):
    """`[nome, tipo, breakpoint]` di ogni curva, nell'ordine in cui esce,
    con tutto acceso: costanti e offset per voce compresi."""
    estratte = get_stream_envelopes(
        stream(nome, samples_dir), show_static=True, show_voice_offsets=True)
    return [[chiave, env.type, [list(bp) for bp in env.breakpoints]]
            for chiave, env in estratte.items()]
