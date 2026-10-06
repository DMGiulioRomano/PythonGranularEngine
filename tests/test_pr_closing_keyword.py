# =============================================================================
# tests/test_pr_closing_keyword.py
# =============================================================================
"""Il corpo di una PR dichiara l'issue che chiude, e la catena che lo pretende.

GitHub chiude un'issue al merge soltanto se un closing keyword inglese compare
nel **corpo** della pull request. La #219 e' rimasta aperta dopo il merge della
PR #293 perche' quel corpo diceva «Chiude #219»: una frase italiana che GitHub
non legge, su una PR per il resto impeccabile.

La catena che lo impedisce ha quattro anelli, e tre di essi sbagliano **in
silenzio** — e' per quelli che questa suite esiste, non per il regex.

1. `.github/scripts/check_closing_keyword.py` decide. I casi del `verdict`
   stanno qui sotto, e la regola che li governa e' **piu' stretti di GitHub,
   mai piu' larghi**: un rifiuto si vede e si corregge, un verde su una riga
   che GitHub non collega e' l'issue che resta aperta e nessuno guarda.
2. `.github/pull_request_template.md` mette la riga davanti agli occhi. Il suo
   esempio sta dentro un commento HTML, e se la potatura dei commenti cadesse
   il check sarebbe verde **per via del proprio esempio**, su ogni PR mai
   compilata. Percio' qui si pretende che il template, cosi' come e'
   versionato, *non* passi il check.
3. `.github/workflows/pr-closes-issue.yml` lo esegue. Due tipi di evento sono
   load-bearing e la loro assenza non e' un rosso: senza `edited` il check non
   torna mai verde dopo aver corretto il corpo, senza `synchronize` la head
   nuova di un push resta senza check e il merge aspetta per sempre un
   contesto che nessuno pubblichera'.
4. `.github/rulesets/main-closes-issue.json` lo pretende verde, per nome. Se
   il nome del job e il contesto richiesto divergono, il merge resta appeso a
   un contesto inesistente: un cancello che non si apre piu'.
"""
import ast
import importlib.util
import io
import json
import os
import re

import pytest

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RADICE, '.github', 'scripts', 'check_closing_keyword.py')
TEMPLATE = os.path.join(RADICE, '.github', 'pull_request_template.md')
WORKFLOW = os.path.join(RADICE, '.github', 'workflows', 'pr-closes-issue.yml')
RULESET = os.path.join(RADICE, '.github', 'rulesets', 'main-closes-issue.json')

#: Le nove parole chiave che GitHub documenta. Trascritte qui di proposito:
#: sono una proprieta' di GitHub, non del motore, quindi non c'e' un sorgente
#: da cui leggerle. Se il modulo ne perde una, un `Resolved #12` scritto in
#: buona fede smette di valere e il check lo rifiuta senza che niente dica
#: perche'.
KEYWORDS_DI_GITHUB = frozenset((
    'close', 'closes', 'closed',
    'fix', 'fixes', 'fixed',
    'resolve', 'resolves', 'resolved',
))


