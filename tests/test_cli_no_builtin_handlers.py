"""`cli.main()` non cattura piu' nessun builtin sul percorso di caricamento
(issue #257).

## Il difetto

La #241 aveva chiuso il caso csound assente dando al binario mancante un tipo
suo. Restava il capo a monte: `Generator.load_yaml` sollevava un
`FileNotFoundError` nudo, e `main()` lo intercettava per stampare
« Errore: file 'x.yml' non trovato». Che quel messaggio fosse vero dipendeva da
un fatto fragile — dentro quel blocco `try` nessun'altra riga apriva un secondo
file — cioe' dall'**estensione fisica** del blocco, non dal **tipo**
dell'eccezione. Niente lo faceva fallire il giorno in cui smetteva di valere:
una pre-scansione dei sample, una validazione di `--samples-dir`, o il
passaggio della CLI ad `api.load_generator` (che impacchetta anche
`create_elements`, dove i sample *si aprono davvero*) rimettevano in circolo il
messaggio falso, in silenzio.

## Le tre guardie

- **Strutturale**: nessun `try` che avvolge il caricamento dello YAML cattura un
  tipo builtin — restano `EngineError` e il ramo generico, in quest'ordine — e
  nessun handler *annidato* dentro quel blocco ne cattura uno. La distinzione
  non e' teorica: un `try/except` messo attorno al solo render vive dentro il
  blocco della pipeline senza contenere `load_yaml()`, quindi
  `_try_del_caricamento` non lo vede, e un `except:` nudo li' dentro
  intercetterebbe anche l'`EngineError` che i due rami di fuori esistono per
  ricevere. Questa e' la garanzia *per tipo*.
- **Di raggio**: nessun handler di `cli.py` — pipeline o no — cattura un errore
  della famiglia `OSError`. E' la famiglia che risale da qualunque profondita'
  di I/O (csound assente, #241; un sample illeggibile; un disco pieno), cioe'
  l'unica che il tipo da solo non basta a collocare: una `except
  FileNotFoundError` che tornasse in questo file avrebbe di nuovo bisogno di
  stare *nel punto giusto* per non mentire. Gli `except ValueError` attorno a
  `int()`/`float()` su `sys.argv` non sono di quella famiglia e restano leciti.
- **Comportamentale**: un `FileNotFoundError` sollevato **dentro** quel blocco
  ma per un file che non e' lo YAML non fa dire all'utente che manca la sua
  configurazione. E' il test che sabota la premessa invece di riasserirla:
  prima della #257 sarebbe stato rosso, e nessuno se ne sarebbe accorto.

## E le guardie sono misurate

`TestLaGuardiaMisurata` sabota dei sorgenti finti, non `cli.py`: e' l'unico
modo di sapere che una guardia strutturale vede davvero cio' che dichiara di
vedere, invece di essere verde perche' non guarda. Le tre forme che misura
sono quelle su cui una lettura ingenua tacerebbe — l'`except:` nudo (non
nomina nessun builtin), l'handler annidato in un `finally:`, e gli handler
legittimi, che devono restare tali.
"""

import ast
import builtins
import inspect
import sys

import pytest
from unittest.mock import patch

from tests.main_mocks import mocks  # noqa: F401  (fixture pytest)


# Il sorgente del modulo *importato*, non un path ricostruito a mano.
import pge.cli as _cli_module

CLI_PATH = inspect.getsourcefile(_cli_module)

# I due soli handler ammessi sul percorso di caricamento, nell'ordine in cui
# devono comparire: `EngineError` per primo, o il ramo generico lo copre.
HANDLER_ATTESI = ['EngineError', 'Exception']


def _albero(sorgente=None):
    """L'AST di `cli.py`, o quello di un sorgente finto da misurare."""
    if sorgente is not None:
        return ast.parse(sorgente, filename='<sabotaggio>')
    with open(CLI_PATH, encoding='utf-8') as fh:
        return ast.parse(fh.read(), filename=CLI_PATH)


def _main_di_cli(albero=None):
    albero = _albero() if albero is None else albero
    return next(n for n in albero.body
                if isinstance(n, ast.FunctionDef) and n.name == 'main')


