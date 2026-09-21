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
   e la guardia e' sul *corpo* di `create` -- nessun `raise` -- perche' il
   comportamento da solo non distingue una delega da una quinta copia della
   stessa riga.

Piu' la convergenza delle firme, che e' un criterio della #185 e non un gusto:
il primo parametro si chiama `name` ovunque (`variation_mode`, `mode_name` e
`param_name` dicevano da dove viene il valore, non che cosa e' -- la chiave del
registry) e il secondo `strategy_class`. Tutti i chiamanti vivi li passano
posizionalmente (misurato: nessuna chiamata per parola chiave in `src/` o in
`tests/`), quindi la convergenza non rompe niente.

**Chi resta fuori, e perche' e' dichiarato qui invece che dedotto.**
`StrategyFactory.create_density_strategy` non e' nel giro delle firme uniformi:
tiene la propria (`selected_param_name, param_obj, all_params`) e la propria
validazione, che non e' lookup ma una regola su come si costruisce una strategy
di density. L'ordine fra le due -- lookup prima, validazione dopo -- decide il
tipo dell'eccezione quando entrambe le condizioni sono vive, ed e' pinnato in
`tests/strategies/test_registry_errors.py`, non qui.

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
    # vedi il docstring del modulo.
    create_uniforme: bool


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
    ),
]

# Della famiglia, ma fuori dal giro di #184/#185. Il valore e' la ragione, ed
# e' li' perche' il messaggio di un censimento rosso la deve poter citare.
FUORI_DAL_GIRO = {
    os.path.join('controllers', 'window_selection_strategy.py'):
        'issue #265, dopo il tracer bullet',
    os.path.join('strategies', 'grain_clip_strategy.py'):
        'issue #265: non ha un punto di registrazione, e se debba averlo '
        'e\' parte di quella decisione',
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
    """Il contenuto sopravvive alla conversione, chiave per chiave."""
    registry = _registry(caso)

    assert len(registry) > 0, f"{caso.mappa} e' vuota"
    for nome, cls in registry.items():
        assert isinstance(nome, str) and nome, f"chiave non valida: {nome!r}"
        assert isinstance(cls, type), f"{nome} non mappa una classe: {cls!r}"


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

    assert set(trovate) == dichiarate, (
        "la famiglia dei registry non e' piu' allineata ai sorgenti.\n"
        f"  solo nei sorgenti: {sorted(set(trovate) - dichiarate)}\n"
        f"  solo nella tabella: {sorted(dichiarate - set(trovate))}\n"
        "Un registry nuovo va su StrategyRegistry (CONVERTITI) oppure "
        "dichiarato fuori dal giro con la sua ragione (FUORI_DAL_GIRO)."
    )

    # Il nome della mappa e' quello che la tabella dichiara: i test qui sopra
    # la cercano per attributo, quindi un rename la farebbe sparire invece di
    # fallire.
    for caso in CONVERTITI:
        assert trovate[caso.relpath] == [caso.mappa], (
            f"{caso.relpath} non espone piu' {caso.mappa} ma "
            f"{trovate[caso.relpath]}"
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

@pytest.mark.parametrize('caso', UNIFORMI, ids=IDS_UNIFORMI)
def test_create_non_alza_l_errore_per_conto_proprio(caso):
    """Il corpo di `create` non contiene `raise`: il lookup e' del registry.

    Il comportamento da solo non discrimina -- un `create` che ricostruisce
    `StrategyNotFoundError` a mano supera il test qui sotto -- e ricostruirlo
    e' proprio la duplicazione che la #177 ha misurato divergere.
    """
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
    alza = [n for n in ast.walk(corpi[0]) if isinstance(n, ast.Raise)]
    assert not alza, (
        f"{caso.factory}.{caso.create} alza ancora un'eccezione per conto "
        "proprio: il lookup e StrategyNotFoundError vivono in "
        "StrategyRegistry.create, la factory delega."
    )


@pytest.mark.parametrize('caso', UNIFORMI, ids=IDS_UNIFORMI)
def test_create_alza_strategy_not_found_con_il_dominio_del_registry(caso):
    """La delega non cambia l'errore che il chiamante vede.

    `available` e' letto dal registry vivo, non da una lista scritta nel
    modulo: una strategy registrata a runtime compare fra le disponibili.
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
            crea('_nome_che_nessuno_registra')

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


# =============================================================================
# 5. LE COSTANTI ACCANTO AL REGISTRY NON SONO STATE TRASCINATE DENTRO
# =============================================================================

def test_semitone_locked_resta_un_nome_di_modulo_allineato_al_registry():
    """`SEMITONE_LOCKED` e' un'affermazione sulle unita', non contenuto.

    La legge `Stream._init_voice_manager` importandola per nome, e resta un
    `frozenset` di chiavi del registry: attaccarla all'oggetto registry
    darebbe alla classe generica una superficie per dominio, cioe' il caso
    speciale che la #177 vieta.
    """
    from pge.strategies.voice_pitch_strategy import (
        SEMITONE_LOCKED,
        VOICE_PITCH_STRATEGIES,
    )

    assert isinstance(SEMITONE_LOCKED, frozenset)
    assert not hasattr(VOICE_PITCH_STRATEGIES, 'semitone_locked')
    assert SEMITONE_LOCKED <= set(VOICE_PITCH_STRATEGIES), (
        "SEMITONE_LOCKED nomina strategy che il registry non ha: "
        f"{sorted(SEMITONE_LOCKED - set(VOICE_PITCH_STRATEGIES))}"
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
        assert all(isinstance(i, int) for i in intervalli)
