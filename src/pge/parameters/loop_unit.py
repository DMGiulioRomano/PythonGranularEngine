"""
loop_unit.py

Il vocabolario di `pointer.loop_unit` (issue #222) e le chiavi del blocco
`pointer` che quell'unita' interpreta. Due tuple e nient'altro: il modulo non
importa niente, e sta qui per questo (issue #246).

Stavano in `controllers/pointer_controller.py`. Quel modulo oggi si importa
senza terze parti — `Envelope`, l'orchestratore, `StreamConfig` e il logger
usano la sola stdlib — ma per caso e non per contratto: nessuna guardia lo
sorveglia, e la prima dipendenza pesante che scendesse da li' lo renderebbe
illeggibile a chi non ha il venv del motore. Questo modulo non importa niente,
e `_MODULI_SENZA_TERZE_PARTI` lo misura.

Chi le legge lo fa dal **sorgente**, al path: il bridge di PGE-ui (che non
importa mai il motore, per costruzione) le usa per dire mentre si scrive che
una grafia il motore la rifiuta, invece di lasciarlo scoprire da un render che
muore, e i patti di parita' di PGE-ls rileggono tutte e due le tuple per il
mirror statico del language server. gl-ls ne tiene un mirror statico a sua
volta. Il path e la forma letterale sono quindi parte del contratto, e
`tests/parameters/test_loop_unit.py` li tiene fermi.

Per lo stesso motivo le due tuple vanno scritte come **letterali**: chi legge
da fuori lo fa con `ast`, risolve al piu' i nomi di un livello e dentro lo
stesso file, e un valore calcolato gli torna come "non lo so".
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
# Pubblica senza underscore dalla #246: PGE-ls la rilegge da qui nei suoi patti
# di parita', gl-ls la mirrora in `diagnostics._UNIT_SCALED` e PGE-ui in
# `loopUnitRescaleKeys`, che decide se mostrare il selettore dell'unita'. Era
# privata di nome e non di fatto.
LOOP_UNIT_SCOPE = ('start', 'loop_start', 'loop_end', 'loop_dur')
