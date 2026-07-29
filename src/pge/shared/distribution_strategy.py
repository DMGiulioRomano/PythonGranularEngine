"""
distribution_strategy.py - Strategy Pattern per distribuzioni statistiche.

Implementa diverse distribuzioni di probabilità per la generazione 
di valori stocastici nei parametri granulari.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Tuple

from pge.shared.exceptions import (
    InvalidFieldValueError,
    InvalidStrategyConfigError,
    StrategyNotFoundError,
)

# =============================================================================
# ANCORA DEL RANGE
# =============================================================================
# `spread` e' SEMPRE la larghezza della banda. L'ancora dice dove cade il
# valore base dentro quella banda:
#
#   center (default) -> [base - spread/2, base + spread/2]
#   min              -> [base,           base + spread]
#
# E' un asse ortogonale alla forma della distribuzione (`distribution_mode`),
# non una sua variante: la stessa ancora vale per uniform, gaussian e per
# qualunque distribuzione registrata in futuro.

ANCHOR_CENTER = 'center'
ANCHOR_MIN = 'min'

#: Valori validi della chiave YAML per-stream `range_anchor`. Esposto come
#: registry perche' PGE-ls e PGE-ui possano leggerlo dal vivo invece di
#: duplicarne una copia statica (stesso ruolo di DistributionFactory.modes()).
RANGE_ANCHORS = (ANCHOR_CENTER, ANCHOR_MIN)


def validate_range_anchor(anchor: str) -> str:
    """Valida il valore di `range_anchor`, restituendolo normalizzato.

    Raises:
        InvalidFieldValueError: se il valore non e' fra RANGE_ANCHORS.
    """
    if anchor not in RANGE_ANCHORS:
        raise InvalidFieldValueError(
            field='range_anchor',
            value=anchor,
            hint=f"valori ammessi: {' | '.join(RANGE_ANCHORS)}",
        )
    return anchor


class DistributionStrategy(ABC):
    """
    Strategy astratta per distribuzioni statistiche.

    Ogni strategia implementa un metodo sample() che genera
    un valore random secondo una specifica distribuzione.

    RNG locale (issue #154): il costruttore accetta un `random.Random`
    iniettato; i sample pescano da quello, così ogni Parameter ha il proprio
    stream di draw isolato. Senza rng si usa il modulo `random` globale
    (comportamento legacy).

    Ancora del range: il costruttore accetta `anchor` (ANCHOR_CENTER di
    default). L'ancora e' stato dell'istanza, non un argomento di sample():
    cosi' la firma `sample(center, spread)` resta invariata e i chiamanti
    (VariationStrategy) non devono sapere che l'ancora esiste.
    """

    def __init__(self, rng=None, anchor: str = ANCHOR_CENTER):
        self._rng = rng if rng is not None else random
        self._anchor = validate_range_anchor(anchor)

    @property
    def rng(self):
        """RNG locale della strategia (random.Random o modulo random)."""
        return self._rng

    @property
    def anchor(self) -> str:
        """Ancora del range: ANCHOR_CENTER o ANCHOR_MIN."""
        return self._anchor

    def _band(self, center: float, spread: float) -> Tuple[float, float]:
        """Banda [lo, hi] effettiva per (center, spread) sotto l'ancora attiva.

        E' la fonte di verita' condivisa da sample() e get_bounds(): una sola
        definizione della banda, nessuna possibilita' che le due divergano.
        """
        if self._anchor == ANCHOR_MIN:
            return (center, center + spread)
        half_spread = spread / 2
        return (center - half_spread, center + half_spread)

    @abstractmethod
    def sample(self, center: float, spread: float) -> float:        # pragma: no cover
        """
        Genera un campione dalla distribuzione.
        
        Args:
            center: Valore centrale (media o punto di riferimento)
            spread: Ampiezza della distribuzione (range o deviazione standard)
        
        Returns:
            Valore generato secondo la distribuzione
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:        # pragma: no cover
        """Nome descrittivo della distribuzione."""
        pass
    
    @abstractmethod
    def get_bounds(self, center: float, spread: float) -> Tuple[float, float]:         # pragma: no cover
        """
        Restituisce i bounds teorici della distribuzione.
        
        Utile per documentazione e debugging.
        
        Returns:
            (min_theoretical, max_theoretical)
        """
        pass 


class UniformDistribution(DistributionStrategy):
    """
    Distribuzione uniforme: tutti i valori nel range sono equiprobabili.
    
    Comportamento:
    - spread definisce la larghezza della banda
    - ancora `center`: output in [center - spread/2, center + spread/2]
    - ancora `min`:    output in [center, center + spread]

    Uso tipico: comportamento attuale del sistema.
    """

    def sample(self, center: float, spread: float) -> float:
        """
        Genera valore uniformemente distribuito nella banda.

        Ancora `center`: center + rng.uniform(-0.5, 0.5) * spread
        Ancora `min`:    center + rng.uniform(0.0, 1.0) * spread

        Il ramo `center` e' volutamente scritto come espressione letterale
        invariata (non derivata da _band): e' il default storico e deve
        restare identico bit per bit.
        """
        if spread <= 0:
            return center

        if self._anchor == ANCHOR_MIN:
            return center + self._rng.uniform(0.0, 1.0) * spread

        return center + self._rng.uniform(-0.5, 0.5) * spread

    @property
    def name(self) -> str:
        return "uniform"

    def get_bounds(self, center: float, spread: float) -> Tuple[float, float]:
        """Bounds della banda, secondo l'ancora attiva."""
        return self._band(center, spread)


class GaussianDistribution(DistributionStrategy):
    """
    Distribuzione gaussiana troncata: campana dentro una banda chiusa.

    Comportamento:
    - spread = LARGHEZZA della banda (non σ)
    - σ = spread / 6, cioè i bordi della banda cadono a 3σ dalla media
    - μ = centro della banda, che dipende dall'ancora:
        `center` -> banda [center - spread/2, center + spread/2], μ = center
        `min`    -> banda [center, center + spread],              μ = center + spread/2
    - la coda oltre 3σ (~0.3%) viene clampata ai bordi, non lasciata uscire

    Uso tipico: texture "smooth", nuvole sonore, variazioni naturali — dove
    si vuole una banda dichiarata, con i valori addensati al centro invece che
    distribuiti piatti.

    Nota storica: fino alla v5.2.0 `spread` era σ e la campana era illimitata,
    richiusa solo dal clamp ai bounds del parametro in Parameter._clamp(). Con
    `range: 200` su `base: 300` i valori arrivavano grosso modo a 0..600 invece
    che a 200..400. La semantica e' stata cambiata perche' `range` doveva
    significare la stessa cosa in tutte le distribuzioni: la larghezza della
    banda. È un cambio di comportamento voluto, non retrocompatibile.
    """

    #: Rapporto larghezza/σ: i bordi della banda cadono a 3σ dalla media.
    SIGMA_DIVISOR = 6.0

    def sample(self, center: float, spread: float) -> float:
        """
        Genera valore gaussiano dentro la banda, con clamp ai bordi.

        Formula: clamp(rng.gauss(μ=centro_banda, σ=spread/6), lo, hi)
        """
        if spread <= 0:
            return center

        lo, hi = self._band(center, spread)
        mu = (lo + hi) / 2.0
        sigma = spread / self.SIGMA_DIVISOR

        return min(max(self._rng.gauss(mu, sigma), lo), hi)

    @property
    def name(self) -> str:
        return "gaussian"

    def get_bounds(self, center: float, spread: float) -> Tuple[float, float]:
        """Bounds della banda, secondo l'ancora attiva.

        Sono bounds esatti, non piu' la stima 3σ: la distribuzione e' troncata,
        quindi nessun campione cade fuori da qui.
        """
        return self._band(center, spread)


class DistributionFactory:
    """
    Factory per creare istanze di DistributionStrategy.
    
    Registry pattern: mappa stringhe a classi.
    """
    
    _registry = {
        'uniform': UniformDistribution,
        'gaussian': GaussianDistribution,
    }
    
    @classmethod
    def create(cls, mode: str, rng=None, anchor: str = ANCHOR_CENTER) -> DistributionStrategy:
        """
        Crea una strategia di distribuzione.

        Args:
            mode: Nome della distribuzione ('uniform', 'gaussian')
            rng: random.Random locale da iniettare (issue #154);
                 None → modulo random globale (legacy)
            anchor: ancora del range ('center' default, 'min')

        Returns:
            Istanza di DistributionStrategy

        Raises:
            StrategyNotFoundError: Se mode non è riconosciuto
            InvalidFieldValueError: Se anchor non è fra RANGE_ANCHORS
        """
        if mode not in cls._registry:
            raise StrategyNotFoundError(
                strategy_kind="distribution",
                name=mode,
                available=list(cls._registry.keys()),
            )

        strategy_class = cls._registry[mode]
        return strategy_class(rng=rng, anchor=validate_range_anchor(anchor))

    @classmethod
    def modes(cls) -> list:
        """Nomi delle distribuzioni registrate.

        Punto di lettura per i consumer esterni (PGE-ls legge di qui l'enum di
        `distribution_mode`) invece di ispezionare `_registry`.
        """
        return list(cls._registry.keys())

    @classmethod
    def register(cls, name: str, strategy_class: type):
        """
        Registra una nuova distribuzione (estensibilità futura).

        Nota: la classe deve accettare il kwarg `rng` nel costruttore
        (basta non ridefinire __init__ ed ereditare da DistributionStrategy).

        Esempio:
            DistributionFactory.register('triangular', TriangularDistribution)
        """
        if not (isinstance(strategy_class, type) and issubclass(strategy_class, DistributionStrategy)):
            raise InvalidStrategyConfigError(
                strategy_kind="distribution",
                field="strategy_class",
                value=strategy_class,
                hint="deve essere subclass di DistributionStrategy",
            )
        cls._registry[name] = strategy_class
