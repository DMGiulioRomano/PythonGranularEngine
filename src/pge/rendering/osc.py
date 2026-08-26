# src/pge/rendering/osc.py
"""
Encoder OSC 1.0 e scrittore di score NRT per scsynth (issue #228).

Perche' vive qui e non in una dipendenza: il backend SuperCollider ha
bisogno di un solo verso (scrivere) e di sei tipi (int32, float32, stringa,
blob, bundle, timetag). Una libreria OSC completa porterebbe il parsing, il
trasporto UDP e la gestione dei pattern, che qui non servono a nulla; il
formato, invece, e' congelato dal 2002 e sta in un centinaio di righe.

Regole di formato (OSC 1.0):
- stringa: ASCII, terminatore nullo, paddata con nulli a multipli di 4 byte
  (una stringa gia' allineata riceve comunque 4 nulli: il terminatore c'e'
  sempre);
- int32 / float32: big-endian;
- blob: int32 con la lunghezza dei DATI, poi i dati, poi il padding a 4;
- messaggio: address + type tag string (`,` seguito da un tag per argomento)
  + argomenti;
- bundle: `#bundle\\0` + timetag a 64 bit + elementi, ognuno preceduto dalla
  propria lunghezza int32.

Il file letto da `scsynth -N` (qui `write_nrt_score`) non ha header: e' la
concatenazione dei bundle, ognuno preceduto dalla propria lunghezza int32
big-endian. In NRT il timetag NON e' un istante NTP assoluto ma il tempo
trascorso dall'inizio del render, cosi' come lo scrive la classe `Score` di
SuperCollider.
"""
from __future__ import annotations

import struct
from typing import Iterable, List, Sequence, Union


# Un timetag NTP a 64 bit: 32 bit di secondi + 32 bit di frazione.
_FRACTION_SCALE = 2 ** 32

OscArg = Union[int, float, str, bytes, bytearray]


def _pad(data: bytes) -> bytes:
    """Padding con nulli fino al multiplo di 4 successivo."""
    remainder = len(data) % 4
    return data if remainder == 0 else data + b'\x00' * (4 - remainder)


def encode_string(value: str) -> bytes:
    """Stringa OSC: ASCII + terminatore nullo + padding a multipli di 4."""
    return _pad(value.encode('ascii') + b'\x00')


def encode_int32(value: int) -> bytes:
    """Intero con segno a 32 bit, big-endian."""
    return struct.pack('>i', int(value))


def encode_float32(value: float) -> bytes:
    """Float a singola precisione, big-endian.

    La perdita di precisione da float64 e' del formato, non nostra: OSC non
    ha un tipo a doppia precisione fra quelli che scsynth accetta per gli
    argomenti dei comandi.
    """
    return struct.pack('>f', float(value))


def encode_blob(data: bytes) -> bytes:
    """Blob OSC: int32 con la lunghezza dei dati, poi i dati paddati.

    La lunghezza dichiarata e' quella dei dati, non quella del blocco
    paddato: il lettore deve sapere dove finiscono i dati veri.
    """
    return encode_int32(len(data)) + _pad(bytes(data))


def encode_timetag(seconds: float) -> bytes:
    """Timetag NTP a 64 bit dal tempo in secondi.

    In NRT il tempo e' relativo all'inizio del render (0.0 = istante zero),
    non all'epoca NTP.

    Raises:
        ValueError: se il tempo e' negativo. In uno score NRT non esiste un
            "prima dello zero": sarebbe un secondo campo unsigned che va in
            wrap, cioe' un evento sparato alla fine del render.
    """
    if seconds < 0:
        raise ValueError(
            f"Timetag negativo non rappresentabile in uno score NRT: {seconds!r}"
        )
    whole = int(seconds)
    # min(): un tempo appena sotto l'intero successivo arrotonderebbe a 2**32,
    # che nel campo frazionario non ci sta e diventerebbe un secondo in piu'.
    fraction = min(_FRACTION_SCALE - 1,
                   int(round((seconds - whole) * _FRACTION_SCALE)))
    return struct.pack('>II', whole, fraction)


def message(address: str, *args: OscArg) -> bytes:
    """Messaggio OSC: address + type tag string + argomenti.

    Tipi supportati (gli unici che i comandi di scsynth usano):
    int -> 'i', float -> 'f', str -> 's', bytes -> 'b'.

    Raises:
        TypeError: per qualunque altro tipo. Meglio un errore in fase di
            scrittura che un byte stream che scsynth rifiuta senza dire dove.
    """
    tags = [',']
    payload: List[bytes] = []

    for arg in args:
        # bool prima di int: in Python bool e' sottoclasse di int, e un True
        # che arriva qui e' quasi sempre una svista del chiamante. Lo si
        # normalizza a 0/1 invece di lasciarlo passare per caso.
        if isinstance(arg, bool):
            tags.append('i')
            payload.append(encode_int32(1 if arg else 0))
        elif isinstance(arg, int):
            tags.append('i')
            payload.append(encode_int32(arg))
        elif isinstance(arg, float):
            tags.append('f')
            payload.append(encode_float32(arg))
        elif isinstance(arg, str):
            tags.append('s')
            payload.append(encode_string(arg))
        elif isinstance(arg, (bytes, bytearray)):
            tags.append('b')
            payload.append(encode_blob(arg))
        else:
            raise TypeError(
                f"Tipo non serializzabile in OSC: {type(arg).__name__} "
                f"({arg!r}). Validi: int, float, str, bytes."
            )

    return encode_string(address) + encode_string(''.join(tags)) + b''.join(payload)


def bundle(time: float, elements: Sequence[bytes]) -> bytes:
    """Bundle OSC: header + timetag + elementi size-prefixed.

    Un bundle senza elementi e' legale ed e' l'idioma con cui si dichiara la
    durata del render: l'ultimo bundle di uno score NRT fissa l'istante in
    cui scsynth smette di produrre campioni.
    """
    parts = [b'#bundle\x00', encode_timetag(time)]
    for element in elements:
        parts.append(encode_int32(len(element)))
        parts.append(element)
    return b''.join(parts)


def write_nrt_score(path: str, bundles: Iterable[bytes]) -> str:
    """Scrive il file .osc letto da `scsynth -N`.

    Nessun header: la concatenazione dei bundle, ognuno preceduto dalla
    propria lunghezza int32 big-endian.

    Returns:
        Il path scritto.
    """
    with open(path, 'wb') as f:
        for data in bundles:
            f.write(encode_int32(len(data)))
            f.write(data)
    return path
