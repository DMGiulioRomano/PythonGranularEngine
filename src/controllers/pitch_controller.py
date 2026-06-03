# src/pitch_controller.py
"""
PitchController - Gestione pitch/trasposizione per sintesi granulare

Modello unit-driven: il blocco pitch è espresso da UN'unica chiave-unità tra
{semitones, cents, quarter_tone, eighth_tone, edo, ratio}. L'unità (PitchUnit)
è la singola fonte di verità: conversione a ratio, bounds di sicurezza e
modalità di variazione. Nessun gruppo esclusivo, nessuna strategy per-preset.

Fornisce un unico metodo `calculate(t)` che restituisce sempre un ratio.
Ispirato al DMX-1000 di Barry Truax (1988).
"""

from parameters.parameter_orchestrator import ParameterOrchestrator
from parameters.pitch_unit import make_pitch_unit, PITCH_UNIT_PRESETS
from strategies.strategie import UnitPitchStrategy
from shared.exceptions import InvalidFieldValueError
from core.stream_config import StreamConfig

# Chiavi-unità riconosciute nel blocco pitch. `edo` è parametrico
# ({divisions, value}); gli altri sono preset nominali.
PITCH_UNIT_KEYS = frozenset(PITCH_UNIT_PRESETS) | {'edo'}


class PitchController:
    """
    Gestisce la trasposizione del pitch per i grani.

    Responsabilità:
    1. Selezionare l'unità di misura dal blocco pitch.
    2. Costruire il Parameter con i bounds dell'unità (+ range/dephase).
    3. Fornire `calculate(t)` che restituisce sempre un ratio.
    """

    def __init__(
        self,
        params: dict,                # 1. Dati specifici (blocco pitch YAML)
        config: StreamConfig         # 2. Regole processo
    ):
        self._orchestrator = ParameterOrchestrator(config=config)
        self._config = config

        unit, value_raw = self._select_unit(params)
        self._active_param = self._orchestrator.create_pitch_parameter(
            name=f'pitch_{unit.name}',
            value_raw=value_raw,
            range_raw=params.get('range'),
            bounds=unit.value_bounds(),
            dephase_key='pitch',
        )
        self._strategy = UnitPitchStrategy(self._active_param, unit, unit.name)

    # =========================================================================
    # SELEZIONE UNITÀ
    # =========================================================================

    def _select_unit(self, params: dict):
        """
        Individua l'unità dal blocco pitch e il valore grezzo associato.

        - 0 chiavi-unità → default semitoni, valore neutro (ratio 1.0).
        - 1 chiave → quell'unità (edo: valore annidato, altri: valore diretto).
        - >1 chiavi → InvalidFieldValueError (ambiguità esplicita).
        """
        present = [k for k in params if k in PITCH_UNIT_KEYS]
        if len(present) > 1:
            raise InvalidFieldValueError(
                field='pitch',
                value=present,
                hint=(
                    "una sola unità per blocco pitch; trovate: "
                    f"{present}. Unità disponibili: {sorted(PITCH_UNIT_KEYS)}."
                ),
            )
        if not present:
            unit = make_pitch_unit('semitones')
            return unit, unit.identity_value()

        key = present[0]
        if key == 'edo':
            return self._build_edo(params['edo'])
        return make_pitch_unit(key), params[key]

    def _build_edo(self, edo_spec):
        """pitch: {edo: {divisions: N, value: X}} — divisione EDO arbitraria."""
        if (not isinstance(edo_spec, dict)
                or 'divisions' not in edo_spec
                or 'value' not in edo_spec):
            raise InvalidFieldValueError(
                field='pitch.edo',
                value=edo_spec,
                hint="forma attesa: edo: {divisions: N, value: X}.",
            )
        unit = make_pitch_unit({'edo': edo_spec['divisions']})  # valida divisions > 0
        return unit, edo_spec['value']

    # =========================================================================
    # CALCOLO
    # =========================================================================

    def calculate(
        self,
        elapsed_time: float,
        grain_reverse: bool = False
    ) -> float:
        """
        Calcola il pitch ratio finale con compensazione reverse.

        Args:
            elapsed_time: tempo corrente nello stream
            grain_reverse: se True, nega il pitch per lettura backward

        Returns:
            float: pitch ratio finale (può essere negativo se reverse)
        """
        pitch_ratio = self._strategy.calculate(elapsed_time)
        # Compensazione fisica per reverse: il phasor legge backward via freq negativa
        if grain_reverse:
            pitch_ratio *= -1
        return pitch_ratio

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def mode(self) -> str:
        return self._strategy.name

    @property
    def base_ratio(self):
        """Valore base se l'unità è ratio, altrimenti None (per ScoreVisualizer)."""
        return self._active_param.value if self.mode == 'ratio' else None

    @property
    def base_semitones(self):
        """Valore base se l'unità è semitoni, altrimenti None (per ScoreVisualizer)."""
        return self._active_param.value if self.mode == 'semitones' else None

    @property
    def range(self):
        """Espone il range del parametro attivo (0.0 se assente)."""
        param = self._active_param
        if hasattr(param, '_mod_range') and param._mod_range is not None:
            return param._mod_range
        return 0.0

    # =========================================================================
    # REPR
    # =========================================================================

    def __repr__(self) -> str:
        return f"PitchController(mode={self.mode}, strategy={self._strategy.name})"
