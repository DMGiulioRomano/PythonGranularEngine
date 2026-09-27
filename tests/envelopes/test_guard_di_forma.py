"""
test_guard_di_forma.py

I guard di **forma** degli envelope vivono in `EnvelopeBuilder` e valgono per
ogni chiave (issue #211).

Fino a #211 esistevano solo per `grain.read_direction`, che li applicava al
proprio valore grezzo prima del builder: lo stesso corpo scritto sotto
`density` o `grain.duration` risaliva come `ValueError` nudo — fuori dalla
gerarchia `EngineError`, senza campo e senza stream_id — oppure si rendeva in
silenzio. Nessuno di quei guard sa qualcosa del verso di lettura: sono
vincoli della forma, e la forma e' del builder.

Il builder non conosce il nome YAML della chiave che sta costruendo: il campo
glielo passa chi lo conosce (`field=`). Senza, l'errore nomina la
sotto-posizione dentro l'envelope (`envelope.compact.n_reps`), che e' il
meglio che il builder possa dire da solo — e resta comunque un
`InvalidFieldValueError`, non un `ValueError` nudo.

Organizzazione:
1. BP group: arita'
2. Formato compatto: n_reps
3. Formato compatto: end_time
4. Formato compatto: il pattern
5. Formato compatto: la distribuzione temporale
6. Elemento non riconosciuto
7. Il campo di ripiego
"""

import pytest

from pge.envelopes.envelope_builder import EnvelopeBuilder
from pge.shared.exceptions import InvalidFieldValueError

CAMPO = 'density'


def _rifiuta(raw, field=CAMPO):
    """Il corpo deve cadere come InvalidFieldValueError; restituisce l'errore."""
    with pytest.raises(InvalidFieldValueError) as exc:
        EnvelopeBuilder.parse(raw, field=field)
    return exc.value


# =============================================================================
# 1. BP GROUP: ARITA'
# =============================================================================

class TestAritaDelGruppo:
    """Una zona con meno di 2 punti non ha segmenti interni."""

    @pytest.mark.parametrize("forma", ['diretta', 'in_lista'])
    def test_un_solo_punto_nomina_il_campo(self, forma):
        gruppo = [[[0, 1]], 'step']
        raw = gruppo if forma == 'diretta' else [gruppo, [1.0, 2]]

        err = _rifiuta(raw)

        assert err.field == CAMPO
        assert err.value == [[0, 1]]
        assert '2 punti' in err.hint

    def test_due_punti_restano_validi(self):
        assert EnvelopeBuilder.parse([[[0, 1], [1, 2]], 'step'], field=CAMPO)


# =============================================================================
# 2. FORMATO COMPATTO: N_REPS
# =============================================================================

class TestRipetizioni:
    """Il terzo elemento del compatto e' un intero >= 1."""

    @pytest.mark.parametrize("n_reps", [0, -3])
    @pytest.mark.parametrize("forma", ['diretta', 'in_lista'])
    def test_meno_di_un_ciclo(self, forma, n_reps):
        compatto = [[[0, 1], [100, 2]], 2.0, n_reps]
        raw = compatto if forma == 'diretta' else [[0, 1], compatto]

        err = _rifiuta(raw)

        assert err.field == CAMPO
        assert err.value == n_reps

    def test_booleano_rifiutato(self):
        """`isinstance(True, int)` e' vero, quindi `true` supera il
        riconoscimento della forma, e `True < 1` e' falso: senza un guard
        esplicito `range(True)` rende un ciclo, in silenzio. `true` non e'
        `1`, per la stessa politica per cui non lo e' in nessun altro punto."""
        err = _rifiuta([[[0, 1], [100, 2]], 2.0, True])

        assert err.value is True
        assert 'ripetizioni' in err.hint

    def test_un_ciclo_resta_valido(self):
        """Il guard e' `>= 1`, non `> 1`."""
        assert EnvelopeBuilder.parse([[[0, 1], [100, 2]], 2.0, 1], field=CAMPO)


# =============================================================================
# 3. FORMATO COMPATTO: END_TIME
# =============================================================================

