"""
L'interprete delle espressioni (issue #308, mappe caotiche 1/7), da solo.

Un parametro che legge una mappa si scrive come un'espressione,
`(0.02 + 0.08*m1)`. L'interprete e' un parser a discesa ricorsiva che compila
in chiusure, senza `eval`: e' il porting di quello del «Banco del chirp»
(docs/plans/mappe-caotiche-pagine/banco-del-chirp.html), che il plan indica
come lettura di riferimento. I valori qui sotto sono quelli del plan e della
issue; dove il banco e Python divergono (la divisione per zero, `round`) vale
il banco, ed e' scritto nel caso.
"""
import ast
import math
import os

import pytest

from pge.expressions.expression import (
    CONSTANTS,
    FUNCTIONS,
    compile_expression,
)
from pge.shared.exceptions import ConfigError, EngineError, ExpressionError


def valuta(sorgente, **ambiente):
    """Compila con i nomi dell'ambiente dichiarati, e valuta."""
    return compile_expression(sorgente, ambiente.keys())(ambiente)


# =============================================================================
# 1. ARITMETICA E PRECEDENZE
# =============================================================================

class TestAritmetica:

    @pytest.mark.parametrize('sorgente, atteso', [
        ('1 + 2', 3.0),
        ('7 - 10', -3.0),
        ('3 * 4', 12.0),
        ('1 / 4', 0.25),
        ('2 ** 10', 1024.0),
        ('1 + 2 * 3', 7.0),
        ('(1 + 2) * 3', 9.0),
        ('10 - 4 - 3', 3.0),          # associa a sinistra
        ('24 / 4 / 2', 3.0),          # associa a sinistra
        ('2 * 3 ** 2', 18.0),
        ('.5 + 1.', 1.5),
        ('1e3 + 2.5e-1', 1000.25),
    ])
    def test_le_quattro_operazioni_e_la_potenza(self, sorgente, atteso):
        assert valuta(sorgente) == pytest.approx(atteso)

    def test_il_meno_unario_lega_meno_della_potenza(self):
        """Riferimento del plan: `-m1**2` con m1 = 0.5 da' -0.25, come in
        Python (`-(m1**2)`), non 0.25."""
        assert valuta('-m1**2', m1=0.5) == -0.25

    def test_la_potenza_associa_a_destra(self):
        """Riferimento del plan: `2**3**2` e' 2**(3**2) = 512, non 64."""
        assert valuta('2**3**2') == 512.0

    def test_l_esponente_puo_avere_il_segno(self):
        assert valuta('2**-1') == 0.5
        assert valuta('2**-m1', m1=2) == 0.25

    def test_i_segni_unari_si_ripetono(self):
        assert valuta('--3') == 3.0
        assert valuta('-+3') == -3.0
        assert valuta('2 - -3') == 5.0

    def test_l_espressione_della_issue(self):
        """`(0.02 + 0.08*m1)`: fra parentesi, com'e' scritta nello YAML."""
        assert valuta('(0.02 + 0.08*m1)', m1=0.5) == pytest.approx(0.06)

    def test_il_risultato_e_un_float(self):
        assert isinstance(valuta('1 + 2'), float)


# =============================================================================
# 2. NOMI
# =============================================================================

class TestNomi:

    def test_le_costanti(self):
        assert valuta('pi') == math.pi
        assert valuta('e') == math.e
        assert set(CONSTANTS) == {'pi', 'e'}

    def test_le_variabili_dichiarate_si_leggono_dall_ambiente(self):
        assert valuta('m1 + t', m1=0.25, t=3.0) == 3.25

    def test_la_stessa_chiusura_si_rivaluta_con_un_altro_ambiente(self):
        f = compile_expression('2 * m1', ['m1'])
        assert f({'m1': 1.0}) == 2.0
        assert f({'m1': 0.5}) == 1.0

    def test_un_nome_puntato_e_un_nome_solo(self):
        """`m1.y` e' la seconda variabile di una mappa a due variabili."""
        f = compile_expression('m1 + m1.y', ['m1', 'm1.y'])
        assert f({'m1': 1.0, 'm1.y': 0.5}) == 1.5

    def test_la_chiusura_dice_quali_nomi_legge(self):
        """Serve a chi prepara l'ambiente: una mappa che l'espressione non
        nomina non va letta."""
        f = compile_expression('m1 * sin(t) + pi', ['m1', 'm2', 't'])
        assert f.names == ('m1', 't')


# =============================================================================
# 3. FUNZIONI
# =============================================================================

