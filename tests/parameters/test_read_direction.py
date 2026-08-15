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
5. Guard di arita': quello che passa di qui arriva vivo al builder
6. La stessa grammatica ai due ingressi (lista nuda e dict {points})
7. Forme non riconosciute
"""

import pytest

from pge.parameters.read_direction import (
    READ_DIRECTION_FIELD,
    READ_DIRECTION_VALUES,
    _FORM_HINT,
    _REPS_ARITY_HINT,
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
# 5. QUELLO CHE PASSA DI QUI ARRIVA VIVO AL BUILDER
# =============================================================================

class TestGuardDiArita:
    """Un corpo che il validatore accetta non deve esplodere nel builder.

    `normalize_read_direction` dichiara di sollevare `InvalidFieldValueError`,
    che porta il campo e a cui `Stream` attribuisce lo stream_id. Un `ValueError`
    nudo che risale da `EnvelopeBuilder` esce dalla gerarchia `EngineError`:
    l'utente perde la riga di contesto e PGE-ls perde il messaggio che parsa.

    Sono guard di **arità**, non una seconda validazione del builder: dicono
    quanti elementi servono perché la forma sia quella dichiarata, non se i
    valori hanno senso. L'unica eccezione è la distribuzione temporale, che
    non si controlla ma si delega al suo factory (vedi `_check_time_dist`).

    L'invariante non è chiuso, e non lo si dichiari tale: restano fuori le
    condizioni che dipendono da quanto il builder ha già percorso — `end_time`
    contro l'offset accumulato — e una distribuzione che validi i propri
    parametri solo quando la si usa (oggi `power`). Sono pinnate a Stream in
    `TestNienteValueErrorNudo`, che copre ciò che è davvero coperto.
    """

    @pytest.mark.parametrize("ingresso", ['dict', 'lista'])
    def test_bp_group_con_un_solo_punto(self, ingresso):
        """Una zona con meno di 2 punti non ha segmenti interni: e' la stessa
        condizione che il builder verifica, sollevata dove ha un campo."""
        corpo = [[[0, 1]], 'step']
        raw = {'points': corpo} if ingresso == 'dict' else corpo

        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(raw)
        assert exc.value.field == READ_DIRECTION_FIELD
        assert '2 punti' in exc.value.hint

    @pytest.mark.parametrize("ingresso", ['dict', 'lista'])
    def test_compatto_con_zero_ripetizioni(self, ingresso):
        corpo = [[[0, 1], [100, -1]], 2.0, 0]
        raw = {'points': corpo} if ingresso == 'dict' else corpo

        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(raw)
        assert exc.value.value == 0

    @pytest.mark.parametrize("ingresso", ['dict', 'lista'])
    def test_compatto_con_ripetizioni_negative(self, ingresso):
        corpo = [[[0, 1], [100, -1]], 2.0, -3]
        raw = {'points': corpo} if ingresso == 'dict' else corpo

        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(raw)
        assert exc.value.value == -3

    def test_una_ripetizione_resta_valida(self):
        """Il guard e' `>= 1`, non `> 1`: un ciclo solo e' legittimo."""
        corpo = [[[0, 1], [100, -1]], 2.0, 1]
        assert normalize_read_direction({'points': corpo})['points'] is corpo

    @pytest.mark.parametrize("ingresso", ['dict', 'lista'])
    def test_ripetizioni_booleane_rifiutate(self, ingresso):
        """`isinstance(True, int)` è vero, quindi `true` supera il
        riconoscimento della forma e poi `True < 1` è falso: il guard non
        scatta e `range(True)` rende un ciclo, in silenzio. È la stessa
        politica per cui `true` non è `+1` in nessun altro punto del modulo —
        e `false` era già rifiutato, per il valore, non per il tipo."""
        corpo = [[[0, 1], [100, -1]], 2.0, True]
        raw = {'points': corpo} if ingresso == 'dict' else corpo

        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(raw)
        assert exc.value.value is True
        assert exc.value.hint == _REPS_ARITY_HINT

    @pytest.mark.parametrize("ingresso", ['dict', 'lista'])
    def test_macro_forma_dentro_il_pattern_di_un_ciclo(self, ingresso):
        """`_is_compact_format` guarda solo la lunghezza dei punti del pattern
        (2 o 3), e un BP group e' lungo 2: passa quel filtro e arriva al
        builder, che sul primo elemento fa `x_pct / 100.0` e solleva un
        TypeError nudo. Qui il punto del pattern deve essere piatto."""
        corpo = [[[[[0, 1], [50, -1]], 'step']], 2.0, 2]
        raw = {'points': corpo} if ingresso == 'dict' else corpo

        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(raw)
        # Il valore dice QUALE elemento e' caduto: il gruppo annidato, non la
        # lista che lo contiene. Se un domani `_is_compact_format` si
        # stringesse e il corpo finisse su `_check_item`, cadrebbe `corpo[0]`
        # e questa asserzione lo direbbe.
        assert exc.value.value == corpo[0][0]
        assert exc.value.hint == _FORM_HINT

    @pytest.mark.parametrize("ingresso", ['dict', 'lista'])
    def test_punto_del_pattern_senza_interp_dichiarato(self, ingresso):
        """`[x%, y, None]` e' un punto piatto con l'interp lasciato al default,
        non una forma annidata: passa, e il builder lo espande in un
        breakpoint a due elementi. Il guard sul pattern pretende che il primo
        elemento sia un numero, non che il punto abbia due soli elementi."""
        corpo = [[[0, 1], [50, 1, None], [100, -1]], 2.0, 2]
        raw = {'points': corpo} if ingresso == 'dict' else corpo

        assert normalize_read_direction(raw)['points'] is corpo

    def test_pattern_vuoto_rifiutato(self):
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction({'points': [[], 2.0, 2]})

    @pytest.mark.parametrize("x", [150, -10, 100.5])
    @pytest.mark.parametrize("ingresso", ['dict', 'lista'])
    def test_x_del_pattern_fuori_da_zero_cento(self, ingresso, x):
        """La x di un punto del pattern è una **percentuale del ciclo**, e il
        vincolo `[0, 100]` è dichiarato nel docstring di `EnvelopeBuilder` ma
        non applicato da nessuno. Fuori da lì il ciclo sfonda i propri
        confini: con `x = 150` il ciclo dopo comincia prima che questo sia
        finito, con `x = -10` esce un breakpoint a tempo negativo."""
        corpo = [[[0, 1], [x, -1]], 2.0, 2]
        raw = {'points': corpo} if ingresso == 'dict' else corpo

        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(raw)
        assert exc.value.value == x

    @pytest.mark.parametrize("ingresso", ['dict', 'lista'])
    def test_x_del_pattern_che_tornano_indietro(self, ingresso):
        """Le x possono stare in `[0, 100]` e ciononostante tornare indietro:
        `[[100, 1], [0, -1]]` espande in `[[1.0, 1], [0.0, -1]]`, tempi
        all'indietro. L'envelope a `step` legge l'ultimo valore scritto e il
        `+1` dichiarato non compare in nessun grano — la regola 2 del modulo
        violata dal modulo."""
        corpo = [[[100, 1], [0, -1]], 2.0, 2]
        raw = {'points': corpo} if ingresso == 'dict' else corpo

        with pytest.raises(InvalidFieldValueError) as exc:
            normalize_read_direction(raw)
        assert exc.value.value == 0

    def test_x_ripetuta_resta_valida(self):
        """Una x ripetuta è una discontinuità voluta, non un errore: il
        vincolo è non-decrescente, non strettamente crescente."""
        corpo = [[[0, 1], [50, 1], [50, -1], [100, -1]], 2.0, 2]
        assert normalize_read_direction({'points': corpo})['points'] is corpo

    @pytest.mark.parametrize("x", [0, 100, 0.0, 100.0])
    def test_estremi_del_pattern_ammessi(self, x):
        """`0` e `100` sono i confini del ciclo, non valori fuori."""
        corpo = [[[x, 1], [100, -1]], 2.0, 2]
        assert normalize_read_direction({'points': corpo})['points'] is corpo


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

    def test_elemento_non_breakpoint(self):
        with pytest.raises(InvalidFieldValueError):
            normalize_read_direction([[0, 1], 'cycle'])
