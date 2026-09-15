"""
La copertura di un target e' dichiarata, non scoperta a meta' render.

Il difetto che la #202 chiude: `NumpyWindowRegistry.available_windows()`
restituiva `WindowRegistry.all_names()` -- il registry *dichiarava* di saper
generare tutti i nomi del catalogo, mentre `_generate()` poteva sollevare
`InvalidWindowError` per un nome che i suoi dizionari interni non conoscevano.
Aggiungere una finestra al solo catalogo Csound superava la validazione YAML e
falliva a meta' rendering.

Qui la relazione e' rovesciata: la copertura la dichiara l'emitter
(`supports`), il catalogo si limita a descrivere, e la guardia gira su **ogni
emitter registrato** invece di essere cablata su NumPy.
"""

import numpy as np
import pytest

from pge.controllers.window_emitter import WindowEmitter
from pge.controllers.window_registry import (
    WindowRegistry,
    WindowShape,
    WindowSpec,
)
from pge.rendering.csound_window_emitter import GenTable
from pge.rendering.numpy_window_emitter import NumpyWindowEmitter
from pge.rendering.numpy_window_registry import NumpyWindowRegistry
from pge.rendering.window_emitters import all_window_emitters
from pge.shared.exceptions import InvalidWindowError


RESOLUTION = 128

EMITTERS = all_window_emitters()
EMITTER_IDS = [emitter.target for emitter in EMITTERS]


class _AlienSpec:
    """Una spec con una forma che nessun emitter conosce.

    Non e' una `WindowSpec`: il costruttore rifiuta una forma fuori
    vocabolario, ed e' giusto cosi' -- una forma inventata e' un errore di
    catalogo, non una lacuna di target. Serve pero' un modo per interrogare
    `supports()` su una forma ignota, e questo e' il minimo che gli emitter
    leggono.
    """

    name = 'tukey'
    shape = 'tapered_cosine'
    coefficients = ()
    params = {}

    def param(self, key, default=None):
        return self.params.get(key, default)


class _BareSpec:
    """Una spec-like che dichiara una forma e nient'altro.

    Non e' una `WindowSpec` per la stessa ragione di `_AlienSpec`: dalla
    guardia sulla completezza il costruttore rifiuta una descrizione a cui
    manca un campo che la sua forma legge, quindi una spec cosi' non e'
    costruibile. Resta pero' interrogabile, ed e' il caso per cui
    `supports()` prende uno spec-like: una descrizione che arriva da fuori
    dal catalogo -- un plugin, un test, un ramo a meta' -- e che il target
    deve saper rifiutare da se'.
    """

    def __init__(self, shape):
        self.name = f'bare_{shape}'
        self.shape = shape
        self.coefficients = ()
        self.params = {}

    def param(self, key, default=None):
        return self.params.get(key, default)


class _PlainSpec:
    """Una spec-like che espone i suoi `params` e *non* il metodo `param()`.

    E' la forma minima che il contratto dichiara di accettare:
    `missing_shape_fields` legge i parametri con `getattr(spec, 'params')`,
    quindi a uno spec-like basta quell'attributo. Gli emitter leggevano
    invece `spec.param(key)` -- un metodo che ha solo `WindowSpec` -- ed e'
    la seconda porta da cui la stessa domanda usciva con una risposta
    diversa: `NumpyWindowEmitter.supports()` rispondeva di si' e
    `materialize()` moriva con un `AttributeError` (non l'`InvalidWindowError`
    che il contratto promette), mentre `CsoundWindowEmitter.supports()` --
    che deve restituire un booleano -- alzava `AttributeError` da se'.

    E' il difetto della #202 sull'accessorio invece che sulla forma:
    dichiarato e reale che divergono dentro lo stesso oggetto.
    """

    def __init__(self, shape, params=None, coefficients=()):
        self.name = f'plain_{shape}'
        self.shape = shape
        self.coefficients = coefficients
        self.params = dict(params or {})


