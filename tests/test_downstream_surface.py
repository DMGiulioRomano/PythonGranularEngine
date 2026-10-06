# =============================================================================
# tests/test_downstream_surface.py
# =============================================================================
"""
La superficie del motore che un altro repository legge, in forma eseguibile
(issue #246).

## Perche' esiste

PGE-ui ha un harness di parita' (PGE-ui#146, chiude PGE-ui#133): alcune regole
del motore erano ricopiate a memoria nel codice della UI -- i bounds dei
parametri, la grammatica di `--magnify-at`, la classificazione di
`deviation_probability`, le soglie di overflow delle time distribution, la
derivata del fingerprint -- e una si era gia' disallineata in silenzio. Adesso
quelle regole vengono **chieste al motore** a ogni run.

La conseguenza voluta e' che una divergenza si vede subito. La conseguenza da
registrare e' che PGE-ui dipende ora da **nomi e path interni** del motore, non
solo dalla sua superficie pubblica. E il prezzo lo paga chi non se lo aspetta:
una rinomina qui lascia il motore funzionante e `make tests` verde, e rende
rossa la CI di la', su **ogni** pull request aperta, comprese quelle che non
c'entrano niente.

Questo file e' il campanello che suona prima. Non impedisce niente: una
rinomina voluta passa da qui, e aggiornare questo elenco e' la checklist di
cosa va aggiornato anche di la'.

## Quello che NON e'

**Non e' una promessa di API pubblica.** Un nome elencato qui resta privato se
ha l'underscore: il motore non si impegna a mantenerlo, si impegna a non
rinominarlo per sbaglio. La differenza e' tutta nel messaggio di errore.

**Non e' il contratto di stdout.** Le righe che PGE-ui *parsa* -- `[CACHE] <id>:
DIRTY|clean`, i path del blocco riassuntivo -- sono forme, non nomi, e stanno
in `tests/shared/test_stdout_contract.py`, che le censisce in entrambe le
direzioni. Qui si guardano i nomi e i path; una seconda copia di quel
censimento sarebbe il difetto che tutti e due i file esistono per chiudere.

**Non e' il guardiano delle dipendenze.** Che i moduli letti senza il venv del
motore non acquistino una terza parte lo misura
`tests/shared/test_engine_exceptions.py` in un interprete figlio
(`_MODULI_SENZA_TERZE_PARTI`). Qui c'e' solo la *giunzione* fra i due registri
(`test_i_moduli_letti_senza_venv_sono_quelli_dichiarati_leggeri`, e per gli
import fatti alla chiamata `test_gli_import_lazy_delle_funzioni_chiamate_...`),
che e' cio' che rende verificabile la completezza di quella lista dal lato di
chi legge.

## Le due meta', e perche' si misurano in modo diverso

**Importati.** L'oracolo di parita' (`tests/parity/engine_oracle.py`) importa il
modulo e legge l'attributo. Qui si fa lo stesso: se il nome non c'e' piu',
l'`import` o il `getattr` lo dicono.

**Letti dal sorgente.** Il *bridge* di PGE-ui (`server.py`) non importa mai il
motore -- e' un processo Flask nel venv dell'editor, che non ha matplotlib e non
deve eseguire codice del motore per rispondere a `GET /bounds` -- quindi legge
il **testo** dei file con `ast`. Li' il contratto e' la coppia **path piu'
nome**: spostare la costante in un altro modulo la rende invisibile a quella
lettura esattamente come rinominarla, e l'esito e' peggiore, perche' il valore
mancante vale "motore ignoto" e un motore ignoto non pretende niente -- l'asse
di staleness si spegne e ogni stem diventa verde proprio mentre il motore sta
per riscriverlo diverso. Per questa meta' si verifica dunque che il nome sia
dichiarato **in quel file**, e dove serve che sia **letterale**: la risoluzione
dei nomi di chi legge va di un livello e dentro lo stesso file.

## Riferimenti

- registrazione del vincolo: issue #246
- harness: `tests/parity/README.md` in PGE-ui, `PGE-ui/engine_introspect.py`
- regola di impatto cross-repo: `.claude/rules/cross-repo-impact.md`
"""

import ast
import inspect
import os

import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'src', 'pge')