class TestFunzioni:

    def test_l_elenco_e_quello_della_issue(self):
        assert set(FUNCTIONS) == set(
            'sin cos tan abs sqrt exp log floor round sign min max pow '
            'frac clip fold wrap'.split())

    @pytest.mark.parametrize('sorgente, atteso', [
        ('sin(pi / 2)', 1.0),
        ('cos(0)', 1.0),
        ('tan(pi / 4)', 1.0),
        ('abs(-3.5)', 3.5),
        ('sqrt(16)', 4.0),
        ('exp(1)', math.e),
        ('log(e)', 1.0),
        ('floor(2.7)', 2.0),
        ('floor(-2.1)', -3.0),
        ('sign(-4)', -1.0),
        ('sign(0)', 0.0),
        ('sign(0.1)', 1.0),
        ('min(3, 1, 2)', 1.0),
        ('max(3, 1, 2)', 3.0),
        ('min(5)', 5.0),
        ('pow(2, 8)', 256.0),
        ('frac(2.75)', 0.75),
        ('frac(-0.25)', 0.75),
        ('clip(1.5, 0, 1)', 1.0),
        ('clip(-0.5, 0, 1)', 0.0),
        ('clip(0.4, 0, 1)', 0.4),
    ])
    def test_valori_noti(self, sorgente, atteso):
        assert valuta(sorgente) == pytest.approx(atteso)

    def test_fold_riflette(self):
        """Riferimento del plan: `fold(1.3, 0, 1)` da' 0.7."""
        assert valuta('fold(1.3, 0, 1)') == pytest.approx(0.7)
        assert valuta('fold(-0.2, 0, 1)') == pytest.approx(0.2)
        assert valuta('fold(2.3, 0, 1)') == pytest.approx(0.3)
        assert valuta('fold(0.4, 0, 1)') == pytest.approx(0.4)

    def test_wrap_riparte_dall_altro_capo(self):
        """Riferimento del plan: `wrap(-0.25, 0, 1)` da' 0.75."""
        assert valuta('wrap(-0.25, 0, 1)') == pytest.approx(0.75)
        assert valuta('wrap(1.25, 0, 1)') == pytest.approx(0.25)
        assert valuta('wrap(7, 2, 5)') == pytest.approx(4.0)

    def test_fold_e_wrap_su_una_fascia_vuota_danno_il_minimo(self):
        """Come nel banco: senza larghezza non c'e' dove riflettere."""
        assert valuta('fold(3, 1, 1)') == 1.0
        assert valuta('wrap(3, 2, 1)') == 2.0

    def test_round_arrotonda_il_mezzo_verso_l_alto(self):
        """Come `Math.round` del banco, non come `round` di Python (che
        manda 0.5 a 0 e 2.5 a 2): la stessa espressione deve dare lo stesso
        grano nella pagina e nel motore."""
        assert valuta('round(0.5)') == 1.0
        assert valuta('round(2.5)') == 3.0
        assert valuta('round(-0.5)') == 0.0
        assert valuta('round(2.4)') == 2.0

    def test_le_funzioni_si_annidano(self):
        assert valuta('clip(0.02 + 0.18*fold(m1*2, 0, 1), 0.05, 0.15)',
                      m1=0.8) == pytest.approx(0.092)


# =============================================================================
# 4. FUORI DOMINIO: UN NUMERO NON FINITO, MAI UN'ECCEZIONE
# =============================================================================

class TestFuoriDominio:
    """Un'espressione si valuta a ogni grano, dentro il giro che genera i
    grani: non puo' sollevare. Fuori dominio da' un non-finito, come nel
    banco (JavaScript), e a tagliarlo e scriverlo sul clip log e' il clamp
    del parametro."""

    def test_la_divisione_per_zero_e_un_infinito(self):
        assert valuta('1 / 0') == math.inf
        assert valuta('-1 / 0') == -math.inf
        assert math.isnan(valuta('0 / 0'))

    def test_la_radice_di_un_negativo_e_nan(self):
        assert math.isnan(valuta('sqrt(-1)'))

    def test_il_logaritmo_fuori_dominio(self):
        assert valuta('log(0)') == -math.inf
        assert math.isnan(valuta('log(-1)'))

    def test_la_potenza_fuori_dominio(self):
        assert math.isnan(valuta('(-8) ** 0.5'))
        assert valuta('0 ** -1') == math.inf
        assert valuta('10 ** 400') == math.inf

    def test_l_esponenziale_che_trabocca(self):
        assert valuta('exp(1000)') == math.inf

    def test_un_non_finito_attraversa_le_funzioni(self):
        assert math.isnan(valuta('floor(0 / 0)'))
        assert valuta('floor(1 / 0)') == math.inf
        assert math.isnan(valuta('round(0 / 0)'))
        assert math.isnan(valuta('wrap(1 / 0, 0, 1)'))
        assert math.isnan(valuta('min(1, 0 / 0)'))
        assert math.isnan(valuta('max(0 / 0, 1)'))
        assert math.isnan(valuta('clip(0 / 0, 0, 1)'))


