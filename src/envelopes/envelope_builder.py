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

from typing import List, Union, Tuple, Optional


class EnvelopeBuilder:
    """
    Builder per creare liste di breakpoints da formati multipli.
    
    Supporta:
    - Compact format: [[[0, 0], [100, 1]], end_time, n_reps, interp?, time_dist?]
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
    
    @classmethod
    def parse(cls, raw_points: list) -> list:
        """
        Parsa lista mista di formati, espandendo formato compatto.
        
        Calcola automaticamente l'offset temporale per parti compatte in formato misto.
        
        Args:
            raw_points: 
                - [[[x%, y], ...], end_time, n_reps, interp?] (formato compatto diretto)
                - Lista con mix di:
                    * [time, value] (legacy)
                    * [[[x%, y], ...], end_time, n_reps, interp?] (compact wrapped)
                
        Returns:
            Lista espansa con solo [time, value]
            
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
        if cls._is_compact_format(raw_points):
            # Formato compatto diretto: offset = 0
            expanded = cls._expand_compact_format(raw_points, time_offset=0.0)
            
            # Log risultato finale
            cls._log_final_envelope(raw_points, expanded)
            
            return expanded
        
        # Altrimenti, itera sugli elementi (formato legacy o misto)
        expanded = []
        current_time = 0.0  # Traccia tempo corrente per offset
        
        for item in raw_points:
            if cls._is_compact_format(item):
                # Espandi formato compatto CON OFFSET
                compact_expanded = cls._expand_compact_format(item, time_offset=current_time)
                expanded.extend(compact_expanded)
                
                # Aggiorna tempo corrente (ultimo breakpoint espanso)
                if compact_expanded:
                    current_time = compact_expanded[-1][0]
            else:
                if not (isinstance(item, list) and len(item) == 2):
                    raise ValueError(
                        f"Elemento non valido nel formato envelope: {item!r}. "
                        "Atteso [time, value]."
                    )
                expanded.append(item)
                current_time = max(current_time, item[0])
        
        # Log risultato finale
        cls._log_final_envelope(raw_points, expanded)
        
        return expanded
    
    @classmethod
    def _is_compact_format(cls, item) -> bool:
        """
        Rileva se item è formato compatto.
        
        Formato compatto: [pattern_points, end_time, n_reps, interp?, time_dist?]
        - pattern_points è lista di liste [[x%, y], ...]
        - end_time è float/int (TEMPO ASSOLUTO FINALE, non durata)
        - n_reps è int
        - interp è str opzionale
        - time_dist è str/dict opzionale (distribuzione temporale)
        
        Returns:
            True se è formato compatto
        """
        if not isinstance(item, list):
            return False
        
        # Deve avere 3, 4 o 5 elementi
        if len(item) < 3:  # Minimo: [pattern_points, end_time, n_reps]
            return False
        
        if len(item) > 5:  # Massimo: [pattern_points, end_time, n_reps, interp, time_dist]
            return False
        
        # Primo elemento deve essere lista (anche se vuota)
        if not isinstance(item[0], list):
            return False
        
        # Se pattern NON vuoto, verifica formato [x, y]
        if item[0]:
            if not all(isinstance(p, list) and len(p) == 2 for p in item[0]):
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
        if len(item) == 5 and item[4] is not None:
            if not isinstance(item[4], (str, dict)):
                return False
        
        return True
        
    @classmethod
    def _expand_compact_format(cls, compact: list, time_offset: float = 0.0) -> list:
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
        # Import TimeDistributionFactory
        from envelopes.time_distribution import TimeDistributionFactory
        
        # Parse input
        pattern_points_pct = compact[0]
        end_time = compact[1]  # Tempo assoluto finale
        n_reps = compact[2]
        interp_type = compact[3] if len(compact) >= 4 else None
        time_dist_spec = compact[4] if len(compact) == 5 else None
        
        # Valida
        if n_reps < 1:
            raise ValueError(f"n_reps deve essere >= 1, ricevuto: {n_reps}")
        
        if end_time <= time_offset:
            raise ValueError(
                f"end_time ({end_time}) deve essere > time_offset ({time_offset})"
            )
        
        if not pattern_points_pct:
            raise ValueError("pattern_points non può essere vuoto")
        
        # CALCOLA durata totale dall'offset
        total_duration = end_time - time_offset
        
        # CREA strategia di distribuzione temporale
        distributor = TimeDistributionFactory.create(time_dist_spec)
        
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
            for i, (x_pct, y) in enumerate(pattern_points_pct):
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
            
                expanded.append([t_absolute, y])
        
        # LOGGING della trasformazione compatta
        cls._log_compact_transformation(
            compact, expanded, time_offset, total_duration, distributor
        )
        
        return expanded


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
        from shared.logger import get_clip_logger, CLIP_LOG_CONFIG
        
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
            t, v = expanded[i]
            logger.info(f"    [{i}] t={t:.6f}s, v={v}")
        
        if len(expanded) > preview_count:
            logger.info(f"  ...")
            logger.info(f"  Last {preview_count} breakpoints:")
            for i in range(len(expanded) - preview_count, len(expanded)):
                t, v = expanded[i]
                logger.info(f"    [{i}] t={t:.6f}s, v={v}")
        
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
        from shared.logger import get_clip_logger, CLIP_LOG_CONFIG

        if not CLIP_LOG_CONFIG.get('log_transformations', True):
            return

        logger = get_clip_logger()
        if logger is None:
            return
        
        # Conta quanti elementi sono compatti vs standard
        n_compact = 0
        n_standard = 0
        
        if cls._is_compact_format(raw_input):
            n_compact = 1
        else:
            for item in raw_input:
                if cls._is_compact_format(item):
                    n_compact += 1
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
        logger.info(f"  Format type: {'compact' if cls._is_compact_format(raw_input) else 'mixed' if n_compact > 0 else 'standard'}")
        
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
        if cls._is_compact_format(raw_points):
            # Formato compatto con 4 elementi include interp_type
            if len(raw_points) == 4:
                return raw_points[3]
            return None
        
        # Altrimenti itera sugli elementi (formato misto)
        for item in raw_points:
            if cls._is_compact_format(item):
                # Formato compatto con 4 elementi include interp_type
                if len(item) == 4:
                    return item[3]
        
        return None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def detect_format_type(item) -> str:
    """
    Helper per debugging: rileva tipo di formato.
    
    Returns:
        'compact' | 'breakpoint' | 'cycle' | 'unknown'
    """
    if isinstance(item, str) and item.lower() == 'cycle':
        return 'cycle'
    
    if EnvelopeBuilder._is_compact_format(item):
        return 'compact'
    
    if isinstance(item, list) and len(item) == 2:
        return 'breakpoint'
    
    return 'unknown'