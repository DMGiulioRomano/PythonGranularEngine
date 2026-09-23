---
slug: strategy-registry
type: explanation
status: stable
tags: [strategy, registry, refactor, estensibilita, architecture]
sources:
  - src/pge/strategies/registry.py
  - src/pge/strategies/voice_pitch_strategy.py
  - src/pge/strategies/voice_onset_strategy.py
  - src/pge/strategies/voice_pointer_strategy.py
  - src/pge/strategies/voice_pan_strategy.py
  - src/pge/strategies/strategy_registry.py
  - src/pge/strategies/variation_registry.py
  - src/pge/strategies/grain_clip_strategy.py
  - src/pge/controllers/window_selection_strategy.py
  - src/pge/shared/distribution_strategy.py
  - src/pge/envelopes/envelope_factory.py
  - src/pge/core/stream.py
  - src/pge/parameters/parameter.py
  - src/pge/shared/exceptions.py
  - src/pge/shared/logger.py
  - tests/shared/test_diagnostic_logger.py
  - tests/shared/test_distribution_strategy.py
  - tests/shared/test_range_anchor.py
  - tests/shared/test_stdout_contract.py
  - tests/strategies/test_misc_strategy_errors.py
  - tests/strategies/test_registry.py
  - tests/strategies/test_registry_convergenza.py
  - tests/strategies/test_registry_errors.py
  - tests/strategies/test_strategies.py
  - tests/strategies/test_variation_registry.py
  - tests/strategies/test_voice_pan_strategy.py
  - tests/test_minimum_python_syntax.py
  - pyproject.toml
last_synced_commit: dc97880
---

# Il registry generico delle strategy — la forma decisa

**Documenti collegati:** [[INDEX]] · [[architecture]] · [[multi-voice]] · [[contratto-stdout]] · [[add-voice-strategy]] · [[add-variation-strategy]]

Questo documento è l'esito della issue #177: la **decisione** su che forma prende
il registry generico, non la sua esecuzione. L'esecuzione è #184 (tracer bullet)
e #185 (le altre).

