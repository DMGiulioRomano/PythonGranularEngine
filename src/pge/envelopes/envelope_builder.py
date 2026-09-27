# envelope_builder.py
"""
Builder per parsing formati Envelope (legacy + nuovo formato compatto).

Design Pattern: Builder
- Separa logica di parsing da Envelope
- Gestisce nuovo formato: [[[x%, y], ...], end_time, n_reps, interp_type?]

MODIFICHE PRINCIPALI:
1. Formato compatto usa END_TIME (tempo assoluto finale) invece di total_time (durata)
2. Offset temporale automatico: la parte compatta parte dall'ultimo breakpoint precedente
3. Logging completo: sia della trasformazione compatta che dell'envelope finale
"""
from __future__ import annotations

from typing import List, Union, Tuple, Optional

from pge.shared.exceptions import InvalidFieldValueError


# I guard di forma (issue #211). Vivono qui e non nelle singole chiavi perche'
# non sanno niente del parametro che l'envelope descrive: dicono quanti punti
# servono a una zona, fin dove arriva un ciclo, come si scrive una
# distribuzione. Prima esistevano solo per `grain.read_direction`, e lo stesso
# corpo sotto qualunque altra chiave risaliva come ValueError nudo — fuori
# dalla gerarchia EngineError, senza campo e senza stream_id — o si rendeva in
# silenzio.
#
# Il campo non e' il loro: il builder non conosce il nome YAML della chiave che
# sta costruendo, e lo riceve da chi lo conosce (`field=`). Per questo gli hint
# nominano la sotto-posizione ("il terzo elemento del formato compatto"): il
# campo dice DOVE nel file, l'hint dice DOVE nell'envelope.

