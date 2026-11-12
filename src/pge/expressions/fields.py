"""
fields.py

I campi YAML in cui un'espressione vale come valore, e quelli in cui il
motore la rifiuta con un suggerimento (issue #308, #313).

Letterali in un modulo che non importa niente: chi legge il motore dal
sorgente (un language server, un editor) li trova qui, e sa dove una stringa
fra parentesi che nomina una mappa e' un valore e dove resta un errore.

Ogni voce e' il path YAML dentro lo stream.
"""

EXPRESSION_FIELDS = (
    'grain.duration', 'grain.iot', 'pointer.position',
    'volume', 'pan',
    'pitch.semitones', 'pitch.cents', 'pitch.quarter_tone',
    'pitch.eighth_tone', 'pitch.ratio', 'pitch.value',
    'density', 'fill_factor', 'distribution',
    'grain.read_direction',
)
"""Dove un'espressione vale: il **valore base** di ogni parametro a schema.

`pitch.<unita'>` e' il valore del pitch nell'unita' scritta; `pitch.value` e'
quello di `edo: N`. Non le bande `_range`, non `deviation_probability`, non
`voices.scatter` ne' i parametri delle strategie di voce: li' una stringa
resta un errore, che dice dove le espressioni valgono.
"""

EXPRESSION_REFUSALS = {
    'pointer.speed_ratio': (
        "la velocita' si integra nel tempo per ricavare la posizione, e "
        "un'espressione non si integra: per leggere la posizione da una "
        "mappa usa pointer.position"),
    'pointer.start': (
        "e' la posizione di partenza, un numero: per una posizione che "
        "cambia a ogni grano usa pointer.position"),
    'pointer.loop_start': (
        "i bordi della finestra di loop sono numeri o envelope: la finestra "
        "e' il vincolo del puntatore. La mappa muove la posizione dentro la "
        "finestra, con pointer.position"),
    'pointer.loop_end': (
        "i bordi della finestra di loop sono numeri o envelope: la finestra "
        "e' il vincolo del puntatore. La mappa muove la posizione dentro la "
        "finestra, con pointer.position"),
    'pointer.loop_dur': (
        "i bordi della finestra di loop sono numeri o envelope: la finestra "
        "e' il vincolo del puntatore. La mappa muove la posizione dentro la "
        "finestra, con pointer.position"),
    'voices.num_voices': (
        "il numero di voci si decide prima dei grani (e' il picco del suo "
        "envelope): un numero o un envelope. Una mappa puo' muovere volume, "
        "pan e pitch, e ogni voce ha il suo stato"),
}
"""Dove un'espressione NON vale, e che cosa scrivere al suo posto: path YAML
-> suggerimento. Sono i campi in cui ci si aspetterebbe di poterla scrivere;
ogni altro campo fuori da `EXPRESSION_FIELDS` la rifiuta lo stesso, col
suggerimento generico."""
