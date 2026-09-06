# =============================================================================
# src/shared/exceptions.py
# =============================================================================
"""
Gerarchia EngineError per errori engine destinati a output user-facing pulito
(issue #33). Ogni eccezione fornisce user_message() per il terminale e
__str__ per i log.
"""
from __future__ import annotations

import errno
import os

# Import non lazy: `ConfigParseError` eredita `yaml.YAMLError`, e una classe
# base deve esistere al momento in cui la classe si crea. PyYAML e' una
# dipendenza dura del pacchetto (pyproject) e `pge.engine.generator` lo importa
# gia' a livello di modulo -- questo import non aggiunge una dipendenza, la
# dichiara dove serve.
import yaml


class EngineError(Exception):
    """Base per errori dell'pge.engine. Sottoclassi forniscono user_message()."""

    def user_message(self) -> str:
        return str(self)


class SampleNotFoundError(EngineError):
    def __init__(self, filename: str, search_path: str):
        self.filename = filename
        self.search_path = search_path
        self.stream_id: str | None = None
        self.config_file: str | None = None
        super().__init__(f"Sample non trovato: '{filename}' in {search_path}")

    def user_message(self) -> str:
        lines = [
            f"[ERRORE] Sample non trovato: '{self.filename}'",
            f"  Path cercato: {self.search_path}{self.filename}",
        ]
        if self.stream_id:
            lines.append(f"  Stream:       {self.stream_id}")
        if self.config_file:
            lines.append(f"  Config:       {self.config_file}")
        return "\n".join(lines)


class ConfigError(EngineError, ValueError):
    """
    Errori di configurazione YAML user-facing (issue #38).

    Eredita ValueError per compatibilita con catch espliciti pre-esistenti.
    Sottoclassi forniscono user_message() con context strutturato.
    """

    def __init__(self, message: str):
        self.stream_id: str | None = None
        self.config_file: str | None = None
        super().__init__(message)

    def _context_lines(self) -> list[str]:
        lines = []
        if self.stream_id:
            lines.append(f"  Stream:       {self.stream_id}")
        if self.config_file:
            lines.append(f"  Config:       {self.config_file}")
        return lines


class ConfigFileNotFoundError(ConfigError, FileNotFoundError):
    """File di configurazione YAML inesistente (issue #257).

    Eredita ANCHE `FileNotFoundError`, al contrario di
    `SuperColliderNotFoundError` e `CsoundNotFoundError` (#228, #241).
    L'asimmetria e' voluta e sta nel valore di verita' del builtin: per un
    binario assente era una bugia -- il file mancante non era quello che il
    tipo lasciava intendere -- mentre qui e' semplicemente vero, il file che
    non c'e' e' proprio quello. La doppia ereditarieta' tiene in piedi la
    promessa che `Generator.load_yaml` e `api.load_generator` dichiarano da
    sempre nei `Raises`, con lo stesso precedente della base
    `ConfigError(EngineError, ValueError)`.

    Il costo, dichiarato: il tipo non isola. Un `FileNotFoundError` di altra
    origine, impacchettato qui per errore, tornerebbe a confondersi con la
    configurazione mancante -- ed e' per questo che `load_yaml` avvolge il
    solo `open()` dello YAML e niente altro.

    Chi cattura non ne ha piu' bisogno per distinguere: `cli.main()` prende
    ora solo `EngineError`, e lo fa per tipo -- non per estensione fisica del
    blocco `try`, che era la garanzia fragile chiusa da questa issue.
    """

    def __init__(self, path: str):
        super().__init__(f"File di configurazione non trovato: '{path}'")
        self.path = path
        self.config_file = path
        # Risolto al momento del guasto: e' la cwd di quell'`open()` a contare,
        # non quella di chi stampa il messaggio piu' tardi.
        self.resolved_path = os.path.abspath(path)
        # Ereditare il tipo non basta: chi cattura `FileNotFoundError` non si
        # ferma alla cattura, legge `e.filename` e confronta `e.errno` con
        # `errno.ENOENT`. Su un wrapper nudo sono `None`, cioe' la promessa
        # regge per `isinstance` e cade per tutto il resto, in silenzio --
        # che e' la forma di guasto che questa issue chiude un livello piu'
        # su. `open()` li avrebbe riempiti: li riempiamo anche noi.
        self.errno = errno.ENOENT
        self.strerror = os.strerror(errno.ENOENT)
        self.filename = path

    def __str__(self) -> str:
        # Il prezzo dei tre campi qui sopra: con `filename` valorizzato
        # `OSError.__str__` smette di stampare `args[0]` e scrive
        # «[Errno 2] No such file or directory: 'x.yml'», buttando via la
        # prosa italiana. Ed e' proprio `str(err)` che finisce nel log engine
        # (`logger.error("%s", err)`) e nel ramo generico della CLI. Il
        # messaggio resta quello che la classe ha costruito.
        return self.args[0]

    def user_message(self) -> str:
        # Nessuna riga `Config:` da `_context_lines()`: il file e' il soggetto
        # del head, ripeterlo sotto non aggiunge niente. Il path assoluto si',
        # ma solo quando dice qualcosa in piu': e' l'informazione che il
        # messaggio precedente non dava -- «hai lanciato dalla directory
        # sbagliata» -- e su un path gia' assoluto sarebbe la stessa riga due
        # volte.
        lines = [f"[ERRORE] File di configurazione non trovato: '{self.path}'"]
        if self.resolved_path != self.path:
            lines.append(f"  Path cercato: {self.resolved_path}")
        return "\n".join(lines)