def _leggi(percorso):
    with io.open(percorso, encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def check():
    """Il modulo del check, importato dal suo percorso.

    `.github/scripts/` non e' un package e non sta su `sys.path`: importarlo
    per percorso e' l'unico modo, ed e' anche cio' che fa la CI (`python3
    .github/scripts/...`). Se il file non c'e' il test **falla** invece di
    skippare: uno skip qui vorrebbe dire «la catena non esiste» detto in verde.
    """
    assert os.path.isfile(SCRIPT), SCRIPT
    spec = importlib.util.spec_from_file_location('check_closing_keyword', SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# ---------------------------------------------------------------------------
# 1. Il verdetto
# ---------------------------------------------------------------------------

class TestVerdetto:

    @pytest.mark.parametrize('corpo, issues', [
        ('Closes #219', [219]),
        ('closes #219', [219]),
        ('CLOSES #219', [219]),
        ('Fixes #7', [7]),
        ('Resolved #7', [7]),
        ('Closes GH-77', [77]),
        ('Closes #1\nCloses #2', [1, 2]),
        ('Closes   #1', [1]),
        ('Testo prima. Closes #5. Testo dopo.', [5]),
        # Ogni issue vuole la sua parola chiave: la seconda non e' collegata
        # da GitHub, e il check non deve fingere che lo sia.
        ('Closes #1, #2', [1]),
        ('Closes #1 e fixes #2', [1, 2]),
        # Lo stesso numero due volte conta una volta.
        ('Closes #3\nFixes #3', [3]),
    ])
    def test_le_grafie_che_github_collega(self, check, corpo, issues):
        assert check.same_repo_issues(corpo) == issues
        assert check.verdict(corpo)[0] is True

    @pytest.mark.parametrize('corpo, perche', [
        ('', 'corpo vuoto'),
        ('Chiude #219, entrambi i punti.', 'il caso vero della #219: italiano'),
        ('Risolve #219', 'italiano'),
        ('Closes: #12', 'i due punti non sono fra le grafie documentate'),
        ('Closes#12', 'serve uno spazio'),
        ('Closes #abc', 'non e\' un numero'),
        ('Closes #', 'la riga del template non compilata'),
        ('prefixes #12', 'non e\' una parola chiave: e\' la coda di un\'altra'),
        ('un-fix #12', 'idem, col trattino'),
        ('Vedi #219', '«vedi» non chiude'),
        ('Refs #219', '«refs» non chiude'),
        ('#219', 'il numero da solo collega ma non chiude'),
    ])
    def test_le_grafie_che_non_chiudono(self, check, corpo, perche):
        assert check.same_repo_issues(corpo) == [], perche
        assert check.verdict(corpo)[0] is False, perche

    @pytest.mark.parametrize('corpo', [
        'Closes DMGiulioRomano/PGE-ui#162',
        'Fixes DMGiulioRomano/PGE-ls#67',
        'Closes https://github.com/DMGiulioRomano/gl-ls/issues/60',
    ])
    def test_un_issue_di_un_altro_repo_non_chiude(self, check, corpo):
        """`Closes owner/repo#n` e' un rimando, e il messaggio lo dice.

        Riconoscere queste due grafie serve a **rifiutarle col motivo giusto**:
        in un gruppo di repo che si citano a ogni PR, «manca la riga» manderebbe
        a cercare una riga che c'e'.
        """
        ok, messaggio = check.verdict(corpo)
        assert ok is False, corpo
        assert 'altro repo' in messaggio, corpo

    def test_un_url_di_repo_col_frammento_non_e_una_grafia(self, check):
        """`https://github.com/owner/repo#67` non e' l'URL di un'issue.

        E' l'URL del repo con un frammento, e GitHub non lo collega: nasce dal
        copiare uno slug (`owner/repo#67`) dentro un URL. Rifiutato col
        messaggio generico, che e' il vero: qui non c'e' nessuna chiusura, ne'
        di qui ne' di altrove.
        """
        ok, messaggio = check.verdict('Fixes https://github.com/DMGiulioRomano/PGE-ls#67')
        assert ok is False
        assert 'altro repo' not in messaggio

    def test_il_rimando_fuori_repo_non_annulla_la_chiusura_qui(self, check):
        """Con entrambi, la PR e' valida e il fuori-repo resta una nota."""
        ok, messaggio = check.verdict(
            'Closes #219\nCloses DMGiulioRomano/PGE-ui#193'
        )
        assert ok is True
        assert '#219' in messaggio
        assert 'DMGiulioRomano/PGE-ui#193' in messaggio
        assert 'non si chiudera' in messaggio

    @pytest.mark.parametrize('corpo', [
        '<!-- Closes #1, #2 -->',
        '<!--\n  Esempio:\n  Closes #123\n-->',
        '```\nCloses #9\n```',
        '~~~\nCloses #9\n~~~',
        'Vedi `Closes #9` per la grafia.',
    ])
    def test_cio_che_github_non_legge_non_conta(self, check, corpo):
        """Commenti HTML, recinti e codice in linea escono prima del confronto.

        E' l'anello che fa la differenza fra un check e un check verde per via
        del template.
        """
        assert check.same_repo_issues(corpo) == []
        assert check.verdict(corpo)[0] is False

    def test_il_corpo_di_soli_commenti_lo_dice(self, check):
        ok, messaggio = check.verdict('<!-- tutto qui -->')
        assert ok is False
        assert 'solo i commenti del template' in messaggio

    @pytest.mark.parametrize('corpo, motivo', [
        ('No issue: refuso nel README', 'refuso nel README'),
        ('Cosa cambia: niente.\nNo issue: tooling di CI', 'tooling di CI'),
        ('   No issue:   spazi   ', 'spazi'),
    ])
    def test_la_via_duscita_vuole_un_motivo(self, check, corpo, motivo):
        assert check.no_issue_reason(corpo) == motivo
        assert check.verdict(corpo)[0] is True

    @pytest.mark.parametrize('corpo', ['No issue:', 'No issue:   ', 'No issue'])
    def test_la_via_duscita_senza_motivo_non_vale(self, check, corpo):
        """Senza il motivo non si distingue una PR senza issue da una a cui
        la riga e' stata tolta."""
        assert check.no_issue_reason(corpo) == ''
        assert check.verdict(corpo)[0] is False

    def test_le_nove_parole_chiave_ci_sono_tutte(self, check):
        assert frozenset(k.lower() for k in check.KEYWORDS) == KEYWORDS_DI_GITHUB

    def test_il_messaggio_di_rifiuto_insegna_la_grafia(self, check):
        ok, messaggio = check.verdict('')
        assert ok is False
        # Chi legge il log della CI deve poter correggere senza aprire la doc.
        assert 'Closes #' in messaggio
        assert 'No issue:' in messaggio

    def test_main_ritorna_il_codice_di_uscita(self, check, monkeypatch, capsys):
        monkeypatch.setenv('PR_BODY', 'Closes #219')
        assert check.main([]) == 0
        monkeypatch.setenv('PR_BODY', 'Chiude #219')
        assert check.main([]) == 1
        monkeypatch.delenv('PR_BODY', raising=False)
        assert check.main([]) == 1, 'nessun corpo: rifiuta, non assolve'
        assert capsys.readouterr().out.strip()


# ---------------------------------------------------------------------------
# 2. Il template
# ---------------------------------------------------------------------------

class TestTemplate:

    def test_esiste_e_porta_la_riga_da_compilare(self):
        testo = _leggi(TEMPLATE)
        assert re.search(r'^Closes #\s*$', testo, re.MULTILINE), (
            "il template deve aprire con una riga `Closes #` da completare"
        )

    def test_il_template_versionato_non_passa_il_check(self, check):
        """Un template che passa il check e' un template inutile.

        Se il `Closes #` nudo o gli esempi dentro i commenti bastassero, una
        PR aperta e lasciata col template addosso sarebbe verde: e' il caso
        che questo meccanismo esiste per prendere.
        """
        ok, _ = check.verdict(_leggi(TEMPLATE))
        assert ok is False

    def test_dice_che_le_parole_chiave_sono_inglesi(self):
        testo = _leggi(TEMPLATE)
        assert 'closes' in testo.lower()
        assert 'Chiude' in testo, (
            "il template nomina il caso vero (un «Chiude #219» non chiude): "
            "e' la ragione per cui la riga esiste, e senza di essa la "
            "prescrizione sembra burocrazia"
        )


# ---------------------------------------------------------------------------
# 3. Il workflow
# ---------------------------------------------------------------------------

def _workflow():
    yaml = pytest.importorskip('yaml')
    dati = yaml.safe_load(_leggi(WORKFLOW))
    # In YAML 1.1 la chiave `on:` e' il booleano vero: PyYAML la legge come
    # `True`, non come la stringa 'on'. Leggerne una sola delle due e' il modo
    # piu' facile di scrivere una guardia che non guarda niente.
    trigger = dati.get('on', dati.get(True))
    assert trigger is not None, 'il workflow non dichiara nessun trigger'
    return dati, trigger


class TestWorkflow:

    def test_gira_sulle_pull_request_e_non_sui_push(self):
        _, trigger = _workflow()
        assert 'pull_request' in trigger
        assert 'push' not in trigger, (
            "su un push non c'e' nessun corpo di PR da leggere: il check "
            "sarebbe rosso su ogni commit"
        )

    @pytest.mark.parametrize('tipo, perche', [
        ('opened', 'la prima occasione'),
        ('edited', "senza, correggere il corpo non fa tornare verde il check"),
        ('synchronize', "senza, la head nuova resta senza check e il merge "
                        "aspetta un contesto che nessuno pubblica"),
        ('reopened', 'una PR riaperta'),
    ])
    def test_i_tipi_di_evento_load_bearing(self, tipo, perche):
        _, trigger = _workflow()
        assert tipo in trigger['pull_request']['types'], perche

    def test_il_contesto_e_il_nome_del_job(self):
        dati, _ = _workflow()
        job = dati['jobs']['closes-issue']
        assert job['name'] == 'closes-issue', (
            "il contesto che il ruleset pretende e' il nome visualizzato del "
            "job: se divergono, il merge resta appeso a un contesto che non "
            "esiste"
        )

    def test_il_corpo_passa_per_lambiente_non_per_la_shell(self):
        """Il corpo di una PR lo scrive chiunque: interpolato nel `run`, un
        backtick o un `$(...)` sarebbe eseguito sul runner."""
        dati, _ = _workflow()
        passi = dati['jobs']['closes-issue']['steps']
        esecuzioni = [p for p in passi if 'run' in p]
        assert esecuzioni, 'il job non esegue niente'
        for passo in esecuzioni:
            assert '${{' not in passo['run'], passo['run']
        env = {}
        for passo in esecuzioni:
            env.update(passo.get('env') or {})
        assert 'PR_BODY' in env
        assert 'pull_request.body' in env['PR_BODY']

    def test_esegue_lo_script_versionato(self):
        testo = _leggi(WORKFLOW)
        assert '.github/scripts/check_closing_keyword.py' in testo, (
            "il controllo sta in un file con i suoi test, non in una riga di "
            "workflow che nessuno esegue in locale"
        )


# ---------------------------------------------------------------------------
# 4. Il ruleset
# ---------------------------------------------------------------------------

class TestRuleset:

    def test_pretende_il_contesto_del_job(self):
        dati = json.loads(_leggi(RULESET))
        regole = [r for r in dati['rules']
                  if r['type'] == 'required_status_checks']
        assert len(regole) == 1
        contesti = [c['context']
                    for c in regole[0]['parameters']['required_status_checks']]
        assert contesti == ['closes-issue']

    def test_vale_sul_branch_di_default(self):
        dati = json.loads(_leggi(RULESET))
        assert dati['target'] == 'branch'
        assert dati['enforcement'] == 'active'
        assert '~DEFAULT_BRANCH' in dati['conditions']['ref_name']['include'], (
            "il closing keyword chiude solo al merge nel branch di default: "
            "un ruleset puntato su un altro ref non difenderebbe niente"
        )

    def test_il_json_e_una_copia_dichiarata_tale(self):
        """Il ruleset vive nelle impostazioni, non nel repo: se il README non
        lo dice, qualcuno modifichera' il JSON aspettandosi un effetto."""
        readme = _leggi(os.path.join(RADICE, '.github', 'rulesets', 'README.md'))
        assert 'copia' in readme.lower()
        assert 'Import a ruleset' in readme


# ---------------------------------------------------------------------------
# 5. La regola che Claude Code legge
# ---------------------------------------------------------------------------

def test_la_regola_e_raggiungibile_da_claude_md():
    """Una regola che il CLAUDE.md non importa e' una regola che nessuno legge.

    E' la meta' che fa il lavoro vero: il template e il check prendono
    l'errore, questa riga impedisce di commetterlo.
    """
    regola = os.path.join(RADICE, '.claude', 'rules', 'pr-closes-issue.md')
    assert os.path.isfile(regola)
    claude_md = _leggi(os.path.join(RADICE, 'CLAUDE.md'))
    assert '@.claude/rules/pr-closes-issue.md' in claude_md

    testo = _leggi(regola)
    for atteso in ('Closes #', 'Chiude #219', 'No issue:'):
        assert atteso in testo, atteso