# -----------------------------------------------------------------------------
# META' 1 — i simboli che l'oracolo di parita' importa
# -----------------------------------------------------------------------------
# `senza_venv` dice se PGE-ui li legge col solo python del runner: e' il
# contratto «No op may need the engine venv», e il job node della sua CI quel
# venv non lo costruisce. Dove e' True, il modulo deve comparire anche in
# `_MODULI_SENZA_TERZE_PARTI` -- la giunzione la verifica un test qui sotto.

SIMBOLI_IMPORTATI = {
    'pge.rendering.stream_cache_manager': {
        'senza_venv': True,
        'nomi': ('VARIATION_SEMANTICS_VERSION', 'FINGERPRINT_IGNORE_KEYS',
                 'StreamCacheManager'),
        'perche': 'fingerprint degli stem e versione di semantica',
    },
    'pge.parameters.parameter_definitions': {
        'senza_venv': True,
        'nomi': ('GRANULAR_PARAMETERS', 'DEFAULT_PROB', 'RANGE_UNITS',
                 'RANGE_UNIT_DEFAULT', 'RANGE_UNIT_RELATIVE',
                 'RELATIVE_RANGE_BOUNDS'),
        'perche': 'bounds dei parametri, vocabolario di <param>_range_unit',
    },
    'pge.parameters.parameter_schema': {
        'senza_venv': True,
        'nomi': ('ALL_SCHEMAS',),
        'perche': 'chiavi per-param di deviation_probability, default di grain_duration',
    },
    'pge.parameters.pitch_unit': {
        'senza_venv': True,
        'nomi': ('PITCH_UNIT_PRESETS', 'EdoUnit'),
        'perche': 'bounds delle unita di pitch',
    },
    'pge.parameters.gate_factory': {
        'senza_venv': True,
        'nomi': ('GateFactory', 'DeviationProbabilityMode',
                 'DEVIATION_PROBABILITY_FIELD'),
        'perche': 'classificazione di deviation_probability',
    },
    'pge.envelopes.time_distribution': {
        'senza_venv': True,
        'nomi': ('TimeDistributionFactory',),
        'perche': 'soglie di overflow delle time distribution',
    },
    'pge.shared.constants': {
        'senza_venv': True,
        'nomi': ('DEFAULT_OUTPUT_SR',),
        'perche': 'sample rate: la UI ci converte duration_unit: samples',
    },
    'pge.rendering.envelope_extractor': {
        'senza_venv': True,
        'nomi': ('ENVELOPE_COLORS', 'PLOT_ENVELOPE_KEYS'),
        'perche': 'nomi validi per --plot-envelopes',
    },
    'pge.api': {
        'senza_venv': True,
        'nomi': ('renderer_types',),
        'perche': 'elenco dei backend audio per il popover del render',
    },
    # L'op `build_envelope` (PGE-ui #180, sui guard di forma della #211)
    # costruisce un `Envelope` vero e ne legge il `field` dell'errore; l'op
    # `constants` chiede al builder le interpolazioni ammesse, che
    # `PGEEnv.INTERP_TYPES` ricopia.
    'pge.envelopes.envelope': {
        'senza_venv': True,
        'nomi': ('Envelope',),
        'perche': 'verdetto del motore sulla forma di un envelope',
    },
    'pge.envelopes.envelope_builder': {
        'senza_venv': True,
        'nomi': ('EnvelopeBuilder',),
        'perche': 'interpolazioni ammesse in un BP group',
    },
    # I due moduli nati dalla #246 perche' l'oracolo li importasse invece di
    # estrarne i nodi dall'AST ed eseguirli. Il terzo, `parameters/loop_unit.py`,
    # non e' qui: di la' lo legge solo il bridge, dal sorgente (sotto).
    'pge.shared.magnify_spec': {
        'senza_venv': True,
        'nomi': ('parse_magnify_spec', 'MAGNIFY_KEYS', 'MAGNIFY_NUMERIC_KEYS',
                 'MAGNIFY_STR_KEYS'),
        'perche': 'grammatica di --magnify-at',
    },
    'pge.engine.solo_mute': {
        'senza_venv': True,
        'nomi': ('filter_solo_mute',),
        'perche': 'quali stream il motore costruisce (mute/solo)',
    },
}


