# src/score_writer.py
"""
ScoreWriter: gestione scrittura file .sco Csound.
Separato dalla logica di orchestrazione.
"""
from typing import List
from core.stream import Stream
from core.cartridge import Cartridge
from rendering.ftable_manager import FtableManager
from envelopes.envelope import Envelope
from parameters.parameter import Parameter


class ScoreWriter:
    """
    Scrive lo score Csound su file.
    
    Responsabilita:
    - Formattare header e metadati
    - Delegare scrittura ftables a FtableManager
    - Scrivere eventi grani (Stream)
    - Scrivere eventi cartridges (TapeRecorder)
    - Gestire commenti e statistiche
    """
    
    def __init__(self, ftable_manager: FtableManager):
        """
        Args:
            ftable_manager: manager delle function tables
        """
        self.ftable_manager = ftable_manager
    
    def write_score(
        self,
        filepath: str,
        streams: List[Stream],
        cartridges: List[Cartridge],
        yaml_source: str = None,
        per_stream: bool = False,
    ):
        """
        Scrive score completo su file.
        
        Args:
            filepath: percorso file output .sco
            streams: lista stream granulari
            cartridges: lista cartridges tape recorder
            yaml_source: path file YAML sorgente (per header)
            per_stream: se True, onset dei grani relativo a stream.onset (STEMS mode)
        """
        with open(filepath, 'w') as f:
            self._write_header(f, yaml_source)
            self.ftable_manager.write_to_file(f)
            self._write_events(f, streams, cartridges, per_stream=per_stream)
            self._write_footer(f)
        
        self._print_generation_summary(filepath, streams, cartridges)
    
    # =========================================================================
    # SEZIONI PRINCIPALI
    # =========================================================================
    
    def _write_header(self, f, yaml_source: str = None):
        """Scrive intestazione file score."""
        f.write("; " + "="*77 + "\n")
        f.write("; CSOUND SCORE\n")
        if yaml_source:
            f.write(f"; Generated from: {yaml_source}\n")
        f.write("; " + "="*77 + "\n\n")
    
    def _write_events(self, f, streams: List[Stream], cartridges: List[Cartridge], per_stream: bool = False):
        """Scrive tutti gli eventi (grani + cartridges)."""
        if streams:
            self._write_granular_streams(f, streams, per_stream=per_stream)

        if cartridges:
            self._write_tape_recorder_cartridges(f, cartridges)
    
    def _write_footer(self, f):
        """Scrive chiusura file score."""
        f.write("\n; " + "="*77 + "\n")
        f.write("; End of score\n")
        f.write("; " + "="*77 + "\n")
        f.write("e\n")
    
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
        f.write("; " + "="*77 + "\n")
        f.write("; GRANULAR STREAMS\n")
        f.write("; " + "="*77 + "\n\n")

        for stream in streams:
            onset_offset = stream.onset if per_stream else 0.0
            self._write_stream_section(f, stream, onset_offset=onset_offset)
    
    def _write_stream_section(self, f, stream: Stream, onset_offset: float = 0.0):
        """Scrive sezione completa di uno stream.

        Args:
            onset_offset: sottratto dall'onset di ogni grain (STEMS mode).
        """
        # Header stream
        f.write(f'; Stream: {stream.stream_id}\n')
        self._write_stream_metadata(f, stream)

        # Eventi grani per voice
        for voice_index, voice_grains in enumerate(stream.voices):
            if voice_grains:  # Solo se la voice ha grani
                f.write(f';   Voice {voice_index} ({len(voice_grains)} grains)\n')

                for grain in voice_grains:
                    f.write(grain.to_score_line(onset_offset=onset_offset))

                f.write('\n')  # Separatore tra voices

        f.write('\n')  # Separatore tra streams
    
    def _write_stream_metadata(self, f, stream: Stream):
        """
        Scrive metadati dello stream come commenti.
        
        Formatta parametri gestendo Envelope e valori dinamici.
        """
        # Grain parameters
        f.write(f'; Grain duration: {self._format_param(stream.grain_duration, 1000, "ms")}\n')
        
        # Density parameters
        f.write(f'; Density: {self._format_param(stream.density, 1, " g/s")}\n')
        f.write(f'; Distribution: {self._format_param(stream.distribution)}\n')
                
        # Statistiche
        f.write(f'; Num voices: {self._format_param(stream.num_voices)}\n')
        total_grains = sum(len(voice_grains) for voice_grains in stream.voices)
        f.write(f'; Total grains: {total_grains}\n\n')
    
    # =========================================================================
    # TAPE RECORDER cartridges
    # =========================================================================
    
    def _write_tape_recorder_cartridges(self, f, cartridges: List[Cartridge]):
        """Scrive sezione cartridges tape recorder."""
        f.write("; " + "="*77 + "\n")
        f.write("; TAPE RECORDER TRACKS\n")
        f.write("; " + "="*77 + "\n\n")
        
        for Cartridge in cartridges:
            self._write_cartridge_section(f, Cartridge)
    
    def _write_cartridge_section(self, f, Cartridge: Cartridge):
        """Scrive sezione completa di una Cartridge."""
        # Header Cartridge
        f.write(f'; Cartridge: {Cartridge.cartridge_id}\n')
        f.write(f'; Sample: {Cartridge.sample_path}\n')
        f.write(f'; Speed: {Cartridge.speed}x (resampling)\n')
        f.write(f'; Duration: {Cartridge.duration}s\n\n')
        
        # Evento Cartridge
        f.write(Cartridge.to_score_line())
        f.write('\n')
    
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
        cartridges: List[Cartridge]
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
        
        # cartridges
        if cartridges:
            print(f"  - {len(cartridges)} cartridges tape recorder")