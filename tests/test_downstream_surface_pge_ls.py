# =============================================================================
# tests/test_downstream_surface_pge_ls.py
# =============================================================================
"""
La superficie del motore che PGE-ls legge, in forma eseguibile (issue #269).

## Perche' esiste

E' la gemella di `tests/test_downstream_surface.py`, che fa lo stesso per
PGE-ui (#246). Il lettore e' un altro, e cambia il modo di fallire. In PGE-ui
la divergenza e' rumorosa per costruzione: l'harness chiede i valori al motore
a ogni run, e un rename e' un rosso immediato. In PGE-ls no, per tre vie:

- il language server vero (`granular_ls/schema_bridge.py`) legge il motore
  dentro `try/except`, con un fallback statico accanto: un rename non fa
  fallire niente, fa scivolare il LS sulla propria copia scritta a mano, che
  da quel momento invecchia in silenzio;
- molti patti della sua parita' (`tests/test_pge_parity.py`) leggono i file
  del motore per percorso, e su file o nome mancante fanno
  `pytest.skip("engine precede ...")`, cioe' verde;
- il checkout del motore nella sua CI e' condizionato a un secret, e senza la
  parita' salta tutta.

La #269 lo diceva cosi': qui rinominare non rende rossa una CI, la rende muta.
Questo file e' il rosso che mancava, dal lato del motore. Elenca cio' che
PGE-ls legge e verifica che si risolva ancora dove lo si cerca, nella forma in
cui lo si usa. Una rinomina voluta passa da qui, e aggiornare questo elenco e'
la checklist di cosa va aggiornato anche di la'.

## Quello che NON e'

**Non e' una promessa di API pubblica**, come il gemello: un nome con
l'underscore resta privato, e il motore si impegna solo a non rinominarlo per
sbaglio. **Non e' una copia della parita' di PGE-ls**: i valori — bounds,
nomi di strategy, soglie — li chiede PGE-ls al motore, e seguono da soli.
Qui si guarda che ci siano i nomi, i path e le forme da cui li chiede.

## Le quattro meta'

1. **Importati** — il bridge e la parita' li importano come `pge.<modulo>`
   (ripiegando sul layout piatto). La CI di PGE-ls installa solo pygls,
   lsprotocol, PyYAML e pytest: ogni modulo deve importarsi senza numpy,
   soundfile e matplotlib, e la giunzione con `_MODULI_SENZA_TERZE_PARTI` lo
   fa misurare.
2. **Letti dal sorgente, al path** — `_literal_from_engine_source`:
   `literal_eval` del valore di un'assegnazione di modulo, annotata o no,
   senza risolvere nomi. Spostata la costante, il patto salta in verde.
3. **Funzioni estratte dal sorgente ed eseguite** — il nodo `def` preso
   dall'AST, compilato da solo con un namespace scritto a mano e un `self`
   finto. Qui il contratto e' piu' del nome: i nomi che l'exec chiede — quelli
   del corpo e quelli che si valutano al `def`, annotazioni comprese — devono
   stare nel namespace che PGE-ls passa, gli attributi di `self` che il corpo
   legge nel suo `self` finto, gli argomenti in quelli che gli da'.
4. **Forme** — la riga che un regex insegue, i campi che il bridge esclude per
   nome, le firme chiamate dove un'eccezione si legge come verdetto del motore.

## Riferimenti

- registrazione del vincolo: issue #269; la gemella per PGE-ui: #246
- PGE-ls, letti al commit 94b811f: `granular_ls/schema_bridge.py`
  (`from_python_path`), `tests/test_pge_parity.py`
- regola di impatto cross-repo: `.claude/rules/cross-repo-impact.md`
"""

import ast
import builtins
import dataclasses
import importlib
import inspect
import os
import re
import symtable
import textwrap
from types import SimpleNamespace

import pytest

from tests.test_downstream_surface import SRC, _assegnato, _albero


# -----------------------------------------------------------------------------
# META' 1 — importati
# -----------------------------------------------------------------------------

# Il language server, a runtime: `SchemaBridge.from_python_path`. Per ogni
# voce, che cosa succede di la' se il nome o il modulo si muove — e' la
# differenza che la #269 registra, quindi va nel messaggio.
LETTI_DAL_LANGUAGE_SERVER = (
    ('pge.parameters.parameter_schema', ('ALL_SCHEMAS',),
     "il bridge non si costruisce: l'eccezione risale"),
    ('pge.parameters.parameter_definitions', ('GRANULAR_PARAMETERS',),
     "il bridge non si costruisce: l'eccezione risale"),
    ('pge.parameters.parameter_definitions',
     ('RANGE_UNITS', 'RELATIVE_RANGE_BOUNDS'),
     "`except AttributeError`: il language server ripiega sul fallback "
     "statico e tace"),
    ('pge.core.stream_config', ('StreamContext', 'StreamConfig'),
     "spostato il modulo, `except ImportError`: le chiavi di stream "
     "diventano la lista statica, in silenzio"),
    ('pge.shared.distribution_strategy',
     ('DistributionFactory', 'RANGE_ANCHORS'),
     "`except Exception: pass`: il language server ripiega sul fallback "
     "statico e tace"),
    ('pge.controllers.window_registry', ('WindowRegistry',),
     "`except Exception: pass`: il language server ripiega sul fallback "
     "statico e tace"),
)