# -----------------------------------------------------------------------------
# META' 2 — i nomi che il bridge legge dal sorgente, al loro path
# -----------------------------------------------------------------------------
# Path relativi a src/pge/. `letterale` = la lettura a valle pretende un valore
# riducibile a letterale, perche' il suo risolutore va di un livello e dentro
# lo stesso file; dove e' False il nome e' cercato ma il valore no (lo
# `_VALID_TYPES` dentro una classe, che il bridge legge come insieme di stringhe
# ma che qui basta esista).

LETTI_DAL_SORGENTE = (
    ('rendering/envelope_extractor.py', 'ENVELOPE_COLORS', True),
    ('parameters/parameter_definitions.py', 'GRANULAR_PARAMETERS', False),
    ('parameters/parameter_definitions.py', 'RANGE_UNITS', True),
    ('parameters/parameter_definitions.py', 'RELATIVE_RANGE_BOUNDS', True),
    ('parameters/pitch_unit.py', 'PITCH_UNIT_PRESETS', False),
    ('shared/constants.py', 'DEFAULT_OUTPUT_SR', True),
    ('rendering/stream_cache_manager.py', 'VARIATION_SEMANTICS_VERSION', True),
    ('parameters/loop_unit.py', 'LOOP_UNITS', True),
    ('rendering/supercollider_renderer.py', 'DEFAULT_SYNTHDEF_SOURCE', True),
    ('rendering/supercollider_renderer.py', 'DEFAULT_SYNTHDEF_DIR', True),
    ('rendering/sc_score_writer.py', 'SYNTH_NAME', True),
)

# Dentro una classe, non a livello di modulo: il bridge scende nel ClassDef e
# cerca li' un'assegnazione o un metodo con quel nome.
LETTI_DENTRO_UNA_CLASSE = (
    ('rendering/renderer_factory.py', 'RendererFactory', '_VALID_TYPES',
     "e' l'unica strada per cui l'elenco dei backend arriva al popover del "
     "render (l'API pubblica renderer_types() il bridge non la puo' "
     "chiamare, non importa il motore)"),
    ('parameters/pitch_unit.py', 'EdoUnit', 'value_bounds',
     "il bridge ne ricava il fattore di ottave dei bounds EDO "
     "(`_parse_edo_factor`): senza, i preset EDO di GET /bounds spariscono"),
    ('parameters/pitch_unit.py', 'RatioUnit', 'value_bounds',
     "il bridge ne ricava i bounds di pitch.ratio (`_parse_ratio_bounds`): "
     "senza, GET /bounds non porta la chiave ratio"),
)

# Letterali di stringa che a valle valgono una domanda, non un valore: «questo
# motore sa fare questa cosa?». Il criterio di chi legge e' la costante
# esattamente com'e' scritta nel sorgente -- i commenti non sopravvivono
# all'AST -- quindi va cercata come costante e non come testo del file.
LETTERALI_DI_CAPACITA = (
    ('cli.py', '--samples-dir',
     'il bridge decide se refs/ puo seguire il workspace (PGE #235)'),
    ('cli.py', '--bw',
     'la checkbox della partitura in bianco e nero (PGE #248)'),
    ('rendering/csound_renderer.py', 'csound',
     'il binario che il bridge cerca nel PATH per dire se il backend c-e'),
    ('rendering/supercollider_renderer.py', 'scsynth',
     'idem, server di SuperCollider'),
    ('rendering/supercollider_renderer.py', 'sclang',
     'idem, compilatore della SynthDef'),
)


def _albero(relpath):
    with open(os.path.join(SRC, relpath), encoding='utf-8') as fh:
        return ast.parse(fh.read(), filename=relpath)


def _riducibile(valore, prima):
    """Il valore si riduce a un dato, con la regola di chi legge da fuori.

    Non `literal_eval` secco: il risolutore del bridge va di **un livello**,
    e dentro lo stesso file. Il motore scrive le tuple di vocabolario per nome
    (`RANGE_UNITS = (RANGE_UNIT_ABSOLUTE, RANGE_UNIT_RELATIVE)`), e un
    `literal_eval` su quel nodo risponde "non lo so" sul checkout vero -- cioe'
    accuserebbe una scrittura che a valle funziona benissimo. Un nome che punta
    a un'espressione invece non si riduce davvero, e li' il rosso e' giusto.

    `prima` sono gli statement che precedono l'assegnazione: conta l'ULTIMA
    assegnazione del nome, non l'ultima che era un letterale.
    """
    try:
        ast.literal_eval(valore)
        return True
    except (ValueError, TypeError):
        pass
    if not isinstance(valore, (ast.Tuple, ast.List)):
        return False
    for elt in valore.elts:
        if not isinstance(elt, ast.Name):
            try:
                ast.literal_eval(elt)
            except (ValueError, TypeError):
                return False
            continue
        legato = None
        for nodo in prima:
            trovato = _assegnato(nodo, elt.id)
            if trovato is not None:
                legato = trovato
        if legato is None:
            return False
        try:
            ast.literal_eval(legato)
        except (ValueError, TypeError):
            return False
    return True