class ConfigParseError(ConfigError, yaml.YAMLError):
    """File di configurazione YAML illeggibile (issue #257).

    Il gradino successivo a `ConfigFileNotFoundError`: il file c'e' ma non si
    parsa. Prima nessuno traduceva `yaml.YAMLError` e l'utente riceveva
    messaggio piu' traceback dal ramo generico della CLI.

    Eredita anche `yaml.YAMLError` per la stessa ragione dell'altra classe: e'
    il tipo che `load_yaml` e `api.load_generator` promettono nei `Raises`.
    """

    #: Gli attributi che `yaml.MarkedYAMLError` espone e che il chiamante
    #: legge. Riportati dalla causa quando ci sono, mai fabbricati: su un
    #: `yaml.YAMLError` nudo restano assenti, come sull'originale.
    _ATTRIBUTI_PYYAML = ('context', 'context_mark', 'problem', 'problem_mark',
                         'note')

    def __init__(self, path: str, cause: Exception):
        super().__init__(f"File di configurazione malformato: '{path}'")
        self.path = path
        self.cause = cause
        self.config_file = path
        # Stessa ragione dei campi OSError dell'altra classe: `e.problem_mark`
        # *e'* l'idioma con cui si legge un errore PyYAML, e prima della #257
        # il chiamante riceveva il MarkedYAMLError vero. Un wrapper che eredita
        # `yaml.YAMLError` e basta lo fa sparire senza che niente fallisca.
        for attributo in self._ATTRIBUTI_PYYAML:
            if hasattr(cause, attributo):
                setattr(self, attributo, getattr(cause, attributo))

    def user_message(self) -> str:
        lines = [f"[ERRORE] File di configurazione malformato: '{self.path}'"]
        # `problem_mark` c'e' solo sui MarkedYAMLError, ed e' 0-based: renderlo
        # cosi' com'e' manderebbe l'utente una riga sopra a quella che il suo
        # editor gli mostra. Letto da `self`: dopo il riporto qui sopra e' la
        # stessa cosa, e cosi' il messaggio e chi interroga l'eccezione
        # guardano un unico posto.
        mark = getattr(self, 'problem_mark', None)
        if mark is not None:
            lines.append(f"  Riga/colonna: {mark.line + 1}:{mark.column + 1}")
        dettaglio = getattr(self, 'problem', None) or str(self.cause)
        lines.append(f"  Dettaglio:    {dettaglio}")
        return "\n".join(lines)


class MissingFieldError(ConfigError):
    """Campo YAML obbligatorio mancante o null."""

    def __init__(self, field: str | None = None, fields: list[str] | None = None, hint: str | None = None):
        if field is None and not fields:
            raise TypeError("MissingFieldError richiede 'field' o 'fields'")
        self.fields: list[str] = [field] if field else list(fields or [])
        self.hint = hint
        if len(self.fields) == 1:
            base = f"Campo obbligatorio mancante: '{self.fields[0]}'"
        else:
            joined = ", ".join(f"'{f}'" for f in self.fields)
            base = f"Campi obbligatori mancanti: {joined}"
        super().__init__(base)

    def user_message(self) -> str:
        if len(self.fields) == 1:
            head = f"[ERRORE] Campo obbligatorio mancante: '{self.fields[0]}'"
        else:
            joined = ", ".join(f"'{f}'" for f in self.fields)
            head = f"[ERRORE] Campi obbligatori mancanti: {joined}"
        lines = [head]
        if self.hint:
            lines.append(f"  Hint:         {self.hint}")
        lines.extend(self._context_lines())
        return "\n".join(lines)


