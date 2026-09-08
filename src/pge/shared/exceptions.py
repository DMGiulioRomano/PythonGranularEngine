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

# Import non lazy: `ConfigParseError` eredita `yaml.YAMLError`, e una base
# deve esistere quando la classe si crea. PyYAML e' dipendenza dura del
# pacchetto (pyproject) e `pge.engine.generator` la importa gia' a livello di
# modulo: questo import non ne aggiunge una, la dichiara dove serve.
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
    """Il file YAML di configurazione non esiste (issue #257).

    EREDITA FileNotFoundError, all'opposto di `_BinaryNotFoundError`, e
    l'asimmetria e' voluta. Per un binario assente quel tipo era una bugia
    utile a nessuno -- il file che mancava non era quello che il tipo lasciava
    intendere. Qui e' semplicemente vero, ed e' anche cio' che
    `Generator.load_yaml` e `api.load_generator` dichiarano da sempre fra i
    `Raises`: chi lo cattura continua a catturarlo, per la stessa ragione per
    cui `ConfigError` eredita `ValueError`.

    Le due decisioni opposte fanno una regola sola, e la regola e' il guadagno:
    dentro la gerarchia EngineError `FileNotFoundError` significa una cosa e
    una sola -- il file di configurazione che hai nominato non esiste. Cosi'
    la CLI puo' smettere di intercettare il builtin (questo errore le arriva
    da `except EngineError`), e un guasto di I/O che risale da qualunque altra
    profondita' non si traveste piu' da configurazione mancante. Prima della
    #257 quella garanzia era l'estensione fisica di un `try`, non un tipo:
    reggeva finche' nessuno aggiungeva una riga li' dentro.
    """

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"File di configurazione non trovato: '{path}'")
        # Il contesto strutturato di casa: chi legge l'eccezione a programma
        # trova il path dove lo trova in tutte le sorelle.
        self.config_file = path
        # Ereditare il tipo non basta a mantenere la promessa. Chi cattura un
        # FileNotFoundError raramente si ferma alla cattura: legge `filename`
        # e confronta `errno` con `errno.ENOENT`. Su un wrapper nudo sono
        # None -- cioe' la compatibilita' regge per `isinstance` e cade per
        # tutto il resto, in silenzio. `open()` li avrebbe riempiti.
        self.errno = errno.ENOENT
        self.strerror = os.strerror(errno.ENOENT)
        self.filename = path

    def __str__(self) -> str:
        # Il prezzo dei tre campi qui sopra: con `filename` valorizzato
        # `OSError.__str__` smette di stampare `args[0]` e scrive «[Errno 2]
        # No such file or directory: 'x.yml'». Ed e' `str(err)` che finisce
        # nel log engine (`logger.error("%s", err)`) e nel ramo generico di
        # chi ci chiama: il messaggio resta quello che la classe ha costruito.
        return self.args[0]

    def __reduce__(self):
        # Secondo prezzo degli stessi tre campi, e va pagato anche questo.
        # `OSError.__reduce__` accoda `filename` agli `args`, perche' un
        # OSError si ricostruisce da `(errno, strerror, filename)`. Qui
        # `args` e' uno solo -- la prosa della classe -- e la ricostruzione
        # chiamerebbe `ConfigFileNotFoundError(<la prosa>)`: il messaggio si
        # anniderebbe dentro se' stesso e `path`, `filename` e `config_file`
        # diventerebbero il messaggio. Senza sollevare niente: la promessa
        # reggerebbe per `isinstance` e cadrebbe in silenzio per tutto il
        # resto, cioe' la forma di guasto che la #257 chiude un piano piu'
        # su. Il path ricostruisce tutto cio' che `__init__` deriva; il
        # `__dict__` va accodato lo stesso, perche' non tutto lo stato viene
        # da li'. `stream_id` lo scrive il chiamante piu' prossimo dopo il
        # raise (punto 5 di docs/reference/errors.md, la regola di ogni
        # sottoclasse di ConfigError), e senza il terzo elemento -- che il
        # `__reduce__` di BaseException accoda proprio per questo -- il round
        # trip lo perdeva, cioe' toglieva la riga `Stream:` dal messaggio
        # senza sollevare niente: la stessa promessa muta che questi tre
        # override esistono per non fare.
        return (self.__class__, (self.path,), self.__dict__)

    def user_message(self) -> str:
        lines = ["[ERRORE] File di configurazione non trovato"]
        risolto = os.path.abspath(self.path)
        # Il path risolto dice in quale directory si e' cercato, e serve
        # proprio a chi ha passato un path relativo. Con un path gia'
        # assoluto sarebbe la riga `Config:` scritta due volte: stessa regola
        # dei bounds ignoti di ParameterBoundError, una riga che non aggiunge
        # niente non si stampa.
        if risolto != self.path:
            lines.append(f"  Path cercato: {risolto}")
        lines.extend(self._context_lines())
        return "\n".join(lines)


