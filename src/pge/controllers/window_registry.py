"""
WindowRegistry: il catalogo delle finestre grano.

Single source of truth su quali nomi lo YAML puo' scrivere e qual e' il
canonico di ciascuno. Descrive ogni finestra nei termini della GEN routine
che la genera, ma non la materializza: gli adapter sono `CsoundEmitter`
(statement `f`) e `NumpyWindowRegistry` (array), issue #203.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

@dataclass
class WindowSpec:
    """
    Specifica di una window Csound per finestratura grano.
    
    Attributes:
        name: identificatore univoco (e.g., 'hanning')
        gen_routine: numero GEN Csound
        gen_params: parametri della GEN routine
        description: descrizione leggibile
        family: categoria (window, asymmetric, custom)
    """
    name: str
    gen_routine: int
    gen_params: List
    description: str
    family: str = "window"

class WindowRegistry:
    """
    Registro centralizzato delle window disponibili.
    Usato sia da Generator che da UI/validation.
    """
    
    # Definizioni dichiarative (invece di if/elif)
    WINDOWS = {
        # GEN20: Window Functions
        'hamming': WindowSpec(
            name='hamming',
            gen_routine=20,
            gen_params=[1, 1],
            description="Hamming window (GEN20 opt 1)",
            family="window"
        ),
        'hanning': WindowSpec(
            name='hanning',
            gen_routine=20,
            gen_params=[2, 1],
            description="Hanning/von Hann window (GEN20 opt 2)",
            family="window"
        ),
        'bartlett': WindowSpec(
            name='bartlett',
            gen_routine=20,
            gen_params=[3, 1],
            description="Bartlett/Triangle window (GEN20 opt 3)",
            family="window"
        ),
        'blackman': WindowSpec(
            name='blackman',
            gen_routine=20,
            gen_params=[4, 1],
            description="Blackman window (GEN20 opt 4)",
            family="window"
        ),
        'blackman_harris': WindowSpec(
            name='blackman_harris',
            gen_routine=20,
            gen_params=[5, 1],
            description="Blackman-Harris window (GEN20 opt 5)",
            family="window"
        ),
        'gaussian': WindowSpec(
            name='gaussian',
            gen_routine=20,
            gen_params=[6, 1, 3],  # opt=6, shape param=3
            description="Gaussian window (GEN20 opt 6)",
            family="window"
        ),
        'kaiser': WindowSpec(
            name='kaiser',
            gen_routine=20,
            gen_params=[7, 1, 6],  # opt=7, beta=6
            description="Kaiser-Bessel window (GEN20 opt 7)",
            family="window"
        ),
        'rectangle': WindowSpec(
            name='rectangle',
            gen_routine=20,
            gen_params=[8, 1],
            description="Rectangular/Dirichlet window (GEN20 opt 8)",
            family="window"
        ),
        'sinc': WindowSpec(
            name='sinc',
            gen_routine=20,
            gen_params=[9, 1, 1],
            description="Sinc function (GEN20 opt 9)",
            family="window"
        ),
        
        # GEN09: Composite Waveforms
        'half_sine': WindowSpec(
            name='half_sine',
            gen_routine=9,
            gen_params=[0.5, 1, 0],
            description="Half-sine envelope (GEN09)",
            family="custom"
        ),
        
        # GEN16: Asymmetric Curves
        'expodec': WindowSpec(
            name='expodec',
            gen_routine=16,
            gen_params=[1, 1024, 4, 0],
            description="Exponential decay (GEN16, Roads-style)",
            family="asymmetric"
        ),
        'expodec_strong': WindowSpec(
            name='expodec_strong',
            gen_routine=16,
            gen_params=[1, 1024, 10, 0],
            description="Strong exponential decay (GEN16)",
            family="asymmetric"
        ),
        'exporise': WindowSpec(
            name='exporise',
            gen_routine=16,
            gen_params=[0, 1024, -4, 1],
            description="Exponential rise (GEN16)",
            family="asymmetric"
        ),
        'exporise_strong': WindowSpec(
            name='exporise_strong',
            gen_routine=16,
            gen_params=[0, 1024, -10, 1],
            description="Strong exponential rise (GEN16)",
            family="asymmetric"
        ),
        'rexpodec': WindowSpec(
            name='rexpodec',
            gen_routine=16,
            gen_params=[1, 1024, -4, 0],
            description="Reverse exponential decay (GEN16)",
            family="asymmetric"
        ),
        'rexporise': WindowSpec(
            name='rexporise',
            gen_routine=16,
            gen_params=[0, 1024, 4, 1],
            description="Reverse exponential rise (GEN16)",
            family="asymmetric"
        ),
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
    
