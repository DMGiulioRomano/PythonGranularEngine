"""
expression.py

L'interprete delle espressioni (issue #308, mappe caotiche 1/7).

Un parametro che legge una mappa si scrive come un'espressione, dove stanno
un numero o un envelope:

    grain:
      duration: (0.02 + 0.08*m1)

Qui c'e' il linguaggio, e nient'altro: un parser a discesa ricorsiva che
compila il testo in chiusure, senza `eval`. E' il porting dell'interprete del
«Banco del chirp» (docs/plans/mappe-caotiche-pagine/banco-del-chirp.html), che
il plan indica come lettura di riferimento, con due differenze volute:

- `%` e `^` non ci sono (li' sono il resto e un sinonimo di `**`). Le
  precedenze dichiarate sono quelle di Python, dove `^` e' lo XOR, e il resto
  si scrive gia' con `frac` e `wrap`: aggiungerli dopo non rompe niente,
  toglierli si'.
- il numero di argomenti e' controllato per ogni funzione, non solo per
  `clip`, `fold`, `wrap` e `pow`: `Math.sin(1, 2)` ignora il secondo, e un
  argomento ignorato in silenzio e' un errore che nessuno vede.

Il linguaggio:

    espressione := termine (('+' | '-') termine)*
    termine     := unario (('*' | '/') unario)*
    unario      := ('-' | '+') unario | potenza
    potenza     := primario ('**' unario)?
    primario    := numero | '(' espressione ')' | nome '(' argomenti ')' | nome

Quindi `-x**2` e' `-(x**2)` e `2**3**2` e' `2**(3**2)`, come in Python.

**Una chiusura compilata non solleva mai.** Si valuta a ogni grano, dentro il
giro che genera i grani: fuori dominio (`1/0`, `sqrt(-1)`, `exp(1000)`) da' un
numero non finito, come in JavaScript, e a tagliarlo e scriverlo sul clip log
e' il clamp del parametro. Gli errori sono tutti al parse.

Vale anche per la profondita'. Una catena di somme o di prodotti
(`a + b - c + ...`) e' **una** chiusura, che fa le operazioni da sinistra
come le farebbero chiusure annidate: annidate, una per operatore, la
valutazione di una catena lunga scendeva di un frame per termine, e oltre il
limite di ricorsione di Python usciva un `RecursionError` a ogni grano. Cio'
che si annida davvero — parentesi, segni, potenze, chiamate — ha un limite
dichiarato, `MAX_DEPTH`, e oltre e' un `ExpressionError` al parse.

Questo modulo non importa terze parti, e del motore solo gli errori: lo legge
chi deve validare un'espressione senza costruire uno stream.
"""
from __future__ import annotations

import math
import re
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from pge.shared.exceptions import ExpressionError

_NAN = math.nan
_INF = math.inf


# =============================================================================
# FUNZIONI
# =============================================================================
# Ognuna prende float e restituisce un float, senza sollevare: e' la regola
# della chiusura compilata (vedi il docstring del modulo).

def _sicura(funzione):
    """Fuori dominio un NaN, in trabocco un infinito: mai un'eccezione."""
    def protetta(*argomenti):
        try:
            return float(funzione(*argomenti))
        except (ValueError, ZeroDivisionError):
            return _NAN
        except OverflowError:
            return _INF
    return protetta


def _log(v):
    if v == 0:
        return -_INF
    return math.log(v)


def _floor(v):
    # `math.floor` restituisce un intero, e su un non-finito solleva.
    return v if not math.isfinite(v) else float(math.floor(v))


def _round(v):
    """Il mezzo verso l'alto, come `Math.round`: non il `round` di Python,
    che lo manda al pari (0.5 -> 0, 2.5 -> 2). La stessa espressione deve
    dare lo stesso valore nel banco e nel motore."""
    return v if not math.isfinite(v) else float(math.floor(v + 0.5))


