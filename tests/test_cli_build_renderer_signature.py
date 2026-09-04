"""L'adapter CLI -> API deve rifiutare i nomi che non conosce (issue #252).

`_build_renderer(tipo, generator, **kwargs)` raccoglieva tutto in `**kwargs` e
poi pescava una chiave per volta con `.get()`: un nome fuori elenco non era un
`TypeError`, non era un warning, era un no-op perfetto. E' cosi' che e' nata la
#243 — `utils/bench_cost.py` passava `ssdir=<tmpdir>` a un build `numpy`, dove
`ssdir` viene letto solo nel ramo Csound, e il `SampleRegistry` ricadeva sul
default storico `./refs/` senza che niente nominasse la causa.

Questi test fissano il contratto della firma esplicita: l'elenco dei kwargs e'
finito e noto, quindi lo verifica Python. Piu' due guardie che il resto della
correzione non si sfaldi: i default storici non si sono mossi, e il sito di
chiamata dentro `main()` non puo' divergere dalla firma senza che qualcosa lo
dica (con `**kwargs` divergeva in silenzio, che e' esattamente il difetto).
"""

import ast
import inspect
import os

import pytest
from unittest.mock import Mock, patch

from pge import api
from pge.cli import _build_renderer


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_PATH = os.path.join(REPO_ROOT, 'src', 'pge', 'cli.py')


@pytest.fixture
def gen():
    """Generator finto: `_build_renderer` non lo tocca, lo inoltra e basta."""
    return Mock(name='generator')


@pytest.fixture
def costruito():
    """Cattura la chiamata ad `api.build_renderer` senza costruire nulla."""
    with patch.object(api, 'build_renderer') as build:
        yield build


class TestKwargSconosciuto:
    """Il test chiesto dalla issue: oggi passa, e non dovrebbe.

    Tutti e tre montano `costruito`: senza, un `Mock` al posto del generator
    fa sollevare `TypeError` al renderer vero, e il test passerebbe per la
    ragione sbagliata anche con `**kwargs` intatto. Con l'API sostituita
    l'unico `TypeError` possibile e' quello della firma.
    """

    def test_nome_inventato_e_typeerror(self, gen, costruito):
        with pytest.raises(TypeError):
            _build_renderer('numpy', gen, kwarg_inesistente=1)

    def test_il_refuso_di_samples_dir_e_typeerror(self, gen, costruito):
        """La forma concreta della svista: un nome plausibile e sbagliato."""
        with pytest.raises(TypeError):
            _build_renderer('numpy', gen, sample_dir='/tmp/x')

    def test_gli_argomenti_sono_keyword_only(self, gen, costruito):
        """Nessun terzo posizionale: la lettura del sito di chiamata non
        deve dipendere dall'ordine."""
        with pytest.raises(TypeError):
            _build_renderer('numpy', gen, 48000)


class TestFirmaEsplicita:
    """La firma e' l'elenco, non un commento nel docstring."""

    def test_niente_var_keyword(self):
        params = inspect.signature(_build_renderer).parameters.values()
        var_kw = [p.name for p in params
                  if p.kind is inspect.Parameter.VAR_KEYWORD]
        assert var_kw == [], (
            f"_build_renderer ha ancora **{var_kw[0]}: i nomi fuori elenco "
            "tornano a essere no-op silenziosi")

    def test_il_sito_di_chiamata_non_diverge_dalla_firma(self):
        """Guardia strutturale sul sorgente, non sull'esecuzione di main().

        Con `**kwargs` un flag nuovo passato da `main()` e mai letto dentro
        `_build_renderer` era invisibile: nessun errore, nessun test rosso.
        Qui i due elenchi vengono confrontati direttamente.
        """
        with open(CLI_PATH, encoding='utf-8') as fh:
            tree = ast.parse(fh.read(), filename=CLI_PATH)

        chiamate = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == '_build_renderer'
        ]
        assert chiamate, "nessuna chiamata a _build_renderer in cli.py"

        firma = set(inspect.signature(_build_renderer).parameters)
        for chiamata in chiamate:
            passati = {kw.arg for kw in chiamata.keywords if kw.arg}
            assert passati <= firma, (
                "main() passa a _build_renderer nomi che la firma non "
                f"dichiara: {sorted(passati - firma)}")


class TestDefaultInvariati:
    """La firma esplicita non deve spostare nessun default storico."""

    def test_chiamata_nuda(self, gen, costruito):
        from pge.shared.constants import DEFAULT_OUTPUT_SR
        from pge.rendering.audio_format import DEFAULT_FORMAT

        _build_renderer('numpy', gen)

        _, kwargs = costruito.call_args
        assert kwargs['output_sr'] == DEFAULT_OUTPUT_SR
        assert kwargs['jobs'] == 'auto'
        assert kwargs['audio_format'] is DEFAULT_FORMAT
        assert kwargs['samples_dir'] is None
        assert kwargs['cache_manifest_path'] is None
        assert kwargs['csound'] is None
        assert kwargs['supercollider'] is None

    def test_opzioni_csound(self, gen, costruito):
        _build_renderer('csound', gen, ssdir='/s', sfdir='/f', sco_dir='/sco')

        opts = costruito.call_args.kwargs['csound']
        assert (opts.ssdir, opts.sfdir, opts.sco_dir) == ('/s', '/f', '/sco')
        # I default storici del ramo restano dove stavano
        assert opts.orc_path == 'csound/main.orc'
        assert opts.incdir == 'src'
        assert opts.log_dir == 'logs'
        assert opts.message_level == 134

    def test_opzioni_supercollider(self, gen, costruito):
        _build_renderer('supercollider', gen,
                        sc_synthdef_source='/a.scd', sc_block_size=64,
                        osc_dir='/osc')

        opts = costruito.call_args.kwargs['supercollider']
        assert opts.synthdef_source == '/a.scd'
        assert opts.block_size == 64
        assert opts.osc_dir == '/osc'
        # Nessun default ricopiato dalla CLI: decide il renderer
        assert opts.synthdef_dir is None
        assert opts.max_nodes is None

    def test_manifest_della_cache(self, gen, costruito, capsys):
        _build_renderer('numpy', gen, use_cache=True, yaml_basename='brano',
                        cache_dir='cache')

        atteso = os.path.join('cache', 'brano.json')
        assert costruito.call_args.kwargs['cache_manifest_path'] == atteso
        assert f"[CACHE] Manifest: {atteso}" in capsys.readouterr().out


class TestCacheSenzaBasename:
    """`use_cache` senza `yaml_basename` era un KeyError nudo."""

    def test_dice_cosa_manca(self, gen, costruito):
        with pytest.raises(ValueError) as errore:
            _build_renderer('numpy', gen, use_cache=True)
        assert 'yaml_basename' in str(errore.value)