def _builtin_exception(nome):
    """La classe builtin omonima, se e' un'eccezione; altrimenti None.

    Derivata da `builtins`, non da un elenco trascritto: un elenco andrebbe
    aggiornato da chi aggiunge l'handler, cioe' proprio da chi non ci pensa.
    """
    cls = getattr(builtins, nome, None)
    if isinstance(cls, type) and issubclass(cls, BaseException):
        return cls
    return None


def _colpevole(handler, famiglia=None):
    """Perche' questo `except` viola la regola, o None se non la viola.

    `famiglia` restringe ai builtin che ereditano da quel tipo; None
    significa «qualunque builtin».

    Un `except:` nudo e' colpevole in entrambe le letture, e va detto qui e
    non in ognuna delle guardie: non nomina niente, quindi una guardia
    scritta sui soli nomi lo lascerebbe passare — restando verde proprio
    sull'handler piu' largo che esista, che cattura tutta la famiglia
    `OSError` e anche `EngineError`. E' la stessa distinzione che la #257
    corregge nel codice: la garanzia non puo' dipendere da come l'handler e'
    scritto.
    """
    if handler.type is None:
        return 'except: nudo (cattura tutto, famiglia OSError compresa)'
    for nome in _nomi_catturati(handler):
        cls = _builtin_exception(nome)
        if cls is not None and (famiglia is None or issubclass(cls, famiglia)):
            return nome
    return None


def _handler_annidati(blocco):
    """Gli `except` che vivono *dentro* il blocco, a qualunque profondita'.

    `body` piu' `orelse` e `finalbody`: un handler messo in un `finally:` (o
    in un `else:`) sta dentro il blocco quanto uno messo nel corpo. I
    `handlers` del blocco stesso restano fuori ed e' l'unica esclusione: li'
    i due rami sono `EngineError` e `Exception`, cioe' un builtin per
    costruzione, e li fissa `test_handler_attesi_e_nel_loro_ordine`.
    """
    return [n
            for corpo in list(blocco.body) + list(blocco.orelse)
            + list(blocco.finalbody)
            for n in ast.walk(corpo)
            if isinstance(n, ast.ExceptHandler)]


def _contiene_load_yaml(nodo):
    """Il nodo contiene, a qualunque profondita', una chiamata a load_yaml()?"""
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == 'load_yaml'
        for n in ast.walk(nodo)
    )


def _try_del_caricamento(albero=None):
    """Ogni `try` di `main()` che avvolge il caricamento dello YAML.

    Plurale di proposito: un `try` annidato attorno alle sole due righe del
    caricamento e' esattamente la forma che la #257 sostituisce, quindi la
    guardia deve vederlo e non solo quello piu' esterno.
    """
    return [n for n in ast.walk(_main_di_cli(albero))
            if isinstance(n, ast.Try) and _contiene_load_yaml(n)]


def _nomi_catturati(handler):
    """I nomi dei tipi catturati da un `except`; `[None]` per un except nudo."""
    if handler.type is None:
        return [None]
    tipi = (handler.type.elts if isinstance(handler.type, ast.Tuple)
            else [handler.type])
    return [t.id if isinstance(t, ast.Name) else ast.unparse(t) for t in tipi]


