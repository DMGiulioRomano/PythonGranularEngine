---
slug: strategy-registry
type: explanation
status: stable
tags: [strategy, registry, refactor, estensibilita, architecture]
sources:
  - src/pge/strategies/voice_pitch_strategy.py
  - src/pge/strategies/voice_onset_strategy.py
  - src/pge/strategies/voice_pointer_strategy.py
  - src/pge/strategies/voice_pan_strategy.py
  - src/pge/strategies/strategy_registry.py
  - src/pge/strategies/variation_registry.py
  - src/pge/strategies/grain_clip_strategy.py
  - src/pge/controllers/window_selection_strategy.py
  - src/pge/envelopes/envelope_factory.py
  - src/pge/core/stream.py
  - src/pge/parameters/parameter.py
  - src/pge/shared/exceptions.py
  - src/pge/shared/logger.py
  - tests/shared/test_stdout_contract.py
  - tests/strategies/test_registry_errors.py
last_synced_commit: e44ede3
---

# Il registry generico delle strategy — la forma decisa

**Documenti collegati:** [[INDEX]] · [[architecture]] · [[multi-voice]] · [[contratto-stdout]] · [[add-voice-strategy]] · [[add-variation-strategy]]

Questo documento è l'esito della issue #177: la **decisione** su che forma prende
il registry generico, non la sua esecuzione. L'esecuzione è #184 (tracer bullet)
e #185 (le altre). Al commit qui sopra nessun modulo è ancora stato convertito:
quel che segue descrive la forma verso cui convergere e, per ogni scelta, il
vincolo che l'ha decisa.

---

## Problema

Lo stesso schema — un dizionario di modulo, una `register_*()`, una classe
`Factory` con un solo `create()` statico — è ripetuto in **otto** moduli, non
sei. La #177 ne elenca sei perché guarda `strategies/`; il criterio però non è
la cartella, è la forma:

| modulo | mappa | registrazione | riga diagnostica | `create()` |
|---|---|---|---|---|
| `strategies/voice_pitch_strategy.py` | `VOICE_PITCH_STRATEGIES` | `(name, cls)` | no | `create(name, **kwargs)` |
| `strategies/voice_onset_strategy.py` | `VOICE_ONSET_STRATEGIES` | `(name, cls)` | no | `create(name, **kwargs)` |
| `strategies/voice_pointer_strategy.py` | `VOICE_POINTER_STRATEGIES` | `(name, cls)` | no | `create(name, **kwargs)` |
| `strategies/voice_pan_strategy.py` | `VOICE_PAN_STRATEGIES` | `(name, strategy_class)` | sì, dominio `'pan voce'` | `create(strategy_name, **kwargs)` |
| `strategies/strategy_registry.py` | `DENSITY_STRATEGIES` | `(param_name, strategy_class)` | sì, dominio `'density'` | `create_density_strategy(selected_param_name, param_obj, all_params)` |
| `strategies/variation_registry.py` | `VARIATION_STRATEGIES` | `(mode_name, strategy_class)` | sì, dominio `'variation'` | `create(variation_mode)` |
| `controllers/window_selection_strategy.py` | `WINDOW_STRATEGY_REGISTRY` | `(name, cls)` | no | `create(name, **kwargs)` + `from_spec(...)` |
| `strategies/grain_clip_strategy.py` | `GRAIN_CLIP_STRATEGIES` | — | — | `create(name, **kwargs)` |

La tabella è la prova che si tratta di duplicazione e non di somiglianza: per
una cosa sola — «registra una classe sotto un nome» — ci sono tre parole per il
primo parametro (`name`, `param_name`, `mode_name`), due per il secondo (`cls`,
`strategy_class`), due convenzioni per il nome della mappa (`*_STRATEGIES` e
`WINDOW_STRATEGY_REGISTRY`), tre etichette di dominio scritte a mano, e un
ottavo registry che non ha nemmeno il punto di registrazione.