class InvalidFieldValueError(ConfigError):
    """Campo YAML presente ma con valore invalido."""

    def __init__(self, field: str, value, hint: str | None = None):
        self.field = field
        self.value = value
        self.hint = hint
        super().__init__(f"Valore invalido per '{field}': {value!r}")

    def user_message(self) -> str:
        lines = [
            f"[ERRORE] Valore invalido per '{self.field}'",
            f"  Trovato:      {self.value!r}",
        ]
        if self.hint:
            lines.append(f"  Hint:         {self.hint}")
        lines.extend(self._context_lines())
        return "\n".join(lines)


class InvalidParameterError(ConfigError):
    """Parametro YAML con formato/tipo non supportato (issue #38, PR2)."""

    def __init__(self, param_name: str, value, hint: str | None = None):
        self.param_name = param_name
        self.value = value
        self.hint = hint
        super().__init__(f"Formato non valido per '{param_name}': {value!r}")

    def user_message(self) -> str:
        lines = [
            f"[ERRORE] Formato non valido per '{self.param_name}'",
            f"  Trovato:      {self.value!r}",
        ]
        if self.hint:
            lines.append(f"  Hint:         {self.hint}")
        lines.extend(self._context_lines())
        return "\n".join(lines)


class StrategyNotFoundError(ConfigError):
    """Strategia non registrata nel registry corrispondente (issue #38, PR3)."""

    def __init__(self, strategy_kind: str, name: str, available: list[str]):
        self.strategy_kind = strategy_kind
        self.name = name
        self.available = list(available)
        super().__init__(
            f"Strategia {strategy_kind} non trovata: '{name}'. "
            f"Disponibili: {sorted(self.available)}"
        )

    def user_message(self) -> str:
        lines = [
            f"[ERRORE] Strategia {self.strategy_kind} non trovata: '{self.name}'",
            f"  Disponibili:  {', '.join(sorted(self.available))}",
        ]
        lines.extend(self._context_lines())
        return "\n".join(lines)


class InvalidStrategyConfigError(ConfigError):
    """Strategia trovata ma configurazione invalida (issue #38, PR3)."""

    def __init__(
        self,
        strategy_kind: str,
        field: str,
        value,
        hint: str | None = None,
    ):
        self.strategy_kind = strategy_kind
        self.field = field
        self.value = value
        self.hint = hint
        super().__init__(
            f"Config invalida per strategia {strategy_kind} "
            f"(campo '{field}'): {value!r}"
        )

    def user_message(self) -> str:
        lines = [
            f"[ERRORE] Config invalida per strategia {self.strategy_kind}",
            f"  Campo:        {self.field}",
            f"  Trovato:      {self.value!r}",
        ]
        if self.hint:
            lines.append(f"  Hint:         {self.hint}")
        lines.extend(self._context_lines())
        return "\n".join(lines)


class InvalidRendererError(ConfigError):
    """Renderer kind sconosciuto (issue #38, PR4)."""

    def __init__(self, renderer_type: str, available: list[str]):
        self.renderer_type = renderer_type
        self.available = list(available)
        super().__init__(
            f"Renderer '{renderer_type}' non supportato. "
            f"Tipi validi: {', '.join(sorted(self.available))}"
        )

    def user_message(self) -> str:
        lines = [
            f"[ERRORE] Renderer non supportato: '{self.renderer_type}'",
            f"  Disponibili:  {', '.join(sorted(self.available))}",
        ]
        lines.extend(self._context_lines())
        return "\n".join(lines)


class InvalidWindowError(ConfigError):
    """Window function invalida (nome sconosciuto o parametri fuori dominio) (issue #38, PR4)."""

    def __init__(
        self,
        name: str | None = None,
        available: list[str] | None = None,
        reason: str | None = None,
        param: str | None = None,
        value=None,
    ):
        self.name = name
        self.available = list(available or [])
        self.reason = reason
        self.param = param
        self.value = value
        if name and available is not None:
            base = (
                f"Finestra '{name}' non trovata. "
                f"Disponibili: {sorted(self.available)}"
            )
        elif param is not None:
            base = f"Parametro finestra invalido '{param}': {value!r}"
        else:
            base = reason or f"Finestra invalida: {name!r}"
        super().__init__(base)

    def user_message(self) -> str:
        if self.name and self.available:
            head = f"[ERRORE] Window non trovata: '{self.name}'"
            lines = [head, f"  Disponibili:  {', '.join(sorted(self.available))}"]
        elif self.param is not None:
            head = f"[ERRORE] Parametro window invalido: '{self.param}'"
            lines = [head, f"  Trovato:      {self.value!r}"]
        else:
            lines = [f"[ERRORE] Window invalida: {self.reason or self.name}"]
        lines.extend(self._context_lines())
        return "\n".join(lines)


