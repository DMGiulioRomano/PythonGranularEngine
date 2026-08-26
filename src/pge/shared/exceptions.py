# =============================================================================
# src/shared/exceptions.py
# =============================================================================
"""
Gerarchia EngineError per errori engine destinati a output user-facing pulito
(issue #33). Ogni eccezione fornisce user_message() per il terminale e
__str__ per i log.
"""
from __future__ import annotations


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


class CsoundRenderError(EngineRuntimeError, RuntimeError):
    """Subprocess csound fallito (issue #38, PR4).

    Eredita RuntimeError per backward-compat.
    """

    def __init__(self, returncode: int, command: list[str], stderr: str):
        self.returncode = returncode
        self.command = list(command)
        self.stderr = stderr
        super().__init__(
            f"Csound ha fallito con codice {returncode}.\n"
            f"Comando: {' '.join(command)}\n"
            f"Stderr: {stderr}"
        )

    def user_message(self) -> str:
        lines = [
            f"[ERRORE] Csound rendering fallito (exit code {self.returncode})",
            f"  Comando:      {' '.join(self.command)}",
        ]
        if self.stderr.strip():
            stderr_first = self.stderr.strip().splitlines()[0]
            lines.append(f"  Stderr:       {stderr_first}")
        lines.extend(self._context_lines())
        return "\n".join(lines)


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


class SuperColliderRenderError(EngineRuntimeError, RuntimeError):
    """Subprocess SuperCollider fallito -- scsynth o sclang (issue #228).

    Eredita RuntimeError come la sorella Csound, per simmetria con i catch
    generici gia' in giro.
    """

    def __init__(self, returncode: int, command: list[str], stderr: str,
                 stage: str = "scsynth"):
        self.returncode = returncode
        self.command = list(command)
        self.stderr = stderr
        # 'scsynth' (rendering) o 'sclang' (compilazione della SynthDef): due
        # guasti con due rimedi diversi, e il messaggio deve dire quale.
        self.stage = stage
        super().__init__(
            f"{stage} ha fallito con codice {returncode}.\n"
            f"Comando: {' '.join(command)}\n"
            f"Stderr: {stderr}"
        )

    def user_message(self) -> str:
        lines = [
            f"[ERRORE] {self.stage} fallito (exit code {self.returncode})",
            f"  Comando:      {' '.join(self.command)}",
        ]
        if self.stderr.strip():
            stderr_first = self.stderr.strip().splitlines()[0]
            lines.append(f"  Stderr:       {stderr_first}")
        lines.extend(self._context_lines())
        return "\n".join(lines)


class SuperColliderNotFoundError(EngineRuntimeError):
    """Binario SuperCollider o sorgente della SynthDef non trovati (issue #228).

    NON eredita FileNotFoundError di proposito: la CLI intercetta quel tipo
    per annunciare 'file YAML non trovato', e un binario mancante che
    passasse di li' verrebbe riportato come una configurazione inesistente.
    """

    def __init__(self, what: str, hint: str | None = None):
        self.what = what
        self.hint = hint
        super().__init__(f"SuperCollider: {what} non trovato")

    def user_message(self) -> str:
        lines = [f"[ERRORE] SuperCollider: {self.what} non trovato"]
        if self.hint:
            lines.append(f"  Hint:         {self.hint}")
        lines.extend(self._context_lines())
        return "\n".join(lines)
