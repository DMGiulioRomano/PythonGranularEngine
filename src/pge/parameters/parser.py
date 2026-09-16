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
from pge.parameters.parameter_definitions import (
    RANGE_UNIT_DEFAULT,
    get_parameter_definition,
    range_unit_is_relative,
    relative_band_width,
    relative_range_bounds,
    validate_range_unit,
)
from pge.shared.distribution_strategy import (
    ANCHOR_CENTER,
    ANCHOR_MIN,
    validate_range_anchor,
)
from pge.shared.exceptions import (
    ConfigError,
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
        bounds_override: Any = None,
        range_unit: Any = None,
    ) -> Parameter:
        """
        Metodo Factory principale. Crea un oggetto Parameter pronto all'uso.

        Args:
            name: Nome del parametro (deve esistere in parameter_definitions.py).
            value_raw: Valore base dal YAML (numero, lista breakpoints, dict envelope).
            range_raw: Valore range/randomness dal YAML (opzionale).
            prob_raw: Valore probabilità/deviation_probability dal YAML (opzionale).
            bounds_override: ParameterBounds espliciti. Se forniti, bypassano il
                Registry — usati per parametri con bounds dinamici (es. pitch,
                i cui bounds derivano dall'unità di misura, non dal nome).
            range_unit: unità del `_range` dichiarato (issue #267): 'absolute'
                (default, la larghezza è il numero scritto) o 'relative' (il
                numero è una frazione del valore base). None → default.

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

        # 1-bis. Unita' del range (issue #267). La sostituzione del dominio si
        # applica DOPO i bounds, override compreso: e' un fatto della modalita',
        # non del parametro, e vale su qualunque provenienza dei bounds.
        unit = self._validated_range_unit(range_unit)
        is_relative = range_unit_is_relative(unit)
        if is_relative:
            bounds = relative_range_bounds(bounds)

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
        self._validate_band_ceiling(validated_value, validated_range, bounds, name,
                                    is_relative=is_relative)

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
            range_relative=is_relative,
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
            # La costruzione dell'envelope ha errori suoi (bounds del formato
            # compatto, overflow delle potenze): nascono dove lo stream non si
            # conosce, e vanno attribuiti qui come ogni altro errore del parser.
            try:
                return create_scaled_envelope(
                    raw_data, self.duration, self.time_mode
                )
            except ConfigError as err:
                err.stream_id = self.stream_id
                raise
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

    def _validated_range_unit(self, unit: Any) -> str:
        """Valida l'unita' del range attribuendo l'errore allo stream.

        `None` significa "unita' non dichiarata" e vale il default assoluto: e'
        il caso di ogni parametro che l'unita' non la prevede nemmeno, quindi
        qui non puo' essere un errore. Qui il parser riceve un *valore*, non
        una chiave, e non ha modo di distinguere una chiave assente da una
        scritta e lasciata vuota: quella distinzione la fa
        `ParameterOrchestrator._range_unit_from_spec`, che lo YAML lo legge, e
        una chiave vuota la rifiuta prima di arrivare fin qui.

        Il chiamante ordinario (ParameterOrchestrator) valida gia' la grafia
        col path YAML della chiave, e li' l'errore la nomina per esteso. Questo
        e' il presidio del parser per chi lo usa direttamente: gemello di
        _validated_anchor, e per la stessa ragione — qui si conosce lo
        stream_id, che il modulo dei bounds non conosce.
        """
        if unit is None:
            return RANGE_UNIT_DEFAULT
        try:
            return validate_range_unit(unit)
        except InvalidFieldValueError as err:
            err.stream_id = self.stream_id
            raise

    def _validate_band_ceiling(
        self,
        value: Optional[ParamInput],
        mod_range: Optional[ParamInput],
        bounds: Any,
        param_name: str,
        is_relative: bool = False,
    ) -> None:
        """Verifica che il tetto della banda stia sotto max_val.

        Il tetto dipende dall'unita' del range (issue #267): `base + range`
        quando il range e' assoluto, `base + range * |base|` quando e' una
        frazione. Sommare una frazione a una durata sommerebbe due grandezze
        diverse, e il controllo lascerebbe passare in silenzio proprio le bande
        larghe — con `base: 8` e frazione `0.5` la somma da' 8.5, la banda
        arriva a 12.

        La larghezza della banda relativa non si riscrive qui: la misura
        `relative_band_width`, la stessa funzione che `Parameter` chiama a ogni
        grano. Il tetto al parse e la banda a runtime sono due letture della
        stessa banda, e devono coincidere per costruzione — scritte
        separatamente divergevano gia' su una base negativa.

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

        Il controllo scatta solo quando il massimo e' calcolabile da un solo
        lato:

            base scalare + range scalare   -> base, range
            base envelope + range scalare  -> ogni base, range
            base scalare + range envelope  -> base, max(range)

        Con entrambi envelope il massimo della combinazione non e' la
        combinazione dei massimi (i due picchi possono cadere in istanti
        diversi): il controllo sarebbe conservativo e un falso positivo
        bloccherebbe un render valido. In quel caso resta il safety clamp.
        Vale per la somma come per il prodotto.

        Sulla base si valuta ogni breakpoint e non il solo massimo: la banda
        relativa e' monotona nella base solo finche' la frazione sta sotto 1,
        e farne un'assunzione legherebbe questo controllo al tetto di
        RELATIVE_RANGE_BOUNDS senza dirlo (vedi il commento al calcolo).

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

        # La combinazione e' monotona nel RANGE — la larghezza non e' mai
        # negativa (min_range >= 0) e cresce con la frazione — quindi il suo
        # picco basta. Nella BASE no, e assumerlo era una dipendenza
        # nascosta: sotto zero la banda relativa vale `base * (1 - r)`, che
        # cresce con la base solo finche' `r <= 1` e decresce appena `r` lo
        # supera. Reggeva percio' su RELATIVE_RANGE_BOUNDS[1] <= 1 — un
        # dominio che nessuno dichiara load-bearing e che allargare sarebbe
        # retrocompatibile ovunque tranne qui. Valutare la banda su OGNI base
        # candidata invece che sul solo picco toglie l'assunzione: costa un
        # max su breakpoint gia' letti, e il tetto resta quello di prima dove
        # la base e' positiva, cioe' sull'unico parametro cablato oggi.
        base_candidates = ([y for _, y in value.breakpoints]
                           if value_is_env else [float(value)])
        peak_range = (max(y for _, y in mod_range.breakpoints)
                      if range_is_env else float(mod_range))
        ceiling = max(
            base + (relative_band_width(peak_range, base)
                    if is_relative else peak_range)
            for base in base_candidates
        )

        if ceiling <= bounds.max_val:
            return

        formula = ('base + range * |base|' if is_relative else 'base + range')
        err = ParameterBoundError(
            param_name=param_name,
            value_type=f'{formula} (range_anchor: min)',
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
