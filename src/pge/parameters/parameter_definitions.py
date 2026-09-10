"""
parameter_definitions.py

Questo modulo agisce come REGISTRY (Registro) centrale per le definizioni dei parametri.
Contiene i metadati e le regole di validazione (Bounds) per ogni parametro del sistema granulare.

Design Pattern:
- Value Object: La classe ParameterBounds è immutabile.
- Registry: Il dizionario GRANULAR_PARAMETERS centralizza la configurazione.

Qui definiamo COSA sono i parametri, non COME vengono calcolati.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict

from pge.shared.exceptions import InvalidFieldValueError

@dataclass(frozen=True)
class ParameterBounds:
    """
    Definisce i limiti e il comportamento di variazione per un parametro.
    
    Attributes:
        min_val (float): Valore minimo assoluto consentito (Safety Clamp).
        max_val (float): Valore massimo assoluto consentito (Safety Clamp).
        min_range (float): Valore minimo per il parametro range/randomness associato.
        max_range (float): Valore massimo per il parametro range/randomness associato.
        default_jitter (float): Valore di default per variazioni implicite (Scenario B).
        variation_mode (str): Strategia di variazione stocastica.
            - 'additive': (Default) Variazione continua float (valore ± range/2).
                          Es. Volume, Pan, Density.
            - 'quantized': Variazione a step interi (valore ± int(range/2)).
                           Es. Pitch in semitoni, Sample ID.
            - 'invert':   Variazione booleana/probabilistica (flip 0 <-> 1).
                          Es. Reverse (non usa range additivo, usa probabilità).
    """
    min_val: float
    max_val: float | None
    min_range: float = 0.0
    max_range: float = 0.0
    default_jitter: float = 0.0
    variation_mode: str = 'additive'

# =============================================================================
# UNITA' DEL RANGE DICHIARATO
# =============================================================================
# Terzo asse della banda dei `_range`, ortogonale a `distribution_mode` (come
# la banda si riempie) e a `range_anchor` (dove cade la base dentro la banda):
# **quanto la banda e' larga**.
#
#   absolute (default) -> la larghezza e' il numero scritto, nell'unita' del
#                         parametro (secondi, dB, gradi)
#   relative           -> il numero e' una FRAZIONE del valore base a quel
#                         momento, quindi la larghezza e' `frazione * base`
#
# Nasce da issue #267: con `grain.duration` che spazia su piu' ordini di
# grandezza una banda assoluta e' molte volte la durata sui grani corti e
# percentualmente trascurabile sui lunghi, e il carattere della dispersione
# cambia da solo lungo lo sweep. Precedente in casa: `pointer.offset_range` e'
# gia' relativo, frazione della finestra di loop attiva.
#
# Sta qui e non in distribution_strategy.py accanto a RANGE_ANCHORS perche'
# quello che l'unita' cambia e' il DOMINIO del range — la materia di questo
# modulo — non il modo in cui la distribuzione lo riempie: chi consuma
# l'ancora e' la DistributionStrategy, chi consuma l'unita' e' il Parameter,
# prima che la distribuzione entri in scena.

RANGE_UNIT_ABSOLUTE = 'absolute'
RANGE_UNIT_RELATIVE = 'relative'

#: Grafie ammesse per una chiave `<param>_range_unit`. La prima e' canonica.
#: Esposto come registry perche' PGE-ls e PGE-ui lo leggano dal vivo invece di
#: tenerne una copia statica (stesso ruolo di RANGE_ANCHORS e LOOP_UNITS).
RANGE_UNITS = (RANGE_UNIT_ABSOLUTE, RANGE_UNIT_RELATIVE)

#: Default: assoluto, cioe' la semantica storica. Chi non scrive la chiave non
#: vede cambiare niente, e nessun YAML esistente si rilegge diversamente.
RANGE_UNIT_DEFAULT = RANGE_UNIT_ABSOLUTE

#: Dominio del range dichiarato in modalita' relativa: una frazione in [0, 1].
#: 1.0 significa una banda larga quanto la base, che le due ancore consumano in
#: modi diversi — `center` -> [base/2, 3*base/2] (±50%), `min` -> [base, 2*base]
#: (+100%). E' un dominio proprio della modalita', non del parametro: che per
#: `grain_duration` coincida col max_range assoluto (1.0 s) e' una coincidenza
#: numerica, e alzare l'uno non deve alzare l'altro.
RELATIVE_RANGE_BOUNDS = (0.0, 1.0)


def validate_range_unit(unit, field: str = 'range_unit') -> str:
    """Valida una grafia di `<param>_range_unit`, restituendola normalizzata.

    Args:
        unit: la grafia scritta nel YAML.
        field: il path YAML della chiave, per nominarla nell'errore. Il
            chiamante lo conosce (`spec.range_unit_path`), questo modulo no.

    Raises:
        InvalidFieldValueError: se la grafia non e' fra RANGE_UNITS.
    """
    if unit not in RANGE_UNITS:
        raise InvalidFieldValueError(
            field=field,
            value=unit,
            hint=f"valori ammessi: {' | '.join(RANGE_UNITS)}",
        )
    return unit


def range_unit_is_relative(unit) -> bool:
    """True se la grafia dichiara una banda relativa.

    Lettura PURA: non valida il vocabolario. La validazione tocca a chi conosce
    il path YAML della chiave e sa quindi nominarla nell'errore
    (ParameterOrchestrator); qui una grafia sbagliata legge come non-relativa e
    l'errore arriva comunque, dal punto che sa dirlo bene. Una grafia sola per
    "e' relativo", condivisa fra il pre-normalizzatore delle unita' dello
    Stream e l'orchestratore.
    """
    return unit == RANGE_UNIT_RELATIVE


def relative_range_bounds(bounds: 'ParameterBounds') -> 'ParameterBounds':
    """Gli stessi bounds col dominio del range sostituito da quello frazionario.

    Sostituisce, non restringe: il dominio assoluto e quello relativo misurano
    grandezze diverse, e un `min` fra i due non vorrebbe dire niente.
    """
    return replace(
        bounds,
        min_range=RELATIVE_RANGE_BOUNDS[0],
        max_range=RELATIVE_RANGE_BOUNDS[1],
    )


# =============================================================================
# SYSTEM CONSTANTS & DEFAULTS
# =============================================================================

# Probabilità di default (1%) usata quando deviation_probability è attivo ma senza range espliciti.
# Questo attiva il "Jitter Implicito" definito nei bounds dei parametri.
DEFAULT_PROB = 1.0 

# =============================================================================
# PARAMETER REGISTRY
# =============================================================================
# Qui sono definiti tutti i parametri supportati dal sistema.
# Se aggiungi un nuovo parametro al motore audio, devi aggiungerlo qui.

GRANULAR_PARAMETERS: Dict[str, ParameterBounds] = {
    
    # =========================================================================
    # DENSITY & TIME
    # =========================================================================
    'density': ParameterBounds(
        min_val=0.01,
        max_val=4000.0,
    ),
    
    'fill_factor': ParameterBounds(
        min_val=0.001,
        max_val=50.0,
    ),
    
    'distribution': ParameterBounds(
        min_val=0.0,
        max_val=1.0
        # distribution non ha solitamente un range stocastico associato
    ),
    
    'effective_density': ParameterBounds(
        min_val=1,
        max_val=4000.0
    ),

    # =========================================================================
    # GRAIN PROPERTIES
    # =========================================================================
    'grain_duration': ParameterBounds(
        min_val=0.001,  # 1 ms
        max_val=10.0,    # 10 secondi
        min_range=0.0,
        max_range=1.0,
        default_jitter=0.01,
        variation_mode='additive'
    ),
    
    'reverse': ParameterBounds(
        min_val=0,
        max_val=1,
        min_range=0,
        max_range=1,
        variation_mode='invert'  # <--- NOTA: (Boolean Flip)
    ),

    # Verso di lettura interno al grano (issue #207): -1 indietro, +1 avanti.
    # Alternativa dichiarativa a 'reverse', in exclusive group con essa.
    # variation_mode='negate' perche' il dominio ha segno: il flip per-grano
    # e' un cambio di segno, non il `1 - base` di 'invert'.
    'read_direction': ParameterBounds(
        min_val=-1,
        max_val=1,
        min_range=0,
        max_range=0,
        variation_mode='negate'
    ),

    'grain_envelope': ParameterBounds(
        min_val=0,      # Non usato per choice
        max_val=0,      # Non usato per choice
        min_range=0.0,  # Non usato per choice
        max_range=0.0,  # Non usato per choice
        variation_mode='choice'  # Usa ChoiceVariation
    ),
    # =========================================================================
    # PITCH
    # =========================================================================
    # I bounds del pitch sono unit-driven: derivano da PitchUnit.value_bounds()
    # (±3 ottave per la famiglia EDO, [0.001, 8] per ratio) e non sono registrati
    # qui. Vedi src/parameters/pitch_unit.py.

    # =========================================================================
    # POINTER (PLAYHEAD)
    # =========================================================================
    'pointer_speed_ratio': ParameterBounds(
        min_val=-100.0,
        max_val=100.0
    ),
    
    'pointer_deviation': ParameterBounds(
        min_val=-1.0,
        max_val=1.0,        
        min_range=0.0,
        max_range=1.0,
        default_jitter=0.05,
        variation_mode='additive'
    ),
    
    'loop_dur': ParameterBounds(
        min_val=0.005,
        max_val=None  # bound reale = sample_dur_sec, passato dinamicamente
    ),

    'loop_start': ParameterBounds(
        min_val=0,
        max_val=None  # bound reale = sample_dur_sec, passato dinamicamente
    ),

    'loop_end': ParameterBounds(
        min_val=0.0,
        max_val=None  # bound reale = sample_dur_sec, passato dinamicamente
    ),


    # =========================================================================
    # OUTPUT (SPATIALIZATION & AMP)
    # =========================================================================
    'volume': ParameterBounds(
        min_val=-120.0,
        max_val=12.0,
        min_range=0.0,
        max_range=24.0,
        default_jitter=3
    ),
    
    'pan': ParameterBounds(
        min_val=-3600.0, # Supporto per pan rotativo su più giri
        max_val=3600.0,
        min_range=0.0,
        max_range=360.0,
        default_jitter=30.0
    ),

    # =========================================================================
    # VOICES
    # =========================================================================
    'num_voices': ParameterBounds(
        min_val=1.0,
        max_val=256.0, # Soglia di sicurezza: consente texture a voci molto dense
        variation_mode='quantized' # Le voci sono intere, ma gestite dal manager
    ),
    
    'voice_pitch_offset': ParameterBounds(
        min_val=-48.0,
        max_val=48.0
    ),
    
    'voice_pointer_offset': ParameterBounds(
        min_val=-1.0, # Consenti offset negativi
        max_val=1.0
    ),
    
    'voice_pointer_range': ParameterBounds(
        min_val=0.0,
        max_val=1.0
    ),

    'scatter': ParameterBounds(
        min_val=0.0,
        max_val=1.0,
        variation_mode='additive',
    ),
}

_LOOP_PARAMS = frozenset({'loop_dur', 'loop_start', 'loop_end'})


def get_parameter_definition(
    param_name: str,
    sample_dur_sec: float | None = None,
    output_sr: int | None = None,
) -> ParameterBounds:
    """
    Recupera la definizione di un parametro dal registro.

    Per loop_dur, loop_start e loop_end, se sample_dur_sec è fornito,
    restituisce un nuovo ParameterBounds con max_val = sample_dur_sec.

    Per grain_duration, se output_sr è fornito, restituisce un nuovo
    ParameterBounds con min_val = 1 campione (1/output_sr): la durata
    minima di un grano è la risoluzione temporale del motore.

    Tutti gli altri campi rimangono invariati.

    Args:
        param_name: Il nome del parametro (es. 'density')
        sample_dur_sec: Durata del file audio in secondi (opzionale).
            Se fornito, sovrascrive max_val per i parametri loop.
        output_sr: Sample rate di output del motore (opzionale).
            Se fornito, sovrascrive min_val per grain_duration.

    Returns:
        ParameterBounds: L'oggetto configurazione.

    Raises:
        KeyError: Se il parametro non esiste nel registro.
    """
    if param_name not in GRANULAR_PARAMETERS:
        raise KeyError(f"Parametro '{param_name}' non definito in parameter_definitions.py")
    bounds = GRANULAR_PARAMETERS[param_name]
    if sample_dur_sec is not None and param_name in _LOOP_PARAMS:
        return ParameterBounds(
            min_val=bounds.min_val,
            max_val=sample_dur_sec,
            min_range=bounds.min_range,
            max_range=bounds.max_range,
            default_jitter=bounds.default_jitter,
            variation_mode=bounds.variation_mode,
        )
    if output_sr is not None and param_name == 'grain_duration':
        return ParameterBounds(
            min_val=1.0 / output_sr,
            max_val=bounds.max_val,
            min_range=bounds.min_range,
            max_range=bounds.max_range,
            default_jitter=bounds.default_jitter,
            variation_mode=bounds.variation_mode,
        )
    return bounds