def _artifact_is_well_formed(artifact):
    """Un artefatto materializzato non porta buchi dentro.

    Il tipo di ritorno e' quello del target -- e' il contratto -- quindi la
    domanda si pone sull'artefatto e non sul nome dell'emitter: un array di
    finestra e' finito e non identicamente nullo, una `GenTable` non ha un
    `None` fra i p-field (`f 7 0 1024 20 7 1 None` e' una riga che Csound
    rifiuta). Un target nuovo che restituisca altro va aggiunto qui, come
    agli oracoli della suite di parita'.
    """
    if isinstance(artifact, np.ndarray):
        return bool(np.all(np.isfinite(artifact)) and np.any(artifact != 0.0))
    if isinstance(artifact, GenTable):
        return all(p is not None for p in artifact.params)

    raise AssertionError(
        f"artefatto di tipo {type(artifact).__name__} non previsto: un "
        f"target nuovo va aggiunto a questa lettura."
    )


class _FakeCatalogue:
    """Un catalogo con dentro una spec che un target non sa esprimere."""

    def __init__(self, extra):
        self._extra = extra

    def all_names(self):
        return WindowRegistry.all_names() + [self._extra.name]

    def get(self, name):
        if name == self._extra.name:
            return self._extra
        return WindowRegistry.get(name)


# =============================================================================
# 1. OGNI SPEC DEL CATALOGO E' MATERIALIZZABILE DA OGNI EMITTER REGISTRATO
# =============================================================================

class TestEveryEmitterCoversTheCatalogue:
    """La guardia anti-drift della #202, generalizzata a N target."""

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    def test_no_catalogue_name_is_uncovered(self, emitter):
        assert emitter.uncovered_names() == [], (
            f"il target '{emitter.target}' non sa materializzare "
            f"{emitter.uncovered_names()}: o si aggiunge la traduzione, o la "
            f"finestra non entra nel catalogo"
        )

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    def test_every_catalogue_name_materializes(self, emitter):
        for name in WindowRegistry.all_names():
            spec = WindowRegistry.get(name)
            assert emitter.materialize(spec, RESOLUTION) is not None, name

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    def test_covered_names_are_the_catalogue_names(self, emitter):
        assert set(emitter.covered_names()) == set(WindowRegistry.all_names())

    def test_there_is_more_than_one_emitter(self):
        """La guardia parametrizzata sarebbe una guardia su NumPy travestita
        se il registro dei target ne contenesse uno solo."""
        assert len(EMITTERS) >= 2
        assert {'csound', 'numpy'} <= set(EMITTER_IDS)

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    def test_every_emitter_honours_the_contract(self, emitter):
        assert isinstance(emitter, WindowEmitter)


# =============================================================================
# 2. UNA SPEC FUORI COPERTURA SI DICHIARA, NON ESPLODE AL RENDER
# =============================================================================

class TestUncoveredSpecIsDeclared:

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    def test_alien_shape_is_not_supported(self, emitter):
        assert emitter.supports(_AlienSpec()) is False

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    def test_alien_shape_shows_up_as_uncovered(self, emitter):
        catalogue = _FakeCatalogue(_AlienSpec())

        assert emitter.uncovered_names(catalogue) == ['tukey']
        assert 'tukey' not in emitter.covered_names(catalogue)

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    def test_materializing_an_alien_shape_names_the_target(self, emitter):
        with pytest.raises(InvalidWindowError) as exc_info:
            emitter.materialize(_AlienSpec(), RESOLUTION)

        message = str(exc_info.value)
        assert emitter.target in message
        assert 'tapered_cosine' in message

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    def test_a_spec_like_without_a_name_is_still_refused_as_promised(
            self, emitter):
        """Il rifiuto e' un `InvalidWindowError`, anche quando la spec-like
        e' meno di quanto il catalogo garantisce.

        `supports()` prende uno spec-*like* di proposito, e `missing_shape_fields`
        lo legge con `getattr` per questo. Il messaggio del rifiuto leggeva
        invece `spec.name` per attributo: una descrizione arrivata da fuori --
        un plugin, un ramo a meta' -- usciva con un `AttributeError`, cioe'
        con l'eccezione sbagliata proprio nel punto che esiste per dare quella
        giusta.
        """
        class _NamelessSpec:
            shape = WindowShape.GAUSSIAN
            coefficients = ()
            params = {}

            def param(self, key, default=None):
                return self.params.get(key, default)

        with pytest.raises(InvalidWindowError) as exc_info:
            emitter.materialize(_NamelessSpec(), RESOLUTION)

        assert emitter.target in str(exc_info.value)
        assert 'sigma' in str(exc_info.value)

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    def test_non_positive_resolution_is_refused(self, emitter):
        spec = WindowRegistry.get('hanning')

        for bad in (0, -1):
            with pytest.raises(InvalidWindowError):
                emitter.materialize(spec, bad)

    def test_csound_cannot_express_an_arbitrary_cosine_sum(self):
        """La partita' non e' un dettaglio teorico: GEN20 implementa un menu
        chiuso di finestre, quindi una somma di coseni con altri coefficienti
        (flat-top, Nuttall) e' esprimibile in NumPy e non in Csound.

        E' esattamente il caso che deve essere *dichiarato*: senza copertura
        il nome passerebbe la validazione e morirebbe nello score.
        """
        from pge.rendering.csound_window_emitter import CsoundWindowEmitter

        flat_top = WindowSpec(
            name='flat_top',
            shape=WindowShape.COSINE_SUM,
            coefficients=(0.21557895, 0.41663158, 0.277263158,
                          0.083578947, 0.006947368),
            description="Flat-top window",
        )

        assert NumpyWindowEmitter().supports(flat_top) is True
        assert CsoundWindowEmitter().supports(flat_top) is False


