"""
test_read_direction.py

Validazione e normalizzazione del valore grezzo di `grain.read_direction`
(issue #207).

La chiave dichiara il verso di lettura INTERNO al grano: due stati, -1
(indietro) e +1 (avanti). Da questa natura discendono le due regole che il
modulo fa rispettare, entrambe come errore esplicito e mai come correzione
silenziosa:

1. l'interpolazione e' `step`, implicita e obbligatoria — dichiarare `linear`
   o `cubic` (dict, per-punto o BP group) e' errore;
2. i valori dichiarati stanno in {-1, +1} — 0 non ha un segno, 0.3 non e' un
   verso.

Organizzazione:
1. Scalari
2. Envelope in forma di lista di breakpoint
3. Interpolazione: step implicito, step esplicito, tutto il resto errore
4. Dominio dei valori
5. La forma del corpo non e' piu' affare di questo modulo (issue #211)
6. La stessa grammatica ai due ingressi (lista nuda e dict {points})
7. Forme non riconosciute

I guard di forma — arita' dei gruppi, `end_time`, `n_reps`, pattern,
distribuzione temporale — stavano qui fino a #211 e sono saliti in
`EnvelopeBuilder`, che li applica a ogni chiave. Per questa chiave la risposta
e' rimasta la stessa, e la fissa `tests/core/test_stream_read_direction.py`
(`TestNienteValueErrorNudo`), attraverso lo Stream: e' li' che l'errore la
ottiene, non piu' in `normalize_read_direction`.
"""

import pytest

from pge.parameters.read_direction import (
    READ_DIRECTION_FIELD,
    READ_DIRECTION_VALUES,
    normalize_read_direction,
)
from pge.shared.exceptions import InvalidFieldValueError


# =============================================================================
# 1. SCALARI
# =============================================================================

class TestScalari:
    """Uno scalare resta uno scalare: niente envelope da costruire."""

    @pytest.mark.parametrize("value", [1, 1.0, -1, -1.0])
    def test_valori_ammessi(self, value):
        assert normalize_read_direction(value) == float(value)

    def test_restituisce_float(self):
        assert isinstance(normalize_read_direction(1), float)

    def test_chiave_vuota_e_errore(self):
        """`read_direction:` senza valore non e' una dichiarazione di verso."""
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(None)
        assert exc.value.field == READ_DIRECTION_FIELD

    @pytest.mark.parametrize("value", [True, False])
    def test_booleani_rifiutati(self, value):
        """`true` non e' +1: la chiave non e' un flag."""
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction(value)

    def test_stringa_rifiutata(self):
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction('avanti')

    @pytest.mark.parametrize("value", [
        10 ** 400,          # int arbitrariamente grande: non ha un float
        -(10 ** 400),
        float('nan'),
        float('inf'),
    ])
    def test_numeri_senza_float_o_senza_ordine(self, value):
        """Un numero fuori dominio va rifiutato, non fatto esplodere.

        `float()` su un `int` più grande di ogni double alza `OverflowError`
        dentro il validatore: un errore che non porta il campo, sollevato
        proprio da chi deve produrne uno che lo porta. Il confronto
        sull'appartenenza non converte niente."""
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(value)
        assert exc.value.field == READ_DIRECTION_FIELD


# =============================================================================
# 2. ENVELOPE COME LISTA DI BREAKPOINT
# =============================================================================

class TestListaDiBreakpoint:
    """La forma normale: una spezzata qualsiasi, il gradino lo impone la chiave."""

    def test_lista_normalizzata_in_dict_step(self):
        raw = [[0, 1], [12, -1], [20, 1]]
        assert normalize_read_direction(raw) == {'type': 'step', 'points': raw}

    def test_punti_preservati(self):
        raw = [[0, -1], [5, 1]]
        assert normalize_read_direction(raw)['points'] == raw

    def test_lista_vuota_rifiutata(self):
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction([])


# =============================================================================
# 3. INTERPOLAZIONE
# =============================================================================

