# =============================================================================
# tests/strategies/test_registry_convergenza.py
# =============================================================================
"""
I registry della famiglia stanno tutti sulla forma decisa in #177 (issue #185).

La #184 ha portato `voice_pan` sulla classe generica `StrategyRegistry` e ha
lasciato gli altri otto sulla forma vecchia, deliberatamente: il tracer bullet
doveva provare che la forma regge prima di replicarla. Questo modulo e' il
presidio della replica -- pitch, onset, pointer, density e variation -- e
misura le tre cose che la convergenza produce e che nessun test vedeva:

1. la mappa di modulo **e'** un `StrategyRegistry` che conosce il proprio
   dominio (`kind`) e la propria ABC (`base`);
2. il `register_*` di modulo delega a `StrategyRegistry.register`, quindi la
   riga diagnostica esce **una volta sola** e porta il `kind` del registry
   invece di un letterale scritto accanto alla chiamata. Erano tre etichette
   scritte a mano su nove registri, e pitch, onset e pointer non emettevano
   la riga affatto: registrare una strategy la' non si vedeva da nessuna
   parte;
3. il `create()` delle factory non costruisce piu' l'errore per conto proprio.
   Il lookup e `StrategyNotFoundError` vivono nel registry, la factory delega,
   e la guardia e' sul *corpo* di `create` perche' il comportamento da solo
   non distingue una delega da una quinta copia della stessa riga. Sono due
   guardie, non una, e la differenza e' density: sulle cinque facade di solo
   lookup il corpo non alza **niente**, mentre il divieto del solo `raise
   StrategyNotFoundError` vale su tutte e sei -- density inclusa, che una
   validazione sua da difendere ce l'ha.

Piu' la convergenza delle firme, che e' un criterio della #185 e non un gusto:
il primo parametro si chiama `name` ovunque (`variation_mode`, `mode_name` e
`param_name` dicevano da dove viene il valore, non che cosa e' -- la chiave del
registry) e il secondo `strategy_class`. Tutti i chiamanti vivi li passano
posizionalmente (misurato: nessuna chiamata per parola chiave in `src/` o in
`tests/`), quindi la convergenza non rompe niente.

**«Ovunque» include la classe generica**, non solo le facade. I sei
`register_*` delegano a `StrategyRegistry.register`, che per il censimento di
`tests/shared/test_stdout_contract.py` e' un punto di registrazione come loro,
e il suo secondo parametro si chiamava `cls` -- il nome da cui pitch, onset e
pointer sono stati convertiti qui. Misurata sulle sole facade, la convergenza
lasciava quel nome vivo nell'unico punto che le serve tutte e sei.

**Chi resta fuori, e perche' e' dichiarato qui invece che dedotto.**
`StrategyFactory.create_density_strategy` non e' nel giro delle firme uniformi:
tiene la propria (`selected_param_name, param_obj, all_params`) e la propria
validazione, che non e' lookup ma una regola su come si costruisce una strategy
di density. L'ordine fra le due -- lookup prima, validazione dopo -- decide il
tipo dell'eccezione quando entrambe le condizioni sono vive, ed e' pinnato in
`tests/strategies/test_registry_errors.py`, non qui.

**Fuori dalla firma, e da nient'altro.** `create_uniforme=False` e' una
esenzione sulla forma della firma, non sulla delega: density il lookup lo
delega come gli altri cinque, quindi sta in entrambe le misure che lo
verificano -- la guardia sul sorgente qui sopra e l'errore chiesto al vivo,
che raggiunge la sua facade coi posizionali dichiarati in `Caso`. Il flag le
teneva fuori tutte e tre, cioe' era piu' largo della propria ragione, e la
conseguenza era misurabile: rimettendo a mano in `create_density_strategy` il
`raise StrategyNotFoundError` che la #185 ha tolto, `make tests` restava
interamente verde.

`WINDOW_STRATEGY_REGISTRY` e `GRAIN_CLIP_STRATEGIES` sono della famiglia ma
fuori da #184/#185: sono la #265. `DistributionFactory` e' fuori piu' a lungo e
per una ragione sua -- la sua `register` valida `issubclass`, quel rifiuto e'
superficie pubblica pinnata da due test, e convertirla lo **toglierebbe**. Il
razionale completo sta in `docs/explanation/strategy-registry.md`.

**Il limite del censimento, dichiarato.** `test_il_censimento_della_famiglia_e_completo`
cerca le mappe di *modulo* il cui nome finisce in `_STRATEGIES` o
`_STRATEGY_REGISTRY`: e' la grafia di tutte e otto, ed e' quella che un asse
nuovo eredita copiando un modulo esistente. Non vede una mappa che viva come
attributo di classe -- `DistributionFactory._registry`,
`InterpolationStrategyFactory._STRATEGY_MAP` -- ne' una battezzata diversamente.
Per quelle il presidio e' il censimento dei punti di registrazione in
`tests/shared/test_stdout_contract.py`, che legge i `def register_*_strategy` e
i metodi `register`: un criterio ortogonale a questo, non lo stesso ripetuto.

Il confronto e' su due piani e servono entrambi: l'insieme dei *file* dice se
e' nato un modulo che nessuno ha dichiarato, l'elenco dei *nomi* per file dice
se dentro un file dichiarato e' nata una seconda mappa. Il secondo piano
copriva i soli `CONVERTITI`, e li' il buco era misurabile: appendendo
`SONDA_STRATEGIES = {...}` a `grain_clip_strategy.py` -- un asse nuovo sulla
forma vecchia, esattamente il caso per cui il censimento esiste -- l'insieme
dei file non si muoveva e il test restava verde. Per questo `FUORI_DAL_GIRO`
porta il nome della propria mappa accanto alla ragione.
"""
import ast
import importlib
import inspect
import logging
import os

