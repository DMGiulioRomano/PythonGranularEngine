# src/stream.py
"""
Stream - Orchestratore per la sintesi granulare.

Fase 6 del refactoring: questa classe coordina i controller specializzati:
- ParameterEvaluator: parsing e validazione parametri
- PointerController: posizionamento testina con loop e jitter
- PitchController: trasposizione (semitoni o ratio)
- DensityController: densità e distribuzione temporale
- VoiceManager: voci multiple con offset pitch/pointer

Mantiene backward compatibility con Generator e ScoreVisualizer.
Ispirato al DMX-1000 di Barry Truax (1988).
"""
import random
from typing import List, Optional, Union

from core.grain import Grain
from envelopes.envelope import Envelope
from controllers.window_controller import WindowController
from controllers.pointer_controller import PointerController
from controllers.pitch_controller import PitchController
from controllers.density_controller import DensityController
from shared.utils import get_sample_duration
from parameters.parameter_schema import STREAM_PARAMETER_SCHEMA
from parameters.parameter_orchestrator import ParameterOrchestrator
from core.stream_config import StreamConfig, StreamContext
from controllers.voice_manager import VoiceManager, VoiceConfig
from strategies.voice_pitch_strategy import VoicePitchStrategyFactory
from strategies.voice_onset_strategy import VoiceOnsetStrategyFactory
from strategies.voice_pointer_strategy import VoicePointerStrategyFactory
from strategies.voice_pan_strategy import VoicePanStrategyFactory
from dataclasses import fields