class TestGuardiaStrutturale:
    """La garanzia e' sul tipo, non sulla lunghezza del blocco."""

    def test_il_caricamento_dello_yaml_sta_dentro_un_try(self):
        """Premessa delle altre due: se sparisse, sarebbero vacue."""
        assert _try_del_caricamento(), (
            "nessun try di main() avvolge load_yaml(): la guardia sotto "
            "non misura piu' niente")

    def test_nessun_handler_builtin_attorno_al_caricamento(self):
        for nodo in _try_del_caricamento():
            for handler in nodo.handlers:
                for nome in _nomi_catturati(handler):
                    if nome is None:
                        pytest.fail("except nudo attorno al caricamento")
                    if nome == 'Exception':
                        continue  # il ramo generico, esplicitamente ammesso
                    assert not hasattr(builtins, nome), (
                        f"main() cattura il builtin '{nome}' attorno al "
                        f"caricamento dello YAML: e' il difetto della #257 — "
                        f"il tipo deve essere di dominio (EngineError)")

    def test_handler_attesi_e_nel_loro_ordine(self):
        """`EngineError` prima del ramo generico, o non viene mai raggiunto."""
        for nodo in _try_del_caricamento():
            nomi = [n for h in nodo.handlers for n in _nomi_catturati(h)]
            assert nomi == HANDLER_ATTESI, (
                f"handler attorno al caricamento: {nomi}, "
                f"attesi {HANDLER_ATTESI}")

    def test_nessun_handler_builtin_annidato_nel_blocco(self):
        """L'altro modo di rimettere in circolo il messaggio falso.

        `_try_del_caricamento` trova i `try` che *contengono* `load_yaml()`;
        un `try/except` messo attorno al solo render sta dentro il blocco
        della pipeline senza contenerlo, quindi da li' non si vede. Ed e'
        proprio quello il punto in cui un `except FileNotFoundError` — o un
        `except:` nudo, che intercetta anche l'`EngineError` dei due rami di
        fuori — tornerebbe a dipendere dalla propria posizione.
        """
        colpevoli = [(motivo, h.lineno)
                     for blocco in _try_del_caricamento()
                     for h in _handler_annidati(blocco)
                     for motivo in [_colpevole(h)] if motivo is not None]
        assert not colpevoli, (
            "un handler su un tipo builtin e' tornato dentro il try della "
            f"pipeline: {colpevoli}. Il messaggio che ne esce vale finche' "
            "il blocco non cresce, e cresce senza che nessun test lo dica "
            "(issue #257).")


def test_cli_non_cattura_nessun_errore_della_famiglia_oserror():
    """La guardia di raggio: vale su tutto `cli.py`, pipeline o no.

    Le altre due leggono il blocco della pipeline, e leggerlo basta finche'
    il blocco e' dove il caricamento avviene. La famiglia `OSError` no: e'
    quella che risale da qualunque profondita' di I/O, quindi un handler
    piazzato *fuori* dal blocco la intercetterebbe lo stesso — e con lei
    l'errore di dominio che la #257 ha creato apposta per non passare di li'.
    """
    colpevoli = [(motivo, nodo.lineno)
                 for nodo in ast.walk(_albero())
                 if isinstance(nodo, ast.ExceptHandler)
                 for motivo in [_colpevole(nodo, famiglia=OSError)]
                 if motivo is not None]
    assert not colpevoli, (
        "pge/cli.py cattura di nuovo un errore della famiglia OSError: "
        f"{colpevoli}. Un guasto di I/O risale da qualunque profondita', "
        "quindi il tipo non basta a collocarlo e il messaggio torna a "
        "dipendere da dove sta l'handler (issue #241/#257). Dagli un tipo "
        "di dominio nel punto che lo produce, come ConfigFileNotFoundError.")


def _esegui(mocks, argv):
    """main() con argv; ritorna il codice di uscita."""
    with patch.object(sys, 'argv', argv):
        with pytest.raises(SystemExit) as exc:
            mocks['main'].main()
    return exc.value.code