import pytest
from typing import NamedTuple

from pge.shared.exceptions import StrategyNotFoundError
from pge.shared.logger import DIAGNOSTIC_LOGGER_NAME
from pge.strategies.registry import StrategyRegistry


SRC_PGE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'pge'))


# =============================================================================
# LA FAMIGLIA, DICHIARATA
# =============================================================================

class Caso(NamedTuple):
    """Un registry della famiglia e i nomi con cui il suo modulo lo espone."""

    relpath: str
    modulo: str
    mappa: str
    kind: str
    base: str
    registrazione: str
    factory: str
    create: str
    # La facade di density non e' uniforme per decisione, non per dimenticanza:
    # vedi il docstring del modulo. Il flag esenta la *firma* e nient'altro:
    # le due guardie sulla delega valgono anche per lei, per la via qui sotto.
    create_uniforme: bool
    # I posizionali che il `create` vuole dopo la chiave. Servono a chiedere
    # l'errore di lookup a una facade che non e' `(name, **kwargs)`: senza di
    # loro density usciva anche da quella misura, e non per decisione.
    create_args_extra: tuple = ()


CONVERTITI = [
    Caso(
        relpath=os.path.join('strategies', 'voice_pan_strategy.py'),
        modulo='pge.strategies.voice_pan_strategy',
        mappa='VOICE_PAN_STRATEGIES',
        kind='voice_pan',
        base='VoicePanStrategy',
        registrazione='register_voice_pan_strategy',
        factory='VoicePanStrategyFactory',
        create='create',
        create_uniforme=True,
    ),
    Caso(
        relpath=os.path.join('strategies', 'voice_pitch_strategy.py'),
        modulo='pge.strategies.voice_pitch_strategy',
        mappa='VOICE_PITCH_STRATEGIES',
        kind='voice_pitch',
        base='VoicePitchStrategy',
        registrazione='register_voice_pitch_strategy',
        factory='VoicePitchStrategyFactory',
        create='create',
        create_uniforme=True,
    ),
    Caso(
        relpath=os.path.join('strategies', 'voice_onset_strategy.py'),
        modulo='pge.strategies.voice_onset_strategy',
        mappa='VOICE_ONSET_STRATEGIES',
        kind='voice_onset',
        base='VoiceOnsetStrategy',
        registrazione='register_voice_onset_strategy',
        factory='VoiceOnsetStrategyFactory',
        create='create',
        create_uniforme=True,
    ),
    Caso(
        relpath=os.path.join('strategies', 'voice_pointer_strategy.py'),
        modulo='pge.strategies.voice_pointer_strategy',
        mappa='VOICE_POINTER_STRATEGIES',
        kind='voice_pointer',
        base='VoicePointerStrategy',
        registrazione='register_voice_pointer_strategy',
        factory='VoicePointerStrategyFactory',
        create='create',
        create_uniforme=True,
    ),
    Caso(
        relpath=os.path.join('strategies', 'variation_registry.py'),
        modulo='pge.strategies.variation_registry',
        mappa='VARIATION_STRATEGIES',
        kind='variation',
        base='VariationStrategy',
        registrazione='register_variation_strategy',
        factory='VariationFactory',
        create='create',
        create_uniforme=True,
    ),
    Caso(
        relpath=os.path.join('strategies', 'strategy_registry.py'),
        modulo='pge.strategies.strategy_registry',
        mappa='DENSITY_STRATEGIES',
        kind='density',
        base='DensityStrategy',
        registrazione='register_density_strategy',
        factory='StrategyFactory',
        create='create_density_strategy',
        create_uniforme=False,
        create_args_extra=(None, {}),
    ),
]

