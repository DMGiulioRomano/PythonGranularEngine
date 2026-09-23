# =============================================================================
# src/pge/strategies/registry.py
# =============================================================================
"""
La mappa nome -> classe strategy, una volta sola (issue #184, forma decisa
in #177).

Lo stesso schema — un dizionario di modulo, un punto di registrazione, una
`Factory` il cui `create()` fa lookup e alza `StrategyNotFoundError` — era
ripetuto in nove moduli, e le copie stavano divergendo: tre parole per il
primo parametro della registrazione, due per il secondo, tre etichette di
dominio scritte a mano sulla riga diagnostica, un `create()` che chiamava la
chiave `strategy_name` e uno che la chiamava `name`.

`StrategyRegistry` **e'** la mappa — eredita da `dict` — perche' il dizionario
deve restare raggiungibile e mutabile sotto il proprio nome di modulo: le
fixture dei test ne fanno snapshot e ripristino con `dict()`/`clear()`/
`update()`, e la parita' di PGE-ls ne legge le chiavi importandolo per nome.
Una composizione avrebbe lasciato il dizionario fuori comunque, separato dalle
funzioni che lo governano: la duplicazione di oggi spostata di due righe.

Il dominio arriva alla costruzione, non a ogni chiamata: non e' un dato del
chiamante, e' una proprieta' del registry. Lo stesso `kind` va sia nello
`strategy_kind` di `StrategyNotFoundError` sia nella riga diagnostica, che e'
cio' che uniforma le etichette scritte a mano.

Il razionale completo, con i vincoli che hanno scelto ogni pezzo, sta in
`docs/explanation/strategy-registry.md`.
"""
from __future__ import annotations

from typing import Dict, Type, TypeVar

from pge.shared.exceptions import StrategyNotFoundError
from pge.shared.logger import log_strategy_registration

S = TypeVar('S')


class StrategyRegistry(Dict[str, Type[S]]):
    """Mappa nome -> classe strategy che conosce il proprio dominio."""

    def __init__(
        self,
        kind: str,
        base: Type[S],
        initial: Dict[str, Type[S]] | None = None,
    ):
        """
        Args:
            kind: dominio del registry ('voice_pan', 'density', ...). E' la
                  stessa stringa che compare nello `strategy_kind` degli
                  errori e nella riga diagnostica della registrazione.
            base: ABC del dominio. E' portata, non imposta: il registry NON
                  verifica `issubclass` alla registrazione, perche' per i
                  registry che convergono su questa forma sarebbe un rifiuto
                  nuovo — cioe' un cambio di superficie pubblica, che vuole
                  una issue sua.
            initial: contenuto iniziale della mappa.
        """
        super().__init__(initial or {})
        self.kind = kind
        self.base = base

    def register(self, name: str, strategy_class: Type[S]) -> None:
        """
        Registra una strategy e lo annuncia al logger diagnostico.

        Il dominio della riga e' il `kind` del registry, non un letterale
        scritto accanto alla chiamata: e' cosi' che le etichette scritte a
        mano smettono di divergere.

        `registry[name] = strategy_class` resta una registrazione legale e
        muta — e' quel che fanno le fixture per rimettere a posto lo stato —
        ma la riga appartiene a questo punto d'ingresso esplicito.

        La firma e' quella dei `register_*` di modulo che delegano qui
        (issue #185): `(name, strategy_class)`. Il secondo parametro si
        chiamava `cls`, cioe' proprio il nome da cui pitch, onset e pointer
        sono stati convertiti — misurata sulle sole facade, la convergenza
        lasciava quel nome vivo nell'unico punto che le serve tutte e sei, e
        per il censimento di `tests/shared/test_stdout_contract.py` questo e'
        un punto di registrazione come loro. Nessuna chiamata viva lo passa
        per parola chiave.
        """
        self[name] = strategy_class
        log_strategy_registration(self.kind, name, strategy_class)

    def create(self, name: str, *args, **kwargs) -> S:
        """
        Costruisce la strategy registrata sotto `name`.

        Gli argomenti non vengono ispezionati: arrivano al costruttore cosi'
        come sono. I posizionali non sono un lusso — le due strategy di
        density si costruiscono con `(param, distribution_param)` e chiamano
        quel primo parametro con due nomi diversi, quindi per parola chiave
        non si passano affatto.

        Args:
            name: chiave del registry.
            *args, **kwargs: inoltrati tali e quali al costruttore.

        Raises:
            StrategyNotFoundError: se `name` non e' registrato, con il
                dominio del registry e l'elenco delle chiavi disponibili.
        """
        if name not in self:
            raise StrategyNotFoundError(
                strategy_kind=self.kind,
                name=name,
                available=list(self.keys()),
            )
        return self[name](*args, **kwargs)