# =============================================================================
# 5. ERRORI
# =============================================================================

class TestErrori:

    def test_sta_nella_gerarchia_degli_errori_di_configurazione(self):
        assert issubclass(ExpressionError, ConfigError)
        assert issubclass(ExpressionError, EngineError)

    @pytest.mark.parametrize('sorgente, dice', [
        ('', "e' vuota"),
        ('   ', "e' vuota"),
        ('1 + $', "non capisco «$»"),
        ('(1 + 2', "manca una parentesi chiusa"),
        ('sin(1', "manca una parentesi chiusa"),
        ('1 +', "finisce a meta'"),
        ('1 2', "non mi aspettavo «2»"),
        ('1 + 2)', "non mi aspettavo «)»"),
        ('* 2', "non mi aspettavo «*»"),
        ('m2 * 2', "nome sconosciuto «m2»"),
        ('m1.y', "nome sconosciuto «m1.y»"),
        ('boh(1)', "funzione sconosciuta «boh»"),
        ('sin()', "sin vuole 1 argomento"),
        ('sin(1, 2)', "sin vuole 1 argomento"),
        ('pow(2)', "pow vuole 2 argomenti"),
        ('clip(1, 2)', "clip vuole 3 argomenti"),
        ('fold(1, 2, 3, 4)', "fold vuole 3 argomenti"),
        ('wrap(1)', "wrap vuole 3 argomenti"),
        ('min()', "min vuole almeno un argomento"),
        ('2 % 3', "non capisco «%"),
        ('2 ^ 3', "non capisco «^"),
    ])
    def test_ogni_errore_dice_cosa_non_va(self, sorgente, dice):
        with pytest.raises(ExpressionError) as exc:
            compile_expression(sorgente, ['m1'])
        assert dice in exc.value.reason

    def test_l_errore_porta_il_campo_e_l_espressione(self):
        with pytest.raises(ExpressionError) as exc:
            compile_expression('(0.02 + 0.08*m2)', ['m1', 't'],
                               field='grain.duration')
        err = exc.value
        assert err.field == 'grain.duration'
        assert err.expression == '(0.02 + 0.08*m2)'
        messaggio = err.user_message()
        assert "grain.duration" in messaggio
        assert "(0.02 + 0.08*m2)" in messaggio
        assert "nome sconosciuto «m2»" in messaggio

    def test_un_nome_sconosciuto_dice_quali_ci_sono(self):
        with pytest.raises(ExpressionError) as exc:
            compile_expression('m2', ['m1', 't'])
        assert 'm1' in exc.value.hint and 't' in exc.value.hint

    def test_lo_stream_lo_aggiunge_chi_lo_conosce(self):
        """Come ogni ConfigError: l'interprete non sa di quale stream e'."""
        with pytest.raises(ExpressionError) as exc:
            compile_expression('1 +', [])
        err = exc.value
        assert err.stream_id is None
        err.stream_id = 's1'
        assert 'Stream:       s1' in err.user_message()

    def test_una_stringa_non_e_obbligatoria_ma_un_non_testo_e_un_errore(self):
        with pytest.raises(ExpressionError):
            compile_expression(None, [])


# =============================================================================
# 6. NIENTE EVAL
# =============================================================================

class TestNienteEval:

    def test_il_modulo_non_chiama_eval_exec_ne_compile(self):
        """Il criterio della issue, letto nel sorgente: l'interprete non
        delega a Python la valutazione di un testo scritto in uno YAML."""
        import pge.expressions.expression as modulo
        with open(modulo.__file__, encoding='utf-8') as f:
            albero = ast.parse(f.read())
        chiamate = {
            nodo.func.id for nodo in ast.walk(albero)
            if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
        }
        assert not chiamate & {'eval', 'exec', 'compile', '__import__'}

    def test_un_testo_python_valido_non_e_un_espressione(self):
        for sorgente in ('__import__("os")', 'm1.__class__', '[1, 2]',
                         'lambda: 1', '1 if 1 else 2', '"a"'):
            with pytest.raises(ExpressionError):
                compile_expression(sorgente, ['m1'])