# Della famiglia, ma fuori dal giro di #184/#185. Il valore e' la ragione, e il
# messaggio del censimento la cita quando uno di questi path sparisce dai
# sorgenti: e' il momento in cui serve, perche' dice che cosa sta scadendo --
# se il registry e' stato convertito la riga va spostata in CONVERTITI, se e'
# stato tolto la ragione se ne va con lui. Fin qui il messaggio nominava la
# tabella e non i suoi valori, che erano percio' morti.
FUORI_DAL_GIRO = {
    os.path.join('controllers', 'window_selection_strategy.py'):
        ('WINDOW_STRATEGY_REGISTRY', 'issue #265, dopo il tracer bullet'),
    os.path.join('strategies', 'grain_clip_strategy.py'):
        ('GRAIN_CLIP_STRATEGIES',
         'issue #265: non ha un punto di registrazione, e se debba averlo '
         'e\' parte di quella decisione'),
}

IDS = [caso.kind for caso in CONVERTITI]
UNIFORMI = [caso for caso in CONVERTITI if caso.create_uniforme]
IDS_UNIFORMI = [caso.kind for caso in UNIFORMI]


def _registry(caso):
    return getattr(importlib.import_module(caso.modulo), caso.mappa)


def _sorgente(relpath):
    with open(os.path.join(SRC_PGE, relpath), encoding='utf-8') as f:
        return f.read()


def _moduli_pge():
    """Tutti i moduli sotto `src/pge/`, path relativo a `SRC_PGE`."""
    for radice, cartelle, files in os.walk(SRC_PGE):
        cartelle[:] = [c for c in cartelle if c != '__pycache__']
        for nome in files:
            if nome.endswith('.py'):
                yield os.path.relpath(os.path.join(radice, nome), SRC_PGE)


def _mappe_di_modulo(tree):
    """I nomi delle mappe di strategy assegnate al livello del modulo."""
    nomi = []
    for nodo in tree.body:
        if isinstance(nodo, ast.Assign):
            bersagli = [t.id for t in nodo.targets if isinstance(t, ast.Name)]
        elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            bersagli = [nodo.target.id]
        else:
            continue
        nomi += [
            n for n in bersagli
            if n.endswith('_STRATEGIES') or n.endswith('_STRATEGY_REGISTRY')
        ]
    return nomi


# =============================================================================
# 1. LA MAPPA DI MODULO E' UN REGISTRY GENERICO
# =============================================================================

@pytest.mark.parametrize('caso', CONVERTITI, ids=IDS)
def test_la_mappa_di_modulo_e_un_registry_generico(caso):
    """La mappa non e' piu' un `dict` spoglio: sa il proprio dominio.

    Resta un `dict` a tutti gli effetti -- le fixture di mezza suite ne fanno
    snapshot e ripristino, e la parita' di PGE-ls ne legge le chiavi
    importandola per nome -- ma con `kind` e `base` accanto.
    """
    registry = _registry(caso)

    assert isinstance(registry, StrategyRegistry), (
        f"{caso.mappa} e' ancora sulla forma vecchia: la #185 la vuole su "
        "StrategyRegistry (docs/explanation/strategy-registry.md)."
    )
    assert isinstance(registry, dict), (
        f"{caso.mappa} deve restare un dict: le fixture ne fanno snapshot "
        "con dict()/clear()/update() e la parita' di PGE-ls ne legge le chiavi."
    )
    assert registry.kind == caso.kind, (
        f"il dominio di {caso.mappa} e' '{registry.kind}', atteso "
        f"'{caso.kind}': e' la stessa stringa che compare nello "
        "strategy_kind di StrategyNotFoundError."
    )

    modulo = importlib.import_module(caso.modulo)
    assert registry.base is getattr(modulo, caso.base), (
        f"{caso.mappa}.base non e' {caso.base}"
    )


