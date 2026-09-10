# tests/parameters/test_range_unit_definitions.py
"""
test_range_unit_definitions.py

Il vocabolario di `duration_range_unit` e il dominio della frazione (#267).

Un range relativo NON ha lo stesso dominio di uno assoluto: assoluto e' una
quantita' nell'unita' del parametro (secondi, dB, gradi), relativo e' una
frazione adimensionale. Che per `grain_duration` i due numeri coincidano oggi
(max_range 1.0 in entrambi) e' un caso, non un progetto — e i test qui sotto lo
misurano su un parametro dove i due domini divergono davvero.
"""

import pytest

from pge.parameters.parameter_definitions import (
    GRANULAR_PARAMETERS,
    RANGE_UNITS,
    RANGE_UNIT_ABSOLUTE,
    RANGE_UNIT_DEFAULT,
    RANGE_UNIT_RELATIVE,
    RELATIVE_RANGE_BOUNDS,
    get_parameter_definition,
    range_unit_is_relative,
    relative_range_bounds,
    validate_range_unit,
)
from pge.shared.exceptions import InvalidFieldValueError


class TestVocabolario:

    def test_le_due_grafie_ammesse(self):
        assert RANGE_UNITS == (RANGE_UNIT_ABSOLUTE, RANGE_UNIT_RELATIVE)

    def test_il_default_e_assoluto(self):
        """Retrocompatibilita': chi non scrive la chiave non cambia semantica."""
        assert RANGE_UNIT_DEFAULT == RANGE_UNIT_ABSOLUTE

    def test_una_grafia_valida_torna_normalizzata(self):
        assert validate_range_unit('relative') == RANGE_UNIT_RELATIVE

    def test_una_grafia_ignota_e_un_errore_di_campo(self):
        with pytest.raises(InvalidFieldValueError) as exc:
            validate_range_unit('relativo', field='grain.duration_range_unit')

        assert 'grain.duration_range_unit' in str(exc.value)

    def test_il_predicato_riconosce_solo_la_grafia_relativa(self):
        assert range_unit_is_relative(RANGE_UNIT_RELATIVE) is True
        assert range_unit_is_relative(RANGE_UNIT_ABSOLUTE) is False
        assert range_unit_is_relative(None) is False


class TestDominioDellaFrazione:

    def test_la_frazione_vive_in_zero_uno(self):
        """1.0 = ±50% con ancora `center`, +100% con ancora `min`."""
        assert RELATIVE_RANGE_BOUNDS == (0.0, 1.0)

    def test_sostituisce_il_dominio_assoluto_del_parametro(self):
        """Su `volume` i due domini divergono: 24 dB contro la frazione."""
        assoluto = GRANULAR_PARAMETERS['volume']
        relativo = relative_range_bounds(assoluto)

        assert assoluto.max_range == 24.0
        assert (relativo.min_range, relativo.max_range) == RELATIVE_RANGE_BOUNDS

    def test_non_tocca_nient_altro_dei_bounds(self):
        assoluto = GRANULAR_PARAMETERS['volume']
        relativo = relative_range_bounds(assoluto)

        assert relativo.min_val == assoluto.min_val
        assert relativo.max_val == assoluto.max_val
        assert relativo.default_jitter == assoluto.default_jitter
        assert relativo.variation_mode == assoluto.variation_mode

    def test_convive_col_minimo_dinamico_di_grain_duration(self):
        """Il pavimento di 1 campione non deve sparire sotto la sostituzione."""
        dinamico = get_parameter_definition('grain_duration', output_sr=48000)
        relativo = relative_range_bounds(dinamico)

        assert relativo.min_val == pytest.approx(1.0 / 48000)
        assert (relativo.min_range, relativo.max_range) == RELATIVE_RANGE_BOUNDS


# =============================================================================
# PARSER: dall'unita' al Parameter
# =============================================================================

