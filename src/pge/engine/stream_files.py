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

from pge.shared.exceptions import (
    ConfigError, InvalidFieldValueError, StreamFileChainError, StreamFileCountError,
    StreamFileDuplicateIdError, StreamFileKeyError,
)


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
    file_per_indice = {}
    for indice, voce in enumerate(data['streams']):
        if not (isinstance(voce, dict) and 'file' in voce):
            risolti.append(voce)
            continue
        if not (isinstance(voce['file'], str) and voce['file']):
            err = InvalidFieldValueError(
                f"streams[{indice}].file", voce['file'],
                hint="'file:' vuole il path di un documento YAML con un solo "
                     "stream, relativo alla cartella del master")
            err.config_file = master_path
            raise err
        origine = StreamFileOrigin(
            master=master_path, index=indice, file=voce['file'],
            path=os.path.join(cartella, voce['file']))
        file_per_indice[indice] = voce['file']
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
        stream = _stream_unico(importato, origine)
        # Regola 3: niente catene. Si guarda la chiave e non il valore: un
        # `file:` qualunque nello stream importato e' una catena cominciata.
        if 'file' in stream:
            raise StreamFileChainError(origine, stream['file'])
        risolto = {k: v for k, v in stream.items()
                   if k not in CHIAVI_DI_PIAZZAMENTO}
        piazzamento = {k: voce[k] for k in CHIAVI_DI_PIAZZAMENTO
                       if k in voce}
        if piazzamento.get('stream_id') is None:
            piazzamento['stream_id'] = os.path.splitext(
                os.path.basename(voce['file']))[0]
        risolti.append({**piazzamento, **risolto})

    _rifiuta_id_duplicati(master_path, risolti, file_per_indice)
    return {**data, 'streams': risolti}


def _stream_unico(documento, origine):
    """L'unico stream del documento importato, o `StreamFileCountError`.

    Ogni forma che non e' «una lista `streams:` con un mapping dentro» e' lo
    stesso errore; quel che cambia e' la riga `Trovati:`, che dice quale
    forma e' stata letta.
    """
    if not isinstance(documento, dict):
        if documento is None:
            raise StreamFileCountError(origine, 'nessuno stream')
        raise StreamFileCountError(
            origine, f"il documento non e' una mappa "
                     f"({type(documento).__name__})")
    streams = documento.get('streams')
    if streams is None:
        raise StreamFileCountError(origine, 'nessuno stream')
    if not isinstance(streams, list):
        raise StreamFileCountError(
            origine, f"'streams' non e' una lista "
                     f"({type(streams).__name__})")
    if len(streams) != 1:
        raise StreamFileCountError(
            origine,
            'nessuno stream' if not streams else f'{len(streams)} stream')
    (stream,) = streams
    if not isinstance(stream, dict):
        raise StreamFileCountError(
            origine, f"una voce che non e' uno stream "
                     f"({type(stream).__name__})")
    return stream


def _rifiuta_id_duplicati(master_path, streams, file_per_indice):
    """Regola 7: un id effettivo condiviso da due voci, se una e' `file:`.

    L'id effettivo e' la stringa: e' cosi' che diventa il nome dello stem e
    la chiave del manifest della cache, quindi `1` e `'1'` collidono. Le voci
    che non sono mapping, o che non dichiarano un id, non partecipano: il loro
    errore e' di un altro, e arriva dallo `Stream`.
    """
    if not file_per_indice:
        return
    per_id = {}
    for indice, stream in enumerate(streams):
        if isinstance(stream, dict) and stream.get('stream_id') is not None:
            per_id.setdefault(str(stream['stream_id']), []).append(indice)
    for stream_id, indici in per_id.items():
        if len(indici) > 1 and any(i in file_per_indice for i in indici):
            raise StreamFileDuplicateIdError(
                master_path, stream_id,
                [(i, file_per_indice.get(i)) for i in indici])