@pytest.mark.parametrize('caso', CONVERTITI, ids=IDS)
def test_il_registry_non_e_vuoto_e_mappa_nomi_su_classi(caso):
    """Il contenuto sopravvive alla conversione, chiave per chiave.

    **E la `base` dichiarata e' vera del contenuto.** Il test qui sopra la
    confronta con `getattr(modulo, caso.base)`, cioe' chiede che il sorgente
    dica quel che dice la tabella: due grafie dello stesso nome, non una
    misura di che cosa quella classe sia. Un `Caso` nasce copiando quello
    dell'asse accanto, e li' il nome della ABC e' una delle sette righe da
    cambiare -- sbagliarla in tutte e due le grafie insieme e' esattamente la
    forma che quella copia prende. Misurato: cablando
    `StrategyRegistry('voice_pointer', VoiceOnsetStrategy, ...)` e mettendo
    `base='VoiceOnsetStrategy'` nella tabella, `make tests` restava
    interamente verde -- `base` non la legge nessuno, quindi un valore
    sbagliato e' inerte finche' qualcuno non ci costruisce sopra (la #265, o
    la decisione sulla validazione di `distribution`).

    Non e' il rifiuto che `tests/strategies/test_registry.py` vieta: li' il
    divieto e' su `StrategyRegistry.register`, che non deve **rifiutare** una
    classe duck-typed, perche' sarebbe superficie pubblica nuova. Qui non si
    rifiuta niente, si misura quel che i sei registry della famiglia gia'
    contengono.
    """
    registry = _registry(caso)

    assert len(registry) > 0, f"{caso.mappa} e' vuota"
    for nome, cls in registry.items():
        assert isinstance(nome, str) and nome, f"chiave non valida: {nome!r}"
        assert isinstance(cls, type), f"{nome} non mappa una classe: {cls!r}"
        assert issubclass(cls, registry.base), (
            f"{caso.mappa}['{nome}'] e' {cls.__name__}, che non eredita la "
            f"base dichiarata dal registry ({registry.base.__name__}): o la "
            "strategy non e' di questo dominio, o il `base` passato alla "
            "costruzione nomina la ABC di un altro asse."
        )


def test_il_censimento_della_famiglia_e_completo():
    """La famiglia e' derivata dai sorgenti, non solo dichiarata.

    Un asse nuovo nasce copiando un modulo esistente, cioe' sulla forma
    vecchia, e una tabella scritta a mano non lo vedrebbe: e' esattamente
    cosi' che `register_window_strategy` e' rimasto fuori dalla guardia della
    diagnostica finche' qualcuno non l'ha cercato.
    """
    trovate = {
        rel: nomi
        for rel in _moduli_pge()
        if (nomi := _mappe_di_modulo(ast.parse(_sorgente(rel))))
    }
    dichiarate = {caso.relpath for caso in CONVERTITI} | set(FUORI_DAL_GIRO)

    sparite = sorted(dichiarate - set(trovate))
    assert set(trovate) == dichiarate, (
        "la famiglia dei registry non e' piu' allineata ai sorgenti.\n"
        f"  solo nei sorgenti: {sorted(set(trovate) - dichiarate)}\n"
        "  solo nella tabella: "
        + ', '.join(
            f"{rel} (dichiarata fuori dal giro: {FUORI_DAL_GIRO[rel][1]})"
            if rel in FUORI_DAL_GIRO else rel
            for rel in sparite
        ) + "\n"
        "Un registry nuovo va su StrategyRegistry (CONVERTITI) oppure "
        "dichiarato fuori dal giro con la sua ragione (FUORI_DAL_GIRO)."
    )

    # Il nome della mappa e' quello che la tabella dichiara: i test qui sopra
    # la cercano per attributo, quindi un rename la farebbe sparire invece di
    # fallire.
    #
    # Vale anche per i due file fuori dal giro, che non hanno un test per
    # attributo ma hanno lo stesso buco: il confronto fra insiemi qui sopra
    # ragiona sui *file*, quindi una seconda mappa aggiunta a un file gia'
    # dichiarato non sposta nessun insieme. Misurato: appendendo
    # `SONDA_STRATEGIES = {...}` a `grain_clip_strategy.py` — cioe' un asse
    # nuovo sulla forma vecchia, esattamente il caso per cui il censimento
    # esiste — questo test restava verde. Un file dichiarato espone una mappa
    # e quella soltanto.
    attese = {caso.relpath: [caso.mappa] for caso in CONVERTITI}
    attese.update({rel: [mappa] for rel, (mappa, _) in FUORI_DAL_GIRO.items()})
    for rel, nomi in attese.items():
        assert trovate[rel] == nomi, (
            f"{rel} non espone piu' {nomi} ma {trovate[rel]}"
        )


# =============================================================================
# 2. IL `register_*` DI MODULO DELEGA AL REGISTRY
# =============================================================================

