# =============================================================================
# logger.py - Gestione logging per envelope clip warnings
# =============================================================================
import logging
from datetime import datetime
import os

# =============================================================================
# CONFIGURAZIONE
# =============================================================================
CLIP_LOG_CONFIG = {
    'enabled': True,                    # Master switch: False disabilita tutto
    'console_enabled': True,            # Stampa su terminale
    'file_enabled': True,               # Scrive su file
    'log_dir': './logs',                # Directory per i file di log
    'log_filename': None,               # None = auto-genera con timestamp
    'validation_mode': 'strict',
    'log_transformations': True,        # Logga trasformazioni envelope compatti
}

_clip_logger = None
_clip_logger_initialized = False


# =============================================================================
# FUNZIONI PUBBLICHE
# =============================================================================

def configure_clip_logger(
    enabled=True,
    console_enabled=True,
    file_enabled=True,
    log_dir='./logs',
    yaml_name=None,
    log_transformations=True
):
    """
    Configura il logger per i clip warnings e trasformazioni envelope.
    Chiamare PRIMA di creare qualsiasi Stream.
    
    Args:
        enabled: Master switch - se False, nessun logging
        console_enabled: Se True, stampa warning su terminale
        file_enabled: Se True, scrive su file
        log_dir: Directory dove salvare i file di log
        yaml_name: Nome del file YAML (senza path, senza estensione)
                   Il file sarà: envelope_clips_{yaml_name}.log
    """
    global CLIP_LOG_CONFIG, _clip_logger, _clip_logger_initialized
    
    CLIP_LOG_CONFIG['enabled'] = enabled
    CLIP_LOG_CONFIG['console_enabled'] = console_enabled
    CLIP_LOG_CONFIG['file_enabled'] = file_enabled
    CLIP_LOG_CONFIG['log_dir'] = log_dir
    CLIP_LOG_CONFIG['yaml_name'] = yaml_name  # <-- NUOVO
    CLIP_LOG_CONFIG['log_transformations'] = log_transformations

    # Reset logger per ri-inizializzazione
    _clip_logger = None
    _clip_logger_initialized = False

