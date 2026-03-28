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
from typing import Dict, Any

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
    """

    def __init__(self, score_writer, csound_config: Dict[str, Any]):
        self.score_writer = score_writer
        self.csound_config = csound_config

    def render_stream(self, stream, output_path: str) -> str:
        """
        Renderizza uno stream: ScoreWriter -> .sco -> csound -> .aif

        Args:
            stream: oggetto Stream con voices e grains
            output_path: percorso file .aif di output

        Returns:
            Il percorso del file .aif prodotto

        Raises:
            RuntimeError: se csound esce con errore
            FileNotFoundError: se csound non e' installato
        """
        # 1. Scrivi .sco temporaneo
        sco_path = self._write_temp_score(
            streams=[stream],
            cartridges=[],
        )

        # 2. Invoca csound
        self._run_csound(sco_path, output_path)

        return output_path

    def render_cartridge(self, cartridge, output_path: str) -> str:
        """
        Renderizza una cartridge: ScoreWriter -> .sco -> csound -> .aif
        """
        sco_path = self._write_temp_score(
            streams=[],
            cartridges=[cartridge],
        )

        self._run_csound(sco_path, output_path)

        return output_path

    # =========================================================================
    # INTERNAL
    # =========================================================================

    def _write_temp_score(self, streams, cartridges) -> str:
        """Scrive un file .sco temporaneo via ScoreWriter."""
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