"""
Test di accettazione della issue #203: l'output `.sco` byte per byte.

La issue #203 sposta la generazione di sintassi Csound fuori da `Grain`,
`FtableManager` e `WindowRegistry` verso un `CsoundEmitter` in `rendering/`.
E' un refactor a comportamento invariato: il criterio di riuscita non e' che
i moduli siano piu' puliti, e' che **il file prodotto non cambi di un byte**.

Percio' il golden e' scritto per intero e confrontato con `==`, non con una
serie di `in`: un `in` non vede una riga in piu', un separatore perso, un
commento spostato — cioe' esattamente le regressioni che un travaso di codice
produce. Se questo test diventa rosso dopo una modifica al formato, il golden
va aggiornato **di proposito**, in un commit che lo dichiara.

Il golden copre le quattro forme di f-statement in circolazione (GEN01 per il
sample, GEN20/GEN16/GEN09 per le finestre), una voice vuota (che va saltata
mantenendo la numerazione delle altre), un grano da un campione a 48 kHz (le
otto cifre decimali di p2/p3) e i due valori di `per_stream`.
"""
from __future__ import annotations

import io
import types
from contextlib import redirect_stdout

import pytest

from pge.core.grain import Grain
from pge.rendering.ftable_manager import FtableManager
from pge.rendering.score_writer import ScoreWriter


ONE_SAMPLE_48K = 1.0 / 48000


def _grain(onset, duration, ptr, ratio, vol, pan, sample_table, envelope_table):
    return Grain(
        onset=onset, duration=duration, pointer_pos=ptr, pitch_ratio=ratio,
        volume=vol, pan=pan,
        sample_table=sample_table, envelope_table=envelope_table,
    )


def _stream(stream_id, onset, voices, grain_duration, density, distribution, num_voices):
    """Stand-in per Stream con i soli attributi che ScoreWriter legge.

    Non e' uno Stream vero perche' costruirne uno richiede una config
    completa e un sample su disco: qui l'oggetto sotto esame e' il formato
    del testo, e i grani — quelli si' — sono `Grain` reali.
    """
    return types.SimpleNamespace(
        stream_id=stream_id, onset=onset, voices=voices,
        grain_duration=grain_duration, density=density,
        distribution=distribution, num_voices=num_voices,
    )


@pytest.fixture
def ftable_manager():
    fm = FtableManager(start_num=1)
    fm.register_sample('refs/voce.wav')
    fm.register_window('hanning')     # GEN20
    fm.register_window('expodec')     # GEN16
    fm.register_window('half_sine')   # GEN09
    return fm


@pytest.fixture
def streams():
    return [
        _stream(
            'stream1', 2.5,
            [
                [
                    _grain(2.5, 0.05, 0.25, 1.0, -6.0, 0.5, 1, 2),
                    _grain(2.5 + ONE_SAMPLE_48K, ONE_SAMPLE_48K,
                           0.5, 1.059463, -12.0, -1.0, 1, 3),
                ],
                [],  # voice vuota: saltata, ma la Voice 2 resta la 2
                [_grain(3.0, 0.1, 1.25, 0.5, 0.0, 1.0, 1, 4)],
            ],
            grain_duration=0.05, density=120.0, distribution=0.5, num_voices=3,
        ),
        _stream(
            'stream2', 0.0,
            [[_grain(0.0, ONE_SAMPLE_48K, 0.0, 2.0, -3.0, 0.0, 1, 2)]],
            grain_duration=ONE_SAMPLE_48K, density=4800.0,
            distribution=1.0, num_voices=1,
        ),
    ]


GOLDEN_ABSOLUTE = '''; =============================================================================
; CSOUND SCORE
; Generated from: configs/PGE_test.yml
; =============================================================================

; =============================================================================
; FUNCTION TABLES
; =============================================================================

; Sample: refs/voce.wav
f 1 0 0 1 "refs/voce.wav" 0 0 1

; Window: hanning - Hanning/von Hann window (GEN20 opt 2)
f 2 0 1024 20 2 1

; Window: expodec - Exponential decay (GEN16, Roads-style)
f 3 0 1024 16 1 1024 4 0

; Window: half_sine - Half-sine envelope (GEN09)
f 4 0 1024 9 0.5 1 0

; =============================================================================
; GRANULAR STREAMS
; =============================================================================

; Stream: stream1
; Grain duration: 50.0ms
; Density: 120.0 g/s
; Distribution: 0.5
; Num voices: 3.0
; Total grains: 3

;   Voice 0 (2 grains)
i "Grain" 2.50000000 0.05000000 0.250000 1.000000 -6.00 0.500 1 2
i "Grain" 2.50002083 0.00002083 0.500000 1.059463 -12.00 -1.000 1 3

;   Voice 2 (1 grains)
i "Grain" 3.00000000 0.10000000 1.250000 0.500000 0.00 1.000 1 4


; Stream: stream2
; Grain duration: 0.0208ms
; Density: 4800.0 g/s
; Distribution: 1.0
; Num voices: 1.0
; Total grains: 1

;   Voice 0 (1 grains)
i "Grain" 0.00000000 0.00002083 0.000000 2.000000 -3.00 0.000 1 2



; =============================================================================
; End of score
; =============================================================================
e
'''