class TestInterpolazione:
    """`step` e' la natura della chiave: implicito, e l'unico ammesso."""

    def test_step_implicito_sulla_lista_nuda(self):
        assert normalize_read_direction([[0, 1], [3, -1]])['type'] == 'step'

    def test_step_esplicito_e_ridondanza_accettata(self):
        raw = {'type': 'step', 'points': [[0, 1], [3, -1]]}
        assert normalize_read_direction(raw) == raw

    def test_dict_senza_type_riceve_step(self):
        out = normalize_read_direction({'points': [[0, 1], [3, -1]]})
        assert out['type'] == 'step'

    def test_dict_preserva_le_altre_chiavi(self):
        """time_unit governa la scala dei tempi: non va persa nella normalizzazione."""
        raw = {'points': [[0, 1], [1, -1]], 'time_unit': 'normalized'}
        assert normalize_read_direction(raw)['time_unit'] == 'normalized'

    @pytest.mark.parametrize("interp", ['linear', 'cubic'])
    def test_dict_con_interp_diverso_da_step_e_errore(self, interp):
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction({'type': interp, 'points': [[0, 1], [3, -1]]})
        assert exc.value.field == READ_DIRECTION_FIELD

    @pytest.mark.parametrize("interp", ['linear', 'cubic'])
    def test_per_punto_con_interp_diverso_da_step_e_errore(self, interp):
        """Tag per-punto (issue #54): [t, v, type]."""
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction([[0, 1, interp], [3, -1]])

    def test_per_punto_step_accettato(self):
        raw = [[0, 1, 'step'], [3, -1]]
        assert normalize_read_direction(raw)['points'] == raw

    @pytest.mark.parametrize("interp", ['linear', 'cubic'])
    def test_bp_group_con_interp_diverso_da_step_e_errore(self, interp):
        """BP group (issue #64): [points, interp]."""
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction([[[0, 1], [3, -1]], interp])

    def test_bp_group_step_accettato(self):
        raw = [[[0, 1], [3, -1]], 'step']
        assert normalize_read_direction(raw) == {'type': 'step', 'points': raw}

    @pytest.mark.parametrize("interp", ['linear', 'cubic'])
    def test_compatto_con_interp_diverso_da_step_e_errore(self, interp):
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction([[[0, 1], [50, -1]], 4.0, 2, interp])

    def test_compatto_step_accettato(self):
        raw = [[[0, 1], [50, -1]], 4.0, 2, 'step']
        assert normalize_read_direction(raw) == {'type': 'step', 'points': raw}

    def test_compatto_senza_interp_accettato(self):
        raw = [[[0, 1], [50, -1]], 4.0, 2]
        assert normalize_read_direction(raw) == {'type': 'step', 'points': raw}

    def test_hint_spiega_il_perche(self):
        """Il messaggio dice PERCHE', non solo COSA: due stati, non una rampa."""
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction({'type': 'linear', 'points': [[0, 1], [3, -1]]})
        hint = exc.value.hint.lower()
        assert 'step' in hint
        assert 'due stati' in hint

    def test_errore_nomina_l_interp_trovato(self):
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction({'type': 'cubic', 'points': [[0, 1], [3, -1]]})
        assert exc.value.value == 'cubic'


# =============================================================================
# 4. DOMINIO DEI VALORI
# =============================================================================

class TestDominio:
    """Con `step` imposto l'envelope emette solo i valori scritti: si validano
    quelli, invece di arrotondarli al segno."""

    def test_valori_ammessi_sono_due(self):
        assert set(READ_DIRECTION_VALUES) == {-1.0, 1.0}

    @pytest.mark.parametrize("value", [0, 0.5, -0.3, 2, -2])
    def test_scalare_fuori_dominio_e_errore(self, value):
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(value)
        assert exc.value.field == READ_DIRECTION_FIELD

    def test_zero_e_errore_esplicito(self):
        """0 non ha un segno: non c'e' risposta non arbitraria."""
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(0)
        assert '0' in exc.value.hint or 'segno' in exc.value.hint.lower()

    @pytest.mark.parametrize("value", [0, 0.5, 3])
    def test_breakpoint_fuori_dominio_e_errore(self, value):
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction([[0, 1], [3, value]])

    def test_breakpoint_fuori_dominio_nel_gruppo(self):
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction([[[0, 1], [3, 0]], 'step'])

    def test_breakpoint_fuori_dominio_nel_compatto(self):
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction([[[0, 1], [50, 0.5]], 4.0, 2])

    def test_end_time_e_n_reps_non_sono_valori(self):
        """Nel formato compatto solo i pattern points portano il verso."""
        raw = [[[0, 1], [50, -1]], 4.0, 2]
        assert normalize_read_direction(raw)['points'] is raw


# =============================================================================
# 5. LA FORMA NON E' PIU' AFFARE DI QUESTO MODULO (issue #211)
# =============================================================================