class TestSabotaggioDellaPremessa:
    """Un `FileNotFoundError` che *non* riguarda lo YAML, dentro il blocco."""

    def test_file_not_found_da_create_elements_non_accusa_lo_yaml(
            self, mocks, capsys):
        """Il caso reale: `api.load_generator` impacchetta anche
        `create_elements`, dove i sample si aprono davvero."""
        mocks['generator_instance'].create_elements.side_effect = (
            FileNotFoundError("refs/pino.wav"))

        assert _esegui(mocks, ['main.py', 'presente.yml', 'out.aif']) == 1
        out = capsys.readouterr().out
        assert "file 'presente.yml' non trovato" not in out
        assert "File di configurazione non trovato" not in out

    def test_file_not_found_dal_caricamento_stesso_non_accusa_lo_yaml(
            self, mocks, capsys):
        """Anche dentro `load_yaml`: un builtin nudo non e' piu' una diagnosi.

        E' il caso della pre-scansione o dell'`include` che apre un secondo
        file: la riga in piu' sta proprio li' dentro.
        """
        mocks['generator_instance'].load_yaml.side_effect = (
            FileNotFoundError("un altro file"))

        assert _esegui(mocks, ['main.py', 'presente.yml', 'out.aif']) == 1
        out = capsys.readouterr().out
        assert "file 'presente.yml' non trovato" not in out
        assert "File di configurazione non trovato" not in out

    def test_il_builtin_finisce_nel_ramo_generico(self, mocks, capsys):
        """Messaggio dell'eccezione su stdout, traceback su stderr."""
        mocks['generator_instance'].create_elements.side_effect = (
            FileNotFoundError("refs/pino.wav"))

        _esegui(mocks, ['main.py', 'presente.yml', 'out.aif'])
        captured = capsys.readouterr()
        assert 'refs/pino.wav' in captured.out
        assert 'Traceback' in captured.err


class TestMessaggiDiDominio:
    """Lo YAML che manca e quello malformato, dopo la #257."""

    def test_yaml_mancante_ha_il_messaggio_di_casa(self, mocks, capsys):
        from pge.shared.exceptions import ConfigFileNotFoundError

        mocks['generator_instance'].load_yaml.side_effect = (
            ConfigFileNotFoundError('missing.yml'))

        assert _esegui(mocks, ['main.py', 'missing.yml', 'out.aif']) == 1
        captured = capsys.readouterr()
        assert ("[ERRORE] File di configurazione non trovato: 'missing.yml'"
                in captured.out)
        assert 'Traceback' not in captured.err

    def test_yaml_malformato_non_e_piu_un_traceback(self, mocks, capsys):
        """Il difetto vicino, chiuso nella stessa passata: prima di questa
        issue `yaml.YAMLError` non lo traduceva nessuno e l'utente riceveva
        messaggio piu' traceback dal ramo generico."""
        import yaml
        from pge.shared.exceptions import ConfigParseError

        mocks['generator_instance'].load_yaml.side_effect = (
            ConfigParseError('broken.yml', yaml.YAMLError('boom')))

        assert _esegui(mocks, ['main.py', 'broken.yml', 'out.aif']) == 1
        captured = capsys.readouterr()
        assert ("[ERRORE] File di configurazione malformato: 'broken.yml'"
                in captured.out)
        assert 'Traceback' not in captured.err

    def test_i_due_messaggi_passano_dall_handler_EngineError(
            self, mocks, capsys):
        """Cioe' portano la riga «Dettagli:» col path del log engine."""
        from pge.shared.exceptions import ConfigFileNotFoundError

        mocks['generator_instance'].load_yaml.side_effect = (
            ConfigFileNotFoundError('missing.yml'))

        _esegui(mocks, ['main.py', 'missing.yml', 'out.aif'])
        assert "  Dettagli:     /tmp/engine.log\n" in capsys.readouterr().out


    def test_yaml_illeggibile_non_e_piu_un_traceback(self, mocks, capsys):
        """Il quarto e il quinto modo, chiusi con gli altri tre.

        Una directory al posto del file (`pge configs/ out.wav`) e un file
        senza permessi di lettura sono `OSError` che non sono
        `FileNotFoundError`: erano gli ultimi del percorso di caricamento a
        uscire dal ramo generico come messaggio piu' traceback.
        """
        from pge.shared.exceptions import ConfigReadError

        mocks['generator_instance'].load_yaml.side_effect = ConfigReadError(
            'configs/', IsADirectoryError(21, 'Is a directory', 'configs/'))

        assert _esegui(mocks, ['main.py', 'configs/', 'out.aif']) == 1
        captured = capsys.readouterr()
        assert ("[ERRORE] File di configurazione non leggibile: 'configs/'"
                in captured.out)
        assert '  Dettaglio:    Is a directory' in captured.out
        assert 'Traceback' not in captured.err