def _is_number(value) -> bool:
    """Numero vero: `bool` e' sottoclasse di `int`, ma `true` non e' `1`."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


_GROUP_ARITY_HINT = (
    "un BP group richiede almeno 2 punti: con meno non ha segmenti interni, "
    "quindi non c'e' nessuna zona a cui applicare l'interpolazione del gruppo. "
    "Un punto isolato si scrive come breakpoint nudo [t, v]."
)

_END_TIME_TYPE_HINT = (
    "il secondo elemento del formato compatto e' l'istante assoluto in cui il "
    "blocco finisce: un numero (`true` non e' `1`)."
)

_END_TIME_OFFSET_HINT = (
    "il secondo elemento del formato compatto e' l'istante assoluto in cui il "
    "blocco finisce, non la sua durata, e deve superare quello in cui comincia: "
    "qui {inizio}. Nella forma diretta il blocco comincia a 0; in una lista "
    "mista comincia dall'ultimo breakpoint scritto prima di lui."
)

_PATTERN_EMPTY_HINT = (
    "il primo elemento del formato compatto e' il pattern del ciclo, e non "
    "puo' essere vuoto: senza punti non c'e' niente da ripetere."
)

_PATTERN_POINT_HINT = (
    "un punto del pattern del formato compatto e' piatto: [x%, y] o "
    "[x%, y, type], con x un numero. Le macro-forme (BP group, formato "
    "compatto) non si annidano dentro un pattern."
)

_PATTERN_X_HINT = (
    "la prima coordinata di un punto del pattern e' una percentuale del ciclo "
    "e sta in [0, 100]. Fuori da li' il ciclo sfonda i propri confini: sopra "
    "100 il ciclo successivo comincia prima che questo sia finito, sotto 0 "
    "esce un breakpoint a tempo negativo."
)

_PATTERN_ORDER_HINT = (
    "le percentuali del pattern non possono tornare indietro: il ciclo si "
    "percorre in avanti una volta sola, e con tempi che si invertono "
    "l'envelope non rende il pattern scritto. Una percentuale ripetuta invece "
    "va bene: e' la discontinuita'."
)

_DIST_NAME_HINT = (
    "il quinto elemento del formato compatto e' la distribuzione temporale "
    "dei cicli, e ne esiste un elenco chiuso: {disponibili}. Si scrive come "
    "nome ('exponential') o come dict con i suoi parametri "
    "({{type: geometric, ratio: 1.5}}); omettendola i cicli durano uguale."
)

_DIST_PARAM_HINT = (
    "i parametri della distribuzione temporale '{nome}' non sono validi.{nota} "
    "I vincoli sui parametri di ciascuna distribuzione sono documentati con "
    "lei (docs/reference/yaml.md, distribuzioni temporali nei cicli)."
)

_DIST_TIPO_IMPLICITO = (
    " Senza la chiave `type` la distribuzione e' `linear`, che non prende "
    "parametri: se ne volevi un'altra, dichiarane il nome."
)

_ELEMENT_HINT = (
    "un elemento di un envelope e' un breakpoint [t, v] o [t, v, type] con t "
    "e v numeri (anche nella forma {t, v, type}), un BP group "
    "[[punti], interp] o un formato compatto [pattern, end_time, n_reps, ...]."
)

_REPS_HINT = (
    "il terzo elemento del formato compatto e' il numero di ripetizioni del "
    "pattern: un intero >= 1 (`true` non e' `1`). Con zero o meno cicli non "
    "c'e' nessun breakpoint da generare."
)


class EnvelopeBuilder:
    """
    Builder per creare liste di breakpoints da formati multipli.

    Supporta:
    - Compact format: [[[0, 0], [100, 1]], end_time, n_reps, interp?, time_dist?]
    - BP group (issue #64): [[[t, v], ...], interp] — macrozona di breakpoint
      con interp proprio, desugarata in 3-tuple [t, v, type]
    - Mixed formats in single list
    
    FORMATO COMPATTO ESTESO:
    [pattern_points, end_time, n_reps, interp_type?, time_dist_spec?]
    
    - pattern_points: Lista di [[x%, y], ...] con x in [0, 100]
    - end_time: Tempo assoluto finale (secondi)
    - n_reps: Numero di ripetizioni (int >= 1)
    - interp_type: 'linear' | 'cubic' | 'step' (opzionale, default='linear')
    - time_dist_spec: Specifica distribuzione temporale (opzionale, default='linear')
      - None o 'linear': distribuzione uniforme
      - 'exponential': accelerando (cicli sempre più brevi)
      - 'logarithmic': ritardando (cicli sempre più lunghi)
      - {'type': 'geometric', 'ratio': 1.5}: con parametri custom
      - {'type': 'power', 'exponent': 2.0}: power law
    
    OFFSET TEMPORALE AUTOMATICO:
    In formato misto, la parte compatta parte automaticamente dall'ultimo 
    breakpoint precedente. Il parametro end_time specifica il tempo assoluto 
    finale, e total_duration viene calcolato come (end_time - time_offset).
    
    Esempio formato misto:
        [[0, 10], [0.3, 10], [[[0, 30], [100, 50]], 1.3, 5, 'linear', 'exponential']]
        
        - Breakpoints standard fino a t=0.3
        - Parte compatta: end_time=1.3, quindi total_duration = 1.3 - 0.3 = 1.0
        - 5 ripetizioni con distribuzione exponential (accelerando)
        - Primo breakpoint compatto a t=0.300001 (con DISCONTINUITY_OFFSET)
    """
    
    # Offset infinitesimale per discontinuità
    DISCONTINUITY_OFFSET = 0.000001

    # Gli slot del formato compatto (issue #213). Non sono una comodità di
    # lettura: sono il punto unico in cui il layout della tupla esiste. Chi
    # espande (`_expand_compact_format`) e chi valida a monte
    # (`read_direction._check_compact`) decodificavano le stesse posizioni per
    # conto proprio, e il caso peggiore non era un errore ma un silenzio — un
    # `time_dist_spec` spostato di slot avrebbe lasciato il validatore a
    # controllare quello vecchio senza che nessun test se ne accorgesse.
    COMPACT_PATTERN = 0
    COMPACT_END_TIME = 1
    COMPACT_N_REPS = 2
    COMPACT_INTERP = 3
    COMPACT_TIME_DIST = 4
    COMPACT_WRAP = 5


    @classmethod
    def parse(cls, raw_points: list, field: Optional[str] = None) -> list:
        """
        Parsa lista mista di formati, espandendo formato compatto.
        
        Calcola automaticamente l'offset temporale per parti compatte in formato misto.
        
        Args:
            field: il nome YAML della chiave che l'envelope descrive
                (`density`, `grain.duration`, ...), cioe' il campo che ogni
                `InvalidFieldValueError` di forma nominera' (issue #211). Il
                builder non ha modo di saperlo da se': lo passa chi lo sa. Senza,
                l'errore nomina la sotto-posizione dentro l'envelope
                (`envelope.group.points`, `envelope.compact.n_reps`, ...).
            raw_points:
                - [[[x%, y], ...], end_time, n_reps, interp?] (formato compatto diretto)
                - [[[t, v], ...], interp] (BP group diretto, issue #64)
                - Lista con mix di:
                    * [time, value] (legacy)
                    * [time, value, type] (per-punto, issue #54)
                    * [[[x%, y], ...], end_time, n_reps, interp?] (compact wrapped)
                    * [[[t, v], ...], interp] (BP group, issue #64)

        Returns:
            Lista espansa con solo [time, value] / [time, value, type]
            
        Examples:
            # Formato compatto DIRETTO (caso più comune)
            >>> EnvelopeBuilder.parse([[[0, 0], [100, 1]], 0.4, 4])
            [[0.0, 0], [0.1, 1], [0.100001, 0], [0.2, 1], ...]
            
            # Formato MISTO con offset automatico
            >>> EnvelopeBuilder.parse([[0, 10], [0.3, 10], [[[0, 30], [100, 50]], 1.3, 5]])
            [[0, 10], [0.3, 10], [0.3, 30], [0.5, 50], [0.500001, 30], ...]
            
            # Legacy passa invariato
            >>> EnvelopeBuilder.parse([[0, 0], [1, 10], 'cycle'])
            [[0, 0], [1, 10], 'cycle']
        """
        # FIX 1: Controlla PRIMA se raw_points STESSO è un formato compatto
        if cls.is_compact_format(raw_points):
            # Formato compatto diretto: offset = 0
            expanded = cls._expand_compact_format(
                raw_points, time_offset=0.0, field=field)

            # Log risultato finale
            cls._log_final_envelope(raw_points, expanded)

            return expanded

        # BP group diretto [points, interp] (issue #64), simmetrico al compatto
        if cls.is_bp_group(raw_points):
            expanded = cls._expand_bp_group(raw_points, field=field)

            cls._log_final_envelope(raw_points, expanded)

            return expanded
        
        # Altrimenti, itera sugli elementi (formato legacy o misto)
        expanded = []
        current_time = 0.0  # Traccia tempo corrente per offset
        
        for item in raw_points:
            # L'elemento come scritto, per l'errore: il dict normalizzato qui
            # sotto non e' quello che l'utente ritrova nel file.
            scritto = item
            # Normalizza dict per-punto {t, v, type?} in lista
            if isinstance(item, dict) and 't' in item and 'v' in item:
                if 'type' in item:
                    item = [item['t'], item['v'], item['type']]
                else:
                    item = [item['t'], item['v']]
            if cls.is_compact_format(item):
                # Espandi formato compatto CON OFFSET
                compact_expanded = cls._expand_compact_format(
                    item, time_offset=current_time, field=field)
                expanded.extend(compact_expanded)

                # Aggiorna tempo corrente (ultimo breakpoint espanso)
                if compact_expanded:
                    current_time = compact_expanded[-1][0]
            elif cls.is_bp_group(item):
                # Espandi BP group [points, interp] in 3-tuple (issue #64)
                group_expanded = cls._expand_bp_group(
                    item, current_time=current_time,
                    has_preceding=bool(expanded), field=field,
                )
                expanded.extend(group_expanded)
                current_time = max(current_time, group_expanded[-1][0])
            else:
                if cls.is_3tuple_breakpoint(item):
                    expanded.append(item)
                    current_time = max(current_time, item[0])
                elif (isinstance(item, list) and len(item) == 2
                      and isinstance(item[0], (int, float)) and not isinstance(item[0], bool)
                      and isinstance(item[1], (int, float)) and not isinstance(item[1], bool)):
                    expanded.append(item)
                    current_time = max(current_time, item[0])
                else:
                    raise InvalidFieldValueError(
                        field=cls._field(field, "point"),
                        value=scritto,
                        hint=_ELEMENT_HINT,
                    )
        
        # Log risultato finale
        cls._log_final_envelope(raw_points, expanded)
        
        return expanded
    
    VALID_INTERP_TYPES = ('linear', 'cubic', 'step')

    @classmethod
    def is_3tuple_breakpoint(cls, item) -> bool:
        """
        Rileva se item è breakpoint 3-tuple [t, v, type].

        Discriminato da formato compatto (len==3 anche lì) tramite type(elem[0]):
        - 3-tuple breakpoint: elem[0] numerico
        - compact: elem[0] lista

        Returns:
            True se [t, v, type] con t,v numerici e type stringa valida.
        """
        if not isinstance(item, list) or len(item) != 3:
            return False
        if not isinstance(item[0], (int, float)) or isinstance(item[0], bool):
            return False
        if not isinstance(item[1], (int, float)) or isinstance(item[1], bool):
            return False
        if not isinstance(item[2], str):
            return False
        return True

    @classmethod
    def is_bp_group(cls, item) -> bool:
        """
        Rileva se item è un BP group [points, interp] (issue #64).

        BP group: lista a 2 elementi dove
        - item[0] è lista di punti [t, v] o [t, v, type] (tempi ASSOLUTI,
          come i breakpoint nudi — non percentuali come nei loop block)
        - item[1] è stringa: interp della macrozona

        Check strutturale (come is_3tuple_breakpoint): il valore di interp
        e il vincolo "almeno 2 punti" vengono validati in _expand_bp_group,
        per dare errori precisi. Discriminato da:
        - breakpoint [t, v]: elem[0] numerico, non lista
        - 3-tuple [t, v, type] e loop block: len != 2
        - legacy [[t, v], 'marker']: elem[0] è UN punto, non lista di punti

        Returns:
            True se è un BP group
        """
        if not isinstance(item, list) or len(item) != 2:
            return False

        points, interp = item

        if not isinstance(interp, str):
            return False

        if not isinstance(points, list):
            return False

        def _is_num(x):
            return isinstance(x, (int, float)) and not isinstance(x, bool)

        for p in points:
            if not isinstance(p, list) or len(p) not in (2, 3):
                return False
            if not _is_num(p[0]) or not _is_num(p[1]):
                return False
            if len(p) == 3 and not isinstance(p[2], str):
                return False

        return True

    @staticmethod
    def _field(field: Optional[str], posizione: str) -> str:
        """Il campo dell'errore: la chiave YAML se il chiamante l'ha passata,
        altrimenti la sotto-posizione dentro l'envelope, che e' tutto cio' che
        il builder sa da solo."""
        return field if field is not None else f"envelope.{posizione}"

    @classmethod
    def _expand_bp_group(cls, group: list, current_time: float = 0.0,
                         has_preceding: bool = False,
                         field: Optional[str] = None) -> list:
        """
        Espande un BP group [points, interp] in breakpoint 3-tuple.

        Desugar sull'infrastruttura per-punto (issue #54): ogni punto della
        zona tranne l'ultimo viene emesso come [t, v, interp], così il group
        interp governa i soli segmenti INTERNI (n punti → n-1 segmenti). Il
        segmento in uscita dall'ultimo punto resta al default globale, come
        i breakpoint nudi. Un punto 3-tuple dentro la zona fa override del
        group interp per il proprio segmento.

        Bordo zona: se il primo punto collide col breakpoint precedente
        (t <= current_time), viene spostato a current_time +
        DISCONTINUITY_OFFSET — stessa regola dei loop block.

        Args:
            group: [points, interp] con interp in VALID_INTERP_TYPES
            current_time: tempo dell'ultimo breakpoint precedente
            has_preceding: True se la zona segue altri breakpoint
            field: la chiave YAML da nominare negli errori (vedi `parse`)

        Returns:
            Lista di breakpoint [t, v] / [t, v, type]
        """
        points, interp = group

        if interp not in cls.VALID_INTERP_TYPES:
            raise InvalidFieldValueError(
                field=cls._field(field, "group.interp"),
                value=interp,
                hint=f"Tipi validi: {', '.join(cls.VALID_INTERP_TYPES)}",
            )

        if len(points) < 2:
            raise InvalidFieldValueError(
                field=cls._field(field, "group.points"),
                value=points,
                hint=_GROUP_ARITY_HINT,
            )

        expanded = []
        last_index = len(points) - 1
        for i, point in enumerate(points):
            t, v = point[0], point[1]
            own_type = point[2] if len(point) == 3 else None

            if i == 0 and has_preceding and t <= current_time:
                t = current_time + cls.DISCONTINUITY_OFFSET

            seg_type = own_type if own_type is not None else (
                interp if i < last_index else None
            )
            if seg_type is not None:
                expanded.append([t, v, seg_type])
            else:
                expanded.append([t, v])

        return expanded

    @classmethod
    def is_compact_format(cls, item) -> bool:
        """
        Rileva se item è formato compatto.
        
        Formato compatto: [pattern_points, end_time, n_reps, interp?, time_dist?, wrap?]
        - pattern_points è lista di liste [[x%, y], ...]
        - end_time è float/int (TEMPO ASSOLUTO FINALE, non durata)
        - n_reps è int
        - interp è str opzionale
        - time_dist è str/dict opzionale (distribuzione temporale)
        - wrap è bool opzionale (default False): se True, gap inter-ciclo
          interpola da v_finale a primo y del ciclo successivo (loop chiuso)

        Returns:
            True se è formato compatto
        """
        if not isinstance(item, list):
            return False

        # Deve avere 3, 4, 5 o 6 elementi
        if len(item) < 3:  # Minimo: [pattern_points, end_time, n_reps]
            return False

        if len(item) > 6:  # Massimo: [pattern_points, end_time, n_reps, interp, time_dist, wrap]
            return False

        # Primo elemento deve essere lista (anche se vuota)
        if not isinstance(item[0], list):
            return False

        # Se pattern NON vuoto, verifica formato [x, y] o [x, y, type]
        if item[0]:
            if not all(isinstance(p, list) and len(p) in (2, 3) for p in item[0]):
                return False

        # Secondo elemento: end_time (float/int)
        if not isinstance(item[1], (int, float)):
            return False

        # Terzo elemento: n_reps (int)
        if not isinstance(item[2], int):
            return False

        # Quarto elemento opzionale: interp_type (str)
        if len(item) >= 4 and item[3] is not None:
            if not isinstance(item[3], str):
                return False

        # Quinto elemento opzionale: time_dist_spec (str o dict)
        if len(item) >= 5 and item[4] is not None:
            if not isinstance(item[4], (str, dict)):
                return False

        # Sesto elemento opzionale: wrap (bool)
        if len(item) == 6 and item[5] is not None:
            # Nota: isinstance(True, int) e' True in Python, ma vogliamo solo bool puro
            if not isinstance(item[5], bool):
                return False

        return True
        
    @classmethod
    def _expand_compact_format(cls, compact: list, time_offset: float = 0.0,
                               field: Optional[str] = None) -> list:
        """
        Espande formato compatto in breakpoints assoluti con discontinuità.
        Usa TimeDistributionFactory per distribuire cicli nel tempo.
        
        NUOVA SEMANTICA:
        - Il secondo parametro è END_TIME (tempo assoluto finale)
        - total_duration viene calcolato come: end_time - time_offset
        - TimeDistributionStrategy calcola distribuzione cicli su total_duration
        
        Args:
            compact: [[[x%, y], ...], end_time, n_reps, interp?, time_dist?]
            time_offset: Tempo di inizio (da ultimo breakpoint precedente)
            field: la chiave YAML da nominare negli errori (vedi `parse`)
            
        Returns:
            Lista di breakpoints [t, v] con tempi strettamente crescenti
                        
        Examples:
            # Linear distribution (default)
            >>> cls._expand_compact_format([[[0, 0], [100, 1]], 0.4, 4], time_offset=0.0)
            [[0.0, 0], [0.1, 1], [0.100001, 0], [0.2, 1], ...]
            
            # Con offset + exponential distribution
            >>> cls._expand_compact_format(
            ...     [[[0, 30], [100, 50]], 1.3, 5, 'linear', 'exponential'], 
            ...     time_offset=0.3
            ... )
            [[0.3, 30], [0.45, 50], ...] # cicli accelerano
        """
        # Parse input
        # Precondizione: `compact` ha gia' passato `is_compact_format`, che
        # ammette da 3 a 6 elementi. I tre `len(compact) > SLOT` qui sotto
        # distinguono quindi solo gli slot opzionali assenti — non c'e' un
        # settimo slot da cui difendersi, e `COMPACT_WRAP` e' l'ultimo per
        # costruzione: e' quel limite superiore a rendere questi test
        # esaustivi invece che parziali.
        pattern_points_pct = compact[cls.COMPACT_PATTERN]
        end_time = compact[cls.COMPACT_END_TIME]  # Tempo assoluto finale
        n_reps = compact[cls.COMPACT_N_REPS]
        interp_type = (compact[cls.COMPACT_INTERP]
                       if len(compact) > cls.COMPACT_INTERP else None)
        time_dist_spec = (compact[cls.COMPACT_TIME_DIST]
                          if len(compact) > cls.COMPACT_TIME_DIST else None)
        wrap = (compact[cls.COMPACT_WRAP]
                if len(compact) > cls.COMPACT_WRAP else False)
        if wrap is None:
            wrap = False
        
        # Valida
        # Il `bool` va escluso a mano: `is_compact_format` lo lascia passare
        # per sottoclasse di `int`, e `True < 1` e' falso — senza questo
        # `range(True)` rende un ciclo in silenzio.
        if not _is_number(n_reps) or n_reps < 1:
            raise InvalidFieldValueError(
                field=cls._field(field, "compact.n_reps"),
                value=n_reps,
                hint=_REPS_HINT,
            )
        
        # Il segno non ha un guard a parte: l'offset non e' mai negativo, quindi
        # `end_time <= 0` e' gia' `end_time <= time_offset`.
        if not _is_number(end_time):
            raise InvalidFieldValueError(
                field=cls._field(field, "compact.end_time"),
                value=end_time,
                hint=_END_TIME_TYPE_HINT,
            )
        if end_time <= time_offset:
            raise InvalidFieldValueError(
                field=cls._field(field, "compact.end_time"),
                value=end_time,
                hint=_END_TIME_OFFSET_HINT.format(inizio=time_offset),
            )
        
        if not pattern_points_pct:
            raise InvalidFieldValueError(
                field=cls._field(field, "compact.pattern"),
                value=pattern_points_pct,
                hint=_PATTERN_EMPTY_HINT,
            )
        precedente = None
        for point in pattern_points_pct:
            cls._check_pattern_point(point, precedente, field)
            precedente = point[0]
        
        # CALCOLA durata totale dall'offset
        total_duration = end_time - time_offset
        
        # CREA strategia di distribuzione temporale
        distributor = cls._time_distribution(time_dist_spec, field)
        
        # OTTIENI distribuzione cicli (tempi relativi a time_offset=0)
        relative_cycle_starts, cycle_durations = distributor.calculate_distribution(
            total_duration, 
            n_reps
        )
        
        # Espandi breakpoints usando la distribuzione
        expanded = []
        
        for rep in range(n_reps):
            # Tempo inizio ciclo: offset + start relativo
            cycle_start_time = time_offset + relative_cycle_starts[rep]
            cycle_duration = cycle_durations[rep]
                        
            # Converti coordinate % → assolute per questo ciclo
            for i, point in enumerate(pattern_points_pct):
                x_pct, y = point[0], point[1]
                seg_type = point[2] if len(point) == 3 else None
                # x_pct è in [0, 100]
                # Normalizza a [0, 1]
                x_normalized = x_pct / 100.0

                # Calcola tempo assoluto
                t_absolute = cycle_start_time + (x_normalized * cycle_duration)

                # Applica offset DISCONTINUITY per evitare collisioni:
                # 1. Primo punto di cicli successivi (rep > 0)
                # 2. Primo punto assoluto della parte compatta SE c'è time_offset
                if (rep > 0 and i == 0) or (rep == 0 and i == 0 and time_offset > 0):
                    t_absolute += cls.DISCONTINUITY_OFFSET

                if seg_type is not None:
                    expanded.append([t_absolute, y, seg_type])
                else:
                    expanded.append([t_absolute, y])

        # WRAP MODE: inietta breakpoint sintetici a fine ogni ciclo
        # con y = first_y del pattern (loop chiuso). Skip se ultimo punto
        # pattern coincide con fine ciclo (x_pct == 100, nessun gap).
        if wrap:
            last_x_pct = pattern_points_pct[-1][0]
            if last_x_pct < 100:
                first_y = pattern_points_pct[0][1]
                for rep in range(n_reps):
                    cycle_start = time_offset + relative_cycle_starts[rep]
                    cycle_end = cycle_start + cycle_durations[rep]
                    synthetic_t = cycle_end - cls.DISCONTINUITY_OFFSET
                    expanded.append([synthetic_t, first_y])
                expanded.sort(key=lambda p: p[0])

        # LOGGING della trasformazione compatta
        cls._log_compact_transformation(
            compact, expanded, time_offset, total_duration, distributor
        )

        return expanded


    @classmethod
    def _time_distribution(cls, spec, field: Optional[str]):
        """La distribuzione temporale del ciclo, o l'errore che nomina il campo.

        Due passaggi, per due ragioni diverse:

        1. **Il nome si legge dal registro.** E' la stessa lista che il factory
           consulta, e leggerla qui evita che `{type: 5}` arrivi a `.lower()` e
           risalga come AttributeError — e che `{type: null}`, che il factory
           non sa leggere, faccia lo stesso. In cambio l'hint elenca i nomi
           validi, che e' l'errore piu' frequente.
        2. **I parametri li valida il costruttore**, costruendo. Sono vincoli
           delle singole distribuzioni e replicarli qui sarebbe codice
           destinato a divergere.

        Il catch e' stretto a ValueError/TypeError — i due modi in cui il
        registro dice "questo dato non va", `EngineError` compresi (ereditano
        ValueError): un `ParameterBoundError` nomina `rate`, un
        `InvalidFieldValueError` nomina `power.exponent`, e nessuna delle due e'
        una chiave dello YAML. `MemoryError` e ogni guasto che non parla dello
        YAML restano visibili per quello che sono. L'hint non riversa
        `str(exc)`: una parte di quelle stringhe la genera CPython
        (`... got an unexpected keyword argument`), quindi cambia fra versioni,
        e PGE-ls i messaggi li parsa. La causa resta nel `__cause__`.
        """
        from pge.envelopes.time_distribution import TimeDistributionFactory

        if spec is None:
            return TimeDistributionFactory.create(None)

        disponibili = TimeDistributionFactory.list_available()
        nome = spec.get('type', 'linear') if isinstance(spec, dict) else spec
        if not isinstance(nome, str) or nome.lower() not in disponibili:
            raise InvalidFieldValueError(
                field=cls._field(field, "compact.time_dist"),
                value=spec,
                hint=_DIST_NAME_HINT.format(disponibili=', '.join(disponibili)),
            )

        try:
            return TimeDistributionFactory.create(spec)
        except (ValueError, TypeError) as exc:
            senza_tipo = isinstance(spec, dict) and 'type' not in spec
            raise InvalidFieldValueError(
                field=cls._field(field, "compact.time_dist"),
                value=spec,
                hint=_DIST_PARAM_HINT.format(
                    nome=nome,
                    nota=_DIST_TIPO_IMPLICITO if senza_tipo else '',
                ),
            ) from exc

    @classmethod
    def _check_pattern_point(cls, point: list, precedente,
                             field: Optional[str]) -> None:
        """Un punto del pattern: piatto, con la x in `[0, 100]` e non indietro.

        La forma del punto `is_compact_format` la guarda solo in lunghezza (2 o
        3), e un BP group e' lungo 2: senza il primo guard ci si infila, e
        l'espansione fa `x_pct / 100.0` su una lista.

        Args:
            point: il punto da controllare.
            precedente: la x del punto che lo precede, o `None` se e' il primo.
                Una x ripetuta e' ammessa: e' la discontinuita'.
            field: la chiave YAML da nominare negli errori (vedi `parse`).
        """
        x = point[0]
        if not _is_number(x):
            raise InvalidFieldValueError(
                field=cls._field(field, "compact.pattern"),
                value=point,
                hint=_PATTERN_POINT_HINT,
            )
        if not 0 <= x <= 100:
            raise InvalidFieldValueError(
                field=cls._field(field, "compact.pattern"),
                value=x,
                hint=_PATTERN_X_HINT,
            )
        if precedente is not None and x < precedente:
            raise InvalidFieldValueError(
                field=cls._field(field, "compact.pattern"),
                value=x,
                hint=_PATTERN_ORDER_HINT,
            )

    @classmethod
    def _log_compact_transformation(
        cls, 
        compact: list, 
        expanded: list,
        time_offset: float,
        total_duration: float,
        distributor = None
    ):
        """
        Logga la trasformazione da formato compatto a espanso.
        
        Args:
            compact: Formato originale [[[x%, y], ...], end_time, n_reps, interp?, time_dist?]
            expanded: Lista espansa di breakpoints [[t, v], ...]
            time_offset: Offset temporale di inizio
            total_duration: Durata totale calcolata (end_time - time_offset)
            distributor: TimeDistributionStrategy usata (opzionale)
        """
        # Importa logger locale per evitare circular imports
        from pge.shared.logger import get_clip_logger, CLIP_LOG_CONFIG
        
        if not CLIP_LOG_CONFIG.get('log_transformations', True):
            return

        logger = get_clip_logger()
        if logger is None:
            return
        
        # Parse compact format
        pattern_points_pct = compact[0]
        end_time = compact[1]
        n_reps = compact[2]
        interp_type = compact[3] if len(compact) >= 4 else 'linear'
        time_dist_spec = compact[4] if len(compact) == 5 else None
        
        # Conta breakpoints espansi
        n_breakpoints = len(expanded)
        
        # Log header
        logger.info(
            f"\n{'='*80}\n"
            f"COMPACT ENVELOPE TRANSFORMATION\n"
            f"{'='*80}"
        )
        
        # Log formato compatto INPUT
        logger.info(f"\n[INPUT] Compact format:")
        logger.info(f"  Pattern points: {pattern_points_pct}")
        logger.info(f"  End time: {end_time}s (absolute)")
        logger.info(f"  Time offset: {time_offset}s (from previous breakpoints)")
        logger.info(f"  Total duration: {total_duration}s (end_time - offset)")
        logger.info(f"  Repetitions: {n_reps}")
        if interp_type:
            logger.info(f"  Interpolation: {interp_type}")
        if time_dist_spec:
            logger.info(f"  Time distribution spec: {time_dist_spec}")
        if distributor:
            logger.info(f"  Distribution strategy: {distributor.name}")
        
        # Log distribuzione cicli
        if distributor and n_reps > 1:
            # Ricalcola per logging (già fatto in expand ma va bene)
            relative_starts, durations = distributor.calculate_distribution(
                total_duration, n_reps
            )
            logger.info(f"\n[CYCLE DISTRIBUTION]:")
            for i in range(min(n_reps, 10)):  # Mostra max 10 cicli
                abs_start = time_offset + relative_starts[i]
                abs_end = abs_start + durations[i]
                logger.info(
                    f"  Cycle {i}: {abs_start:.6f}s - {abs_end:.6f}s "
                    f"(duration: {durations[i]:.6f}s)"
                )
            if n_reps > 10:
                logger.info(f"  ... ({n_reps - 10} more cycles)")
        
        # Log risultato espanso OUTPUT
        logger.info(f"\n[OUTPUT] Expanded format:")
        logger.info(f"  Total breakpoints: {n_breakpoints}")
        logger.info(f"  Time range: {expanded[0][0]:.6f}s → {expanded[-1][0]:.6f}s")
        
        # Log primi e ultimi breakpoints per verifica
        preview_count = min(5, len(expanded))
        logger.info(f"\n  First {preview_count} breakpoints:")
        for i in range(preview_count):
            bp = expanded[i]
            t, v = bp[0], bp[1]
            extra = f", type={bp[2]}" if len(bp) == 3 else ""
            logger.info(f"    [{i}] t={t:.6f}s, v={v}{extra}")

        if len(expanded) > preview_count:
            logger.info(f"  ...")
            logger.info(f"  Last {preview_count} breakpoints:")
            for i in range(len(expanded) - preview_count, len(expanded)):
                bp = expanded[i]
                t, v = bp[0], bp[1]
                extra = f", type={bp[2]}" if len(bp) == 3 else ""
                logger.info(f"    [{i}] t={t:.6f}s, v={v}{extra}")
        
        logger.info(f"{'='*80}\n")

    

    @classmethod
    def _log_final_envelope(cls, raw_input: list, expanded: list):
        """
        Logga l'envelope completo finale (DOPO parsing di tutti i formati).
        
        Mostra la differenza tra input originale e output finale espanso.
        
        Args:
            raw_input: Input originale (può essere misto, compatto, legacy)
            expanded: Lista finale espansa di breakpoints
        """
        from pge.shared.logger import get_clip_logger, CLIP_LOG_CONFIG

        if not CLIP_LOG_CONFIG.get('log_transformations', True):
            return

        logger = get_clip_logger()
        if logger is None:
            return
        
        # Conta quanti elementi sono compatti vs BP group vs standard
        n_compact = 0
        n_group = 0
        n_standard = 0

        if cls.is_compact_format(raw_input):
            n_compact = 1
        elif cls.is_bp_group(raw_input):
            n_group = 1
        else:
            for item in raw_input:
                if cls.is_compact_format(item):
                    n_compact += 1
                elif cls.is_bp_group(item):
                    n_group += 1
                elif isinstance(item, list) and len(item) == 2:
                    n_standard += 1

        # Log header
        logger.info(
            f"\n{'='*80}\n"
            f"FINAL ENVELOPE (after parsing)\n"
            f"{'='*80}"
        )

        # Log statistiche input
        logger.info(f"\n[INPUT SUMMARY]:")
        logger.info(f"  Standard breakpoints: {n_standard}")
        logger.info(f"  Compact sections: {n_compact}")
        logger.info(f"  BP groups: {n_group}")
        if cls.is_compact_format(raw_input):
            format_type = 'compact'
        elif cls.is_bp_group(raw_input):
            format_type = 'bp_group'
        elif n_compact > 0 or n_group > 0:
            format_type = 'mixed'
        else:
            format_type = 'standard'
        logger.info(f"  Format type: {format_type}")
        
        # Log output finale
        logger.info(f"\n[FINAL OUTPUT]:")
        logger.info(f"  Total breakpoints: {len(expanded)}")
        
        if expanded:
            logger.info(f"  Time range: {expanded[0][0]:.6f}s → {expanded[-1][0]:.6f}s")
            
            # Mostra TUTTI i breakpoints se sono pochi, altrimenti preview
            if len(expanded) <= 20:
                logger.info(f"\n  All {len(expanded)} breakpoints:")
                for i, bp in enumerate(expanded):
                    if isinstance(bp, list) and len(bp) == 2:
                        t, v = bp
                        logger.info(f"    [{i}] t={t:.6f}s, v={v}")
                    else:
                        logger.info(f"    [{i}] {bp}")  # 'cycle' marker
            else:
                # Preview primi e ultimi
                preview_count = 10
                logger.info(f"\n  First {preview_count} breakpoints:")
                for i in range(preview_count):
                    if isinstance(expanded[i], list) and len(expanded[i]) == 2:
                        t, v = expanded[i]
                        logger.info(f"    [{i}] t={t:.6f}s, v={v}")
                    else:
                        logger.info(f"    [{i}] {expanded[i]}")
                
                logger.info(f"  ...")
                logger.info(f"  Last {preview_count} breakpoints:")
                for i in range(len(expanded) - preview_count, len(expanded)):
                    if isinstance(expanded[i], list) and len(expanded[i]) == 2:
                        t, v = expanded[i]
                        logger.info(f"    [{i}] t={t:.6f}s, v={v}")
                    else:
                        logger.info(f"    [{i}] {expanded[i]}")
        
        logger.info(f"{'='*80}\n")


    @classmethod
    def extract_interp_type(cls, raw_points: list) -> Optional[str]:
        """
        Estrae tipo interpolazione da formato compatto (se presente).
        
        Se ci sono più formati compatti con tipi diversi, usa il primo.
        
        Args:
            raw_points: Lista con possibili formati compatti
            
        Returns:
            str or None: Tipo interpolazione ('linear', 'cubic', 'step')
        """
        # FIX 2: Controlla PRIMA se raw_points STESSO è formato compatto con tipo
        if cls.is_compact_format(raw_points):
            # Lo slot dell'interp e' quello nominato (issue #213): scritto a
            # mano, un giorno che cambiasse posizione questa funzione tornerebbe
            # None invece del tipo dichiarato — non un errore, un envelope
            # interpolato col default.
            if (len(raw_points) > cls.COMPACT_INTERP
                    and raw_points[cls.COMPACT_INTERP] is not None):
                return raw_points[cls.COMPACT_INTERP]
            return None

        # Altrimenti itera sugli elementi (formato misto)
        for item in raw_points:
            if cls.is_compact_format(item):
                if (len(item) > cls.COMPACT_INTERP
                        and item[cls.COMPACT_INTERP] is not None):
                    return item[cls.COMPACT_INTERP]

        return None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def detect_format_type(item) -> str:
    """
    Helper per debugging: rileva tipo di formato.

    Returns:
        'compact' | 'bp_group' | 'breakpoint' | 'cycle' | 'unknown'
    """
    if isinstance(item, str) and item.lower() == 'cycle':
        return 'cycle'

    if EnvelopeBuilder.is_compact_format(item):
        return 'compact'

    if EnvelopeBuilder.is_bp_group(item):
        return 'bp_group'

    if isinstance(item, list) and len(item) == 2:
        return 'breakpoint'

    return 'unknown'