@pytest.mark.parametrize('caso', CONVERTITI, ids=IDS)
def test_la_registrazione_delega_al_registry(caso, caplog):
    """Una registrazione, una riga diagnostica, col dominio del registry.

    Le due meta' sono una sola misura. Pitch, onset e pointer non emettevano
    niente (zero righe), density e variation la emettevano con un letterale
    scritto accanto alla chiamata: se il `register_*` si limita a delegare, il
    conteggio dice che non c'e' una seconda copia e il testo dice che
    l'etichetta viene dal `kind`.
    """
    modulo = importlib.import_module(caso.modulo)
    registry = _registry(caso)
    registra = getattr(modulo, caso.registrazione)

    class StrategyDiProva(getattr(modulo, caso.base)):
        pass

    nome = '_convergenza_di_prova'
    try:
        with caplog.at_level(logging.DEBUG, logger=DIAGNOSTIC_LOGGER_NAME):
            registra(nome, StrategyDiProva)

        assert registry[nome] is StrategyDiProva

        messaggi = [r.getMessage() for r in caplog.records
                    if r.name == DIAGNOSTIC_LOGGER_NAME]
        assert len(messaggi) == 1, (
            f"{caso.registrazione} ha prodotto {len(messaggi)} righe "
            "diagnostiche invece di una: zero significa che non delega a "
            "StrategyRegistry.register, due che il modulo tiene anche la "
            "propria chiamata a log_strategy_registration."
        )
        assert caso.kind in messaggi[0], (
            f"la riga diagnostica di {caso.registrazione} non nomina il "
            f"dominio '{caso.kind}': {messaggi[0]!r}"
        )
        assert nome in messaggi[0]
        assert 'StrategyDiProva' in messaggi[0]
    finally:
        registry.pop(nome, None)


@pytest.mark.parametrize('caso', CONVERTITI, ids=IDS)
def test_la_registrazione_resta_una_def_di_modulo(caso):
    """Non un alias di `REGISTRY.register`.

    La guardia della diagnostica in `tests/shared/test_stdout_contract.py`
    cerca `def register_*_strategy` di livello modulo: un alias farebbe uscire
    il modulo dal censimento, che e' il solo posto dove il divieto di stampare
    e' scritto. E' la #177 a vietarlo, in «Implicazioni codice».
    """
    tree = ast.parse(_sorgente(caso.relpath))
    definizioni = [
        nodo.name for nodo in tree.body
        if isinstance(nodo, ast.FunctionDef)
    ]

    assert caso.registrazione in definizioni, (
        f"{caso.registrazione} non e' piu' una def di livello modulo in "
        f"{caso.relpath}"
    )


# =============================================================================
# 3. IL `create()` DELLA FACTORY DELEGA AL REGISTRY
# =============================================================================

def _corpo_di_create(caso):
    """Il nodo AST del `create` della factory dichiarata dal caso."""
    tree = ast.parse(_sorgente(caso.relpath))
    corpi = [
        figlio for classe in ast.walk(tree)
        if isinstance(classe, ast.ClassDef) and classe.name == caso.factory
        for figlio in classe.body
        if isinstance(figlio, ast.FunctionDef) and figlio.name == caso.create
    ]

    assert len(corpi) == 1, (
        f"{caso.factory}.{caso.create} non trovato in {caso.relpath}"
    )
    return corpi[0]


def _nome_finale(espressione):
    """Il nome finale di un'espressione, `attr` o `id`, o `None`.

    **Le due grafie contano entrambe**, e leggere il solo `ast.Name` rendeva
    la guardia qui sotto piu' stretta della regola che dichiara -- lo stesso
    difetto che questa issue ha gia' corretto due volte. Misurato: rimettendo
    in `create_density_strategy` il `raise` che la #185 ha tolto, scritto
    `exc.StrategyNotFoundError(...)` con `from pge.shared import exceptions
    as exc` (la grafia che `tests/shared/test_engine_exceptions.py` gia' usa),
    `tests/strategies/` e `tests/shared/` restavano verdi: la copia esatta che
    la #177 ha visto divergere rientrava dalla porta di servizio, e proprio
    sull'unico caso -- density -- che la guardia severa non copre.

    Che l'eccezione arrivi da un import diretto o da un modulo importato per
    nome non cambia che cosa il `create` sta ricostruendo. Resta fuori un
    alias d'import (`from ... import StrategyNotFoundError as X`): il nome
    finale e' allora un altro, e leggerlo vorrebbe risolvere gli import del
    modulo.
    """
    if isinstance(espressione, ast.Attribute):
        return espressione.attr
    return espressione.id if isinstance(espressione, ast.Name) else None


def _ricostruisce(nodo, eccezione):
    """Se `nodo` costruisce o alza `eccezione`.

    **La costruzione, non solo il `raise`.** Leggere l'eccezione dentro il
    `raise` lasciava fuori la grafia in due tempi -- `errore =
    StrategyNotFoundError(...)` e poi `raise errore` -- dove il `raise` nomina
    una variabile e la copia sta una riga sopra. Misurato: scritto cosi' in
    `create_density_strategy`, `tests/strategies/` e `tests/shared/`
    restavano verdi, ancora sull'unico caso che la guardia severa non copre.
    Resta il `raise` della classe nuda (`raise StrategyNotFoundError`), che
    la istanzia senza una `Call` scritta.
    """
    if isinstance(nodo, ast.Call):
        return _nome_finale(nodo.func) == eccezione
    if isinstance(nodo, ast.Raise):
        return _nome_finale(nodo.exc) == eccezione
    return False


