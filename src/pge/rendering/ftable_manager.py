"""
FtableManager: allocatore dei numeri di function table.

E' la symbol table condivisa fra i back-end -- il renderer NumPy riceve la
stessa `table_map` nel costruttore, e lo score SuperCollider ne fa numeri di
buffer -- quindi alloca e deduplica, ma non scrive: la sintassi Csound delle
tabelle sta in `CsoundEmitter` (issue #203).
"""
from __future__ import annotations

from typing import Dict, Tuple, Optional
from pge.controllers.window_registry import WindowRegistry

class FtableManager:
    """
    Gestisce allocazione e deduplicazione function tables.

    Non conosce nessun target: chi materializza le tabelle legge
    `get_all_tables()`.
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
            from pge.shared.exceptions import InvalidWindowError
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
    
