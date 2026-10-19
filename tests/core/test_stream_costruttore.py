"""
test_stream_costruttore.py

Il costruttore di `Stream` e' l'unico ingresso (issue #283).

I test costruivano `Stream` a meta', con `object.__new__(Stream)`, e la
produzione portava le cicatrici di quegli oggetti: `getattr` con un default su
attributi che `__init__` scrive sempre, un ripiego sulla clip strategy, una
ragione «raggiungibile da chi bypassa `__init__`» scritta accanto a un ramo. Da
qui i test passano dal costruttore — le factory costruiscono uno `Stream` vero
con `build_stream` e poi sostituiscono i collaboratori che vogliono isolare — e
questo file fissa i contratti che quel percorso rende visibili.

Organizzazione:
1. Il contesto si legge una volta
2. I riferimenti che assegna il Generator sono dichiarati
3. Nessun test costruisce uno Stream a meta'
"""

import ast
import os

import pytest

from pge.shared.exceptions import EngineRuntimeError


# =============================================================================
# 1. IL CONTESTO SI LEGGE UNA VOLTA
# =============================================================================

class TestIlContestoSiLeggeUnaVolta:
    """`Stream` costruisce lo `StreamContext` e ne legge i campi: non li
    ri-deriva dal dizionario con le stesse funzioni, e non rilegge l'header
    del sample per sapere quanto dura."""

    def test_una_sola_lettura_dell_header_del_sample(self, build_stream,
                                                     monkeypatch):
        import pge.core.stream as modulo
        letture = []
        vera = modulo.get_sample_duration

        def contata(sample, *args, **kwargs):
            letture.append(sample)
            return vera(sample, *args, **kwargs)

        monkeypatch.setattr(modulo, 'get_sample_duration', contata)

        build_stream()

        assert letture == ['silence.wav']


# =============================================================================
# 2. I RIFERIMENTI CHE ASSEGNA IL GENERATOR SONO DICHIARATI
# =============================================================================

class TestIRiferimentiDelGenerator:
    """`Generator._create_stream` assegna le tabelle dopo la costruzione:
    `sample_table_num` e `window_table_map`. Il contratto era scritto in un
    posto solo, la docstring di una fixture; uno Stream costruito fuori dal
    Generator e letto con `.voices` moriva dall'interno della generazione,
    con un `AttributeError` sulla mappa delle finestre o, assegnata quella,
    con il `TypeError` della validazione di `Grain` sulla sample table."""

    def test_la_costruzione_li_dichiara_vuoti(self, build_stream):
        s = build_stream()

        assert s.sample_table_num is None
        assert s.window_table_map is None

    def test_generare_senza_riferimenti_dice_cosa_manca(self, build_stream):
        s = build_stream(stream_id='nuvola')

        with pytest.raises(EngineRuntimeError) as exc:
            s.voices

        messaggio = str(exc.value)
        assert 'sample_table_num' in messaggio
        assert 'window_table_map' in messaggio
        assert 'Generator' in messaggio
        assert 'nuvola' in messaggio
        assert exc.value.stream_id == 'nuvola'

    @pytest.mark.parametrize('assegnato,mancante', [
        ('sample_table_num', 'window_table_map'),
        ('window_table_map', 'sample_table_num'),
    ])
    def test_nomina_solo_quello_che_manca(self, build_stream, assegnato,
                                          mancante):
        s = build_stream()
        setattr(s, assegnato, 1 if assegnato == 'sample_table_num'
                else {'hanning': 2})

        with pytest.raises(EngineRuntimeError) as exc:
            s.generate_grains()

        assert mancante in str(exc.value)
        assert assegnato not in str(exc.value)

    def test_con_i_riferimenti_assegnati_genera(self, build_stream):
        s = build_stream()
        s.sample_table_num = 1
        s.window_table_map = {'hanning': 2}

        assert sum(len(voce) for voce in s.voices) > 0


# =============================================================================
# 3. NESSUN TEST COSTRUISCE UNO STREAM A META'
# =============================================================================

TESTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _costruzioni_a_meta(albero):
    """Le chiamate `object.__new__(Stream)` e `Stream.__new__(Stream)`."""
    for nodo in ast.walk(albero):
        if not (isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == '__new__'
                and isinstance(nodo.func.value, ast.Name)
                and nodo.func.value.id in ('object', 'Stream')):
            continue
        if any(isinstance(a, ast.Name) and a.id == 'Stream' for a in nodo.args):
            yield nodo.lineno


class TestNessunoStreamAMeta:
    """La guardia che tiene chiusa la porta.

    Un oggetto a meta' non ha gli attributi che `__init__` dichiara, e il
    costo lo pagava la produzione: i `getattr` con un default e il ripiego
    sulla clip strategy esistevano per lui. Letta dall'AST e non dal testo,
    cosi' questo file — che il nome lo scrive nelle docstring — non accusa se
    stesso.
    """

    def test_nessun_object_new_di_stream(self):
        trovati = []
        for cartella, _, file in os.walk(TESTS_DIR):
            for nome in sorted(file):
                if not nome.endswith('.py'):
                    continue
                percorso = os.path.join(cartella, nome)
                with open(percorso, encoding='utf-8') as fh:
                    albero = ast.parse(fh.read(), filename=percorso)
                relativo = os.path.relpath(percorso, TESTS_DIR)
                trovati += [f"{relativo}:{riga}"
                            for riga in _costruzioni_a_meta(albero)]

        assert not trovati, (
            "Stream costruito saltando __init__: " + ", ".join(trovati) +
            ". Costruiscilo con la fixture `build_stream` di tests/conftest.py "
            "e sostituisci dopo i collaboratori da isolare (issue #283).")

    def test_la_guardia_vede_le_due_grafie(self):
        """La controprova: senza, una guardia che non trova niente e una
        guardia cieca si leggono uguali."""
        albero = ast.parse(
            "a = object.__new__(Stream)\n"
            "b = Stream.__new__(Stream)\n"
            "c = object.__new__(Altro)\n")

        assert list(_costruzioni_a_meta(albero)) == [1, 2]