class TestParserRangeUnit:
    """`GranularParser.parse_parameter(range_unit=...)` cabla i due effetti:
    il dominio contro cui la frazione e' validata, e la modalita' del
    Parameter costruito."""

    def _parser(self, **cfg):
        from pge.core.stream_config import StreamConfig, StreamContext
        from pge.parameters.parser import GranularParser

        ctx = StreamContext(stream_id='s1', onset=0.0, duration=4.0,
                            sample='x.wav', sample_dur_sec=10.0)
        return GranularParser(StreamConfig(context=ctx, **cfg))

    def test_senza_unita_resta_assoluto(self):
        p = self._parser().parse_parameter('grain_duration', 0.05, 0.01)

        assert p.get_value(0.0) == pytest.approx(0.05, abs=0.005)

    def test_relativo_produce_una_banda_frazionaria(self):
        from pge.shared.probability_gate import AlwaysGate

        p = self._parser().parse_parameter(
            'grain_duration', 0.5, 0.5, range_unit=RANGE_UNIT_RELATIVE)
        p.set_probability_gate(AlwaysGate())

        draws = [p.get_value(0.0) for _ in range(400)]

        # banda = 0.5 * 0.5 = 0.25, centrata su 0.5 -> 0.375 .. 0.625
        assert min(draws) >= 0.375 - 1e-9
        assert max(draws) <= 0.625 + 1e-9
        assert max(draws) - min(draws) > 0.2

    def test_una_frazione_fuori_dominio_e_un_errore_di_bounds(self):
        from pge.shared.exceptions import ParameterBoundError

        with pytest.raises(ParameterBoundError):
            self._parser().parse_parameter(
                'grain_duration', 0.05, 1.5, range_unit=RANGE_UNIT_RELATIVE)

    def test_il_dominio_relativo_non_e_quello_del_parametro(self):
        """`volume` ammette 24 dB assoluti ma solo 1.0 di frazione."""
        from pge.shared.exceptions import ParameterBoundError

        self._parser().parse_parameter('volume', 0.0, 12.0)   # assoluto: passa

        with pytest.raises(ParameterBoundError):
            self._parser().parse_parameter(
                'volume', 0.0, 12.0, range_unit=RANGE_UNIT_RELATIVE)

    def test_per_il_parser_none_resta_non_dichiarato(self):
        """La distinzione assente/vuota vive nell'orchestratore, non qui.

        Il parser riceve un valore, non una chiave: `None` e' la firma di ogni
        chiamante che l'unita' non la prevede nemmeno (create_pitch_parameter,
        il window controller), quindi qui non puo' essere un errore. Solo chi
        legge lo YAML sa se quella chiave c'era.
        """
        p = self._parser().parse_parameter(
            'grain_duration', 0.05, 0.01, range_unit=None)

        assert p.get_value(0.0) == pytest.approx(0.05, abs=0.005)

    def test_una_grafia_ignota_arriva_attribuita_allo_stream(self):
        with pytest.raises(InvalidFieldValueError) as exc:
            self._parser().parse_parameter(
                'grain_duration', 0.05, 0.5, range_unit='relativo')

        assert exc.value.stream_id == 's1'


# =============================================================================
# TETTO DELLA BANDA (range_anchor: min)
# =============================================================================

class TestTettoDellaBandaRelativa:
    """Con ancora `min` la banda arriva a `base * (1 + frazione)`, non a
    `base + frazione`: sommare una frazione a una durata sarebbe sommare due
    grandezze diverse, e il controllo al parse lascerebbe passare bande che
    poi il safety clamp schiaccia contro il tetto, un warning per grano."""

    def _parser(self, anchor):
        from pge.core.stream_config import StreamConfig, StreamContext
        from pge.parameters.parser import GranularParser

        ctx = StreamContext(stream_id='s1', onset=0.0, duration=4.0,
                            sample='x.wav', sample_dur_sec=10.0)
        return GranularParser(StreamConfig(context=ctx, range_anchor=anchor))

    def test_una_banda_che_sfora_il_massimo_e_un_errore(self):
        """8 s con frazione 0.5 arriva a 12 s: oltre il tetto di 10 s.

        La somma 8 + 0.5 non ci arriverebbe mai — e' il caso che il controllo
        additivo lascerebbe passare in silenzio."""
        from pge.shared.exceptions import ParameterBoundError

        with pytest.raises(ParameterBoundError) as exc:
            self._parser('min').parse_parameter(
                'grain_duration', 8.0, 0.5, range_unit=RANGE_UNIT_RELATIVE)

        assert '12' in str(exc.value)

    def test_una_banda_che_ci_sta_passa(self):
        self._parser('min').parse_parameter(
            'grain_duration', 4.0, 0.5, range_unit=RANGE_UNIT_RELATIVE)

    def test_col_picco_dell_envelope_di_base(self):
        from pge.shared.exceptions import ParameterBoundError

        with pytest.raises(ParameterBoundError):
            self._parser('min').parse_parameter(
                'grain_duration', [[0, 0.01], [4, 9.0]], 0.5,
                range_unit=RANGE_UNIT_RELATIVE)

    def test_sotto_ancora_center_il_controllo_non_scatta(self):
        """Storico: con `center` la banda arriva a meta' e la gestisce il clamp."""
        self._parser('center').parse_parameter(
            'grain_duration', 8.0, 0.5, range_unit=RANGE_UNIT_RELATIVE)

    def test_l_errore_nomina_la_formula_che_ha_applicato(self):
        """Il messaggio deve dire `base * (1 + range)`, non `base + range`.

        E' l'unico modo che ha il lettore di rifare il conto: chi ha scritto
        `8.0` e `0.5` e legge «base + range» ottiene 8.5 e non capisce da dove
        venga il 12 dell'errore. La formula e' la meta' utile del messaggio, e
        cambia con la modalita': in assoluto resta la somma.

        Si legge su `user_message()`, non su `str()`: `value_type` sta nel
        corpo strutturato, ed e' quello che la CLI stampa (`cli.py` -> `print(
        err.user_message())`). Un test su `str()` non vedrebbe la formula
        nemmeno quando c'e'.
        """
        from pge.shared.exceptions import ParameterBoundError

        with pytest.raises(ParameterBoundError) as rel:
            self._parser('min').parse_parameter(
                'grain_duration', 8.0, 0.5, range_unit=RANGE_UNIT_RELATIVE)
        assert 'base * (1 + range)' in rel.value.user_message()

        with pytest.raises(ParameterBoundError) as ass:
            self._parser('min').parse_parameter(
                'grain_duration', 9.5, 0.9, range_unit=RANGE_UNIT_ABSOLUTE)
        assert 'base + range' in ass.value.user_message()
        assert 'base * (1 + range)' not in ass.value.user_message()


