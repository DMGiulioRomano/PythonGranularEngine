"""
loop_unit.py

Il vocabolario di `pointer.loop_unit` (issue #222) e le chiavi del blocco
`pointer` che quell'unita' interpreta. Due tuple e nient'altro: il modulo non
importa niente, e sta qui per questo (issue #246).

Stavano in `controllers/pointer_controller.py`, che tira dentro
`pge.envelopes.envelope` e quindi numpy: la' nessuno le poteva importare. Le
legge PGE-ui, per dire mentre si scrive che una grafia il motore la rifiuta
invece di lasciarlo scoprire da un render che muore, e ne tengono un mirror
statico gl-ls e PGE-ls. Il bridge dell'editor continuera' a leggerle dal
sorgente — non importa mai il motore, per costruzione — ma legge un modulo che
esiste per essere letto, e il suo oracolo di parita' ora le importa.

Per lo stesso motivo le due tuple vanno scritte come **letterali**: chi legge
da fuori lo fa con `ast`, risolve i nomi di un livello e dentro lo stesso file,
e un valore calcolato gli torna come "non lo so".
"""
from __future__ import annotations

# Vocabolario di 'loop_unit' (issue #222). Fuori di qui e' un errore.
#
# 'seconds' e' la grafia canonica — allinea loop_unit a grain.duration_unit,
# l'unita' nata «sul modello di loop_unit» (CHANGELOG v5.1.0) — e 'absolute'
# l'alias storico, quello che i config e la reference hanno sempre scritto.
# Sono la stessa lettura: valori gia' in secondi assoluti, nessuna conversione.
#
# L'ordine conta per chi legge: la prima grafia e' quella canonica, ed e'
# quella che il selettore dell'editor scrive. Una tupla, non un insieme.
LOOP_UNITS = ('seconds', 'absolute', 'normalized')

# Le chiavi del blocco pointer che 'loop_unit' interpreta. 'start' e' fra
# queste benche' loop non sia: e' una posizione nel sample come loop_start,
# stesso dominio e stessa unita' (reference §10.1), e sopravvive al loop.
#
# Pubblica senza underscore dalla #246: PGE-ui decide da questo elenco se
# mostrare il selettore dell'unita' (`loopUnitRescaleKeys`) e gl-ls lo mirrora
# in `diagnostics._UNIT_SCALED`. Era privata di nome e non di fatto.
LOOP_UNIT_SCOPE = ('start', 'loop_start', 'loop_end', 'loop_dur')
