#!/usr/bin/env python3
"""
Genera i sample di prova che i test end-to-end si aspettano in refs/.

I .wav sono gitignorati: un checkout fresco ha `refs/` vuoto, e gli e2e che
citano `pino.wav` nel proprio YAML falliscono dentro un `make` con un errore
che non nomina la causa vera. La CI non se ne accorgeva perche' se lo generava
da se' con `sox` -- cioe' la definizione del sample viveva in una riga del
workflow, fuori dal repo, e chi lavorava in locale non l'aveva.

Idempotente: un file gia' presente non viene toccato. Chi ha in `refs/` il
proprio materiale (il `pino.wav` vero, che non e' una sinusoide) non se lo
vede sovrascritto lanciando i test.

    python3 utils/make_test_samples.py           # crea cio' che manca
    python3 utils/make_test_samples.py --force   # rigenera comunque

Usato da `make test-samples`, che e' un prerequisito di `make e2e-tests`.
"""
import argparse
import os
import sys

# 3 secondi di sinusoide a 440 Hz: gli stessi che la CI generava con
# `sox -n refs/pino.wav synth 3 sine 440`. Gli e2e non guardano il contenuto
# -- vogliono un file audio leggibile, di durata nota -- ma la durata entra
# nel fingerprint della cache degli stream senza `duration` (#205), quindi
# cambiarla non e' gratis.
SAMPLES = {
    'pino.wav': dict(freq=440.0, dur=3.0, sr=48000),
}


def genera(path, *, freq, dur, sr):
    import numpy as np
    import soundfile as sf

    t = np.arange(int(dur * sr)) / sr
    audio = 0.5 * np.sin(2 * np.pi * freq * t)
    sf.write(path, audio.astype('float32'), sr, subtype='PCM_16')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refs-dir', default='refs',
                        help="directory dei sample (default: refs)")
    parser.add_argument('--force', action='store_true',
                        help="rigenera anche i file gia' presenti")
    args = parser.parse_args(argv)

    os.makedirs(args.refs_dir, exist_ok=True)
    for nome, spec in SAMPLES.items():
        path = os.path.join(args.refs_dir, nome)
        if os.path.exists(path) and not args.force:
            print(f"[samples] {path} c'e' gia', non lo tocco")
            continue
        genera(path, **spec)
        print(f"[samples] {path}: {spec['dur']}s a {spec['freq']} Hz, "
              f"{spec['sr']} Hz")
    return 0


if __name__ == '__main__':
    sys.exit(main())
