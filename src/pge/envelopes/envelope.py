# envelope.py - versione semplificata
"""
Envelope system with Composite Pattern.

Supports:
- Standard breakpoints: [[t, v], ...] e per-punto [[t, v, type], ...]
- Compact format: [[[x%, y], ...], total_time, n_reps, interp?]
- BP group (issue #64): [[[t, v], ...], interp] — macrozona con interp proprio
- Dict format: {'type': 'cubic', 'points': [...]}
"""
from __future__ import annotations

from typing import Union, List, Dict, Any
from pge.envelopes.envelope_factory import InterpolationStrategyFactory
from pge.envelopes.envelope_segment import NormalSegment, Segment
from pge.envelopes.envelope_interpolation import InterpolationStrategy

class Envelope:
    """
    Envelope temporale con supporto formato compatto.
    
    Supporta interpolazione lineare, cubica e step.
    Supporta nuovo formato compatto per cicli ripetuti.
    """
    
    def __init__(self, breakpoints):
        """
        Args:
            breakpoints:
                - Lista di [time, value] / [time, value, type]
                - Nuovo formato compatto: [[[x%, y], ...], total_time, n_reps, interp?]
                - BP group (issue #64): [[[t, v], ...], interp]
                - Dict con 'type' e 'points'

        Examples:
            # Standard breakpoints
            Envelope([[0, 0], [0.5, 1], [1.0, 0]])

            # Nuovo formato compatto: 4 ripetizioni in 0.4s
            Envelope([[[0, 0], [100, 1]], 0.4, 4])

            # BP group: macrozona step, poi gap linear verso [1, 0]
            Envelope([
                [[[0, 0], [0.5, 1]], 'step'],   # zona con interp proprio
                [1.0, 0]
            ])
            
            # Formato misto
            Envelope([
                [[[0, 0], [100, 1]], 0.4, 4],  # Compatto
                [0.5, 0.5],                     # Standard
                [1.0, 0]                        # Standard
            ])
            
            # Con tipo esplicito nel dict
            Envelope({
                'type': 'cubic',
                'points': [[[0, 0], [50, 0.5], [100, 1]], 0.2, 2]
            })
        """
        # Import qui per evitare circular import
        from pge.envelopes.envelope_builder import EnvelopeBuilder
        
        # Parse type e raw_points
        if isinstance(breakpoints, dict):
            self.type = breakpoints.get('type', 'linear')
            raw_points = breakpoints['points']
        elif isinstance(breakpoints, list):
            # Controlla se c'è tipo in formato compatto
            extracted_type = EnvelopeBuilder.extract_interp_type(breakpoints)
            self.type = extracted_type or 'linear'
            raw_points = breakpoints
        else:
            raise ValueError(f"Formato envelope non valido: {breakpoints}")
        
        # ESPANDI formato compatto usando Builder
        expanded_points = EnvelopeBuilder.parse(raw_points)
        
        # Crea strategy usando Factory
        self.strategy = InterpolationStrategyFactory.create(self.type)
        
        # Parse segmenti → List[NormalSegment]
        self.segments = self._parse_segments(expanded_points)
        
        # Valida
        if not self.segments:
            raise ValueError("Envelope deve contenere almeno un breakpoint.")
    
    def _parse_segments(self, breakpoints: list) -> List[Segment]:
        """
        Parsa lista di breakpoints in List[NormalSegment].

        Accetta breakpoint 2-elem [t, v] (usa strategy globale) o 3-elem
        [t, v, type] (override per-segmento, type applicato a seg i→i+1).

        Quando non ci sono override per-punto crea un singolo segmento
        (backward compat). Altrimenti crea N segmenti (uno per coppia).

        Returns:
            List[NormalSegment]
        """
        if not breakpoints:
            raise ValueError("Lista breakpoints vuota.")

        from pge.envelopes.envelope_builder import EnvelopeBuilder as _EB

        # Estrai (point_2elem, seg_type) per ogni breakpoint
        points = []
        seg_types: List[Any] = []
        has_per_point_type = False
        for item in breakpoints:
            if not isinstance(item, list):
                raise ValueError(
                    f"Formato breakpoint non valido: {item}. "
                    "Deve essere [time, value] o [time, value, type]."
                )
            if len(item) == 2:
                points.append(item)
                seg_types.append(None)
            elif len(item) == 3:
                if not _EB._is_3tuple_breakpoint(item):
                    raise ValueError(
                        f"Formato breakpoint non valido: {item}. "
                        "Deve essere [time, value] o [time, value, type]."
                    )
                if item[2] not in _EB.VALID_INTERP_TYPES:
                    from pge.shared.exceptions import InvalidFieldValueError
                    raise InvalidFieldValueError(
                        field="envelope.point.type",
                        value=item[2],
                        hint=f"Tipi validi: {', '.join(_EB.VALID_INTERP_TYPES)}",
                    )
                points.append([item[0], item[1]])
                seg_types.append(item[2])
                has_per_point_type = True
            else:
                raise ValueError(
                    f"Formato breakpoint non valido: {item}. "
                    "Deve essere [time, value] o [time, value, type]."
                )

        # Tangenti globali (usate solo dai segmenti cubic)
        global_tangents = self._compute_fritsch_carlson_tangents(points)

        # Backward compat: nessun override → singolo segmento
        if not has_per_point_type:
            context = self._create_context_for_segment(points)
            return [NormalSegment(breakpoints=points, strategy=self.strategy, context=context)]

        # N segmenti: uno per coppia (points[i], points[i+1])
        # seg_types[i] applicato a segmento i→i+1; ultimo type ignorato (warning)
        if seg_types[-1] is not None:
            import logging
            logging.getLogger(__name__).warning(
                f"Envelope: type='{seg_types[-1]}' su ultimo punto ignorato (no segmento successivo)."
            )

        if len(points) == 1:
            # Caso degenere: 1 solo punto
            context = self._create_context_for_segment(points)
            return [NormalSegment(breakpoints=points, strategy=self.strategy, context=context)]

        segments: List[Segment] = []
        for i in range(len(points) - 1):
            pair = [points[i], points[i + 1]]
            t_for_seg = seg_types[i] if seg_types[i] is not None else self.type
            strategy = InterpolationStrategyFactory.create(t_for_seg)
            context: Dict[str, Any] = {}
            if t_for_seg == 'cubic':
                context['tangents'] = [global_tangents[i], global_tangents[i + 1]]
            segments.append(NormalSegment(breakpoints=pair, strategy=strategy, context=context))

        return segments
    
    def _create_context_for_segment(self, points: List[List[float]]) -> Dict[str, Any]:
        """
        Crea context dict per il segmento (es. tangenti per cubic).
        
        Args:
            points: Breakpoints del segmento
            
        Returns:
            Dict con context (es. {'tangents': [...]})
        """
        context = {}
        
        # Per cubic, calcola tangenti con Fritsch-Carlson
        if self.type == 'cubic':
            tangents = self._compute_fritsch_carlson_tangents(points)
            context['tangents'] = tangents
        
        return context
    
    def _compute_fritsch_carlson_tangents(self, points: List[List[float]]) -> List[float]:
        """
        Calcola tangenti usando algoritmo Fritsch-Carlson.
        
        Previene overshooting mantenendo monotonia.
        """
        n = len(points)
        if n < 2:
            return [0.0] * n

        # Caso 2 punti: l'unica informazione è la slope del segmento, e
        # assegnarla a entrambe le tangenti degenererebbe in una retta.
        # Forzando le tangenti a zero l'Hermite diventa lo smoothstep
        # simmetrico v0+(v1-v0)(3s^2-2s^3): ease-in-out visibile, monotòno,
        # senza overshoot. Per la retta resta disponibile type: linear.
        if n == 2:
            return [0.0, 0.0]

        tangents = [0.0] * n
        
        # Pendenze dei segmenti
        deltas = []
        for i in range(n - 1):
            t0, v0 = points[i]
            t1, v1 = points[i + 1]
            if t1 > t0:
                delta = (v1 - v0) / (t1 - t0)
            else:
                delta = 0.0
            deltas.append(delta)
        
        # Tangente iniziale
        tangents[0] = deltas[0]
        
        # Tangenti interne: media pesata con monotonia
        for i in range(1, n - 1):
            d_left = deltas[i - 1]
            d_right = deltas[i]
            
            # Se segni diversi → tangente zero (punto critico)
            if d_left * d_right <= 0:
                tangents[i] = 0.0
            else:
                # Media armonica ponderata (Fritsch-Carlson)
                tangents[i] = 2.0 / (1.0 / d_left + 1.0 / d_right)
        
        # Tangente finale
        tangents[n - 1] = deltas[n - 2]
        
        return tangents
    
    def evaluate(self, t: float) -> float:
        """
        Valuta l'envelope al tempo t.

        Multi-segmento: trova il segmento che contiene t (o restituisce hold
        agli estremi globali).
        """
        if len(self.segments) == 1:
            return self.segments[0].evaluate(t)

        # Hold pre/post sugli estremi globali
        global_start = self.segments[0].start_time
        global_end = self.segments[-1].end_time
        if t <= global_start:
            return self.segments[0].breakpoints[0][1]
        if t >= global_end:
            return self.segments[-1].breakpoints[-1][1]

        # Trova segmento contenente t (segmenti adiacenti condividono boundary)
        for seg in self.segments:
            if seg.start_time <= t <= seg.end_time:
                return seg.evaluate(t)

        # Fallback: ultimo valore (non dovrebbe accadere)
        return self.segments[-1].breakpoints[-1][1]

    def integrate(self, from_time: float, to_time: float) -> float:
        """
        Integrale dell'envelope tra from_time e to_time.

        Multi-segmento: somma per-segmento sul range overlap; hold pre/post
        gestito sugli estremi globali.
        """
        if from_time > to_time:
            return -self.integrate(to_time, from_time)
        if from_time == to_time:
            return 0.0

        if len(self.segments) == 1:
            return self.segments[0].integrate(from_time, to_time)

        global_start = self.segments[0].start_time
        global_end = self.segments[-1].end_time
        total = 0.0
        cursor = from_time

        # Hold prima del primo segmento
        if cursor < global_start:
            hold_end = min(to_time, global_start)
            total += self.segments[0].breakpoints[0][1] * (hold_end - cursor)
            cursor = hold_end
            if cursor >= to_time:
                return total

        # Integra su segmenti che overlappano [cursor, to_time]
        for seg in self.segments:
            if cursor >= to_time:
                break
            if to_time <= seg.start_time or cursor >= seg.end_time:
                continue
            a = max(cursor, seg.start_time)
            b = min(to_time, seg.end_time)
            if b > a:
                total += seg.strategy.integrate(a, b, seg.breakpoints, **seg.context)
                cursor = b

        # Hold dopo l'ultimo segmento
        if cursor < to_time and cursor >= global_end:
            total += self.segments[-1].breakpoints[-1][1] * (to_time - cursor)

        return total
        
    @property
    def breakpoints(self) -> List[List[float]]:
        """
        Property per accesso ai breakpoints (backward compatibility).
        
        Dopo il refactoring, i breakpoints sono contenuti nei segments.
        Questa property fornisce accesso diretto per codice legacy.
        
        Returns:
            List[List[float]]: Lista di breakpoints [[t, v], ...]
        """
        # Tipicamente c'è un solo segment con tutti i breakpoints
        if len(self.segments) == 1:
            return self.segments[0].breakpoints

        # Multi-segmento: concatena senza duplicare punti di giunzione
        # (segmenti adiacenti condividono bp boundary)
        all_breakpoints = list(self.segments[0].breakpoints)
        for seg in self.segments[1:]:
            # Skip primo bp di seg se coincide con ultimo bp già aggiunto
            seg_bps = seg.breakpoints
            if seg_bps and all_breakpoints and seg_bps[0] == all_breakpoints[-1]:
                all_breakpoints.extend(seg_bps[1:])
            else:
                all_breakpoints.extend(seg_bps)
        return all_breakpoints



    @staticmethod
    def is_envelope_like(obj: Any) -> bool:
        """
        Type checker centralizzato: rileva se un oggetto rappresenta envelope-like data.
        
        Supporta:
        - Envelope instances
        - Liste di breakpoints [[t, v], ...]
        - Dict con 'type' e 'points'
        - Formato compatto
        
        Returns:
            bool: True se l'oggetto è envelope-like
        """
        from pge.envelopes.envelope_builder import EnvelopeBuilder
        
        # Istanza Envelope
        if isinstance(obj, Envelope):
            return True
        
        # Lista di breakpoints o formato compatto
        if isinstance(obj, list):
            # Lista vuota: NO
            if not obj:
                return False
            
            # Formato compatto
            if EnvelopeBuilder._is_compact_format(obj):
                return True

            # BP group diretto [points, interp] (issue #64)
            if EnvelopeBuilder._is_bp_group(obj):
                return True

            # Lista con almeno un [t, v]
            for item in obj:
                if isinstance(item, list) and len(item) == 2:
                    return True
                # Formato compatto dentro lista
                if EnvelopeBuilder._is_compact_format(item):
                    return True
                # BP group dentro lista
                if EnvelopeBuilder._is_bp_group(item):
                    return True
            return False
        
        # Dict con 'points'
        if isinstance(obj, dict):
            return 'points' in obj
        
        return False
    

    @staticmethod
    def _scale_raw_values_y(raw_data: Union[List, Dict], scale_factor: float) -> Union[List, Dict]:
        """
        Scala i valori Y dei dati raw, restituendo dati raw (stesso formato dell'input).
        Usato da PointerController._scale_value per mantenere compatibilita'
        col pipeline parser a valle.
        """
        from pge.envelopes.envelope_builder import EnvelopeBuilder
        import copy
        
        def _scale_group_y(group):
            scaled_points = [
                [p[0], p[1] * scale_factor] if len(p) == 2
                else [p[0], p[1] * scale_factor, p[2]]
                for p in group[0]
            ]
            return [scaled_points, group[1]]

        def _scale_list_y(points_list):
            scaled = []
            for item in points_list:
                if EnvelopeBuilder._is_compact_format(item):
                    pattern = item[0]
                    scaled_pattern = [[p[0], p[1] * scale_factor] for p in pattern]
                    new_item = list(item)
                    new_item[0] = scaled_pattern
                    scaled.append(new_item)
                elif EnvelopeBuilder._is_bp_group(item):
                    # BP group: scala i valori Y dei punti, preserva interp e
                    # type per-punto. Prima del branch [t, v]: anche il gruppo
                    # è una lista a 2 elementi.
                    scaled.append(_scale_group_y(item))
                elif isinstance(item, list) and len(item) == 2:
                    scaled.append([item[0], item[1] * scale_factor])
                elif EnvelopeBuilder._is_3tuple_breakpoint(item):
                    scaled.append([item[0], item[1] * scale_factor, item[2]])
                elif isinstance(item, dict) and 't' in item and 'v' in item:
                    scaled_dict = dict(item)
                    scaled_dict['v'] = item['v'] * scale_factor
                    scaled.append(scaled_dict)
                else:
                    scaled.append(item)
            return scaled

        if isinstance(raw_data, dict):
            new_data = copy.deepcopy(raw_data)
            if 'points' in new_data:
                new_data['points'] = _scale_list_y(new_data['points'])
            return new_data

        if isinstance(raw_data, list):
            if EnvelopeBuilder._is_compact_format(raw_data):
                pattern = raw_data[0]
                scaled_pattern = [[p[0], p[1] * scale_factor] for p in pattern]
                new_data = list(raw_data)
                new_data[0] = scaled_pattern
                return new_data
            elif EnvelopeBuilder._is_bp_group(raw_data):
                # BP group diretto [points, interp]
                return _scale_group_y(raw_data)
            else:
                return _scale_list_y(raw_data)

        raise ValueError(f"Formato non supportato per _scale_raw_values_y: {raw_data}")

    @staticmethod
    def scale_envelope_values(raw_data: Union[List, Dict], scale_factor: float) -> 'Envelope':
        """
        Crea un Envelope scalando i VALORI Y (non il tempo).
        Usato da PointerController per loop normalizzati (0-1 -> 0-SampleDur).
        """
        scaled_raw = Envelope._scale_raw_values_y(raw_data, scale_factor)
        return Envelope(scaled_raw)


