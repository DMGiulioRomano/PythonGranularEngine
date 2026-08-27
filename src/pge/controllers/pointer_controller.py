# src/pointer_controller.py
"""
PointerController - Gestione posizionamento testina di lettura

Gestisce la posizione di lettura nel sample con:
- Movimento lineare con integrazione envelope
- Loop con phase accumulator per durata dinamica
- Deviazioni stocastiche (jitter, offset_range)

Ispirato al DMX-1000 di Barry Truax (1988)
"""
from __future__ import annotations

from typing import Callable
from pge.envelopes.envelope import Envelope, scale_raw_param_values
from pge.parameters.parameter_schema import POINTER_PARAMETER_SCHEMA
from pge.parameters.parameter_orchestrator import ParameterOrchestrator
from pge.core.stream_config import StreamConfig
from pge.shared.logger import (
    log_config_warning,
    log_loop_drift_warning,
    log_loop_dynamic_mode,
    log_loop_init,
    log_loop_unit_migration_warning,
)
from pge.shared.exceptions import InvalidFieldValueError

# Vocabolario di 'loop_unit' (issue #222). Fuori di qui e' un errore.
#
# 'seconds' e' la grafia canonica — allinea loop_unit a grain.duration_unit,
# l'unita' nata «sul modello di loop_unit» (CHANGELOG v5.1.0) — e 'absolute'
# l'alias storico, quello che i config e la reference hanno sempre scritto.
# Sono la stessa lettura: valori gia' in secondi assoluti, nessuna conversione.
LOOP_UNITS = ('seconds', 'absolute', 'normalized')

# Le chiavi del blocco pointer che 'loop_unit' interpreta. 'start' e' fra
# queste benche' loop non sia: e' una posizione nel sample come loop_start,
# stesso dominio e stessa unita' (reference §10.1).
_LOOP_UNIT_SCOPE = ('start', 'loop_start', 'loop_end', 'loop_dur')


