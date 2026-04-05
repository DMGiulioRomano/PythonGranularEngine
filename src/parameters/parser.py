"""
parser.py

Modulo Factory/Builder per la creazione di oggetti Parameter.
Agisce come un ponte tra i dati grezzi (YAML) e il modello a oggetti (Parameter).

Responsabilità:
1. Validazione statica: Controlla che il parametro esista nel Registry.
2. Conversione Tipi: Trasforma liste/dict in oggetti Envelope.
3. Normalizzazione Temporale: Scala i tempi degli envelope se richiesto (normalized -> absolute).
4. Iniezione delle Dipendenze: Assembla l'oggetto Parameter con i suoi Bounds.
"""

from typing import Union, Optional, List, Any
from parameters.parameter import Parameter, ParamInput
from envelopes.envelope import Envelope, create_scaled_envelope
from parameters.parameter_definitions import get_parameter_definition

class GranularParser:
    """
    Factory contestuale per la creazione di parametri.
    Mantiene lo stato dello Stream (durata, id) per configurare correttamente
    gli Envelope e i log.
    """

    def __init__(self, config):
        """
        Inizializza il parser con il contesto dello Stream.

        Args:
            stream_id: ID dello stream (usato per i log del parametro).
            duration: Durata totale dello stream (usata per time_scale).
            time_mode: 'absolute' (sec) o 'normalized' (0-1). Default per gli envelope.
        """
        self.stream_id = config.context.stream_id
        self.duration = config.context.duration
        self.sample_dur_sec = config.context.sample_dur_sec
        self.time_mode = config.time_mode
        self.distribution_mode = config.distribution_mode

    def parse_parameter(
        self,
        name: str,
        value_raw: Any,
        range_raw: Any = None,
        prob_raw: Any = None
    ) -> Parameter:
        """
        Metodo Factory principale. Crea un oggetto Parameter pronto all'uso.

        Args:
            name: Nome del parametro (deve esistere in parameter_definitions.py).
            value_raw: Valore base dal YAML (numero, lista breakpoints, dict envelope).
            range_raw: Valore range/randomness dal YAML (opzionale).
            prob_raw: Valore probabilità/dephase dal YAML (opzionale).

        Returns:
            Un'istanza configurata di Parameter.
        """
        # 1. Recupera la definizione (Bounds & Rules) dal Registry.
        # Per loop_dur/loop_start/loop_end il bound massimo è la durata del file audio.
        bounds = get_parameter_definition(name, sample_dur_sec=self.sample_dur_sec)

        # 2. Converte i dati grezzi in formati utilizzabili (float o Envelope)
        # Qui avviene la normalizzazione temporale se necessaria
        clean_value = self._parse_input(value_raw, f"{name}.value")
        clean_range = self._parse_input(range_raw, f"{name}.range")
        clean_prob = self._parse_input(prob_raw, f"{name}.probability")


        # 3. VALIDAZIONE E CLIPPING (NUOVO!)
        validated_value = self._validate_and_clip(
            clean_value,
            bounds.min_val,
            bounds.max_val,
            name,
            value_type='value'
        )
        
        validated_range = self._validate_and_clip(
            clean_range,
            bounds.min_range,
            bounds.max_range,
            name,
            value_type='range'
        ) if clean_range is not None else None
        
        # Probability ha bounds fissi [0, 100]
        validated_prob = self._validate_and_clip(
            clean_prob,
            0.0,
            100.0,
            name,
            value_type='probability'
        ) if clean_prob is not None else None

        # 4. Assembla e restituisce l'oggetto Smart Parameter
        return Parameter(
            name=name,
            value=validated_value,
            bounds=bounds,
            mod_range=validated_range,
            owner_id=self.stream_id,
            distribution_mode=self.distribution_mode
        )

    # =========================================================================
    # INTERNAL HELPER METHODS
    # =========================================================================

    def _parse_input(self, raw_data: Any, context_info: str) -> Optional[ParamInput]:
        """
        Analizza un input grezzo e restituisce float, Envelope o None.
        Gestisce la logica di scaling temporale per gli Envelope.
        """
        # Caso 0: Dato mancante
        if raw_data is None:
            return None

        # Caso 1: Numero semplice (int/float)
        if isinstance(raw_data, (int, float)):
            return float(raw_data)

        # Caso 2: Struttura complessa (Lista o Dict) -> Envelope
        if isinstance(raw_data, (list, dict)):
            return create_scaled_envelope(raw_data, self.duration, self.time_mode)
        # Caso Errore: Tipo non supportato
        raise ValueError(
            f"Formato non valido per '{context_info}': {raw_data}. "
            f"Atteso numero, lista di punti, o dict envelope."
        )

    def _validate_and_clip(
        self,
        param: Optional[ParamInput],
        min_bound: float,
        max_bound: float,
        param_name: str,
        value_type: str
    ) -> Optional[ParamInput]:
        """
        Valida parametro con policy configurabile:
        - STRICT: solleva ValueError se fuori bounds
        - PERMISSIVE: logga warning e clippa        
        Gestisce sia numeri che Envelope. Per Envelope, valida ogni breakpoint Y.
        
        Args:
            param: numero, Envelope, o None
            min_bound: limite minimo
            max_bound: limite massimo
            param_name: nome parametro (per logging)
            value_type: 'value', 'range', o 'probability'
            
        Returns:
            Parametro validato (clippato se necessario)
        """
        from shared.logger import log_config_warning, CLIP_LOG_CONFIG
        
        if param is None:
            return None

        validation_mode = CLIP_LOG_CONFIG.get('validation_mode', 'strict')
    
        # Caso 1: Numero scalare
        if isinstance(param, (int, float)):
            clean = float(param)
            clipped = max(min_bound, min(max_bound, clean))
            
            if clipped != clean:
                # Calcola messaggio di errore
                bound_type = "MIN" if clean < min_bound else "MAX"
                bound_value = min_bound if clean < min_bound else max_bound
                deviation = clean - bound_value
                
                error_msg = (
                    f"Parametro '{param_name}' fuori bounds!\n"
                    f"  {value_type}: {clean:.2f}\n"
                    f"  {bound_type} consentito: {bound_value:.2f}\n"
                    f"  Deviazione: {deviation:+.2f}\n"
                    f"  Stream: {self.stream_id}\n"
                    f"  Bounds validi: [{min_bound}, {max_bound}]"
                )
                
                if validation_mode == 'strict':
                    # FAIL FAST: solleva eccezione
                    raise ValueError(error_msg)
                else:
                    # PERMISSIVE: logga e continua
                    log_config_warning(
                        stream_id=self.stream_id,
                        param_name=param_name,
                        raw_value=clean,
                        clipped_value=clipped,
                        min_val=min_bound,
                        max_val=max_bound,
                        value_type=value_type
                    )
            
            return clipped
        
        # Caso 2: Envelope
        if isinstance(param, Envelope):
            needs_fixing = False
            errors = []
            fixed_points = []
            
            for t, y in param.breakpoints:
                clipped_y = max(min_bound, min(max_bound, y))
                
                if clipped_y != y:
                    needs_fixing = True
                    bound_type = "MIN" if y < min_bound else "MAX"
                    bound_value = min_bound if y < min_bound else max_bound
                    deviation = y - bound_value
                    
                    errors.append(
                        f"  t={t:.2f}s: {value_type}={y:.2f} → {bound_type}={bound_value:.2f} (Δ{deviation:+.2f})"
                    )
                
                fixed_points.append([t, clipped_y])
            
            if needs_fixing:
                error_msg = (
                    f"Envelope '{param_name}' ha breakpoint fuori bounds!\n"
                    f"  Stream: {self.stream_id}\n"
                    f"  Bounds validi: [{min_bound}, {max_bound}]\n"
                    f"  Violazioni:\n" + "\n".join(errors)
                )
                
                if validation_mode == 'strict':
                    raise ValueError(error_msg)
                else:
                    # Log ogni violazione
                    for t, y in param.breakpoints:
                        clipped_y = max(min_bound, min(max_bound, y))
                        if clipped_y != y:
                            log_config_warning(
                                stream_id=self.stream_id,
                                param_name=f"{param_name}_ENV[t={t:.2f}]",
                                raw_value=y,
                                clipped_value=clipped_y,
                                min_val=min_bound,
                                max_val=max_bound,
                                value_type=value_type
                            )
                    return Envelope(fixed_points)
            
            return param
        
        raise TypeError(f"Cannot validate type {type(param)}")