class TestLaFormaEDelBuilder:
    """`normalize_read_direction` giudica il dominio — interp e valori — e
    lascia la forma al builder, che la giudica per ogni chiave.

    Non e' un buco: il corpo arriva comunque a `EnvelopeBuilder` attraverso
    l'orchestratore, che gli passa il campo, e li' cade con lo stesso
    `InvalidFieldValueError` su `grain.read_direction`
    (`tests/core/test_stream_read_direction.py`). Quello che questi test
    fissano e' che il modulo non ne tenga una seconda copia — era l'isola che
    #211 ha chiuso.
    """

    @pytest.mark.parametrize("corpo", [
        pytest.param([[[0, 1]], 'step'], id='bp_group_un_punto'),
        pytest.param([[[0, 1], [100, -1]], 2.0, 0], id='zero_ripetizioni'),
        pytest.param([[[0, 1], [100, -1]], 2.0, True],
                     id='ripetizioni_booleane'),
        pytest.param([[[0, 1], [50, -1]], True, 2], id='end_time_booleano'),
        pytest.param([[], 2.0, 2], id='pattern_vuoto'),
        pytest.param([[[0, 1], [150, -1]], 2.0, 2], id='x_oltre_cento'),
        pytest.param([[[100, 1], [0, -1]], 2.0, 2], id='x_indietro'),
        pytest.param([[[0, 1], [100, -1]], 2.0, 2, 'step', 'banana'],
                     id='distribuzione_ignota'),
    ])
    def test_la_forma_passa_al_builder(self, corpo):
        assert normalize_read_direction(corpo)['points'] is corpo

    def test_un_gruppo_senza_punti_non_e_una_forma_sconosciuta(self):
        """Un gruppo senza punti e' un gruppo con troppo pochi punti: l'hint
        giusto e' quello del builder, non il `_FORM_HINT` di una lista vuota."""
        corpo = [[], 'step']
        assert normalize_read_direction(corpo)['points'] is corpo

    def test_una_macro_forma_nel_pattern_non_si_legge_come_valore(self):
        """Da un BP group infilato nel pattern il "y" sarebbe la stringa del
        suo interp: il modulo non lo legge, e non dice che `'step'` non e' un
        verso. Il punto lo rifiuta il builder, nominandolo."""
        corpo = [[[[[0, 1], [50, -1]], 'step']], 2.0, 2]
        assert normalize_read_direction(corpo)['points'] is corpo

    @pytest.mark.parametrize("corpo, valore", [
        pytest.param([[[0, 1]], 'linear'], 'linear', id='gruppo'),
        pytest.param([[[0, 0], [150, 1]], 2.0, 2], 0, id='compatto'),
    ])
    def test_il_dominio_resta_qui_anche_sulle_forme_malformate(
            self, corpo, valore):
        """Il dominio si giudica prima della forma: un gruppo a un punto con
        interp `linear`, un pattern oltre 100 con un valore 0, cadono qui per
        quello che questa chiave non ammette."""
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(corpo)
        assert exc.value.field == READ_DIRECTION_FIELD
        assert exc.value.value == valore


# =============================================================================
# 6. LA STESSA GRAMMATICA AI DUE INGRESSI
# =============================================================================

