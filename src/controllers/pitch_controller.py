# src/controllers/pitch_controller.py
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

# Chiavi non-unità ammesse nel blocco pitch (modificatori).
# `value` è il valore della griglia EDO (`edo: N` + `value: X`); per i preset
# il valore sta nella chiave stessa (es. `semitones: 7`).
PITCH_BLOCK_EXTRA_KEYS = frozenset({'range', 'value'})

# Whitelist completa del blocco pitch: unità + modificatori. Chiavi fuori da
# questo insieme sono refusi/errori e vanno segnalate, non ignorate.
PITCH_BLOCK_KEYS = PITCH_UNIT_KEYS | PITCH_BLOCK_EXTRA_KEYS


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
        self._unit = unit
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

        - `pitch:` vuoto (None) o non-mapping (lista, scalare) →
          InvalidFieldValueError: niente silent default a ratio 1.0, niente
          TypeError grezzo. Per nessuna trasposizione si omette il blocco.
        - `pitch: {}` o blocco assente (Stream passa `{}`) → default semitoni
          neutro (ratio 1.0): i due casi sono indistinguibili a valle.
        - chiavi fuori da PITCH_BLOCK_KEYS (refusi, es. `semitone`) →
          InvalidFieldValueError: nessun silent default.
        - 0 chiavi-unità (solo modificatori, es. `range`) → default semitoni.
        - 1 chiave → quell'unità (edo: `value` a fianco; altri: valore diretto).
        - >1 chiavi → InvalidFieldValueError (ambiguità esplicita).
        - `value` è ammesso solo con `edo`: altrove è ambiguo (il valore dei
          preset sta nella chiave) → InvalidFieldValueError.
        """
        if not isinstance(params, dict):
            # `pitch:` vuoto (None) o non-mapping (lista/scalare): blocco
            # presente ma privo di unità. Nessun silent default, nessun
            # TypeError grezzo dall'iterazione sottostante. Il blocco assente
            # arriva invece come `{}` (default di Stream) → ramo key=None sotto.
            raise InvalidFieldValueError(
                field='pitch',
                value=params,
                hint=(
                    "il blocco pitch deve specificare un'unità "
                    "(es. semitones: 7, ratio: 1.5, oppure edo: 31 + value: 18). "
                    "Per nessuna trasposizione, ometti del tutto il blocco pitch."
                ),
            )

        unknown = [k for k in params if k not in PITCH_BLOCK_KEYS]
        if unknown:
            raise InvalidFieldValueError(
                field='pitch',
                value=unknown,
                hint=(
                    "chiavi sconosciute nel blocco pitch: "
                    f"{unknown}. Chiavi valide: {sorted(PITCH_BLOCK_KEYS)}."
                ),
            )

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

        key = present[0] if present else None
        if 'value' in params and key != 'edo':
            raise InvalidFieldValueError(
                field='pitch.value',
                value=params.get('value'),
                hint=(
                    "`value` è ammesso solo con `edo: N`; per i preset il valore "
                    "sta nella chiave (es. semitones: 7)."
                ),
            )
        if key is None:
            unit = make_pitch_unit('semitones')
            return unit, unit.identity_value()
        if key == 'edo':
            return self._build_edo(params)
        return make_pitch_unit(key), params[key]

    def _build_edo(self, params):
        """pitch: {edo: N, value: X} — N divisioni per ottava, valore a fianco."""
        divisions = params['edo']
        if isinstance(divisions, dict):  # vecchia forma annidata: hard break
            raise InvalidFieldValueError(
                field='pitch.edo',
                value=divisions,
                hint=(
                    "forma edo cambiata: ora `edo: N` con `value: X` a fianco "
                    "(es. edo: 31, value: 18). La forma annidata "
                    "{divisions, value} non è più valida."
                ),
            )
        if 'value' not in params:
            raise InvalidFieldValueError(
                field='pitch.edo',
                value=params,
                hint="con `edo: N` serve `value: X` a fianco (es. edo: 31, value: 18).",
            )
        unit = make_pitch_unit({'edo': divisions})  # valida divisions int > 0
        return unit, params['value']

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
    def unit(self):
        """L'unità di misura attiva (PitchUnit): per visualizzazione e label."""
        return self._unit

    @property
    def value(self):
        """Valore base del pitch (Envelope o scalare) nell'unità attiva."""
        return self._active_param.value

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
