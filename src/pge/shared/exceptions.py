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

# `ConfigParseError` eredita `yaml.YAMLError`, e una classe base deve esistere
# nel momento in cui la classe *si crea*: l'import non puo' essere lazy. Ma
# nemmeno duro, e la ragione non e' il pyproject -- PyYAML e' dipendenza
# dichiarata del pacchetto. E' che questo modulo sta sotto quasi ogni altro,
# `pge/__init__.py` compreso, che di se' dichiara di ri-esportare «solo simboli
# leggeri»: un import duro qui mette PyYAML fra le dipendenze di import
# dell'intero motore, comprese le parti che YAML non lo parsano.
#
# Il conto lo paga chi importa il motore da un checkout senza installarlo:
# l'oracolo di parita' di PGE-ui (`tests/parity/engine_oracle.py`) importa otto
# moduli del motore con il solo python del runner, per contratto scritto («No op
# may need the engine venv»). Nessuno di quegli otto ha una dipendenza di terze
# parti; con `import yaml` qui smettevano tutti di importarsi, e il rosso
# sarebbe arrivato su ogni PR di un altro repository. La meta' di loro l'oracolo
# la chiede dentro un `try/except` che scrive `None` nel payload invece di
# morire: rosso comunque a valle, e piu' muto -- da qui l'elenco intero in
# `_MODULI_SENZA_TERZE_PARTI` (`tests/shared/test_engine_exceptions.py`), che e'
# la forma eseguibile di questo commento e blocca ogni dipendenza dichiarata,
# non la sola PyYAML.
#
# Il ripiego non e' una degradazione silenziosa: dove PyYAML manca, `yaml` non
# e' nominabile, quindi nessuno puo' scrivere l'`except yaml.YAMLError` che la
# doppia ereditarieta' tiene in piedi -- e `ConfigParseError` non e' nemmeno
# sollevabile, perche' a sollevarla e' `Generator.load_yaml`, in un modulo che
# PyYAML lo importa davvero. `PYYAML_ASSENTE` rende il ramo osservabile, e due
# test lo fissano nelle due direzioni.
try:
    from yaml import YAMLError as _YamlError, MarkedYAMLError as _MarkedYamlError
    # `ReaderError` non sta nel namespace `yaml` (`yaml/__init__.py` non lo
    # ri-esporta), quindi va chiesto al sottomodulo: e' l'unica ragione per cui
    # qui gli import da PyYAML sono due e non uno. Stesso `try`, cosi' resta una
    # cosa sola che riesce o fallisce -- un ripiego a meta' darebbe una
    # `ConfigParseError` senza la sua sottoclasse, senza che niente lo dica.
    from yaml.reader import ReaderError as _ReaderError
    PYYAML_ASSENTE = False
except ImportError:  # PyYAML non installato: vedi sopra
    class _YamlError(Exception):
        """Segnaposto per `yaml.YAMLError` dove PyYAML non c'e'."""

    class _MarkedYamlError(_YamlError):
        """Segnaposto per `yaml.MarkedYAMLError`; eredita l'altro come
        l'originale, cosi' l'MRO delle sottoclassi non cambia forma."""

    class _ReaderError(_YamlError):
        """Segnaposto per `yaml.reader.ReaderError`; come l'originale eredita
        `YAMLError` e non `MarkedYAMLError`."""

    PYYAML_ASSENTE = True