@pytest.mark.parametrize('caso', CONVERTITI, ids=IDS)
def test_create_non_ricostruisce_strategy_not_found(caso):
    """Nessun `create` della famiglia riscrive l'errore di lookup.

    Il criterio nomina una sola eccezione, ed e' quel che le permette di
    valere anche dove `create` ha il diritto di alzare qualcosa di suo: su
    density, che prima non aveva nessuna guardia sulla delega.
    `create_uniforme=False` la escludeva da entrambe le misure sulla delega,
    ma quel flag dichiara un'esenzione sulla *firma*: il lookup density lo
    delega come gli altri cinque. Misurato: rimettendo in
    `create_density_strategy` il `raise StrategyNotFoundError` che la #185 ha
    tolto -- la copia esatta che la #177 ha visto divergere -- `make tests`
    restava interamente verde.

    Il comportamento non puo' discriminare: una copia scritta a mano alza la
    stessa classe, col dominio giusto e con `available` letto dal registry
    vivo, quindi supera ogni asserzione sull'eccezione. Solo il sorgente lo
    dice.
    """
    ricostruzioni = [
        n for n in ast.walk(_corpo_di_create(caso))
        if _ricostruisce(n, 'StrategyNotFoundError')
    ]

    assert not ricostruzioni, (
        f"{caso.factory}.{caso.create} ricostruisce StrategyNotFoundError "
        "per conto proprio: il lookup e il suo errore vivono in "
        "StrategyRegistry.create, la facade delega."
    )


@pytest.mark.parametrize('caso', UNIFORMI, ids=IDS_UNIFORMI)
def test_create_non_alza_l_errore_per_conto_proprio(caso):
    """Sulle cinque facade di solo lookup il corpo non alza **niente**.

    Le due guardie si dividono il lavoro per criterio e per popolazione, e le
    due divisioni vanno in senso opposto. Questa ha il criterio piu' severo --
    qualunque `raise`, non una classe nominata -- e la popolazione piu'
    stretta: vale dove non c'e' nessuna regola di costruzione da difendere,
    quindi dove ogni `raise` e' codice che il registry gia' fa. Density ha la
    propria validazione, percio' il criterio severo non le si puo' applicare e
    la copre quella qui sopra, che nomina una sola eccezione ma le vale su
    tutte e sei.
    """
    alza = [n for n in ast.walk(_corpo_di_create(caso)) if isinstance(n, ast.Raise)]
    assert not alza, (
        f"{caso.factory}.{caso.create} alza ancora un'eccezione per conto "
        "proprio: il lookup e StrategyNotFoundError vivono in "
        "StrategyRegistry.create, la factory delega."
    )


@pytest.mark.parametrize('caso', CONVERTITI, ids=IDS)
def test_create_alza_strategy_not_found_con_il_dominio_del_registry(caso):
    """La delega non cambia l'errore che il chiamante vede.

    `available` e' letto dal registry vivo, non da una lista scritta nel
    modulo: una strategy registrata a runtime compare fra le disponibili.

    Density e' qui come gli altri cinque, per i posizionali che `Caso`
    dichiara: la sua firma non e' uniforme, il suo errore di lookup si'. A
    tenerla fuori era il flag della firma, e l'esenzione era piu' larga della
    sua ragione.
    """
    modulo = importlib.import_module(caso.modulo)
    registry = _registry(caso)
    crea = getattr(getattr(modulo, caso.factory), caso.create)

    class StrategyDiProva(getattr(modulo, caso.base)):
        pass

    nome = '_convergenza_disponibile'
    try:
        registry[nome] = StrategyDiProva

        with pytest.raises(StrategyNotFoundError) as info:
            crea('_nome_che_nessuno_registra', *caso.create_args_extra)

        err = info.value
        assert err.strategy_kind == caso.kind
        assert err.name == '_nome_che_nessuno_registra'
        assert nome in err.available, (
            "available non viene dal registry vivo"
        )
    finally:
        registry.pop(nome, None)


@pytest.mark.parametrize('caso', CONVERTITI, ids=IDS)
def test_la_factory_resta_un_metodo_statico(caso):
    """La facade e' uno `@staticmethod` che delega, non un alias.

    Un alias di metodo legato passerebbe il comportamento e cambierebbe la
    superficie: `StrategyFactory.__dict__['create_density_strategy']` e'
    pinnato come `staticmethod` da `tests/strategies/test_strategies.py`, e la
    #177 estende la regola a tutte le facade.
    """
    factory = getattr(importlib.import_module(caso.modulo), caso.factory)

    assert isinstance(factory.__dict__[caso.create], staticmethod), (
        f"{caso.factory}.{caso.create} non e' piu' uno staticmethod"
    )


