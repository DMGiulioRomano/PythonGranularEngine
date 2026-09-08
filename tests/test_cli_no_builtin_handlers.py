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

## Le due guardie

- **Strutturale**: nessun `try` che avvolge il caricamento dello YAML cattura un
  tipo builtin — restano `EngineError` e il ramo generico, in quest'ordine.
  Questa e' la garanzia *per tipo*.
- **Comportamentale**: un `FileNotFoundError` sollevato **dentro** quel blocco
  ma per un file che non e' lo YAML non fa dire all'utente che manca la sua
  configurazione. E' il test che sabota la premessa invece di riasserirla:
  prima della #257 sarebbe stato rosso, e nessuno se ne sarebbe accorto.
"""

import ast
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


def _main_di_cli():
    with open(CLI_PATH, encoding='utf-8') as fh:
        albero = ast.parse(fh.read(), filename=CLI_PATH)
    return next(n for n in albero.body
                if isinstance(n, ast.FunctionDef) and n.name == 'main')


def _contiene_load_yaml(nodo):
    """Il nodo contiene, a qualunque profondita', una chiamata a load_yaml()?"""
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == 'load_yaml'
        for n in ast.walk(nodo)
    )


def _try_del_caricamento():
    """Ogni `try` di `main()` che avvolge il caricamento dello YAML.

    Plurale di proposito: un `try` annidato attorno alle sole due righe del
    caricamento e' esattamente la forma che la #257 sostituisce, quindi la
    guardia deve vederlo e non solo quello piu' esterno.
    """
    return [n for n in ast.walk(_main_di_cli())
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
        import builtins

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
