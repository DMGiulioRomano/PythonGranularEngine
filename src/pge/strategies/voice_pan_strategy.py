# src/strategies/voice_pan_strategy.py
"""
voice_pan_strategy.py

Strategy pattern per la distribuzione spaziale (pan) delle voci
nella sintesi granulare multi-voice.

Responsabilita':
- Calcolare l'offset di pan MACRO per una voce data, basandosi su
  voice_index, num_voices e tempo corrente.
- NON gestisce il micro-jitter per-grano (responsabilita' del VoiceManager).
- Ogni implementazione concreta garantisce voice_index==0 → 0.0 (Voice-0 invariant).

Design (uniformato a voice_onset_strategy / voice_pointer_strategy / voice_pitch_strategy):
- VoicePanStrategy (ABC): interfaccia comune
- RangePanStrategy: distribuzione deterministica equidistante in [-spread/2, +spread/2]
- StochasticPanStrategy: posizioni casuali stabili per voce (seed deterministico)
- StepPanStrategy: voce i → i × step gradi
- VOICE_PAN_STRATEGIES: registry globale {nome: classe}
- register_voice_pan_strategy(): estensibilita' dinamica
- VoicePanStrategyFactory: factory con create() statico

Ogni strategy possiede il proprio parametro come StrategyParam
(Union[float, Envelope]) e lo risolve internamente con resolve_param(param, time):
spread per range/stochastic, step per step.

Coerente con: voice_onset_strategy.py, voice_pointer_strategy.py,
              voice_pitch_strategy.py
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Type

from pge.parameters.parameter import resolve_param, StrategyParam
from pge.shared.exceptions import (
    InvalidStrategyConfigError,
    StrategyNotFoundError,
)
from pge.shared.seeding import voice_rng


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class VoicePanStrategy(ABC):
    """
    Strategy astratta per la distribuzione spaziale delle voci.

    Ogni implementazione definisce come le voci vengono distribuite
    nel panorama stereo/spaziale in base al loro indice e al numero
    totale di voci attive.

    Il valore restituito e' un OFFSET in gradi rispetto al pan base
    dello stream. Il VoiceManager somma questo offset al pan_base
    per ottenere il pan finale della voce.

    Voice-0 invariant: ogni implementazione concreta deve restituire 0.0
    per voice_index == 0, garantendo che la voce di riferimento non
    abbia offset spaziale.
    """

    @abstractmethod
    def get_pan_offset(
        self,
        voice_index: int,
        num_voices: int,
        time: float,
    ) -> float:
        """
        Calcola l'offset di pan macro per la voce specificata al tempo dato.

        Args:
            voice_index: indice della voce (0-based)
            num_voices: numero totale di voci attive
            time: tempo corrente in secondi (onset del grain)

        Returns:
            Offset in gradi da sommare al pan base dello stream.
            Voce 0 → sempre 0.0.
        """
        pass  # pragma: no cover

    @property
    @abstractmethod
    def name(self) -> str:
        """Nome identificativo della strategy, deve corrispondere alla chiave nel registry."""
        pass  # pragma: no cover


# =============================================================================
# CONCRETE STRATEGIES
# =============================================================================

class RangePanStrategy(VoicePanStrategy):
    """
    Distribuzione deterministica equidistante.

    Le voci vengono distribuite linearmente nell'intervallo
    [-spread/2, +spread/2] con passo costante.

    Con N voci:
        offset(v) = -spread/2 + v * spread / (N - 1)   per N > 1
        offset(0) = 0.0                                  per N == 1

    `spread` può essere scalare o Envelope (risolto al tempo del grain).
    """

    def __init__(self, spread: StrategyParam):
        self.spread = spread

    def get_pan_offset(
        self,
        voice_index: int,
        num_voices: int,
        time: float,
    ) -> float:
        """Calcola offset equidistante in [-spread/2, +spread/2]."""
        spread = resolve_param(self.spread, time)
        if voice_index == 0 or spread == 0.0 or num_voices <= 1:
            return 0.0

        return -spread / 2.0 + voice_index * spread / (num_voices - 1)

    @property
    def name(self) -> str:
        return 'range'


class StochasticPanStrategy(VoicePanStrategy):
    """
    Distribuzione stocastica uniforme con posizione stabile per voce.

    _cache[voice_index] memorizza il fattore normalizzato in [-1, 1].
    Offset = _cache[vi] * spread / 2; la magnitudine può variare nel tempo
    se spread è un Envelope.
    Seed (issue #81): se `seed` è None il RNG per-voce usa hash(stream_id+vi) —
    stabile ENTRO un run, NON riproducibile fra processi (hash() randomizzato
    per-processo, PYTHONHASHSEED non fissato). Se `seed` è valorizzato la
    derivazione è hashlib (vedi shared.seeding.voice_rng): l'offset diventa
    riproducibile fra processi diversi.
    Voce 0 → sempre 0.0.

    Uso tipico: posizionamento "random but bounded" delle voci, texture
    dove la distribuzione spaziale deve essere imprevedibile ma contenuta.
    """

    def __init__(self, spread: StrategyParam, stream_id: str, seed=None):
        self.spread = spread
        self.stream_id = stream_id
        self.seed = seed
        self._cache: Dict[int, float] = {}

    def get_pan_offset(
        self,
        voice_index: int,
        num_voices: int,
        time: float,
    ) -> float:
        """Campiona offset uniforme nel range [-spread/2, +spread/2], stabile per voce."""
        spread = resolve_param(self.spread, time)
        if spread == 0.0:
            return 0.0

        if spread < 0.0:
            raise InvalidStrategyConfigError(
                strategy_kind="voice_pan",
                field="spread",
                value=spread,
                hint="spread deve essere >= 0",
            )

        if voice_index == 0:
            return 0.0

        if voice_index not in self._cache:
            rng = voice_rng(self.seed, self.stream_id, voice_index)
            self._cache[voice_index] = rng.uniform(-1.0, 1.0)

        return self._cache[voice_index] * spread / 2.0

    @property
    def name(self) -> str:
        return 'stochastic'


class StepPanStrategy(VoicePanStrategy):
    """
    Spaziatura lineare uniforme tra voci.

    Voce i → i × step(t) gradi.
    Esempio: step=15, 4 voci → [0, 15, 30, 45] gradi.

    Coerente con LinearOnsetStrategy (onset) e StepPitchStrategy (pitch):
    offset proporzionale all'indice della voce. `step` può essere negativo
    (pan verso sinistra) e può essere scalare o Envelope.
    """

    def __init__(self, step: StrategyParam):
        self.step = step

    def get_pan_offset(
        self,
        voice_index: int,
        num_voices: int,
        time: float,
    ) -> float:
        """Ritorna voice_index × step risolto al tempo dato."""
        if voice_index == 0:
            return 0.0
        return float(voice_index) * resolve_param(self.step, time)

    @property
    def name(self) -> str:
        return 'step'


# =============================================================================
# REGISTRY
# =============================================================================

VOICE_PAN_STRATEGIES: Dict[str, Type[VoicePanStrategy]] = {
    'range':      RangePanStrategy,
    'stochastic': StochasticPanStrategy,
    'step':       StepPanStrategy,
}


# =============================================================================
# FUNZIONE DI REGISTRAZIONE (per estensibilita' dinamica)
# =============================================================================

def register_voice_pan_strategy(
    name: str,
    strategy_class: Type[VoicePanStrategy]
) -> None:
    """
    Registra una nuova strategy di pan voce nel registry globale.

    Permette di aggiungere implementazioni custom senza modificare
    questo modulo (Open/Closed Principle).

    Args:
        name: chiave stringa per il registry (es. 'stereo_spread')
        strategy_class: classe concreta che eredita da VoicePanStrategy

    Esempio:
        class MyStereoSpread(VoicePanStrategy):
            def __init__(self, spread):
                self.spread = spread
            def get_pan_offset(self, voice_index, num_voices, time):
                return (voice_index % 2) * self.spread - self.spread / 2
            @property
            def name(self): return 'stereo_spread'

        register_voice_pan_strategy('stereo_spread', MyStereoSpread)
    """
    VOICE_PAN_STRATEGIES[name] = strategy_class
    print(
        f"Registrata nuova strategia pan voce: "
        f"'{name}' -> {strategy_class.__name__}"
    )


# =============================================================================
# FACTORY
# =============================================================================

class VoicePanStrategyFactory:
    """
    Factory per la creazione di istanze VoicePanStrategy.

    Legge dal registry globale VOICE_PAN_STRATEGIES per supportare
    estensibilita' dinamica tramite register_voice_pan_strategy().

    Uso:
        strategy = VoicePanStrategyFactory.create('range', spread=120.0)
        strategy = VoicePanStrategyFactory.create('stochastic', spread=180.0, stream_id='s1')
        strategy = VoicePanStrategyFactory.create('step', step=15.0)
        offset = strategy.get_pan_offset(voice_index=2, num_voices=4, time=0.0)
    """

    @staticmethod
    def create(strategy_name: str, **kwargs) -> VoicePanStrategy:
        """
        Crea e restituisce un'istanza della strategy specificata.

        Args:
            strategy_name: nome della strategy nel registry
                           ('range', 'stochastic', 'step', o custom)
            **kwargs: parametri passati al costruttore della strategy

        Returns:
            Istanza di VoicePanStrategy corrispondente al nome

        Raises:
            StrategyNotFoundError: se strategy_name non e' nel registry,
                        con messaggio che elenca le strategy disponibili
        """
        if strategy_name not in VOICE_PAN_STRATEGIES:
            raise StrategyNotFoundError(
                strategy_kind="voice_pan",
                name=strategy_name,
                available=list(VOICE_PAN_STRATEGIES.keys()),
            )

        strategy_class = VOICE_PAN_STRATEGIES[strategy_name]
        return strategy_class(**kwargs)