def get_clip_logger():
    """
    Ottiene il logger per i clip warnings (lazy initialization).
    Rispetta la configurazione in CLIP_LOG_CONFIG.
    
    Returns:
        logging.Logger o None se disabilitato
    """
    global _clip_logger, _clip_logger_initialized
    
    # Se già inizializzato, ritorna (anche se None)
    if _clip_logger_initialized:
        return _clip_logger
    
    _clip_logger_initialized = True
    
    # Master switch
    if not CLIP_LOG_CONFIG['enabled']:
        _clip_logger = None
        return None
    
    # Se né console né file sono abilitati, disabilita
    if not CLIP_LOG_CONFIG['console_enabled'] and not CLIP_LOG_CONFIG['file_enabled']:
        _clip_logger = None
        return None
    
    # Crea logger
    _clip_logger = logging.getLogger('envelope_clip')
    _clip_logger.setLevel(logging.INFO)
    _clip_logger.handlers = []  # Pulisci handler esistenti
    
    # === FILE HANDLER ===
    if CLIP_LOG_CONFIG['file_enabled']:
        log_dir = CLIP_LOG_CONFIG['log_dir']
        
        # Crea directory se non esiste
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            print(f"📁 Creata directory log: {log_dir}")
        
        # Nome file
        if CLIP_LOG_CONFIG.get('yaml_name'):
            # Usa nome YAML
            yaml_name = CLIP_LOG_CONFIG['yaml_name']
            log_filename = f'envelope_clips_{yaml_name}.log'
        else:
            # Fallback: timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f'envelope_clips_{timestamp}.log'
        
        log_path = os.path.join(log_dir, log_filename)
        
        file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_format = logging.Formatter(
            '%(asctime)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        _clip_logger.addHandler(file_handler)
        
        print(f"📝 Clip log file: {log_path}")
    
    # === CONSOLE HANDLER ===
    if CLIP_LOG_CONFIG['console_enabled']:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_format = logging.Formatter('⚠️  CLIP: %(message)s')
        console_handler.setFormatter(console_format)
        _clip_logger.addHandler(console_handler)
    
    return _clip_logger

def get_clip_log_path():
    """
    Ritorna il percorso del file di log corrente (se esiste).
    
    Returns:
        str o None
    """
    if _clip_logger is None:
        return None
    
    for handler in _clip_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            return handler.baseFilename
    return None

def log_clip_warning(stream_id, param_name, time, raw_value, clipped_value, 
                     min_val, max_val, is_envelope=False):
    """
    Logga un warning per un valore clippato.
    
    Args:
        stream_id: ID dello stream
        param_name: nome del parametro
        time: tempo in secondi
        raw_value: valore originale
        clipped_value: valore dopo il clip
        min_val: limite minimo
        max_val: limite massimo
        is_envelope: True se il valore viene da un Envelope
    """
    logger = get_clip_logger()
    
    if logger is None:
        return
    
    # Calcola bound violato
    if raw_value < min_val:
        deviation = raw_value - min_val
        bound_type = "MIN"
        bound_value = min_val
    else:
        deviation = raw_value - max_val
        bound_type = "MAX"
        bound_value = max_val
    
    source_type = "ENV" if is_envelope else "FIX"
    
    logger.warning(
        f"[{stream_id}] {param_name:<20} | "
        f"t={time:>7.3f}s | "
        f"raw={raw_value:>12.6f} → clip={clipped_value:>12.6f} | "
        f"{bound_type}={bound_value:>10.4f} | "
        f"Δ={deviation:>+10.6f} | "
        f"({source_type})"
    )
    

def log_config_warning(stream_id: str, param_name: str, 
                    raw_value: float, clipped_value: float,
                    min_val: float, max_val: float,
                    value_type: str = "value"):
    """
    Logga un warning per un valore di configurazione fuori bounds.
    
    Usato al momento della creazione del Parameter per segnalare
    valori iniziali che violano i bounds.
    
    Args:
        stream_id: ID dello stream
        param_name: nome del parametro
        raw_value: valore originale dallo YAML
        clipped_value: valore clippato ai bounds
        min_val: limite minimo
        max_val: limite massimo
        value_type: 'value', 'range', o 'probability'
    """
    logger = get_clip_logger()
    
    if logger is None:
        return
    
    # Calcola bound violato
    if raw_value < min_val:
        deviation = raw_value - min_val
        bound_type = "MIN"
        bound_value = min_val
    else:
        deviation = raw_value - max_val
        bound_type = "MAX"
        bound_value = max_val
    
    # Tag diverso per config
    logger.warning(
        f"[CONFIG] [{stream_id}] {param_name:<20} | "
        f"{value_type}: raw={raw_value:>12.6f} → clip={clipped_value:>12.6f} | "
        f"{bound_type}={bound_value:>10.4f} | "
        f"Δ={deviation:>+10.6f}"
    )

def log_loop_drift_warning(stream_id: str, elapsed_time: float,
                           pointer_pos: float,
                           loop_start: float, loop_end: float,
                           speed_ratio: float, loop_start_drift_rate: float,
                           stream_duration: float,
                           is_first: bool = False):
    """
    Logga un warning quando il pointer non riesce a entrare nel loop
    perche' loop_start si sposta piu' velocemente della speed del pointer.

    Args:
        stream_id: ID dello stream
        elapsed_time: tempo corrente elapsed nello stream
        pointer_pos: posizione attuale del pointer nel sample (secondi)
        loop_start: valore corrente di loop_start (secondi)
        loop_end: valore corrente di loop_end (secondi)
        speed_ratio: speed_ratio corrente del pointer
        loop_start_drift_rate: velocita' stimata di spostamento di loop_start (s/s)
        stream_duration: durata totale dello stream in secondi
    """
    logger = get_clip_logger()
    if logger is None:
        return

    loop_length = loop_end - loop_start
    gap = loop_start - pointer_pos  # distanza tra pointer e ingresso loop

    # Velocita' minima necessaria per stare dentro il loop
    min_speed_needed = loop_start_drift_rate if loop_start_drift_rate > 0 else 0.0
    tag = "[LOOP_DRIFT_FIRST]" if is_first else "[LOOP_DRIFT]"
    note = " << PRIMO AVVISO — log successivi soppressi (rate limit 5s)" if is_first else ""

    logger.warning(
        f"{tag} [{stream_id}] "
        f"t={elapsed_time:>7.2f}s | "
        f"pointer={pointer_pos:>8.4f}s | "
        f"loop=[{loop_start:.4f}, {loop_end:.4f}]s (len={loop_length:.4f}s) | "
        f"gap={gap:>+8.4f}s | "
        f"speed={speed_ratio:.6f} | "
        f"loop_drift={loop_start_drift_rate:.6f} s/s | "
        f"min_speed_needed>={min_speed_needed:.6f} | "
        f"ratio_actual/needed={speed_ratio / max(min_speed_needed, 1e-9):.3f}x"
        f"{note}"
    )


def log_loop_dynamic_mode(stream_id: str, loop_start_initial: float,
                          loop_end_initial: float, start_overridden: bool,
                          original_start: float):
    """
    Logga l'attivazione della modalita' loop dinamico.

    Emessa UNA SOLA VOLTA al momento dell'init del PointerController,
    quando loop_start e' un Envelope. In questa modalita' il pointer
    entra immediatamente nel loop senza attendere che la posizione
    lineare intersechi la regione.

    Args:
        stream_id: ID dello stream
        loop_start_initial: valore di loop_start a elapsed=0
        loop_end_initial: valore di loop_end a elapsed=0
        start_overridden: True se il parametro 'start' YAML e' stato
                          ignorato perche' diverso da loop_start_initial
        original_start: valore 'start' specificato nel YAML (per info)
    """
    logger = get_clip_logger()
    if logger is None:
        return

    override_note = (
        f" | 'start'={original_start:.4f} ignorato (sovrascrtto da loop_start)"
        if start_overridden else ""
    )

    logger.warning(
        f"[LOOP_DYNAMIC] [{stream_id}] "
        f"loop_start e' un Envelope → entrata immediata nel loop | "
        f"loop_start(0)={loop_start_initial:.4f}s | "
        f"loop_end(0)={loop_end_initial:.4f}s"
        f"{override_note}"
    )

def log_window_curve_warning(
    stream_id: str,
    curve_max_t: float,
    valid_max_t: float,
    last_value: float,
    time_mode: str,
):
    """
    Logga un warning quando la curve di window transition finisce prima
    della fine del range valido. L'ultimo valore viene tenuto fino alla fine.

    Args:
        stream_id:    ID dello stream
        curve_max_t:  tempo massimo della curve
        valid_max_t:  tempo massimo valido (1.0 se normalized, duration se absolute)
        last_value:   valore dell'ultimo breakpoint della curve
        time_mode:    'normalized' o 'absolute'
    """
    logger = get_clip_logger()
    if logger is None:
        return

    logger.warning(
        f"[WINDOW_CURVE] [{stream_id}] "
        f"curve termina a t={curve_max_t} < range valido t={valid_max_t} "
        f"(time_mode='{time_mode}'). "
        f"L'ultimo valore ({last_value:.4f}) sarà tenuto fino alla fine."
    )


def log_loop_init(
    stream_id: str,
    loop_start: float,
    loop_end: float,
    loop_dur: float,
    sample_dur_sec: float
):
    """
    Logga la regione loop risolta al momento dell'inizializzazione del
    PointerController (modalita' statica).

    Emessa UNA SOLA VOLTA per stream, subito dopo _init_params.
    Serve a diagnosticare configurazioni errate come regioni invertite
    (loop_end < loop_start) prodotte da fallback su Parameter(value=None).

    Args:
        stream_id:      ID dello stream
        loop_start:     valore risolto di loop_start (secondi)
        loop_end:       valore risolto di loop_end (secondi), None se si usa loop_dur
        loop_dur:       valore risolto di loop_dur (secondi), None se si usa loop_end
        sample_dur_sec: durata totale del sample in secondi
    """
    logger = get_clip_logger()
    if logger is None:
        return

    if loop_dur is not None:
        resolved_end = loop_start + loop_dur
        mode_str = f"loop_dur={loop_dur:.4f}s"
    else:
        resolved_end = loop_end if loop_end is not None else 0.0
        mode_str = f"loop_end={resolved_end:.4f}s"

    loop_length = resolved_end - loop_start

    inverted_note = " *** INVERTED REGION — loop non attivo ***" if loop_length <= 0 else ""
    fallback_note = " [FALLBACK: loop_end = sample_dur]" if (
        loop_end is not None and abs(loop_end - sample_dur_sec) < 1e-9
    ) else ""

    logger.warning(
        f"[LOOP_INIT] [{stream_id}] "
        f"loop_start={loop_start:.4f}s | "
        f"{mode_str} | "
        f"resolved=[{loop_start:.4f}, {resolved_end:.4f}]s | "
        f"length={loop_length:.4f}s | "
        f"sample_dur={sample_dur_sec:.4f}s"
        f"{fallback_note}"
        f"{inverted_note}"
    )