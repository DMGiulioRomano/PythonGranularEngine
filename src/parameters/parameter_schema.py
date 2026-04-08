"""
parameter_schema.py

Schema DICHIARATIVO per i parametri di Stream.
Definisce la STRUTTURA YAML e le relazioni tra parametri.

Design Pattern: 
- Registry Pattern: Lista centralizzata di specifiche
- Data-Driven Configuration: Descrivi COSA, non COME

Questo file risponde a: "Dove trovo i dati nel YAML per Stream?"
parameter_definitions.py risponde a: "Quali sono i limiti di sicurezza?"

NOTA: I parametri dei Controller (pointer_speed, pitch_ratio, etc.) NON sono qui.
      Quelli sono gestiti direttamente dai rispettivi Controller.
"""

from dataclasses import dataclass
from typing import Optional, Any, List

@dataclass(frozen=True)
class ParameterSpec:
    """
    Specifica dichiarativa per un singolo parametro di Stream.
    
    Attributes:
        name: Nome del parametro (chiave in GRANULAR_PARAMETERS E attributo Stream)
        yaml_path: Percorso nel YAML (supporta dot notation: 'grain.duration')
        default: Valore di default se assente nel YAML
        range_path: Percorso YAML per il parametro _range associato (opzionale)
        dephase_key: Chiave nel blocco dephase (opzionale)
        is_smart: Se True, crea un oggetto Parameter. Se False, valore raw.
    
    NOTA: Non c'è bounds_key separato perché usiamo 'name' come chiave 
          in GRANULAR_PARAMETERS. Un nome, una identità. (DRY)
    """
    name: str
    yaml_path: str
    default: Any
    range_path: Optional[str] = None
    dephase_key: Optional[str] = None
    is_smart: bool = True
    exclusive_group: Optional[str] = None
    group_priority: int = 99  

# =============================================================================
# STREAM PARAMETER SCHEMA
# =============================================================================
# Qui sono definiti SOLO i parametri che diventano attributi di Stream.
# I parametri dei Controller (pointer, pitch, density, voices) sono gestiti
# dai rispettivi Controller e non appaiono qui.
#
# Per aggiungere un nuovo parametro a Stream:
# 1. Aggiungi i bounds in parameter_definitions.py (se non esistono)
# 2. Aggiungi una ParameterSpec qui sotto
# Fine! Il sistema fa il resto.
# =============================================================================

STREAM_PARAMETER_SCHEMA: List[ParameterSpec] = [
    
    # =========================================================================
    # OUTPUT PARAMETERS
    # =========================================================================
    ParameterSpec(
        name='volume',
        yaml_path='volume',
        default=-6.0,
        range_path='volume_range',
        dephase_key='volume'
    ),
    ParameterSpec(
        name='pan',
        yaml_path='pan',
        default=0.0,
        range_path='pan_range',
        dephase_key='pan'
    ),
    
    # =========================================================================
    # GRAIN PARAMETERS
    # =========================================================================
    ParameterSpec(
        name='grain_duration',
        yaml_path='grain.duration',
        default=0.05,
        range_path='grain.duration_range',
        dephase_key='duration'
    ),
    ParameterSpec(
        name='grain_envelope',
        yaml_path='grain.envelope',
        default='hanning',
        dephase_key='envelope',
        is_smart=False
    ),    
    # =========================================================================
    # REVERSE (caso speciale: variation_mode='invert')
    # =========================================================================
    ParameterSpec(
        name='reverse',
        yaml_path='grain.reverse',
        default=0,  # 0 = forward, 1 = reverse
        dephase_key='reverse'
        # Nota: 'reverse' usa variation_mode='invert', quindi
        # il dephase_key controlla la PROBABILITÀ di flip, non un range
    ),
]

# =============================================================================
# POINTER PARAMETER SCHEMA
# =============================================================================
# Parametri gestiti da PointerController.
# NOTA: I parametri loop (loop_start, loop_end, loop_dur) hanno logica speciale
#       con normalizzazione e sono gestiti direttamente nel Controller.
# =============================================================================

POINTER_PARAMETER_SCHEMA: List[ParameterSpec] = [
    ParameterSpec(
        name='pointer_start',
        yaml_path='start',
        default=0.0,
        is_smart=False  # Valore raw, non usa bounds
    ),
    ParameterSpec(
        name='pointer_speed_ratio',
        yaml_path='speed_ratio',
        default=1.0
    ),
    ParameterSpec(
        name='pointer_deviation',   
        yaml_path='_dummy_fixed_zero_',   
        default=0.0,                
        range_path='offset_range',  
        dephase_key='pointer',
    ),
    ParameterSpec(
        name='loop_start',
        yaml_path='loop_start',
        default=None
    ),
    ParameterSpec(
        name='loop_end',
        yaml_path='loop_end',
        default=None,
        exclusive_group='loop_bounds',
        group_priority=1                    
    ),
    ParameterSpec(
        name='loop_dur',
        yaml_path='loop_dur',
        default=None,
        exclusive_group='loop_bounds',
    ),
]