def _sign(v):
    if v != v:
        return _NAN
    return 0.0 if v == 0 else math.copysign(1.0, v)


def _min(*valori):
    if any(v != v for v in valori):
        return _NAN
    return min(valori)


def _max(*valori):
    if any(v != v for v in valori):
        return _NAN
    return max(valori)


def _pow(base, esponente):
    try:
        return math.pow(base, esponente)
    except ValueError:
        # 0 ** -1 e' un polo, non un fuori dominio: infinito, come nel banco.
        return _INF if base == 0 and esponente < 0 else _NAN
    except OverflowError:
        dispari = esponente == math.floor(esponente) and esponente % 2 == 1
        return -_INF if base < 0 and dispari else _INF


def _div(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        if a == 0 or a != a:
            return _NAN
        return math.copysign(_INF, a) * math.copysign(1.0, b)


def _frac(v):
    return v - _floor(v)


def _clip(v, lo, hi):
    if v != v:
        return _NAN
    return min(hi, max(lo, v))


def _wrap(v, lo, hi):
    """Riparte dall'altro capo. Su una fascia vuota: il minimo."""
    larghezza = hi - lo
    if not larghezza > 0:
        return lo
    # Il doppio resto e' quello del banco: tiene il risultato in [0, w) anche
    # dove un resto solo, per arrotondamento, restituirebbe w.
    return lo + math.fmod(math.fmod(v - lo, larghezza) + larghezza, larghezza)


def _fold(v, lo, hi):
    """Riflette ai bordi. Su una fascia vuota: il minimo."""
    larghezza = hi - lo
    if not larghezza > 0:
        return lo
    doppia = 2 * larghezza
    u = math.fmod(math.fmod(v - lo, doppia) + doppia, doppia)
    return lo + (doppia - u if u > larghezza else u)


#: nome -> (funzione, argomenti minimi, argomenti massimi; None = quanti si
#: vuole). E' l'elenco del linguaggio: chi lo documenta o lo completa in un
#: editor lo legge da qui.
FUNCTIONS: Dict[str, Tuple[Callable[..., float], int, Optional[int]]] = {
    'sin': (_sicura(math.sin), 1, 1),
    'cos': (_sicura(math.cos), 1, 1),
    'tan': (_sicura(math.tan), 1, 1),
    'abs': (_sicura(abs), 1, 1),
    'sqrt': (_sicura(math.sqrt), 1, 1),
    'exp': (_sicura(math.exp), 1, 1),
    'log': (_sicura(_log), 1, 1),
    'floor': (_sicura(_floor), 1, 1),
    'round': (_sicura(_round), 1, 1),
    'sign': (_sicura(_sign), 1, 1),
    'min': (_sicura(_min), 1, None),
    'max': (_sicura(_max), 1, None),
    'pow': (_sicura(_pow), 2, 2),
    'frac': (_sicura(_frac), 1, 1),
    'clip': (_sicura(_clip), 3, 3),
    'fold': (_sicura(_fold), 3, 3),
    'wrap': (_sicura(_wrap), 3, 3),
}

#: Le costanti del linguaggio.
CONSTANTS: Dict[str, float] = {'pi': math.pi, 'e': math.e}

#: Quanti livelli si possono annidare: una parentesi, un segno, una potenza,
#: una chiamata sono un livello ciascuno. Un'espressione scritta a mano ne ha
#: meno di dieci (le parentesi esterne sono gia' uno); il limite c'e' perche'
#: il parser e le chiusure scendono di qualche frame per livello, e oltre il
#: limite di ricorsione di Python uscirebbe un `RecursionError`, fuori dagli
#: errori del motore. Cinquanta livelli stanno sotto quel limite con margine,
#: anche quando la compilazione o la valutazione partono in fondo allo stack.
MAX_DEPTH = 50

#: Un nome: lettere, cifre e `_`, con al piu' un punto (`m1.y`).
NAME_PATTERN = r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?'

_TOKEN = re.compile(
    r'\s*(?:'
    r'(?P<numero>\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+)'
    rf'|(?P<nome>{NAME_PATTERN})'
    r'|(?P<segno>\*\*|[-+*/(),])'
    r')'
)


# =============================================================================
# COMPILAZIONE
# =============================================================================

class _Errore(Exception):
    """Il motivo, prima che `compile_expression` ne faccia un ExpressionError
    col testo e il campo: il parser conosce solo i token."""

    def __init__(self, reason: str, hint: Optional[str] = None):
        super().__init__(reason)
        self.reason = reason
        self.hint = hint


def _token(sorgente: str) -> List[Tuple[str, object]]:
    """Il testo in token `(tipo, valore)`: `n`umero, `id`, o il segno."""
    trovati = []
    posizione = 0
    while posizione < len(sorgente):
        if not sorgente[posizione:].strip():
            break
        m = _TOKEN.match(sorgente, posizione)
        if not m:
            resto = sorgente[posizione:].strip()[:12]
            raise _Errore(f"non capisco «{resto}»")
        posizione = m.end()
        if m.group('numero') is not None:
            trovati.append(('n', float(m.group('numero'))))
        elif m.group('nome') is not None:
            trovati.append(('id', m.group('nome')))
        else:
            trovati.append((m.group('segno'), m.group('segno')))
    return trovati


def _argomenti_attesi(nome: str, minimo: int, massimo: Optional[int]) -> str:
    if massimo is None:
        return f"{nome} vuole almeno un argomento"
    return f"{nome} vuole {minimo} argoment{'o' if minimo == 1 else 'i'}"


class _Parser:
    """Discesa ricorsiva: ogni metodo restituisce una chiusura `env -> float`."""

    def __init__(self, token, variabili):
        self._token = token
        self._p = 0
        self._variabili = variabili
        self.letti: List[str] = []
        self._profondita = 0

    def _scendi(self):
        """Un livello in piu' (vedi MAX_DEPTH). Chi scende risale a mano a
        lavoro fatto: un errore abbandona il parser intero, e non c'e' niente
        da rimettere a posto."""
        self._profondita += 1
        if self._profondita > MAX_DEPTH:
            raise _Errore(
                f"e' annidata troppo: al piu' {MAX_DEPTH} livelli fra "
                "parentesi, segni, potenze e chiamate",
                hint="togli le parentesi e i segni che non servono: "
                     "((x)) e' x, --x e' x")

    def _tipo(self):
        return self._token[self._p][0] if self._p < len(self._token) else None

    def _vuole(self, tipo):
        if self._tipo() != tipo:
            raise _Errore("manca una parentesi chiusa" if tipo == ')'
                          else f"manca «{tipo}»")
        self._p += 1

    def tutto(self):
        chiusura = self.espressione()
        if self._p < len(self._token):
            raise _Errore(f"non mi aspettavo «{self._mostra()}»")
        return chiusura

    def _mostra(self):
        tipo, valore = self._token[self._p]
        return f"{valore:g}" if tipo == 'n' else str(valore)

    def espressione(self):
        primo = self.termine()
        resto = []
        while self._tipo() in ('+', '-'):
            meno = self._tipo() == '-'
            self._p += 1
            resto.append((meno, self.termine()))
        if not resto:
            return primo
        resto = tuple(resto)

        def somma(env):
            # Da sinistra, un termine alla volta: lo stesso ordine — e lo
            # stesso arrotondamento — di `((a + b) - c) + d`.
            valore = primo(env)
            for meno, termine in resto:
                if meno:
                    valore = valore - termine(env)
                else:
                    valore = valore + termine(env)
            return valore
        return somma

    def termine(self):
        primo = self.unario()
        resto = []
        while self._tipo() in ('*', '/'):
            diviso = self._tipo() == '/'
            self._p += 1
            resto.append((diviso, self.unario()))
        if not resto:
            return primo
        resto = tuple(resto)

        def prodotto(env):
            valore = primo(env)
            for diviso, fattore in resto:
                if diviso:
                    valore = _div(valore, fattore(env))
                else:
                    valore = valore * fattore(env)
            return valore
        return prodotto

    def unario(self):
        tipo = self._tipo()
        if tipo == '-':
            self._p += 1
            self._scendi()
            a = self.unario()
            self._profondita -= 1
            return lambda env: -a(env)
        if tipo == '+':
            self._p += 1
            self._scendi()
            a = self.unario()
            self._profondita -= 1
            return a
        return self.potenza()

    def potenza(self):
        base = self.primario()
        if self._tipo() == '**':
            self._p += 1
            self._scendi()
            esponente = self.unario()
            self._profondita -= 1
            return lambda env: _pow(base(env), esponente(env))
        return base

    def primario(self):
        if self._p >= len(self._token):
            raise _Errore("finisce a meta'")
        tipo, valore = self._token[self._p]
        if tipo == 'n':
            self._p += 1
            return lambda env: valore
        if tipo == '(':
            self._p += 1
            self._scendi()
            a = self.espressione()
            self._vuole(')')
            self._profondita -= 1
            return a
        if tipo == 'id':
            self._p += 1
            if self._tipo() == '(':
                return self._chiamata(valore)
            return self._nome(valore)
        raise _Errore(f"non mi aspettavo «{valore}»")

    def _chiamata(self, nome):
        if nome not in FUNCTIONS:
            raise _Errore(f"funzione sconosciuta «{nome}»",
                          hint=f"funzioni: {' '.join(FUNCTIONS)}")
        funzione, minimo, massimo = FUNCTIONS[nome]
        self._p += 1
        self._scendi()
        argomenti = []
        if self._tipo() != ')':
            argomenti.append(self.espressione())
            while self._tipo() == ',':
                self._p += 1
                argomenti.append(self.espressione())
        self._vuole(')')
        self._profondita -= 1
        quanti = len(argomenti)
        if quanti < minimo or (massimo is not None and quanti > massimo):
            raise _Errore(_argomenti_attesi(nome, minimo, massimo))
        if quanti == 1:
            a, = argomenti
            return lambda env: funzione(a(env))
        if quanti == 2:
            a, b = argomenti
            return lambda env: funzione(a(env), b(env))
        if quanti == 3:
            a, b, c = argomenti
            return lambda env: funzione(a(env), b(env), c(env))
        return lambda env: funzione(*[f(env) for f in argomenti])

    def _nome(self, nome):
        if nome in CONSTANTS:
            costante = CONSTANTS[nome]
            return lambda env: costante
        if nome in self._variabili:
            if nome not in self.letti:
                self.letti.append(nome)
            return lambda env: env[nome]
        disponibili = sorted(self._variabili) + sorted(CONSTANTS)
        raise _Errore(f"nome sconosciuto «{nome}»",
                      hint=f"nomi disponibili: {', '.join(disponibili)}")


class CompiledExpression:
    """Un'espressione compilata: si chiama con l'ambiente, `nome -> valore`.

    `names` sono le variabili che legge davvero, nell'ordine in cui compaiono
    (le costanti no): chi prepara l'ambiente non deve leggere una mappa che
    l'espressione non nomina.
    """

    __slots__ = ('source', 'names', '_chiusura')

    def __init__(self, source: str, names: Tuple[str, ...], chiusura):
        self.source = source
        self.names = names
        self._chiusura = chiusura

    def __call__(self, env: Mapping[str, float]) -> float:
        return float(self._chiusura(env))

    def __repr__(self) -> str:
        return f"CompiledExpression({self.source!r})"


def compile_expression(
    source,
    variables: Iterable[str] = (),
    field: Optional[str] = None,
) -> CompiledExpression:
    """Compila un'espressione.

    Args:
        source: il testo, con o senza le parentesi esterne.
        variables: i nomi che l'espressione puo' leggere dall'ambiente, oltre
            alle costanti: le mappe dichiarate nello stream, `t`.
        field: il path YAML del campo, per l'errore che lo nomina.

    Raises:
        ExpressionError: se il testo non e' un'espressione del linguaggio. Lo
            stream lo aggiunge chi lo conosce.
    """
    if not isinstance(source, str):
        raise ExpressionError(source, "non e' un testo", field=field)
    if not source.strip():
        raise ExpressionError(source, "e' vuota", field=field)
    try:
        parser = _Parser(_token(source), frozenset(variables))
        chiusura = parser.tutto()
    except _Errore as errore:
        raise ExpressionError(source, errore.reason, field=field,
                              hint=errore.hint) from None
    return CompiledExpression(source, tuple(parser.letti), chiusura)


# =============================================================================
# L'ESPRESSIONE COME VALORE DI UN PARAMETRO
# =============================================================================

def outer_parenthesized(source: str) -> bool:
    """True se il testo sta tutto dentro una coppia di parentesi esterne.

    E' come un'espressione si scrive in uno YAML: `(0.02 + 0.08*m1)`. La
    parentesi che apre deve chiudersi all'ultimo carattere: `(a) + (b)`
    comincia e finisce con una parentesi, ma non e' fra parentesi.
    """
    testo = source.strip()
    if len(testo) < 2 or testo[0] != '(' or testo[-1] != ')':
        return False
    aperte = 0
    for posizione, carattere in enumerate(testo):
        if carattere == '(':
            aperte += 1
        elif carattere == ')':
            aperte -= 1
            if aperte == 0:
                return posizione == len(testo) - 1
    return False


class ExpressionSource:
    """Un'espressione ancora da compilare, con cio' che il parser dei
    parametri non puo' sapere da solo: il path YAML da cui viene e il fattore
    da applicare al **risultato** (l'unita' di misura del campo).

    La costruisce chi legge lo YAML, e solo per i campi in cui un'espressione
    vale: e' cosi' che una stringa altrove resta un errore.
    """

    __slots__ = ('text', 'field', 'scale')

    def __init__(self, text: str, field: Optional[str] = None,
                 scale: float = 1.0):
        self.text = text
        self.field = field
        self.scale = scale

    def __repr__(self) -> str:
        return f"ExpressionSource({self.text!r}, field={self.field!r})"


class Expression:
    """Il terzo tipo di valore di un `Parameter`, accanto a numero ed
    `Envelope` (issue #308).

    Come un envelope si valuta a un tempo (`evaluate`), ma non e' una curva:
    il suo valore puo' dipendere dallo stato di una mappa, che non e' una
    funzione del tempo. Per questo non ha breakpoint e non si integra, e chi
    distingue i valori per tipo lo riconosce come un caso suo.

    L'ambiente lo fornisce `reader(nomi, tempo)`: le mappe dello stream.
    """

    __slots__ = ('_compiled', '_reader', 'scale')

    def __init__(self, compiled: CompiledExpression,
                 reader: Callable[[Tuple[str, ...], float], Mapping[str, float]],
                 scale: float = 1.0):
        self._compiled = compiled
        self._reader = reader
        self.scale = scale

    @property
    def source(self) -> str:
        """Il testo com'e' scritto nello YAML."""
        return self._compiled.source

    @property
    def names(self) -> Tuple[str, ...]:
        """Le variabili che l'espressione legge."""
        return self._compiled.names

    def evaluate(self, time: float) -> float:
        valore = self._compiled(self._reader(self._compiled.names, time))
        return valore * self.scale

    def __str__(self) -> str:
        return self.source

    def __repr__(self) -> str:
        return f"Expression({self.source!r})"
