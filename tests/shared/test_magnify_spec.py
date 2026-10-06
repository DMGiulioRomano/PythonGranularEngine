# =============================================================================
# tests/shared/test_magnify_spec.py
# =============================================================================
"""
La grammatica di `--magnify-at` come modulo a se', e perche' (issue #246).

La grammatica sono tre insiemi di chiavi e una funzione che non dipendono da
niente: ne' numpy, ne' soundfile, ne' matplotlib, ne' da un'altra riga del
motore. Stavano in `pge/cli.py` solo per storia, e li' nessuno le poteva
importare: `import pge.cli` tira dentro `ScoreVisualizer` (matplotlib) e
`Generator` (numpy via `core.stream`).

Il prezzo lo pagava un altro repository. L'oracolo di parita' di PGE-ui
(`tests/parity/engine_oracle.py`) promette «l'oracolo importa dal motore, non
ne riscrive la logica», e il job node della sua CI fa il checkout del motore
ma non ne costruisce il venv. Per chiedere al motore come si parsa uno SPEC
doveva percio' aprire `cli.py`, cercarne i quattro nodi AST per nome,
compilarli ed eseguirli. Sono i byte del motore, quindi la risposta era vera;
ma la lettura pinnava **i nomi privati** e la loro posizione nel file, e una
rinomina qui (sono privati: per convenzione, roba nostra) rendeva rossa la CI
di la', su ogni pull request aperta, comprese quelle che non c'entravano.

Da qui il modulo. I nomi sono pubblici perche' qualcuno li legge davvero, e
stanno in un modulo che si importa con il python nudo di qualunque runner: la
deroga a quella promessa, su questa meta', non serve piu'.

**Il comportamento non e' cambiato di un byte, ed e' deliberato.** La funzione
stampa su stdout e chiama `sys.exit(1)` come faceva dentro la CLI — non alza.
Quei messaggi sono interfaccia (`CLASSIFICAZIONE` in
`tests/shared/test_stdout_contract.py`) e il mirror JS di PGE-ui
(`src/lib/magnify-spec.js`) promette di anticiparli mentre si scrive nel
popover, con la parita' che confronta le due risposte sullo stesso corpus.
Trasformarli in eccezioni e' una modifica alla superficie osservabile della
CLI, non uno spostamento: va chiesta, non fatta per strada.

Le prove di comportamento *attraverso la CLI* restano dove stavano
(`TestMagnifyAtValidationGolden` in `tests/test_cli_contract.py`), e sono la
rete che dice che lo spostamento non ha cambiato niente. Qui si misura la
funzione come la chiama chi la importa, che e' l'uso nuovo.
"""

import ast
import os

import pytest

from pge.shared.magnify_spec import (
    MAGNIFY_KEYS,
    MAGNIFY_NUMERIC_KEYS,
    MAGNIFY_STR_KEYS,
    parse_magnify_spec,
)


def _cli_source():
    import pge.cli as cli
    with open(cli.__file__, encoding='utf-8') as fh:
        return fh.read()


class TestVocabolario:

    def test_le_chiavi_numeriche_sono_quelle_documentate(self):
        assert MAGNIFY_NUMERIC_KEYS == frozenset({'t', 'y', 'zoom', 'out', 'src'})

    def test_le_chiavi_stringa_sono_quelle_documentate(self):
        assert MAGNIFY_STR_KEYS == frozenset({'stream'})

    def test_le_chiavi_ammesse_sono_l_unione_delle_due(self):
        """Non una terza lista scritta a mano: l'unione, come prima.

        Una copia qui potrebbe ammettere una chiave che poi nessun ramo sa
        convertire, cioe' un target con un valore di tipo sbagliato invece di
        un errore."""
        assert MAGNIFY_KEYS == MAGNIFY_NUMERIC_KEYS | MAGNIFY_STR_KEYS

    def test_le_due_meta_non_si_sovrappongono(self):
        assert not (MAGNIFY_NUMERIC_KEYS & MAGNIFY_STR_KEYS)


class TestParse:

    def test_un_target_minimo(self):
        assert parse_magnify_spec('t=14') == [{'t': 14.0}]

    def test_tutte_le_chiavi(self):
        assert parse_magnify_spec(
            't=14,y=0.5,zoom=10,out=3,src=2,stream=stream1') == [{
                't': 14.0, 'y': 0.5, 'zoom': 10.0,
                'out': 3.0, 'src': 2.0, 'stream': 'stream1'}]

    def test_i_target_si_separano_col_punto_e_virgola(self):
        assert parse_magnify_spec('t=1;t=2') == [{'t': 1.0}, {'t': 2.0}]

    def test_gli_spazi_intorno_ai_token_non_contano(self):
        assert parse_magnify_spec(' t = 1 , zoom = 2 ') == [
            {'t': 1.0, 'zoom': 2.0}]

    def test_le_numeriche_diventano_float(self):
        """`t=14` vale 14.0, non '14': il visualizer ci fa aritmetica."""
        target = parse_magnify_spec('t=14')[0]
        assert isinstance(target['t'], float)

    def test_la_chiave_stringa_resta_stringa(self):
        assert parse_magnify_spec('t=1,stream=2')[0]['stream'] == '2'