# =============================================================================
# 7. PROFONDITA': UNA CHIUSURA COMPILATA NON SOLLEVA MAI
# =============================================================================

class TestProfondita:
    """Il docstring del modulo promette che una chiusura compilata non
    sollevi mai, e che gli errori siano tutti al parse. Due modi di
    smentirlo, tutti e due fuori dalla gerarchia `EngineError`:

    - una catena lunga (`a + b + c + ...`) si compilava in chiusure annidate
      una nell'altra, una per operatore: si compilava, e alla valutazione —
      a ogni grano — usciva un `RecursionError`;
    - un annidamento profondo (parentesi, segni, potenze, chiamate) usciva
      con un `RecursionError` gia' al parse.

    La catena ora e' una chiusura sola, e l'annidamento ha un limite
    dichiarato (`MAX_DEPTH`), detto da un `ExpressionError`.
    """

    @pytest.mark.parametrize('operatore, termine, atteso', [
        ('+', '0.001', 5.0),
        ('-', '0.001', -4.998),
        ('*', '1', 1.0),
        ('/', '1', 1.0),
    ])
    def test_una_catena_lunga_si_valuta(self, operatore, termine, atteso):
        sorgente = f' {operatore} '.join([termine] * 5000)
        assert valuta(sorgente) == pytest.approx(atteso)

    def test_una_catena_lunga_si_valuta_anche_in_fondo_allo_stack(self):
        """A ogni grano la valutazione arriva gia' qualche decina di frame
        in fondo: la chiusura non deve aggiungerne uno per operatore."""
        import sys
        compilata = compile_expression(' + '.join(['m1'] * 5000), ['m1'])

        def in_fondo(n):
            return in_fondo(n - 1) if n else compilata({'m1': 1.0})

        margine = sys.getrecursionlimit() - 200
        assert in_fondo(margine) == 5000.0

    @pytest.mark.parametrize('sorgente, atteso', [
        ('0.1 + 0.2 - 0.3', (0.1 + 0.2) - 0.3),
        ('1 - 2 - 3', -4.0),
        ('2 / 4 / 8', 0.0625),
        ('2 * 3 / 4 * 5', 7.5),
        ('1 - 2 * 3 + 4 / 2', -3.0),
    ])
    def test_la_catena_si_valuta_da_sinistra(self, sorgente, atteso):
        """`0.1 + 0.2 - 0.3` da' un numero da sinistra e un altro da destra
        (5.55e-17 e 2.78e-17): la chiusura sola fa le operazioni nello
        stesso ordine delle chiusure annidate, bit per bit."""
        assert valuta(sorgente) == atteso
        assert valuta('0.1 + 0.2 - 0.3') != 0.1 + (0.2 - 0.3)

    @pytest.mark.parametrize('costruisci', [
        lambda n: '(' * n + '1' + ')' * n,
        lambda n: '-' * n + '1',
        lambda n: '2**' * n + '1',
        lambda n: 'abs(' * n + '1' + ')' * n,
    ], ids=['parentesi', 'segni', 'potenze', 'chiamate'])
    def test_fino_al_limite_si_compila(self, costruisci):
        from pge.expressions.expression import MAX_DEPTH
        compile_expression(costruisci(MAX_DEPTH), [])({})

    @pytest.mark.parametrize('costruisci', [
        lambda n: '(' * n + '1' + ')' * n,
        lambda n: '-' * n + '1',
        lambda n: '2**' * n + '1',
        lambda n: 'abs(' * n + '1' + ')' * n,
    ], ids=['parentesi', 'segni', 'potenze', 'chiamate'])
    def test_oltre_il_limite_e_un_errore_al_parse(self, costruisci):
        from pge.expressions.expression import MAX_DEPTH
        for n in (MAX_DEPTH + 1, 2000):
            with pytest.raises(ExpressionError) as exc:
                compile_expression(costruisci(n), [], field='grain.duration')
            assert 'annidata' in exc.value.reason
            assert str(MAX_DEPTH) in exc.value.reason
            assert exc.value.field == 'grain.duration'

    def test_un_espressione_vera_resta_lontana_dal_limite(self):
        """Il limite non tocca niente di quello che si scrive: qui ci sono
        cinque livelli (le parentesi esterne, un segno, una chiamata, una
        potenza, una parentesi)."""
        from pge.expressions.expression import MAX_DEPTH
        assert MAX_DEPTH >= 32
        assert valuta('(-fold(m1**(2), 0, 1))', m1=0.5) == -0.25