# La parita', `tests/test_pge_parity.py`. Qui di solito il rosso c'e' — il
# fixture `pge` o il test esplode — ma non sempre: dove la lettura e'
# `getattr(modulo, NOME, None)` seguita da `pytest.skip`, il nome che sparisce
# fa saltare il patto in verde (`_RIMEDI_OVERFLOW`, `DEFAULT_OUTPUT_SR`,
# `SECONDS_PER_MILLISECOND`, `get_parameter_definition`, `ANCHOR_MIN`,
# `RANGE_ANCHORS`, `RANGE_UNITS`).
IMPORTATI_DALLA_PARITA = {
    'pge.strategies.voice_pitch_strategy': (
        'VOICE_PITCH_STRATEGIES', 'CHORD_INTERVALS'),
    'pge.strategies.voice_onset_strategy': ('VOICE_ONSET_STRATEGIES',),
    'pge.strategies.voice_pointer_strategy': ('VOICE_POINTER_STRATEGIES',),
    'pge.strategies.voice_pan_strategy': ('VOICE_PAN_STRATEGIES',),
    'pge.parameters.pitch_unit': ('PITCH_UNIT_PRESETS',),
    'pge.parameters.parameter_definitions': (
        'GRANULAR_PARAMETERS', 'RANGE_UNITS', 'get_parameter_definition',
        'range_unit_is_relative'),
    'pge.parameters.parameter_schema': (
        'ALL_SCHEMAS', 'POINTER_PARAMETER_SCHEMA', 'resolve_yaml_path'),
    'pge.parameters.parameter_orchestrator': ('ParameterOrchestrator',),
    'pge.parameters.parser': ('GranularParser',),
    'pge.parameters.gate_factory': ('GateFactory',),
    'pge.parameters.read_direction': (
        'normalize_read_direction', 'READ_DIRECTION_FIELD'),
    'pge.controllers.window_registry': ('WindowRegistry',),
    'pge.controllers.pointer_controller': ('PointerController',),
    'pge.core.stream_config': ('StreamContext', 'StreamConfig'),
    'pge.shared.constants': ('SECONDS_PER_MILLISECOND', 'DEFAULT_OUTPUT_SR'),
    'pge.shared.distribution_strategy': (
        'DistributionFactory', 'RANGE_ANCHORS', 'ANCHOR_MIN', 'ANCHOR_CENTER'),
    'pge.shared.exceptions': (
        'ConfigError', 'InvalidFieldValueError', 'MissingFieldError',
        'ParameterBoundError'),
    'pge.envelopes.time_distribution': (
        'TimeDistributionFactory', '_RIMEDI_OVERFLOW'),
    'pge.envelopes.envelope': (
        'create_scaled_envelope', 'scale_raw_param_values'),
}

# Attributi letti su una classe, che il solo `hasattr` sul modulo non vede.
LETTI_SULLE_CLASSI = (
    ('pge.shared.distribution_strategy', 'DistributionFactory', '_registry',
     "il bridge ne legge le chiavi a runtime: le modalita' di distribuzione, "
     "con un `except Exception: pass` che tace"),
    ('pge.controllers.window_registry', 'WindowRegistry', 'all_names',
     "il bridge ne legge i nomi delle finestre, alias compresi"),
    ('pge.envelopes.time_distribution', 'TimeDistributionFactory',
     '_DISTRIBUTIONS',
     "la parita' confronta i nomi delle time distribution, alias compresi"),
    ('pge.envelopes.time_distribution', 'TimeDistributionFactory', 'create',
     "la parita' costruisce la distribuzione per cercarne il trabocco"),
    ('pge.parameters.gate_factory', 'GateFactory', 'create_gate',
     "la parita' di deviation_probability chiede il verdetto al gate"),
    ('pge.parameters.parser', 'GranularParser', 'parse_parameter',
     "la parita' delle bande e dei bounds chiede il verdetto al parser"),
    ('pge.parameters.parameter_orchestrator', 'ParameterOrchestrator',
     '_range_unit_from_spec',
     "la parita' di grain.duration_range_unit lo chiama slegato, con un "
     "`self` finto"),
    ('pge.core.stream_config', 'StreamContext', 'from_yaml',
     "la parita' di pointer.start e del loop costruisce il contesto cosi'"),
)