def _assegnato(nodo, nome):
    """Il valore assegnato a `nome` da questo statement, o None.

    Riconosce `nome = ...` e `nome: T = ...`: la grafia annotata e' stile di
    casa qui (`GRANULAR_PARAMETERS`, `PITCH_UNIT_PRESETS` ce l'hanno), e il
    lettore a valle le riconosce entrambe proprio perche' filtrare sul solo
    `ast.Assign` aveva fatto sparire un asse in silenzio."""
    if isinstance(nodo, ast.Assign):
        bersagli = [t.id for t in nodo.targets if isinstance(t, ast.Name)]
        valore = nodo.value
    elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
        bersagli = [nodo.target.id]
        valore = nodo.value
    else:
        return None
    return valore if nome in bersagli else None


# -----------------------------------------------------------------------------
# I test
# -----------------------------------------------------------------------------

class TestSimboliImportati:

    @pytest.mark.parametrize('modulo', sorted(SIMBOLI_IMPORTATI))
    def test_il_modulo_si_importa(self, modulo):
        import importlib
        assert importlib.import_module(modulo) is not None

    @pytest.mark.parametrize('modulo,nome', [
        (m, n) for m, voce in sorted(SIMBOLI_IMPORTATI.items())
        for n in voce['nomi']])
    def test_il_nome_c_e(self, modulo, nome):
        import importlib
        mod = importlib.import_module(modulo)
        assert hasattr(mod, nome), (
            f"{modulo}.{nome} non esiste piu'. Lo legge l'oracolo di parita' "
            f"di PGE-ui ({SIMBOLI_IMPORTATI[modulo]['perche']}): se la "
            f"rinomina e' voluta, aggiorna questo elenco e apri la issue su "
            f"PGE-ui prevista da .claude/rules/cross-repo-impact.md. Vedi "
            f"issue #246.")

    def test_i_moduli_letti_senza_venv_sono_quelli_dichiarati_leggeri(self):
        """La giunzione fra i due registri.

        `_MODULI_SENZA_TERZE_PARTI` misura che questi moduli si importino con
        le dipendenze bloccate; questo elenco dice *chi* li legge e perche'.
        Separati, ognuno dei due puo' restare indietro sull'altro senza che
        niente lo dica -- ed e' quello che era successo: l'oracolo importa
        `pge.api` dalla PGE-ui #150, e quella lista non lo sapeva.

        Il confronto e' un sottoinsieme in una direzione sola:
        `pge.shared.exceptions` sta nella lista di la' perche' sta *sotto* ogni
        altro modulo, non perche' PGE-ui ne legga un nome."""
        from tests.shared.test_engine_exceptions import _MODULI_SENZA_TERZE_PARTI
        senza_venv = {m for m, voce in SIMBOLI_IMPORTATI.items()
                      if voce['senza_venv']}
        mancanti = sorted(senza_venv - set(_MODULI_SENZA_TERZE_PARTI))
        assert not mancanti, (
            f"PGE-ui importa {', '.join(mancanti)} senza il venv del motore, "
            f"ma _MODULI_SENZA_TERZE_PARTI non li sorveglia: un import pesante "
            f"la' dentro passerebbe in silenzio. Aggiungili in "
            f"tests/shared/test_engine_exceptions.py.")

    def test_gli_import_lazy_delle_funzioni_chiamate_sono_sorvegliati(self):
        """La giunzione vale anche per cio' che una funzione importa da dentro.

        La guardia di `_MODULI_SENZA_TERZE_PARTI` *importa* i moduli e basta:
        non chiama niente. Ma l'oracolo le funzioni le chiama, e un import
        dentro il corpo di una funzione avviene solo li'. `renderer_types()`
        e' il caso: importa `pge.rendering.renderer_factory` alla chiamata, e
        `import pge.api` non lo carica -- un `import numpy` in quel modulo
        lasciava la guardia verde e faceva morire l'op del popover nel job
        node. Il commento che diceva «la guardia copre tutti e due» era la
        premessa non misurata.

        Derivato dall'AST delle funzioni elencate, non trascritto: la
        prossima funzione che importa da dentro entra qui da sola. Le classi
        restano fuori dichiaratamente -- i loro metodi chiamati a valle non
        stanno in questo registro, e scendere in tutti accuserebbe import
        pesanti voluti (la durata implicita dello `StreamCacheManager`, che
        l'oracolo lascia esplodere apposta)."""
        import importlib
        import textwrap

        from tests.shared.test_engine_exceptions import (
            _MODULI_SENZA_TERZE_PARTI, _dipendenze_di_terze_parti)
        terze_parti = set(_dipendenze_di_terze_parti())

        def scoperto(nome_modulo):
            """Un import da dentro che la guardia non misura: un modulo del
            motore che lei non importa, o una terza parte e basta."""
            radice = nome_modulo.split('.')[0]
            if radice in terze_parti:
                return True
            return radice == 'pge' and nome_modulo not in _MODULI_SENZA_TERZE_PARTI

        scoperti = []
        for modulo, voce in sorted(SIMBOLI_IMPORTATI.items()):
            if not voce['senza_venv']:
                continue
            mod = importlib.import_module(modulo)
            for nome in voce['nomi']:
                oggetto = getattr(mod, nome, None)
                if not inspect.isfunction(oggetto):
                    continue
                albero = ast.parse(textwrap.dedent(inspect.getsource(oggetto)))
                for nodo in ast.walk(albero):
                    if isinstance(nodo, ast.ImportFrom) and nodo.module:
                        importati = [nodo.module]
                    elif isinstance(nodo, ast.Import):
                        importati = [a.name for a in nodo.names]
                    else:
                        continue
                    scoperti.extend(f"{modulo}.{nome} -> {m}"
                                    for m in importati if scoperto(m))
        assert not scoperti, (
            f"import fatti alla chiamata che _MODULI_SENZA_TERZE_PARTI non "
            f"sorveglia: {', '.join(scoperti)}. La guardia importa i moduli "
            f"ma non chiama le funzioni, quindi un import pesante la' dentro "
            f"passerebbe in silenzio. Un modulo del motore va aggiunto in "
            f"tests/shared/test_engine_exceptions.py; una terza parte rompe "
            f"la funzione nel job node di PGE-ui, e va tolta o discussa la' "
            f"(.claude/rules/cross-repo-impact.md).")