**Stato: il tracer bullet è stato sparato, la forma ha retto, e la replica è
fatta.** La #184 ha messo la classe in `src/pge/strategies/registry.py` e vi ha
cablato `voice_pan_strategy`; la #185 ci ha portato altri cinque registry
(pitch, onset, pointer, density, variation), e i **tre** che restano sono
quelli che questo documento tiene fuori per ragioni loro — `window_selection`
e `grain_clip` (#265), `distribution` dopo la decisione sulla validazione.
Nessun caso speciale è servito per farla passare, né al tracer bullet né alla
replica — che era la domanda a cui il tracer bullet doveva rispondere. Quel che segue descrive la forma e, per ogni
scelta, il vincolo che l'ha decisa; dove #184 ha *aggiunto* qualcosa alla
decisione — la misura eseguibile dello scheletro, il criterio della guardia —
è detto sul posto.

---

## Problema

Lo stesso schema — una mappa nome → classe, un punto di registrazione, una
classe `Factory` il cui `create()` fa lookup e alza `StrategyNotFoundError` —
è ripetuto in **nove** moduli, non sei. La #177 ne elenca sei perché guarda
`strategies/`; il criterio però non è la cartella, è la forma, e applicato
davvero arriva a nove: il criterio operativo è il `raise
StrategyNotFoundError(strategy_kind=…)` dentro `create()`, che nell'albero ha
esattamente nove siti.

**La tabella fotografa lo stato prima di #184/#185**, che è il suo mestiere:
è il problema come lo si è trovato. Le due righe `↳` dicono dove è arrivato.
Dopo #185 quei nove siti sono **quattro** — `window_selection_strategy`,
`grain_clip_strategy`, `distribution_strategy` e `StrategyRegistry.create`,
l'ultimo dei quali serve sei registry.

| modulo | mappa | registrazione | riga diagnostica | `create()` |
|---|---|---|---|---|
| `strategies/voice_pitch_strategy.py` | `VOICE_PITCH_STRATEGIES` | `(name, cls)` | no | `create(name, **kwargs)` |
| `strategies/voice_onset_strategy.py` | `VOICE_ONSET_STRATEGIES` | `(name, cls)` | no | `create(name, **kwargs)` |
| `strategies/voice_pointer_strategy.py` | `VOICE_POINTER_STRATEGIES` | `(name, cls)` | no | `create(name, **kwargs)` |
| `strategies/voice_pan_strategy.py` | `VOICE_PAN_STRATEGIES` | `(name, strategy_class)` | sì, dominio `'pan voce'` | `create(strategy_name, **kwargs)` |
| ↳ *dopo #184* | `StrategyRegistry('voice_pan', …)` | delega a `.register` | sì, dominio `voice_pan` | `create(name, **kwargs)`, delega |
| `strategies/strategy_registry.py` | `DENSITY_STRATEGIES` | `(param_name, strategy_class)` | sì, dominio `'density'` | `create_density_strategy(selected_param_name, param_obj, all_params)` |
| `strategies/variation_registry.py` | `VARIATION_STRATEGIES` | `(mode_name, strategy_class)` | sì, dominio `'variation'` | `create(variation_mode)` |
| ↳ *dopo #185* (pitch, onset, pointer, density, variation) | `StrategyRegistry('<kind>', …)` | `(name, strategy_class)`, delega a `.register` | sì, dominio `<kind>` | delega a `.create`; density tiene la propria façade e la propria validazione |
| `controllers/window_selection_strategy.py` | `WINDOW_STRATEGY_REGISTRY` | `(name, cls)` | no | `create(name, **kwargs)` + `from_spec(...)` |
| `strategies/grain_clip_strategy.py` | `GRAIN_CLIP_STRATEGIES` | — | — | `create(name, **kwargs)` |
| `shared/distribution_strategy.py` | `DistributionFactory._registry` (attributo di classe) | `DistributionFactory.register(name, strategy_class)`, classmethod, **valida** | no | `create(mode, rng=None, anchor=…)` |

La tabella è la prova che si tratta di duplicazione e non di somiglianza: per
una cosa sola — «registra una classe sotto un nome» — ci sono tre parole per il
primo parametro (`name`, `param_name`, `mode_name`), due per il secondo (`cls`,
`strategy_class`), tre convenzioni per il nome della mappa
(`*_STRATEGIES`, `WINDOW_STRATEGY_REGISTRY` e un `_registry` privato di classe),
tre etichette di dominio scritte a mano sulla riga diagnostica e nove sul
`strategy_kind` dell'errore, un registry che non ha nemmeno il punto di
registrazione e uno che il punto di registrazione ce l'ha ma **valida**.

**L'ultima riga è quella che il censimento per cartella non poteva vedere, ed è
la più istruttiva delle nove.** `DistributionFactory` (`shared/`) tiene la
mappa come attributo di classe invece che come nome di modulo e registra con
una classmethod `register`, non con una `def register_*_strategy`: due
differenze di grafia che la fanno sparire da entrambe le grate con cui si
guarda di solito — la cartella `strategies/` e il nome della funzione. Per
forma è però della famiglia più di `grain_clip`, che nel conto c'è: alza lo
stesso `StrategyNotFoundError` con lo stesso `strategy_kind`, e un punto di
registrazione ce l'ha. Torna due volte più sotto, perché è il **contro-esempio
vivo** a due decisioni di questo documento: è l'unico registry dell'albero che
valida alla registrazione (§ «`base` è portato, non imposto»), ed è il secondo
punto di registrazione fuori dal campo visivo delle guardie della #187
(§ «Il `print()`»).

**Un punto della #177 è già stato sciolto altrove, e conviene arrivarci
sapendolo.** Il `print()` alla registrazione non esiste più: la #187 lo ha
portato a `log_strategy_registration`, cioè al logger `pge.diagnostics`, e la
regola di quale riga vive su stdout è scritta in [[contratto-stdout]]. Quel che
resta della divergenza descritta dalla issue non è il canale, è **chi la riga la
emette**: tre registry su nove la emettono, cinque tacciono, uno non ha la
funzione da cui emetterla. Quel conto è la fotografia del prima, come la
tabella qui sotto: dopo #185 i registry che parlano sono sei, **due**
tacciono (`window` e `distribution`) e uno non ha ancora la funzione
(`grain_clip`) — il conto a convergenza avvenuta è nella sezione «Il
`print()`», che lo tiene aggiornato. I due che tacciono non tacciono per la
stessa ragione, ed è la sezione «Chi resta fuori» a dirlo: `window` è nel
seguito (#265), `DistributionFactory.register` è ferma davanti alla decisione
sulla validazione. Contarne uno solo faceva nove registri su otto, e mandava a
cercare in `distribution` una riga che non c'è.

Due vincoli esterni rendono questa duplicazione più cara di quanto sembri, e
sono ciò che decide la forma più di ogni preferenza di stile:

- **Cinque nomi di modulo sono superficie pinnata, e solo cinque.**
  `tests/test_pge_parity.py` di PGE-ls importa dai moduli del motore
  `VOICE_PITCH_STRATEGIES`, `VOICE_ONSET_STRATEGIES`,
  `VOICE_POINTER_STRATEGIES`, `VOICE_PAN_STRATEGIES` e `CHORD_INTERVALS`, e ne
  confronta le chiavi con il proprio registro statico: spostare o rinominare
  una di quelle cinque rende rossa la CI di un altro repository senza far
  fallire un test di PGE — quando quella CI il motore ce l'ha, perché il
  checkout è condizionato a un secret e senza di esso la parità skippa in
  verde (#269). Le altre quattro mappe (density, variation, window,
  grain_clip) nessuno le importa da fuori, e nemmeno i `register_*`, le
  `Factory` o `SEMITONE_LOCKED` — di quest'ultima PGE-ls tiene una copia a mano
  (`SEMITONE_LOCKED_STRATEGIES` in `granular_ls/pitch_units.py`), che un rename
  qui per definizione non tocca: resta indietro in silenzio invece di gridare.
  È la stessa *classe* di esposizione che inventaria la #246, non la stessa
  esposizione — quell'issue elenca ciò che importa l'harness di parità di
  **PGE-ui**, e fra i suoi moduli non compare nessuna di queste mappe. Il
  censimento dell'esposizione PGE-ls, che al momento di scrivere questa
  decisione non esisteva, è la #269.
- **La guardia sulla diagnostica è derivata dai sorgenti.**
  `tests/shared/test_stdout_contract.py` cerca con `ast` le `def
  register_*_strategy` di livello modulo, pretende che l'insieme dei moduli che
  ne contengono una sia *esattamente* quello dichiarato, e che nessuna di quelle
  funzioni stampi. Il refactor passa dentro quella guardia, e conviene sapere
  in che modo: una forma che facesse sparire quelle `def` non la spegnerebbe —
  il censimento pretende `trovati == dichiarati`, quindi diventa rosso subito.
  A spegnersi in silenzio è la *copertura*, un passo dopo: riallineata la
  lista dichiarata per tornare verdi, la guardia per funzione non sorveglia
  più niente. È la differenza su cui gira tutta la sezione «Il `print()`».
  Da quando questa decisione è stata scritta quella guardia non è più sola:
  la #266 le ha messo accanto un censimento delle `print()` di **tutto**
  `src/pge/` (`test_ogni_print_di_src_pge_e_classificato`), che di ciascuna
  pretende una voce in `CLASSIFICAZIONE` invece di vietarla. Vede quindi
  anche la classe generica, ovunque la si collochi — ma vedere e proibire
  non sono la stessa cosa, e la differenza è misurata in quella sezione.

## Modello

### La forma

Una classe generica che **è** la mappa, in un modulo nuovo
`src/pge/strategies/registry.py`:

```python
from __future__ import annotations

from typing import Dict, Type, TypeVar

from pge.shared.exceptions import StrategyNotFoundError
from pge.shared.logger import log_strategy_registration

S = TypeVar("S")


class StrategyRegistry(Dict[str, Type[S]]):
    """Mappa nome -> classe strategy che conosce il proprio dominio."""

    def __init__(self, kind: str, base: Type[S],
                 initial: Dict[str, Type[S]] | None = None):
        super().__init__(initial or {})
        self.kind = kind
        self.base = base

    def register(self, name: str, strategy_class: Type[S]) -> None:
        self[name] = strategy_class
        log_strategy_registration(self.kind, name, strategy_class)

    def create(self, name: str, *args, **kwargs) -> S:
        if name not in self:
            raise StrategyNotFoundError(
                strategy_kind=self.kind,
                name=name,
                available=list(self.keys()),
            )
        return self[name](*args, **kwargs)
```

**La prima riga non è un ornamento**, ed è la ragione per cui sta nello
scheletro invece di essere lasciata all'esecuzione: `Dict[str, Type[S]] | None`
è un'annotazione di *firma*, quindi l'interprete la valuta alla `def`, e sulla
3.9 — il minimo che `pyproject.toml` dichiara — un PEP 604 valutato alza
`TypeError` in import. Il modulo non fallirebbe un test: smetterebbe di
esistere, e con lui la classe che tutti gli altri importano. È il difetto che
la #257 ha pagato per davvero e che ora `tests/test_minimum_python_syntax.py`
sorveglia su `src/`; ogni modulo di `src/pge/` porta quell'import (misurato), e
il nuovo non fa eccezione. La base `Dict[str, Type[S]]` invece non è
un'annotazione e si valuta comunque: è legale sulla 3.9 perché viene da
`typing`, e lo sarebbe anche scritta `dict[str, Type[S]]`, dato che PEP 585
c'è dalla 3.9. Solo PEP 604 è il problema.

Ogni modulo conserva tre cose e nient'altro:

```python
VOICE_PAN_STRATEGIES = StrategyRegistry('voice_pan', VoicePanStrategy, {
    'range': RangePanStrategy,
    'stochastic': StochasticPanStrategy,
    'step': StepPanStrategy,
})


def register_voice_pan_strategy(name, strategy_class):
    """<docstring con l'esempio di estensione, invariata>"""
    VOICE_PAN_STRATEGIES.register(name, strategy_class)


class VoicePanStrategyFactory:
    @staticmethod
    def create(name: str, **kwargs) -> VoicePanStrategy:
        return VOICE_PAN_STRATEGIES.create(name, **kwargs)
```

### Perché una classe e non funzioni di modulo che chiudono su un dizionario

È la domanda 1 della #177, e a deciderla non è il gusto: è che **il dizionario
deve restare raggiungibile e mutabile sotto il suo nome di modulo**. I test di
oggi lo trattano come tale — `isinstance(registry, dict)`, `dict(registry)` per
lo snapshot della fixture, `registry.clear()` e `registry.update()` per il
ripristino, `del registry[k]` e `registry.pop(k, None)` per il cleanup — e la
parità di PGE-ls ne legge le chiavi. Con delle closure il dizionario resterebbe
comunque fuori, esposto e separato dalle funzioni che lo governano: si
riscriverebbe la duplicazione di oggi, spostata di due righe. Una classe che
eredita da `dict` è invece un solo oggetto che soddisfa tutta quella superficie
e in più sa il proprio dominio.

Lo scheletro qui sopra è stato **misurato** contro quei vincoli fuori albero,
non solo argomentato: `isinstance(..., dict)`, il giro
`dict()`/`clear()`/`update()` della fixture di pan, `del`/`pop`, la riga
diagnostica che arriva a `pge.diagnostics` e non a stdout,
`StrategyNotFoundError` con `strategy_kind`/`name`/`available`, e le tre forme
di costruzione (`**kwargs` per pan, due posizionali per density, nessun
argomento per variation). Il codice che li misura vive in #184, dove è
diventato test: `tests/strategies/test_registry.py` interroga la classe da
sola — non attraverso pan — perché è la classe che gli altri otto registry
erediteranno, e perché due costi *dichiarati* vanno pinnati come tali e non
lasciati alla prosa: `copy()` restituisce un `dict` spoglio, e
`registry[name] = strategy_class` resta una registrazione legale e muta.

### Il dominio alla costruzione (domanda 2)

Alla costruzione. Il dominio non è un dato della chiamata, è una proprietà del
registry: `create()` non ha modo di sbagliarlo e nessun chiamante deve
ripeterlo. Ha due grafie e vanno tenute entrambe anche in #184: `kind` come
parametro del costruttore, `strategy_kind` come parola chiave di
`StrategyNotFoundError` — la seconda è superficie dell'eccezione e il nome che
porta oggi, la prima no. Il valore è già quello che l'errore riporta
(`voice_pan`, `density`, `variation`, …), quindi **i messaggi d'errore non
cambiano** — verificato che nessuno, in PGE-ui o PGE-ls, li parsi.

Lo stesso `kind` diventa anche il dominio della riga diagnostica, e questo
uniforma le tre etichette scritte a mano: `'pan voce'` diventa `voice_pan`.

**Quell'etichetta non è sorvegliata da nessun test, e crederla sorvegliata è il
modo di sbagliare il rename.** La lettura naturale di
`test_register_logs_instead_of_printing` è che `assert 'pan' in messaggi[0]`
pinni il dominio — e resti verde perché `voice_pan` contiene `pan`. Misurato,
non è così: il test registra la strategy sotto la chiave `'logged_pan'` e la
riga successiva asserisce `'logged_pan' in messaggi[0]`, quindi è **il nome
registrato** a soddisfare anche la prima asserzione. Sostituendo il dominio del
modulo con `'XYZ_dominio_sbagliato'` l'intera suite resta verde (`make tests`:
6905 passed, 18 skipped): la prima asserzione non discrimina nulla.

**E #184 l'ha chiusa, per pan soltanto.** La misura qui sopra descrive lo stato
*prima* del tracer bullet, e va letta come storia: l'asserzione ora nomina
`voice_pan` per esteso — che nella chiave registrata dal test (`logged_pan`)
non compare — quindi lo stesso sabotaggio che lasciava la suite interamente
verde adesso fa tre rossi.

**E #185 l'ha chiusa per gli altri cinque, ma per un'altra strada: non
rinominando.** I cinque domini erano già la stringa che compariva nel loro
`StrategyNotFoundError` (`voice_pitch`, `voice_onset`, `voice_pointer`,
`density`, `variation`), quindi non c'era nessun `'pan voce'` da riscrivere —
il letterale a mano è semplicemente sparito, perché la riga la emette il
registry dal proprio `kind`. Quel che #185 aggiunge è l'asserzione che
discrimina, per tutti e cinque:
`test_registry_convergenza.py::test_la_registrazione_delega_al_registry`
registra una chiave (`_convergenza_di_prova`) in cui nessuno dei cinque domini
compare come sottostringa, quindi il dominio è l'unica cosa che può
soddisfarla.

La conseguenza per #184 è che il rename `'pan voce'` → `voice_pan` va
verificato leggendo, non aspettandosi un rosso — e che il letterale sopravvive
in altri due punti che nessun test allinea: la docstring di
`log_strategy_registration`, che lo cita come esempio di `domain`, e
`tests/shared/test_diagnostic_logger.py`, che lo passa come proprio letterale a
una chiamata diretta dell'helper. Vanno aggiornati nello stesso commit, o
restano indietro in silenzio.

### `create(name, *args, **kwargs)`

Il registry **non guarda dentro gli argomenti**: li inoltra al costruttore così
come arrivano. I posizionali non sono un lusso: le due strategy di density si
costruiscono con `(param, distribution_param)` e chiamano quel primo parametro
con due nomi diversi (`fill_factor_param`, `density_param`), quindi per parola
chiave non si passano affatto. Con `*args` la density entra dalla stessa porta
delle altre invece di avere un `create` proprio, che è esattamente il caso
speciale che la #184 vieta di aggiungere.

Il primo parametro si chiama `name` ovunque. `strategy_name` (pan) e
`variation_mode` (variation) descrivono da dove viene il valore, non che cosa è:
è la chiave del registry. Tutti i chiamanti di oggi lo passano posizionalmente
— in `Stream`, in `Parameter`, nei test — quindi la convergenza non rompe
niente.

### `base` è portato, non imposto

Il registry riceve l'ABC del proprio dominio: serve a inferire il tipo di
ritorno di `create()` e a rendere l'oggetto autodescrittivo. **Non** verifica
`issubclass` alla registrazione: per gli otto registry che convergono sarebbe
un rifiuto nuovo, e un rifiuto nuovo è un cambio di superficie pubblica — chi
oggi registra una strategy duck-typed smetterebbe di poterlo fare. Se lo si
vuole, è una issue sua, con la sua analisi d'impatto, non un effetto collaterale
del refactor.

**Né rientra dalla riga diagnostica.** `log_strategy_registration` leggeva
`strategy_class.__name__` come espressione argomento, cioè avidamente, quindi
un registrabile chiamabile ma senza quel dunder (una `functools.partial`)
moriva di `AttributeError` dentro `register`, con la diagnostica accesa o
spenta. Con #185 la cosa riguarda pitch, onset e pointer, i cui `register_*`
prima assegnavano nel dizionario senza ispezionare niente: l'etichetta si
risolve ora senza pretenderla (`__name__`, altrimenti il nome del tipo), e
`tests/strategies/test_registry.py::TestRegister::test_register_accetta_un_registrabile_senza_dunder_name`
lo pinna accanto a `test_register_non_verifica_issubclass`, che misurava la
stessa promessa con una *classe*.

**Non imposto non vuol dire non misurato, e #185 ha dovuto separare le due
cose.** Il divieto riguarda `register`, che non deve *rifiutare* una classe:
non dice nulla su che cosa i registry della famiglia contengano oggi. E
quello non lo chiedeva nessuno — `registry.base` era confrontata solo con il
nome che la tabella del presidio dichiara, cioè due grafie dello stesso nome —
mentre `base` non la legge nessun ramo di codice, essendo portata per il
seguito (#265, e la decisione qui sotto su `distribution`). Un `base` cablato
sull'ABC di un altro asse era perciò **inerte**: misurato, con
`StrategyRegistry('voice_pointer', VoiceOnsetStrategy, …)` e la tabella
d'accordo — le due grafie sbagliate insieme, che è la forma che prende la
copia di un `Caso` dall'asse accanto — `make tests` restava interamente verde.
`test_registry_convergenza.py::test_il_registry_non_e_vuoto_e_mappa_nomi_su_classi`
misura ora il contenuto contro la `base` del proprio registry: non respinge
niente, quindi non tocca la superficie pubblica che il divieto protegge.

**Il nono registry però valida già, e la direzione in cui sbaglia è
l'opposta.** `DistributionFactory.register` rifiuta una classe che non sia
sottoclasse di `DistributionStrategy`, con `InvalidStrategyConfigError`
(`strategy_kind="distribution"`, `field="strategy_class"`); il rifiuto è
superficie pubblica dichiarata — `tests/shared/test_range_anchor.py` lo scrive
in una docstring — ed è pinnato da due test,
`tests/shared/test_distribution_strategy.py` e
`tests/strategies/test_misc_strategy_errors.py`. Convertirlo sulla forma decisa
qui non sarebbe quindi meccanico: **toglierebbe** un rifiuto vivo e farebbe
cadere quei due test. È esattamente il caso che la regola di #184 nomina — se
un modulo chiede un'eccezione si torna a questo documento e si cambia la forma,
non si aggiunge l'eccezione — e per questo `distribution` non è nel giro di
#184/#185 né nel suo seguito immediato (#265): la decisione che gli serve
(validare è opzione del registry, o è la classe generica a doverlo sapere
fare?) è una domanda in più, e va posta prima di toccarlo, non durante.

Che è anche il motivo per cui il censimento doveva arrivarci: il guadagno
promesso più sotto è che «questo registry valida?» abbia **una risposta sola**,
e finché distribution resta fuori dal conto quella domanda ne ha due senza che
nessuno lo veda scritto.

### Le costanti restano dove sono (domanda 3)

`SEMITONE_LOCKED` e `CHORD_INTERVALS` restano nomi di modulo in
`voice_pitch_strategy.py`, fuori dal registry. Due ragioni, e la seconda è più
forte della prima:

1. non sono contenuto del registry. `SEMITONE_LOCKED` è un'affermazione sulle
   *unità*, indicizzata per nome di strategy e letta da
   `Stream._take_voice_pitch_keys` (il `take_block_keys` del pitch nel wiring
   di `_init_voice_manager`, #186); `CHORD_INTERVALS` è il dominio di un kwarg.
   Attaccarle all'oggetto registry darebbe alla classe generica una superficie
   per dominio, cioè il caso speciale;
2. sono già lette da chi non può seguirle. `CHORD_INTERVALS` la importa dal
   motore, per nome, il test di parità di PGE-ls (`tests/test_pge_parity.py`);
   il `diagnostic_provider.py` di quel repo la nomina anche lui, ma legge il
   proprio specchio in `granular_ls/voice_strategies.py`, quindi non è un
   secondo vincolo — è una copia a mano, e la copia non protesta.
   `SEMITONE_LOCKED` non esce da qui: la legge `Stream._take_voice_pitch_keys`, e
   PGE-ls ne tiene un altro specchio (`SEMITONE_LOCKED_STRATEGIES`). Spostarle
   costa una CI rossa — altrove per la prima, qui per la seconda — in cambio di
   niente.

Resta vero che `SEMITONE_LOCKED` è un `frozenset` di nomi che deve restare
allineato alle chiavi del registry, e che una strategy registrata dinamicamente non può
dichiararsi semitone-locked. La cura sarebbe metadato sulla classe, non sul
registry. Il wiring (#186) non l'ha presa, e l'ha resa più piccola: la lettura
di `SEMITONE_LOCKED` ora sta in un punto solo, `Stream._take_voice_pitch_keys`,
che è dove un attributo di classe andrebbe letto. Spostare la dichiarazione dai
nomi alle classi resta però una decisione sulla superficie d'estensione
([[add-voice-strategy]]) e tocca `voice_pitch_strategy.py`: materiale per la
decomposizione di `Stream` (#190) o per una issue sua, non per qui.

### Il `print()` (domanda 4)

Già deciso dalla #178 e fatto dalla #187: logger diagnostico, mai stdout. La
forma generica lo eredita in un punto solo — `StrategyRegistry.register` — con
la conseguenza che **i quattro registry oggi muti cominciano a parlare** (pitch,
onset, pointer, window). È voluto: è una riga `DEBUG` su un logger che di
default non ha handler, quindi non compare a nessuno che non l'abbia accesa, e
l'alternativa sarebbe conservare la divergenza per non toccarla.

C'è però un presidio che il refactor **indebolisce**, e va rinforzato nello
stesso passo. Le guardie della #187 sono due, e una sola perde di vista la
classe generica. `test_la_registrazione_dinamica_non_stampa` riconosce con `ast`
le `def register_*_strategy` di livello modulo: un `log_strategy_registration`
spostato dentro un *metodo* di `StrategyRegistry` le esce dal campo visivo.
`test_le_strategie_non_stampano` invece è scoped per **cartella** e vieta
qualunque `print()` in `strategies/*.py`, quindi copre `strategies/registry.py`
— dove questa decisione mette la classe — pur non sapendo niente di lei.

**Accanto alle due ce n'è ora un terzo, che non è della #187 e non è un
divieto.** `test_ogni_print_di_src_pge_e_classificato` è arrivato dopo la prima
stesura di questa decisione (#178, scaglione #266) e chiede a `CLASSIFICAZIONE`
una voce per ogni `print()` di `src/pge/`, nelle due direzioni: una `print()`
nuova che nessuno classifica è rossa ovunque viva, e una voce che resta in
tabella dopo che la riga se n'è andata è rossa a sua volta. Cambia perciò il
conto della misura qui sotto — che è stata rifatta — ma non la prescrizione, e
il perché sta tutto nella sua natura: **censisce, non vieta**.

**Misurato — e la prima misura era presa nella sola configurazione in cui il
difetto non può esistere.** Su uno scheletro *non cablato*, cioè un modulo che
nessuno chiama, una `print()` dentro `StrategyRegistry.register` faceva fallire
`test_le_strategie_non_stampano[registry.py]` se il modulo stava in
`src/pge/strategies/` e lasciava l'intera suite verde se stava altrove: da lì la
conclusione che a tenere chiuso il buco fosse la cartella.

Quella seconda metà è scaduta con la stessa #266 che cambia il conto qui sotto,
e va detto qui e non solo più giù, perché è la premessa da cui la conclusione
veniva. Rimisurato adesso, sempre non cablato: in `shared/registry.py` la suite
non è verde, resta rosso `test_ogni_print_di_src_pge_e_classificato` — che non
guarda né la cartella né chi chiama — e in `strategies/registry.py` di rossi ce
ne sono due. Fra le due collocazioni la differenza è sempre di un test, ed è
sempre quello per cartella: a reggere la conclusione era la differenza, non il
verde, e quella regge ancora.

Ma il modulo cablato è ciò che questa decisione prescrive, e lì il conto cambia.
Con `VOICE_PAN_STRATEGIES` costruita sulla classe e il wrapper che le delega —
cioè #184 fatta — la stessa `print()` dava, **a `92712ef`, cioè con la #184
simulata a mano e non ancora scritta** (misurato sulla suite intera, dopo la
#266):

| collocazione della classe | test rossi |
|---|---|
| `src/pge/strategies/registry.py` | `test_le_strategie_non_stampano[registry.py]`, `test_ogni_print_di_src_pge_e_classificato`, `test_register_logs_instead_of_printing` |
| `src/pge/shared/registry.py` | `test_ogni_print_di_src_pge_e_classificato`, `test_register_logs_instead_of_printing` |

Fra le due collocazioni resta **un test di differenza**, non un rosso contro
un'intera suite verde — ed è sempre quello scoped per cartella, perché il
censimento della #266 parla in entrambe le righe e quindi non discrimina. A
tenere la seconda riga sono dunque due presidi di natura diversa, e la
differenza fra i due è tutto ciò che conta qui.

**E la #184, scrivendola davvero, ha cambiato il conto in entrambe le righe —
la conclusione no.** La guardia per funzione vede ora il metodo, e la classe si
è portata dietro una suite propria: rimisurato sul codice di #184, la stessa
`print()` dà cinque rossi dove la classe sta (`strategies/registry.py`) —
`test_le_strategie_non_stampano[registry.py]`,
`test_la_registrazione_dinamica_non_stampa[strategies/registry.py]`,
`test_ogni_print_di_src_pge_e_classificato`,
`tests/strategies/test_registry.py::test_la_registrazione_non_stampa` e
`test_register_logs_instead_of_printing` — e quattro in `shared/registry.py`,
gli stessi meno quello per cartella (misurato spostando davvero il modulo e
riallineando la lista dichiarata, che il censimento pretende allineata). La
differenza fra le due collocazioni è ancora di un test ed è ancora quello per
cartella; quel che cambia è che adesso, accanto ai presidi incidentali di cui
sotto, a parlare c'è anche una guardia **scritta per questo**.

Il primo la #187 l'ha lasciato accanto a quelli per `ast`: tre test
*comportamentali* — `test_register_logs_instead_of_printing` (pan),
`test_register_density_logs_instead_of_printing` (density),
`test_register_does_not_write_to_stdout` (variation) — chiamano il vero
`register_*_strategy` sotto `capsys` e pretendono `captured.out == ''`. Una
`print()` nella classe generica passa di lì qualunque cartella la ospiti.

Il secondo è il censimento della #266, e la sua copertura è di un altro tipo:
non vieta la `print()`, **pretende che sia dichiarata**. `DIAGNOSTICA` è una
categoria legale — `engine/generator.py` ne ha due — quindi il rimedio che
riporta il verde è una riga in `CLASSIFICAZIONE`, non la rimozione della
`print()`. Misurato: aggiunta quella voce per `shared/registry.py`, il
censimento tace e resta rosso il solo `test_register_logs_instead_of_printing`.
È esattamente il suo scopo dichiarato — rendere deliberata ogni riga su stdout,
non proibirla — ma vuol dire che a *chiudere* il buco non arriva: lo rende
rumoroso, e il rumore si spegne con una riga.

**Il che non salva la prescrizione: la rende più precisa.** La copertura
comportamentale è *incidentale*. Vale finché almeno una fra pan, density e
variation resta cablata su questa classe e tiene la propria asserzione; copre il
solo cammino che quei tre test percorrono, `register` e non `create`; e non dice
niente sui quattro registry che il refactor fa *cominciare* a parlare (pitch,
onset, pointer, window), nessuno dei quali ha un test con `capsys` sul proprio
wrapper. Il censimento della #266 non è incidentale — vede la classe per
costruzione, in tutte e due le collocazioni — ma si accontenta di una riga di
classificazione, quindi non è un divieto. Le guardie per `ast` — quelle scritte
apposta per sorvegliare *questo*, cioè per vietarlo anche fuori da
`strategies/` — restavano invece cieche alla classe in entrambe le
collocazioni. Il buco quindi non era «aperto il giorno in cui la classe cambia
cartella»: era aperto da subito nei presidi che dovrebbero vederlo, e chiuso
non lo teneva nessuno — a coprirlo per caso era un test scritto per pan, e
accanto a lui un censimento che lo rende rumoroso senza proibirlo. **È il
paragrafo che la #184 ha chiuso**, ed è il motivo per cui la regola qui sotto
chiede alla guardia di imparare `StrategyRegistry.register`: fatto quello, il
divieto non dipende più né dalla cartella né da pan.

Che è esattamente la lezione del settimo entry point in [[contratto-stdout]] —
il criterio è la funzione, non la cartella — un giro più in là:
`register_window_strategy` è già il precedente di un punto di registrazione che
vive fuori da `strategies/` ed è rimasto scoperto fino alla guardia per
funzione.

**E non è l'unico: ce n'è un secondo, ancora senza divieto, e il censimento per
forma di questo documento è ciò che lo rende visibile.**
`DistributionFactory.register` (`shared/distribution_strategy.py`) è un punto di
registrazione documentato come superficie pubblica, e cade fuori da *entrambe*
le guardie per due motivi indipendenti: non sta in `strategies/`, come quello
delle finestre, e in più non è una `def register_*_strategy` di livello modulo
ma una classmethod `register` — cioè la stessa grafia che qui si teme per
`StrategyRegistry.register`. Oggi non stampa, quindi il buco è latente e non un
rosso mancato; ma è il precedente esatto della cecità che #184 deve chiudere, e
allargare il finder a un *metodo* chiamato `register` è il passo che
potenzialmente porta dentro anche lui.

**Anche qui la #266 sposta il confine di «scoperto», e nella stessa direzione.**
Misurato a `92712ef`: una `print()` dentro `DistributionFactory.register` faceva
cadere un test, `test_ogni_print_di_src_pge_e_classificato`, e nessun altro —
né quella per cartella, che il modulo non lo vede, né quella per funzione, che
la classmethod le usciva dal campo visivo. Valeva quindi parola per parola quel
che vale per la classe generica: la riga non passerebbe più in silenzio, ma il
rimedio che riporta il verde è una voce in `CLASSIFICAZIONE`, non la rimozione
della `print()`. Ciò che restava scoperto era il **divieto**, non il censimento
— ed è la distinzione da tenere in mano leggendo il paragrafo qui sotto.

**Quella misura è scaduta con la #184, ed è l'unico punto di questa sezione in
cui la conclusione cambia e non solo il conto.** Scegliendo il criterio largo,
la guardia per funzione ha smesso di essere cieca alla classmethod: rimisurato
sul codice di #184, la stessa `print()` fa cadere **due** test, il censimento e
`test_la_registrazione_dinamica_non_stampa[shared/distribution_strategy.py]`.
Il divieto che mancava a `distribution` adesso c'è, e senza che `distribution`
sia stato convertito — che è precisamente ciò che il paragrafo qui sotto
chiedeva di decidere.

Chi esegue #184 decida quale dei due criteri sta scrivendo — «il metodo
`register` di `StrategyRegistry`» o «un metodo `register` su un registry» —
perché il secondo cambia anche l'insieme dei `trovati` del censimento qui sotto,
e il primo lascia distribution fuori dai divieti, con la sua cecità intatta
nelle sole guardie che vietano.

**#184 ha scritto il secondo**, cioè il più largo: un metodo chiamato
esattamente `register` dentro una classe, accanto alle `def
register_*_strategy` di modulo. Il censimento cresce perciò di *due* voci e
non di una — `strategies/registry.py` e `shared/distribution_strategy.py` — e
nessuna delle due è un'eccezione: sono i punti di registrazione, ora che la
guardia li vede. Sorvegliare `distribution` non è convertirlo: resta sulla
forma vecchia con la sua validazione `issubclass`, in attesa della decisione
che gli serve.

Il criterio è `register` **esatto** e non `register_*`, e la differenza è
misurata: `FtableManager.register_sample` e `register_window` sono metodi che
cominciano per `register` e non registrano nessuna strategy. Una guardia che
li accusasse chiederebbe di mantenere una lista di falsi positivi — il difetto
speculare a quello che l'allargamento chiude — quindi c'è un test anche per
quella direzione.

Quel test **verifica le proprie esche prima di scartarle**, e chi scrive
l'analogo per #185 erediti la ragione: le due `register_*` stanno in un modulo
che della guardia non sa niente, quindi un `assert trovate == []` da solo resta
verde anche quando non c'è più niente da scartare — misurato, rinominando
`register_sample`. Il confine fra criterio largo e criterio stretto smetterebbe
di essere tenuto esattamente nel momento in cui qualcuno allarga il criterio.

Da cui due regole per #184:
la guardia impari anche `StrategyRegistry.register`, così che il presidio smetta
di dipendere dalla cartella e dal caso; e le `def register_*_strategy` restino
`def` di modulo (una riga di corpo che delega), non alias
`register_x = REGISTRY.register`. Un alias farebbe sparire quel modulo dal
censimento dei sorgenti: il test lo direbbe subito, ma la decisione è che i
wrapper restino, perché sono l'API di estensione documentata e portano le
proprie docstring con gli esempi.

**La prima delle due regole si porta dietro un passo, e non è opzionale.**
`_funzioni_di_registrazione` non serve una guardia sola: la leggono sia
`test_la_registrazione_dinamica_non_stampa` sia
`test_la_lista_dei_punti_di_registrazione_e_completa`, che su quello stesso
insieme asserisce `trovati == dichiarati`. Insegnarle `StrategyRegistry.register`
fa dunque entrare `strategies/registry.py` fra i `trovati` — misurato: senza
altro, il censimento fallisce con `solo nei sorgenti: ['strategies/registry.py']`,
e a cadere è una guardia che #184 non stava toccando. Il modulo della classe va
quindi aggiunto a `MODULI_CON_REGISTRAZIONE_DINAMICA` nello stesso commit che
allarga il criterio, dove non è un'eccezione ma il caso proprio: è il punto di
registrazione, ora che la registrazione vive lì. L'alternativa — una guardia
separata per il metodo, che lasci il finder condiviso intatto — tiene il
censimento verde ma rimette in piedi due criteri per una regola sola, cioè
esattamente ciò che questa sezione toglie di mezzo.

### density e variation entrano, le loro façade no (domanda 5)

Entrano per **archiviazione, lookup ed errore**: sono un dizionario nome →
classe con lo stesso `StrategyNotFoundError`, e la differenza di dominio
(density, variation) è esattamente ciò che il `kind` alla costruzione esiste per
portare.

Non entra la loro logica di dominio. `StrategyFactory.create_density_strategy`
tiene la propria firma e la propria validazione: cerca `distribution` fra i
parametri e solleva `InvalidStrategyConfigError` se manca. Quello non è lookup,
è una regola su come si costruisce una strategy di density — e la sua firma è
pinnata anche in dettaglio, con un test che pretende che
`StrategyFactory.__dict__['create_density_strategy']` sia uno `staticmethod`.
Per la stessa ragione tutte le façade restano `@staticmethod` che delegano, non
alias di metodo legato.

**Una cosa la façade non può delegare, e l'ordine in cui non la delega è
pinnato.** `tests/strategies/test_registry_errors.py` chiama
`create_density_strategy("bogus", None, {})` e pretende
`StrategyNotFoundError`. Lì le due condizioni di fallimento sono vive insieme —
il nome non è registrato *e* `distribution` manca — quindi è l'ordine a
decidere il tipo dell'eccezione, e oggi il lookup viene prima. Una façade che
delegasse il lookup a `DENSITY_STRATEGIES.create(...)` tenendo davanti la
propria validazione solleverebbe `InvalidStrategyConfigError` e farebbe cadere
quel test: il lookup va interrogato per primo (`name in REGISTRY` davanti al
controllo di `distribution`) e solo la costruzione delegata al registry. È un
vincolo per #185, non una preferenza.

**#185 l'ha applicato in questa forma**: la validazione di `distribution` sta
dentro il ramo `selected_param_name in DENSITY_STRATEGIES`, così che un nome
non registrato cada sul `create` del registry qualunque cosa contenga
`all_params`, e la façade non ricostruisca l'errore per conto proprio. Il test
che pinna l'ordine è rimasto quello che c'era; il «qualunque cosa contenga»
lo pinna `test_density_not_found_non_dipende_dal_tipo_di_all_params`, nello
stesso file, perché dentro il ramo sta anche la *lettura* di `distribution` e
non solo il `raise` — con `all_params.get(...)` davanti al gate un
`all_params` che non è una mappa alzava `AttributeError` invece dell'errore di
lookup.

### Chi fa da tracer bullet

`voice_pan_strategy`, come dice la #184 — ma non più per le ragioni scritte lì,
e vale la pena dirlo perché quelle ragioni sono invecchiate: non è più «l'unica
il cui `register_*()` stampa su stdout» (nessuna stampa più dalla #187). Regge
lo stesso, per tre motivi:

- è l'unica il cui `create()` chiama il primo parametro `strategy_name` — non
  l'unica a divergere da `name` (variation ha `variation_mode`, density
  `selected_param_name`), ma l'unica in cui la divergenza cade sulla firma
  `create(name, **kwargs)` che il registry generico deve assorbire tale e
  quale, senza casi speciali;
- è una delle tre che emettono la riga diagnostica, quindi passa per il punto
  dove il dominio si uniforma (`'pan voce'` → `voice_pan`);
- i suoi test esercitano la mappa in tutte le *forme* che la classe generica
  deve soddisfare — `isinstance(..., dict)`, snapshot e ripristino con
  `dict()`/`clear()`/`update()`, `pop()` nel `finally`, indicizzazione e
  appartenenza — quindi un `dict` sottoclassato che non regge la superficie
  cade già sul tracer bullet, senza aspettare #185.

**Non è però il banco di prova più largo, e crederlo sarebbe il modo di
sbagliare #185.** A maltrattare di più la mappa sono i test di *variation*:
`tests/strategies/test_variation_registry.py` rifà per intero la superficie di
pan — `isinstance`, `dict()`/`clear()`/`update()`, `pop()`, indicizzazione,
appartenenza, `items()` — e vi aggiunge tre operazioni che pan non compie mai:
misura la lunghezza, itera il registry direttamente (`for key in ...`), legge i
`values()`. Nessuna delle tre è a rischio su una sottoclasse di `dict` — è
proprio perché il verde di pan non le ha viste che vanno nominate qui: il
tracer bullet non è la prova che la superficie `dict` sia coperta, è la prova
che la forma decisa regge su un modulo. La copertura si misura in #185, ed è
`variation` a doverla misurare.

**Misurata: la superficie regge, e il rosso è arrivato da un'altra parte.** Le
tre operazioni in più — lunghezza, iterazione diretta, `values()` — sono
passate senza toccare la classe, come previsto. A cadere sulla conversione di
variation è stato invece `test_register_logs_confirmation`, che pretende
`len(messaggi) == 1`: lasciare nel modulo la sua `log_strategy_registration`
accanto alla delega a `StrategyRegistry.register` fa uscire la riga **due
volte**. È il difetto che solo i due registry già parlanti (density, variation)
potevano avere, e che il tracer bullet non poteva vedere — pan la sua
`print()` l'aveva persa con la #187 — quindi la lezione di questa sezione
resta giusta per una ragione diversa da quella scritta: il banco di prova più
largo non era la superficie `dict`, era la riga diagnostica.

Se per farla passare servisse un caso speciale nella classe generica, la regola
è quella della #184: si torna qui e si cambia la forma, non si aggiunge
l'eccezione. Non è servito: né per pan, né per i cinque di #185.

### Chi resta fuori

`InterpolationStrategyFactory` (`envelopes/envelope_factory.py`) **non** entra:
la sua mappa è privata, normalizza il nome (`strip().lower()`), accetta in
ingresso anche un'istanza già costruita e solleva `ValueError` invece di
`StrategyNotFoundError`. È un adattatore, non un registry, e uniformarlo
significherebbe cambiare cosa accetta — un'altra decisione, con un altro
impatto.

`window_selection_strategy` e `grain_clip_strategy` invece **rientrano**, ma
dopo: sono il seguito di #185 — aperto nel frattempo come #265 — non parte di
#184/#185, così che il tracer bullet resti misurato su un modulo solo. La prima
porta anche `from_spec()`, che è lettura di YAML e resta sua; il secondo non ha
punto di registrazione e la conversione è l'occasione per decidere se debba
averlo.

`distribution_strategy` rientra anche lui, ma **più tardi ancora e con una
domanda aperta davanti**: la sua `register` valida `issubclass` e quel rifiuto
è pinnato (vedi «`base` è portato, non imposto»), quindi convertirlo sulla
forma decisa qui è una perdita di comportamento, non una riscrittura. Finché
quella domanda non ha risposta è nel censimento e fuori dal giro: sapere che è
della famiglia serve per non decidere due volte la stessa cosa in modi diversi,
che è il guadagno per cui esiste questo documento.

## Trade-off

**Ereditare da `dict` è un compromesso, ed è quello che i vincoli scelgono.**
La forma più pulita — composizione, la mappa privata dietro un'interfaccia
stretta — è preclusa da ciò che i test e la parità di PGE-ls già trattano come
un dizionario. Il costo si paga in due punti: `registry.copy()` restituisce un
`dict` normale, che non ha né `kind` né `create()` (chi vuole un registry lo
costruisce, chi vuole uno snapshot ha quel che gli serve); e `registry['x'] =
strategy_class` resta una registrazione legale e muta, che scavalca la riga
diagnostica.
Il secondo è voluto: la riga appartiene al punto di ingresso esplicito, e la
scrittura diretta è quel che fanno le fixture per rimettere a posto lo stato.

**La riga diagnostica passa da tre registry a sette.** Uniformare vuol dire
anche estendere, non solo togliere: i quattro muti di allora (pitch, onset,
pointer, window) cominciano a parlare. Sette è però il conto a convergenza
avvenuta, non quello di #184/#185: **con #185 chiusa i registry che parlano sono
sei**, perché `window` è nel seguito insieme a `grain_clip` (#265, vedi «Chi
resta fuori»). Gli altri due sono quelli che il conto non tocca, ciascuno per il
proprio motivo: `grain_clip` un punto di registrazione oggi non ce l'ha — ne
parlerebbe otto solo se il seguito decidesse di dargliene uno, che è appunto la
domanda lasciata aperta lì — e `distribution` ce l'ha ma è fermo davanti alla
domanda sulla validazione, quindi il suo eventuale nono ingresso è oltre
l'orizzonte di questa decisione. Su un canale
spento di default il prezzo è nullo a runtime; il prezzo vero è che d'ora in
poi «registrare» e «annunciare la registrazione» sono la stessa operazione e
non si possono più separare per registry — che è precisamente quel che si
voleva.

**Il risparmio in righe è modesto.** Le copie di una ventina di righe che
convergono davvero — otto delle nove, distribution a parte — diventano una
classe di trenta più otto superfici sottili: il conto netto è piccolo, e chi cerca lì il guadagno resterà deluso. Il guadagno è che la
prossima divergenza ha un posto solo dove succedere, e che la prossima domanda
(«questo registry valida? logga? come si chiama il primo parametro?») ha una
risposta sola.

**Il refactor tocca moduli che un altro repository importa per nome.** Ogni
nome di livello modulo — le otto mappe di modulo, i sette `register_*`, le nove
`Factory` (`grain_clip` compresa: la façade ce l'ha pur senza avere il punto di
registrazione; `DistributionFactory` compresa, che la mappa la tiene dentro di
sé) — sopravvive identico. Per cinque di quei nomi, e cinque soli, è
la condizione perché la parità di PGE-ls resti verde: le quattro mappe voce e
`CHORD_INTERVALS`. Per tutti gli altri è disciplina interna, non vincolo
esterno, e conviene saperlo in questi termini: chi esegue #184/#185 deve
verificare *quali* nomi sono davvero pinnati, e il posto dove leggerlo è la
#269 (o il censimento qui sopra) — non la #246, che inventaria la superficie
importata da **PGE-ui** e non nomina nessuna di queste mappe.

**La documentazione di estensione è già disallineata, e questo la rimette in
riga.** [[add-voice-strategy]] dice «registra nella factory
`Voice<Axis>StrategyFactory.REGISTRY`» e [[add-variation-strategy]] dice
`VariationFactory.REGISTRY`: quell'attributo non è mai esistito. La forma decisa
qui non lo introduce — la mappa vive a livello di modulo, dove i test e PGE-ls
la cercano — quindi le due how-to vanno corrette nel passo che le tocca, non
prese come specifica. #184 ha corretto [[add-voice-strategy]], che è la
how-to dell'asse toccato: il passo 3 nomina ora la mappa di modulo e la
`register_voice_<axis>_strategy`, e dice quale asse è già sulla forma nuova.
#185 ha corretto [[add-variation-strategy]] allo stesso modo: il passo 2
nomina la mappa di modulo `VARIATION_STRATEGIES` e la
`register_variation_strategy(name, strategy_class)`, e dice che la mappa è uno
`StrategyRegistry`. Il passo 3 di [[add-voice-strategy]] perde a sua volta la
frase che distingueva pan dagli altri tre assi: ora sono tutti sulla forma
nuova.

## Implicazioni codice

- **Aggiungi una strategy a un asse esistente** → `register_<asse>_strategy(nome,
  Classe)`, che delega a `REGISTRY.register`. La mappa di modulo resta il posto
  dove si guarda cosa è registrato.
- **Aggiungi un asse o un registry nuovo** → `StrategyRegistry('<kind>', ABC,
  {...})` al livello di modulo, più una `def register_<kind>_strategy` che
  delega, più il modulo in `MODULI_CON_REGISTRAZIONE_DINAMICA` di
  `tests/shared/test_stdout_contract.py`. Il `kind` è la stessa stringa che
  compare in `StrategyNotFoundError`.
- **Non trasformare i `register_*` in alias** di `REGISTRY.register`: la guardia
  della diagnostica cerca `def register_*_strategy` di livello modulo, e un
  alias fa uscire il modulo dal censimento.
- **Non spostare né rinominare** le mappe di modulo, i `register_*`, le
  `Factory`, `SEMITONE_LOCKED`, `CHORD_INTERVALS` — ma sapendo quanto costa
  ciascuno. `VOICE_PITCH/ONSET/POINTER/PAN_STRATEGIES` e `CHORD_INTERVALS` sono
  importati per nome dal test di parità di PGE-ls (#269): lì il costo è
  immediato e fuori da qui. Gli altri costano dentro (`SEMITONE_LOCKED` la legge `Stream`)
  o non costano ancora niente, e restano fermi per non spendere una decisione su
  niente. Se uno deve muoversi, prima l'analisi d'impatto cross-repo.
- **Non aggiungere validazione `issubclass`** dentro `register()` in #184/#185:
  per i registry che convergono è un rifiuto nuovo e va introdotto da una issue
  sua. Vale al contrario per `DistributionFactory`, che quel rifiuto ce l'ha già
  e pinnato: lì il rischio è **toglierlo** convertendo, e la conversione aspetta
  una decisione propria.
- **Rinominando il dominio della riga diagnostica** (`'pan voce'` → `voice_pan`)
  non aspettarti un rosso: nessun test lo pinna, misurato. I tre letterali —
  il modulo, la docstring di `log_strategy_registration`,
  `tests/shared/test_diagnostic_logger.py` — vanno allineati leggendo.
  **Per pan questo non vale più**: #184 ha reso discriminante l'asserzione di
  `test_register_logs_instead_of_printing` (`'voice_pan'`, che nella chiave
  registrata dal test non compare, invece di `'pan'`, che ci compariva), e lo
  stesso sabotaggio che prima lasciava la suite interamente verde ora fa tre
  rossi. **Per gli altri cinque non vale più nemmeno come regola**: #185 ha
  trovato i domini già allineati agli errori — niente da rinominare — e ha
  lasciato al loro posto un'asserzione che discrimina, una per registry
  (`test_registry_convergenza.py`). **Sulla riga diagnostica** in `src/` non
  c'è più un solo letterale di dominio: `log_strategy_registration` ha un
  unico chiamante, `StrategyRegistry.register`, che passa il proprio `kind`.
  Restano gli esempi nella docstring dell'helper e i cinque letterali che
  `tests/shared/test_diagnostic_logger.py` passa a chiamate dirette
  dell'helper — dati di quel test, non la copia dell'etichetta di un modulo.

  **E non si ferma sulle façade.** `StrategyRegistry.register` — il metodo a
  cui tutte e sei delegano, e un punto di registrazione a pieno titolo per il
  censimento di [[contratto-stdout]], che legge le `def register_*_strategy`
  di modulo **e** i metodi `register` dentro una classe — teneva `cls` come
  secondo parametro: il nome da cui pitch, onset e pointer sono stati
  convertiti, sopravvissuto nell'unico punto che serve tutti e sei i domini.
  Si chiama `strategy_class` anche lì, e
  `test_registry_convergenza.py::test_la_firma_della_classe_generica_e_quella_delle_sei_facade`
  lo pretende.

  La misura è quella e non una più larga, perché la più larga sarebbe falsa e
  verrebbe letta come regola: lo `strategy_kind` degli **errori** è ancora
  scritto a mano in ventidue punti di `src/`, **dieci** dei quali
  `"voice_pitch"` dentro il modulo che #185 ha convertito — altri due stanno
  in `core/stream.py`, che #185 non tocca — e uno `"density"` nella façade
  che ha riscritto. Non è una svista: il censimento della #177 —
  «tre etichette di dominio scritte a mano» — contava i chiamanti
  dell'helper, non ogni stringa che nomina un dominio, e a quel censimento
  risponde questa riga. Gli `strategy_kind` degli errori sono un'altra
  domanda, e nessuna issue l'ha ancora posta.
- **Ordine di esecuzione** → ~~#184 (pan, con la guardia estesa a
  `StrategyRegistry.register`)~~ **fatta**, ~~#185 (pitch, onset, pointer,
  density, variation)~~ **fatta**, poi #265 per `window_selection_strategy` e
  `grain_clip_strategy`, e `distribution_strategy` dopo la decisione sulla
  validazione.
- **Se il tracer bullet chiede un'eccezione** → si torna a questo documento e si
  cambia la forma. Un caso speciale nella classe generica è il segnale che la
  forma è sbagliata, non che il modulo è strano.

## Vedi anche

- [[contratto-stdout]] — perché la conferma di registrazione è diagnostica e non
  stdout, e perché il criterio di una guardia è la funzione e non la cartella
- [[multi-voice]] — gli assi che i quattro registry voce servono
- [[architecture]] — l'Open/Closed che i registry realizzano
- [[add-voice-strategy]] · [[add-variation-strategy]] — le how-to che questa
  decisione obbliga a correggere
- Issue #177 (questa decisione), #184 (tracer bullet), #185 (le altre cinque),
  #265 (il seguito: `window_selection_strategy` e `grain_clip_strategy`),
  #187 e #178 (il canale della riga di registrazione), #266 (lo scaglione di
  #178 che ha portato il censimento di `CLASSIFICAZIONE`, da cui il conto della
  misura in «Il `print()`»), #269 (la superficie
  interna pinnata da PGE-ls: i cinque nomi di cui sopra, e perché il loro
  presidio può tacere), #246 (la gemella per PGE-ui: stessa classe di
  vincolo, altro elenco)