# =============================================================================
# 2bis. UNA DESCRIZIONE INCOMPLETA E' FUORI COPERTURA, PER OGNI TARGET
# =============================================================================

class TestIncompleteSpecIsDeclared:
    """La stessa lezione della classe sopra, un livello piu' in basso.

    Li' la spec descrive una forma che il target non conosce; qui descrive
    una forma nota *senza i campi che quella forma legge*. La prima e' una
    lacuna di copertura, la seconda una descrizione che nessun target puo'
    leggere -- ma il modo di fallire era lo stesso, e peggiore: `supports()`
    rispondeva di si' guardando solo il nome della forma, e il prezzo lo
    pagava chi rendeva. NumPy valutava la formula con un `None` dentro
    (`TypeError`, non l'`InvalidWindowError` che il contratto promette) o,
    per una somma di coseni vuota, restituiva un array di zeri -- un grano
    reso come silenzio digitale, senza errore. Csound scriveva il `None` nel
    p-field: `f 7 0 1024 20 7 1 None`, morto a meta' render.
    """

    PARAMETRIC = sorted(set(WindowShape.REQUIRED_PARAMS)
                        | WindowShape.REQUIRES_COEFFICIENTS)

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    @pytest.mark.parametrize("shape", PARAMETRIC)
    def test_a_shape_without_its_fields_is_not_supported(self, emitter, shape):
        assert emitter.supports(_BareSpec(shape)) is False

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    @pytest.mark.parametrize("shape", PARAMETRIC)
    def test_materializing_it_raises_instead_of_guessing(self, emitter, shape):
        with pytest.raises(InvalidWindowError) as exc_info:
            emitter.materialize(_BareSpec(shape), RESOLUTION)

        assert emitter.target in str(exc_info.value)

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    def test_the_message_names_the_field_that_is_missing(self, emitter):
        """Il messaggio serve a sapere cosa scrivere nel catalogo, quindi
        nomina il campo e non la tabella di traduzione del target: prima, la
        gaussiana senza sigma rispondeva 'l'apertura GEN20 per sigma=None non
        e' nota', che manda a cercare la cosa sbagliata."""
        with pytest.raises(InvalidWindowError) as exc_info:
            emitter.materialize(_BareSpec(WindowShape.GAUSSIAN), RESOLUTION)

        assert 'sigma' in str(exc_info.value)

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    def test_it_shows_up_as_uncovered(self, emitter):
        catalogue = _FakeCatalogue(_BareSpec(WindowShape.KAISER))

        assert emitter.uncovered_names(catalogue) == ['bare_kaiser']
        assert 'bare_kaiser' not in emitter.covered_names(catalogue)

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    @pytest.mark.parametrize("shape", sorted(WindowShape.ALL))
    def test_what_a_bare_spec_does_materialize_is_well_formed(
            self, emitter, shape):
        """La misura, e l'altra meta' della guardia.

        Rifiutare tutto la renderebbe verde a vuoto: le forme che non leggono
        parametri -- rettangolare, triangolare, i due lobi -- una spec spoglia
        la descrive per intero, e devono materializzarsi. Quello che *non*
        puo' succedere e' che una spec spoglia venga accettata e produca un
        artefatto con un buco dentro: un array non finito o identicamente
        nullo, un p-field `None`. Il controllo e' sull'artefatto, quindi vale
        anche per il target che verra'.
        """
        spec = _BareSpec(shape)

        if not emitter.supports(spec):
            pytest.skip(f"'{shape}' non e' descritta da una spec spoglia")

        assert _artifact_is_well_formed(emitter.materialize(spec, RESOLUTION))

    def test_some_shape_survives_a_bare_spec(self):
        """Il test sopra e' fatto di skip se ogni forma chiede qualcosa: qui
        si fissa che almeno una forma non chiede niente, altrimenti la meta'
        positiva della misura non gira."""
        bare_shapes = [shape for shape in WindowShape.ALL
                       if NumpyWindowEmitter().supports(_BareSpec(shape))]

        assert bare_shapes