class TestStessaGrammaticaNeiDueIngressi:
    """Una curva scritta come lista nuda e la stessa curva dentro
    `{points: ...}` sono la stessa curva.

    I due ingressi — dict e lista — devono accettare e rifiutare le stesse
    cose. Non e' una comodita': `Envelope` costruisce entrambe le forme (il
    dict con `points` in formato compatto e' l'esempio nel suo docstring),
    quindi un ingresso piu' stretto dell'altro rifiuterebbe uno YAML che il
    motore renderizza, e con un messaggio che elenca fra le forme valide
    proprio quella che sta rifiutando.
    """

    COMPATTO = [[[0, 1], [50, -1]], 20, 2]
    GRUPPO = [[[0, 1], [10, -1]], 'step']

    def test_compatto_accettato_nel_dict(self):
        assert normalize_read_direction(
            {'points': self.COMPATTO})['points'] is self.COMPATTO

    def test_compatto_stessa_risposta_nei_due_ingressi(self):
        assert (normalize_read_direction({'points': self.COMPATTO})
                == normalize_read_direction(self.COMPATTO))

    def test_bp_group_accettato_nel_dict(self):
        assert normalize_read_direction(
            {'points': self.GRUPPO})['points'] is self.GRUPPO

    def test_bp_group_stessa_risposta_nei_due_ingressi(self):
        assert (normalize_read_direction({'points': self.GRUPPO})
                == normalize_read_direction(self.GRUPPO))

    def test_lista_vuota_dentro_il_dict(self):
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction({'points': []})

    # --- I rifiuti valgono anche dentro le macro-forme nel dict ---------------
    # Simmetria non vuol dire permissivita': allargare l'ingresso dict alle
    # macro-forme non deve aprire una scorciatoia per dichiarare un interp o un
    # valore che la chiave non ammette.

    @pytest.mark.parametrize("interp", ['linear', 'cubic'])
    def test_dict_con_compatto_a_interp_non_step(self, interp):
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(
                {'points': [[[0, 1], [50, -1]], 20, 2, interp]})
        assert exc.value.value == interp

    @pytest.mark.parametrize("interp", ['linear', 'cubic'])
    def test_dict_con_bp_group_a_interp_non_step(self, interp):
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(
                {'points': [[[0, 1], [10, -1]], interp]})
        assert exc.value.value == interp

    def test_dict_con_compatto_fuori_dominio(self):
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction({'points': [[[0, 1], [50, 0]], 20, 2]})
        # La ragione, non solo il tipo: senza questa riga il test passerebbe
        # anche se il corpo fosse rifiutato per la forma invece che per lo 0.
        assert exc.value.value == 0
        assert 'segno' in exc.value.hint

    def test_dict_con_bp_group_fuori_dominio(self):
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction({'points': [[[0, 1], [10, 0.5]], 'step']})
        assert exc.value.value == 0.5

    def test_il_type_del_dict_vale_anche_sulle_macro_forme(self):
        """`type: linear` sul dict resta un errore comunque sia scritto il
        corpo: le due dichiarazioni non si annullano a vicenda."""
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(
                {'type': 'linear', 'points': self.COMPATTO})
        assert exc.value.value == 'linear'

    # --- Le stesse posizioni in cui le riconosce il builder -------------------

    MISTO = [[0, 1], [0.3, 1], [[[0, -1], [100, 1]], 1.3, 2]]

    def test_lista_mista_accettata_nei_due_ingressi(self):
        """Una sezione compatta dentro una lista di breakpoint e' forma
        documentata del builder, e passa da entrambi gli ingressi."""
        assert (normalize_read_direction({'points': self.MISTO})['points']
                is self.MISTO)
        assert (normalize_read_direction(self.MISTO)['points']
                is self.MISTO)

    def test_lista_mista_valida_i_valori_della_sezione_compatta(self):
        misto = [[0, 1], [0.3, 1], [[[0, 0], [100, 1]], 1.3, 2]]
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction({'points': misto})
        assert exc.value.value == 0

    def test_elemento_estraneo_in_una_lista_mista(self):
        """Il marcatore stringa e' l'elemento che cade, non la sezione
        compatta che lo precede: quella e' valida e viene accettata."""
        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(
                {'points': [[[[0, 1], [50, -1]], 20, 2], 'step']})
        assert exc.value.value == 'step'


# =============================================================================
# 7. FORME NON RICONOSCIUTE
# =============================================================================

class TestFormeNonRiconosciute:

    def test_dict_senza_points(self):
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction({'type': 'step'})

    @pytest.mark.parametrize("t", ['x', None, True, [0]])
    @pytest.mark.parametrize("ingresso", ['dict', 'lista'])
    def test_breakpoint_dict_con_t_non_numerico(self, ingresso, t):
        """Il breakpoint in forma `{t, v}` deve dichiarare un tempo come
        quello in forma lista: là `_is_number(item[0])` è già preteso, qui no,
        e il valore arriva al builder che lo rifiuta con un `ValueError` nudo.
        È l'asimmetria fra le forme che il modulo dichiara chiusa."""
        corpo = [{'t': t, 'v': 1}, {'t': 1.0, 'v': -1}]
        raw = {'points': corpo} if ingresso == 'dict' else corpo

        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(raw)
        assert exc.value.value == corpo[0]

    def test_breakpoint_dict_valido_resta_valido(self):
        corpo = [{'t': 0, 'v': 1}, {'t': 1.0, 'v': -1}]
        assert normalize_read_direction(corpo)['points'] is corpo

    def test_elemento_non_breakpoint(self):
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction([[0, 1], 'cycle'])