def _moduli_importati():
    letti = {modulo for modulo, _, _ in LETTI_DAL_LANGUAGE_SERVER}
    return sorted(letti | set(IMPORTATI_DALLA_PARITA))


def _nomi_importati():
    coppie = {(modulo, nome) for modulo, nomi, _ in LETTI_DAL_LANGUAGE_SERVER
              for nome in nomi}
    coppie |= {(modulo, nome) for modulo, nomi in IMPORTATI_DALLA_PARITA.items()
               for nome in nomi}
    return sorted(coppie)


def _chi_lo_legge(modulo, nome):
    for m, nomi, se_si_muove in LETTI_DAL_LANGUAGE_SERVER:
        if m == modulo and nome in nomi:
            return f"il language server a runtime ({se_si_muove})"
    return "la parita' di PGE-ls"


# -----------------------------------------------------------------------------
# META' 2 — letti dal sorgente, al path
# -----------------------------------------------------------------------------
# Path relativi a src/pge/. La lettura di PGE-ls e' una sola,
# `_literal_from_engine_source`: le assegnazioni di livello modulo, annotate o
# no, e `literal_eval` del valore, senza risolvere nomi.

def _stringhe(valore):
    """una tupla o lista non vuota di stringhe"""
    return (isinstance(valore, (tuple, list)) and bool(valore)
            and all(isinstance(v, str) for v in valore))


def _mappa_di_stringhe(valore):
    """un dict non vuoto da stringa a stringa"""
    return (isinstance(valore, dict) and bool(valore)
            and all(isinstance(k, str) and isinstance(v, str)
                    for k, v in valore.items()))


def _numero(valore):
    """un numero, non un booleano"""
    return isinstance(valore, (int, float)) and not isinstance(valore, bool)


LETTI_DAL_SORGENTE = (
    ('core/stream.py', 'GRAIN_DURATION_UNITS', _stringhe,
     "l'enum di grain.duration_unit, confrontato con `_GRAIN_DURATION_UNITS` "
     "del diagnostic provider (il drift di PGE-ls#36)"),
    ('core/stream.py', '_GRAIN_DURATION_UNIT_LABELS', _mappa_di_stringhe,
     "entra nel namespace con cui `_pre_normalize_grain_params` si esegue"),
    ('parameters/loop_unit.py', 'LOOP_UNITS', _stringhe,
     "il vocabolario di pointer.loop_unit, ordine compreso: il primo e' il "
     "default che la completion propone"),
    ('parameters/loop_unit.py', 'LOOP_UNIT_SCOPE', _stringhe,
     "le chiavi a cui loop_unit si applica, nei bounds, nell'hover e nei "
     "semantic token"),
    ('controllers/density_controller.py', 'DENSITY_NOTICE_THRESHOLD', _numero,
     "il tetto di disegno di density per snippet e GUI envelope"),
)


# -----------------------------------------------------------------------------
# META' 3 — funzioni estratte dal sorgente ed eseguite
# -----------------------------------------------------------------------------
# (path, nome, namespace che PGE-ls passa, attributi del `self` finto,
#  argomenti posizionali con cui la chiama, perche')

FUNZIONI_ESEGUITE = (
    ('core/stream.py', '_init_grain_reverse',
     frozenset({'InvalidFieldValueError', 'READ_DIRECTION_FIELD'}),
     frozenset({'stream_id'}), 2,
     "il mirror di grain.reverse si confronta col metodo vero "
     "(`_load_init_grain_reverse`)"),
    ('core/stream.py', '_pre_normalize_grain_params',
     frozenset({'GRAIN_DURATION_UNITS', '_GRAIN_DURATION_UNIT_LABELS',
                'InvalidFieldValueError', 'MissingFieldError',
                'SECONDS_PER_MILLISECOND', 'range_unit_is_relative',
                'scale_raw_param_values'}),
     frozenset({'stream_id'}), 3,
     "le chiavi che grain.duration_unit scala, e il range relativo che resta "
     "fuori (`_load_pre_normalize_grain_params`)"),
    ('engine/generator.py', '_eval_math_expressions',
     frozenset({'math', 're'}),
     frozenset({'_eval_math_expressions'}), 2,
     "le espressioni che il Generator valuta prima del parse, e il loro "
     "regex (`_load_eval_math_expressions`)"),
)


