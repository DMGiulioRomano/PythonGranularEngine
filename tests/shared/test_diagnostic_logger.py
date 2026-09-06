# =============================================================================
# tests/shared/test_diagnostic_logger.py
# =============================================================================
"""
Test per il diagnostic logger (issue #187, primo scaglione della #178).

Terzo logger accanto a clip ed engine, e con un compito diverso dai loro: le
righe che nessuno parsa e nessuno legge come interfaccia — la registrazione
dinamica di una strategy — smettono di essere `print()` e diventano record di
logging.

Il motivo per cui non possono restare su stdout non e' estetico: stdout e' un
canale di protocollo. `render_pipeline.py` di PGE-ui lo legge riga per riga e
ne ricava gli eventi NDJSON dell'editor. Ogni riga che finisce li' e' materiale
che un parser a valle deve attraversare.

Da qui i due vincoli che questa suite fissa:
1. muto di default, e muto su *stdout* in ogni caso (il canale della console
   di `logging` e' stderr);
2. nessun effetto collaterale sul filesystem — registrare una strategy non
   deve creare una cartella `logs/`, che e' invece cio' che farebbe
   `get_engine_logger()`, il quale si auto-configura.
"""
import logging
import os

from pge.shared.logger import (
    DIAGNOSTIC_LOGGER_NAME,
    get_diagnostic_logger,
    log_strategy_registration,
)


class _Strategia:
    """Classe fittizia: al logger interessa solo il suo `__name__`."""


# =============================================================================
# 1. IDENTITA' DEL LOGGER
# =============================================================================

def test_diagnostic_logger_ha_un_nome_dedicato():
    """Il logger e' suo, non il root: un host puo' alzarlo o zittirlo da solo."""
    logger = get_diagnostic_logger()

    assert isinstance(logger, logging.Logger)
    assert logger.name == DIAGNOSTIC_LOGGER_NAME
    assert logger is logging.getLogger(DIAGNOSTIC_LOGGER_NAME)


def test_diagnostic_logger_non_impone_un_livello():
    """Il livello e' dell'host: qui resta NOTSET, e non e' un'omissione.

    Il DEBUG sta sulla chiamata, non sul logger. Alzarlo qui non renderebbe la
    diagnostica *accendibile* — la renderebbe accesa: `Logger.callHandlers`
    confronta il record col livello dell'**handler** e non ricontrolla quello
    del logger, e un `logging.basicConfig()` senza argomenti lascia il proprio
    StreamHandler a NOTSET. Con un `setLevel(DEBUG)` qui, ogni host che chiama
    `basicConfig()` si troverebbe la diagnostica su stderr senza averla
    chiesta: esattamente l'astensione che questo logger esiste per praticare.
    """
    logger = get_diagnostic_logger()

    assert logger.level == logging.NOTSET, (
        "il diagnostic logger si e' dato un livello: cosi' non e' piu' l'host "
        "a decidere se ascoltarlo"
    )


def test_diagnostic_logger_e_idempotente():
    """Chiamate ripetute non impilano handler.

    `get_clip_logger` puo' permettersi di azzerare `handlers` perche' li
    possiede tutti; qui gli handler sono dell'applicazione ospite e vanno
    lasciati stare, quindi l'unica difesa contro il duplicato e' non
    riaggiungere il NullHandler a ogni chiamata.
    """
    primo = get_diagnostic_logger()
    quanti = len(primo.handlers)

    for _ in range(5):
        get_diagnostic_logger()

    assert len(primo.handlers) == quanti


# =============================================================================
# 2. MUTO DI DEFAULT, E SOPRATTUTTO MUTO SU STDOUT
# =============================================================================

def test_diagnostic_logger_non_scrive_niente_senza_configurazione(capsys):
    """Senza configurazione dell'host, nessun byte esce."""
    logger = get_diagnostic_logger()

    logger.debug("registrata qualcosa")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