# =============================================================================
# 2ter. I PARAMETRI SI LEGGONO DA UNA PORTA SOLA
# =============================================================================

class TestSpecLikeIsReadThroughOneDoor:
    """`supports()` prende uno spec-*like* di proposito, e va letto come tale
    fino in fondo.

    `missing_shape_fields` lo legge con `getattr(spec, 'params', ...)` --
    cioe' dichiara che a una descrizione arrivata da fuori catalogo basta
    quell'attributo -- mentre gli emitter leggevano i parametri con
    `spec.param(key)`, che e' un metodo di `WindowSpec` e di nessun altro.
    Due porte per la stessa domanda, e la seconda non era quella dichiarata:
    e' la stessa lezione del `getattr` dentro `_reject` (il nome di una
    spec-like) e di `_evaluator` (il metodo che valuta una forma), su un
    terzo accessorio.

    Il sintomo era diverso per i due target, e nessuno dei due e' il
    contratto: NumPy rispondeva `supports() is True` e moriva dentro
    `materialize()` con un `AttributeError` invece dell'`InvalidWindowError`
    promesso; Csound alzava `AttributeError` gia' da `supports()`, che di
    mestiere restituisce un booleano.
    """

    PARAMETRIC = {
        WindowShape.GAUSSIAN: {'sigma': 0.4},
        WindowShape.KAISER: {'beta': 6.0},
        WindowShape.EXPONENTIAL_SEGMENT: {'start': 1.0, 'curve': 4.0,
                                          'end': 0.0},
    }

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    @pytest.mark.parametrize("shape", sorted(PARAMETRIC))
    def test_a_spec_like_without_param_is_supported(self, emitter, shape):
        spec = _PlainSpec(shape, self.PARAMETRIC[shape])

        assert emitter.supports(spec) is True

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    @pytest.mark.parametrize("shape", sorted(PARAMETRIC))
    def test_it_materializes_like_the_spec_that_has_the_method(
            self, emitter, shape):
        """La misura: non solo non esplode -- produce lo stesso artefatto
        della `WindowSpec` che quei parametri li dichiara uguali."""
        params = self.PARAMETRIC[shape]
        plain = _PlainSpec(shape, params)
        full = WindowSpec(name=plain.name, shape=shape, description="d",
                          params=params,
                          family='asymmetric'
                          if shape == WindowShape.EXPONENTIAL_SEGMENT
                          else 'window',
                          symmetry='asymmetric'
                          if shape == WindowShape.EXPONENTIAL_SEGMENT
                          else 'symmetric')

        produced = emitter.materialize(plain, RESOLUTION)
        expected = emitter.materialize(full, RESOLUTION)

        if isinstance(produced, np.ndarray):
            np.testing.assert_array_equal(produced, expected)
        else:
            assert produced == expected

    @pytest.mark.parametrize("emitter", EMITTERS, ids=EMITTER_IDS)
    @pytest.mark.parametrize("shape", sorted(PARAMETRIC))
    def test_without_its_params_it_is_refused_as_promised(
            self, emitter, shape):
        """L'altra meta': la porta unica non deve ammettere di piu' -- una
        spec-like incompleta resta fuori copertura, e il rifiuto e'
        l'eccezione del contratto."""
        spec = _PlainSpec(shape)

        assert emitter.supports(spec) is False
        with pytest.raises(InvalidWindowError):
            emitter.materialize(spec, RESOLUTION)


