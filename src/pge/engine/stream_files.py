# src/pge/engine/stream_files.py
"""
Lo stream come file (issue #290).

Una voce della lista `streams:` del master puo' essere `- file: <path>`: lo
stream e' scritto in un altro documento YAML, un documento del laboratorio
che si apre e si rende anche da solo. Il master lo importa e ne decide il
piazzamento.

La risoluzione avviene in `Generator.load_yaml`, prima di tutto il resto --
anche delle espressioni matematiche, che valgono sullo stream importato come
su quello scritto nel master. Da li' in poi il motore vede una lista di stream
come prima: cache, fingerprint e solo/mute lavorano sullo stream gia'
risolto, e nessuno di loro deve sapere che `file:` esiste.
"""
from __future__ import annotations

import os
from typing import NamedTuple

from pge.shared.exceptions import ConfigError, StreamFileKeyError


#: Le chiavi che il master tiene accanto a `file:`. E' il piazzamento dello
#: stream nel brano, e soltanto quello.
CHIAVI_DI_PIAZZAMENTO = ('stream_id', 'onset', 'mute', 'solo')


class StreamFileOrigin(NamedTuple):
    """Da dove viene uno stream importato: la voce del master che lo nomina.

    E' cio' che gli errori leggono per nominare i due file, ed e' cio' che
    `Generator.stream_origins` conserva per ogni stream importato.
    """

    #: il path del master, come il Generator l'ha ricevuto
    master: str
    #: la posizione della voce nella lista `streams:` del master (da 0)
    index: int
    #: il valore di `file:`, come e' scritto nel master
    file: str
    #: il path del file importato, risolto sulla cartella del master
    path: str

    @property
    def entry(self) -> str:
        """La voce come la si scrive in un path del documento."""
        return f"streams[{self.index}]"


def resolve_stream_files(data, master_path, read):
    """La lista `streams:` del master con ogni voce `file:` risolta.

    Args:
        data: il documento del master come lo restituisce `yaml.safe_load`.
        master_path: il path del master: i `file:` sono relativi alla sua
            cartella.
        read: la funzione che legge un documento YAML dato il path. E' la
            stessa del master, cosi' un file importato che non si legge ha
            gli stessi tipi d'errore del master che non si legge.

    Returns:
        Il documento con le voci `file:` sostituite dallo stream che importano.
        Un documento senza voci `file:` torna identico.
    """
    if not isinstance(data, dict) or not isinstance(data.get('streams'), list):
        return data

    cartella = os.path.dirname(master_path)
    risolti = []
    for indice, voce in enumerate(data['streams']):
        if not (isinstance(voce, dict) and 'file' in voce):
            risolti.append(voce)
            continue
        origine = StreamFileOrigin(
            master=master_path, index=indice, file=voce['file'],
            path=os.path.join(cartella, voce['file']))
        # Regola 4: prima di leggere il file. L'errore sta nel master, e il
        # master si corregge anche se il file non c'e'.
        estranee = [k for k in voce
                    if k != 'file' and k not in CHIAVI_DI_PIAZZAMENTO]
        if estranee:
            raise StreamFileKeyError(origine, estranee, CHIAVI_DI_PIAZZAMENTO)
        # Regola 8: un file importato che non si legge ha i tipi del master
        # che non si legge (#257), perche' e' lo stesso guasto. Il messaggio
        # pero' deve dire chi lo stava cercando.
        try:
            importato = read(origine.path)
        except ConfigError as err:
            err.imported_by = origine
            raise
        stream = importato['streams'][0]
        risolto = {k: v for k, v in stream.items()
                   if k not in CHIAVI_DI_PIAZZAMENTO}
        piazzamento = {k: voce[k] for k in CHIAVI_DI_PIAZZAMENTO
                       if k in voce}
        if piazzamento.get('stream_id') is None:
            piazzamento['stream_id'] = os.path.splitext(
                os.path.basename(voce['file']))[0]
        risolti.append({**piazzamento, **risolto})

    return {**data, 'streams': risolti}