# per_stream=True: cambia solo p2, che diventa relativo a stream.onset.
#
# La sostituzione e' su **righe intere**, non sul prefisso `i "Grain" p2 p3`:
# due grani di stream diversi possono condividere onset e durata, e un
# prefisso li riscriverebbe entrambi -- il golden atteso conterrebbe allora
# un onset che il writer non produce mai, e il test fallirebbe per una
# ragione che non ha niente a che vedere col codice sotto esame.
_PER_STREAM_ONSETS = {
    'i "Grain" 2.50000000 0.05000000 0.250000 1.000000 -6.00 0.500 1 2':
        'i "Grain" 0.00000000 0.05000000 0.250000 1.000000 -6.00 0.500 1 2',
    'i "Grain" 2.50002083 0.00002083 0.500000 1.059463 -12.00 -1.000 1 3':
        'i "Grain" 0.00002083 0.00002083 0.500000 1.059463 -12.00 -1.000 1 3',
    'i "Grain" 3.00000000 0.10000000 1.250000 0.500000 0.00 1.000 1 4':
        'i "Grain" 0.50000000 0.10000000 1.250000 0.500000 0.00 1.000 1 4',
}


def _to_per_stream(golden: str) -> str:
    """Riscrive gli onset riga per riga, e pretende di averle trovate tutte.

    Senza il conteggio, un ritocco alla fixture che cambia una di quelle
    righe lascerebbe la mappa muta invece che rossa: il golden per_stream
    tornerebbe identico a quello assoluto e il test verificherebbe l'altro
    caso due volte.
    """
    lines = golden.split('\n')
    rewritten = [_PER_STREAM_ONSETS.get(line, line) for line in lines]

    matched = sum(1 for line in lines if line in _PER_STREAM_ONSETS)
    assert matched == len(_PER_STREAM_ONSETS), (
        f"{matched} righe su {len(_PER_STREAM_ONSETS)} trovate nel golden "
        f"assoluto: la fixture e la mappa degli onset si sono disallineate."
    )

    return '\n'.join(rewritten)


GOLDEN_PER_STREAM = _to_per_stream(GOLDEN_ABSOLUTE)


def _write(ftable_manager, streams, tmp_path, per_stream):
    filepath = str(tmp_path / 'golden.sco')
    writer = ScoreWriter(ftable_manager)
    with redirect_stdout(io.StringIO()):
        writer.write_score(
            filepath, streams,
            yaml_source='configs/PGE_test.yml', per_stream=per_stream,
        )
    with open(filepath, 'r') as f:
        return f.read()


class TestScoreBytesUnchanged:
    """Il `.sco` completo, confrontato per intero."""

    def test_absolute_onsets(self, ftable_manager, streams, tmp_path):
        assert _write(ftable_manager, streams, tmp_path, False) == GOLDEN_ABSOLUTE

    def test_per_stream_onsets(self, ftable_manager, streams, tmp_path):
        assert _write(ftable_manager, streams, tmp_path, True) == GOLDEN_PER_STREAM

    def test_per_stream_touches_only_p2(self, ftable_manager, streams, tmp_path):
        """Le due varianti differiscono solo nelle righe i-statement.

        Se un giorno `per_stream` iniziasse a spostare anche le ftable o i
        commenti, i due golden lo direbbero; questo test lo dice anche quando
        i golden sono stati aggiornati entrambi insieme.
        """
        absolute = _write(ftable_manager, streams, tmp_path, False).splitlines()
        relative = _write(ftable_manager, streams, tmp_path, True).splitlines()

        assert len(absolute) == len(relative)
        for line_a, line_b in zip(absolute, relative):
            if line_a != line_b:
                assert line_a.startswith('i "Grain"')
                assert line_b.startswith('i "Grain"')