def _funzioni_col_nome(relpath, nome):
    """Ogni `def nome` del file, nell'ordine in cui PGE-ls le cerca: il
    primo di `ast.walk`, cioe' quello che esegue."""
    return [n for n in ast.walk(_albero(relpath))
            if isinstance(n, ast.FunctionDef) and n.name == nome]


def _nomi_liberi(funzione):
    """I nomi globali che l'exec di PGE-ls chiede, builtin esclusi.

    Dal `symtable` del modulo fatto della sola funzione, com'e' compilata di
    la'. Contano i nomi letti al `def`, nello scope del modulo — default,
    decoratori e annotazioni, che li' si valutano subito perche' il modulo
    estratto non ha il `from __future__ import annotations` del file — e i
    globali di ogni scope sotto: il corpo, le comprehension, le lambda, le
    funzioni interne e, dalla 3.14, il blocco `__annotate__` (PEP 649), che
    `symtable` mette davanti alla funzione. Per questo si visitano tutti i
    figli e non il primo: dalla 3.14 il primo e' quel blocco. Il nome della
    funzione non conta, lo definisce l'exec stesso."""
    radice = symtable.symtable(ast.unparse(funzione), '<estratta>', 'exec')
    liberi = {s.get_name() for s in radice.get_symbols() if s.is_referenced()}
    pila = list(radice.get_children())
    while pila:
        corrente = pila.pop()
        liberi |= {s.get_name() for s in corrente.get_symbols()
                   if s.is_global()}
        pila.extend(corrente.get_children())
    return liberi - set(dir(builtins)) - {funzione.name}


def _attributi_letti_di_self(funzione):
    """Gli attributi del primo argomento che il corpo legge senza averli
    scritti prima: quelli che il `self` finto deve avere."""
    nome_self = funzione.args.args[0].arg

    def di_self(ctx):
        return {n.attr for n in ast.walk(funzione)
                if isinstance(n, ast.Attribute) and isinstance(n.ctx, ctx)
                and isinstance(n.value, ast.Name) and n.value.id == nome_self}

    return di_self(ast.Load) - di_self(ast.Store)


def _accetta_posizionali(funzione, quanti):
    argomenti = funzione.args
    tutti = len(argomenti.posonlyargs) + len(argomenti.args)
    obbligatori = tutti - len(argomenti.defaults)
    return obbligatori <= quanti and (quanti <= tutti
                                      or argomenti.vararg is not None)


# -----------------------------------------------------------------------------
# I test
# -----------------------------------------------------------------------------

class TestImportati:

    @pytest.mark.parametrize('modulo', _moduli_importati())
    def test_il_modulo_si_importa(self, modulo):
        assert importlib.import_module(modulo) is not None

    @pytest.mark.parametrize('modulo,nome', _nomi_importati())
    def test_il_nome_c_e(self, modulo, nome):
        mod = importlib.import_module(modulo)
        assert hasattr(mod, nome), (
            f"{modulo}.{nome} non esiste piu'. Lo legge "
            f"{_chi_lo_legge(modulo, nome)}: se la rinomina e' voluta, "
            f"aggiorna questo elenco e apri la issue su PGE-ls prevista da "
            f".claude/rules/cross-repo-impact.md. Vedi issue #269.")

    @pytest.mark.parametrize('modulo,classe,nome,perche', LETTI_SULLE_CLASSI,
                             ids=[f'{c}.{n}' for _, c, n, _ in LETTI_SULLE_CLASSI])
    def test_l_attributo_della_classe_c_e(self, modulo, classe, nome, perche):
        cls = getattr(importlib.import_module(modulo), classe)
        assert hasattr(cls, nome), (
            f"{classe}.{nome} non esiste piu': {perche} (#269)")

    def test_i_moduli_importati_sono_quelli_dichiarati_leggeri(self):
        """La giunzione con `_MODULI_SENZA_TERZE_PARTI`.

        La CI di PGE-ls non installa numpy, soundfile ne' matplotlib, e un
        modulo che ne importasse una li' non si importerebbe: il bridge
        ripiegherebbe sul fallback, la parita' esploderebbe o salterebbe. Oggi
        i diciannove moduli si importano senza, ma per undici di loro era un
        caso: la guardia non li sorvegliava."""
        from tests.shared.test_engine_exceptions import _MODULI_SENZA_TERZE_PARTI
        mancanti = sorted(set(_moduli_importati())
                          - set(_MODULI_SENZA_TERZE_PARTI))
        assert not mancanti, (
            f"PGE-ls importa {', '.join(mancanti)} senza le dipendenze del "
            f"motore, ma _MODULI_SENZA_TERZE_PARTI non li sorveglia: un "
            f"import pesante la' dentro passerebbe in silenzio. Aggiungili in "
            f"tests/shared/test_engine_exceptions.py.")


