# tests/export/test_depfile_writer.py
"""
La depfile di make (issue #290): il render dipende dal master e da ogni file
che il master importa con `file:`.

Con `make all STEMS=false` la regola `$(SFDIR)/%.aif: $(YMLDIR)/%.yml` vede
solo il master: modificare soltanto un file importato lasciava l'audio di
prima, con un «nothing to be done». La depfile e' la soluzione di gcc
(`-MD -MP`): il motore, che sa quali file ha letto, li scrive in un frammento
di Makefile che il Makefile include.

Il testo si verifica due volte: per forma, e facendolo leggere a un make vero
(`make -q`), perche' l'escaping e' la parte che si sbaglia in silenzio -- un
path con uno spazio diventa due prerequisiti, nessuno dei quali esiste.
"""
import os
import shutil
import subprocess

import pytest

from pge.export.depfile_writer import make_depfile, write_depfile


# =============================================================================
# La forma
# =============================================================================

def test_il_target_dipende_dal_master_e_dai_file_importati():
    testo = make_depfile('output/brano.aif', [
        'configs/brano.yml', 'configs/streams/risacca.yml'])

    righe = [r for r in testo.splitlines() if r and not r.startswith('#')]
    assert righe[0] == ('output/brano.aif: configs/brano.yml '
                        'configs/streams/risacca.yml')


def test_ogni_file_importato_ha_una_regola_vuota():
    """La `-MP` di gcc: un file importato che sparisce non ferma make con
    «No rule to make target», ma rifa' il render -- che e' il posto dove
    il file mancante ha il suo messaggio (`ConfigFileNotFoundError`)."""
    testo = make_depfile('out.aif', ['m.yml', 'a.yml', 'b.yml'])

    righe = [r for r in testo.splitlines() if r and not r.startswith('#')]
    assert righe[1:] == ['a.yml:', 'b.yml:']


def test_il_master_non_ha_la_regola_vuota():
    """Il master e' il prerequisito della regola a pattern: se sparisce,
    l'errore giusto e' quello di make, non un render rifatto."""
    testo = make_depfile('out.aif', ['m.yml'])

    righe = [r for r in testo.splitlines() if r and not r.startswith('#')]
    assert righe == ['out.aif: m.yml']


def test_un_file_importato_due_volte_compare_una_volta():
    testo = make_depfile('out.aif', ['m.yml', 'a.yml', 'b.yml', 'a.yml'])

    righe = [r for r in testo.splitlines() if r and not r.startswith('#')]
    assert righe == ['out.aif: m.yml a.yml b.yml', 'a.yml:', 'b.yml:']


@pytest.mark.parametrize('path, atteso', [
    ('streams/nuovo stream.yml', r'streams/nuovo\ stream.yml'),
    ('streams/a#b.yml', r'streams/a\#b.yml'),
    ('streams/c$d.yml', 'streams/c$$d.yml'),
    # `%` e' letterale fra i prerequisiti: e' nel *target* che fa di una
    # regola una regola a pattern (vedi sotto).
    ('streams/e%f.yml', 'streams/e%f.yml'),
    # I tre che make separa o interpreta come lo spazio, e che sono legali in
    # un nome di file POSIX: nudi, la depfile non si legge affatto (`:` da'
    # «multiple target patterns», `|` manda make a cercare `streams/g`).
    ('streams/g:h.yml', r'streams/g\:h.yml'),
    ('streams/i|j.yml', r'streams/i\|j.yml'),
    ('streams/k\tl.yml', 'streams/k\\\tl.yml'),
    # Fra i prerequisiti `=` e' letterale: make legge l'intera riga come un
    # assegnamento solo quando sta in testa (vedi sotto).
    ('streams/m=n.yml', 'streams/m=n.yml'),
    # Il backslash e' letterale dove make non lo legge, cioe' davanti a ogni
    # carattere che non scappa...
    ('streams/a\\b.yml', 'streams/a\\b.yml'),
    # ...e davanti a uno che scappa vale la regola di make: un carattere
    # dietro 2N+1 backslash e' N backslash e il carattere letterale. Senza
    # raddoppiarli, il backslash del nome scappa quello della depfile, e il
    # carattere torna nudo (`q\\#` apre un commento, `s\\:` separa).
    ('streams/o\\ p.yml', 'streams/o\\\\\\ p.yml'),
    ('streams/q\\#r.yml', 'streams/q\\\\\\#r.yml'),
    ('streams/s\\:t.yml', 'streams/s\\\\\\:t.yml'),
    ('streams/u\\\\:v.yml', 'streams/u\\\\\\\\\\:v.yml'),
], ids=['spazio', 'cancelletto', 'dollaro', 'percento', 'due_punti', 'pipe',
        'tab', 'uguale', 'backslash', 'backslash_spazio',
        'backslash_cancelletto', 'backslash_due_punti',
        'due_backslash_due_punti'])
