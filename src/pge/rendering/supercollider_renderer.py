# src/pge/rendering/supercollider_renderer.py
"""
SuperColliderRenderer - Adapter sulla pipeline NRT di SuperCollider.

Terza implementazione concreta di `AudioRenderer`, modellata su
`CsoundRenderer`: entrambi sono adapter sottili su un motore esterno, e la
lista dei grani che ricevono e' la stessa che ricevono NumPy e i tre
exporter non sonori.

Pipeline:

    Stream -> SuperColliderScoreWriter -> .osc -> scsynth -N -> .aif

Il `.osc` e' l'omologo binario del `.sco` Csound: una sequenza di bundle OSC
ordinati per tempo. Lo genera Python (`sc_score_writer.py`), quindi il
percorso di rendering non fa girare nessun linguaggio intermedio.

## Perche' sclang compare comunque

L'unico pezzo davvero nuovo di questo backend e' la SynthDef del grano --
l'equivalente di `csound/main.orc`. Vive in `supercollider/pge_grain.scd`
come sorgente leggibile e versionato, e viene compilata in `.scsyndef` una
volta sola: e' un artefatto di build, non un passo del rendering. Il
renderer la ricompila da solo quando manca o quando il sorgente e' piu'
recente, e il resto del tempo si limita a spedirne i byte dentro lo score.

L'alternativa -- emettere il binario `.scsyndef` direttamente da Python --
toglierebbe la dipendenza da sclang (che comunque arriva nello stesso
pacchetto di scsynth) al prezzo di un grafo di UGen serializzato a mano, che
nessuno puo' rileggere come DSP e che nessun test puo' validare senza un
server. Un `.scd` accanto a `main.orc` e' la forma in cui questo progetto
tiene gia' il proprio DSP scritto a mano.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from pge.rendering.audio_format import AudioFormat, DEFAULT_FORMAT
from pge.rendering.audio_renderer import AudioRenderer
from pge.rendering.sc_score_writer import SYNTH_NAME, SuperColliderScoreWriter
from pge.shared.constants import DEFAULT_OUTPUT_SR


# Sorgente e destinazione della SynthDef. Il default e' un path relativo alla
# working directory, come `csound/main.orc` per il backend Csound: e' la
# convenzione del progetto, e Makefile e CLI lo passano esplicito.
DEFAULT_SYNTHDEF_SOURCE = 'supercollider/pge_grain.scd'
DEFAULT_SYNTHDEF_DIR = 'generated'

# Block size di scsynth. 1 = onset campione-accurati, la stessa scelta di
# main.orc, che gira a ksmps=1 (sr=kr=48000 in testa al file). Col default di
# scsynth (64) gli onset dei grani si quantizzerebbero a 1.33 ms a 48 kHz:
# nella sintesi granulare la posizione del grano E' il materiale, non un
# dettaglio di scheduling. Il prezzo e' il tempo di render, ed e' il motivo
# per cui resta configurabile.
DEFAULT_BLOCK_SIZE = 1

# Nodi massimi. Il default di scsynth e' 1024, cioe' il numero di grani che
# possono suonare insieme: una densita' alta con grani lunghi lo supera e il
# render muore a meta'. La struttura e' una hash table di puntatori, quindi
# alzarla costa memoria trascurabile.
DEFAULT_MAX_NODES = 32768

# subtype di libsndfile -> sample format di scsynth. Il header format
# (AIFF/WAV/FLAC) invece coincide gia' con `AudioFormat.sf_format`.
_SAMPLE_FORMATS = {
    'FLOAT': 'float',
    'DOUBLE': 'double',
    'PCM_16': 'int16',
    'PCM_24': 'int24',
    'PCM_32': 'int32',
}


class SuperColliderRenderer(AudioRenderer):
    """
    Renderer audio via scsynth in non-realtime.

    Args:
        table_map: {numero: ('sample'|'window', nome)} dal FtableManager.
        window_registry: NumpyWindowRegistry (la stessa del renderer NumPy:
            e' cio' che rende le finestre identiche per costruzione).
        samples_dir: directory dei sample audio.
        output_sr: sample rate di render.
        audio_format: formato del file prodotto.
        sc_config: dict di configurazione:
            - scsynth_bin / sclang_bin: binari (default: dal PATH)
            - synthdef_source: sorgente .scd della SynthDef
            - synthdef_dir: dove sta (o va scritto) il .scsyndef compilato
            - block_size: block size di scsynth (default 1)
            - max_nodes: nodi massimi (default 32768)
        cache_manager: StreamCacheManager opzionale per skip stream invariati.
        stream_data_map: {stream_id: yaml_dict} per il fingerprint della cache.
        osc_dir: se valorizzato, gli score .osc restano qui invece di essere
            temporanei (--keep-osc, omologo di --keep-sco).
    """

    renderer_type = 'supercollider'

    def __init__(
        self,
        table_map: Dict[int, Any],
        window_registry,
        *,
        samples_dir: str = './refs/',
        output_sr: int = DEFAULT_OUTPUT_SR,
        audio_format: AudioFormat = DEFAULT_FORMAT,
        sc_config: Optional[Dict[str, Any]] = None,
        cache_manager=None,
        stream_data_map: Optional[Dict[str, dict]] = None,
        osc_dir: Optional[str] = None,
    ):
        self.table_map = dict(table_map)
        self.window_registry = window_registry
        self.samples_dir = samples_dir
        self.output_sr = output_sr
        self.audio_format = audio_format
        self.sc_config = dict(sc_config or {})
        self.cache_manager = cache_manager
        self.stream_data_map = dict(stream_data_map) if stream_data_map is not None else {}
        self.osc_dir = osc_dir

        self._synthdef_bytes: Optional[bytes] = None
        self._score_writer: Optional[SuperColliderScoreWriter] = None

    # =========================================================================
    # AudioRenderer ABC
    # =========================================================================

    def render_single_stream(self, stream, output_path: str) -> str:
        """
        Renderizza UN stream (onset relativi): score -> scsynth -> audio.

        Usato per: STEMS mode.
        """
        if self._cache_skip(stream, output_path):
            return output_path

        self._render([stream], output_path, per_stream=True)
        self._update_cache(stream)
        return output_path

    def render_merged_streams(self, streams: List, output_path: str) -> str:
        """
        Renderizza PIU' stream in UN file (onset assoluti).

        Usato per: MIX mode. Come nel backend Csound la cache non interviene:
        la build incrementale e' per stem.
        """
        self._render(streams, output_path, per_stream=False)
        return output_path

    # =========================================================================
    # INTERNAL - render
    # =========================================================================

    def _render(self, streams: List, output_path: str, per_stream: bool) -> None:
        osc_path = self._score_path(output_path)
        try:
            self.score_writer().write_score(
                osc_path, streams, per_stream=per_stream)
            self._run_scsynth(osc_path, output_path)
        finally:
            # Lo score temporaneo se ne va anche quando il render fallisce:
            # per ispezionarlo c'e' --keep-osc, che e' proprio la modalita' in
            # cui il file non e' temporaneo.
            if not self.osc_dir and os.path.exists(osc_path):
                os.unlink(osc_path)

    def _score_path(self, output_path: str) -> str:
        """Path dello score .osc: deterministico con --keep-osc, temporaneo
        altrimenti. Stessa logica di CsoundRenderer._write_score."""
        if self.osc_dir:
            base = os.path.splitext(os.path.basename(output_path))[0]
            os.makedirs(self.osc_dir, exist_ok=True)
            return os.path.join(self.osc_dir, f"{base}.osc")
        fd, path = tempfile.mkstemp(suffix='.osc')
        os.close(fd)
        return path

    def _run_scsynth(self, osc_path: str, output_path: str) -> None:
        """Invoca scsynth in non-realtime.

        Le opzioni precedono `-N`: tutto cio' che segue viene letto come
        argomento posizionale (score, input, output, sr, header, formato).
        """
        cmd = [
            self.sc_config.get('scsynth_bin', 'scsynth'),
            '-o', '2',                                     # uscita stereo
            '-i', '0',                                     # nessun ingresso
            '-z', str(self.sc_config.get('block_size', DEFAULT_BLOCK_SIZE)),
            '-n', str(self.sc_config.get('max_nodes', DEFAULT_MAX_NODES)),
            '-N', osc_path, '_', output_path,
            str(self.output_sr),
            self.audio_format.sf_format,
            self._sample_format(),
        ]
        self._run(cmd, stage='scsynth', hint=(
            "Installa SuperCollider (Debian/Ubuntu: apt install supercollider; "
            "macOS: brew install --cask supercollider) oppure usa "
            "--renderer numpy."
        ))

    def _sample_format(self) -> str:
        subtype = self.audio_format.sf_subtype
        if subtype not in _SAMPLE_FORMATS:
            from pge.shared.exceptions import SuperColliderNotFoundError
            raise SuperColliderNotFoundError(
                what=f"formato campione '{subtype}'",
                hint=f"scsynth accetta: {', '.join(sorted(set(_SAMPLE_FORMATS.values())))}",
            )
        return _SAMPLE_FORMATS[subtype]

    # =========================================================================
    # INTERNAL - SynthDef
    # =========================================================================

    def score_writer(self) -> SuperColliderScoreWriter:
        """Score writer del renderer, costruito alla prima necessita'.

        E' lazy perche' ha bisogno dei byte della SynthDef, che possono
        richiedere una compilazione: costruire il renderer non deve far
        partire sclang.
        """
        if self._score_writer is None:
            self._score_writer = SuperColliderScoreWriter(
                table_map=self.table_map,
                window_registry=self.window_registry,
                synthdef_bytes=self.synthdef_bytes(),
                samples_dir=self.samples_dir,
                output_sr=self.output_sr,
                synth_name=SYNTH_NAME,
            )
        return self._score_writer

    def synthdef_bytes(self) -> bytes:
        """Byte del .scsyndef, compilandolo se serve (una volta per renderer)."""
        if self._synthdef_bytes is None:
            self._synthdef_bytes = self._load_or_compile_synthdef()
        return self._synthdef_bytes

    def _load_or_compile_synthdef(self) -> bytes:
        from pge.shared.exceptions import SuperColliderNotFoundError

        source = self.sc_config.get('synthdef_source', DEFAULT_SYNTHDEF_SOURCE)
        target_dir = self.sc_config.get('synthdef_dir', DEFAULT_SYNTHDEF_DIR)
        compiled = os.path.join(target_dir, f"{SYNTH_NAME}.scsyndef")

        if not self._needs_compile(source, compiled):
            with open(compiled, 'rb') as f:
                return f.read()

        if not os.path.exists(source):
            raise SuperColliderNotFoundError(
                what=f"sorgente della SynthDef '{source}'",
                hint=("Passa --sc-synthdef-source PATH, oppure indica con "
                      "--sc-synthdef-dir la directory che contiene "
                      f"{SYNTH_NAME}.scsyndef gia' compilato."),
            )

        os.makedirs(target_dir, exist_ok=True)
        self._run(
            [self.sc_config.get('sclang_bin', 'sclang'), source],
            stage='sclang',
            hint=("Compila la SynthDef una volta con `make sc-synthdef`. "
                  "Serve sclang, che arriva nello stesso pacchetto di "
                  "scsynth; in alternativa compilala altrove e indica la "
                  "directory con --sc-synthdef-dir."),
            env={**os.environ, 'PGE_SYNTHDEF_DIR': target_dir},
        )

        if not os.path.exists(compiled):
            from pge.shared.exceptions import SuperColliderRenderError
            raise SuperColliderRenderError(
                returncode=0,
                command=[self.sc_config.get('sclang_bin', 'sclang'), source],
                stderr=(f"sclang e' uscito senza errori ma {compiled} non "
                        f"esiste: lo script non ha scritto la SynthDef."),
                stage='sclang',
            )

        with open(compiled, 'rb') as f:
            return f.read()

    @staticmethod
    def _needs_compile(source: str, compiled: str) -> bool:
        """True se il .scsyndef manca o e' piu' vecchio del suo sorgente.

        Un .scsyndef piu' vecchio del .scd e' un grafo che non e' piu' quello
        scritto: la ricompilazione e' la stessa regola di un Makefile. Se il
        sorgente non c'e' affatto (installazione che spedisce solo il
        compilato) il compilato vale comunque.
        """
        if not os.path.exists(compiled):
            return True
        if not os.path.exists(source):
            return False
        return os.path.getmtime(source) > os.path.getmtime(compiled)

    # =========================================================================
    # INTERNAL - subprocess
    # =========================================================================

    @staticmethod
    def _run(cmd: List[str], *, stage: str, hint: str, env=None) -> None:
        """Esegue un binario SuperCollider e traduce i suoi due modi di
        fallire in due eccezioni distinte, perche' hanno rimedi distinti."""
        from pge.shared.exceptions import (
            SuperColliderNotFoundError, SuperColliderRenderError,
        )

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        except FileNotFoundError:
            raise SuperColliderNotFoundError(
                what=f"binario '{cmd[0]}'",
                hint=hint,
            ) from None

        if result.returncode != 0:
            raise SuperColliderRenderError(
                returncode=result.returncode,
                command=cmd,
                stderr=result.stderr or "",
                stage=stage,
            )

    # =========================================================================
    # INTERNAL - cache (stessa semantica di CsoundRenderer/NumpyAudioRenderer)
    # =========================================================================

    def _cache_skip(self, stream, output_path: str) -> bool:
        """True se lo stream e' clean e la build va saltata. is_dirty va
        chiamato PRIMA di toccare .voices (#117)."""
        if not self.cache_manager:
            return False
        stream_dict = self.stream_data_map.get(stream.stream_id)
        if not stream_dict:
            return False
        dirty = self.cache_manager.is_dirty(stream_dict, output_path)
        print(f"[CACHE] {stream.stream_id}: {'DIRTY' if dirty else 'clean'}",
              flush=True)
        return not dirty

    def _update_cache(self, stream) -> None:
        """Aggiorna la cache dopo una build riuscita dello stream."""
        if not self.cache_manager:
            return
        stream_dict = self.stream_data_map.get(stream.stream_id)
        if stream_dict:
            self.cache_manager.update_after_build([stream_dict])