class ConfigParseError(ConfigError, yaml.YAMLError):
    """Il file di configurazione c'e' ma non si lascia leggere (issue #257).

    Stessa ereditarieta' doppia della sorella qui sopra e per la stessa
    ragione: `yaml.YAMLError` e' dichiarato nei `Raises` di `load_yaml` e di
    `api.load_generator`. Prima della #257 nessuno lo traduceva, e uno YAML
    malformato usciva dal ramo generico della CLI -- messaggio piu' traceback
    invece di un `user_message()`. E' lo stesso difetto un gradino piu' in
    la' del file che manca: chiuderne uno solo avrebbe lasciato la gerarchia
    coperta a meta'.

    `problem` e `problem_mark` di PyYAML dicono gia' cosa e dove: la
    posizione non si stima, si legge.
    """

    def __init__(self, path: str, reason: str,
                 line: int | None = None, column: int | None = None):
        self.path = path
        self.reason = reason
        self.line = line
        self.column = column
        posizione = f" (riga {line}, colonna {column})" if line is not None else ""
        super().__init__(f"YAML non valido in '{path}'{posizione}: {reason}")
        self.config_file = path

    @classmethod
    def from_yaml_error(cls, path: str, err: Exception) -> "ConfigParseError":
        """Costruisce dall'errore di PyYAML, marca inclusa quando c'e'.

        `problem_mark` esiste solo su MarkedYAMLError: un YAMLError generico
        conserva il motivo e non si inventa una posizione.
        """
        reason = getattr(err, 'problem', None)
        if not reason:
            testo = str(err).strip()
            reason = testo.splitlines()[0] if testo else type(err).__name__
        mark = getattr(err, 'problem_mark', None)
        # PyYAML conta righe e colonne da 0, gli editor da 1.
        line = mark.line + 1 if mark is not None else None
        column = mark.column + 1 if mark is not None else None
        return cls(path, reason, line=line, column=column)

    def user_message(self) -> str:
        lines = [
            "[ERRORE] YAML non valido",
            f"  Motivo:       {self.reason}",
        ]
        if self.line is not None:
            lines.append(
                f"  Posizione:    riga {self.line}, colonna {self.column}")
        lines.extend(self._context_lines())
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

    NON eredita FileNotFoundError di proposito, ed e' meta' di una regola
    che la #257 ha chiuso dall'altro lato: dentro EngineError quel builtin
    significa una cosa sola -- il file di configurazione che l'utente ha
    nominato non esiste (`ConfigFileNotFoundError`). Un binario mancante che
    lo ereditasse si confonderebbe con quello. Fino alla #241 si confondeva
    davvero: la CLI intercettava il builtin per annunciare 'file YAML non
    trovato', e chi non aveva csound si sentiva dire che mancava il suo YAML.
    Quell'handler non esiste piu' (#257) e il messaggio falso non puo' piu'
    arrivare da li'; la regola resta perche' ora e' il *tipo* a collocare
    l'errore, e un secondo erede la romperebbe di nuovo -- lo dice
    `tests/shared/test_engine_exceptions.py::test_solo_la_configurazione_e_un_FileNotFoundError`.
    Il tipo di un errore serve a chi lo cattura, non a descriverne la causa.

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