# =============================================================================
# 4. LE FIRME SONO UNIFORMI
# =============================================================================

@pytest.mark.parametrize('caso', CONVERTITI, ids=IDS)
def test_il_primo_parametro_della_registrazione_si_chiama_name(caso):
    """`mode_name` e `param_name` dicevano da dove viene il valore.

    Quello che e' -- la chiave del registry -- si chiama `name`, e la classe
    `strategy_class`. Criterio della #185: le firme dei `register_*` sono
    uniformi fra tutte.
    """
    modulo = importlib.import_module(caso.modulo)
    parametri = list(
        inspect.signature(getattr(modulo, caso.registrazione)).parameters)

    assert parametri[:2] == ['name', 'strategy_class'], (
        f"{caso.registrazione}{tuple(parametri)}: la #185 vuole "
        "(name, strategy_class)"
    )


@pytest.mark.parametrize('caso', UNIFORMI, ids=IDS_UNIFORMI)
def test_il_primo_parametro_di_create_si_chiama_name(caso):
    """Lo stesso, sul `create()` delle factory di solo lookup.

    Fuori resta `create_density_strategy`, che tiene la propria firma perche'
    tiene la propria validazione: vedi il docstring del modulo.
    """
    modulo = importlib.import_module(caso.modulo)
    crea = getattr(getattr(modulo, caso.factory), caso.create)
    parametri = list(inspect.signature(crea).parameters)

    assert parametri[0] == 'name', (
        f"{caso.factory}.{caso.create}{tuple(parametri)}: il primo parametro "
        "e' la chiave del registry e si chiama `name`"
    )


def test_la_firma_della_classe_generica_e_quella_delle_sei_facade():
    """La convergenza non si ferma un livello sopra chi la esegue.

    Le due guardie qui sopra leggono le sei `register_*` di modulo e i cinque
    `create` di solo lookup, cioe' le *facade*. Ma la registrazione la fa
    `StrategyRegistry.register`, a cui tutte e sei delegano, e per il
    censimento di `tests/shared/test_stdout_contract.py` quello e' un punto di
    registrazione come gli altri: `_funzioni_di_registrazione` enumera le `def
    register_*_strategy` di modulo **e** i metodi chiamati `register` dentro
    una classe.

    Il suo secondo parametro si chiamava `cls` -- esattamente il nome da cui
    pitch, onset e pointer sono stati convertiti in questa issue -- quindi la
    misura, letta solo sulle facade, lasciava `cls` vivo nell'unico punto che
    le serve tutte e sei: il nome da cui si converte sopravviveva sotto quello
    a cui si converge. Nessuna chiamata viva passa i due argomenti per parola
    chiave (misurato: in `src/` e in `tests/` ogni `.register(` e'
    posizionale), quindi la convergenza qui non rompe niente piu' di quanto ne
    rompesse sulle facade.
    """
    parametri = list(inspect.signature(StrategyRegistry.register).parameters)
    assert parametri[1:] == ['name', 'strategy_class'], (
        f"StrategyRegistry.register{tuple(parametri)}: la #185 vuole "
        "(name, strategy_class), la stessa firma delle sei facade che "
        "delegano qui"
    )

    parametri = list(inspect.signature(StrategyRegistry.create).parameters)
    assert parametri[1] == 'name', (
        f"StrategyRegistry.create{tuple(parametri)}: il primo parametro e' "
        "la chiave del registry e si chiama `name`"
    )


# =============================================================================
# 5. LE COSTANTI ACCANTO AL REGISTRY NON SONO STATE TRASCINATE DENTRO
# =============================================================================

# Gli attributi che la classe generica da' a **ogni** registry. Derivati da
# un'istanza, non trascritti: aggiungerne uno a `StrategyRegistry` e' una
# decisione sulla forma, e la guardia qui sotto non deve accusarla.
SUPERFICIE_GENERICA = frozenset(vars(StrategyRegistry('_sonda', object)))