def test_escaping_dei_prerequisiti(path, atteso):
    testo = make_depfile('out.aif', ['m.yml', path])

    righe = [r for r in testo.splitlines() if r and not r.startswith('#')]
    assert righe[0] == f'out.aif: m.yml {atteso}'


def test_il_percento_si_scappa_solo_dove_e_un_target():
    """`a%b.yml:` sarebbe una regola a pattern, e un file importato che
    sparisce fermerebbe make. `\\%` fra i prerequisiti invece resta
    letterale, backslash compreso: lo stesso carattere vuole due grafie."""
    testo = make_depfile('out/p%q.aif', ['m.yml', 'e%f.yml'])

    righe = [r for r in testo.splitlines() if r and not r.startswith('#')]
    assert righe == [r'out/p\%q.aif: m.yml e%f.yml', r'e\%f.yml:']


def test_un_backslash_davanti_al_percento_del_target_si_raddoppia():
    """Il `%` di un target si scappa, quindi un backslash del nome davanti
    a lui va raddoppiato come davanti agli altri: `\\\\\\%` e' un backslash e
    un `%` letterale, mentre `\\\\%` farebbe di nuovo una regola a pattern."""
    testo = make_depfile('out/p\\%q.aif', ['m.yml', 'e\\%f.yml'])

    righe = [r for r in testo.splitlines() if r and not r.startswith('#')]
    assert righe == ['out/p\\\\\\%q.aif: m.yml e\\%f.yml',
                     'e\\\\\\%f.yml:']


def test_un_path_con_un_a_capo_non_si_puo_scrivere():
    """Make non ha una grafia per l'a capo, e la depfile e' inclusa da ogni
    `make`: una riga spezzata li fermerebbe tutti, non solo questo render."""
    with pytest.raises(ValueError, match='a capo'):
        make_depfile('out.aif', ['m.yml', 'stra\nno.yml'])


@pytest.mark.parametrize('prerequisiti', [
    ['stra;no.yml'],
    ['m.yml', 'stra;no.yml'],
], ids=['master', 'importato'])
def test_un_punto_e_virgola_non_si_puo_scrivere(prerequisiti):
    """Il `;` apre la ricetta, e il backslash non lo salva: fra i
    prerequisiti make cerca una regola per la meta' sinistra del nome, in
    testa a una riga da' «missing separator». Stessa ragione dell'a capo:
    fermerebbe ogni `make` dopo, non questo render."""
    with pytest.raises(ValueError, match='punto e virgola'):
        make_depfile('out.aif', prerequisiti)


@pytest.mark.parametrize('prerequisiti', [
    ['stra\\'],
    ['m.yml', 'stra\\'],
    ['m.yml', 'stra\\', 'c.yml'],
], ids=['master', 'importato_in_fondo', 'importato_in_mezzo'])
def test_un_backslash_in_fondo_al_nome_non_si_puo_scrivere(prerequisiti):
    """In fondo a una riga il backslash e' la continuazione: make attacca
    la riga dopo, e la depfile nomina un file che non c'e' (misurato: «No
    rule to make target»). Raddoppiato non si salva, perche' make dimezza i
    backslash solo davanti a un carattere che legge, e il fine riga non lo
    e': `stra\\\\` resta due backslash. Il file puo' finire in fondo alla riga
    in ogni posizione -- l'ultimo prerequisito -- quindi si rifiuta in ogni
    posizione, come il `;`."""
    with pytest.raises(ValueError, match='backslash in fondo'):
        make_depfile('out.aif', prerequisiti)


@pytest.mark.parametrize('target, atteso', [
    ('out/a=b.aif', 'uguale'),
    ('out/a|b.aif', 'barra verticale'),
    ('out/a\tb.aif', 'tab'),
], ids=['uguale', 'pipe', 'tab'])
def test_un_target_che_make_non_registra_non_si_puo_scrivere(target, atteso):
    """La prima riga *e'* la depfile: se make non ne registra il target, la
    dipendenza non esiste, e in silenzio.

    `=` glielo impedisce leggendo l'intera riga come un assegnamento di
    variabile (`out/a = b.aif: m.yml`); `|` e il tab, pur col backslash,
    valgono fra i prerequisiti ma non in testa a una riga.
    """
    with pytest.raises(ValueError, match=atteso):
        make_depfile(target, ['m.yml'])


@pytest.mark.parametrize('nome', ['a=b.yml', 'a|b.yml', 'a\tb.yml'],
                         ids=['uguale', 'pipe', 'tab'])