class TestFormeChiamate:
    """Non solo il nome: la forma con cui a valle lo si chiama.

    Un nome che resta mentre la sua firma cambia e' un rosso a valle che il
    solo `hasattr` non anticipa."""

    def test_stream_cache_manager_accetta_i_suoi_kwargs(self):
        """`renderer_type` compreso: l'oracolo lo passa da PGE-ui #151, perche'
        il backend e' il terzo asse dentro l'hash, e un manager costruito
        senza chiederebbe ogni fingerprint in una configurazione in cui il
        prodotto non gira mai."""
        from pge.rendering.stream_cache_manager import StreamCacheManager
        parametri = inspect.signature(StreamCacheManager.__init__).parameters
        for kwarg in ('cache_path', 'samples_dir', 'renderer_type'):
            assert kwarg in parametri, (
                f"StreamCacheManager non accetta piu' {kwarg}=: l'oracolo di "
                f"PGE-ui lo costruisce cosi' per l'op fingerprint")

    def test_compute_fingerprint_prende_uno_stream(self):
        from pge.rendering.stream_cache_manager import StreamCacheManager
        parametri = inspect.signature(
            StreamCacheManager.compute_fingerprint).parameters
        assert len(parametri) >= 2, (
            'compute_fingerprint(self, stream): e la forma che l-oracolo chiama')

    def test_la_classificazione_di_deviation_probability_c_e(self):
        from pge.parameters.gate_factory import GateFactory
        for nome in ('_classify_deviation_probability', 'create_gate'):
            assert hasattr(GateFactory, nome), (
                f"GateFactory.{nome} non esiste piu': e' la regola che il "
                f"mirror JS di PGE-ui promette di replicare. Il nome e' "
                f"privato -- il motore non si impegna a tenerlo -- ma una "
                f"rinomina va accompagnata, non scoperta a valle (#246)")

    def test_la_factory_delle_time_distribution_risponde(self):
        from pge.envelopes.time_distribution import TimeDistributionFactory
        for nome in ('create', 'list_available'):
            assert hasattr(TimeDistributionFactory, nome)
        assert TimeDistributionFactory.list_available(), (
            'list_available() vuota: le soglie di overflow non si misurano piu')

    def test_gli_spec_portano_gli_attributi_che_a_valle_si_leggono(self):
        """`deviation_probability_key`, `is_smart`, `name`, `default`.

        L'oracolo ci cammina sopra per dire *quali* chiavi gli spec del motore
        dichiarano dentro `deviation_probability` -- cioe' per verificare la
        COMPLETEZZA delle liste della UI e non il solo contenuto: senza,
        svuotare quelle liste lasciava la suite verde."""
        from pge.parameters.parameter_schema import ALL_SCHEMAS
        assert ALL_SCHEMAS, 'ALL_SCHEMAS vuoto'
        for specs in ALL_SCHEMAS.values():
            for spec in specs:
                for attributo in ('deviation_probability_key', 'is_smart',
                                  'name', 'default'):
                    assert hasattr(spec, attributo), (
                        f"uno spec di ALL_SCHEMAS non ha piu' {attributo}")

    def test_i_bounds_portano_i_quattro_campi(self):
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS
        assert GRANULAR_PARAMETERS, 'GRANULAR_PARAMETERS vuoto'
        for nome, bounds in GRANULAR_PARAMETERS.items():
            for campo in ('min_val', 'max_val', 'min_range', 'max_range'):
                assert hasattr(bounds, campo), (
                    f"i bounds di {nome} non hanno piu' {campo}: la mappa "
                    f"ENGINE_PARAM_MAP di PGE-ui dice, per chiave della UI, "
                    f"quale di questi quattro leggere")

    def test_il_tetto_di_edo_si_chiede_cosi(self):
        """`EdoUnit(...).value_bounds().max_val`, la catena che l'oracolo
        percorre per i bounds del pitch."""
        from pge.parameters.pitch_unit import EdoUnit
        bounds = EdoUnit(12).value_bounds()
        assert hasattr(bounds, 'max_val')

    def test_le_interpolazioni_del_builder_si_chiedono_alla_classe(self):
        """`EnvelopeBuilder.VALID_INTERP_TYPES`: attributo di classe, che il
        solo `hasattr` sul modulo non vede."""
        from pge.envelopes.envelope_builder import EnvelopeBuilder
        tipi = getattr(EnvelopeBuilder, 'VALID_INTERP_TYPES', None)
        assert tipi, (
            "EnvelopeBuilder.VALID_INTERP_TYPES non c'e' piu' (o e' vuota): "
            "l'op constants di PGE-ui la legge, e PGEEnv.INTERP_TYPES la "
            "ricopia per envShapeError")

    def test_un_envelope_rifiutato_dice_il_campo(self):
        """L'op `build_envelope` costruisce un `Envelope` e legge `field`
        dall'errore: la parita' della #211 pretende che ogni rifiuto lo porti,
        e un `getattr(exc, 'field', None)` a valle non distingue un attributo
        rinominato da un rifiuto senza campo."""
        from pge.envelopes.envelope import Envelope
        with pytest.raises(Exception) as rifiuto:
            Envelope([[[0, 0], [100, 1]], 1, True])
        assert isinstance(getattr(rifiuto.value, 'field', None), str), (
            f"{type(rifiuto.value).__name__} non porta piu' `field`: e' la "
            f"sotto-posizione che la parita' delle forme di PGE-ui confronta")

    def test_renderer_types_resta_la_porta_dei_backend(self):
        from pge.api import renderer_types
        tipi = renderer_types()
        assert isinstance(tipi, list) and tipi, (
            'renderer_types() vuota: e la lista che il popover del render di '
            'PGE-ui trasforma in bottoni')