class TestRifiuti:
    """I cinque rifiuti, chiamando la funzione come la chiama chi la importa.

    Stesso messaggio e stesso exit code di prima dello spostamento: li'
    arrivano dalla CLI (`tests/test_cli_contract.py`), qui dalla funzione. Sono
    i messaggi che il mirror di PGE-ui promette di anticipare, quindi il testo
    e' il dato, non un dettaglio."""

    def _rifiuta(self, spec, capsys):
        with pytest.raises(SystemExit) as uscita:
            parse_magnify_spec(spec)
        assert uscita.value.code == 1
        return capsys.readouterr().out

    def test_token_senza_uguale(self, capsys):
        assert self._rifiuta('zoom', capsys) == (
            "--magnify-at: token non valido 'zoom'. "
            "Usa chiave=valore (es. t=14,zoom=10).\n")

    def test_chiave_ignota(self, capsys):
        assert self._rifiuta('t=5,foo=1', capsys) == (
            "--magnify-at: chiave ignota 'foo'. "
            "Valide: out, src, stream, t, y, zoom.\n")

    def test_valore_non_numerico(self, capsys):
        assert self._rifiuta('t=abc', capsys) == (
            "--magnify-at: valore non numerico per 't': 'abc'.\n")

    def test_t_mancante(self, capsys):
        assert self._rifiuta('zoom=10', capsys) == (
            "--magnify-at: ogni target richiede la chiave 't' "
            "(tempo in secondi).\n")

    def test_spec_vuoto(self, capsys):
        assert self._rifiuta('   ', capsys) == (
            "--magnify-at: nessun target valido nello SPEC.\n")


class TestUnSoloPosto:
    """La grammatica sta qui e non anche in `cli.py`.

    Lo spostamento serve a un repository che legge: se `cli.py` riaprisse una
    copia dei nomi, quella lettura tornerebbe a pinnare un simbolo privato di
    `cli.py` e lo spostamento non avrebbe comprato niente. La guardia e' sul
    sorgente perche' una copia *identica* non si vede dal comportamento."""

    @pytest.mark.parametrize('nome', [
        '_MAGNIFY_KEYS', '_MAGNIFY_NUMERIC_KEYS', '_MAGNIFY_STR_KEYS'])
    def test_cli_non_ridichiara_le_chiavi(self, nome):
        albero = ast.parse(_cli_source())
        dichiarati = [
            n for n in ast.walk(albero)
            if isinstance(n, ast.Assign)
            and any(getattr(t, 'id', None) == nome for t in n.targets)]
        assert not dichiarati, (
            f"cli.py ridichiara {nome}: la grammatica di --magnify-at sta in "
            f"pge/shared/magnify_spec.py, e un secondo posto e' esattamente "
            f"cio' che la issue #246 ha tolto")

    def test_cli_non_ridefinisce_il_parser(self):
        albero = ast.parse(_cli_source())
        definiti = [n.name for n in ast.walk(albero)
                    if isinstance(n, ast.FunctionDef)
                    and n.name in ('parse_magnify_spec', '_parse_magnify_spec')]
        assert not definiti, (
            "cli.py ridefinisce il parser di --magnify-at: la funzione sta in "
            "pge/shared/magnify_spec.py")

    def test_cli_lo_usa_importandolo(self):
        """E lo usa: una guardia che chiede solo l'assenza sarebbe verde anche
        su una CLI che ha smesso di leggere lo SPEC."""
        sorgente = _cli_source()
        assert 'from pge.shared.magnify_spec import' in sorgente
        assert 'parse_magnify_spec(' in sorgente


class TestModuloLeggero:
    """Niente import di terze parti, e nessun import del motore pesante.

    La proprieta' che rende il modulo importabile dal runner di PGE-ui e'
    misurata davvero in un interprete figlio con le dipendenze bloccate, dentro
    `test_engine_exceptions.py` (`_MODULI_SENZA_TERZE_PARTI`): qui si guarda il
    sorgente, che e' la diagnosi -- dice *quale* import e' comparso, mentre
    l'altra dice soltanto che non si importa piu'."""

    def test_non_importa_niente_fuori_dalla_stdlib(self):
        from pge.shared import magnify_spec
        with open(magnify_spec.__file__, encoding='utf-8') as fh:
            albero = ast.parse(fh.read())
        radici = set()
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Import):
                radici.update(a.name.split('.')[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                radici.add(nodo.module.split('.')[0])
        assert radici <= {'__future__', 'sys'}, (
            f"magnify_spec.py importa {sorted(radici - {'__future__', 'sys'})}: "
            f"il modulo esiste per essere importabile senza il venv del motore "
            f"(issue #246)")

    def test_sta_dove_l_oracolo_lo_cerca(self):
        """Il path e' parte del contratto: PGE-ui lo nomina.

        Un modulo spostato di cartella e' invisibile a un import che gli serve
        per nome, e il ripiego dell'oracolo e' l'ast-slice di `cli.py`, dove la
        grammatica non c'e' piu': diventerebbe un rosso che dice 'la grammatica
        si e' spostata' senza dire dove."""
        from pge.shared import magnify_spec
        atteso = os.path.join('pge', 'shared', 'magnify_spec.py')
        assert magnify_spec.__file__.endswith(atteso)
