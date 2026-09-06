# src/score_writer.py
"""
ScoreWriter: gestione scrittura file .sco Csound.
Separato dalla logica di orchestrazione.
"""
from __future__ import annotations

from typing import List, Optional

from pge.core.stream import Stream
from pge.rendering.csound_emitter import CsoundEmitter
from pge.rendering.ftable_manager import FtableManager
from pge.envelopes.envelope import Envelope
from pge.parameters.parameter import Parameter


class ScoreWriter:
    """
    Scrive lo score Csound su file.

    Responsabilita:
    - Formattare header e metadati
    - Disporre le sezioni del file
    - Scrivere eventi grani (Stream)
    - Gestire commenti e statistiche

    La sintassi la costruisce `CsoundEmitter` (issue #203) -- gli statement
    dei grani e delle tabelle, la `e` di fine score, e anche il `;` dei
    commenti e i separatori di sezione: qui si decide *cosa* dire e in che
    ordine, non come lo si scrive.
    """

    def __init__(
        self,
        ftable_manager: FtableManager,
        emitter: Optional[CsoundEmitter] = None,
    ):
        """
        Args:
            ftable_manager: manager delle function tables
            emitter: generatore di sintassi Csound (default: `CsoundEmitter()`)
        """
        self.ftable_manager = ftable_manager
        # `is None` e non `or`: un emitter falsy -- ne basta uno che definisca
        # __len__ -- verrebbe scartato in silenzio e lo score uscirebbe in
        # Csound, che e' esattamente cio' che il parametro serve a evitare.
        self.emitter = CsoundEmitter() if emitter is None else emitter

    def write_score(
        self,
        filepath: str,
        streams: List[Stream],
        yaml_source: str = None,
        per_stream: bool = False,
    ):
        """
        Scrive score completo su file.

        Args:
            filepath: percorso file output .sco
            streams: lista stream granulari
            yaml_source: path file YAML sorgente (per header)
            per_stream: se True, onset dei grani relativo a stream.onset (STEMS mode)
        """
        with open(filepath, 'w') as f:
            self._write_header(f, yaml_source)
            self.emitter.write_ftables(f, self.ftable_manager.get_all_tables())
            self._write_events(f, streams, per_stream=per_stream)
            self._write_footer(f)

        self._print_generation_summary(filepath, streams)

    # =========================================================================
    # SEZIONI PRINCIPALI
    # =========================================================================

    def _write_header(self, f, yaml_source: str = None):
        """Scrive intestazione file score."""
        f.write(self.emitter.rule())
        f.write(self.emitter.comment("CSOUND SCORE"))
        if yaml_source:
            f.write(self.emitter.comment(f"Generated from: {yaml_source}"))
        f.write(self.emitter.rule() + "\n")

    def _write_events(self, f, streams: List[Stream], per_stream: bool = False):
        """Scrive tutti gli eventi (grani)."""
        if streams:
            self._write_granular_streams(f, streams, per_stream=per_stream)

    def _write_footer(self, f):
        """Scrive chiusura file score."""
        f.write("\n" + self.emitter.rule())
        f.write(self.emitter.comment("End of score"))
        f.write(self.emitter.rule())
        f.write(self.emitter.end_statement())

    # =========================================================================
    # GRANULAR STREAMS
    # =========================================================================

    def _write_granular_streams(self, f, streams: List[Stream], per_stream: bool = False):
        """
        Scrive sezione stream granulari.

        Per ogni stream:
        - Intestazione con metadati
        - Eventi grani organizzati per voice
        """
        f.write(self.emitter.rule())
        f.write(self.emitter.comment("GRANULAR STREAMS"))
        f.write(self.emitter.rule() + "\n")

        for stream in streams:
            onset_offset = stream.onset if per_stream else 0.0
            self._write_stream_section(f, stream, onset_offset=onset_offset)

    def _write_stream_section(self, f, stream: Stream, onset_offset: float = 0.0):
        """Scrive sezione completa di uno stream.

        Args:
            onset_offset: sottratto dall'onset di ogni grain (STEMS mode).
        """
        # Header stream
        f.write(self.emitter.comment(f'Stream: {stream.stream_id}'))
        self._write_stream_metadata(f, stream)

        # Un'i-statement per grano, per milioni di grani: il metodo si risolve
        # una volta per sezione invece che a ogni riga.
        grain_statement = self.emitter.grain_statement

        # Eventi grani per voice
        for voice_index, voice_grains in enumerate(stream.voices):
            if voice_grains:  # Solo se la voice ha grani
                f.write(self.emitter.comment(
                    f'  Voice {voice_index} ({len(voice_grains)} grains)'))

                for grain in voice_grains:
                    f.write(grain_statement(grain, onset_offset=onset_offset))

                f.write('\n')  # Separatore tra voices

        f.write('\n')  # Separatore tra streams

    def _write_stream_metadata(self, f, stream: Stream):
        """
        Scrive metadati dello stream come commenti.

        Formatta parametri gestendo Envelope e valori dinamici.
        """
        comment = self.emitter.comment

        # Grain parameters
        f.write(comment(
            f'Grain duration: {self._format_param(stream.grain_duration, 1000, "ms")}'))

        # Density parameters
        f.write(comment(f'Density: {self._format_param(stream.density, 1, " g/s")}'))
        f.write(comment(f'Distribution: {self._format_param(stream.distribution)}'))

        # Statistiche
        f.write(comment(f'Num voices: {self._format_param(stream.num_voices)}'))
        total_grains = sum(len(voice_grains) for voice_grains in stream.voices)
        f.write(comment(f'Total grains: {total_grains}') + '\n')

    # =========================================================================
    # UTILITY - FORMATTAZIONE PARAMETRI
    # =========================================================================

    def _format_param(
        self,
        param,
        multiplier: float = 1.0,
        unit: str = ''
    ) -> str:
        """
        Formatta un parametro per i commenti SCO.

        Gestisce:
        - Parameter objects (estrae value)
        - Envelope (indica "dynamic")
        - None (restituisce "N/A")
        - Numeri (applica moltiplicatore e unità)

        Args:
            param: parametro da formattare
            multiplier: moltiplicatore per conversione unità
            unit: stringa unità di misura

        Returns:
            str: parametro formattato per commento
        """
        # Estrai valore da Parameter
        if isinstance(param, Parameter):
            param = param._value

        # Gestisci casi speciali
        if param is None:
            return "N/A"

        if isinstance(param, Envelope):
            return "dynamic (envelope)"

        # Formatta numero
        try:
            value = float(param) * multiplier
            # Sotto 0.1 un solo decimale collasserebbe a 0.0 (es. grani da
            # 1 campione = 0.0208 ms): servono piu' cifre significative.
            if 0 < abs(value) < 0.1:
                return f"{value:.4f}{unit}"
            return f"{value:.1f}{unit}"
        except (ValueError, TypeError):
            # Fallback se non è un numero
            return str(param)

    # =========================================================================
    # UTILITY - STATISTICHE
    # =========================================================================

    def _print_generation_summary(
        self,
        filepath: str,
        streams: List[Stream],
    ):
        """Stampa riepilogo generazione score."""
        print(f"✓ Score generato: {filepath}")

        # Function tables
        num_tables = len(self.ftable_manager.get_all_tables())
        print(f"  - {num_tables} function tables")

        # Streams e grani
        if streams:
            total_grains = sum(
                sum(len(voice_grains) for voice_grains in stream.voices)
                for stream in streams
            )
            print(f"  - {len(streams)} streams granulari")
            print(f"  - {total_grains} grani totali")