class TestLettiDalSorgente:

    @pytest.mark.parametrize(
        'relpath,nome,forma,perche', LETTI_DAL_SORGENTE,
        ids=[f'{relpath}:{nome}' for relpath, nome, _, _ in LETTI_DAL_SORGENTE])
    def test_il_letterale_e_dichiarato_in_quel_file(self, relpath, nome,
                                                    forma, perche):
        valore = next((v for v in (_assegnato(n, nome)
                                   for n in _albero(relpath).body)
                       if v is not None), None)
        assert valore is not None, (
            f"{relpath} non dichiara piu' {nome} a livello di modulo. PGE-ls "
            f"lo legge dall'AST di QUESTO file ({perche}), e su un nome che "
            f"manca il suo patto fa pytest.skip: spostarlo lo spegne in verde "
            f"(#269)")
        try:
            letto = ast.literal_eval(valore)
        except ValueError:
            letto = None
        assert letto is not None and forma(letto), (
            f"{relpath}:{nome} non si legge piu' con literal_eval come "
            f"{forma.__doc__}: e' la lettura di `_literal_from_engine_source`, "
            f"che non risolve nomi e su un valore illeggibile torna None, cioe' "
            f"'motore che precede' (#269)")


class TestFunzioniEseguite:

    @pytest.mark.parametrize(
        'relpath,nome,namespace,attributi,posizionali,perche',
        FUNZIONI_ESEGUITE,
        ids=[f'{relpath}:{nome}' for relpath, nome, *_ in FUNZIONI_ESEGUITE])
    def test_la_funzione_si_esegue_come_la_esegue_pge_ls(
            self, relpath, nome, namespace, attributi, posizionali, perche):
        trovate = _funzioni_col_nome(relpath, nome)
        assert trovate, (
            f"{relpath} non definisce piu' {nome}. PGE-ls la estrae per AST "
            f"da questo file e la esegue ({perche}): spostata o rinominata, il "
            f"suo patto fa pytest.skip, in verde (#269)")
        assert len(trovate) == 1, (
            f"{relpath} definisce {len(trovate)} funzioni {nome}: PGE-ls "
            f"esegue la prima di ast.walk, che non e' detto sia quella giusta")
        funzione = trovate[0]

        fuori = sorted(_nomi_liberi(funzione) - namespace)
        assert not fuori, (
            f"{nome} legge {', '.join(fuori)}, che PGE-ls non mette nel "
            f"namespace con cui la esegue ({', '.join(sorted(namespace))}): "
            f"di la' sarebbe un NameError. Aggiorna il namespace in "
            f"tests/test_pge_parity.py di PGE-ls e questo elenco (#269)")

        di_self = sorted(_attributi_letti_di_self(funzione) - attributi)
        assert not di_self, (
            f"{nome} legge self.{', self.'.join(di_self)}, che il `self` "
            f"finto di PGE-ls non ha (ha {', '.join(sorted(attributi))}): di "
            f"la' sarebbe un AttributeError (#269)")

        assert _accetta_posizionali(funzione, posizionali), (
            f"{nome} non si chiama piu' con {posizionali} argomenti "
            f"posizionali, self compreso: e' come la chiama PGE-ls (#269)")

    def test_il_regex_delle_espressioni_e_un_letterale_della_funzione(self):
        """`_load_eval_math_expressions` torna anche il pattern, letto
        nell'AST di `_eval_math_expressions` come `pattern = '<stringa>'`: il
        mirror di PGE-ls lo confronta carattere per carattere, e senza quella
        riga il patto salta."""
        funzione, = _funzioni_col_nome('engine/generator.py',
                                       '_eval_math_expressions')
        pattern = [n.value.value for n in ast.walk(funzione)
                   if isinstance(n, ast.Assign)
                   and any(getattr(t, 'id', None) == 'pattern'
                           for t in n.targets)
                   and isinstance(n.value, ast.Constant)
                   and isinstance(n.value.value, str)]
        assert pattern, (
            "_eval_math_expressions non assegna piu' `pattern` a una stringa: "
            "il confronto del regex di PGE-ls salta (#269)")

    def test_le_chiavi_che_l_unita_del_grano_scala(self):
        """`test_le_chiavi_scalate_dall_unita` di PGE-ls pretende che le
        stringhe nelle tuple di `_pre_normalize_grain_params` siano proprio
        `duration` e `duration_range`: sono le chiavi che il suo
        `_check_grain_duration_unit` converte. Una terza chiave scalata qui
        e' un rosso su ogni PR di PGE-ls, e conviene saperlo prima."""
        funzione, = _funzioni_col_nome('core/stream.py',
                                       '_pre_normalize_grain_params')
        nominate = {elt.value for nodo in ast.walk(funzione)
                    if isinstance(nodo, ast.Tuple) for elt in nodo.elts
                    if isinstance(elt, ast.Constant)
                    and isinstance(elt.value, str)}
        assert nominate == {'duration', 'duration_range'}

    def test_le_letture_del_registro_vedono_cio_che_vedrebbe_l_exec(self):
        """La controprova delle tre regole, su una funzione finta: senza, un
        registro che non trova niente e un registro cieco si leggono uguali."""
        modulo = ast.parse(textwrap.dedent("""
            def f(self, a, b=1):
                import os
                x = [g(v) for v in a]
                self.scritto = 1
                return CONST + self.letto + self.scritto + len(x) + os.sep
        """))
        funzione = modulo.body[0]

        assert _nomi_liberi(funzione) == {'g', 'CONST'}
        assert _attributi_letti_di_self(funzione) == {'letto'}
        assert _accetta_posizionali(funzione, 2)
        assert _accetta_posizionali(funzione, 3)
        assert not _accetta_posizionali(funzione, 4)

    def test_i_nomi_letti_al_def_contano_e_il_nome_della_funzione_no(self):
        """L'exec di PGE-ls compila la sola funzione, senza il `from
        __future__ import annotations` del file: sul suo Python (3.11) default,
        decoratori e annotazioni si valutano al `def`, nel namespace che passa,
        e un nome che manca e' un NameError prima ancora della chiamata. Il
        nome della funzione invece lo definisce l'exec stesso, e una chiamata
        ricorsiva lo trova.

        L'insieme deve essere lo stesso su ogni Python della matrice. Dalla
        3.14 `symtable` mette davanti a ogni funzione un blocco `__annotate__`
        (PEP 649): la lettura che ne prendeva il primo figlio leggeva quello, e
        tornava vuota — i tre test sulle funzioni vere passavano per cecita'."""
        modulo = ast.parse(textwrap.dedent("""
            @DECORO
            def f(self, a: Tipo, b=DEFAULT, *, c: 'Stringa' = None) -> Ritorno:
                h = lambda q: q + LAMBDA_G
                def interna():
                    return INTERNA_G
                return f(a) + h(1) + interna()
        """))
        assert _nomi_liberi(modulo.body[0]) == {
            'DECORO', 'Tipo', 'DEFAULT', 'Ritorno', 'LAMBDA_G', 'INTERNA_G'}

    def test_pointer_legge_le_posizioni_senza_time_mode(self):
        """`_pre_normalize_loop_params` lo legge PGE-ls per nome, nel file del
        pointer controller: pretende che fra i nomi del corpo non ci sia
        `time_mode`, la premessa del suo lato di PGE #222. Spostato il
        metodo, il patto salta; time_mode tornato, e' rosso su ogni PR di
        la'."""
        trovate = _funzioni_col_nome('controllers/pointer_controller.py',
                                     '_pre_normalize_loop_params')
        assert trovate, (
            "controllers/pointer_controller.py non definisce piu' "
            "_pre_normalize_loop_params: PGE-ls la cerca li', e il suo patto "
            "su loop_unit salta in verde (#269)")
        nomi = {n.attr for n in ast.walk(trovate[0])
                if isinstance(n, ast.Attribute)}
        nomi |= {n.id for n in ast.walk(trovate[0]) if isinstance(n, ast.Name)}
        assert 'time_mode' not in nomi