class TestLettiDalSorgente:

    @pytest.mark.parametrize('relpath,nome,letterale', LETTI_DAL_SORGENTE)
    def test_il_nome_e_dichiarato_in_quel_file(self, relpath, nome, letterale):
        albero = _albero(relpath)
        valore, prima = None, []
        for nodo in albero.body:
            valore = _assegnato(nodo, nome)
            if valore is not None:
                break
            prima.append(nodo)
        assert valore is not None, (
            f"{relpath} non dichiara piu' {nome} a livello di modulo. Il "
            f"bridge di PGE-ui non importa il motore: legge il testo di QUESTO "
            f"file con ast, quindi spostare la costante altrove la rende "
            f"invisibile come rinominarla, e il valore mancante vale 'motore "
            f"ignoto' -- un controllo che si spegne senza dirlo (#246)")
        if letterale and not _riducibile(valore, prima):
            pytest.fail(
                f"{relpath}:{nome} non e' piu' riducibile a un dato: il "
                f"risolutore a valle va di un livello e dentro lo stesso "
                f"file, quindi leggerebbe 'non lo so' -- e un 'non lo so' "
                f"preso per un valore e' il modo silenzioso di sbagliare")

    @pytest.mark.parametrize('relpath,classe,nome,perche', LETTI_DENTRO_UNA_CLASSE)
    def test_il_nome_e_dichiarato_in_quella_classe(self, relpath, classe, nome,
                                                   perche):
        albero = _albero(relpath)
        corpo = next((n.body for n in albero.body
                      if isinstance(n, ast.ClassDef) and n.name == classe), None)
        assert corpo is not None, (
            f"{relpath} non dichiara piu' la classe {classe}: il bridge di "
            f"PGE-ui la cerca per nome in questo file ({perche})")
        assert any(_assegnato(n, nome) is not None
                   or (isinstance(n, ast.FunctionDef) and n.name == nome)
                   for n in corpo), (
            f"{classe}.{nome} non e' piu' dichiarato in {relpath}: {perche}")

    @pytest.mark.parametrize('relpath,letterale,perche', LETTERALI_DI_CAPACITA)
    def test_il_letterale_di_capacita_c_e(self, relpath, letterale, perche):
        albero = _albero(relpath)
        costanti = {n.value for n in ast.walk(albero)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        assert letterale in costanti, (
            f"{relpath} non contiene piu' la costante {letterale!r}: a valle "
            f"vale una domanda sulle capacita' di questo motore ({perche}), e "
            f"la risposta negativa non e' un errore ma un comportamento "
            f"diverso -- il modo silenzioso di sbagliare (#246)")


class TestIlRegistroNonEUnaCopia:
    """Le due guardie che tengono onesto il registro stesso."""

    def test_non_censisce_le_righe_di_stdout(self):
        """Le forme delle righe stanno in `test_stdout_contract.py`.

        Qui ci sono nomi e path: una forma di riga entrata in uno di questi
        registri sarebbe una seconda copia di quel censimento, e di due copie
        una resta indietro. La guardia guarda i **registri**, non il testo di
        questo file: la prosa qui sopra deve poter nominare quelle righe per
        dire che non le sorveglia."""
        voci = []
        for modulo, voce in SIMBOLI_IMPORTATI.items():
            voci.extend(voce['nomi'])
            voci.append(voce['perche'])
        voci.extend(n for _, n, _ in LETTI_DAL_SORGENTE)
        voci.extend(n for _, _, n, _ in LETTI_DENTRO_UNA_CLASSE)
        voci.extend(lett for _, lett, _ in LETTERALI_DI_CAPACITA)
        for voce in voci:
            assert '[CACHE]' not in voce and 'SOLO MODE' not in voce, (
                f"{voce!r} e' una forma di riga, non un nome: il suo posto e' "
                f"CLASSIFICAZIONE in tests/shared/test_stdout_contract.py")

    def test_ogni_voce_dice_perche(self):
        """Un elenco di nomi senza il motivo invecchia in un elenco di nomi,
        e chi lo trova rosso non sa cosa aggiornare di la'."""
        for modulo, voce in SIMBOLI_IMPORTATI.items():
            assert voce['perche'], f"{modulo} non dice perche' e' qui"
            assert voce['nomi'], f"{modulo} non elenca nomi"
        for _, _, perche in LETTERALI_DI_CAPACITA:
            assert perche
        for _, _, _, perche in LETTI_DENTRO_UNA_CLASSE:
            assert perche