**Un punto della #177 è già stato sciolto altrove, e conviene arrivarci
sapendolo.** Il `print()` alla registrazione non esiste più: la #187 lo ha
portato a `log_strategy_registration`, cioè al logger `pge.diagnostics`, e la
regola di quale riga vive su stdout è scritta in [[contratto-stdout]]. Quel che
resta della divergenza descritta dalla issue non è il canale, è **chi la riga la
emette**: tre registry su otto la emettono, quattro tacciono, uno non ha la
funzione da cui emetterla.

Due vincoli esterni rendono questa duplicazione più cara di quanto sembri, e
sono ciò che decide la forma più di ogni preferenza di stile:

- **Cinque nomi di modulo sono superficie pinnata, e solo cinque.**
  `tests/test_pge_parity.py` di PGE-ls importa dai moduli del motore
  `VOICE_PITCH_STRATEGIES`, `VOICE_ONSET_STRATEGIES`,
  `VOICE_POINTER_STRATEGIES`, `VOICE_PAN_STRATEGIES` e `CHORD_INTERVALS`, e ne
  confronta le chiavi con il proprio registro statico: spostare o rinominare
  una di quelle cinque rende rossa la CI di un altro repository senza far
  fallire un test di PGE. Le altre quattro mappe (density, variation, window,
  grain_clip) nessuno le importa da fuori, e nemmeno i `register_*`, le
  `Factory` o `SEMITONE_LOCKED` — di quest'ultima PGE-ls tiene una copia a mano
  (`SEMITONE_LOCKED_STRATEGIES` in `granular_ls/pitch_units.py`), che un rename
  qui per definizione non tocca: resta indietro in silenzio invece di gridare.
  È la stessa *classe* di esposizione che inventaria la #246, non la stessa
  esposizione — quell'issue elenca ciò che importa l'harness di parità di
  **PGE-ui**, e fra i suoi moduli non compare nessuna di queste mappe. Il
  vincolo PGE-ls, oggi, non è registrato altrove che qui.
- **La guardia sulla diagnostica è derivata dai sorgenti.**
  `tests/shared/test_stdout_contract.py` cerca con `ast` le `def
  register_*_strategy` di livello modulo, pretende che l'insieme dei moduli che
  ne contengono una sia *esattamente* quello dichiarato, e che nessuna di quelle
  funzioni stampi. Il refactor passa dentro quella guardia: una forma che
  facesse sparire quelle `def` la spegnerebbe.

## Modello

### La forma

Una classe generica che **è** la mappa, in un modulo nuovo
`src/pge/strategies/registry.py`:

