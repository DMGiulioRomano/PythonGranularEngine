"""
magnify_spec.py

La grammatica di `--magnify-at`: il vocabolario delle chiavi di un target e il
parser dello SPEC. Non dipende da niente — ne' da una terza parte, ne' da
un'altra riga del motore — e sta qui per questo (issue #246).

Stava dentro `pge/cli.py`, dove nessuno la poteva importare: `import pge.cli`
tira dentro `ScoreVisualizer` (matplotlib) e `Generator` (numpy, via
`core.stream`). L'oracolo di parita' di PGE-ui, che gira su un runner senza il
venv del motore, era percio' costretto a cercare questi quattro nodi nell'AST
di `cli.py` e a eseguirli — una lettura che pinnava i loro nomi privati e la
loro posizione nel file, cosi' che una rinomina qui rendeva rossa la CI di un
altro repository. Importabili, la deroga non serve piu'.

**Il comportamento e' quello della CLI, non e' cambiato.** Un rifiuto stampa su
stdout ed esce con 1: non alza. Quei cinque messaggi sono interfaccia
(`CLASSIFICAZIONE` in `tests/shared/test_stdout_contract.py`) e il mirror JS
dell'editor li anticipa mentre si scrive nel popover del render, con la parita'
che confronta le due risposte sullo stesso corpus. Trasformarli in eccezioni
sarebbe una modifica della superficie osservabile, non uno spostamento.
"""
from __future__ import annotations

import sys

# Chiavi ammesse in un target di --magnify-at. Numeriche (float) e stringa.
MAGNIFY_NUMERIC_KEYS = frozenset({'t', 'y', 'zoom', 'out', 'src'})
MAGNIFY_STR_KEYS = frozenset({'stream'})
MAGNIFY_KEYS = MAGNIFY_NUMERIC_KEYS | MAGNIFY_STR_KEYS


def parse_magnify_spec(spec):
    """Parsa lo SPEC di --magnify-at in una lista di target dict.

    SPEC = target separati da ';'; ogni target = coppie chiave=valore separate
    da ','. La chiave 't' (tempo in secondi) e' obbligatoria; opzionali y, zoom,
    out, src (float) e stream (stringa). Come --plot-envelopes, la validazione
    e' sempre attiva: token malformato, chiave ignota, valore non numerico o 't'
    mancante stampano un messaggio su stdout ed escono con codice 1.
    """
    targets = []
    for raw in spec.split(';'):
        raw = raw.strip()
        if not raw:
            continue
        target = {}
        for pair in raw.split(','):
            pair = pair.strip()
            if not pair:
                continue
            if '=' not in pair:
                print(f"--magnify-at: token non valido '{pair}'. "
                      f"Usa chiave=valore (es. t=14,zoom=10).")
                sys.exit(1)
            key, _, value = pair.partition('=')
            key, value = key.strip(), value.strip()
            if key not in MAGNIFY_KEYS:
                print(f"--magnify-at: chiave ignota '{key}'. "
                      f"Valide: {', '.join(sorted(MAGNIFY_KEYS))}.")
                sys.exit(1)
            if key in MAGNIFY_NUMERIC_KEYS:
                try:
                    target[key] = float(value)
                except ValueError:
                    print(f"--magnify-at: valore non numerico per '{key}': '{value}'.")
                    sys.exit(1)
            else:
                target[key] = value
        if 't' not in target:
            print("--magnify-at: ogni target richiede la chiave 't' (tempo in secondi).")
            sys.exit(1)
        targets.append(target)
    if not targets:
        print("--magnify-at: nessun target valido nello SPEC.")
        sys.exit(1)
    return targets
