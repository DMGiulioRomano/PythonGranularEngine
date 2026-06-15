"""
FtableManager: gestione centralizzata delle function tables Csound.
Separato dalla logica di orchestrazione.
"""
from __future__ import annotations

from typing import Dict, Tuple, Optional
from controllers.window_registry import WindowRegistry

class FtableManager:
    """
    Gestisce allocazione e deduplicazione function tables.
    """
    
    def __init__(self, start_num: int = 1):
        """
        Args:
            start_num: primo numero tabella disponibile
        """
        self.tables: Dict[int, Tuple[str, str]] = {}  
        self.next_num = start_num
        self._sample_cache: Dict[str, int] = {}  
        self._window_cache: Dict[str, int] = {}
    
    def register_sample(self, sample_path: str) -> int:
        """
        Registra sample (con deduplicazione).
        
        Returns:
            int: numero tabella
        """
        if sample_path in self._sample_cache:
            return self._sample_cache[sample_path]
        
        num = self.next_num
        self.next_num += 1
        self.tables[num] = ('sample', sample_path)
        self._sample_cache[sample_path] = num
        return num
    
    def register_window(self, window_name: str) -> int:
        """
        Registra window (con deduplicazione).
        
        Returns:
            int: numero tabella
        """
        if window_name in self._window_cache:
            return self._window_cache[window_name]
        
        # Valida che la window esista nel registro
        if WindowRegistry.get(window_name) is None:
            from shared.exceptions import InvalidWindowError
            raise InvalidWindowError(
                name=window_name,
                available=list(WindowRegistry.all_names()),
            )
        
        num = self.next_num
        self.next_num += 1
        self.tables[num] = ('window', window_name)
        self._window_cache[window_name] = num
        return num
    
    # =========================================================================
    # AGGIUNTE CONSIGLIATE
    # =========================================================================
    
    def get_sample_table_num(self, sample_path: str) -> Optional[int]:
        """
        Ottieni numero tabella per sample (se già registrato).
        
        Returns:
            int se registrato, None altrimenti
        """
        return self._sample_cache.get(sample_path)
    
    def get_window_table_num(self, window_name: str) -> Optional[int]:
        """
        Ottieni numero tabella per window (se già registrata).
        
        Returns:
            int se registrata, None altrimenti
        """
        return self._window_cache.get(window_name)
    
    def get_all_tables(self) -> Dict[int, Tuple[str, str]]:
        """
        Ritorna copia di tutte le tabelle registrate.
        
        Returns:
            dict: {table_num: (ftype, key)}
        """
        return dict(self.tables)
    
    def __repr__(self) -> str:
        """Rappresentazione per debugging."""
        n_samples = len(self._sample_cache)
        n_windows = len(self._window_cache)
        return (f"FtableManager(tables={len(self.tables)}, "
                f"samples={n_samples}, windows={n_windows}, "
                f"next_num={self.next_num})")
    
    # =========================================================================
    # SCRITTURA FILE SCORE
    # =========================================================================
    
    def write_to_file(self, f) -> None:
        """Scrive tutte le ftables nel file score Csound."""
        f.write("; " + "="*77 + "\n")
        f.write("; FUNCTION TABLES\n")
        f.write("; " + "="*77 + "\n\n")
        
        for num, (ftype, key) in sorted(self.tables.items()):
            if ftype == 'sample':
                f.write(f'; Sample: {key}\n')
                f.write(f'f {num} 0 0 1 "{key}" 0 0 1\n\n')
            
            elif ftype == 'window':
                spec = WindowRegistry.get(key)
                
                # ERROR HANDLING AGGIUNTO
                if spec is None:
                    from shared.exceptions import FtableError
                    raise FtableError(
                        key=key,
                        reason=(
                            f"Window '{key}' non trovata nel WindowRegistry. "
                            f"Stato incoerente: register_window() avrebbe dovuto "
                            f"validarla."
                        ),
                    )
                
                f.write(f'; Window: {key} - {spec.description}\n')
                statement = WindowRegistry.generate_ftable_statement(num, key)
                f.write(f'{statement}\n\n')