class Stream:
    """
    Orchestratore per uno stream di sintesi granulare.
    
    Coordina i controller specializzati e genera la lista di grani.
    Mantiene compatibilità con Generator e ScoreVisualizer.
    
    Attributes:
        voices: List[List[Grain]] - grani organizzati per voce
        grains: List[Grain] - lista flattened (backward compatibility)
    """
    
    def __init__(self, params: dict):
        """
        Inizializza lo stream dai parametri YAML.
        
        Args:
            params: dizionario parametri dallo YAML
        """
        # === 3. CONFIGURATION ===
        config = StreamConfig.from_yaml(params,StreamContext.from_yaml(params, sample_dur_sec=get_sample_duration(params['sample'])))
        self._init_stream_context(params)
        # === 4. PARAMETRI SPECIALI ===
        self._init_grain_reverse(params)
        # === 5. PARAMETRI DIRETTI (riceve config) ===
        self._init_stream_parameters(params, config)
        # === 6. CONTROLLER (riceve config) ===
        self._init_controllers(params, config)
        # === 7. VOICE MANAGER ===
        self._init_voice_manager(params, config)
        # === 8. RIFERIMENTI CSOUND (assegnati da Generator) ===
        self.sample_table_num: Optional[int] = None
        self.envelope_table_num: Optional[int] = None
        # === 9. STATO ===
        self.voices: List[List[Grain]] = []
        self.grains: List[Grain] = []  # backward compatibility
        self.generated = False

    def _init_stream_context(self, params):
        base = {field.name for field in fields(StreamContext) if field.name != 'sample_dur_sec'}
        missing = base - set(params.keys())
        if missing:
            missing_list = sorted(missing)
            if len(missing_list) == 1:
                raise ValueError(f"Parametro obbligatorio mancante: '{missing_list[0]}'")
            else:
                missing_str = ", ".join(f"'{m}'" for m in missing_list)
                raise ValueError(f"Parametri obbligatori mancanti: {missing_str}")
        for key in base:
            setattr(self, key, params[key])
        self.sample_dur_sec = get_sample_duration(self.sample)

    def _init_stream_parameters(self, params: dict, config: StreamConfig) -> None:
        """
        Inizializza parametri diretti di Stream usando ParameterFactory.
        
        Design Pattern: Data-Driven Configuration
        - Lo schema STREAM_PARAMETER_SCHEMA definisce COSA caricare
        - ParameterFactory sa COME crearlo
        - Stream riceve i Parameter già pronti        
        """
        _orchestrator = ParameterOrchestrator(config=config)

        # 3. Crea tutti i parametri
        parameters = _orchestrator.create_all_parameters(
            params,
            schema=STREAM_PARAMETER_SCHEMA
        )
        
        # 4. Assegna come attributi
        for name, param in parameters.items():
            setattr(self, name, param)

    # =========================================================================
    # INIZIALIZZAZIONE CONTROLLER
    # =========================================================================
    
    def _init_controllers(self, params: dict, config: StreamConfig) -> None:
        """Inizializza tutti i controller con i loro parametri."""
        # POINTER CONTROLLER
        self._pointer = PointerController(
            params=params.get('pointer', {}),
            config=config
        )
        
        # PITCH CONTROLLER
        self._pitch = PitchController(
            params=params.get('pitch', {}),
            config=config
            )
        
        # DENSITY CONTROLLER
        self._density = DensityController(
            params=params,
            config=config
        )

        self._window_controller = WindowController(
            params=params.get('grain', {}),
            config=config
        )    
            
    def _init_voice_manager(self, params: dict, config: StreamConfig) -> None:
        """
        Costruisce VoiceManager dal blocco YAML 'voices:'.

        YAML supportato:
            voices:
              num_voices: 4
              pitch:
                strategy: chord
                chord: "dom7"
              onset_offset:
                strategy: linear
                step: 0.05
              pointer:
                strategy: stochastic
                pointer_range: 0.1
              pan:
                strategy: linear
                spread: 60.0

        - voices assente → VoiceManager(max_voices=1)
        - strategy stochastiche: stream_id iniettato automaticamente
        - spread estratto dal blocco pan
        """
        from parameters.parameter import Parameter
        from parameters.parameter_definitions import GRANULAR_PARAMETERS

        v = params.get('voices', {})
        if not v:
            # Senza blocco voices, valori di default (nessun config necessario)
            self._num_voices = Parameter('num_voices', 1.0, GRANULAR_PARAMETERS['num_voices'])
            self._scatter = Parameter('scatter', 0.0, GRANULAR_PARAMETERS['scatter'])
            self._voice_manager = VoiceManager(max_voices=1)
            return

        from parameters.parser import GranularParser
        parser = GranularParser(config)

        raw_num_voices = v.get('num_voices', 1)

        # Estrae max_voices per pre-computare tutti i VoiceConfig all'init.
        # Se num_voices è un Envelope, max_voices = picco dei breakpoints.
        if isinstance(raw_num_voices, list):
            max_voices = int(max(bp[1] for bp in raw_num_voices))
        else:
            max_voices = int(raw_num_voices)

        # Parsa num_voices e scatter come Parameter (supportano Envelope time-varying).
        self._num_voices = parser.parse_parameter('num_voices', raw_num_voices)
        self._scatter = parser.parse_parameter('scatter', v.get('scatter', 0.0))

        # --- PITCH ---
        pitch_strategy = None
        if 'pitch' in v:
            kw = dict(v['pitch'])
            name = kw.pop('strategy')
            if name == 'stochastic':
                kw['stream_id'] = self.stream_id
            pitch_strategy = VoicePitchStrategyFactory.create(name, **kw)

        # --- ONSET ---
        onset_strategy = None
        if 'onset_offset' in v:
            kw = dict(v['onset_offset'])
            name = kw.pop('strategy')
            if name == 'stochastic':
                kw['stream_id'] = self.stream_id
            onset_strategy = VoiceOnsetStrategyFactory.create(name, **kw)

        # --- POINTER ---
        pointer_strategy = None
        if 'pointer' in v:
            kw = dict(v['pointer'])
            name = kw.pop('strategy')
            if name == 'stochastic':
                kw['stream_id'] = self.stream_id
            pointer_strategy = VoicePointerStrategyFactory.create(name, **kw)

        # --- PAN ---
        pan_strategy = None
        pan_spread = 0.0
        if 'pan' in v:
            kw = dict(v['pan'])
            name = kw.pop('strategy')
            pan_spread = float(kw.pop('spread', 0.0))
            pan_strategy = VoicePanStrategyFactory.create(name)

        self._voice_manager = VoiceManager(
            max_voices=max_voices,
            pitch_strategy=pitch_strategy,
            onset_strategy=onset_strategy,
            pointer_strategy=pointer_strategy,
            pan_strategy=pan_strategy,
            pan_spread=pan_spread,
        )

    def _init_grain_reverse(self, params: dict) -> None:
        """
        Inizializza parametri reverse del grano.
        
        Semantica YAML RISTRETTA:
        - Chiave ASSENTE → 'auto' (segue pointer_speed)
        - Chiave PRESENTE (reverse:) → DEVE essere vuota, significa True (forzato reverse)
        - reverse: true/false/auto → ERRORE! Non accettati
        
        Examples YAML validi:
            grain:
            # reverse assente → auto mode
            
            grain:
                reverse:  # ← Unico modo per forzare reverse
        
        Examples YAML INVALIDI:
            grain:
                reverse: true    # x ERRORE
                reverse: false   # x ERRORE
                reverse: 'auto'  # x ERRORE
        """
        grain_params = params.get('grain', {})
        
        if 'reverse' in grain_params:
            # Validazione: se la chiave è presente, DEVE essere None (vuota)
            value = grain_params['reverse']
            if value is not None:
                raise ValueError(
                    f"Stream '{self.stream_id}': grain.reverse deve essere lasciato vuoto.\n"
                    f"  Trovato: reverse: {value}\n"
                    f"  Sintassi corretta:\n"
                    f"    grain:\n"
                    f"      reverse:  # ← senza valore\n"
                    f"  Per seguire pointer_speed, ometti completamente la chiave 'reverse'."
                )
            
            # Chiave presente e vuota → reverse forzato
            self.grain_reverse_mode = True
        else:
            # Chiave assente → auto mode (segue speed)
            self.grain_reverse_mode = 'auto'

    # =========================================================================
    # GENERAZIONE GRANI
    # =========================================================================
    
    def generate_grains(self) -> List[List[Grain]]:
        """
        Genera grani per tutte le voci.

        Per ogni tick temporale, genera un grano per ogni voce attiva.
        La densità complessiva è density × num_voices (ogni voce ha il
        proprio loop temporale indipendente con lo stesso inter-onset).

        Returns:
            List[List[Grain]]: grani organizzati per voce (voce 0 = riferimento)
        """
        max_v = self._voice_manager.max_voices

        # Struttura per raccogliere grani per voce (pre-allocata per max_voices)
        all_voice_grains: List[List[Grain]] = [[] for _ in range(max_v)]

        # Cursore temporale indipendente per ogni voce.
        # Con scatter=0 tutti avanzano dello stesso sync_iot → comportamento identico
        # a prima. Con scatter>0 e distribution>0 i cursori divergono nel tempo.
        voice_cursors = [0.0] * max_v

        while any(c < self.duration for c in voice_cursors):
            # Voice 0 è il riferimento: definisce sync_iot e il valore di scatter
            t0 = voice_cursors[0]
            grain_dur_0 = self.grain_duration.get_value(t0)
            sync_iot = self._density.calculate_inter_onset(t0, grain_dur_0)
            scatter_val = self._scatter.get_value(t0)

            for voice_index in range(max_v):
                t = voice_cursors[voice_index]

                if t >= self.duration:
                    continue

                # Voice 0 condivide già grain_dur_0 (t == t0), evita doppia chiamata
                grain_dur = grain_dur_0 if voice_index == 0 else self.grain_duration.get_value(t)
                active = max(1, min(max_v, int(self.num_voices.get_value(t))))

                if voice_index < active:
                    voice_config = self._voice_manager.get_voice_config(voice_index)
                    grain = self._create_grain(t, grain_dur, voice_config)
                    all_voice_grains[voice_index].append(grain)

                # IOT di questa voce: blend tra sync_iot (condiviso) e indep_iot
                if voice_index == 0 or scatter_val == 0.0:
                    iot = sync_iot
                else:
                    indep_iot = self._density.calculate_inter_onset(t, grain_dur)
                    iot = (1.0 - scatter_val) * sync_iot + scatter_val * indep_iot

                voice_cursors[voice_index] += iot

        self.voices = all_voice_grains
        # Flatten e sort per onset (backward compatibility)
        all_grains = [g for voice in self.voices for g in voice]
        all_grains.sort(key=lambda g: g.onset)
        self.grains = all_grains
        self.generated = True

        return self.voices
    
    def _create_grain(self,
                      elapsed_time: float,
                      grain_dur: float,
                      voice_config: Optional['VoiceConfig'] = None) -> Grain:
        """
        Crea un singolo grano con tutti i parametri calcolati.

        Applica gli offset di VoiceConfig sopra i valori base:
          pitch_ratio  *= 2^(pitch_offset/12)
          pointer_pos  += pointer_offset
          pan          += pan_offset
          onset        += onset_offset

        Args:
            elapsed_time: tempo trascorso dall'inizio dello stream
            grain_dur:    durata del grano
            voice_config: offset per questa voce (None = VoiceConfig(0,0,0,0))

        Returns:
            Grain: oggetto grano completo
        """
        if voice_config is None:
            voice_config = VoiceConfig(0.0, 0.0, 0.0, 0.0)

        grain_reverse = self._calculate_grain_reverse(elapsed_time)

        # === 1. PITCH — base × 2^(semitoni/12) ===
        pitch_ratio = self._pitch.calculate(elapsed_time, grain_reverse=grain_reverse)
        if voice_config.pitch_offset != 0.0:
            pitch_ratio *= 2 ** (voice_config.pitch_offset / 12.0)

        # === 2. POINTER — base + voice_offset ===
        pointer_pos = self._pointer.calculate(elapsed_time, grain_dur, grain_reverse)
        pointer_pos += voice_config.pointer_offset

        # === 3. VOLUME ===
        volume = self.volume.get_value(elapsed_time)

        # === 4. PAN — base + voice_offset ===
        pan = self.pan.get_value(elapsed_time) + voice_config.pan_offset

        # === 5. ONSET — assoluto + voice_onset_offset ===
        absolute_onset = self.onset + elapsed_time + voice_config.onset_offset

        # === 6. WINDOW ===
        window_name = self._window_controller.select_window()
        window_table_num = self.window_table_map[window_name]

        return Grain(
            onset=absolute_onset,
            duration=grain_dur,
            pointer_pos=pointer_pos,
            pitch_ratio=pitch_ratio,
            volume=volume,
            pan=pan,
            sample_table=self.sample_table_num,
            envelope_table=window_table_num
        )


    def _calculate_grain_reverse(self, elapsed_time: float) -> bool:
        """
        Calcola se il grano deve essere riprodotto al contrario.
        
        Usa evaluate_gated_stochastic con variation_mode='invert':
        - 'auto': base_reverse segue pointer_speed
        - grain_reverse_randomness: probabilità di flip (0-100)
        - grain_reverse_randomness=None: nessun flip (mantiene base)
        
        Args:
            elapsed_time: tempo trascorso dall'inizio dello stream
            
        Returns:
            bool: True se grano deve essere riprodotto al contrario
        """
        # 1. Determina base value come float (0.0 o 1.0)
        if self.grain_reverse_mode == 'auto':
            # Se la testina va indietro, il grano è reverse di base
            is_reverse_base = (self._pointer.get_speed(elapsed_time) < 0)
        else:
            # Se forzato da YAML, usiamo il valore caricato nel parametro
            # Nota: self.reverse._value può essere un numero o un Envelope
            val = self.reverse._value
            if hasattr(val, 'evaluate'):
                val = val.evaluate(elapsed_time)
            is_reverse_base = (val > 0.5) if val is not None else True
        
        # FASE 2: Controlliamo se dobbiamo FLIPPARE (Dephase/Probabilità)
        # Usiamo il metodo interno del parametro per vedere se il "dado" vince
        # Nota: Qui stiamo "rubando" la logica probabilistica all'oggetto Parameter
        should_flip = self.reverse._probability_gate.should_apply(elapsed_time)
        
        if should_flip:
            return not is_reverse_base
        return is_reverse_base
    # =========================================================================
    # PROPRIETÀ PER BACKWARD COMPATIBILITY
    # =========================================================================

    @property
    def sampleDurSec(self) -> float:
        """Alias per backward compatibility."""
        return self.sample_dur_sec
        
    @property
    def density(self) -> Optional[Union[float, Envelope]]:
        """Espone density per Generator/ScoreVisualizer."""
        return self._density.density
    
    @property
    def fill_factor(self) -> Optional[Union[float, Envelope]]:
        """Espone fill_factor per Generator/ScoreVisualizer."""
        return self._density.fill_factor
    
    @property
    def distribution(self):
        return self._density.distribution.value if hasattr(self._density.distribution, 'value') else self._density.distribution
        
    @property
    def pointer_speed(self):
        return self._pointer.speed.value

    @property
    def loop_start(self):
        """Espone loop_start del PointerController per ScoreVisualizer."""
        return self._pointer.loop_start

    @property
    def loop_end(self):
        """Espone loop_end del PointerController per ScoreVisualizer."""
        return self._pointer.loop_end

    @property
    def loop_dur(self):
        """Espone loop_dur del PointerController per ScoreVisualizer."""
        return self._pointer.loop_dur

    @property
    def pitch_ratio(self) -> Optional[Union[float, Envelope]]:
        """Espone pitch_ratio per ScoreVisualizer (solo se in modalità ratio)."""
        return self._pitch.base_ratio
    
    @property
    def pitch_semitones(self) -> Optional[Union[float, Envelope]]:
        """Espone pitch_semitones per ScoreVisualizer (solo se in modalità semitoni)."""
        return self._pitch.base_semitones
    
    @property
    def pitch_range(self) -> Union[float, Envelope]:
        """Espone pitch_range per ScoreVisualizer."""
        return self._pitch.range
        
    @property
    def num_voices(self):
        """Espone num_voices come Parameter (supporta Envelope time-varying)."""
        return self._num_voices
            
    # =========================================================================
    # REPR
    # =========================================================================
    
    def __repr__(self) -> str:
        mode = "fill_factor" if self.fill_factor is not None else "density"
        return (f"Stream(id={self.stream_id}, onset={self.onset}, "
                f"dur={self.duration}, mode={mode}, grains={len(self.grains)})")