def test_un_file_cosi_costa_la_sua_regola_vuota_non_la_depfile(nome):
    """La `-MP` e' un'aggiunta, la prima riga e' la dipendenza.

    Fra i prerequisiti quei tre caratteri si scrivono, quindi la dipendenza
    c'e'; la regola vuota no, e si omette invece di far fallire tutta la
    depfile. Il prezzo e' quello che la `-MP` evita: se quel file sparisce,
    make si ferma invece di rifare il render.
    """
    testo = make_depfile('out.aif', ['m.yml', nome, 'c.yml'])

    righe = [r for r in testo.splitlines() if r and not r.startswith('#')]
    assert righe[1:] == ['c.yml:'], "la regola vuota di 'nome' non si scrive"
    assert righe[0].startswith('out.aif: m.yml '), righe[0]
    assert righe[0].endswith(' c.yml'), righe[0]


# =============================================================================
# Make la legge come la scriviamo
# =============================================================================

_MAKEFILE = """\
out/%.aif: src/%.yml
\t@mkdir -p out; touch $@
-include dep.d
"""


@pytest.fixture
def progetto(tmp_path):
    """Un mini-progetto make: `out/m.aif` da `src/m.yml`, piu' `dep.d`."""
    if shutil.which('make') is None:
        pytest.skip('make non disponibile')
    (tmp_path / 'src').mkdir()
    (tmp_path / 'Makefile').write_text(_MAKEFILE, encoding='utf-8')

    def scrivi(nome):
        path = tmp_path / 'src' / nome
        path.write_text('x', encoding='utf-8')
        return path

    def make_q():
        """`make -q`: 0 se aggiornato, 1 se va rifatto, 2 se make si ferma."""
        return subprocess.run(['make', '-q', 'out/m.aif'], cwd=tmp_path,
                              capture_output=True, text=True).returncode

    def build():
        subprocess.run(['make', 'out/m.aif'], cwd=tmp_path, check=True,
                       capture_output=True, text=True)
        return tmp_path / 'out' / 'm.aif'

    class Progetto:
        root = tmp_path
    p = Progetto()
    p.scrivi, p.make_q, p.build = scrivi, make_q, build
    return p


def _nel_futuro(path, rispetto_a):
    t = os.path.getmtime(rispetto_a) + 10
    os.utime(path, (t, t))


@pytest.mark.parametrize('nome', [
    'risacca.yml', 'nuovo stream.yml', 'a#b.yml', 'c$d.yml', 'e%f.yml',
    'g:h.yml', 'i|j.yml', 'k\tl.yml', 'm=n.yml', 'a\\b.yml', 'o\\ p.yml',
    'q\\#r.yml', 's\\:t.yml', 'u\\\\:v.yml', 'w\\|x.yml'])
def test_make_rifa_il_target_quando_cambia_un_file_importato(progetto, nome):
    progetto.scrivi('m.yml')
    importato = progetto.scrivi(nome)
    write_depfile(str(progetto.root / 'dep.d'), 'out/m.aif',
                  ['src/m.yml', f'src/{nome}'])
    aif = progetto.build()

    assert progetto.make_q() == 0, "appena costruito, make lo rifarebbe"

    _nel_futuro(importato, aif)

    assert progetto.make_q() == 1, (
        f"make non vede il file importato '{nome}': l'escaping non e' "
        f"quello che make legge")


@pytest.mark.parametrize('nome', ['risacca.yml', 'nuovo stream.yml',
                                  'e%f.yml', 'g:h.yml', 'o\\ p.yml',
                                  'q\\#r.yml', 's\\:t.yml', 'y\\%z.yml'])
def test_un_file_importato_sparito_non_ferma_make(progetto, nome):
    progetto.scrivi('m.yml')
    importato = progetto.scrivi(nome)
    write_depfile(str(progetto.root / 'dep.d'), 'out/m.aif',
                  ['src/m.yml', f'src/{nome}'])
    progetto.build()

    importato.unlink()

    assert progetto.make_q() == 1, (
        "un file importato sparito deve rifare il render (2 = make si e' "
        "fermato con «No rule to make target»)")


# =============================================================================
# La scrittura
# =============================================================================

def test_la_scrittura_crea_la_cartella(tmp_path):
    path = tmp_path / 'generated' / 'brano.aif.d'

    write_depfile(str(path), 'out.aif', ['m.yml'])

    assert path.read_text(encoding='utf-8') == make_depfile(
        'out.aif', ['m.yml'])


def test_la_scrittura_non_lascia_file_temporanei(tmp_path):
    """La depfile e' inclusa da ogni `make`: si sostituisce con
    `os.replace`, mai si scrive a meta' sul posto."""
    path = tmp_path / 'brano.aif.d'
    path.write_text('vecchia', encoding='utf-8')

    write_depfile(str(path), 'out.aif', ['m.yml', 'a.yml'])

    assert sorted(p.name for p in tmp_path.iterdir()) == ['brano.aif.d']
    assert 'vecchia' not in path.read_text(encoding='utf-8')
