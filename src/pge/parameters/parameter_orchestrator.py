"""

parameter_orchestrator.py - Coordina GranularParser e GateFactory.
Isola completamente la logica di deviation_probability dal parsing dei parametri.

Divisione del lavoro:
- parameter_schema.py: sa DOVE stanno i dati nel YAML (ParameterSpec + il
  risolutore della dot notation)
- parameter_definitions.py: sa QUALI SONO i limiti (bounds)
- parser.py: sa COME si costruisce un Parameter
- qui: legge lo spec, estrae il valore, chiede il Parameter al parser e ci
  inietta il ProbabilityGate
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from pge.parameters.gate_factory import GateFactory
from pge.parameters.parser import GranularParser
from pge.shared.probability_gate import ProbabilityGate
from pge.parameters.parameter import Parameter
from pge.parameters.parameter_schema import ParameterSpec, resolve_yaml_path
from pge.parameters.parameter_definitions import (
    DEFAULT_PROB,
    RANGE_UNIT_DEFAULT,
    range_unit_is_relative,
    validate_range_unit,
)
from pge.parameters.exclusive_selector import ExclusiveGroupSelector
from pge.core.stream_config import StreamConfig
from pge.shared.exceptions import ConfigError, MissingFieldError
from pge.shared.seeding import component_rng

#: Sentinella per "la chiave non c'e'", distinta da una chiave scritta e
#: lasciata vuota (`duration_range_unit:` -> None nello YAML). Serve perche'
#: `resolve_yaml_path` restituisce il default in entrambi i casi, e i due casi
#: non vogliono dire la stessa cosa: assente e' nessuna richiesta, vuota e' una
#: riga che qualcuno ha scritto e che nessuno legge. Vedi
#: `_range_unit_from_spec`.
_KEY_ABSENT = object()


class ParameterOrchestrator:
    """
    Orchestratore: collega GranularParser e GateFactory senza accoppiarli.
    """

    def __init__(self, config: StreamConfig):
        self._parser = GranularParser(config)
        self._config = config


    def create_all_parameters(
        self,
        yaml_data: dict,
        schema: list
    ) -> Dict[str, Parameter]:
        # Seleziona parametri attivi
        selected_specs, group_members = ExclusiveGroupSelector.select_parameters(
            schema, yaml_data
        )

        result = {}
        for spec_name, spec in selected_specs.items():
            if spec.is_smart:
                param = self.create_parameter_with_gate(yaml_data, spec)
                result[spec_name] = param
            else:
                result[spec_name] = self._raw_value(spec, yaml_data)

        # I perdenti dei gruppi esclusivi vanno a None.
        # Garantisce che l'output abbia sempre forma completa:
        # il consumer non deve mai chiedersi quali attributi esistono.
        for group_specs in group_members.values():
            for spec in group_specs:
                if spec.name not in result:
                    result[spec.name] = None

        return result

    def _raw_value(self, spec: ParameterSpec, yaml_data: dict) -> Any:
        """
        Estrae un valore grezzo (non Parameter) dal YAML.

        Usato per gli spec con is_smart=False, come 'grain_envelope', che sono
        stringhe e non vanno parsate in Parameter.
        """
        return resolve_yaml_path(yaml_data, spec.yaml_path, spec.default)

    def _parameter_from_spec(
        self,
        spec: ParameterSpec,
        yaml_data: dict
    ) -> Parameter:
        """
        Legge valore e range dello spec dal YAML e ne fa un Parameter.

        L'unico punto in cui lo schema (DOVE stanno i dati) incontra il parser
        (COME si costruisce un Parameter).
        """
        value = resolve_yaml_path(yaml_data, spec.yaml_path, spec.default)

        range_val = None
        if spec.range_path:
            range_val = resolve_yaml_path(yaml_data, spec.range_path, None)

        return self._parser.parse_parameter(
            name=spec.name,  # Stessa chiave per bounds e attributo
            value_raw=value,
            range_raw=range_val,
            range_unit=self._range_unit_from_spec(spec, yaml_data, range_val),
        )

    def _range_unit_from_spec(
        self,
        spec: ParameterSpec,
        yaml_data: dict,
        range_val: Any,
    ) -> str:
        """L'unita' del `_range` dichiarata nello YAML (issue #267).

        Qui e non nel parser perche' qui si conoscono i due path YAML: quello
        dell'unita', per nominare la chiave in un errore di vocabolario, e
        quello del range, per nominare la chiave che manca. Il parser conosce
        solo il nome del parametro (`grain_duration`), che non e' come si
        scrive nel file.

        Un `relative` senza il range che governa e' un errore, non una chiave
        inerte: senza range dichiarato scatta il jitter implicito, che e'
        assoluto — cioe' esattamente cio' che l'utente stava cercando di
        evitare. Stessa regola di `grain.duration_unit`, che pretende una
        `grain.duration` esplicita per non lasciare base e range in due domini
        diversi.

        Per la stessa ragione la chiave **assente** e la chiave **vuota** non
        prendono la stessa strada. Assente vuol dire che nessuno ha chiesto
        niente, e il default assoluto e' la risposta giusta. Vuota
        (`duration_range_unit:`, cioe' `None`) vuol dire che qualcuno l'ha
        scritta: leggerla come `absolute` sarebbe il default piu' muto
        possibile — nel file non resta niente da cui accorgersi che la riga non
        e' stata letta. La gemella `grain.duration_unit` una grafia vuota la
        rifiuta gia'; qui la distinzione ha bisogno di una sentinella, perche'
        `resolve_yaml_path` non ha modo di dire assente da nullo.
        """
        if not spec.range_unit_path:
            return RANGE_UNIT_DEFAULT

        raw = resolve_yaml_path(yaml_data, spec.range_unit_path, _KEY_ABSENT)
        if raw is _KEY_ABSENT:
            return RANGE_UNIT_DEFAULT

        try:
            unit = validate_range_unit(raw, field=spec.range_unit_path)
        except ConfigError as err:
            err.stream_id = self._config.context.stream_id
            raise

        if range_unit_is_relative(unit) and range_val is None:
            err = MissingFieldError(
                field=spec.range_path,
                hint=(f"con {spec.range_unit_path}: {unit} la banda va "
                      "dichiarata esplicitamente come frazione del valore "
                      "base (senza, varrebbe il jitter implicito, che e' "
                      "assoluto)."),
            )
            err.stream_id = self._config.context.stream_id
            raise err

        return unit

    def create_parameter_with_gate(
        self,
        yaml_data: dict,
        param_spec: ParameterSpec
    ) -> Parameter:
        """
        Crea un Parameter completo con il suo ProbabilityGate.
        
        Design Pattern: Strategy Injection
        """
        # 1. Crea il Parameter base (SENZA probabilità)
        param = self._parameter_from_spec(param_spec, yaml_data)

        # Controlla se range è esplicitato
        has_explicit_range = param.has_explicit_range

        # 2. Crea il ProbabilityGate corrispondente, con RNG per-componente
        # (issue #154): i draw del gate non shiftano gli altri componenti.
        gate = self._create_gate(
            param_key=param_spec.deviation_probability_key,
            has_explicit_range=has_explicit_range,
        )
        # 3. Inietta il gate nel Parameter (modifica la classe Parameter)
        param.set_probability_gate(gate)

        return param

    def _create_gate(
        self,
        param_key: Optional[str],
        has_explicit_range: bool,
    ) -> ProbabilityGate:
        """Il gate del parametro, attribuito allo stream se non si costruisce.

        `GateFactory` e' isolata per progetto: non conosce lo stream, e infatti
        i suoi errori nominano il campo (`deviation_probability.<chiave>`) e
        basta. L'attribuzione tocca al chiamante, come gia' fa il parser per i
        propri — senza, la riga `Stream:` che `docs/reference/errors.md`
        promette negli esempi non compare.
        """
        try:
            return GateFactory.create_gate(
                deviation_probability=self._config.deviation_probability,
                param_key=param_key,
                default_prob=DEFAULT_PROB,
                has_explicit_range=has_explicit_range,
                range_always_active=self._config.range_always_active,
                duration=self._config.context.duration,
                time_mode=self._config.time_mode,
                rng=self._gate_rng(param_key),
            )
        except ConfigError as err:
            err.stream_id = self._config.context.stream_id
            raise

    def _gate_rng(self, deviation_probability_key: Optional[str]):
        """RNG locale del gate, derivato da (seed, rng_id, gate:<key>) —
        rng_id è stream_id o, se dichiarato, il rng_group (issue #169)."""
        return component_rng(
            getattr(self._config, 'seed', None),
            self._config.context.rng_id,
            f"gate:{deviation_probability_key}",
        )
    
    def create_pitch_parameter(
        self,
        name: str,
        value_raw,
        range_raw,
        bounds,
        deviation_probability_key: str = 'pitch',
    ) -> Parameter:
        """
        Crea il Parameter del pitch con bounds dall'unità + ProbabilityGate.

        Il pitch è unit-driven: i bounds derivano dalla PitchUnit, non dallo
        schema. Replica la pipeline di create_parameter_with_gate (range +
        deviation_probability) ma con bounds espliciti.
        """
        param = self._parser.parse_parameter(
            name=name,
            value_raw=value_raw,
            range_raw=range_raw,
            bounds_override=bounds,
        )
        gate = self._create_gate(
            param_key=deviation_probability_key,
            has_explicit_range=param.has_explicit_range,
        )
        param.set_probability_gate(gate)
        return param

    def create_constant_parameter(self, name: str, value: float) -> Parameter:
        """
        Crea un Parameter costante da un valore scalare, senza YAML.

        Usato per fallback interni (es. loop_end = sample_dur_sec) dove il
        valore e' gia' noto ma serve un Parameter con get_value().
        """
        return self._parser.parse_parameter(
            name=name,
            value_raw=value,
            range_raw=None,
        )
