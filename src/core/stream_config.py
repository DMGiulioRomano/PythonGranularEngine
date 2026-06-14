# stream_config.py
from __future__ import annotations

from dataclasses import dataclass,fields
from typing import Optional, Union
    
@dataclass(frozen=True)
class StreamContext:
    stream_id: str
    onset: float
    duration: float
    sample: str
    sample_dur_sec: float          

    @classmethod
    def from_yaml(cls, yaml_data: dict, sample_dur_sec: float, allow_none: bool = True) -> 'StreamConfig':
        """        
        Contiene solo configurazioni che determinano il l'identità e il contesto dello stream.        
        """
        field_names = [f.name for f in fields(cls) if f.name != 'sample_dur_sec']

        
        if allow_none:
            # Includi i campi anche se il valore è None
            kwargs = {name: yaml_data[name] for name in field_names if name in yaml_data}
        else:
            # Includi solo campi con valori non-None
            kwargs = {
                name: yaml_data[name] 
                for name in field_names 
                if name in yaml_data and yaml_data[name] is not None
            }
        kwargs['sample_dur_sec'] = sample_dur_sec
        return cls(**kwargs)


@dataclass(frozen=True)
class StreamConfig:
    """
    Configurazione completa per un singolo stream.
    Contiene:
    - Regole di processo: dephase, time_mode, distribution_mode, etc.
    - Contesto
    
    Condiviso tra Stream e i suoi controller (PointerController, 
    PitchController, DensityController, VoiceManager).
    """
    dephase: Optional[Union[dict, bool, int, float, list]] = False
    range_always_active: bool = False
    distribution_mode: str = 'uniform'
    time_mode: str = 'absolute'
    time_scale: float = 1.0
    clip_strategy: str = 'overflow_margin'
    clip_margin: float = 0.0
    context: Optional[StreamContext] = None

    @classmethod
    def from_yaml(cls, yaml_data: dict, context: StreamContext, allow_none: bool = True) -> 'StreamConfig':
        """
        Regole di processo per la sintesi granulare.
        
        Contiene solo configurazioni che determinano il COMPORTAMENTO
        del sistema, non l'identità o il contesto dello stream.
        
        Può essere condiviso tra più stream che utilizzano le stesse
        regole di processo (anche se tipicamente ogni stream ha il suo).
        """
        field_names = [f.name for f in fields(cls)]
        
        if allow_none:
            # Includi i campi anche se il valore è None
            kwargs = {name: yaml_data[name] for name in field_names if name in yaml_data}
        else:
            # Includi solo campi con valori non-None
            kwargs = {
                name: yaml_data[name] 
                for name in field_names 
                if name in yaml_data and yaml_data[name] is not None
            }
        kwargs['context'] = context
        return cls(**kwargs)
