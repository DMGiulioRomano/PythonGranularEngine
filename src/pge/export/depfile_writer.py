# src/pge/export/depfile_writer.py
"""
La depfile di make di un render (issue #290).

Con lo stream come file un render dipende da piu' di un file: il master e
ogni documento che il master importa con `file:`. La regola di make che rende
un brano (`$(SFDIR)/%.aif: $(YMLDIR)/%.yml`) conosce solo il primo, e
modificare soltanto uno stream importato lasciava l'audio di prima. La
soluzione e' quella di gcc (`-MD -MP`): chi legge i file -- il motore -- li
scrive in un frammento di Makefile, e il Makefile lo include.

    output/brano.aif: configs/brano.yml configs/streams/risacca.yml
    configs/streams/risacca.yml:

La seconda riga e' la `-MP`: un file importato che sparisce non ferma make
con «No rule to make target» (la depfile e' quella del render precedente),
rifa' il render, ed e' li' che il file mancante ha il suo messaggio. Il
master non la ha: e' il prerequisito della regola a pattern, e se sparisce
l'errore giusto e' quello di make.
"""
from __future__ import annotations

import os
import tempfile
from typing import List, Sequence


_INTESTAZIONE = ("# Dipendenze del render, scritte da `--depfile` "
                 "(pge, issue #290). Rigenerata a ogni render.")


def _scappa(path: str, target: bool) -> str:
    """Un path come make lo legge in una lista di file.

    `$` raddoppiato, `#` e lo spazio dietro un backslash: e' la grafia di
    gcc, verificata contro GNU make (`tests/export/test_depfile_writer.py`).
    `%` solo in posizione di target, dove fa di una regola una regola a
    pattern; fra i prerequisiti e' letterale, e `\\%` lo resterebbe col
    backslash.
    """
    if '\n' in path or '\r' in path:
        # Make non ha una grafia per l'a capo, e la depfile e' inclusa da
        # ogni `make`: una riga spezzata li fermerebbe tutti.
        raise ValueError(
            f"path con un a capo, non rappresentabile in una depfile di "
            f"make: {path!r}")
    path = path.replace('$', '$$').replace('#', r'\#').replace(' ', r'\ ')
    if target:
        path = path.replace('%', r'\%')
    return path


def make_depfile(target: str, prerequisites: Sequence[str]) -> str:
    """Il testo della depfile: `target` dipende da `prerequisites`.

    Args:
        target: il file che la regola di make produce, come make lo nomina
            (il `$@` della regola): make confronta i nomi come stringhe.
        prerequisites: il master per primo, poi i file importati. Un file
            che compare due volte -- lo stesso stream importato con due id --
            si scrive una volta sola.
    """
    unici: List[str] = []
    for path in prerequisites:
        if path not in unici:
            unici.append(path)
    importati = unici[1:]
    righe = [_INTESTAZIONE,
             f"{_scappa(target, target=True)}: "
             + " ".join(_scappa(p, target=False) for p in unici)]
    righe.extend(f"{_scappa(p, target=True)}:" for p in importati)
    return "\n".join(righe) + "\n"


def write_depfile(path: str, target: str,
                  prerequisites: Sequence[str]) -> str:
    """Scrive la depfile in `path`; ritorna `path`.

    Per sostituzione (`os.replace`) e mai sul posto: il Makefile la include
    a ogni `make`, e una depfile scritta a meta' da un render interrotto
    fermerebbe anche i make dopo. La cartella si crea se manca.
    """
    testo = make_depfile(target, prerequisites)
    cartella = os.path.dirname(path) or '.'
    os.makedirs(cartella, exist_ok=True)
    fd, temporaneo = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.", suffix='.tmp', dir=cartella)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(testo)
        os.replace(temporaneo, path)
    except BaseException:
        if os.path.exists(temporaneo):
            os.unlink(temporaneo)
        raise
    return path