@pytest.mark.parametrize('caso', CONVERTITI, ids=IDS)
def test_nessun_registry_porta_una_superficie_per_dominio(caso):
    """Sull'oggetto registry non si attacca niente che sia di un dominio solo.

    E' il divieto della #177 -- la classe e' generica, e una costante
    attaccata a un'istanza le darebbe una superficie che gli altri cinque non
    hanno -- misurato sull'intera superficie d'istanza invece che su un nome
    ipotizzato. Il candidato vivo e' `SEMITONE_LOCKED`, e la guardia che
    c'era chiedeva `semitone_locked`: la grafia minuscola, che la costante non
    ha in nessun punto dell'albero. Misurato: scrivendo
    `VOICE_PITCH_STRATEGIES.SEMITONE_LOCKED = SEMITONE_LOCKED` -- cioe'
    facendo esattamente la mossa vietata -- `tests/strategies/` e
    `tests/shared/` restavano verdi.

    Confrontare le chiavi di `vars()` con quelle di un registry appena
    costruito non ipotizza nessun nome, quindi vale anche per la costante che
    a qualcuno verra' in mente domani.
    """
    registry = _registry(caso)
    # `vars()` di un `dict` spoglio alza TypeError: un registry tornato sulla
    # forma vecchia farebbe morire questa misura sulla premessa di un'altra,
    # che quel caso lo dice col proprio messaggio
    # (test_la_mappa_di_modulo_e_un_registry_generico). Senza `__dict__` non
    # c'e' niente di attaccato, che e' la risposta giusta alla domanda di qui.
    attaccati = sorted(set(getattr(registry, '__dict__', {})) - SUPERFICIE_GENERICA)

    assert not attaccati, (
        f"{caso.mappa} porta attributi che la classe generica non da' a "
        f"tutti: {attaccati}. Una costante di dominio resta un nome di "
        "modulo -- attaccarla al registry e' il caso speciale che la #177 "
        "vieta (docs/explanation/strategy-registry.md)."
    )


def test_semitone_locked_resta_un_nome_di_modulo_allineato_al_registry():
    """`SEMITONE_LOCKED` e' un'affermazione sulle unita', non contenuto.

    La legge `Stream._take_voice_pitch_keys` importandola per nome, e resta un
    `frozenset` di chiavi del registry. Che non sia attaccata all'oggetto
    registry lo dice la guardia qui sopra, per tutti e sei e senza ipotizzare
    la grafia; qui restano le due cose che sono sue: il tipo, e
    l'allineamento alle chiavi.
    """
    from pge.strategies.voice_pitch_strategy import (
        SEMITONE_LOCKED,
        VOICE_PITCH_STRATEGIES,
    )

    assert isinstance(SEMITONE_LOCKED, frozenset)
    assert SEMITONE_LOCKED <= set(VOICE_PITCH_STRATEGIES), (
        "SEMITONE_LOCKED nomina strategy che il registry non ha: "
        f"{sorted(SEMITONE_LOCKED - set(VOICE_PITCH_STRATEGIES))}"
    )
    # Le due asserzioni qui sopra sono entrambe soddisfatte dal vuoto --
    # `isinstance(frozenset(), frozenset)` e' vero e l'insieme vuoto e'
    # sottoinsieme di tutto -- quindi da sole non vedono la regressione che
    # conta: `Stream._take_voice_pitch_keys` legge questo insieme per *rifiutare*
    # `voices.pitch.unit` diverso da semitones sulle strategy definite in
    # semitoni, e svuotarlo fa cadere quel rifiuto in silenzio (un `chord` con
    # `unit: cents` renderebbe gli intervalli reinterpretati, senza errore).
    # Il verso giusto e' il contenimento: una quarta strategy locked e' una
    # decisione legittima, che queste tre se ne vadano no.
    assert {'chord', 'chord_progression', 'spectral'} <= SEMITONE_LOCKED, (
        "SEMITONE_LOCKED ha perso strategy definite in semitoni: "
        f"{sorted({'chord', 'chord_progression', 'spectral'} - SEMITONE_LOCKED)}. "
        "Senza di loro Stream._take_voice_pitch_keys smette di rifiutare "
        "`voices.pitch.unit` non-semitones su quelle strategy."
    )


def test_chord_intervals_resta_un_nome_di_modulo():
    """`CHORD_INTERVALS` e' il dominio di un kwarg, non del registry.

    La importa per nome il test di parita' di PGE-ls (#269): il costo di
    spostarla si paga in un altro repo, dove questa suite non arriva.
    """
    from pge.strategies.voice_pitch_strategy import CHORD_INTERVALS

    assert isinstance(CHORD_INTERVALS, dict) and CHORD_INTERVALS
    for nome, intervalli in CHORD_INTERVALS.items():
        assert isinstance(nome, str) and nome
        # `all(...)` su una lista vuota e' vero, quindi il solo controllo di
        # tipo lascia passare un accordo svuotato: quello arriva a
        # `ChordPitchStrategy` e produce zero offset -- tutte le voci sullo
        # stesso pitch, in silenzio -- e la parita' di PGE-ls confronta gli
        # insiemi di chiavi, quindi non lo vedrebbe nemmeno lei.
        assert intervalli, (
            f"l'accordo '{nome}' non porta intervalli: a valle sono zero "
            "offset, cioe' tutte le voci sullo stesso pitch senza errore"
        )
        assert all(isinstance(i, int) for i in intervalli)
