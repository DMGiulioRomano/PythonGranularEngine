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
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Dict, Any, List, Optional

from pge.rendering.audio_renderer import AudioRenderer


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
        cache_manager: StreamCacheManager opzionale per skip stream invariati
        stream_data_map: dict {stream_id: yaml_dict} per fingerprint cache
        sco_dir: se specificato, salva i file .sco in questa directory
                 (utile per debug con --keep-sco); se None usa tempfile
    """

    renderer_type = 'csound'

    def __init__(
        self,
        score_writer,
        csound_config: Dict[str, Any],
        cache_manager=None,
        stream_data_map: Optional[Dict[str, dict]] = None,
        sco_dir: Optional[str] = None,
    ):
        self.score_writer = score_writer
        self.csound_config = csound_config
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
            CsoundRenderError: se csound esce con errore (anche RuntimeError)
            CsoundNotFoundError: se csound non e' installato
        """
        # Cache check: skip se stream e' clean
        if self.cache_manager:
            stream_dict = self.stream_data_map.get(stream.stream_id)
            if stream_dict:
                dirty = self.cache_manager.is_dirty(stream_dict, output_path)
                status = "DIRTY" if dirty else "clean"
                print(f"[CACHE] {stream.stream_id}: {status}", flush=True)
                if not dirty:
                    return output_path

        self._render([stream], output_path, per_stream=True)

        # Aggiorna cache dopo build riuscita
        if self.cache_manager:
            stream_dict = self.stream_data_map.get(stream.stream_id)
            if stream_dict:
                self.cache_manager.update_after_build([stream_dict])

        return output_path

    def render_merged_streams(self, streams: List, output_path: str) -> str:
        """
        Renderizza PIU' stream in UN file (onset assoluti): ScoreWriter -> .sco -> csound -> .aif

        Usato per: MIX mode (tutti gli stream in un file)

        Args:
            streams: lista di Stream objects da mixare
            output_path: percorso file .aif di output

        Returns:
            Il percorso del file .aif prodotto

        Raises:
            CsoundRenderError: se csound esce con errore
            CsoundNotFoundError: se csound non e' installato
        """
        self._render(streams, output_path, per_stream=False)

        return output_path

    # =========================================================================
    # INTERNAL
    # =========================================================================

    def _render(self, streams, output_path: str, per_stream: bool) -> None:
        """Score + csound, con lo score temporaneo che se ne va comunque.

        STEMS e MIX passano di qui, quindi la regola di cancellazione ha una
        scrittura sola. Il `try` copre anche `write_score`, non la sola
        chiamata a csound: il file temporaneo lo crea `_score_path`
        (`mkstemp`) *prima* che ScoreWriter ci scriva, e i grani sono lazy
        (issue #117) -- si materializzano proprio qui, con tutti i modi di
        essere invalidi che il parse non ha visto. Uno score che muore
        scrivendo lasciava un .sco in /tmp esattamente come il csound assente
        della issue #241, con lo stesso nome casuale che l'utente non ha modo
        di ritrovare. E' la forma che `SuperColliderRenderer._render` ha da
        sempre; era questa meta' a non averla.

        Chi il .sco di un render fallito lo vuole ha `--keep-sco`, ed e' la
        modalita' in cui il file non e' temporaneo: la condizione lo rispetta.
        """
        sco_path = self._score_path(output_path)
        try:
            self.score_writer.write_score(
                filepath=sco_path,
                streams=streams,
                per_stream=per_stream,
            )
            self._run_csound(sco_path, output_path)
        finally:
            if not self.sco_dir and os.path.exists(sco_path):
                os.unlink(sco_path)

    def _score_path(self, output_path: str) -> str:
        """Path del file .sco.

        Se sco_dir e' configurato (--keep-sco), path deterministico basato su
        output_path. Altrimenti un file temporaneo, che `mkstemp` crea gia'
        vuoto sul disco: da quel momento e' compito di `_render` toglierlo.

        Args:
            output_path: percorso del file .aif di output (usato per naming)

        Returns:
            Path del file .sco
        """
        if self.sco_dir:
            base = os.path.splitext(os.path.basename(output_path))[0]
            os.makedirs(self.sco_dir, exist_ok=True)
            return os.path.join(self.sco_dir, f"{base}.sco")

        fd, sco_path = tempfile.mkstemp(suffix='.sco')
        os.close(fd)
        return sco_path

    def _run_csound(self, sco_path: str, output_path: str):
        """
        Invoca csound come subprocess.

        Costruisce il comando con env vars e flags dalla configurazione.

        Raises:
            CsoundRenderError: se csound ritorna un codice di errore
            CsoundNotFoundError: se csound non e' installato
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
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            # csound non e' nel PATH. Il FileNotFoundError grezzo finiva
            # nell'handler che la CLI tiene per il file YAML, e l'utente si
            # sentiva dire che la sua configurazione non esiste (issue #241).
            from pge.shared.exceptions import CsoundNotFoundError
            raise CsoundNotFoundError(
                what=f"binario '{cmd[0]}'",
                # `make install-system-deps` NON installa csound su
                # Fedora/RHEL -- non e' nei repo, ne' in RPM Fusion -- ed e'
                # proprio la macchina da cui viene la issue: un rimedio che
                # li' e' un no-op vale quanto il messaggio che ha sostituito.
                hint=("Installa csound (`make install-system-deps`; su "
                      "Fedora/RHEL non e' nei repo e va compilato dai "
                      "sorgenti, vedi README), oppure usa `--renderer "
                      "numpy`, che non richiede binari esterni."),
            ) from None

        if result.returncode != 0:
            from pge.shared.exceptions import CsoundRenderError
            # La riga `Comando:` del messaggio invita a rieseguire, ma nomina
            # uno score che a quel punto non c'e' piu': da quando la
            # cancellazione sta in un `finally` (PR #256) anche l'exit diverso
            # da zero ci passa, e prima invece saltava le due righe lasciando
            # il file in /tmp. Il rimedio esiste ed e' un flag: se il
            # messaggio non lo dice, la prima azione che suggerisce e' un
            # no-op. Con `--keep-sco` gia' attivo il rimedio non esiste piu',
            # e l'hint tace.
            hint = None if self.sco_dir else (
                "Lo score .sco era temporaneo ed e' stato rimosso: rilancia "
                "con `--keep-sco` per conservarlo e rieseguire il comando "
                "qui sopra."
            )
            raise CsoundRenderError(
                returncode=result.returncode,
                command=cmd,
                stderr=result.stderr or "",
                hint=hint,
            )