#: Larghezza del cappello di una riga di `user_message()` -- i due spazi di
#: rientro piu' il nome del campo giustificato (`  Dettaglio:    `,
#: `  Riga/colonna: `). Un valore che debba andare a capo si incolonna qui
#: sotto, cosi' il seguito resta dentro il blocco invece di leggersi come un
#: campo senza nome.
_INDENTO_VALORE = ' ' * 16


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
        # `Exception.__init__` esplicito, non `super()`: le sottoclassi della
        # #257 mescolano un builtin, e alcuni builtin hanno un `__init__`
        # proprio che sta *dopo* ConfigError nell'MRO e intercetterebbe il
        # messaggio. `UnicodeDecodeError.__init__` vuole cinque argomenti e
        # alza `TypeError` su uno; `MarkedYAMLError.__init__` ne accetta uno e
        # lo scrive in `context`, lasciando `args` vuoto -- cioe' fallisce in
        # silenzio, che e' peggio. Qui serve solo che `args` porti il
        # messaggio: e' quello che `__str__` e `user_message()` leggono, e per
        # i campi del builtin provvede ciascuna sottoclasse. Stessa forma del
        # prezzo gia' pagato con gli `__str__` piu' sotto.
        Exception.__init__(self, message)

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

    # `__reduce__` proprio: il default ripassa `self.args` al costruttore, e il
    # costruttore di queste classi vuole il *path*. I builtin che la #257
    # sostituisce erano tutti picklabili -- e' cosi' che un'eccezione
    # attraversa un confine di processo, il meccanismo con cui
    # `ProcessPoolExecutor` (quello di `numpy_parallel`) la ripaga nel parent
    # -- quindi impacchettarli senza questo metodo e' una regressione. I due
    # modi di rompersi sono diversi e uno dei due e' muto: chi ha due
    # argomenti alza `TypeError` in unpickling, chi ne ha uno rientra col
    # messaggio gia' costruito al posto del path e ne esce impacchettato due
    # volte.
    def __reduce__(self):
        return (self.__class__, (self.path,), self.__dict__)

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


