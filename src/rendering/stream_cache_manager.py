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
        if 'stream_id' not in stream_dict:
            raise ValueError(
                "stream_dict deve contenere 'stream_id' per il lookup nel manifest"
            )

        stream_id = stream_dict['stream_id']
        manifest = self.load()
        
        current_fp = self.compute_fingerprint(stream_dict)
        saved_fp = manifest.get(stream_id, 'NON_PRESENTE')
        #match = current_fp == saved_fp
        #aif_exists = os.path.exists(aif_path) if aif_path is not None else 'N/A'
        #print(f"[CACHE DEBUG] {stream_id}: match={match} aif_path={aif_path} aif_exists={aif_exists}", flush=True)

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
        aif_prefix: Optional[str] = None,
    ) -> List[dict]:
        dirty = []
        for d in stream_dicts:
            stream_id = d.get('stream_id', '')
            if aif_dir is not None:
                filename = f"{aif_prefix}_{stream_id}.aif" if aif_prefix else f"{stream_id}.aif"
                aif_path = os.path.join(aif_dir, filename)
            else:
                aif_path = None

            dirty_flag = self.is_dirty(d, aif_path=aif_path)
            status = "DIRTY" if dirty_flag else "clean"
            print(f"[CACHE] {stream_id}: {status}", flush=True)

            if dirty_flag:
                dirty.append(d)

        print(f"[CACHE] {len(dirty)}/{len(stream_dicts)} stream da ricompilare", flush=True)
        return dirty

    # =========================================================================
    # AGGIORNAMENTO POST-BUILD
    # =========================================================================

    def garbage_collect(
        self,
        current_stream_ids: List[str],
        aif_dir: Optional[str] = None,
        aif_prefix: Optional[str] = None,
    ) -> List[str]:
        """
        Rimuove dal manifest le entry di stream non piu' presenti nel YAML corrente.
        Cancella i file .aif orfani se aif_dir e' specificato.

        Args:
            current_stream_ids: lista degli stream_id attualmente nel YAML
            aif_dir: directory dove cercare i file .aif (None = non toccare filesystem)
            aif_prefix: prefisso del nome file (es. 'PGE_test' → 'PGE_test_{sid}.aif')

        Returns:
            Lista degli stream_id rimossi (orfani)
        """
        manifest = self.load()
        current_ids = set(current_stream_ids)
        stale_ids = [sid for sid in manifest if sid not in current_ids]

        for sid in stale_ids:
            if aif_dir is not None:
                filename = f"{aif_prefix}_{sid}.aif" if aif_prefix else f"{sid}.aif"
                aif_path = os.path.join(aif_dir, filename)
                if os.path.exists(aif_path):
                    os.unlink(aif_path)
            del manifest[sid]

        if stale_ids:
            self.save(manifest)

        return stale_ids

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