```python
from __future__ import annotations

S = TypeVar("S")


class StrategyRegistry(Dict[str, Type[S]]):
    """Mappa nome -> classe strategy che conosce il proprio dominio."""

    def __init__(self, kind: str, base: Type[S],
                 initial: Dict[str, Type[S]] | None = None):
        super().__init__(initial or {})
        self.kind = kind
        self.base = base

    def register(self, name: str, cls: Type[S]) -> None:
        self[name] = cls
        log_strategy_registration(self.kind, name, cls)

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
argomento per variation). Il codice che li misura vive in #184, dove diventa
test.

### `strategy_kind` alla costruzione (domanda 2)

Alla costruzione. Il `kind` non è un dato della chiamata, è una proprietà del
registry: `create()` non ha modo di sbagliarlo e nessun chiamante deve
ripeterlo. Quel valore è già quello che `StrategyNotFoundError` riporta oggi
(`voice_pan`, `density`, `variation`, …), quindi **i messaggi d'errore non
cambiano** — verificato che nessuno, in PGE-ui o PGE-ls, li parsi.

Lo stesso `kind` diventa anche il dominio della riga diagnostica, e questo
uniforma le tre etichette scritte a mano: `'pan voce'` diventa `voice_pan`. Il
test che oggi la sorveglia chiede `'pan' in messaggio`, quindi resta verde; la
docstring di `log_strategy_registration`, che cita `'pan voce'` come esempio, va
aggiornata insieme.

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
`issubclass` alla registrazione: sarebbe un rifiuto nuovo, e un rifiuto nuovo è
un cambio di superficie pubblica — chi oggi registra una strategy duck-typed
smetterebbe di poterlo fare. Se lo si vuole, è una issue sua, con la sua analisi
d'impatto, non un effetto collaterale del refactor.

### Le costanti restano dove sono (domanda 3)

`SEMITONE_LOCKED` e `CHORD_INTERVALS` restano nomi di modulo in
`voice_pitch_strategy.py`, fuori dal registry. Due ragioni, e la seconda è più
forte della prima:

1. non sono contenuto del registry. `SEMITONE_LOCKED` è un'affermazione sulle
   *unità*, indicizzata per nome di strategy e letta da
   `Stream._init_voice_manager`; `CHORD_INTERVALS` è il dominio di un kwarg.
   Attaccarle all'oggetto registry darebbe alla classe generica una superficie
   per dominio, cioè il caso speciale;
2. sono già lette da chi non può seguirle. `CHORD_INTERVALS` la importa dal
   motore, per nome, il test di parità di PGE-ls (`tests/test_pge_parity.py`);
   il `diagnostic_provider.py` di quel repo la nomina anche lui, ma legge il
   proprio specchio in `granular_ls/voice_strategies.py`, quindi non è un
   secondo vincolo — è una copia a mano, e la copia non protesta.
   `SEMITONE_LOCKED` non esce da qui: la legge `Stream._init_voice_manager`, e
   PGE-ls ne tiene un altro specchio (`SEMITONE_LOCKED_STRATEGIES`). Spostarle
   costa una CI rossa — altrove per la prima, qui per la seconda — in cambio di
   niente.

Resta vero che `SEMITONE_LOCKED` è una lista di nomi che deve restare allineata
alle chiavi del registry, e che una strategy registrata dinamicamente non può
dichiararsi semitone-locked. La cura sarebbe metadato sulla classe, non sul
registry: è materiale per la decomposizione di `Stream` (#190) e per il wiring
(#186), non per qui.

### Il `print()` (domanda 4)

Già deciso dalla #178 e fatto dalla #187: logger diagnostico, mai stdout. La
forma generica lo eredita in un punto solo — `StrategyRegistry.register` — con
la conseguenza che **i quattro registry oggi muti cominciano a parlare** (pitch,
onset, pointer, window). È voluto: è una riga `DEBUG` su un logger che di
default non ha handler, quindi non compare a nessuno che non l'abbia accesa, e
l'alternativa sarebbe conservare la divergenza per non toccarla.

C'è però un buco che il refactor **apre**, e va chiuso nello stesso passo. La
guardia della #187 riconosce le `def register_*_strategy` di livello modulo: il
`log_strategy_registration` che si sposta dentro un *metodo* di
`StrategyRegistry` esce dal suo campo visivo, e da lì una `print()` potrebbe
rientrare lasciando la suite verde. È la stessa lezione del settimo entry point
in [[contratto-stdout]] — il criterio è la funzione, non la cartella — un giro
più in là: la guardia deve imparare anche `StrategyRegistry.register`, e le
`def register_*_strategy` devono restare `def` di modulo (una riga di corpo che
delega), non alias `register_x = REGISTRY.register`. Un alias farebbe sparire
quel modulo dal censimento dei sorgenti: il test lo direbbe subito, ma la
decisione è che i wrapper restino, perché sono l'API di estensione documentata e
portano le proprie docstring con gli esempi.

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
- i suoi test sono quelli che maltrattano di più la mappa —
  `isinstance(..., dict)`, snapshot e ripristino con `clear()`/`update()`,
  `pop()` nel `finally` — cioè sono la verifica che la classe generica soddisfi
  la superficie `dict` che tutti danno per scontata.

Se per farla passare servisse un caso speciale nella classe generica, la regola
è quella della #184: si torna qui e si cambia la forma, non si aggiunge
l'eccezione.

### Chi resta fuori

`InterpolationStrategyFactory` (`envelopes/envelope_factory.py`) **non** entra:
la sua mappa è privata, normalizza il nome (`strip().lower()`), accetta in
ingresso anche un'istanza già costruita e solleva `ValueError` invece di
`StrategyNotFoundError`. È un adattatore, non un registry, e uniformarlo
significherebbe cambiare cosa accetta — un'altra decisione, con un altro
impatto.

`window_selection_strategy` e `grain_clip_strategy` invece **rientrano**, ma
dopo: sono il seguito di #185, non parte di #184/#185, così che il tracer bullet
resti misurato su un modulo solo. La prima porta anche `from_spec()`, che è
lettura di YAML e resta sua; il secondo non ha punto di registrazione e la
conversione è l'occasione per decidere se debba averlo.

## Trade-off

**Ereditare da `dict` è un compromesso, ed è quello che i vincoli scelgono.**
La forma più pulita — composizione, la mappa privata dietro un'interfaccia
stretta — è preclusa da ciò che i test e la parità di PGE-ls già trattano come
un dizionario. Il costo si paga in due punti: `registry.copy()` restituisce un
`dict` normale, che non ha né `kind` né `create()` (chi vuole un registry lo
costruisce, chi vuole uno snapshot ha quel che gli serve); e `registry['x'] =
cls` resta una registrazione legale e muta, che scavalca la riga diagnostica.
Il secondo è voluto: la riga appartiene al punto di ingresso esplicito, e la
scrittura diretta è quel che fanno le fixture per rimettere a posto lo stato.

**La riga diagnostica passa da tre registry a otto.** Uniformare vuol dire
anche estendere, non solo togliere. Su un canale spento di default il prezzo è
nullo a runtime; il prezzo vero è che d'ora in poi «registrare» e «annunciare la
registrazione» sono la stessa operazione e non si possono più separare per
registry — che è precisamente quel che si voleva.

**Il risparmio in righe è modesto.** Otto copie di una ventina di righe
diventano una classe di trenta più otto superfici sottili: il conto netto è
piccolo, e chi cerca lì il guadagno resterà deluso. Il guadagno è che la
prossima divergenza ha un posto solo dove succedere, e che la prossima domanda
(«questo registry valida? logga? come si chiama il primo parametro?») ha una
risposta sola.

**Il refactor tocca moduli che un altro repository importa per nome.** Ogni
nome di livello modulo — le otto mappe, i sette `register_*`, le otto `Factory`
(`grain_clip` compresa: la façade ce l'ha pur senza avere il punto di
registrazione) — sopravvive identico. Per cinque di quei nomi, e cinque soli, è
la condizione perché la parità di PGE-ls resti verde: le quattro mappe voce e
`CHORD_INTERVALS`. Per tutti gli altri è disciplina interna, non vincolo
esterno, e conviene saperlo in questi termini: chi esegue #184/#185 deve
verificare *quali* nomi sono davvero pinnati, e il posto dove leggerlo è il
censimento qui sopra — non la #246, che inventaria la superficie importata da
**PGE-ui** e non nomina nessuna di queste mappe.

**La documentazione di estensione è già disallineata, e questo la rimette in
riga.** [[add-voice-strategy]] dice «registra nella factory
`Voice<Axis>StrategyFactory.REGISTRY`» e [[add-variation-strategy]] dice
`VariationFactory.REGISTRY`: quell'attributo non è mai esistito. La forma decisa
qui non lo introduce — la mappa vive a livello di modulo, dove i test e PGE-ls
la cercano — quindi le due how-to vanno corrette nel passo che le tocca, non
prese come specifica.

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
  importati per nome dal test di parità di PGE-ls: lì il costo è immediato e
  fuori da qui. Gli altri costano dentro (`SEMITONE_LOCKED` la legge `Stream`)
  o non costano ancora niente, e restano fermi per non spendere una decisione su
  niente. Se uno deve muoversi, prima l'analisi d'impatto cross-repo.
- **Non aggiungere validazione `issubclass`** dentro `register()` in #184/#185:
  è un rifiuto nuovo e va introdotto da una issue sua.
- **Ordine di esecuzione** → #184 (pan, con la guardia estesa a
  `StrategyRegistry.register`), poi #185 (pitch, onset, pointer, density,
  variation), poi un seguito per `window_selection_strategy` e
  `grain_clip_strategy`.
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
  #187 e #178 (il canale della riga di registrazione), #246 (la superficie
  interna pinnata da PGE-ui: stessa classe di vincolo, altro elenco — quello
  di PGE-ls è censito qui)
