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

L'escaping dei nomi non e' un dettaglio: la depfile e' inclusa da ogni
`make`, quindi una riga che make non sa leggere non costa questo render --
ferma tutti i `make` dopo, `make clean` compreso, cioe' il comando con cui
se ne uscirebbe. Quel che si scappa si scappa (`_DA_SCAPPARE`), e quel che
non si scappa in make e' un errore qui, che nomina il file
(`_IRRAPPRESENTABILI`, `_VIETATI_IN_TARGET`).

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


#: I caratteri che vogliono un backslash in entrambe le posizioni. Lo spazio
#: e il tab perche' make separa i file sugli spazi bianchi; `:` perche'
#: separa i target dai prerequisiti e lasciato nudo da' «multiple target
#: patterns»; `|` perche' e' il separatore dei prerequisiti order-only, e
#: nudo manda make a cercare una regola per la meta' sinistra del nome. `#`
#: apre un commento. Il tab, `:` e `|` non erano scappati, e tutti e tre sono
#: legali in un nome di file POSIX. Il backslash basta solo fra i
#: prerequisiti: in posizione di target due dei tre non si scrivono affatto
#: (`_VIETATI_IN_TARGET`). (Il `:` di una lettera di unita' Windows non si
#: scappa cosi', ma le ricette di `make/build.mk` girano su macOS e Linux.)
_DA_SCAPPARE = ('#', ' ', '\t', ':', '|')

#: Caratteri che make non sa leggere in una lista di file in *nessuna*
#: posizione: il backslash non li salva, quindi una depfile che li contenesse
#: non si scrive affatto. La depfile e' inclusa da ogni `make`, e una riga che
#: make non legge non ferma questo render: ferma tutti i `make` dopo, `make
#: clean` compreso, cioe' il comando con cui se ne uscirebbe. Meglio un
#: errore qui, che nomina il file.
_IRRAPPRESENTABILI = {
    '\n': 'un a capo',
    '\r': 'un ritorno a capo',
    # Apre la ricetta: fra i prerequisiti make cerca una regola per la meta'
    # sinistra del nome, in posizione di target da' «missing separator».
    # `\;` non lo salva ne' qui ne' la'.
    ';': 'un punto e virgola',
}

#: E i caratteri che sono un guaio in posizione di target soltanto: fra i
#: prerequisiti si scrivono (letterali o col backslash), in testa a una riga
#: no. Misurati contro GNU make, uno per uno:
#:
#: - `=`: make legge l'intera riga come un assegnamento di variabile
#:   (`out/a = b.aif: m.yml`), quindi la regola non esiste -- e in silenzio,
#:   che qui e' il modo peggiore;
#: - `|` e il tab: col backslash make li accetta *fra* i prerequisiti, ma in
#:   testa a una riga non registra il target, e un file sparito torna a
#:   fermare make con «No rule to make target» -- cioe' proprio il guasto che
#:   la regola vuota della `-MP` esiste per evitare, senza dirlo.
#:
#: Dove il target e' il file che si rende, e' un errore: quella riga e' la
#: depfile. Dove e' una regola vuota della `-MP`, si omette la regola (vedi
#: `make_depfile`).
_VIETATI_IN_TARGET = {
    '=': 'un uguale',
    '|': 'una barra verticale',
    '\t': 'un tab',
}


def _scrivibile_come_target(path: str) -> bool:
    """Se `path` si puo' scrivere in testa a una riga della depfile."""
    return not any(c in path for c in _VIETATI_IN_TARGET)


def _scappa(path: str, target: bool) -> str:
    """Un path come make lo legge in una lista di file.

    `$` raddoppiato, e dietro un backslash `#`, lo spazio, il tab, `:` e `|`:
    e' la grafia di gcc, verificata contro GNU make
    (`tests/export/test_depfile_writer.py`, che fa leggere ogni grafia a un
    make vero). `%` solo in posizione di target, dove fa di una regola una
    regola a pattern; fra i prerequisiti e' letterale, e `\\%` lo resterebbe
    col backslash.

    Raises:
        ValueError: se il path porta un carattere che make non sa leggere --
            `_IRRAPPRESENTABILI` in ogni posizione, `_VIETATI_IN_TARGET` in
            testa a una riga.
    """
    for carattere, nome in _IRRAPPRESENTABILI.items():
        if carattere in path:
            raise ValueError(
                f"path con {nome}, non rappresentabile in una depfile di "
                f"make: {path!r}")
    if target:
        for carattere, nome in _VIETATI_IN_TARGET.items():
            if carattere in path:
                raise ValueError(
                    f"path con {nome} in posizione di target, non "
                    f"rappresentabile in una depfile di make: {path!r}")
    path = path.replace('$', '$$')
    for carattere in _DA_SCAPPARE:
        path = path.replace(carattere, '\\' + carattere)
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
    # La regola vuota della `-MP` e' un'aggiunta, la riga sopra e' la
    # dipendenza: un file importato che non si scrive in posizione di target
    # (`_VIETATI_IN_TARGET`) perde la sua regola vuota e tiene la dipendenza,
    # che fra i prerequisiti si scrive. Fallire tutta la depfile per
    # l'aggiunta sarebbe peggio del guasto che l'aggiunta evita (un file
    # sparito ferma make invece di rifare il render).
    righe.extend(f"{_scappa(p, target=True)}:" for p in importati
                 if _scrivibile_come_target(p))
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