class TestIstanteFinale:
    """Il secondo elemento del compatto e' l'istante ASSOLUTO in cui il blocco
    finisce, e deve superare quello in cui comincia: 0 nella forma diretta,
    l'ultimo breakpoint scritto prima del blocco in una lista mista."""

    def test_booleano_rifiutato(self):
        """Stessa coercizione `bool` -> `int` di `n_reps`: `true` passa il
        riconoscimento della forma e l'espansione lo userebbe come `1.0`."""
        err = _rifiuta([[[0, 1], [50, 2]], True, 2])

        assert err.field == CAMPO
        assert err.value is True

    @pytest.mark.parametrize("end_time", [0, -1.5])
    def test_non_positivo(self, end_time):
        err = _rifiuta([[[0, 1], [50, 2]], end_time, 2])

        assert err.field == CAMPO
        assert err.value == end_time

    def test_non_oltre_l_offset_accumulato(self):
        """In una lista mista il blocco comincia dall'ultimo breakpoint
        precedente: qui 0.5, e un end_time di 0.4 finirebbe prima di partire.
        E' l'unica condizione che solo il builder puo' decidere, perche' solo
        lui conosce l'offset: l'hint lo nomina."""
        err = _rifiuta([[0, 1], [0.5, 1], [[[0, 1], [100, 2]], 0.4, 2]])

        assert err.field == CAMPO
        assert err.value == 0.4
        assert '0.5' in err.hint

    @pytest.mark.parametrize("end_time", [float('inf'), float('nan')])
    def test_non_finito(self, end_time):
        """`.inf` e `.nan` sono numeri per Python ma non un istante. `nan`
        passerebbe il confronto con l'offset — ogni confronto con `nan` e'
        falso — e si espanderebbe in breakpoint `nan`; `inf` in cicli di
        durata infinita."""
        err = _rifiuta([[[0, 1], [50, 2]], end_time, 2])

        assert err.field == CAMPO
        assert err.value is end_time

    def test_positivo_resta_valido(self):
        assert EnvelopeBuilder.parse([[[0, 1], [50, 2]], 0.001, 2], field=CAMPO)


# =============================================================================
# 4. FORMATO COMPATTO: IL PATTERN
# =============================================================================

class TestPattern:
    """Il primo elemento del compatto e' il ciclo: una lista non vuota di
    punti piatti `[x%, y]` / `[x%, y, type]`, con la x che percorre il ciclo
    in avanti una volta sola."""

    def test_vuoto(self):
        err = _rifiuta([[], 2.0, 2])

        assert err.field == CAMPO
        assert err.value == []

    def test_macro_forma_dentro_il_pattern(self):
        """`is_compact_format` guarda solo la lunghezza dei punti (2 o 3), e un
        BP group e' lungo 2: passa quel filtro e l'espansione fa `x / 100.0`
        su una lista — un TypeError nudo. Il valore dice QUALE punto cade."""
        gruppo = [[[0, 1], [50, 2]], 'step']
        err = _rifiuta([[gruppo], 2.0, 2])

        assert err.field == CAMPO
        assert err.value == gruppo

    def test_x_booleana(self):
        err = _rifiuta([[[True, 1], [100, 2]], 2.0, 2])

        assert err.value == [True, 1]

    @pytest.mark.parametrize("x", [150, -10, 100.5])
    def test_x_fuori_da_zero_cento(self, x):
        """La x e' una percentuale del ciclo. Fuori da `[0, 100]` il ciclo
        sfonda i propri confini: con 150 il successivo comincia prima che
        questo sia finito, con -10 esce un breakpoint a tempo negativo. Oggi
        si rende in silenzio."""
        err = _rifiuta([[[0, 1], [x, 2]], 2.0, 2])

        assert err.field == CAMPO
        assert err.value == x

    def test_x_che_torna_indietro(self):
        """In range ma all'indietro: `[[100, 1], [0, 2]]` espande in tempi che
        si invertono, e l'envelope non rende il pattern scritto."""
        err = _rifiuta([[[100, 1], [0, 2]], 2.0, 2])

        assert err.field == CAMPO
        assert err.value == 0

    def test_x_ripetuta_resta_valida(self):
        """Una x ripetuta e' la discontinuita': il vincolo e' non-decrescente."""
        assert EnvelopeBuilder.parse(
            [[[0, 1], [50, 1], [50, 2], [100, 2]], 2.0, 2], field=CAMPO)

    @pytest.mark.parametrize("x", [0, 100, 0.0, 100.0])
    def test_estremi_ammessi(self, x):
        assert EnvelopeBuilder.parse([[[x, 1], [100, 2]], 2.0, 2], field=CAMPO)

    def test_interp_per_punto_lasciato_vuoto(self):
        """`[x, y, None]` e' un punto piatto con l'interp al default."""
        assert EnvelopeBuilder.parse(
            [[[0, 1], [50, 1, None], [100, 2]], 2.0, 2], field=CAMPO)


# =============================================================================
# 5. FORMATO COMPATTO: LA DISTRIBUZIONE TEMPORALE
# =============================================================================