def _rescaling_would_change(value) -> bool:
    """True se la conversione a secondi muoverebbe `value`.

    Serve solo all'avviso di migrazione di #222, e per essere utile deve essere
    lo specchio di cio' che `scale_raw_param_values` tocca davvero: numeri ed
    envelope-like, e nient'altro. Due esclusioni, per due motivi diversi:

    - uno zero e' zero sotto qualunque fattore di scala, quindi non ha niente
      da migrare (ed e' la forma piu' comune nel corpus dei config);
    - quel che la conversione lascia passare invariato — una stringa, per dire
      — non si muoveva nemmeno prima.
    """
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return Envelope.is_envelope_like(value)



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

        # 3b. `start` e' un valore, non una curva: `calculate` lo somma alla
        # posizione (`self.start + sample_position`), e la spec lo dichiara
        # is_smart=False, quindi qui arriva grezzo dallo YAML. Se e' un
        # envelope va fermato adesso, mentre il campo ha ancora un nome: piu'
        # avanti diventa un TypeError dentro la generazione dei grani, quando
        # non c'e' piu' modo di dire all'utente cosa ha scritto.
        if not isinstance(self.start, (int, float)):
            err = InvalidFieldValueError(
                field='pointer.start',
                value=self.start,
                hint=(
                    "pointer.start e' un valore scalare — la posizione di "
                    "partenza nel sample — e non accetta envelope.\n"
                    "  Se non ti serve, ometti la chiave: il default e' 0.0 "
                    "(o loop_start, con un loop attivo).\n"
                    "  Per far variare nel tempo la posizione di lettura usa "
                    "pointer.speed_ratio, oppure un loop mobile con "
                    "loop_start come envelope."
                ),
            )
            err.stream_id = self._config.context.stream_id
            raise err

        # 4. has_loop dipende solo dalla presenza di loop_start
        self.has_loop = 'loop_start' in params
        # Se loop_start è presente ma start non è esplicito nello YAML,
        # il pointer parte direttamente da loop_start(t=0) invece di 0.
        if self.has_loop and 'start' not in params:
            self.start = self.loop_start.get_value(0.0)
        if self.has_loop and self.loop_end is None and self.loop_dur is None:
            self.loop_end = self._orchestrator.create_constant_parameter(
    'loop_end', self._sample_dur_sec
)
        # 4b. Validazione bound statici del loop: loop_end deve essere > loop_start.
        self._validate_loop_bounds(params)
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


    def _validate_loop_bounds(self, params: dict) -> None:
        """Rifiuta loop_end <= loop_start per bound statici (Opzione 1).

        Il loop a cavallo della fine del file si esprime SOLO via loop_dur; un
        loop_end minore o uguale a loop_start degenererebbe in un loop morto
        (regione invertita), quindi va segnalato come errore esplicito.

        Validato solo quando entrambi i bound sono scalari numerici dichiarati:
        - modalita' loop_dur            -> nessuna validazione d'ordine
        - loop_end implicito (fallback) -> nessuna validazione
        - bound dinamici (Envelope)     -> esentati (l'ordine puo' variare nel tempo)
        """
        if not self.has_loop or self.loop_dur is not None:
            return
        # Solo se loop_end e' stato dichiarato esplicitamente dall'utente.
        if params.get('loop_end') is None:
            return
        ls_raw = getattr(self.loop_start, '_value', None)
        le_raw = getattr(self.loop_end, '_value', None)
        # Valida esclusivamente bound statici (scalari numerici).
        if not isinstance(ls_raw, (int, float)) or not isinstance(le_raw, (int, float)):
            return
        start_v = self.loop_start.get_value(0.0)
        end_v = self.loop_end.get_value(0.0)
        if end_v <= start_v:
            raise InvalidFieldValueError(
                field='loop_end',
                value=end_v,
                hint=(
                    f"loop_end deve essere maggiore di loop_start ({start_v}). "
                    "Per un loop a cavallo della fine del file usa loop_dur."
                ),
            )

    def _pre_normalize_loop_params(self, params: dict) -> dict:
        """
        Conversione di unita' per le posizioni nel sample.

        `loop_unit: normalized` scala i valori di `start`, `loop_start`,
        `loop_end` e `loop_dur` da [0.0-1.0] a secondi assoluti usando
        `sample_dur_sec` dal context. Il default e' `seconds`: nessuna
        conversione.

        `loop_unit` NON eredita da `time_mode` (issue #222). Le due chiavi
        governano assi diversi con riferimenti diversi: `time_mode` scala
        l'asse X (tempo) degli envelope sulla `duration` dello stream,
        `loop_unit` scala l'asse Y (valore) sulla `sample_dur_sec` del file
        audio. Restano indipendenti e possono coesistere sullo stesso
        envelope — e' la coesistenza documentata in §10.1 della reference.

        Questo metodo e' l'unico punto nel sistema che legge 'loop_unit'
        dal dizionario grezzo, ed e' il motivo legittimo: loop_unit e' un
        meta-parametro che controlla l'interpretazione degli altri, non un
        valore sintetizzabile.
        """
        if params is None:
            return {}

        if 'loop_unit' not in params:
            self._warn_loop_unit_migration(params)
            return params  # default 'seconds': valori gia' in secondi assoluti

        loop_unit = params['loop_unit']
        if loop_unit not in LOOP_UNITS:
            # Stessa forma di Stream._pre_normalize_grain_params: la chiave
            # e' scritta, quindi il refuso va nominato invece di ricadere in
            # silenzio su "assoluto".
            err = InvalidFieldValueError(
                field='pointer.loop_unit',
                value=loop_unit,
                hint=f"unità disponibili: {list(LOOP_UNITS)}",
            )
            err.stream_id = self._config.context.stream_id
            raise err

        if loop_unit != 'normalized':
            return params  # 'seconds'/'absolute': gia' in secondi assoluti

        scale = self._sample_dur_sec

        # Copia superficiale: non modificare il dizionario originale
        # (il fingerprint della cache e stream_data_map leggono i dati grezzi).
        scaled = dict(params)
        for key in _LOOP_UNIT_SCOPE:
            if scaled.get(key) is not None:
                scaled[key] = self._scale_value(scaled[key], scale)

        return scaled

    # ponytail: si toglie dopo una release, quando il vecchio comportamento
    # di loop_unit non e' piu' memoria viva di nessuno. Il conto lo tiene la
    # issue #242, che elenca tutto cio' che va via insieme a questo metodo:
    # il marcatore da solo non lo greperebbe nessuno.
    def _warn_loop_unit_migration(self, params: dict) -> None:
        """Avvisa gli stream a cui #222 cambia il significato dei numeri.

        Prima di #222 un `loop_unit` mancante ereditava da `time_mode`: su uno
        stream `normalized` queste posizioni venivano scalate per
        `sample_dur_sec`. Ora non piu'.

        Avvisa solo chi cambia davvero: uno zero resta zero sotto qualunque
        fattore di scala, e `start: 0` e' la forma piu' comune nel corpus dei
        config — senza il filtro sarebbero undici avvisi su stream in cui non
        si muove un campione, con i tre casi veri in mezzo al rumore.
        """
        if self._config.time_mode != 'normalized':
            return

        affected = [key for key in _LOOP_UNIT_SCOPE
                    if _rescaling_would_change(params.get(key))]
        if not affected:
            return

        log_loop_unit_migration_warning(
            stream_id=self._config.context.stream_id,
            keys=affected,
            sample_dur_sec=self._sample_dur_sec,
        )


    def _scale_value(self, value, scale: float):
            """
            Scala un valore che puo' essere scalare, envelope, o dict.
            Delega all'helper condiviso scale_raw_param_values (stesso
            meccanismo di grain.duration_unit).
            """
            return scale_raw_param_values(value, scale)


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
        grain_reverse: bool = False,
        voice_offset: float = 0.0
    ) -> float:
        """
        Calcola la posizione di lettura nel sample per questo grano.

        Usa Phase Accumulator per loop con durata dinamica (envelope).
        La fase si accumula incrementalmente, evitando salti quando
        loop_length cambia.

        Con loop attivo la posizione finale (base + deviazione offset_range +
        offset di voce) e' confinata DENTRO la finestra di loop tramite wrap
        modulare; il modulo finale su sample_dur_sec gestisce i loop a cavallo
        della fine del file. Senza loop la finestra coincide col file intero.

        Args:
            elapsed_time: secondi trascorsi dall'onset dello stream
            grain_duration: durata del grano (sommata in reverse, prima del wrap)
            grain_reverse: se True, grano invertito (offset +grain_duration)
            voice_offset: offset di pointer della voce, in secondi, confinato
                al loop insieme alla deviazione (0.0 per la voce di riferimento)

        Returns:
            float: posizione in secondi nel sample sorgente, sempre in [0, sample_dur)
        """
        # 1. Calcola movimento lineare (da speed)
        linear_pos = self._calculate_linear_position(elapsed_time)

        # 2. Ottieni posizione ESTESA e finestra attiva (window_start, window_length)
        #    - Con loop:    extended_pos in coordinate estese [loop_start, loop_start+len),
        #                   window_start = loop_start corrente, window_length = lunghezza loop
        #    - Senza loop:  finestra = file intero (window_start=0, window_length=sample_dur)
        if self.has_loop:
            extended_pos, window_start, window_length = self._apply_loop(linear_pos, elapsed_time)
        else:
            extended_pos = linear_pos
            window_start = 0.0
            window_length = self._sample_dur_sec

        # 3. Somma deviazione per-grano (scalata sulla finestra) e offset di voce,
        #    in coordinate estese. Sono spostamenti temporanei: non modificano lo
        #    stato del loop (il phase accumulator resta intatto).
        dev_normalized = self.deviation.get_value(elapsed_time)
        final_pos = extended_pos + dev_normalized * window_length + voice_offset
        # 4. Offset per grano invertito (aggiunto prima del wrap)
        if grain_reverse:
            final_pos += grain_duration

        # 5. Confinamento alla finestra attiva (wrap modulare), poi rimappa sul
        #    buffer intero. Con loop il grano resta DENTRO il loop; il modulo finale
        #    su sample_dur_sec realizza il loop a cavallo della fine (loop_dur).
        #    Senza loop collassa nel semplice % sample_dur_sec.
        rel = (final_pos - window_start) % window_length
        return (window_start + rel) % self._sample_dur_sec

    def _apply_loop(
        self,
        linear_pos: float,
        elapsed_time: float
    ) -> tuple[float, float, float]:
        """
        Applica logica loop con phase accumulator basato su posizione assoluta.
        
        Strategia:
        - Traccia posizione assoluta nel sample (non fase relativa 0-1)
        - Movimento inerziale: posizione += delta_pos
        - Se loop bounds cambiano e pointer è fuori → RESET a loop_start
        - Se loop bounds stabili e pointer supera loop_end → WRAP modulare
        
        Returns:
            tuple[float, float, float]: (extended_pos, window_start, window_length)
                extended_pos: posizione corrente in coordinate ESTESE, non ancora
                              modulata sul sample. Dentro il loop vive in
                              [loop_start, loop_start+loop_length); il modulo finale
                              su sample_dur_sec (in calculate) realizza il cavallo.
                window_start: inizio della finestra di loop attiva (loop_start corrente);
                              0.0 nel pre-loop (finestra = file intero).
                window_length: lunghezza della finestra attiva (secondi). Usata da
                               calculate() per scalare la deviazione e per il wrap.

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
                    # Pre-loop: finestra = file intero, posizione estesa = lineare grezza
                    return linear_pos, 0.0, self._sample_dur_sec

            # Entrata confermata (statica o dinamica)
            self._in_loop = True
            self._loop_absolute_pos = entry_pos
            self._last_linear_pos = linear_pos
            self._prev_loop_start = current_loop_start
            self._prev_loop_end = current_loop_end
            return entry_pos, current_loop_start, loop_length

        
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
        # STEP 3e: Restituisci risultato in coordinate estese
        # ---------------------------------------------------------------------
        #    _loop_absolute_pos vive in [loop_start, loop_start+loop_length); il
        #    modulo finale su sample_dur_sec (in calculate) gestisce il cavallo.
        return self._loop_absolute_pos, current_loop_start, loop_length

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