# =============================================================================
# PITCH PARAMETER SCHEMA
# =============================================================================
# Parametri gestiti da PitchController.
# NOTA: 'shift_semitones' e 'ratio' sono mutuamente esclusivi.
#       La logica di selezione modalità resta nel Controller.
# =============================================================================

PITCH_PARAMETER_SCHEMA: List[ParameterSpec] = [
    ParameterSpec(
        name='pitch_ratio',
        yaml_path='ratio',
        default=1.0,
        range_path='range',
        dephase_key='pitch', 
        exclusive_group='pitch_mode' 
    ),
    ParameterSpec(
        name='pitch_semitones',
        yaml_path='semitones',
        default=None,
        range_path='range',
        dephase_key='pitch' ,
        exclusive_group='pitch_mode', 
        group_priority=1  
    ),
]

# =============================================================================
# DENSITY PARAMETER SCHEMA
# =============================================================================
# Parametri gestiti da DensityController.
# NOTA: 'fill_factor' e 'density' sono mutuamente esclusivi.
#       fill_factor ha priorità. La logica di selezione resta nel Controller.
# =============================================================================

DENSITY_PARAMETER_SCHEMA: List[ParameterSpec] = [
    ParameterSpec(
        name='fill_factor',
        yaml_path='fill_factor',
        default=2,  # Default non-None
        exclusive_group='density_mode',  # <--- NUOVO GRUPPO
        group_priority=1  # <--- PRIORITÀ PIÙ ALTA
    ),
    ParameterSpec(
        name='density',
        yaml_path='density',
        default=None,  # None = non presente di default
        exclusive_group='density_mode',  # <--- STESSO GRUPPO
        group_priority=2  # <--- PRIORITÀ PIÙ BASSA
    ),
    ParameterSpec(
        name='distribution',
        yaml_path='distribution',
        default=0.0,
    ),
    ParameterSpec(
        name='effective_density',
        yaml_path='_internal_calc_',
        default=0.0,
        is_smart=False
    )
]


# =============================================================================
# REGISTRY COMPLETO: Tutti gli schema indicizzati
# =============================================================================

ALL_SCHEMAS = {
    'stream': STREAM_PARAMETER_SCHEMA,
    'pointer': POINTER_PARAMETER_SCHEMA,
    'pitch': PITCH_PARAMETER_SCHEMA,
    'density': DENSITY_PARAMETER_SCHEMA,
}


# =============================================================================
# HELPER FUNCTIONS AGGIUNTIVE
# =============================================================================

def get_schema(schema_name: str) -> List[ParameterSpec]:
    """
    Recupera uno schema per nome.
    
    Args:
        schema_name: 'stream', 'pointer', 'pitch', 'density'
        
    Raises:
        KeyError: Se lo schema non esiste.
    """
    if schema_name not in ALL_SCHEMAS:
        raise KeyError(f"Schema '{schema_name}' non trovato. "
                      f"Disponibili: {list(ALL_SCHEMAS.keys())}")
    return ALL_SCHEMAS[schema_name]


def get_all_schema_names() -> List[str]:
    """Ritorna i nomi di tutti gli schema disponibili."""
    return list(ALL_SCHEMAS.keys())


def get_parameter_spec_from_schema(schema_name: str, param_name: str) -> ParameterSpec:
    """
    Recupera una specifica parametro da uno schema specifico.
    
    Args:
        schema_name: Nome dello schema ('stream', 'pointer', etc.)
        param_name: Nome del parametro
        
    Raises:
        KeyError: Se schema o parametro non esistono.
    """
    schema = get_schema(schema_name)
    for spec in schema:
        if spec.name == param_name:
            return spec
    raise KeyError(f"Parametro '{param_name}' non trovato in schema '{schema_name}'")


# =============================================================================
# HELPER: Accesso per nome
# =============================================================================

_SCHEMA_BY_NAME = {}
for schema_list in ALL_SCHEMAS.values():
    for spec in schema_list:
        _SCHEMA_BY_NAME[spec.name] = spec


def get_parameter_spec(name: str) -> ParameterSpec:
    """
    Recupera la specifica di un parametro per nome.
    
    Raises:
        KeyError: Se il parametro non è nello schema.
    """
    if name not in _SCHEMA_BY_NAME:
        raise KeyError(f"Parametro '{name}' non definito in STREAM_PARAMETER_SCHEMA")
    return _SCHEMA_BY_NAME[name]


def get_all_parameter_names() -> List[str]:
    """Ritorna la lista di tutti i nomi dei parametri nello schema."""
    return [spec.name for spec in STREAM_PARAMETER_SCHEMA]