def scale_raw_param_values(value, scale_factor: float):
    """
    Scala un valore parametro grezzo (scalare, envelope-like o altro) per
    scale_factor, restituendo dati raw nello stesso formato dell'input,
    compatibili col pipeline parser a valle.

    Punto unico per le conversioni di unita' sui valori Y dei parametri:
    loop_unit normalized (PointerController) e grain.duration_unit samples
    (Stream). Tipi non numerici e non envelope-like passano invariati.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value * scale_factor
    if Envelope.is_envelope_like(value):
        return Envelope._scale_raw_values_y(value, scale_factor)
    return value


def create_scaled_envelope(
    raw_data: Union[List, Dict],
    duration: float,
    time_mode: str = 'absolute'
    ) -> Envelope:
    """
    Factory helper per creare Envelope con scaling TEMPORALE (X axis).
    Sostituisce la vecchia logica integrandosi con EnvelopeBuilder.
    code Code

    Se time_mode='normalized', moltiplica i tempi [t, v] per 'duration'.
    Nota: I formati compatti (che usano total_time esplicito) NON vengono scalati.
    """
    from pge.envelopes.envelope_builder import EnvelopeBuilder

    # 1. Gestione DICT
    if isinstance(raw_data, dict):
        local_unit = raw_data.get('time_unit', time_mode)
        points = raw_data.get('points', [])
        
        if local_unit == 'normalized':
            scaled_points = _scale_time_recursive(points, duration)
            return Envelope({'type': raw_data.get('type', 'linear'), 'points': scaled_points})
        return Envelope(raw_data)

    # 2. Gestione LIST
    # Se il modo globale è normalized, scaliamo solo i breakpoint semplici
    if time_mode == 'normalized':
        scaled_points = _scale_time_recursive(raw_data, duration)
        return Envelope(scaled_points)

    return Envelope(raw_data)

def _scale_group_points_time(group_points: List, factor: float) -> List:
    """Scala i tempi dei punti di un BP group, preservando i type per-punto."""
    return [
        [p[0] * factor, p[1]] if len(p) == 2 else [p[0] * factor, p[1], p[2]]
        for p in group_points
    ]


def _scale_time_recursive(points: List, factor: float) -> List:
    """
    Scala ricorsivamente i tempi per breakpoint standard [t, v].
    Scala anche total_time per formati compatti quando time_mode='normalized'.
    
    Args:
        points: Lista di breakpoints, formati compatti, o mix
        factor: Fattore di scaling (duration dello stream)
    
    Returns:
        Lista con tempi scalati
    """
    from pge.envelopes.envelope_builder import EnvelopeBuilder

    # CASO 1: L'intera lista è un formato compatto
    if EnvelopeBuilder._is_compact_format(points):
        # NUOVO: Scala il total_time (elemento [1])
        scaled_compact = list(points)
        scaled_compact[1] = points[1] * factor
        return scaled_compact

    # CASO 1b: L'intera lista è un BP group diretto [points, interp]
    if EnvelopeBuilder._is_bp_group(points):
        return [_scale_group_points_time(points[0], factor), points[1]]

    # CASO 2: Lista di elementi misti
    scaled = []
    for item in points:
        if EnvelopeBuilder._is_compact_format(item):
            scaled_compact = list(item)
            scaled_compact[1] = item[1] * factor
            scaled.append(scaled_compact)
        elif EnvelopeBuilder._is_bp_group(item):
            # BP group: scala i tempi dei punti, preserva interp e type per-punto.
            # Va controllato prima del branch [t, v]: un gruppo è anch'esso
            # una lista a 2 elementi.
            scaled.append([_scale_group_points_time(item[0], factor), item[1]])
        elif isinstance(item, list) and len(item) == 2:
            # Standard breakpoint: [t, v] -> [t * factor, v]
            scaled.append([item[0] * factor, item[1]])
        elif EnvelopeBuilder._is_3tuple_breakpoint(item):
            # 3-tuple breakpoint: [t, v, type] -> [t * factor, v, type]
            scaled.append([item[0] * factor, item[1], item[2]])
        elif isinstance(item, dict) and 't' in item and 'v' in item:
            # Dict per-punto {t, v, type?}: scala t
            scaled_dict = dict(item)
            scaled_dict['t'] = item['t'] * factor
            scaled.append(scaled_dict)
        else:

            scaled.append(item)
    
    return scaled
