# src/pointer_controller.py
"""
PointerController - Gestione posizionamento testina di lettura

Gestisce la posizione di lettura nel sample con:
- Movimento lineare con integrazione envelope
- Loop con phase accumulator per durata dinamica
- Deviazioni stocastiche (jitter, offset_range)

Ispirato al DMX-1000 di Barry Truax (1988)
"""

from typing import Callable
from envelopes.envelope import Envelope
from parameters.parameter_schema import POINTER_PARAMETER_SCHEMA
from parameters.parameter_orchestrator import ParameterOrchestrator
from core.stream_config import StreamConfig
from shared.logger import log_config_warning, log_loop_drift_warning, log_loop_dynamic_mode, log_loop_init
class PointerController:
    """
    Gestisce il posizionamento della testina di lettura nel sample.
    
    Responsabilità:
    - Parsing parametri pointer da YAML
    - Movimento lineare (velocità costante o envelope)
    - Loop con phase accumulator (gestisce durata dinamica)
    - Deviazioni stocastiche (jitter micro, offset_range macro)
    
    Il controller usa un ParameterEvaluator per:
    - parse(): conversione YAML → numero/Envelope
    - evaluate(): valutazione con bounds safety
    
    Usage:
        evaluator = ParameterEvaluator("stream1", duration, time_mode)
        pointer = PointerController(params['pointer'], evaluator, sample_dur_sec, time_mode)
        
        # Nel loop di generazione grani:
        position = pointer.calculate(elapsed_time)
    """
    
    def __init__(
        self,
        params: dict,       
        config: StreamConfig
    ):
        """
        Inizializza il controller.
        
        Args:
            params: dict con configurazione pointer da YAML
            evaluator: ParameterEvaluator per parsing e valutazione
            sample_dur_sec: durata del sample in secondi
            time_mode: 'absolute' o 'normalized' (default per envelope)
        """
        self._config = config
        self._sample_dur_sec = config.context.sample_dur_sec 
        self._orchestrator = ParameterOrchestrator(config=config)
        self._init_params(params)
        self._init_loop_state()
    
    # =========================================================================
    # INITIALIZATION
    # =========================================================================
    def _init_params(self, params: dict) -> None:
        # 1. Pre-processing: conversione unita' PRIMA del pipeline
        normalized_params = self._pre_normalize_loop_params(params)

        # 2. Tutto entra nel pipeline standard. Nessun caso speciale.
        all_params = self._orchestrator.create_all_parameters(normalized_params, schema=POINTER_PARAMETER_SCHEMA)
        # 3. Assegnazione uniforme. Nessun 'continue', nessun fake_params.
        for name, param_obj in all_params.items():
            attr_name = name.replace('pointer_', '')
            setattr(self, attr_name, param_obj)

        # 4. has_loop dipende solo dalla presenza di loop_start
        self.has_loop = self.loop_start is not None
        if self.has_loop and self.loop_end is None and self.loop_dur is None:
            self.loop_end = self._orchestrator.create_constant_parameter(
    'loop_end', self._sample_dur_sec
)
        # 5. Rileva se il loop e' dinamico (loop_start e' un Envelope).
        #    In modalita' dinamica il pointer entra immediatamente nel loop
        #    a elapsed=0, senza attendere che la posizione lineare
        #    intersechi la regione.
        self._loop_is_dynamic = False
        if self.has_loop:
            self._loop_is_dynamic = isinstance(self.loop_start._value, Envelope)
            if self._loop_is_dynamic:
                loop_start_t0 = self.loop_start.get_value(0.0)
                if self.loop_dur is not None:
                    loop_end_t0 = loop_start_t0 + self.loop_dur.get_value(0.0)
                elif hasattr(self.loop_end, 'get_value'):
                    loop_end_t0 = self.loop_end.get_value(0.0)
                else:
                    loop_end_t0 = float(self.loop_end)
                start_overridden = abs(self.start - loop_start_t0) > 1e-6
                log_loop_dynamic_mode(
                    stream_id=self._config.context.stream_id,
                    loop_start_initial=loop_start_t0,
                    loop_end_initial=loop_end_t0,
                    start_overridden=start_overridden,
                    original_start=self.start
                )
            else:
                loop_start_val = self.loop_start.get_value(0.0)

                if self.loop_dur is not None:
                    loop_dur_val  = self.loop_dur.get_value(0.0)
                    loop_end_val  = None
                else:
                    loop_dur_val  = None
                    if hasattr(self.loop_end, 'get_value'):
                        loop_end_val = self.loop_end.get_value(0.0)  # None -> 0.0 qui
                    elif self.loop_end is not None:
                        loop_end_val = float(self.loop_end)           # float dal fallback
                    else:
                        loop_end_val = None

                log_loop_init(
                    stream_id      = self._config.context.stream_id,
                    loop_start     = loop_start_val,
                    loop_end       = loop_end_val,
                    loop_dur       = loop_dur_val,
                    sample_dur_sec = self._sample_dur_sec
                )


    def _pre_normalize_loop_params(self, params: dict) -> dict:
        """
        Conversione di unita' per i parametri loop.
        
        Se loop_unit == 'normalized', scala i valori dei parametri loop
        da [0.0-1.0] a secondi assoluti usando sample_dur_sec dal context.
        
        Questo metodo e' l'unico punto nel sistema che legge 'loop_unit'
        dal dizionario grezzo, ed e' il motivo legittimo: loop_unit e' un
        meta-parametro che controlla l'interpretazione degli altri, non un
        valore sintetizzabile.
        """
        if params is None:
            return {}

        loop_unit = params.get('loop_unit') or self._config.time_mode
        if loop_unit != 'normalized':
            return params  # Valori gia' in secondi assoluti

        scale = self._sample_dur_sec

        # Copia superficiale: non modificare il dizionario originale
        scaled = dict(params)

        # Scala start (indipendente dalla presenza di loop_start)
        if 'start' in scaled and scaled['start'] is not None:
            scaled['start'] = self._scale_value(scaled['start'], scale)

        # Scala i parametri loop
        for key in ('loop_start', 'loop_end', 'loop_dur'):
            if key in scaled and scaled[key] is not None:
                scaled[key] = self._scale_value(scaled[key], scale)

        return scaled


    def _scale_value(self, value, scale: float):
            """
            Scala un valore che puo' essere scalare, envelope, o dict.
            Restituisce dati raw (stesso formato dell'input) per compatibilita'
            col pipeline parser a valle.
            """
            if isinstance(value, (int, float)):
                return value * scale
            if Envelope.is_envelope_like(value):
                return Envelope._scale_raw_values_y(value, scale)
            return value


    def _init_loop_state(self) -> None:
        self._in_loop = False
        self._loop_absolute_pos = None      
        self._last_linear_pos = None
        self._prev_loop_start = None        
        self._prev_loop_end = None          
        self._drift_prev_loop_start = None
        self._drift_prev_elapsed = None
        self._drift_log_interval = 5.0      
        self._drift_last_logged = -999.0    
        self._drift_first_warning_emitted = False   
    # =========================================================================
    # CALCULATION
    # =========================================================================
    
    def calculate(
        self,
        elapsed_time: float,
        grain_duration: float = 0.0,
        grain_reverse: bool = False
    ) -> float:
        """
        Calcola la posizione di lettura nel sample per questo grano.
        
        Usa Phase Accumulator per loop con durata dinamica (envelope).
        La fase si accumula incrementalmente, evitando salti quando
        loop_length cambia.
        
        Args:
            elapsed_time: secondi trascorsi dall'onset dello stream
            
        Returns:
            float: posizione in secondi nel sample sorgente
        """
        # 1. Calcola movimento lineare (da speed)
        linear_pos = self._calculate_linear_position(elapsed_time)
        
        # 2. Ottieni posizione base e finestra di contesto
        #    - Con loop:    base_pos e' dentro il loop, loop_length e' la sua lunghezza
        #    - Senza loop:  base_pos e' wrap sul sample, loop_length = sample_dur_sec
        if self.has_loop:
            base_pos, loop_length = self._apply_loop(linear_pos, elapsed_time)
        else:
            base_pos = linear_pos % self._sample_dur_sec
            loop_length = self._sample_dur_sec

        # 3. Applica deviazione per-grano (scala rispetto alla finestra attiva)
        #    La deviazione e' un offset temporaneo: non modifica lo stato del loop.
        #    Puo' portare il pointer fuori dal loop — il wrap avviene sul sample intero,
        #    non sul loop (bypass semantics: il grano atterrerra' dove capita nel sample).
        dev_normalized = self.deviation.get_value(elapsed_time)
        final_pos = base_pos + dev_normalized * loop_length
        # 4. Offset per grano invertito (aggiunto prima del wrap)
        if grain_reverse:
            final_pos += grain_duration
        # 5. Wrap finale sempre sul buffer intero
        return final_pos % self._sample_dur_sec

    def _apply_loop(
        self,
        linear_pos: float,
        elapsed_time: float
    ) -> tuple[float, float, Callable[[float], float]]:
        """
        Applica logica loop con phase accumulator basato su posizione assoluta.
        
        Strategia:
        - Traccia posizione assoluta nel sample (non fase relativa 0-1)
        - Movimento inerziale: posizione += delta_pos
        - Se loop bounds cambiano e pointer è fuori → RESET a loop_start
        - Se loop bounds stabili e pointer supera loop_end → WRAP modulare
        
        Returns:
            tuple[float, float]: (base_pos, loop_length)
                base_pos:    posizione corrente nel sample (secondi)
                loop_length: lunghezza della finestra di loop attiva (secondi).
                             Usata da calculate() per scalare la deviazione.
                             Equivale a sample_dur_sec nel pre-loop.
        
        """
        # =========================================================================
        # STEP 1: Valuta loop bounds CORRENTI (possono essere envelope!)
        # =========================================================================
        current_loop_start = self.loop_start.get_value(elapsed_time)
        
        if self.loop_dur is not None:
            # Modalità loop_dur (dinamica)
            current_loop_dur = self.loop_dur.get_value(elapsed_time)

        else:
            # Modalità loop_end (può essere dinamica ora!)
            current_loop_end_val = self.loop_end.get_value(elapsed_time)
            current_loop_dur = current_loop_end_val - current_loop_start
        
        current_loop_end = current_loop_start + current_loop_dur
        loop_length = max(current_loop_dur, 0.001)  
        
        # =========================================================================
        # STEP 2: ENTRATA nel loop
        # =========================================================================
        if not self._in_loop:
            if self._loop_is_dynamic:
                # Modalita' dinamica: entrata immediata a loop_start(0).
                # Il pointer nasce dentro la finestra mobile senza fase pre-loop.
                entry_pos = current_loop_start
            else:
                # Modalita' statica: entrata solo quando la posizione lineare
                # interseca la regione [loop_start, loop_end).
                check_pos = linear_pos % self._sample_dur_sec
                if current_loop_start <= check_pos < current_loop_end:
                    entry_pos = check_pos
                else:
                    # Non ancora dentro → comportamento pre-loop
                    self._emit_loop_drift_warning(
                        check_pos, current_loop_start, current_loop_end, elapsed_time
                    )
                    base_pos = linear_pos % self._sample_dur_sec
                    return base_pos, self._sample_dur_sec

            # Entrata confermata (statica o dinamica)
            self._in_loop = True
            self._loop_absolute_pos = entry_pos
            self._last_linear_pos = linear_pos
            self._prev_loop_start = current_loop_start
            self._prev_loop_end = current_loop_end
            return entry_pos, loop_length

        
        # =========================================================================
        # STEP 3: Siamo DENTRO il loop
        # =========================================================================
        # ---------------------------------------------------------------------
        # STEP 3a: Calcola movimento inerziale del pointer
        # ---------------------------------------------------------------------
        if self._last_linear_pos is not None:
            delta_pos = linear_pos - self._last_linear_pos
            self._loop_absolute_pos += delta_pos
        
        self._last_linear_pos = linear_pos
        
        # ---------------------------------------------------------------------
        # STEP 3b: Rileva se i bounds sono cambiati
        # ---------------------------------------------------------------------
        bounds_changed = (
            self._prev_loop_start is not None and (
                self._prev_loop_start != current_loop_start or
                self._prev_loop_end != current_loop_end
            )
        )
        

        # ---------------------------------------------------------------------
        # STEP 3c: Gestisci fuori-bounds
        # ---------------------------------------------------------------------
        if bounds_changed:
            if not (current_loop_start <= self._loop_absolute_pos < current_loop_end):
                if delta_pos >= 0:
                    self._loop_absolute_pos = current_loop_start
                    reset_target = "loop_start"
                else:
                    self._loop_absolute_pos = current_loop_end - 1e-9
                    reset_target = "loop_end"

                # Log solo se il drift sta superando la speed del pointer,
                # cioe' il pointer non riesce a stare dietro alla finestra mobile.
                # In quel caso _emit_loop_drift_warning mostra anche la speed minima.
                # Reset normali (loop dinamico che avanza regolarmente) → nessun log.
                if self._loop_is_dynamic:
                    self._emit_loop_drift_warning(
                        self._loop_absolute_pos,
                        current_loop_start,
                        current_loop_end,
                        elapsed_time
                    )
                else:
                    # Loop statico: il reset e' inatteso, logga sempre
                    log_config_warning(
                        stream_id=self._config.context.stream_id,
                        param_name="pointer_position",
                        raw_value=self._loop_absolute_pos,
                        clipped_value=self._loop_absolute_pos,
                        min_val=current_loop_start,
                        max_val=current_loop_end,
                        value_type=f"loop_reset_to_{reset_target}"
                    )
        else:
            # Bounds stabili: WRAP MODULARE UNIFICATO
            # Funziona sia per movimento in avanti che indietro!
            if not (current_loop_start <= self._loop_absolute_pos < current_loop_end):
                rel = self._loop_absolute_pos - current_loop_start
                self._loop_absolute_pos = current_loop_start + (rel % loop_length)
                
        # ---------------------------------------------------------------------
        # STEP 3d: Aggiorna tracciamento bounds 
        # ---------------------------------------------------------------------
        self._prev_loop_start = current_loop_start
        self._prev_loop_end = current_loop_end
        
        # ---------------------------------------------------------------------
        # STEP 3e: Restituisci risultato
        # ---------------------------------------------------------------------
        base_pos = self._loop_absolute_pos % self._sample_dur_sec
        return base_pos, loop_length

    def _emit_loop_drift_warning(
        self,
        pointer_pos: float,
        current_loop_start: float,
        current_loop_end: float,
        elapsed_time: float
    ) -> None:
        """
        Emette un warning diagnostico quando il pointer non riesce a entrare
        nel loop, con calcolo del drift rate e della speed minima necessaria.
        Emette al massimo una volta ogni _drift_log_interval secondi.
        """
        # Rate limiting: non spammare il log ad ogni grano (density=2000!)
        if elapsed_time - self._drift_last_logged < self._drift_log_interval:
            return

        # Calcola drift rate di loop_start (quanto si sposta per secondo)
        drift_rate = 0.0
        if (self._drift_prev_loop_start is not None and
                self._drift_prev_elapsed is not None and
                elapsed_time > self._drift_prev_elapsed):
            dt = elapsed_time - self._drift_prev_elapsed
            d_loop_start = current_loop_start - self._drift_prev_loop_start
            drift_rate = d_loop_start / dt

        # Aggiorna stato per prossimo calcolo
        self._drift_prev_loop_start = current_loop_start
        self._drift_prev_elapsed = elapsed_time
        self._drift_last_logged = elapsed_time

        is_first = not self._drift_first_warning_emitted
        self._drift_first_warning_emitted = True

        current_speed = self.speed_ratio.get_value(elapsed_time)

        log_loop_drift_warning(
            stream_id=self._config.context.stream_id,
            elapsed_time=elapsed_time,
            pointer_pos=pointer_pos,
            loop_start=current_loop_start,
            loop_end=current_loop_end,
            speed_ratio=current_speed,
            loop_start_drift_rate=drift_rate,
            stream_duration=self._config.context.sample_dur_sec,
            is_first=is_first
        )

    def _calculate_linear_position(self, elapsed_time: float) -> float:
        """
        Calcola posizione lineare da speed_ratio (con integrazione per envelope).
        
        Se speed_ratio è un Envelope, integra per ottenere la posizione.
        Altrimenti: position = start + time * speed_ratio
        """
        internal_val = self.speed_ratio.value
        if isinstance(internal_val, Envelope):
            sample_position = internal_val.integrate(0, elapsed_time)
        else:
            sample_position = elapsed_time * float(internal_val)
        return self.start + sample_position

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================
    
    def reset(self) -> None:
        """Resetta lo stato del loop (per riuso del controller)."""
        self._init_loop_state()

    def get_speed(self, elapsed_time: float) -> float:
        """Ritorna la velocità istantanea al tempo specificato."""
        return self.speed_ratio.get_value(elapsed_time)
        
    # =========================================================================
    # PROPERTIES (Read-only access)
    # =========================================================================
    
    @property
    def sample_dur_sec(self) -> float:
        """Durata del sample in secondi."""
        return self._sample_dur_sec
    
    @property
    def in_loop(self) -> bool:
        """True se attualmente nel loop."""
        return self._in_loop
    
    @property
    def loop_phase(self) -> float:
        """Fase corrente nel loop (0.0 - 1.0)."""
        if not self._in_loop or self._loop_absolute_pos is None:
            return 0.0
        
        loop_start = self.loop_start.get_value(0)
        if self.loop_dur is not None:
            loop_length = self.loop_dur.get_value(0)
        else:
            loop_end = self.loop_end.get_value(0)
            loop_length = loop_end - loop_start
        
        if loop_length <= 0:
            return 0.0
        
        rel_pos = self._loop_absolute_pos - loop_start
        return (rel_pos % loop_length) / loop_length
    
    
    # =========================================================================
    # REPR
    # =========================================================================
    
    def __repr__(self) -> str:
        if self.has_loop:
            loop_start_val = self.loop_start.get_value(0)
            if self.loop_end is not None:
                loop_end_val = self.loop_end.get_value(0)
                loop_info = f", loop={loop_start_val:.3f}-{loop_end_val:.3f}"
            else:
                loop_info = f", loop={loop_start_val:.3f}-dynamic"
        else:
            loop_info = ""
        return f"PointerController(start={self.start}, speed={self.speed_ratio._value}{loop_info})"