class EngineRuntimeError(EngineError):
    """Errori a runtime engine (non config) — issue #38, PR4."""

    def __init__(self, message: str):
        self.stream_id: str | None = None
        self.config_file: str | None = None
        super().__init__(message)

    def _context_lines(self) -> list[str]:
        lines = []
        if self.stream_id:
            lines.append(f"  Stream:       {self.stream_id}")
        if self.config_file:
            lines.append(f"  Config:       {self.config_file}")
        return lines


class _SubprocessRenderError(EngineRuntimeError, RuntimeError):
    """Base dei render delegati a un binario esterno (csound, scsynth, sclang).

    Csound e SuperCollider erano la stessa classe scritta due volte: stessi
    attributi, stesso `user_message`, stessa doppia eredita' (RuntimeError e'
    li' per i catch generici che precedono la gerarchia EngineError). Con una
    base sola, una correzione al formato del messaggio si applica una volta.

    Le sottoclassi dichiarano `stage` (che compare nel messaggio) e da quale
    capo dei flussi pescare la riga di diagnostica: csound scrive l'errore
    per primo, sclang e scsynth lo scrivono dopo il proprio preambolo.
    """

    stage = "subprocess"
    # Indice della riga diagnostica fra quelle non vuote: 0 = la prima.
    diagnostic_index = 0

    def __init__(self, returncode: int, command: list[str], stderr: str,
                 stdout: str = "", hint: str | None = None):
        self.returncode = returncode
        self.command = list(command)
        self.stderr = stderr
        # Lo stdout non e' decorativo: sclang posta li' `ERROR: Parse error` e
        # il backtrace dell'interprete, scsynth li' scrive `FAILURE IN SERVER`.
        # Senza, un refuso nella SynthDef arriva all'utente senza diagnostica.
        self.stdout = stdout
        # Il rimedio, quando ce n'e' uno che il messaggio da solo non offre.
        # La riga `Comando:` invita a rieseguire, ma lo score che vi compare
        # e' temporaneo e il renderer lo cancella prima che il messaggio si
        # stampi: chi lo vuole ha un flag, e il flag va detto qui. Opzionale
        # perche' con quel flag gia' attivo il rimedio non esiste piu' --
        # stessa regola dell'hint di `_BinaryNotFoundError`.
        self.hint = hint
        super().__init__(
            f"{self.stage} ha fallito con codice {returncode}.\n"
            f"Comando: {' '.join(command)}\n"
            f"Stderr: {stderr}"
        )

    def diagnostic_line(self) -> str | None:
        """Riga piu' informativa fra stderr e stdout, o None se tacciono."""
        for stream in (self.stderr, self.stdout):
            lines = [ln for ln in stream.splitlines() if ln.strip()]
            if lines:
                return lines[self.diagnostic_index].strip()
        return None

    def user_message(self) -> str:
        lines = [
            f"[ERRORE] {self.stage} fallito (exit code {self.returncode})",
            f"  Comando:      {' '.join(self.command)}",
        ]
        diagnostic = self.diagnostic_line()
        if diagnostic:
            lines.append(f"  Output:       {diagnostic}")
        if self.hint:
            lines.append(f"  Hint:         {self.hint}")
        lines.extend(self._context_lines())
        return "\n".join(lines)


class CsoundRenderError(_SubprocessRenderError):
    """Subprocess csound fallito (issue #38, PR4)."""

    stage = "Csound rendering"


class FtableError(ConfigError):
    """Errore di stato/coerenza FtableManager (issue #38, PR4)."""

    def __init__(self, key: str, reason: str):
        self.key = key
        self.reason = reason
        super().__init__(f"FtableManager: {reason} (chiave: {key!r})")

    def user_message(self) -> str:
        lines = [
            f"[ERRORE] Errore ftable: {self.reason}",
            f"  Chiave:       {self.key}",
        ]
        lines.extend(self._context_lines())
        return "\n".join(lines)