class TestDistribuzioneTemporale:
    """Il quinto elemento del compatto: un nome del registro, o un dict col
    nome in `type` e i parametri della distribuzione.

    `is_compact_format` accetta in quella posizione qualunque `str` o `dict`.
    Cio' che non si costruisce falliva dentro `TimeDistributionFactory` con
    errori senza campo — e `{type: 5}` con un AttributeError."""

    PATTERN = [[0, 1], [100, 2]]

    def _compatto(self, spec):
        return [self.PATTERN, 2.0, 3, 'linear', spec]

    def test_nome_ignoto_elenca_quelli_validi(self):
        err = _rifiuta(self._compatto('banana'))

        assert err.field == CAMPO
        assert err.value == 'banana'
        assert 'geometric' in err.hint

    @pytest.mark.parametrize("spec", [{'type': 5}, {'type': None}])
    def test_nome_che_non_e_una_stringa(self, spec):
        err = _rifiuta(self._compatto(spec))

        assert err.field == CAMPO
        assert err.value == spec

    @pytest.mark.parametrize("spec", [
        {'type': 'geometric', 'ratio': -1},
        {'type': 'exponential', 'rate': 0},
        {'type': 'logarithmic', 'base': 1},
        {'type': 'geometric', 'banana': 2},
        {'type': 'power', 'exponent': 'due'},
    ])
    def test_parametri_che_non_si_costruiscono(self, spec):
        """I vincoli dei parametri li conosce il costruttore di ciascuna
        distribuzione: si valida costruendo, e qualunque sia il modo in cui il
        costruttore dice di no l'errore nomina il campo dell'envelope — non
        `rate` o `power.exponent`, che nello YAML non sono chiavi."""
        err = _rifiuta(self._compatto(spec))

        assert err.field == CAMPO
        assert err.value == spec

    def test_parametri_senza_type(self):
        """Senza `type` la distribuzione e' `linear`, che non prende
        parametri: l'hint lo dice, perche' e' l'errore meno leggibile."""
        err = _rifiuta(self._compatto({'ratio': 1.5}))

        assert 'type' in err.hint

    @pytest.mark.parametrize("spec", [
        None, 'linear', 'EXPONENTIAL', 'geo',
        {'type': 'geometric', 'ratio': 1.5},
        {'type': 'power', 'exponent': 2.0},
    ])
    def test_le_forme_valide_restano_valide(self, spec):
        assert EnvelopeBuilder.parse(self._compatto(spec), field=CAMPO)


# =============================================================================
# 6. ELEMENTO NON RICONOSCIUTO
# =============================================================================

class TestElementoNonRiconosciuto:
    """Un elemento di una lista che non e' nessuna delle forme note era
    l'ultimo ValueError nudo sollevato dal builder."""

    @pytest.mark.parametrize("elemento", [
        'cycle', [0], [0, 'a'], {'t': 'x', 'v': 1}, [[0, 1], 'marker'],
    ])
    def test_nomina_il_campo_e_l_elemento(self, elemento):
        err = _rifiuta([[0, 1], elemento, [1, 2]])

        assert err.field == CAMPO
        assert err.value == elemento


# =============================================================================
# 7. IL CAMPO DI RIPIEGO
# =============================================================================

class TestCampoDiRipiego:
    """Senza `field` il builder nomina la sotto-posizione dentro l'envelope:
    e' tutto cio' che sa da solo, e resta un InvalidFieldValueError."""

    @pytest.mark.parametrize("raw, campo", [
        ([[[0, 1]], 'step'], 'envelope.group.points'),
        ([[[0, 1], [1, 2]], 'banana'], 'envelope.group.interp'),
        ([[[0, 1], [100, 2]], 2.0, 0], 'envelope.compact.n_reps'),
        ([[[0, 1], [100, 2]], 0, 2], 'envelope.compact.end_time'),
        ([[], 2.0, 2], 'envelope.compact.pattern'),
        ([[[0, 1], [150, 2]], 2.0, 2], 'envelope.compact.pattern'),
        ([[[0, 1], [100, 2]], 2.0, 2, 'linear', 'banana'],
         'envelope.compact.time_dist'),
        ([[0, 1], 'cycle'], 'envelope.point'),
    ])
    def test_sotto_posizione(self, raw, campo):
        assert _rifiuta(raw, field=None).field == campo

    def test_il_campo_passato_vale_anche_per_l_interp_del_gruppo(self):
        """`envelope.group.interp` era il campo cablato di questo errore: col
        campo passato dall'alto nomina la chiave come tutti gli altri."""
        assert _rifiuta([[[0, 1], [1, 2]], 'banana']).field == CAMPO
