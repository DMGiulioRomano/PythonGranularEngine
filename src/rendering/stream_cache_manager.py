# src/rendering/stream_cache_manager.py
"""
StreamCacheManager

Gestisce il caching incrementale degli stream granulari.

Responsabilita':
- Calcolare il fingerprint SHA-256 del dict YAML raw di ogni stream
- Persistere il manifest {stream_id: fingerprint} su disco come JSON
- Decidere quali stream sono dirty (fingerprint cambiato o .aif assente)
- Aggiornare il manifest dopo una build riuscita

Un stream e' dirty se:
  1. Il suo stream_id non e' nel manifest, oppure
  2. Il fingerprint corrente non corrisponde a quello salvato, oppure
  3. Il file .aif di output non esiste sul disco (con aif_path fornito)
"""

import hashlib
import json
import os
from typing import Dict, List, Optional


class StreamCacheManager:
    """
    Gestore del cache incrementale per gli stream granulari.

    Args:
        cache_path: path del file manifest JSON su disco
    """

    def __init__(self, cache_path: str):
        self.cache_path = cache_path

    # =========================================================================
    # FINGERPRINT
    # =========================================================================

    def compute_fingerprint(self, stream_dict: dict) -> str:
        """
        Calcola il fingerprint SHA-256 del dict YAML raw di uno stream.

        La serializzazione usa sort_keys=True per garantire stabilita'
        indipendentemente dall'ordine delle chiavi nel dict.

        Args:
            stream_dict: dict parametri dello stream dallo YAML

        Returns:
            Stringa esadecimale SHA-256 di 64 caratteri
        """
        serialized = json.dumps(stream_dict, sort_keys=True)
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    # =========================================================================
    # PERSISTENZA
    # =========================================================================

    def load(self) -> Dict[str, str]:
        """
        Carica il manifest dal disco.

        Returns:
            Dict {stream_id: fingerprint}, vuoto se il file non esiste
            o e' malformato.
        """
        if not os.path.exists(self.cache_path):
            return {}
        try:
            with open(self.cache_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, manifest: Dict[str, str]) -> None:
        """
        Salva il manifest su disco.

        Crea la directory genitore se non esiste.

        Args:
            manifest: dict {stream_id: fingerprint} da persistere
        """
        os.makedirs(os.path.dirname(self.cache_path) or '.', exist_ok=True)
        with open(self.cache_path, 'w') as f:
            json.dump(manifest, f, indent=2)

    # =========================================================================
    # DIRTY DETECTION
    # =========================================================================

    def is_dirty(self, stream_dict: dict, aif_path: Optional[str]) -> bool:
        """
        Determina se uno stream deve essere ricompilato.

        Args:
            stream_dict: dict parametri dello stream dallo YAML
            aif_path: path del file .aif di output, o None per ignorare
                      il check sul file

        Returns:
            True se lo stream e' dirty (deve essere ricompilato)

        Raises:
            ValueError: se stream_dict non contiene 'stream_id'
        """
        if 'stream_id' not in stream_dict:
            raise ValueError(
                "stream_dict deve contenere 'stream_id' per il lookup nel manifest"
            )

        stream_id = stream_dict['stream_id']
        manifest = self.load()

        if stream_id not in manifest:
            return True

        if manifest[stream_id] != self.compute_fingerprint(stream_dict):
            return True

        if aif_path is not None and not os.path.exists(aif_path):
            return True

        return False

    def get_dirty_stream_dicts(
        self,
        stream_dicts: List[dict],
        aif_dir: Optional[str],
    ) -> List[dict]:
        """
        Filtra una lista di stream dict restituendo solo quelli dirty.

        Il path del .aif per ogni stream e' calcolato come:
            {aif_dir}/{stream_id}.aif
        Se aif_dir e' None, il check sul file viene ignorato.

        Args:
            stream_dicts: lista di dict parametri stream dallo YAML
            aif_dir: directory dei file .aif di output, o None

        Returns:
            Lista dei soli stream dict che devono essere ricompilati
        """
        dirty = []
        for d in stream_dicts:
            if aif_dir is not None:
                stream_id = d.get('stream_id', '')
                aif_path = os.path.join(aif_dir, f"{stream_id}.aif")
            else:
                aif_path = None

            if self.is_dirty(d, aif_path=aif_path):
                dirty.append(d)

        return dirty

    # =========================================================================
    # AGGIORNAMENTO POST-BUILD
    # =========================================================================

    def update_after_build(self, stream_dicts: List[dict]) -> None:
        """
        Aggiorna il manifest con i fingerprint correnti degli stream buildati.

        Preserva le entry gia' presenti per gli stream non toccati.

        Args:
            stream_dicts: lista dei stream dict appena compilati
        """
        manifest = self.load()
        for d in stream_dicts:
            stream_id = d['stream_id']
            manifest[stream_id] = self.compute_fingerprint(d)
        self.save(manifest)