class ParameterBoundError(ConfigError):
    """Parametro YAML fuori dai bounds (strict validation mode, issue #38, PR2)."""

    def __init__(
        self,
        param_name: str,
        value_type: str,
        min_bound: float,
        max_bound: float | None,
        value: float | None = None,
        violations: list[tuple[float, float]] | None = None,
        hint: str | None = None,
    ):
        if value is None and not violations:
            raise TypeError("ParameterBoundError richiede 'value' o 'violations'")
        self.param_name = param_name
        self.value_type = value_type
        self.value = value
        self.violations = list(violations or [])
        self.min_bound = min_bound
        self.max_bound = max_bound
        # Il vincolo violato non e' sempre un intervallo sul singolo valore
        # (issue #212): `ratio ** n_reps` trabocca per la coppia, e la coppia
        # non si stampa come [min, max]. L'hint la nomina, come nelle sorelle
        # della stessa famiglia (InvalidFieldValueError, InvalidParameterError).
        self.hint = hint
        if violations:
            base = f"Envelope '{param_name}' fuori bounds: {len(violations)} violazione(i)"
        else:
            base = f"Parametro '{param_name}' fuori bounds: {value}"
        super().__init__(base)

    def user_message(self) -> str:
        # Bounds entrambi ignoti: la riga non si stampa. Un intervallo che non
        # esiste scritto come `[None, None]` e' rumore che sembra un dato.
        ha_bounds = self.min_bound is not None or self.max_bound is not None
        bounds = f"[{self.min_bound}, {self.max_bound}]"
        if self.violations:
            head = f"[ERRORE] Envelope '{self.param_name}' fuori bounds"
            lines = [head]
            if ha_bounds:
                lines.append(f"  Bounds:       {bounds}")
            for t, y in self.violations:
                lines.append(f"  t={t}: {self.value_type}={y}")
        else:
            head = f"[ERRORE] Parametro '{self.param_name}' fuori bounds"
            lines = [
                head,
                f"  {self.value_type}:        {self.value}",
            ]
            if ha_bounds:
                lines.append(f"  Bounds:       {bounds}")
        if self.hint:
            lines.append(f"  Hint:         {self.hint}")
        lines.extend(self._context_lines())
        return "\n".join(lines)


class SuperColliderRenderError(_SubprocessRenderError):
    """Subprocess SuperCollider fallito -- scsynth o sclang (issue #228).

    Lo `stage` e' per istanza e non di classe: 'scsynth' (rendering) e
    'sclang' (compilazione della SynthDef) sono due guasti con due rimedi
    diversi, e il messaggio deve dire quale.

    `diagnostic_index = -1`: sclang apre sempre con `compiling class
    library...` e `Found N LADSPA plugins`, quindi la prima riga non e' mai
    l'errore.
    """

    stage = "scsynth"
    diagnostic_index = -1

    def __init__(self, returncode: int, command: list[str], stderr: str,
                 stage: str = "scsynth", stdout: str = ""):
        self.stage = stage
        super().__init__(returncode, command, stderr, stdout=stdout)


class _BinaryNotFoundError(EngineRuntimeError):
    """Un binario esterno -- o un sorgente che serve a produrlo -- non c'e'
    (issue #228 per SuperCollider, #241 per csound).

    NON eredita FileNotFoundError di proposito. La ragione scritta qui prima --
    «la CLI intercetta quel tipo per annunciare 'file YAML non trovato'» -- non
    vale piu' dalla #257: `cli.main()` non cattura piu' nessun builtin. Quella
    che regge e' l'altra: per un binario assente il builtin e' *falso*, perche'
    il file che manca non e' quello che il tipo lascia intendere. Dove invece
    dice il vero il tipo di dominio se lo tiene accanto -- vedi
    `ConfigFileNotFoundError`, che eredita FileNotFoundError proprio perche'
    li' il file mancante e' davvero quello.

    Le sottoclassi dichiarano `tool`, il nome che apre il messaggio: e'
    l'unica cosa che le distingue, come per `_SubprocessRenderError`.
    """

    tool = "binario esterno"

    def __init__(self, what: str, hint: str | None = None):
        self.what = what
        self.hint = hint
        super().__init__(f"{self.tool}: {what} non trovato")

    def user_message(self) -> str:
        lines = [f"[ERRORE] {self.tool}: {self.what} non trovato"]
        if self.hint:
            lines.append(f"  Hint:         {self.hint}")
        lines.extend(self._context_lines())
        return "\n".join(lines)


class SuperColliderNotFoundError(_BinaryNotFoundError):
    """Binario SuperCollider o sorgente della SynthDef non trovati (issue #228)."""

    tool = "SuperCollider"


class CsoundNotFoundError(_BinaryNotFoundError):
    """csound non e' nel PATH (issue #241).

    Il subprocess alza FileNotFoundError, che era anche il tipo promesso
    dalla docstring di `render_single_stream`: la CLI lo intercettava prima
    di EngineError e diceva all'utente che mancava il suo file YAML -- letto
    e parsato pochi istanti prima. Qui il guasto prende un tipo suo, con il
    rimedio scritto dentro.
    """

    tool = "Csound"
