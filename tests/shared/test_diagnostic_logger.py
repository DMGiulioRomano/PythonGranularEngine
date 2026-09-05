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

import pytest

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


def test_diagnostic_logger_non_ricade_su_lastresort(capsys):
    """Il NullHandler copre anche i livelli che `logging` stampa da solo.

    Un logger senza handler manda i record da WARNING in su a
    `logging.lastResort`, che scrive su stderr: la diagnostica sarebbe muta
    solo finche' resta a DEBUG. Il NullHandler chiude anche quella porta.
    """
    logger = get_diagnostic_logger()

    logger.warning("questa non deve comparire da nessuna parte")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


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

    class _Spia(logging.Handler):
        def emit(self, record):
            registrati.append(record)

    logger = get_diagnostic_logger()
    spia = _Spia()
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