class ConfigParseError(ConfigError, _YamlError):
    """File di configurazione YAML illeggibile (issue #257).

    Il gradino successivo a `ConfigFileNotFoundError`: il file c'e' ma non si
    parsa. Prima nessuno traduceva `yaml.YAMLError` e l'utente riceveva
    messaggio piu' traceback dal ramo generico della CLI.

    Eredita anche `yaml.YAMLError` per la stessa ragione dell'altra classe: e'
    il tipo che `load_yaml` e `api.load_generator` promettono nei `Raises`.
    La base e' `_YamlError`, che *e'* `yaml.YAMLError` ovunque PyYAML sia
    installato -- e un segnaposto solo dove non lo e', per non far pagare
    PyYAML all'import dell'intero motore: la ragione sta in testa al modulo.
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

    # `__reduce__` proprio, per la ragione scritta per esteso su
    # `ConfigFileNotFoundError` e non ricopiata qui: una ragione in tre copie
    # e' una ragione che diverge. Di quei due modi di rompersi questo e'
    # quello rumoroso -- il costruttore vuole due argomenti e il default gli
    # ripassa il solo `self.args`, cioe' `TypeError` in unpickling.
    def __reduce__(self):
        return (self.__class__, (self.path, self.cause), self.__dict__)

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
        # Il ripiego `str(self.cause)` puo' parlare su piu' righe, e allora
        # quelle dopo la prima uscivano dal blocco senza nome di campo: una
        # riga che si legge come un campo rotto, fra `Dettaglio:` e il
        # `Dettagli:` che `_handle_engine_error` appende subito sotto. Non e'
        # un caso di scuola -- `yaml.reader.ReaderError` e' l'unico
        # `yaml.YAMLError` del percorso di caricamento che non sia un
        # `MarkedYAMLError` (gli altri quattro non marcati stanno sul lato
        # dump), quindi e' l'unico a cadere qui, e il suo `__str__` e' due
        # righe *sempre*. Il seguito si incolonna sotto il valore invece di
        # essere buttato via: la seconda riga porta `position N`, la sola cosa
        # che dica *dove* sta il carattere rifiutato. Il contratto della Sez. 2
        # di `docs/reference/errors.md` e' righe `  <Campo>: <valore>`, e ogni
        # altra classe lo rispetta -- `_SubprocessRenderError` arriva a pescare
        # *una* riga da uno stderr intero pur di non violarlo.
        prima, *seguito = [r.strip() for r in dettaglio.splitlines()] or ['']
        lines.append(f"  Dettaglio:    {prima}")
        lines.extend(f"{_INDENTO_VALORE}{riga}" for riga in seguito if riga)
        return "\n".join(lines)


class ConfigReadError(ConfigError, OSError):
    """Il file di configurazione c'e' ma il sistema operativo non lo apre
    (issue #257).

    Gli altri due chiudono ENOENT e il contenuto illeggibile; `open()` pero'
    fallisce anche per ragioni che non sono ne' l'una ne' l'altro, e la piu'
    probabile e' la piu' banale: `pge configs/ out.wav`, il typo che la
    tab-completion della shell fabbrica da sola fermandosi sulla directory.
    `IsADirectoryError` non e' un `FileNotFoundError` e non e' un
    `yaml.YAMLError`, quindi restava l'unico modo di sbagliare il path del
    proprio YAML a uscire come traceback dal ramo generico della CLI --
    accanto a `PermissionError` e al resto di `OSError`. Il guasto e' lo
    stesso degli altri tre (il file di configurazione non si legge), quindi
    lo e' anche il tipo.

    Eredita `OSError` per la ragione delle altre due: e' cio' che `load_yaml`
    lasciava salire, e chi lo cattura per nome deve continuare a catturarlo.
    E per la ragione dell'asimmetria con `_BinaryNotFoundError`: qui il
    builtin dice il vero.

    Deliberatamente NON eredita `FileNotFoundError`: una directory non e' un
    file mancante, e il tipo che mente e' il difetto che questa issue chiude.
    """

    def __init__(self, path: str, cause: OSError):
        super().__init__(f"File di configurazione non leggibile: '{path}'")
        self.path = path
        self.cause = cause
        self.config_file = path
        # Riportati dalla causa, non fabbricati: `errno` e `strerror` sono
        # cio' che distingue EISDIR da EACCES, ed e' l'unica cosa che il
        # messaggio puo' dire in piu' di quanto l'utente gia' sappia. Stessa
        # ragione dei tre campi di `ConfigFileNotFoundError`: chi cattura
        # l'`OSError` non si ferma alla cattura, ne legge lo stato.
        self.errno = getattr(cause, 'errno', None)
        self.strerror = getattr(cause, 'strerror', None)
        self.filename = getattr(cause, 'filename', None) or path

    # `__reduce__` proprio, per la ragione scritta per esteso su
    # `ConfigFileNotFoundError` e non ricopiata qui: una ragione in tre copie
    # e' una ragione che diverge. Di quei due modi di rompersi questo e'
    # quello rumoroso -- il costruttore vuole due argomenti e il default gli
    # ripassa il solo `self.args`, cioe' `TypeError` in unpickling.
    def __reduce__(self):
        return (self.__class__, (self.path, self.cause), self.__dict__)

    def __str__(self) -> str:
        # Stesso prezzo gia' pagato da `ConfigFileNotFoundError`: con
        # `filename` valorizzato `OSError.__str__` smette di stampare
        # `args[0]` e riscrive la riga che finisce nel log engine.
        return self.args[0]

    def user_message(self) -> str:
        # Nessuna riga `Config:`, come per l'altra: il file e' il soggetto del
        # head. Nessuna riga `Path cercato:` invece, e questa e' una
        # differenza: li' il path assoluto rispondeva a «sei nella directory
        # sbagliata», qui il file e' stato trovato e la domanda e' un'altra.
        lines = [f"[ERRORE] File di configurazione non leggibile: '{self.path}'"]
        dettaglio = self.strerror or str(self.cause)
        lines.append(f"  Dettaglio:    {dettaglio}")
        return "\n".join(lines)


# =============================================================================
# Il tipo *concreto* della causa (issue #257)
# =============================================================================
#
# Impacchettare e' un guadagno finche' non toglie. Prima della #257 `load_yaml`
# lasciava salire l'eccezione concreta di `open()` e del parser, quindi un
# `except IsADirectoryError` o un `isinstance(e, yaml.MarkedYAMLError)` scritti
# a valle funzionavano; una classe che eredita il solo tipo *generico*
# (`OSError`, `yaml.YAMLError`) li fa smettere di funzionare, e in silenzio.
# E' la stessa promessa che `ConfigFileNotFoundError` mantiene verso
# `FileNotFoundError`: mantenerla a meta' era una scelta che nessuno aveva
# preso.
#
# La regola non cambia -- il tipo deve dire il vero -- e qui il builtin dice il
# vero: e' quello che il sistema operativo, o il parser, hanno sollevato. Il
# guasto e' sempre lo stesso, quindi la base di dominio (e il messaggio, e
# `user_message()`) e' sempre la stessa: la sottoclasse aggiunge il tipo e
# nient'altro.
#
# Il prezzo e' quello gia' pagato due volte per `OSError.__str__`: il builtin
# mescolato porta spesso un `__str__` suo, che riscriverebbe proprio la riga
# che finisce nel log engine. Ogni sottoclasse che ne mescola uno se lo
# riprende.


class ConfigIsADirectoryError(ConfigReadError, IsADirectoryError):
    """`pge configs/ out.wav`: la tab-completion si e' fermata sulla directory."""


class ConfigNotADirectoryError(ConfigReadError, NotADirectoryError):
    """Il typo gemello: un segmento del path e' un file, non una directory."""


class ConfigPermissionError(ConfigReadError, PermissionError):
    """Il file c'e' e si legge, ma non da questo utente."""


#: Il tipo di dominio per ciascun builtin di `OSError` che qualcuno cattura per
#: nome. Corta di proposito: ci sono i tre che descrivono il *path* -- cioe' i
#: modi in cui l'utente sbaglia a nominare il proprio YAML -- e non i quindici
#: che descrivono la macchina (`ConnectionResetError` su un file di
#: configurazione sarebbe una classe che non vuol dire niente). Il ripiego non
#: e' un buco: `ConfigReadError` resta un `OSError` e porta `errno`, che e'
#: esattamente cio' che distingue un builtin dall'altro. Un test verifica che
#: ogni voce erediti la propria chiave, cosi' la tabella non puo' mentire.
LETTURA_PER_BUILTIN = {
    IsADirectoryError: ConfigIsADirectoryError,
    NotADirectoryError: ConfigNotADirectoryError,
    PermissionError: ConfigPermissionError,
}


def config_read_error(path: str, cause: OSError) -> ConfigReadError:
    """`ConfigReadError`, nella sottoclasse che eredita anche il tipo concreto
    della causa quando ce n'e' una.

    Le chiavi della tabella sono sorelle disgiunte, quindi l'ordine della
    scansione non decide niente.
    """
    for builtin, classe in LETTURA_PER_BUILTIN.items():
        if isinstance(cause, builtin):
            return classe(path, cause)
    return ConfigReadError(path, cause)


class ConfigMarkedParseError(ConfigParseError, _MarkedYamlError):
    """Uno YAML malformato che porta con se' la posizione dell'errore.

    `problem_mark` e' gia' riportato sull'eccezione, ma l'idioma completo con
    cui si legge un errore PyYAML e' `isinstance(e, MarkedYAMLError)` *poi*
    `e.problem_mark`: il tipo e' la domanda «questa eccezione porta una
    posizione?», e il solo `YAMLError` rispondeva no a un errore che la
    posizione ce l'ha.
    """

    def __str__(self) -> str:
        # `MarkedYAMLError.__str__` riscriverebbe il messaggio nel formato di
        # PyYAML -- contesto, snippet, freccia -- proprio nella riga che
        # finisce nel log engine. Stesso prezzo di `OSError.__str__`.
        return self.args[0]


class ConfigUnicodeParseError(ConfigParseError, UnicodeDecodeError):
    """Il `.yml` che non si decodifica: prima saliva come builtin nudo.

    `UnicodeDecodeError` e' un `ValueError`, quindi `except ValueError`
    reggeva comunque per via della base `ConfigError`; a cadere era il nome
    esatto, che e' quello che si scrive quando si sa cosa si sta cercando.
    """

    #: Lo stato che `UnicodeDecodeError` espone, e che chi lo cattura legge:
    #: `e.object[e.start:e.end]` sono i byte incriminati, `e.reason` il perche'.
    #: Riportati dalla causa con la regola degli attributi di PyYAML -- mai
    #: fabbricati -- perche' qui il valore vuoto del tipo non e' un'assenza
    #: leggibile: `start` ed `end` varrebbero `0`, cioe' una posizione
    #: plausibile e falsa.
    _ATTRIBUTI_UNICODE = ('encoding', 'object', 'start', 'end', 'reason')

    def __init__(self, path: str, cause: Exception):
        super().__init__(path, cause)
        # `UnicodeDecodeError.__init__` non viene chiamato (vuole cinque
        # argomenti e intercetterebbe il messaggio: la ragione sta su
        # `ConfigError.__init__`), quindi i cinque campi resterebbero al
        # valore vuoto del tipo. Ereditare `UnicodeDecodeError` senza di loro
        # e' la meta' della promessa che regge per `isinstance` e cade per
        # tutto il resto -- lo stesso guasto chiuso sui tre campi `OSError` di
        # `ConfigFileNotFoundError` e sugli attributi di `MarkedYAMLError`.
        for attributo in self._ATTRIBUTI_UNICODE:
            if hasattr(cause, attributo):
                setattr(self, attributo, getattr(cause, attributo))

    def __str__(self) -> str:
        # Come sopra: `UnicodeDecodeError.__str__` scrive «'utf-8' codec can't
        # decode byte ...», che e' la riga di `Dettaglio:`, non il messaggio.
        return self.args[0]


class ConfigReaderParseError(ConfigParseError, _ReaderError):
    """Il carattere che il parser rifiuta prima ancora di leggere un token.

    `yaml.reader.ReaderError` e' l'unico `yaml.YAMLError` che il *load* possa
    sollevare senza essere un `MarkedYAMLError` -- gli altri quattro non
    marcati (Emitter, Representer, Serializer, Resolver) stanno sul lato dump
    -- quindi era l'ultimo caso in cui impacchettare *toglieva*: la base sola
    faceva sparire `e.position` ed `e.character`, che dicono quale carattere e
    dove, e sono l'unico posto in cui quell'informazione esista.

    Non porta un `problem_mark` (non e' marcato) ma porta una posizione sua,
    in caratteri invece che in riga/colonna: il tipo e' quindi
    `ConfigParseError` e non `ConfigMarkedParseError`, come nell'originale.
    """

    #: Lo stato che `ReaderError` espone: `character` e `position` sono il
    #: carattere rifiutato e il suo offset, `reason` il perche'. Riportati
    #: dalla causa con la regola degli altri due, mai fabbricati.
    _ATTRIBUTI_READER = ('name', 'character', 'position', 'encoding', 'reason')

    def __init__(self, path: str, cause: Exception):
        super().__init__(path, cause)
        for attributo in self._ATTRIBUTI_READER:
            if hasattr(cause, attributo):
                setattr(self, attributo, getattr(cause, attributo))

    def __str__(self) -> str:
        # Come per gli altri: `ReaderError.__str__` scrive due righe col nome
        # del file e la posizione, cioe' il testo di `Dettaglio:`, non il
        # messaggio -- e quella e' la riga che finisce nel log engine.
        return self.args[0]


def config_parse_error(path: str, cause: Exception) -> ConfigParseError:
    """`ConfigParseError`, nella sottoclasse che eredita anche il tipo
    concreto della causa quando ce n'e' una.

    Un `yaml.YAMLError` davvero nudo resta la base: non porta ne' posizione ne'
    stato, e il tipo non deve dire il contrario -- la stessa ragione per cui gli
    attributi di `MarkedYAMLError` sono riportati e mai fabbricati. Sul percorso
    di caricamento sono nudi solo quelli costruiti a mano: PyYAML, quando
    rifiuta un file, solleva o un `MarkedYAMLError` o un `ReaderError`.
    """
    if isinstance(cause, _MarkedYamlError):
        return ConfigMarkedParseError(path, cause)
    if isinstance(cause, _ReaderError):
        return ConfigReaderParseError(path, cause)
    if isinstance(cause, UnicodeDecodeError):
        return ConfigUnicodeParseError(path, cause)
    return ConfigParseError(path, cause)


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
        # `Exception.__init__` esplicito, non `super()`: la stessa forma di
        # `ConfigError.__init__`, dove la ragione e' scritta per esteso. Qui
        # nessuna sottoclasse mescola un builtin -- `_BinaryNotFoundError`
        # sceglie di proposito di non farlo (#228, #241) -- quindi la chiamata
        # non cambia niente oggi: tiene simmetriche le due basi per il giorno
        # in cui una sottoclasse di questo ramo mescoli un builtin col proprio
        # `__init__`, che intercetterebbe il messaggio.
        Exception.__init__(self, message)

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