class TestForme:
    """Non solo i nomi: la forma con cui PGE-ls li legge o li chiama."""

    def test_il_guard_di_pointer_start_ha_ancora_la_forma_che_pge_ls_cerca(self):
        """Pinnato per forma, non per nome: un regex sul testo del file. Anche
        una riscrittura equivalente fa rosso di la', senza che niente sia
        rotto — meglio vederlo qui, insieme a chi la fa."""
        with open(os.path.join(SRC, 'controllers', 'pointer_controller.py'),
                  encoding='utf-8') as fh:
            sorgente = fh.read()
        assert re.search(
            r'if not isinstance\(\s*self\.start\s*,\s*\(\s*int\s*,\s*float'
            r'\s*\)\s*\)', sorgente), (
            "il guard di pointer.start non e' piu' `if not "
            "isinstance(self.start, (int, float))`: il test "
            "`test_pointer_start_guard_del_motore_e_ancora_isinstance` di "
            "PGE-ls diventa rosso, e il mirror in "
            "_check_pointer_start_envelope va riallineato (#269)")

    def test_gli_spec_portano_gli_attributi_che_il_bridge_legge(self):
        from pge.parameters.parameter_schema import ALL_SCHEMAS
        attributi = ('name', 'yaml_path', 'default', 'is_smart',
                     'exclusive_group', 'group_priority', 'range_path',
                     'deviation_probability_key', 'range_unit_path')
        for specs in ALL_SCHEMAS.values():
            for spec in specs:
                for attributo in attributi:
                    assert hasattr(spec, attributo), (
                        f"lo spec {spec.name} non ha piu' {attributo}: il "
                        f"bridge di PGE-ls lo copia per ogni spec "
                        f"(`range_unit_path` con un getattr che tace) (#269)")

    def test_i_bounds_portano_i_sei_campi_che_il_bridge_legge(self):
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS
        for nome, bounds in GRANULAR_PARAMETERS.items():
            for campo in ('min_val', 'max_val', 'min_range', 'max_range',
                          'default_jitter', 'variation_mode'):
                assert hasattr(bounds, campo), (
                    f"i bounds di {nome} non hanno piu' {campo}: il bridge di "
                    f"PGE-ls li copia tutti e sei (#269)")

    def test_i_campi_che_il_bridge_esclude_per_nome_esistono(self):
        """Le chiavi di stream del LS sono i campi dei due dataclass meno
        `sample_dur_sec` e `context`, esclusi **per nome**. Rinominato uno dei
        due, il LS offrirebbe come chiave YAML un campo che lo YAML non ha —
        e la parita' non lo vedrebbe, perche' esclude per lo stesso nome."""
        from pge.core.stream_config import StreamConfig, StreamContext
        assert 'sample_dur_sec' in {f.name for f in dataclasses.fields(StreamContext)}
        assert 'context' in {f.name for f in dataclasses.fields(StreamConfig)}

    def test_le_modalita_di_distribuzione_sono_un_registro_con_chiavi(self):
        from pge.shared.distribution_strategy import DistributionFactory
        assert list(DistributionFactory._registry.keys()), (
            "DistributionFactory._registry e' vuoto o non e' una mappa: il "
            "bridge di PGE-ls ne legge le chiavi a runtime (#269)")

    def test_i_nomi_delle_finestre_si_chiedono_al_registro(self):
        from pge.controllers.window_registry import WindowRegistry
        nomi = WindowRegistry.all_names()
        assert nomi and all(isinstance(n, str) for n in nomi)

    def test_il_gate_si_chiede_con_i_kwargs_della_parita(self):
        """`GateFactory.create_gate(deviation_probability=, param_key=,
        duration=)` dentro un `except Exception` che lo legge come «il motore
        rifiuta»: un kwarg rinominato sarebbe un verdetto, non un errore."""
        from pge.parameters.gate_factory import GateFactory
        parametri = inspect.signature(GateFactory.create_gate).parameters
        for kwarg in ('deviation_probability', 'param_key', 'duration'):
            assert kwarg in parametri, (
                f"GateFactory.create_gate non accetta piu' {kwarg}=: la "
                f"parita' di PGE-ls lo passa, e il TypeError le arriverebbe "
                f"come un rifiuto del motore (#269)")

    def test_una_time_distribution_si_calcola_come_la_calcola_pge_ls(self):
        """`factory.create(spec).calculate_distribution(10.0, n_reps)` dentro
        un `except Exception`: per la parita' del trabocco ogni eccezione e' il
        motore che rifiuta. Una firma cambiata si leggerebbe come una soglia."""
        from pge.envelopes.time_distribution import TimeDistributionFactory
        inizi, durate = TimeDistributionFactory.create(
            {'type': 'geometric', 'ratio': 2}).calculate_distribution(10.0, 4)
        assert len(inizi) == len(durate) == 4
        assert sum(durate) == pytest.approx(10.0)

    def test_il_parser_con_la_config_che_costruisce_pge_ls(self, tmp_path,
                                                           monkeypatch):
        """La parita' delle bande e di grain.duration_range_unit costruisce il
        parser con un `SimpleNamespace` al posto dello `StreamConfig`, coi soli
        campi qui sotto, e chiama `_range_unit_from_spec` slegato con un
        `self` che ha solo `_config`. Un campo letto in piu' sarebbe un
        AttributeError dentro un `except Exception` che, nella parita' degli
        envelope, lo legge come «il motore rifiuta per un'altra ragione»."""
        from pge.parameters.parameter_orchestrator import ParameterOrchestrator
        from pge.parameters.parameter_schema import ALL_SCHEMAS, resolve_yaml_path
        from pge.parameters.parser import GranularParser
        from pge.shared.exceptions import ParameterBoundError

        monkeypatch.chdir(tmp_path)  # il logger delle clip scrive in logs/
        contesto = SimpleNamespace(sample_dur_sec=10.0, output_sr=48000,
                                   stream_id='s1', rng_id='r1', duration=10.0)
        config = SimpleNamespace(context=contesto, time_mode='absolute',
                                 distribution_mode='uniform',
                                 range_anchor='center', duration=10.0,
                                 seed=None)
        parser = GranularParser(config)

        parser.parse_parameter('volume', -6.0)
        parser.parse_parameter('volume', 0.0, 6.0)

        spec = next(s for specs in ALL_SCHEMAS.values() for s in specs
                    if s.name == 'grain_duration')
        params = {'grain': {'duration': 0.05, 'duration_range': 0.5,
                            'duration_range_unit': 'relative'}}
        valore = resolve_yaml_path(params, spec.yaml_path, spec.default)
        banda = resolve_yaml_path(params, spec.range_path, None)
        unita = ParameterOrchestrator._range_unit_from_spec(
            SimpleNamespace(_config=config), spec, params, banda)
        parser.parse_parameter(spec.name, valore, banda, range_unit=unita)

        with pytest.raises(ParameterBoundError) as fuori:
            parser.parse_parameter('volume', 999.0)
        for attributo in ('param_name', 'value', 'hint', 'min_bound',
                          'max_bound', 'violations'):
            assert hasattr(fuori.value, attributo), (
                f"ParameterBoundError non porta piu' {attributo}: la parita' "
                f"di PGE-ls lo legge dal rifiuto del motore (#269)")

        # Su un envelope la parita' dei bounds legge le Y rifiutate
        # spacchettando `violations` a coppie, `{float(y) for _t, y in ...}`:
        # un elemento che non e' piu' un (t, y) e' un ValueError di la'.
        with pytest.raises(ParameterBoundError) as envelope_fuori:
            parser.parse_parameter('volume', [[0, 0.0], [1, 999.0]])
        assert {float(y) for _t, y in envelope_fuori.value.violations} == {999.0}

    def test_le_funzioni_si_chiamano_come_le_chiama_pge_ls(self):
        """Posizionali, nell'ordine in cui la parita' li passa."""
        from pge.core.stream_config import StreamConfig, StreamContext
        from pge.envelopes.envelope import (
            create_scaled_envelope, scale_raw_param_values)
        from pge.parameters.parameter_definitions import (
            get_parameter_definition, range_unit_is_relative)
        from pge.parameters.parameter_schema import resolve_yaml_path
        from pge.parameters.read_direction import normalize_read_direction

        assert normalize_read_direction(1) == 1.0
        assert create_scaled_envelope(
            [[0, 1], [1, -1]], 10.0, 'absolute') is not None
        assert scale_raw_param_values([[0, 50], [1, 100]], 0.001) is not None
        assert range_unit_is_relative('relative') is True
        assert resolve_yaml_path({'a': {'b': 2}}, 'a.b', None) == 2
        assert get_parameter_definition(
            'grain_duration', output_sr=48000).min_val == pytest.approx(1 / 48000)

        contesto = StreamContext.from_yaml(
            {'stream_id': 's1', 'sample': 'f.wav', 'duration': 10.0,
             'onset': 0.0}, sample_dur_sec=10.0)
        assert StreamConfig(context=contesto).context is contesto

    def test_il_pointer_si_costruisce_come_lo_costruisce_pge_ls(self):
        """`PointerController(pointer, StreamConfig(context=...))`, posizionali.
        Di la' questa parita' salta per scelta — senza numpy il controller
        non si costruisce — ma dove il motore c'e' intero gira, e una firma
        cambiata farebbe rosso solo li'."""
        from pge.controllers.pointer_controller import PointerController
        from pge.core.stream_config import StreamConfig, StreamContext
        contesto = StreamContext.from_yaml(
            {'stream_id': 's1', 'sample': 'f.wav', 'duration': 10.0,
             'onset': 0.0}, sample_dur_sec=10.0)

        PointerController({'start': 0.0}, StreamConfig(context=contesto))


class TestIlRegistroNonEUnaCopia:

    def test_nessuna_voce_del_gemello_e_dimenticata_qui(self):
        """Quel che PGE-ui e PGE-ls leggono in comune resta in due registri,
        perche' i lettori sono due e i messaggi dicono chi: ma le letture dal
        sorgente che i due condividono devono essere le stesse righe di
        codice. `LOOP_UNITS` e' l'unica, e il gemello la dichiara al path di
        `parameters/loop_unit.py` come qui."""
        from tests.test_downstream_surface import LETTI_DAL_SORGENTE as GEMELLO
        qui = {(r, n) for r, n, _, _ in LETTI_DAL_SORGENTE}
        di_la = {(r, n) for r, n, _, _ in GEMELLO}
        assert ('parameters/loop_unit.py', 'LOOP_UNITS') in qui & di_la