# =============================================================================
# 3. available_windows() RIFLETTE CIO' CHE IL TARGET SA PRODURRE
# =============================================================================

class _NoCosineSumEmitter(NumpyWindowEmitter):
    """Un target NumPy mutilato: non sa fare somme di coseni."""

    def supports(self, spec) -> bool:
        if spec.shape == WindowShape.COSINE_SUM:
            return False
        return super().supports(spec)


class TestAvailableWindowsFollowsCoverage:

    def test_available_windows_is_the_emitters_coverage(self):
        registry = NumpyWindowRegistry()

        assert set(registry.available_windows()) == \
            set(NumpyWindowEmitter().covered_names())

    def test_coverage_and_catalogue_coincide_today(self):
        """Oggi il target NumPy copre tutto il catalogo: la lista che finisce
        nel messaggio d'errore resta quella dei nomi scrivibili nello YAML.

        L'uguaglianza e' un *risultato* della copertura, non piu' la sua
        definizione -- prima `available_windows()` restituiva il catalogo per
        costruzione, ed e' il meccanismo che rendeva silenziosa la divergenza.
        """
        registry = NumpyWindowRegistry()

        assert set(registry.available_windows()) == \
            set(WindowRegistry.all_names())

    def test_a_shape_the_target_cannot_produce_drops_out(self):
        """La misura della guardia: se il target perde una forma, i nomi che
        la usano spariscono dalla lista invece di restare dichiarati."""
        registry = NumpyWindowRegistry(emitter=_NoCosineSumEmitter())
        available = set(registry.available_windows())

        for lost in ('hanning', 'hamming', 'blackman', 'blackman_harris'):
            assert lost not in available, lost

        # Le altre forme restano: la copertura si restringe, non crolla.
        assert 'expodec' in available
        assert 'bartlett' in available

    def test_a_lost_shape_still_raises_when_asked_for(self):
        registry = NumpyWindowRegistry(emitter=_NoCosineSumEmitter())

        with pytest.raises(InvalidWindowError):
            registry.get('hanning', RESOLUTION)


class _TypoEmitter(NumpyWindowEmitter):
    """Il target NumPy con una voce di `_SHAPES` che non risolve."""

    _SHAPES = dict(NumpyWindowEmitter._SHAPES,
                   **{WindowShape.TRIANGULAR: '_triangulare'})


class TestCoverageIsWhatTheTargetCanActuallyEvaluate:
    """`_SHAPES` mappa la forma sul *nome* del metodo che la valuta, e un
    nome e' una cosa che si sbaglia a scrivere.

    Chiedendo alla sola tabella, `supports()` rispondeva di si' e
    `materialize()` usciva con l'`AttributeError` del `getattr` -- copertura
    dichiarata e copertura reale che divergono dentro lo stesso oggetto,
    cioe' il difetto della #202 in miniatura. La domanda e' una: il metodo
    esiste?
    """

    def test_an_unresolvable_shape_is_declared_uncovered(self):
        emitter = _TypoEmitter()

        assert emitter.supports(WindowRegistry.get('bartlett')) is False
        assert 'bartlett' in emitter.uncovered_names()

    def test_it_raises_the_contract_error_and_not_an_attribute_error(self):
        emitter = _TypoEmitter()

        with pytest.raises(InvalidWindowError):
            emitter.materialize(WindowRegistry.get('bartlett'), RESOLUTION)

    def test_the_other_shapes_are_untouched(self):
        emitter = _TypoEmitter()

        assert emitter.supports(WindowRegistry.get('hanning')) is True


# =============================================================================
# 4. IL REGISTRY NUMPY DELEGA, NON REIMPLEMENTA
# =============================================================================

class TestRegistryDelegatesToTheEmitter:

    def test_registry_output_is_the_emitters_output(self):
        registry = NumpyWindowRegistry()
        emitter = NumpyWindowEmitter()

        for name in WindowRegistry.WINDOWS:
            np.testing.assert_array_equal(
                registry.get(name, RESOLUTION),
                emitter.materialize(WindowRegistry.get(name), RESOLUTION),
                err_msg=name,
            )

    def test_registry_still_caches(self):
        registry = NumpyWindowRegistry()

        first = registry.get('hanning', RESOLUTION)
        second = registry.get('hanning', RESOLUTION)

        assert first is second
        assert len(registry) == 1