def test_lo_stub_yaml_dei_mock_conosce_YAMLError(mocks):
    """`ConfigParseError` eredita `yaml.YAMLError` al momento della creazione.

    Non e' un dettaglio dei test: sotto la fixture `mocks` il modulo `yaml` e'
    uno stub, e uno stub senza quell'attributo non farebbe fallire un assert —
    farebbe fallire l'import di `pge.shared.exceptions`, con un
    `AttributeError` che non nomina la causa. Questa guardia lo dice a voce.
    """
    import yaml  # sotto la fixture: lo stub di tests/main_mocks.py
    from pge.shared.exceptions import ConfigParseError

    assert issubclass(ConfigParseError, yaml.YAMLError)


# ---------------------------------------------------------------------------
# Le guardie strutturali, misurate su sorgenti finti.
#
# Sabotare `cli.py` non e' un'opzione: e' il file che le guardie sorvegliano.
# Questi sorgenti sono l'unico modo di distinguere una guardia verde perche'
# il codice e' sano da una verde perche' non guarda -- che e' la stessa
# distinzione, un piano piu' su, che la #257 corregge nel codice.
# ---------------------------------------------------------------------------

SABOTAGGIO_EXCEPT_NUDO = """
def main():
    try:
        generator.load_yaml()
        try:
            api.render(generator)
        except:
            print("Errore: file non trovato")
            sys.exit(1)
    except EngineError:
        pass
    except Exception:
        pass
"""

SABOTAGGIO_NEL_FINALLY = """
def main():
    try:
        generator.load_yaml()
    except EngineError:
        pass
    except Exception:
        pass
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
"""

CODICE_SANO = """
def main():
    try:
        page = int(sys.argv[i + 1])
    except ValueError:
        sys.exit(1)
    try:
        generator.load_yaml()
    except EngineError as err:
        sys.exit(1)
    except Exception:
        sys.exit(1)
"""


class TestLaGuardiaMisurata:
    """Le tre forme su cui una lettura ingenua tacerebbe."""

    def test_vede_l_except_nudo_annidato(self):
        """Non nomina nessun builtin: una guardia sui soli nomi lo
        lascerebbe passare, restando verde sull'handler piu' largo che
        esista — che cattura la famiglia OSError e anche `EngineError`."""
        albero = _albero(SABOTAGGIO_EXCEPT_NUDO)
        blocchi = _try_del_caricamento(albero)
        assert blocchi, "il sorgente finto non e' piu' quello che descrive"
        assert any(_colpevole(h) is not None
                   for b in blocchi for h in _handler_annidati(b))
        assert any(_colpevole(h, famiglia=OSError) is not None
                   for h in ast.walk(albero)
                   if isinstance(h, ast.ExceptHandler))

    def test_vede_l_handler_nel_finally(self):
        """«A nessuna profondita'» comprende `finally:` e `else:`: leggere il
        solo `body` lascerebbe la guardia piu' stretta di come e' scritta."""
        albero = _albero(SABOTAGGIO_NEL_FINALLY)
        blocchi = _try_del_caricamento(albero)
        assert blocchi, "il sorgente finto non e' piu' quello che descrive"
        assert any(_colpevole(h) == 'FileNotFoundError'
                   for b in blocchi for h in _handler_annidati(b))

    def test_lascia_stare_gli_handler_legittimi(self):
        """L'altra meta': una guardia che accusa il codice sano chiede di
        riscriverlo, e viene spenta. `except ValueError` attorno a un `int()`
        su `sys.argv` sta fuori dal blocco e non e' della famiglia OSError —
        e i due rami del blocco sono builtin per costruzione, quindi non
        passano da `_handler_annidati`.
        """
        albero = _albero(CODICE_SANO)
        blocchi = _try_del_caricamento(albero)
        assert blocchi, "il sorgente finto non e' piu' quello che descrive"
        assert not [h for b in blocchi for h in _handler_annidati(b)
                    if _colpevole(h) is not None]
        assert not [h for h in ast.walk(albero)
                    if isinstance(h, ast.ExceptHandler)
                    and _colpevole(h, famiglia=OSError) is not None]
        nomi = [n for b in blocchi for h in b.handlers
                for n in _nomi_catturati(h)]
        assert nomi == HANDLER_ATTESI
