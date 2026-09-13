"""
WindowRegistry: il catalogo delle finestre grano.

Single source of truth su quali nomi lo YAML puo' scrivere, qual e' il
canonico di ciascuno e -- da #202 -- *che forma ha* ciascuna finestra.

La descrizione e' agnostica: forma matematica, coefficienti, parametri,
simmetria. Non cita ne' le GEN routine di Csound ne' le funzioni di NumPy,
perche' una `WindowSpec` deve dire cos'e' una finestra, non come un back-end
la produce. Chi la produce e' un `WindowEmitter`
(`pge.controllers.window_emitter`), uno per target:

    CsoundWindowEmitter   spec -> (GEN routine, parametri)   -> CsoundEmitter
    NumpyWindowEmitter    spec -> np.ndarray

Prima della #202 la spec *era* la descrizione Csound (`gen_routine`,
`gen_params`): il back-end NumPy non poteva derivarne niente e reimplementava
il catalogo da capo. Le due definizioni sono divergite due volte --
`blackman_harris` esisteva solo lato Csound, l'alias `triangle` passava la
validazione YAML ed esplodeva a meta' render. Ora la definizione e' una e i
target la traducono; un target che una spec non sa esprimerla lo dichiara
nella propria copertura (`WindowEmitter.supports`) invece di scoprirlo a
runtime.

## Convenzione di campionamento

Una finestra e' una funzione su [0, 1] campionata in `n` punti sull'intervallo
**chiuso**: il primo campione sta in x=0, l'ultimo in x=1. E' la convenzione
"simmetrica" -- quella di `np.hanning`, non quella periodica -- e sta scritta
qui perche' e' cio' che rende `symmetry` una proprieta' verificabile
sull'array materializzato (`tests/rendering/test_window_shape_parity.py`).

## Le forme

| shape                 | parametri                | forma su x in [0, 1]                                  |
|-----------------------|--------------------------|-------------------------------------------------------|
| `cosine_sum`          | `coefficients` (a0..aK)  | somma_k (-1)^k a_k cos(2 pi k x)                       |
| `triangular`          | --                       | 1 - abs(2x - 1)                                        |
| `gaussian`            | `sigma`                  | exp(-0.5 ((2x-1)/sigma)^2)                             |
| `kaiser`              | `beta`                   | finestra di Kaiser-Bessel di parametro beta            |
| `rectangular`         | --                       | 1                                                      |
| `sinc_lobe`           | --                       | sinc(2x - 1), lobo centrale sin(pi u)/(pi u)           |
| `sine_lobe`           | --                       | sin(pi x)                                              |
| `exponential_segment` | `start`, `curve`, `end`  | start + (end-start) (1-e^(curve x))/(1-e^curve)        |

`cosine_sum` copre a un colpo hamming/hanning/blackman/blackman-harris: sono
la stessa forma con coefficienti diversi, ed e' il motivo per cui aggiungerne
una quinta e' una riga di catalogo e nessuna riga di emitter.

La colonna "parametri" di quella tabella e' eseguibile: sta in
`WindowShape.REQUIRED_PARAMS` e `REQUIRES_COEFFICIENTS`, la legge
`missing_shape_fields()`, e una descrizione a cui manca un campo che la sua
forma legge non arriva a essere una `WindowSpec`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import List, Mapping, Optional, Tuple


class WindowShape:
    """Le forme matematiche che il catalogo sa descrivere.

    Non e' un elenco di finestre: e' l'elenco delle *famiglie di funzioni*.
    Una finestra e' una di queste forme piu' i suoi parametri.
    """

    COSINE_SUM = 'cosine_sum'
    TRIANGULAR = 'triangular'
    GAUSSIAN = 'gaussian'
    KAISER = 'kaiser'
    RECTANGULAR = 'rectangular'
    SINC_LOBE = 'sinc_lobe'
    SINE_LOBE = 'sine_lobe'
    EXPONENTIAL_SEGMENT = 'exponential_segment'

    ALL = frozenset({
        COSINE_SUM, TRIANGULAR, GAUSSIAN, KAISER,
        RECTANGULAR, SINC_LOBE, SINE_LOBE, EXPONENTIAL_SEGMENT,
    })

    # Cosa una forma ha bisogno di leggere nella spec per essere una funzione.
    #
    # Sta qui, accanto al vocabolario delle forme, e non nel corpo di un
    # emitter ne' nella tabella di un test: chi inventa una forma parametrica
    # ne dichiara i parametri nella stessa riga in cui la aggiunge, e ogni
    # lettore -- il costruttore della spec, il `supports()` di ogni target --
    # la deriva da qui invece di trascriverla. Una seconda copia andrebbe muta
    # esattamente nel momento in cui serve: quando la forma nuova e' appena
    # stata scritta e nessuno si ricorda dell'elenco che vive altrove.
    REQUIRED_PARAMS = MappingProxyType({
        GAUSSIAN: ('sigma',),
        KAISER: ('beta',),
        EXPONENTIAL_SEGMENT: ('start', 'curve', 'end'),
    })

    # Le forme che senza coefficienti non sono una funzione: `cosine_sum` con
    # la somma vuota vale zero ovunque, cioe' un grano reso come silenzio
    # digitale -- il caso degenere della #225, per una strada che nessuna
    # soglia sorveglia.
    REQUIRES_COEFFICIENTS = frozenset({COSINE_SUM})


# Simmetria dichiarata: `w(x) == w(1-x)` oppure no. E' una proprieta' della
# forma, non una preferenza di rendering, e un test la rilegge sull'array che
# ogni emitter produce -- una finestra dichiarata simmetrica e materializzata
# con campionamento periodico e' rossa li'.
SYMMETRIC = 'symmetric'
ASYMMETRIC = 'asymmetric'

VALID_SYMMETRIES = frozenset({SYMMETRIC, ASYMMETRIC})


def missing_shape_fields(spec) -> Tuple[str, ...]:
    """I campi che la forma di `spec` legge e che `spec` non dichiara.

    E' la lettura di `WindowShape.REQUIRED_PARAMS` e `REQUIRES_COEFFICIENTS`,
    e l'unica: il costruttore della spec la usa per rifiutare una descrizione
    incompleta, e `supports()` di ogni target per dichiararla fuori copertura.

    Prende uno spec-*like*, non una `WindowSpec`, perche' gli emitter fanno
    lo stesso (`getattr(spec, 'shape', None)`): una spec costruita altrove --
    o un duck type di prova -- deve poter essere interrogata senza passare
    dal catalogo.

    Una forma senza parametri restituisce sempre `()`: non e' un giudizio
    sulla forma, e' l'elenco di cio' che manca, che per lei e' vuoto.
    """
    shape = getattr(spec, 'shape', None)
    missing = []

    if (shape in WindowShape.REQUIRES_COEFFICIENTS
            and not getattr(spec, 'coefficients', ())):
        missing.append('coefficients')

    params = getattr(spec, 'params', None) or {}
    for key in WindowShape.REQUIRED_PARAMS.get(shape, ()):
        if params.get(key) is None:
            missing.append(key)

    return tuple(missing)


@dataclass(frozen=True)
class WindowSpec:
    """Descrizione di una finestra grano, indipendente dal target.

    Attributes:
        name: identificatore univoco (e.g. 'hanning'), il nome dello YAML.
        shape: una delle `WindowShape` -- la famiglia di funzioni.
        description: descrizione leggibile.
        family: raggruppamento di catalogo (window, asymmetric, custom).
        symmetry: `SYMMETRIC` se w(x) == w(1-x), altrimenti `ASYMMETRIC`.
        coefficients: i coefficienti della forma, quando ne ha
            (`cosine_sum`: a0..aK).
        params: i parametri scalari della forma, quando ne ha
            (`gaussian`: sigma; `kaiser`: beta; `exponential_segment`:
            start/curve/end).
    """

    name: str
    shape: str
    description: str
    family: str = "window"
    symmetry: str = SYMMETRIC
    coefficients: Tuple[float, ...] = ()
    # `default_factory` e non un mappingproxy vuoto condiviso: su Python 3.11
    # `dataclasses` rifiuta come default qualunque valore non hashable, e un
    # mappingproxy non lo e' -- `ValueError: mutable default ... use
    # default_factory` alla *definizione* della classe, quindi il modulo non
    # si importava affatto. Solo la 3.11: la 3.10 controlla i tipi mutabili
    # noti (list, dict, set) e la 3.12 ha ristretto il controllo di nuovo, il
    # che rende questa la classe di difetto che il gate locale non vede --
    # gira su un interprete alla volta. `__post_init__` avvolge comunque il
    # dict in `MappingProxyType`, quindi la sola cosa che cambia e' che ogni
    # spec parte dal suo dict vuoto invece che da uno condiviso.
    params: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if self.shape not in WindowShape.ALL:
            raise ValueError(
                f"WindowSpec('{self.name}'): forma sconosciuta "
                f"'{self.shape}'. Valide: {sorted(WindowShape.ALL)}"
            )
        if self.symmetry not in VALID_SYMMETRIES:
            raise ValueError(
                f"WindowSpec('{self.name}'): simmetria sconosciuta "
                f"'{self.symmetry}'. Valide: {sorted(VALID_SYMMETRIES)}"
            )
        # La spec e' un dato condiviso fra tutti gli emitter e vive in un
        # dict di classe: se restasse mutabile, un target potrebbe riscrivere
        # sotto gli altri la descrizione da cui tutti derivano.
        object.__setattr__(self, 'coefficients', tuple(self.coefficients))
        object.__setattr__(self, 'params', MappingProxyType(dict(self.params)))

        # Una forma senza i suoi parametri non e' una descrizione parziale:
        # e' una descrizione che nessun target puo' leggere. Il prezzo di
        # lasciarla passare lo pagava chi rendeva -- NumPy valuta la formula
        # con un `None` dentro (`TypeError`), Csound scrive il `None` nel
        # p-field e lo score muore a meta' render -- cioe' esattamente il
        # modo di fallire che la #202 esiste per togliere di mezzo. Qui il
        # catalogo non puo' nemmeno contenerla: il modulo non si importa.
        missing = missing_shape_fields(self)
        if missing:
            raise ValueError(
                f"WindowSpec('{self.name}'): la forma '{self.shape}' legge "
                f"{', '.join(missing)}, che la spec non dichiara"
            )

    def param(self, key: str, default: Optional[float] = None) -> Optional[float]:
        """Parametro scalare della forma, `default` se la spec non lo dichiara."""
        return self.params.get(key, default)


def _asymmetric_curve(name: str, start: float, curve: float, end: float,
                      description: str) -> WindowSpec:
    """Una delle curve esponenziali del catalogo (famiglia Roads).

    `curve` e' il parametro di curvatura della forma dichiarata sopra: >0 la
    curva parte ripida e si appiattisce, <0 il contrario, 0 e' la retta.
    """
    return WindowSpec(
        name=name,
        shape=WindowShape.EXPONENTIAL_SEGMENT,
        description=description,
        family="asymmetric",
        symmetry=ASYMMETRIC,
        params={'start': start, 'curve': curve, 'end': end},
    )


class WindowRegistry:
    """Registro centralizzato delle window disponibili.

    Usato da Generator, UI/validation e dagli emitter di ogni target.
    """

    # Definizioni dichiarative (invece di if/elif)
    WINDOWS = {
        # Somme di coseni: la stessa forma, coefficienti diversi.
        'hamming': WindowSpec(
            name='hamming',
            shape=WindowShape.COSINE_SUM,
            coefficients=(0.54, 0.46),
            description="Hamming window",
            family="window",
        ),
        'hanning': WindowSpec(
            name='hanning',
            shape=WindowShape.COSINE_SUM,
            coefficients=(0.5, 0.5),
            description="Hanning/von Hann window",
            family="window",
        ),
        'bartlett': WindowSpec(
            name='bartlett',
            shape=WindowShape.TRIANGULAR,
            description="Bartlett/Triangle window",
            family="window",
        ),
        'blackman': WindowSpec(
            name='blackman',
            shape=WindowShape.COSINE_SUM,
            coefficients=(0.42, 0.5, 0.08),
            description="Blackman window (3 termini)",
            family="window",
        ),
        'blackman_harris': WindowSpec(
            name='blackman_harris',
            shape=WindowShape.COSINE_SUM,
            coefficients=(0.35875, 0.48829, 0.14128, 0.01168),
            description="Blackman-Harris window (4 termini)",
            family="window",
        ),
        'gaussian': WindowSpec(
            name='gaussian',
            shape=WindowShape.GAUSSIAN,
            params={'sigma': 0.4},
            description="Gaussian window (sigma 0.4)",
            family="window",
        ),
        'kaiser': WindowSpec(
            name='kaiser',
            shape=WindowShape.KAISER,
            params={'beta': 6.0},
            description="Kaiser-Bessel window (beta 6)",
            family="window",
        ),
        'rectangle': WindowSpec(
            name='rectangle',
            shape=WindowShape.RECTANGULAR,
            description="Rectangular/Dirichlet window",
            family="window",
        ),
        'sinc': WindowSpec(
            name='sinc',
            shape=WindowShape.SINC_LOBE,
            description="Sinc function (lobo centrale)",
            family="window",
        ),

        'half_sine': WindowSpec(
            name='half_sine',
            shape=WindowShape.SINE_LOBE,
            description="Half-sine envelope",
            family="custom",
        ),

        # Curve asimmetriche (Roads-style).
        'expodec': _asymmetric_curve(
            'expodec', 1.0, 4.0, 0.0,
            "Exponential decay (Roads-style)"),
        'expodec_strong': _asymmetric_curve(
            'expodec_strong', 1.0, 10.0, 0.0,
            "Strong exponential decay"),
        'exporise': _asymmetric_curve(
            'exporise', 0.0, -4.0, 1.0,
            "Exponential rise"),
        'exporise_strong': _asymmetric_curve(
            'exporise_strong', 0.0, -10.0, 1.0,
            "Strong exponential rise"),
        'rexpodec': _asymmetric_curve(
            'rexpodec', 1.0, -4.0, 0.0,
            "Reverse exponential decay"),
        'rexporise': _asymmetric_curve(
            'rexporise', 0.0, 4.0, 1.0,
            "Reverse exponential rise"),
    }

    # Alias per backward compatibility
    ALIASES = {
        'triangle': 'bartlett'
    }

    @classmethod
    def canonical(cls, name: str) -> Optional[str]:
        """Nome canonico di `name`, risolti gli alias. None se il catalogo
        non conosce il nome.

        E' il punto in cui un alias smette di essere tale: chi materializza
        una finestra (statement Csound, array NumPy) passa di qui e lavora
        sempre sul nome canonico, cosi' i due adapter non possono divergere
        su quali nomi lo YAML puo' scrivere.
        """
        resolved_name = cls.ALIASES.get(name, name)
        return resolved_name if resolved_name in cls.WINDOWS else None

    @classmethod
    def get(cls, name: str) -> Optional[WindowSpec]:
        """Ottieni specifica envelope (gestisce alias)."""
        resolved_name = cls.canonical(name)
        return cls.WINDOWS.get(resolved_name) if resolved_name else None

    @classmethod
    def all_names(cls) -> List[str]:
        """Tutti i nomi validi (inclusi alias)."""
        return list(cls.WINDOWS.keys()) + list(cls.ALIASES.keys())

    @classmethod
    def get_by_family(cls, family: str) -> List[WindowSpec]:
        """Filtra per famiglia."""
        return [spec for spec in cls.WINDOWS.values()
                if spec.family == family]

    @classmethod
    def get_by_shape(cls, shape: str) -> List[WindowSpec]:
        """Filtra per forma matematica.

        E' la lettura che serve a un emitter per sapere quanto della sua
        traduzione e' esercitata dal catalogo, e a un test per parametrizzare
        sulle forme invece che sui nomi.
        """
        return [spec for spec in cls.WINDOWS.values()
                if spec.shape == shape]
