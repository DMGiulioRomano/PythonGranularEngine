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
from __future__ import annotations

from typing import Union, Optional, List, Any
from pge.parameters.parameter import Parameter, ParamInput
from pge.envelopes.envelope import Envelope, create_scaled_envelope
from pge.parameters.parameter_definitions import get_parameter_definition
from pge.shared.distribution_strategy import (
    ANCHOR_CENTER,
    ANCHOR_MIN,
    validate_range_anchor,
)
from pge.shared.exceptions import (
    InvalidFieldValueError,
    InvalidParameterError,
    ParameterBoundError,
)
from pge.shared.seeding import component_rng

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
        # Identità di derivazione RNG (issue #169): rng_group se dichiarato,
        # altrimenti stream_id. Accesso diretto come negli altri call site
        # della derivazione: la property esiste sempre sulla dataclass.
        # stream_id resta l'identità di log/errori.
        self.rng_id = config.context.rng_id
        self.duration = config.context.duration
        self.sample_dur_sec = config.context.sample_dur_sec
        # Sample rate di output: bound minimo dinamico di grain_duration
        # (1 campione). getattr difensivo per i context parziali dei test.
        self.output_sr = getattr(config.context, 'output_sr', None)
        self.time_mode = config.time_mode
        self.distribution_mode = config.distribution_mode
        # Ancora dei range dichiarati (center | min). getattr difensivo come
        # per `seed`: i config parziali dei test possono non averla.
        # Validata qui e non solo a valle nella DistributionFactory: qui si
        # conosce lo stream_id, quindi un typo dice QUALE stream lo contiene
        # invece del solo valore incriminato.
        self.range_anchor = self._validated_anchor(
            getattr(config, 'range_anchor', ANCHOR_CENTER)
        )
        # Seed effettivo del run (issue #154): deriva l'RNG per-parametro.
        # getattr difensivo: i config parziali dei test possono non averlo.
        self.seed = getattr(config, 'seed', None)

    def parse_parameter(
        self,
        name: str,
        value_raw: Any,
        range_raw: Any = None,
        prob_raw: Any = None,
        bounds_override: Any = None
    ) -> Parameter:
        """
        Metodo Factory principale. Crea un oggetto Parameter pronto all'uso.

        Args:
            name: Nome del parametro (deve esistere in parameter_definitions.py).
            value_raw: Valore base dal YAML (numero, lista breakpoints, dict envelope).
            range_raw: Valore range/randomness dal YAML (opzionale).
            prob_raw: Valore probabilità/dephase dal YAML (opzionale).
            bounds_override: ParameterBounds espliciti. Se forniti, bypassano il
                Registry — usati per parametri con bounds dinamici (es. pitch,
                i cui bounds derivano dall'unità di misura, non dal nome).

        Returns:
            Un'istanza configurata di Parameter.
        """
        # 1. Recupera la definizione (Bounds & Rules) dal Registry, salvo override.
        # Per loop_dur/loop_start/loop_end il bound massimo è la durata del file
        # audio; per grain_duration il bound minimo è 1 campione (1/output_sr).
        bounds = (bounds_override if bounds_override is not None
                  else get_parameter_definition(name,
                                                sample_dur_sec=self.sample_dur_sec,
                                                output_sr=self.output_sr))

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

        # 3-bis. Tetto della banda sotto ancora `min` (vedi _validate_band_ceiling).
        self._validate_band_ceiling(validated_value, validated_range, bounds, name)

        # 4. Assembla e restituisce l'oggetto Smart Parameter.
        # RNG per-componente (issue #154): ogni parametro pesca dal proprio
        # stream derivato da (seed, rng_id, nome) — i draw di un parametro
        # non shiftano quelli degli altri (solo/mute e cache invarianti).
        # rng_id = stream_id, o rng_group se condiviso (issue #169);
        # owner_id resta lo stream_id (identità di log, non di derivazione).
        return Parameter(
            name=name,
            value=validated_value,
            bounds=bounds,
            mod_range=validated_range,
            owner_id=self.stream_id,
            distribution_mode=self.distribution_mode,
            range_anchor=self.range_anchor,
            rng=component_rng(self.seed, self.rng_id, name),
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
        err = InvalidParameterError(
            param_name=context_info,
            value=raw_data,
            hint="atteso numero, lista di punti, o dict envelope",
        )
        err.stream_id = self.stream_id
        raise err

    def _validated_anchor(self, anchor: str) -> str:
        """Valida `range_anchor` attribuendo l'errore allo stream."""
        try:
            return validate_range_anchor(anchor)
        except InvalidFieldValueError as err:
            err.stream_id = self.stream_id
            raise

    def _validate_band_ceiling(
        self,
        value: Optional[ParamInput],
        mod_range: Optional[ParamInput],
        bounds: Any,
        param_name: str,
    ) -> None:
        """Verifica che la banda `[base, base + range]` stia sotto max_val.

        Si applica SOLO con `range_anchor: min`. Sotto l'ancora `center` la
        banda arriva a `base + range/2` e resta gestita dal safety clamp a
        valle: e' il comportamento storico e non si tocca.

        Perche' al parse e non solo col clamp: la modalita' `min` promette una
        banda esatta. Se la banda non e' realizzabile, il clamp la schiaccia
        contro il tetto e produce un warning per grano — un sintomo rumoroso
        ma facile da non leggere, che lascia l'utente convinto di avere la
        banda che ha scritto. Meglio dirlo una volta, prima di renderizzare.

        Solo il tetto: il pavimento della banda e' `base`, gia' validato
        contro min_val da _validate_and_clip.

        Il controllo scatta solo quando il massimo della somma e' calcolabile
        da un solo lato:

            base scalare + range scalare   -> base + range
            base envelope + range scalare  -> max(base) + range
            base scalare + range envelope  -> base + max(range)

        Con entrambi envelope il massimo della somma non e' la somma dei
        massimi (i due picchi possono cadere in istanti diversi): il controllo
        sarebbe conservativo e un falso positivo bloccherebbe un render valido.
        In quel caso resta il safety clamp.

        Il picco di un envelope e' stimato dai suoi breakpoint. Con
        interpolazione cubica la curva puo' superare i breakpoint, quindi la
        stima puo' essere per difetto: il controllo puo' lasciar passare una
        banda che sfora di poco, mai bloccarne una valida. Il residuo lo
        prende il safety clamp — errore di sicurezza dalla parte giusta.
        """
        if self.range_anchor != ANCHOR_MIN:
            return
        if mod_range is None or bounds.max_val is None:
            return

        value_is_env = isinstance(value, Envelope)
        range_is_env = isinstance(mod_range, Envelope)
        if value_is_env and range_is_env:
            return

        peak_value = (max(y for _, y in value.breakpoints)
                      if value_is_env else float(value))
        peak_range = (max(y for _, y in mod_range.breakpoints)
                      if range_is_env else float(mod_range))
        ceiling = peak_value + peak_range

        if ceiling <= bounds.max_val:
            return

        err = ParameterBoundError(
            param_name=param_name,
            value_type='base + range (range_anchor: min)',
            value=ceiling,
            min_bound=bounds.min_val,
            max_bound=bounds.max_val,
        )
        err.stream_id = self.stream_id
        raise err

    def _validate_and_clip(
        self,
        param: Optional[ParamInput],
        min_bound: float,
        max_bound: Optional[float],
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
        from pge.shared.logger import log_config_warning, CLIP_LOG_CONFIG
        
        if param is None:
            return None

        validation_mode = CLIP_LOG_CONFIG.get('validation_mode', 'strict')
    
        # Caso 1: Numero scalare
        if isinstance(param, (int, float)):
            clean = float(param)
            clipped = max(min_bound, clean) if max_bound is None else max(min_bound, min(max_bound, clean))

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
                    err = ParameterBoundError(
                        param_name=param_name,
                        value_type=value_type,
                        value=clean,
                        min_bound=min_bound,
                        max_bound=max_bound,
                    )
                    err.stream_id = self.stream_id
                    raise err
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
                clipped_y = max(min_bound, y) if max_bound is None else max(min_bound, min(max_bound, y))

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
                    violations_list = []
                    for t, y in param.breakpoints:
                        clipped_y = max(min_bound, y) if max_bound is None else max(min_bound, min(max_bound, y))
                        if clipped_y != y:
                            violations_list.append((t, y))
                    err = ParameterBoundError(
                        param_name=param_name,
                        value_type=value_type,
                        violations=violations_list,
                        min_bound=min_bound,
                        max_bound=max_bound,
                    )
                    err.stream_id = self.stream_id
                    raise err
                else:
                    # Log ogni violazione
                    for t, y in param.breakpoints:
                        clipped_y = max(min_bound, y) if max_bound is None else max(min_bound, min(max_bound, y))
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