# =============================================================================
# UNA GRAFIA SOLA PER «E' RELATIVO»
# =============================================================================

class TestUnaSolaGrafiaDelPredicato:
    """`range_unit_is_relative` deve restare l'unico modo di fare la domanda.

    I lettori sono tre e stanno in tre strati diversi — il pre-normalizzatore
    delle unita' (`core/stream.py`), l'orchestratore e il parser — e la
    docstring del predicato lo dichiara. Un `unit == RANGE_UNIT_RELATIVE`
    scritto a mano è una seconda copia della domanda: oggi risponde uguale, e
    il giorno che il vocabolario prendesse un alias (come `loop_unit`, dove
    `seconds` e `absolute` sono la stessa lettura) risponderebbe diverso in un
    lettore su tre, in silenzio.

    La guardia legge il sorgente come AST, non come testo: un confronto dentro
    una stringa o un commento non è un confronto.
    """

    _MODULI = (
        'pge/parameters/parser.py',
        'pge/parameters/parameter_orchestrator.py',
        'pge/core/stream.py',
    )

    def _confronti_col_letterale(self, path):
        import ast
        import pathlib

        src = pathlib.Path(__file__).resolve().parents[2] / 'src' / path
        albero = ast.parse(src.read_text(encoding='utf-8'))

        def nomina_il_letterale(nodo):
            return (isinstance(nodo, ast.Name)
                    and nodo.id == 'RANGE_UNIT_RELATIVE') or (
                    isinstance(nodo, ast.Attribute)
                    and nodo.attr == 'RANGE_UNIT_RELATIVE')

        trovati = []
        for nodo in ast.walk(albero):
            if not isinstance(nodo, ast.Compare):
                continue
            lati = [nodo.left, *nodo.comparators]
            if any(nomina_il_letterale(lato) for lato in lati):
                trovati.append(nodo.lineno)
        return trovati

    @pytest.mark.parametrize('modulo', _MODULI)
    def test_nessun_confronto_scritto_a_mano(self, modulo):
        righe = self._confronti_col_letterale(modulo)

        assert righe == [], (
            f"{modulo}: confronto diretto con RANGE_UNIT_RELATIVE alle righe "
            f"{righe}. Usa range_unit_is_relative(unit).")

    def test_la_guardia_vede_davvero_un_confronto(self):
        """La guardia misurata su se stessa: senza, direbbe sempre di sì."""
        import ast

        albero = ast.parse("x = unit == RANGE_UNIT_RELATIVE\n")
        compare = [n for n in ast.walk(albero) if isinstance(n, ast.Compare)]

        assert len(compare) == 1
        assert any(isinstance(l, ast.Name) and l.id == 'RANGE_UNIT_RELATIVE'
                   for l in [compare[0].left, *compare[0].comparators])
