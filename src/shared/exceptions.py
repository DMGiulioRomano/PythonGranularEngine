# =============================================================================
# src/shared/exceptions.py
# =============================================================================
"""
Gerarchia EngineError per errori engine destinati a output user-facing pulito
(issue #33). Ogni eccezione fornisce user_message() per il terminale e
__str__ per i log.
"""


class EngineError(Exception):
    """Base per errori dell'engine. Sottoclassi forniscono user_message()."""

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