class _SpiaLastResort(logging.Handler):
    """Handler che si limita a contare: sta al posto di `logging.lastResort`."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _isola(logger, monkeypatch):
    """Isola `logger` dagli handler che *l'ambiente* mette sul root.

    Serve perche' l'asserzione qui sotto sia una misura e non una tautologia.
    `Logger.callHandlers` conta gli handler di **tutta la catena** e ricade su
    `lastResort` solo se non ne trova nessuno; sotto pytest il root ne porta
    sempre quattro (`_LiveLoggingNullHandler`, il `_FileHandler` su /dev/null
    e i due `LogCaptureHandler`), quindi `found` non e' mai zero e la porta che
    il NullHandler chiude resta chiusa da sola: un test che guardasse solo
    stderr passerebbe identico dopo aver cancellato la riga che dice di
    difendere.

    L'isolamento si fa spegnendo `propagate` sul logger in esame, non
    svuotando `root.handlers`: la lista del root e' condivisa con il plugin di
    logging di pytest, che alla fine della fase fa `removeHandler` sulla lista
    che trova: sostituirgliela sotto significa lasciargli l'handler attaccato
    per il resto della sessione. Cosi' invece l'unico handler in gioco resta
    quello del logger, che e' esattamente cio' che si vuole misurare.

    Restituisce la spia che prende il posto di `lastResort`.
    """
    spia = _SpiaLastResort()
    monkeypatch.setattr(logging, 'lastResort', spia)
    monkeypatch.setattr(logger, 'propagate', False)
    return spia


def test_diagnostic_logger_non_ricade_su_lastresort(monkeypatch, capsys):
    """Il NullHandler copre anche i livelli che `logging` stampa da solo.

    Un logger senza handler manda i record da WARNING in su a
    `logging.lastResort`, che scrive su stderr: la diagnostica sarebbe muta
    solo finche' resta a DEBUG. Il NullHandler chiude anche quella porta —
    ed e' l'unico a farlo, una volta isolato il logger dall'ambiente.
    """
    logger = get_diagnostic_logger()
    spia = _isola(logger, monkeypatch)

    logger.warning("questa non deve comparire da nessuna parte")

    assert spia.records == [], "record finito su lastResort: manca il NullHandler"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_la_misura_del_lastresort_e_sensibile(monkeypatch):
    """Controprova: senza NullHandler, con lo stesso setup, la spia scatta.

    Senza questa meta' il test precedente non dimostra niente — potrebbe
    essere verde perche' `lastResort` non viene mai raggiunto in nessun caso.
    Qui l'unica differenza e' un logger nudo, e il verdetto si ribalta.
    """
    nudo = logging.getLogger('probe_nuda_senza_handler')
    assert not nudo.handlers, "la probe deve essere nuda per misurare qualcosa"
    spia = _isola(nudo, monkeypatch)

    nudo.warning("questa invece deve arrivare a lastResort")

    assert len(spia.records) == 1, \
        "lastResort non raggiunto nemmeno da un logger nudo: la misura non misura"


def test_diagnostic_logger_non_crea_la_cartella_dei_log(tmp_path, monkeypatch):
    """Nessun effetto collaterale su disco: la diagnostica non configura nulla.

    `get_engine_logger()` si auto-configura e con essa crea `./logs`. Passare
    di li' avrebbe significato materializzare una cartella per dire che una
    strategy e' stata registrata.
    """
    monkeypatch.chdir(tmp_path)

    get_diagnostic_logger()
    log_strategy_registration('density', 'pino', _Strategia)

    assert os.listdir(tmp_path) == []


# =============================================================================
# 3. IL RECORD, QUANDO L'HOST LO ASCOLTA
# =============================================================================

def test_log_strategy_registration_emette_un_record_debug(caplog):
    """Il messaggio esiste ancora: cambia il canale, non l'informazione."""
    with caplog.at_level(logging.DEBUG, logger=DIAGNOSTIC_LOGGER_NAME):
        log_strategy_registration('variation', 'test_mode', _Strategia)

    records = [r for r in caplog.records if r.name == DIAGNOSTIC_LOGGER_NAME]
    assert len(records) == 1

    record = records[0]
    assert record.levelno == logging.DEBUG
    messaggio = record.getMessage()
    assert 'variation' in messaggio
    assert 'test_mode' in messaggio
    assert '_Strategia' in messaggio


def test_log_strategy_registration_formatta_pigramente():
    """Gli argomenti restano tali finche' qualcuno non formatta.

    Con `%s` il costo della stringa lo paga solo chi ascolta davvero — ed e'
    la ragione per cui una diagnostica muta puo' stare su un percorso caldo
    senza pesare.
    """
    registrati = []

    class _SpiaDeiRecord(logging.Handler):
        def emit(self, record):
            registrati.append(record)

    logger = get_diagnostic_logger()
    spia = _SpiaDeiRecord()
    logger.addHandler(spia)
    livello = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        log_strategy_registration('pan voce', 'stereo_spread', _Strategia)
    finally:
        logger.removeHandler(spia)
        logger.setLevel(livello)

    assert len(registrati) == 1
    assert registrati[0].args, "il record non porta argomenti: formattazione avida"
    assert '%s' in registrati[0].msg


def test_log_strategy_registration_non_scrive_su_stdout(capsys):
    """Il punto dell'issue: la riga non entra nel canale che PGE-ui parsa."""
    log_strategy_registration('density', 'fill_factor', _Strategia)

    assert capsys.readouterr().out == ""
