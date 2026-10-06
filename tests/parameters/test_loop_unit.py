# =============================================================================
# tests/parameters/test_loop_unit.py
# =============================================================================
"""
Il vocabolario di `pointer.loop_unit` come modulo a se', e perche' (#246).

Sono due tuple: le grafie ammesse (#222) e le chiavi del blocco `pointer` che
l'unita' interpreta. Stavano in `controllers/pointer_controller.py`, che oggi
si importa senza terze parti ma per caso: `Envelope`, l'orchestratore e
`StreamConfig` usano la sola stdlib, e nessuna guardia lo pretende. Qui il
modulo non importa niente, e `_MODULI_SENZA_TERZE_PARTI` lo misura.

Chi le legge da fuori lo fa dal **sorgente**, con `ast`, al path:

- **PGE-ui** legge `LOOP_UNITS` per dire «questa grafia il motore la rifiuta»
  mentre si scrive, invece di scoprirlo da un render che muore. Il suo bridge
  non importa mai il motore -- e' un processo Flask nel venv dell'editor -- e
  la sua parita' confronta proprio quella lettura, non un import.
- **PGE-ls** rilegge tutte e due le tuple nei patti di parita' del suo mirror
  statico (`granular_ls/loop_unit.py`); **gl-ls** ne tiene un altro
  (`diagnostics._UNIT_SCALED`), che e' prosa: non si accorge di essere stato
  contraddetto.

Il path e la forma letterale sono percio' il contratto, e una lettura dal path
vecchio su un motore nuovo non fallisce: dice «il motore precede #222», cioe'
verde. I ripieghi sul vecchio path, a valle, restano per i motori piu' vecchi.

`LOOP_UNIT_SCOPE` perde l'underscore: due repository lo mirrorano, quindi era
privato solo di nome. Dichiararlo e' meno costoso che lasciare che qualcuno lo
rinomini credendo che non lo guardi nessuno, che e' esattamente il caso che la
#246 ha registrato.
"""

import ast

import pytest

from pge.parameters.loop_unit import LOOP_UNITS, LOOP_UNIT_SCOPE


class TestVocabolario:

    def test_le_grafie_sono_quelle_della_222(self):
        assert LOOP_UNITS == ('seconds', 'absolute', 'normalized')

    def test_la_prima_grafia_e_quella_canonica(self):
        """L'ordine e' significativo e PGE-ui lo pretende: il selettore
        dell'Inspector scrive la prima, e la parita' confronta le due liste
        *in ordine*. Una tupla, non un insieme."""
        assert isinstance(LOOP_UNITS, tuple)
        assert LOOP_UNITS[0] == 'seconds'

    def test_seconds_e_absolute_sono_la_stessa_lettura(self):
        """'absolute' e' l'alias storico, quello che i config e la reference
        hanno sempre scritto: valori gia' in secondi assoluti."""
        assert 'absolute' in LOOP_UNITS
        assert 'normalized' in LOOP_UNITS


class TestScope:

    def test_le_chiavi_sono_quelle_che_l_unita_interpreta(self):
        assert LOOP_UNIT_SCOPE == ('start', 'loop_start', 'loop_end', 'loop_dur')

    def test_start_e_dentro_benche_loop_non_lo_sia(self):
        """`start` e' una posizione nel sample come loop_start -- stesso
        dominio, stessa unita' (reference §10.1) -- e sopravvive al loop:
        togliere il loop non toglie l'unita'. Fuori da questo elenco un valore
        non viene riscalato, e il mirror di PGE-ui decide da qui se mostrare il
        selettore dell'unita'."""
        assert 'start' in LOOP_UNIT_SCOPE
        assert 'loop' not in LOOP_UNIT_SCOPE


class TestUnSoloPosto:
    """Le due tuple stanno qui e non anche in `pointer_controller`."""

    def _sorgente_controller(self):
        import pge.controllers.pointer_controller as pc
        with open(pc.__file__, encoding='utf-8') as fh:
            return fh.read()

    @pytest.mark.parametrize('nome', ['LOOP_UNITS', 'LOOP_UNIT_SCOPE',
                                      '_LOOP_UNIT_SCOPE'])
    def test_il_controller_non_le_ridichiara(self, nome):
        albero = ast.parse(self._sorgente_controller())
        dichiarati = [
            n for n in ast.walk(albero)
            if isinstance(n, ast.Assign)
            and any(getattr(t, 'id', None) == nome for t in n.targets)]
        assert not dichiarati, (
            f"pointer_controller.py ridichiara {nome}: il vocabolario di "
            f"loop_unit sta in pge/parameters/loop_unit.py (issue #246), e una "
            f"seconda dichiarazione e' quella che i lettori a valle "
            f"troverebbero per prima")

    def test_il_controller_le_importa_e_le_usa(self):
        """Una guardia che chiedesse la sola assenza resterebbe verde su un
        controller che ha smesso di validare l'unita'."""
        sorgente = self._sorgente_controller()
        assert 'from pge.parameters.loop_unit import' in sorgente
        assert 'LOOP_UNITS' in sorgente
        assert 'LOOP_UNIT_SCOPE' in sorgente


class TestModuloLeggero:
    """Niente import fuori dalla stdlib.

    Misurata in un interprete figlio con le dipendenze bloccate dentro
    `tests/shared/test_engine_exceptions.py` (`_MODULI_SENZA_TERZE_PARTI`): qui
    si guarda il sorgente, che e' la diagnosi."""

    def test_non_importa_niente(self):
        from pge.parameters import loop_unit
        with open(loop_unit.__file__, encoding='utf-8') as fh:
            albero = ast.parse(fh.read())
        radici = set()
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Import):
                radici.update(a.name.split('.')[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                radici.add(nodo.module.split('.')[0])
        assert radici <= {'__future__'}, (
            f"loop_unit.py importa {sorted(radici - {'__future__'})}: il modulo "
            f"esiste per essere importabile senza il venv del motore (#246)")

    def test_le_due_tuple_sono_letterali(self):
        """Non calcolate: il bridge di PGE-ui e i patti di PGE-ls non
        importano il motore, le leggono dall'AST, e la loro risoluzione dei
        nomi va al piu' di un livello e dentro lo stesso file. Un valore
        costruito da un'espressione gli torna come «non lo so» -- e un «non lo
        so» letto come un valore e' il modo in cui un controllo si spegne in
        silenzio."""
        from pge.parameters import loop_unit
        with open(loop_unit.__file__, encoding='utf-8') as fh:
            albero = ast.parse(fh.read())
        trovate = {}
        for nodo in albero.body:
            if isinstance(nodo, (ast.Assign, ast.AnnAssign)):
                bersagli = (nodo.targets if isinstance(nodo, ast.Assign)
                            else [nodo.target])
                for t in bersagli:
                    if getattr(t, 'id', None) in ('LOOP_UNITS', 'LOOP_UNIT_SCOPE'):
                        trovate[t.id] = nodo.value
        assert set(trovate) == {'LOOP_UNITS', 'LOOP_UNIT_SCOPE'}
        for nome, valore in trovate.items():
            assert ast.literal_eval(valore), (
                f"{nome} non e' un letterale: l'AST di chi legge da fuori non "
                f"saprebbe dire quale sia il vocabolario")
