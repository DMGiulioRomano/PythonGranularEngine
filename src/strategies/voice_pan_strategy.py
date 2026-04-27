# src/strategies/voice_pan_strategy.py
"""
voice_pan_strategy.py

Strategy pattern per la distribuzione spaziale (pan) delle voci
nella sintesi granulare multi-voice.

Responsabilita':
- Calcolare l'offset di pan MACRO per una voce data, basandosi su
  voice_index, num_voices, spread totale e tempo corrente.
- NON gestisce il micro-jitter per-grano (responsabilita' del VoiceManager).
- Ogni implementazione concreta garantisce voice_index==0 → 0.0 (Voice-0 invariant).

Design:
- VoicePanStrategy (ABC): interfaccia comune
- LinearPanStrategy: distribuzione deterministica equidistante
- RandomPanStrategy: distribuzione stocastica per voce, seed deterministico
- AdditivePanStrategy: offset fisso additivo uguale per tutte le voci
- VOICE_PAN_STRATEGIES: registry globale {nome: classe}
- register_voice_pan_strategy(): estensibilita' dinamica
- VoicePanStrategyFactory: factory con create() statico

Coerente con: variation_strategy.py, variation_registry.py,
              distribution_strategy.py, time_distribution.py
"""

import random
from abc import ABC, abstractmethod
from typing import Dict, Type


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
        spread: float,
        time: float,
    ) -> float:
        """
        Calcola l'offset di pan macro per la voce specificata al tempo dato.

        Args:
            voice_index: indice della voce (0-based)
            num_voices: numero totale di voci attive
            spread: escursione totale in gradi (già risolta da VoiceManager)
            time: tempo corrente in secondi (onset del grain)

        Returns:
            Offset in gradi da sommare al pan base dello stream.
            Con spread=0 deve sempre ritornare 0.0.
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

class LinearPanStrategy(VoicePanStrategy):
    """
    Distribuzione deterministica equidistante.

    Le voci vengono distribuite linearmente nell'intervallo
    [-spread/2, +spread/2] con passo costante.

    Con N voci:
        offset(v) = -spread/2 + v * spread / (N - 1)   per N > 1
        offset(0) = 0.0                                  per N == 1

    Il parametro `time` è accettato ma ignorato (spread già risolto dal VoiceManager).
    """

    def get_pan_offset(
        self,
        voice_index: int,
        num_voices: int,
        spread: float,
        time: float,
    ) -> float:
        """Calcola offset lineare equidistante."""
        if voice_index == 0 or spread == 0.0 or num_voices <= 1:
            return 0.0

        return -spread / 2.0 + voice_index * spread / (num_voices - 1)

    @property
    def name(self) -> str:
        return 'linear'


class RandomPanStrategy(VoicePanStrategy):
    """
    Distribuzione stocastica uniforme con posizione stabile per voce.

    _cache[voice_index] memorizza il fattore normalizzato in [-1, 1].
    Offset = _cache[vi] * spread / 2.
    Seed = hash(stream_id + str(voice_index)) — riproducibile tra sessioni.
    Voce 0 → sempre 0.0.

    Uso tipico: posizionamento "random but bounded" delle voci, texture
    dove la distribuzione spaziale deve essere imprevedibile ma contenuta.
    """

    def __init__(self, stream_id: str):
        self.stream_id = stream_id
        self._cache: Dict[int, float] = {}

    def get_pan_offset(
        self,
        voice_index: int,
        num_voices: int,
        spread: float,
        time: float,
    ) -> float:
        """Campiona offset uniforme nel range [-spread/2, +spread/2], stabile per voce."""
        if spread == 0.0:
            return 0.0

        if spread < 0.0:
            raise ValueError(
                f"spread deve essere >= 0, ricevuto: {spread}"
            )

        if voice_index == 0:
            return 0.0

        if voice_index not in self._cache:
            seed = hash(self.stream_id + str(voice_index))
            rng = random.Random(seed)
            self._cache[voice_index] = rng.uniform(-1.0, 1.0)

        return self._cache[voice_index] * spread / 2.0

    @property
    def name(self) -> str:
        return 'random'


class AdditivePanStrategy(VoicePanStrategy):
    """
    Offset fisso additivo identico per tutte le voci.

    Ritorna `spread` direttamente come offset, indipendentemente
    da voice_index e num_voices.

    Semantica: spread e' interpretato come un offset assoluto da
    applicare al pan base dello stream per tutte le voci.

    Il parametro `time` è accettato ma ignorato (spread già risolto dal VoiceManager).
    """

    def get_pan_offset(
        self,
        voice_index: int,
        num_voices: int,
        spread: float,
        time: float,
    ) -> float:
        """Ritorna spread come offset fisso per tutte le voci non-zero."""
        if voice_index == 0:
            return 0.0
        return spread

    @property
    def name(self) -> str:
        return 'additive'


# =============================================================================
# REGISTRY
# =============================================================================

VOICE_PAN_STRATEGIES: Dict[str, Type[VoicePanStrategy]] = {
    'linear':   LinearPanStrategy,
    'random':   RandomPanStrategy,
    'additive': AdditivePanStrategy,
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
            def get_pan_offset(self, voice_index, num_voices, spread, time):
                return (voice_index % 2) * spread - spread / 2
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
        strategy = VoicePanStrategyFactory.create('linear')
        strategy = VoicePanStrategyFactory.create('random', stream_id='s1')
        offset = strategy.get_pan_offset(voice_index=2, num_voices=4, spread=180.0, time=0.0)
    """

    @staticmethod
    def create(strategy_name: str, **kwargs) -> VoicePanStrategy:
        """
        Crea e restituisce un'istanza della strategy specificata.

        Args:
            strategy_name: nome della strategy nel registry
                           ('linear', 'random', 'additive', o custom)
            **kwargs: parametri passati al costruttore della strategy

        Returns:
            Istanza di VoicePanStrategy corrispondente al nome

        Raises:
            ValueError: se strategy_name non e' nel registry,
                        con messaggio che elenca le strategy disponibili
        """
        if strategy_name not in VOICE_PAN_STRATEGIES:
            available = ', '.join(sorted(VOICE_PAN_STRATEGIES.keys()))
            raise ValueError(
                f"Strategy pan voce non trovata: '{strategy_name}'. "
                f"Strategy disponibili: {available}"
            )

        strategy_class = VOICE_PAN_STRATEGIES[strategy_name]
        return strategy_class(**kwargs)
