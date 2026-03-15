"""
parameter_factory.py

Factory che assembla oggetti Parameter per Stream.

Combina:
- parameter_schema.py: Sa DOVE trovare i dati nel YAML
- parameter_definitions.py: Sa QUALI SONO i limiti (bounds)
- parser.py: Sa COME creare oggetti Parameter

Design Pattern:
- Factory: Crea oggetti complessi nascondendo i dettagli
- Facade: Interfaccia semplice verso sottosistemi complessi
"""

from typing import Any
from parameters.parameter import Parameter
from parameters.parser import GranularParser
from parameters.parameter_schema import ParameterSpec
import inspect

class ParameterFactory:
    """
    Factory per la creazione dei parametri di Stream.
    
    Legge lo schema dichiarativo e usa GranularParser per creare
    gli oggetti Parameter. Stream non deve sapere come funziona
    il parsing, riceve solo i Parameter pronti all'uso.
    
    Usage:
        factory = ParameterFactory('stream_1', duration=10.0)
        params = factory.create_all_parameters(yaml_data)
        
        # params = {'volume': Parameter, 'pan': Parameter, ...}
        
        # In Stream.__init__:
        for name, param in params.items():
            setattr(self, name, param)
    """
    
    def __init__(self, config):
        """
        Inizializza la factory con il contesto dello Stream.
        
        Args:
            stream_id: ID dello stream (per logging)
            duration: Durata totale (per normalizzazione envelope)
            time_mode: 'absolute' o 'normalized'
        """
        self._parser = GranularParser(config)
        self._stream_id = config.context.stream_id
        
    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================
    
    def create_smart_parameter(
        self, 
        spec: ParameterSpec, 
        yaml_data: dict
    ) -> Parameter:
        """
        Crea un oggetto Parameter usando GranularParser.
        """
        # 1. Estrai valore base dal YAML
        value = self._get_nested(yaml_data, spec.yaml_path, spec.default)

        # 2. Estrai range se definito nello schema
        range_val = None
        if spec.range_path:
            range_val = self._get_nested(yaml_data, spec.range_path, None)

        # 4. Usa il parser per creare il Parameter
        return self._parser.parse_parameter(
            name=spec.name,  # Stessa chiave per bounds e attributo
            value_raw=value,
            range_raw=range_val,
        )
    
    def create_constant_parameter(self, name: str, value: float) -> Parameter:
        """
        Crea un Parameter costante da un valore scalare, senza YAML.

        Usato per fallback interni (es. loop_end = sample_dur_sec)
        dove il valore e' gia' noto ma serve un Parameter con get_value().
        """
        return self._parser.parse_parameter(
            name=name,
            value_raw=value,
            range_raw=None,
        )

    def create_raw_parameter(self, spec: ParameterSpec, yaml_data: dict) -> Any:
        """
        Estrae un valore raw (non Parameter) dal YAML.
        
        Usato per parametri come 'grain_envelope' che sono stringhe.
        """
        return self._get_nested(yaml_data, spec.yaml_path, spec.default)
    
    @staticmethod
    def _get_nested(data: dict, path: str, default: Any) -> Any:
        """
        Naviga un dict con dot notation.
        
        Examples:
            _get_nested({'grain': {'duration': 0.05}}, 'grain.duration', 0.1)
            → 0.05
            
            _get_nested({'volume': -6}, 'volume', 0)
            → -6
            
            _get_nested({}, 'missing.path', 42)
            → 42
        """
        keys = path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current

    def _get_caller(self):   
        frame = inspect.currentframe().f_back
        caller_info = inspect.getframeinfo(frame)
        return f"{caller_info.function}:{caller_info.lineno}"
    

    def __repr__(self) -> str:
        return f"ParameterFactory(stream_id='{self._stream_id}')"