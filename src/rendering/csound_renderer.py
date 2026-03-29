# src/rendering/csound_renderer.py
"""
CsoundRenderer - Adapter per la pipeline Csound esistente.

Wrappa ScoreWriter + subprocess.run("csound ...") nell'interfaccia
AudioRenderer ABC, mantenendo la pipeline originale invariata.

Pipeline: Stream -> ScoreWriter -> .sco -> csound subprocess -> .aif

Questo e' il renderer di default (--renderer csound). Non modifica
nessun codice esistente: ScoreWriter, FtableManager, main.orc restano
identici.
"""

import os
import subprocess
import tempfile
from typing import Dict, Any, List, Optional

from rendering.audio_renderer import AudioRenderer


class CsoundRenderer(AudioRenderer):
    """
    Renderer audio via Csound subprocess.

    Adapter pattern: wrappa la pipeline esistente (ScoreWriter + csound)
    nell'interfaccia AudioRenderer.

    Args:
        score_writer: istanza di ScoreWriter (con FtableManager gia' configurato)
        csound_config: dict con configurazione Csound:
            - orc_path: percorso dell'orchestra (.orc)
            - env_vars: dict con INCDIR, SSDIR, SFDIR
            - log_dir: directory per i log
            - message_level: livello messaggi csound (-m flag)
        cartridges: lista di Cartridge da includere nel mix (default: [])
        cache_manager: StreamCacheManager opzionale per skip stream invariati
        stream_data_map: dict {stream_id: yaml_dict} per fingerprint cache
        sco_dir: se specificato, salva i file .sco in questa directory
                 (utile per debug con --keep-sco); se None usa tempfile
    """

    def __init__(
        self,
        score_writer,
        csound_config: Dict[str, Any],
        cartridges: Optional[List] = None,
        cache_manager=None,
        stream_data_map: Optional[Dict[str, dict]] = None,
        sco_dir: Optional[str] = None,
    ):
        self.score_writer = score_writer
        self.csound_config = csound_config
        self.cartridges = list(cartridges) if cartridges is not None else []
        self.cache_manager = cache_manager
        self.stream_data_map = dict(stream_data_map) if stream_data_map is not None else {}
        self.sco_dir = sco_dir

    def render_single_stream(self, stream, output_path: str) -> str:
        """
        Renderizza UN stream (onset relativi): ScoreWriter -> .sco -> csound -> .aif

        Se cache_manager e' configurato, salta lo stream se il fingerprint
        non e' cambiato e il file .aif esiste gia'.

        Usato per: STEMS mode (ogni stream in file separato)

        Args:
            stream: oggetto Stream con voices e grains
            output_path: percorso file .aif di output

        Returns:
            Il percorso del file .aif prodotto

        Raises:
            RuntimeError: se csound esce con errore
            FileNotFoundError: se csound non e' installato
        """
        # Cache check: skip se stream e' clean
        if self.cache_manager:
            stream_dict = self.stream_data_map.get(stream.stream_id)
            if stream_dict and not self.cache_manager.is_dirty(stream_dict, output_path):
                return output_path

        sco_path = self._write_score(streams=[stream], cartridges=[], output_path=output_path)
        self._run_csound(sco_path, output_path)

        # Cleanup file temporaneo se non in modalita' keep-sco
        if not self.sco_dir and os.path.exists(sco_path):
            os.unlink(sco_path)

        # Aggiorna cache dopo build riuscita
        if self.cache_manager:
            stream_dict = self.stream_data_map.get(stream.stream_id)
            if stream_dict:
                self.cache_manager.update_after_build([stream_dict])

        return output_path

    def render_merged_streams(self, streams: List, output_path: str) -> str:
        """
        Renderizza PIU' stream in UN file (onset assoluti): ScoreWriter -> .sco -> csound -> .aif

        Include i cartridges (tape recorder) nel file score.

        Usato per: MIX mode (tutti gli stream in un file)

        Args:
            streams: lista di Stream objects da mixare
            output_path: percorso file .aif di output

        Returns:
            Il percorso del file .aif prodotto
        """
        sco_path = self._write_score(
            streams=streams,
            cartridges=self.cartridges,
            output_path=output_path,
        )
        self._run_csound(sco_path, output_path)

        # Cleanup file temporaneo se non in modalita' keep-sco
        if not self.sco_dir and os.path.exists(sco_path):
            os.unlink(sco_path)

        return output_path

    # =========================================================================
    # INTERNAL
    # =========================================================================

    def _write_score(self, streams, cartridges, output_path: str) -> str:
        """
        Scrive il file .sco via ScoreWriter.

        Se sco_dir e' configurato (--keep-sco), salva in path deterministico
        basato su output_path. Altrimenti usa un file temporaneo.

        Args:
            streams: lista di Stream da includere
            cartridges: lista di Cartridge da includere
            output_path: percorso del file .aif di output (usato per naming)

        Returns:
            Path del file .sco scritto
        """
        if self.sco_dir:
            base = os.path.splitext(os.path.basename(output_path))[0]
            sco_path = os.path.join(self.sco_dir, f"{base}.sco")
            os.makedirs(self.sco_dir, exist_ok=True)
        else:
            fd, sco_path = tempfile.mkstemp(suffix='.sco')
            os.close(fd)

        self.score_writer.write_score(
            filepath=sco_path,
            streams=streams,
            cartridges=cartridges,
        )

        return sco_path

    def _run_csound(self, sco_path: str, output_path: str):
        """
        Invoca csound come subprocess.

        Costruisce il comando con env vars e flags dalla configurazione.

        Raises:
            RuntimeError: se csound ritorna un codice di errore
            FileNotFoundError: se csound non e' installato
        """
        cmd = ['csound']

        # Env vars
        env_vars = self.csound_config.get('env_vars', {})
        for key, value in env_vars.items():
            cmd.append(f'--env:{key}+={value}')

        # Message level
        msg_level = self.csound_config.get('message_level', 134)
        cmd.extend(['-m', str(msg_level)])

        # Orchestra e score
        orc_path = self.csound_config.get('orc_path', 'csound/main.orc')
        cmd.append(orc_path)
        cmd.append(sco_path)

        # Output
        cmd.extend(['-o', output_path])

        # Log
        log_dir = self.csound_config.get('log_dir')
        if log_dir:
            basename = os.path.splitext(os.path.basename(output_path))[0]
            cmd.append(f'--logfile={log_dir}/{basename}.log')

        # Esegui
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(
                f"Csound ha fallito con codice {result.returncode}.\n"
                f"Comando: {' '.join(cmd)}\n"
                f"Stderr: {result.stderr}"
            )
