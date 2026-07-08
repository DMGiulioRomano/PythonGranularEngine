"""

parameter_orchestrator.py - Coordina ParameterFactory e GateFactory.
Isola completamente la logica di dephase dal parsing dei parametri.
"""
from __future__ import annotations

from typing import Dict, Optional
from pge.parameters.parameter_factory import ParameterFactory
from pge.parameters.gate_factory import GateFactory
from pge.shared.probability_gate import ProbabilityGate
from pge.parameters.parameter import Parameter
from pge.parameters.parameter_schema import ParameterSpec
from pge.parameters.parameter_definitions import DEFAULT_PROB
from pge.parameters.exclusive_selector import ExclusiveGroupSelector
from pge.core.stream_config import StreamConfig
from pge.shared.seeding import component_rng

class ParameterOrchestrator:
    """
    Orchestratore: collega ParameterFactory e GateFactory senza accoppiarle.
    """
    
    def __init__(
        self,
        config: StreamConfig = None
    ):
        self._param_factory = ParameterFactory(config)
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
                result[spec_name] = self._param_factory.create_raw_parameter(spec, yaml_data)

        # I perdenti dei gruppi esclusivi vanno a None.
        # Garantisce che l'output abbia sempre forma completa:
        # il consumer non deve mai chiedersi quali attributi esistono.
        for group_specs in group_members.values():
            for spec in group_specs:
                if spec.name not in result:
                    result[spec.name] = None

        return result

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
        param = self._param_factory.create_smart_parameter(param_spec, yaml_data)

        # Controlla se range è esplicitato
        has_explicit_range = param.has_explicit_range

        # 2. Crea il ProbabilityGate corrispondente, con RNG per-componente
        # (issue #154): i draw del gate non shiftano gli altri componenti.
        gate = GateFactory.create_gate(
            dephase=self._config.dephase,
            param_key=param_spec.dephase_key,
            default_prob=DEFAULT_PROB,
            has_explicit_range=has_explicit_range,
            range_always_active=self._config.range_always_active,
            duration=self._config.context.duration,
            time_mode=self._config.time_mode,
            rng=self._gate_rng(param_spec.dephase_key),
        )
        # 3. Inietta il gate nel Parameter (modifica la classe Parameter)
        param.set_probability_gate(gate)

        return param

    def _gate_rng(self, dephase_key: Optional[str]):
        """RNG locale del gate, derivato da (seed, stream_id, gate:<key>)."""
        return component_rng(
            getattr(self._config, 'seed', None),
            self._config.context.stream_id,
            f"gate:{dephase_key}",
        )
    
    def create_pitch_parameter(
        self,
        name: str,
        value_raw,
        range_raw,
        bounds,
        dephase_key: str = 'pitch',
    ) -> Parameter:
        """
        Crea il Parameter del pitch con bounds dall'unità + ProbabilityGate.

        Il pitch è unit-driven: i bounds derivano dalla PitchUnit, non dallo
        schema. Replica la pipeline di create_parameter_with_gate (range +
        dephase) ma con bounds espliciti.
        """
        param = self._param_factory.create_smart_parameter_with_bounds(
            name=name,
            value_raw=value_raw,
            range_raw=range_raw,
            bounds=bounds,
        )
        gate = GateFactory.create_gate(
            dephase=self._config.dephase,
            param_key=dephase_key,
            default_prob=DEFAULT_PROB,
            has_explicit_range=param.has_explicit_range,
            range_always_active=self._config.range_always_active,
            duration=self._config.context.duration,
            time_mode=self._config.time_mode,
            rng=self._gate_rng(dephase_key),
        )
        param.set_probability_gate(gate)
        return param

    def create_constant_parameter(self, name: str, value: float) -> Parameter:
        """
        Thin wrapper su ParameterFactory.create_constant_parameter.

        Il controller parla solo con l'orchestrator, mai con la factory diretta.
        """
        return self._param_factory.create_constant_parameter(name, value)
