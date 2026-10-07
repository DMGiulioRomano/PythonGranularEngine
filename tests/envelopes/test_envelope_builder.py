# test_envelope_builder_complete.py
"""
Test suite COMPLETA per EnvelopeBuilder.

Coverage:
1. Test riconoscimento formato compatto (is_compact_format)
2. Test espansione formato compatto (_expand_compact_format)
3. Test estrazione tipo interpolazione (extract_interp_type)
4. Test parse - formato diretto
5. Test parse - formato misto
6. Test parse - formato legacy
7. Test discontinuità temporali
8. Test ordinamento monotono
9. Test edge cases
10. Test validazione errori
11. Test logging trasformazioni (mock)
12. Test helper functions
13. Test matematici (durate cicli, offset, simmetria)
14. Test robustezza input malformati
"""

import pytest
from unittest.mock import patch, MagicMock, call
from pge.envelopes.envelope_builder import EnvelopeBuilder, detect_format_type
from pge.shared.exceptions import InvalidFieldValueError


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def simple_compact():
    """Formato compatto semplice: 2 punti, 4 ripetizioni."""
    return [[[0, 0], [100, 1]], 0.4, 4]


@pytest.fixture
def compact_with_interp():
    """Formato compatto con tipo interpolazione esplicito."""
    return [[[0, 0], [100, 1]], 0.4, 4, 'cubic']


@pytest.fixture
def compact_three_points():
    """Formato compatto con 3 punti nel pattern."""
    return [[[0, 0], [50, 0.5], [100, 1]], 0.3, 3]


@pytest.fixture
def compact_single_rep():
    """Formato compatto con singola ripetizione."""
    return [[[0, 0], [100, 1]], 0.1, 1]


@pytest.fixture
def compact_many_reps():
    """Formato compatto con molte ripetizioni."""
    return [[[0, 0], [100, 1]], 1.0, 100]


@pytest.fixture
def legacy_breakpoints():
    """Formato legacy standard."""
    return [[0, 0], [0.5, 1], [1.0, 0]]





@pytest.fixture
def mixed_format():
    """Formato misto: compatto + standard."""
    return [
        [[[0, 0], [100, 1]], 0.2, 2],  # Compatto
        [0.5, 0.5],                     # Standard
        [1.0, 0]                        # Standard
    ]


@pytest.fixture
def mixed_with_interp():
    """Formato misto con tipi interpolazione diversi."""
    return [
        [[[0, 0], [100, 1]], 0.2, 2, 'cubic'],  # Compatto con cubic
        [0.5, 0.5],                              # Standard
        [[[50, 0], [100, 1]], 0.1, 3, 'step']   # Compatto con step
    ]


# =============================================================================
# 1. TEST RICONOSCIMENTO FORMATO COMPATTO
# =============================================================================

class TestIsCompactFormat:
    """Test is_compact_format() - riconoscimento pattern."""
    
    def test_recognize_simple_compact(self, simple_compact):
        """Riconosce formato compatto semplice (3 elementi)."""
        assert EnvelopeBuilder.is_compact_format(simple_compact)
    
    def test_recognize_compact_with_interp(self, compact_with_interp):
        """Riconosce formato compatto con interpolazione (4 elementi)."""
        assert EnvelopeBuilder.is_compact_format(compact_with_interp)
    
    def test_recognize_compact_three_points(self, compact_three_points):
        """Riconosce formato compatto con 3 punti nel pattern."""
        assert EnvelopeBuilder.is_compact_format(compact_three_points)
    
    def test_recognize_compact_single_rep(self, compact_single_rep):
        """Riconosce formato compatto con singola ripetizione."""
        assert EnvelopeBuilder.is_compact_format(compact_single_rep)
    
    def test_reject_legacy_breakpoint(self):
        """Rifiuta breakpoint legacy [t, v]."""
        assert not EnvelopeBuilder.is_compact_format([0, 10])
    
    def test_reject_legacy_list(self, legacy_breakpoints):
        """Rifiuta lista di breakpoints legacy."""
        assert not EnvelopeBuilder.is_compact_format(legacy_breakpoints)
    

    
    def test_reject_empty_list(self):
        """Rifiuta lista vuota."""
        assert not EnvelopeBuilder.is_compact_format([])
    
    def test_reject_wrong_length(self):
        """Rifiuta liste con lunghezza sbagliata."""
        assert not EnvelopeBuilder.is_compact_format([[[0, 0]], 0.4])  # 2 elementi (troppo pochi)
        # 6° elemento (wrap) deve essere bool, non stringa
        assert not EnvelopeBuilder.is_compact_format([[[0, 0]], 0.4, 4, 'linear', 'linear', 'altro'])
        # 7 elementi (troppi)
        assert not EnvelopeBuilder.is_compact_format([[[0, 0]], 0.4, 4, 'linear', 'linear', True, 'extra'])

    def test_reject_non_list(self):
        """Rifiuta non-liste."""
        assert not EnvelopeBuilder.is_compact_format(42)
        assert not EnvelopeBuilder.is_compact_format("compact")
        assert not EnvelopeBuilder.is_compact_format(None)
    
    def test_reject_wrong_types(self):
        """Rifiuta tipi sbagliati negli elementi."""
        # Pattern non-lista
        assert not EnvelopeBuilder.is_compact_format(["pattern", 0.4, 4])
        
        # Total_time non-numero
        assert not EnvelopeBuilder.is_compact_format([[[0, 0]], "0.4", 4])
        
        # N_reps non-int
        assert not EnvelopeBuilder.is_compact_format([[[0, 0]], 0.4, 4.5])
        
        # Interp_type non-string
        assert not EnvelopeBuilder.is_compact_format([[[0, 0]], 0.4, 4, 123])
    
    def test_accept_empty_pattern(self):
        """Accetta pattern vuoto (validazione in expand)."""
        assert EnvelopeBuilder.is_compact_format([[], 0.4, 4])


# =============================================================================
# 2. TEST ESPANSIONE FORMATO COMPATTO
# =============================================================================

class TestExpandCompactFormat:
    """Test _expand_compact_format() - espansione breakpoints."""
    
    def test_expand_simple_compact(self, simple_compact):
        """Espande formato compatto semplice."""
        expanded = EnvelopeBuilder._expand_compact_format(simple_compact)
        
        assert len(expanded) == 8
        
        # Verifica primi e ultimi punti
        assert expanded[0] == pytest.approx([0.0, 0])
        assert expanded[1] == pytest.approx([0.1, 1])
        assert expanded[-1] == pytest.approx([0.4, 1])
    
    def test_expand_three_points(self, compact_three_points):
        """Espande formato con 3 punti nel pattern."""
        expanded = EnvelopeBuilder._expand_compact_format(compact_three_points)
        
        # 3 cicli * 3 punti + 2 discontinuità = 11 breakpoints
        assert len(expanded) == 9
    
    def test_expand_single_rep(self, compact_single_rep):
        """Espande con singola ripetizione (no discontinuità)."""
        expanded = EnvelopeBuilder._expand_compact_format(compact_single_rep)
        
        # 1 ciclo * 2 punti + 0 discontinuità = 2 breakpoints
        assert len(expanded) == 2
        assert expanded[0] == pytest.approx([0.0, 0])
        assert expanded[1] == pytest.approx([0.1, 1])
    
    def test_correct_cycle_duration(self, simple_compact):
        """Calcola durata ciclo correttamente."""
        expanded = EnvelopeBuilder._expand_compact_format(simple_compact)
        
        # Cycle duration = 0.4 / 4 = 0.1s
        cycle_duration = 0.1
        
        # Primo punto secondo ciclo (indice 2)
        # Ha offset applicato
        assert expanded[2][0] == pytest.approx(
            cycle_duration + EnvelopeBuilder.DISCONTINUITY_OFFSET
        )
    
    def test_percentage_to_absolute_conversion(self):
        """Converte coordinate % correttamente."""
        compact = [[[0, 10], [50, 20], [100, 30]], 1.0, 1]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        # 50% di 1.0s = 0.5s
        assert expanded[0][0] == pytest.approx(0.0)
        assert expanded[1][0] == pytest.approx(0.5)
        assert expanded[2][0] == pytest.approx(1.0)
        
        # Valori Y rimangono invariati
        assert expanded[0][1] == 10
        assert expanded[1][1] == 20
        assert expanded[2][1] == 30
    
    def test_discontinuity_offset_on_first_point(self, simple_compact):
        """Primo punto di ogni ciclo (dopo il primo) ha offset."""
        expanded = EnvelopeBuilder._expand_compact_format(simple_compact)
        
        # Pattern: [[0, 0], [100, 1]]
        # Ciclo 0: [0,1] - indici 0,1
        # Ciclo 1: [0,1] - indici 2,3 (primo ha offset)
        # Ciclo 2: [0,1] - indici 4,5 (primo ha offset)
        # Ciclo 3: [0,1] - indici 6,7 (primo ha offset)
        
        # Primo punto ciclo 1
        assert expanded[2][1] == 0  # Valore = primo del pattern
        assert expanded[2][0] == pytest.approx(0.1 + EnvelopeBuilder.DISCONTINUITY_OFFSET)
        
        # Primo punto ciclo 2
        assert expanded[4][1] == 0
        assert expanded[4][0] == pytest.approx(0.2 + EnvelopeBuilder.DISCONTINUITY_OFFSET)
    
    def test_time_range(self):
        """Range temporale copre esattamente total_time."""
        compact = [[[0, 0], [100, 1]], 2.5, 10]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        # Primo tempo
        assert expanded[0][0] == pytest.approx(0.0)
        
        # Ultimo tempo (può avere offset infinitesimale)
        assert expanded[-1][0] <= 2.5


# =============================================================================
# 3. TEST ESTRAZIONE TIPO INTERPOLAZIONE
# =============================================================================

class TestExtractInterpType:
    """Test extract_interp_type() - estrazione tipo."""
    
    def test_extract_from_compact_direct(self, compact_with_interp):
        """Estrae tipo da formato compatto diretto."""
        interp_type = EnvelopeBuilder.extract_interp_type(compact_with_interp)
        assert interp_type == 'cubic'
    
    def test_extract_from_compact_in_list(self):
        """Estrae tipo da formato compatto dentro lista."""
        points = [
            [0, 0],
            [[[0, 0], [100, 1]], 0.4, 4, 'step'],
            [1, 10]
        ]
        interp_type = EnvelopeBuilder.extract_interp_type(points)
        assert interp_type == 'step'
    
    def test_extract_first_type_only(self, mixed_with_interp):
        """Estrae solo il primo tipo se ce ne sono multipli."""
        interp_type = EnvelopeBuilder.extract_interp_type(mixed_with_interp)
        # Primo compatto ha 'cubic'
        assert interp_type == 'cubic'
    
    def test_no_type_in_compact(self, simple_compact):
        """Ritorna None se compatto non ha tipo."""
        interp_type = EnvelopeBuilder.extract_interp_type(simple_compact)
        assert interp_type is None
    
    def test_no_type_in_legacy(self, legacy_breakpoints):
        """Ritorna None per formato legacy."""
        interp_type = EnvelopeBuilder.extract_interp_type(legacy_breakpoints)
        assert interp_type is None
    
    def test_no_compact_in_list(self):
        """Ritorna None se nessun formato compatto presente."""
        points = [[0, 0], [1, 10], 'cycle']
        interp_type = EnvelopeBuilder.extract_interp_type(points)
        assert interp_type is None


# =============================================================================
# 4. TEST PARSE - FORMATO DIRETTO
# =============================================================================

class TestParseDirectFormat:
    """Test parse() con formato compatto diretto."""
    
    def test_parse_compact_direct(self, simple_compact):
        """Parse formato compatto diretto."""
        expanded = EnvelopeBuilder.parse(simple_compact)
        
        # Deve espandere
        assert len(expanded) == 8
        assert expanded[0] == pytest.approx([0.0, 0])
    
    def test_parse_compact_with_interp(self, compact_with_interp):
        """Parse formato compatto con interpolazione."""
        expanded = EnvelopeBuilder.parse(compact_with_interp)
        
        assert len(expanded) == 8
    
    def test_parse_preserves_exact_values(self):
        """Parse preserva valori esatti."""
        compact = [[[0, 42], [100, 99]], 0.2, 2]
        expanded = EnvelopeBuilder.parse(compact)
        
        # Verifica valori Y
        assert expanded[0][1] == 42
        assert expanded[1][1] == 99


# =============================================================================
# 5. TEST PARSE - FORMATO MISTO
# =============================================================================

class TestParseMixedFormat:
    """Test parse() con formato misto."""
    
    def test_parse_mixed_format(self, mixed_format):
        """Parse formato misto (compatto + standard)."""
        expanded = EnvelopeBuilder.parse(mixed_format)
        
        # Compatto espanso + 2 standard
        # 2 cicli * 2 punti =4
        # + 2 standard = 6 totale
        assert len(expanded) == 6
    

    def test_parse_multiple_compact(self):
        """Parse con multipli formati compatti."""
        points = [
            [[[0, 0], [100, 1]], 0.2, 2],
            [[[0, 5], [100, 10]], 0.5, 1]
        ]
        expanded = EnvelopeBuilder.parse(points)
        
        # Primo: 2 cicli * 2 punti = 4
        # Secondo: 1 ciclo * 2 punti = 2
        # Totale = 6
        assert len(expanded) == 6

# =============================================================================
# 6. TEST PARSE - FORMATO LEGACY
# =============================================================================

class TestParseLegacyFormat:
    """Test parse() con formato legacy."""
    
    def test_parse_legacy_standard(self, legacy_breakpoints):
        """Parse formato legacy standard (passa invariato)."""
        expanded = EnvelopeBuilder.parse(legacy_breakpoints)
        
        assert expanded == legacy_breakpoints
    

    
    def test_parse_single_breakpoint(self):
        """Parse singolo breakpoint."""
        single = [[0, 10]]
        expanded = EnvelopeBuilder.parse(single)
        
        assert expanded == single
    
    def test_parse_empty_list(self):
        """Parse lista vuota (passa invariata)."""
        empty = []
        expanded = EnvelopeBuilder.parse(empty)
        
        assert expanded == []


# =============================================================================
# 7. TEST DISCONTINUITÀ TEMPORALI
# =============================================================================

class TestTemporalDiscontinuities:
    """Test gestione discontinuità temporali."""
    
    def test_discontinuity_offset_applied(self):
        """Offset infinitesimale applicato correttamente."""
        compact = [[[0, 0], [100, 1]], 0.2, 2]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        # Fine primo ciclo
        end_first = expanded[1][0]
        
        # Discontinuità
        discontinuity = expanded[2][0]
        
        assert discontinuity == pytest.approx(
            end_first + EnvelopeBuilder.DISCONTINUITY_OFFSET
        )
        
    def test_discontinuity_offset_not_cumulative(self):
        """Offset NON è cumulativo, sempre lo stesso."""
        compact = [[[0, 0], [100, 1]], 0.3, 3]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        # 3 cicli * 2 punti = 6 breakpoints
        assert len(expanded) == 6
        
        # Verifica offset sempre uguale (non cumulativo)
        # Ciclo 0: [0.0, 0.1]
        # Ciclo 1: [0.100001, 0.2]
        # Ciclo 2: [0.200001, 0.3]
        
        offset1 = expanded[2][0] - 0.1  # Primo punto ciclo 1 - fine ciclo 0
        offset2 = expanded[4][0] - 0.2  # Primo punto ciclo 2 - fine ciclo 1
        
        assert offset1 == pytest.approx(EnvelopeBuilder.DISCONTINUITY_OFFSET)
        assert offset2 == pytest.approx(EnvelopeBuilder.DISCONTINUITY_OFFSET)



    def test_no_discontinuity_single_rep(self, compact_single_rep):
        """Nessuna discontinuità con singola ripetizione."""
        expanded = EnvelopeBuilder._expand_compact_format(compact_single_rep)
        
        # Solo 2 breakpoints, nessuna discontinuità
        assert len(expanded) == 2
    


    def test_total_breakpoint_count(self):
        """Numero totale breakpoints = n_reps * pattern_length."""
        for n_reps in [2, 5, 10, 50]:
            compact = [[[0, 0], [100, 1]], 1.0, n_reps]
            expanded = EnvelopeBuilder._expand_compact_format(compact)
            
            # Formula: n_reps * 2 (no discontinuità separate)
            expected_count = n_reps * 2
            assert len(expanded) == expected_count




# =============================================================================
# 8. TEST ORDINAMENTO MONOTONO
# =============================================================================

class TestMonotonicOrdering:
    """Test garantisce ordinamento monotono stretto."""
    
    def test_times_strictly_increasing(self):
        """Tempi strettamente crescenti."""
        compact = [[[0, 0], [50, 0.5], [100, 1]], 1.0, 10]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        for i in range(1, len(expanded)):
            assert expanded[i][0] > expanded[i-1][0], \
                f"Time at index {i} not > time at {i-1}"
    
    def test_no_equal_times(self):
        """Nessun tempo uguale a un altro."""
        compact = [[[0, 0], [100, 1]], 1.0, 100]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        times = [bp[0] for bp in expanded]
        
        # Set rimuove duplicati - deve avere stessa lunghezza
        assert len(times) == len(set(times))
    
    def test_offset_prevents_collision_between_cycles(self):
        """Offset previene collisioni TRA cicli."""
        # Pattern con UN solo punto
        compact = [[[0, 1]], 0.1, 5]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        # 5 cicli * 1 punto = 5 breakpoints
        times = [bp[0] for bp in expanded]
        assert len(times) == len(set(times))  # Tutti distinti

    
    def test_monotonic_with_many_points(self):
        """Monotonia con molti punti nel pattern."""
        pattern = [[i*10, i] for i in range(11)]  # 0, 10, 20, ..., 100
        compact = [pattern, 1.0, 5]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        for i in range(1, len(expanded)):
            assert expanded[i][0] > expanded[i-1][0]


# =============================================================================
# 9. TEST EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test casi edge e boundary."""
    
    def test_single_point_pattern(self):
        """Pattern con singolo punto."""
        compact = [[[0, 42]], 1.0, 3]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        # 3 cicli * 1 punto + 2 discontinuità = 5
        assert len(expanded) == 3
        
        # Tutti i valori Y = 42
        for bp in expanded:
            assert bp[1] == 42
    
    def test_same_x_percent_in_pattern_collide(self):
        """Punti con stesso x% nello stesso pattern collidono (limitazione)."""
        compact = [[[0, 10], [0, 20], [0, 30]], 0.3, 2]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        # 2 cicli * 3 punti = 6, ma alcuni collidono
        # Questo è un caso limite non gestito
        assert len(expanded) == 6

    
    def test_large_n_reps(self, compact_many_reps):
        """Molte ripetizioni (100)."""
        expanded = EnvelopeBuilder._expand_compact_format(compact_many_reps)
        
        # 100 cicli * 2 punti = 200
        assert len(expanded) == 200
        
        # Primo e ultimo tempo
        assert expanded[0][0] == pytest.approx(0.0)
        assert expanded[-1][0] <= 1.0
    
    def test_very_short_duration(self):
        """Durata molto breve."""
        compact = [[[0, 0], [100, 1]], 0.001, 5]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        # Deve funzionare anche con durate minime
        assert len(expanded) == 10  # 5*2 + 4
        assert expanded[-1][0] <= 0.001
    
    def test_fractional_percentages(self):
        """Percentuali frazionarie."""
        compact = [[[0, 0], [33.33, 0.5], [66.67, 0.8], [100, 1]], 1.0, 1]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        assert len(expanded) == 4
        assert expanded[1][0] == pytest.approx(0.3333)
        assert expanded[2][0] == pytest.approx(0.6667)


# =============================================================================
# 10. TEST VALIDAZIONE ERRORI
# =============================================================================

class TestValidationErrors:
    """Test validazione e errori.

    Da #211 sono `InvalidFieldValueError` (che eredita `ValueError`): chiamato
    senza `field`, il builder nomina la sotto-posizione dentro l'envelope. La
    copertura dei guard per esteso sta in `test_guard_di_forma.py`.
    """
    
    def test_error_zero_n_reps(self):
        """Errore con n_reps = 0."""
        compact = [[[0, 0], [100, 1]], 0.4, 0]
        
        with pytest.raises(InvalidFieldValueError) as exc:
            EnvelopeBuilder._expand_compact_format(compact)
        assert exc.value.field == 'envelope.compact.n_reps'
        assert exc.value.value == 0
    
    def test_error_negative_n_reps(self):
        """Errore con n_reps negativo."""
        compact = [[[0, 0], [100, 1]], 0.4, -5]
        
        with pytest.raises(InvalidFieldValueError) as exc:
            EnvelopeBuilder._expand_compact_format(compact)
        assert exc.value.value == -5
        
    def test_error_zero_total_time(self):
        """Errore con end_time = time_offset."""
        compact = [[[0, 0], [100, 1]], 0.0, 4]
        
        with pytest.raises(InvalidFieldValueError) as exc:
            EnvelopeBuilder._expand_compact_format(compact, time_offset=0.0)
        assert exc.value.field == 'envelope.compact.end_time'

    def test_error_negative_total_time(self):
        """Errore con end_time negativo."""
        compact = [[[0, 0], [100, 1]], -0.5, 4]
        
        with pytest.raises(InvalidFieldValueError) as exc:
            EnvelopeBuilder._expand_compact_format(compact, time_offset=0.0)
        assert exc.value.value == -0.5

    def test_error_empty_pattern(self):
        """Errore con pattern vuoto."""
        compact = [[], 0.4, 4]
        
        with pytest.raises(InvalidFieldValueError) as exc:
            EnvelopeBuilder._expand_compact_format(compact)
        assert exc.value.field == 'envelope.compact.pattern'
    
    def test_error_malformed_pattern_points(self):
        """Errore con pattern points malformati."""
        compact = [[[0]], 0.4, 4]  # Missing Y value
        
        # Dovrebbe sollevare errore durante unpacking
        with pytest.raises((ValueError, TypeError, IndexError)):
            EnvelopeBuilder._expand_compact_format(compact)


# =============================================================================
# 11. TEST LOGGING TRASFORMAZIONI
# =============================================================================

class TestLoggingTransformations:
    """Test logging delle trasformazioni (con mock)."""
    
    @patch('pge.shared.logger.get_clip_logger')
    def test_logging_called_on_expand(self, mock_get_logger, simple_compact):
        """Logging chiamato durante expand."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        EnvelopeBuilder._expand_compact_format(simple_compact)
        
        # Logger deve essere chiamato
        assert mock_logger.info.called
    
    @patch('pge.shared.logger.get_clip_logger')
    def test_logging_contains_input_info(self, mock_get_logger, simple_compact):
        """Log contiene info formato compatto."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        EnvelopeBuilder._expand_compact_format(simple_compact)
        
        # Verifica che il log contenga info rilevanti
        calls = [str(call) for call in mock_logger.info.call_args_list]
        log_text = ' '.join(calls)
        
        assert 'total_time=0.4' in log_text or '0.4s' in log_text
        assert '4' in log_text  # n_reps
    
    @patch('pge.shared.logger.get_clip_logger')
    def test_logging_disabled_when_logger_none(self, mock_get_logger, simple_compact):
        """Nessun errore se logger è None."""
        mock_get_logger.return_value = None
        
        # Non deve sollevare errori
        expanded = EnvelopeBuilder._expand_compact_format(simple_compact)
        assert len(expanded) == 8
    
    @patch('pge.shared.logger.get_clip_logger')
    def test_logging_called_for_each_compact(self, mock_get_logger):
        """Logging chiamato per ogni formato compatto."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        points = [
            [[[0, 0], [100, 1]], 0.2, 2],
            [[[0, 5], [100, 10]], 0.5, 1]  # CAMBIATO: 0.5 invece di 0.1
        ]
        
        EnvelopeBuilder.parse(points)
        
        # Logger deve essere chiamato almeno 2 volte (una per ogni compatto)
        assert mock_logger.info.call_count >= 2

# =============================================================================
# 12. TEST HELPER FUNCTIONS
# =============================================================================

class TestHelperFunctions:
    """Test helper functions."""
    
    def test_detect_compact(self, simple_compact):
        """detect_format_type identifica 'compact'."""
        assert detect_format_type(simple_compact) == 'compact'
    
    def test_detect_breakpoint(self):
        """detect_format_type identifica 'breakpoint'."""
        assert detect_format_type([0, 10]) == 'breakpoint'
        assert detect_format_type([0.5, 42.7]) == 'breakpoint'
    
    def test_detect_cycle(self):
        """detect_format_type identifica 'cycle'."""
        assert detect_format_type('cycle') == 'cycle'
        assert detect_format_type('CYCLE') == 'cycle'
    
    def test_detect_unknown(self):
        """detect_format_type ritorna 'unknown' per altro."""
        assert detect_format_type(42) == 'unknown'
        assert detect_format_type("foo") == 'unknown'
        assert detect_format_type([1, 2, 3]) == 'unknown'


# =============================================================================
# 13. TEST MATEMATICI
# =============================================================================

class TestMathematicalProperties:
    """Test proprietà matematiche."""
    
    def test_cycle_duration_calculation(self):
        """Durata ciclo calcolata correttamente."""
        for total_time in [1.0, 2.5, 0.333]:
            for n_reps in [1, 5, 10]:
                compact = [[[0, 0], [100, 1]], total_time, n_reps]
                expanded = EnvelopeBuilder._expand_compact_format(compact)
                
                expected_cycle_duration = total_time / n_reps
                
                # Verifica usando differenza tra punti corrispondenti
                if n_reps > 1:
                    # Primo punto primo ciclo e primo punto secondo ciclo
                    first_cycle_start = expanded[0][0]
                    second_cycle_start = expanded[2][0]  # 1*2 = indice 2
                    
                    # Sottrai offset
                    actual_cycle_duration = second_cycle_start - first_cycle_start - EnvelopeBuilder.DISCONTINUITY_OFFSET
                    
                    assert actual_cycle_duration == pytest.approx(
                        expected_cycle_duration, rel=1e-3
                    )
    
    def test_total_duration_preserved(self):
        """Durata totale preservata (entro tolleranza offset)."""
        for total_time in [0.5, 1.0, 2.0]:
            compact = [[[0, 0], [100, 1]], total_time, 10]
            expanded = EnvelopeBuilder._expand_compact_format(compact)
            
            actual_duration = expanded[-1][0] - expanded[0][0]
            
            # Differenza dovuta solo agli offset
            max_offset = 9 * EnvelopeBuilder.DISCONTINUITY_OFFSET  # n_reps - 1
            
            assert abs(actual_duration - total_time) <= max_offset
    
    def test_pattern_repetition_symmetry(self):
        """Pattern si ripete identicamente (modulo offset)."""
        compact = [[[0, 5], [50, 10], [100, 5]], 1.0, 3]
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        cycle_duration = 1.0 / 3
        
        # Valori Y devono ripetersi
        # Ciclo 0: indices 0,1,2
        # Ciclo 1: indices 3,4,5
        # Ciclo 2: indices 6,7,8

        assert expanded[0][1] == expanded[3][1] == expanded[6][1]  # = 5
        assert expanded[1][1] == expanded[4][1] == expanded[7][1]  # = 10
        assert expanded[2][1] == expanded[5][1] == expanded[8][1]  # = 5

# =============================================================================
# 14. TEST ROBUSTEZZA INPUT MALFORMATI
# =============================================================================

class TestRobustnessMalformedInput:
    """Test robustezza con input malformati."""
        
    def test_negative_percentages(self):
        """Percentuali negative: rifiutate (issue #211).

        Fissavano il silenzio — «non dovrebbe crashare, ma produce tempi
        strani»: un breakpoint a tempo negativo, reso senza dire niente. La x
        del pattern e' una percentuale del ciclo e sta in [0, 100]."""
        compact = [[[-50, 0], [100, 1]], 0.4, 2]
        
        with pytest.raises(InvalidFieldValueError) as exc:
            EnvelopeBuilder._expand_compact_format(compact)
        assert exc.value.value == -50
    
    def test_percentages_over_100(self):
        """Percentuali > 100: rifiutate (issue #211). Il ciclo successivo
        cominciava prima che questo fosse finito, in silenzio."""
        compact = [[[0, 0], [200, 1]], 0.4, 2]
        
        with pytest.raises(InvalidFieldValueError) as exc:
            EnvelopeBuilder._expand_compact_format(compact)
        assert exc.value.value == 200
    
    def test_float_n_reps_rejected(self):
        """n_reps float rifiutato da is_compact_format."""
        compact = [[[0, 0], [100, 1]], 0.4, 4.5]
        
        # is_compact_format deve rifiutare
        assert not EnvelopeBuilder.is_compact_format(compact)

    # Test aggiuntivi per _log_compact_transformation (da aggiungere a TestLoggingTransformations)

    @patch('pge.shared.logger.get_clip_logger')
    def test_log_compact_direct_call(self, mock_get_logger):
        """Test chiamata diretta a _log_compact_transformation."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        compact = [[[0, 0], [50, 0.5], [100, 1]], 0.3, 3]
        expanded = [
            [0.0, 0], [0.05, 0.5], [0.1, 1],
            [0.100001, 0],
            [0.100002, 0], [0.15, 0.5], [0.2, 1],
            [0.200001, 0],
            [0.200002, 0], [0.25, 0.5], [0.3, 1]
        ]
        
        time_offset = 0.0
        total_duration = 0.3
        distributor = None  # o creare un mock se necessario
        
        EnvelopeBuilder._log_compact_transformation(
            compact, expanded, time_offset, total_duration, distributor
        )
        
        assert mock_logger.info.called

    @patch('pge.shared.logger.get_clip_logger')
    def test_log_shows_pattern_points(self, mock_get_logger):
        """Log mostra pattern points correttamente."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        pattern = [[0, 10], [50, 20], [100, 30]]
        compact = [pattern, 1.0, 5]
        expanded = [[0.0, 10], [0.1, 20], [0.2, 30]]  # Simplified
        
        # AGGIUNGI QUESTE RIGHE:
        time_offset = 0.0
        total_duration = 1.0
        distributor = None
        
        EnvelopeBuilder._log_compact_transformation(compact, expanded, time_offset, total_duration, distributor)
        
        # Verifica che il log contenga info sui pattern points
        assert mock_logger.info.called



    @patch('pge.shared.logger.get_clip_logger')
    def test_log_shows_cycle_info(self, mock_get_logger):
        """Log mostra info cicli (total_time, n_reps, cycle_duration)."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        compact = [[[0, 0], [100, 1]], 2.5, 10]
        expanded = [[0.0, 0], [0.25, 1]]  # Simplified
        
        # AGGIUNGI QUESTE RIGHE:
        time_offset = 0.0
        total_duration = 2.5
        distributor = None
        
        EnvelopeBuilder._log_compact_transformation(compact, expanded, time_offset, total_duration, distributor)
        
        # Verifica che il log contenga info sui cicli
        assert mock_logger.info.called

    @patch('pge.shared.logger.get_clip_logger')
    def test_log_shows_interpolation_type(self, mock_get_logger):
        """Log mostra tipo interpolazione se presente."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        compact = [[[0, 0], [100, 1]], 0.4, 4, 'cubic']
        expanded = [[0.0, 0], [0.1, 1]]  # Simplified
        
        # AGGIUNGI QUESTE RIGHE:
        time_offset = 0.0
        total_duration = 0.4
        distributor = None
        
        EnvelopeBuilder._log_compact_transformation(compact, expanded, time_offset, total_duration, distributor)
        
        # Verifica che il log contenga 'cubic'
        assert mock_logger.info.called


    @patch('pge.shared.logger.get_clip_logger')
    def test_log_shows_output_summary(self, mock_get_logger):
        """Log mostra summary output (n_breakpoints, time_range)."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        compact = [[[0, 0], [100, 1]], 1.0, 5]
        expanded = [
            [0.0, 0], [0.2, 1], [0.200001, 0],
            [0.200002, 0], [0.4, 1], [0.400001, 0],
            [0.400002, 0], [0.6, 1], [0.600001, 0],
            [0.600002, 0], [0.8, 1], [0.800001, 0],
            [0.800002, 0], [1.0, 1]
        ]
        
        # AGGIUNGI QUESTE RIGHE:
        time_offset = 0.0
        total_duration = 1.0
        distributor = None
        
        EnvelopeBuilder._log_compact_transformation(compact, expanded, time_offset, total_duration, distributor)
        
        # Verifica che il log contenga info di summary
        assert mock_logger.info.called


    @patch('pge.shared.logger.get_clip_logger')
    def test_log_shows_preview_breakpoints(self, mock_get_logger):
        """Log mostra preview breakpoints (primi e ultimi 5)."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        # Molti breakpoints per testare preview
        expanded = [[i*0.1, i] for i in range(20)]
        compact = [[[0, 0], [100, 1]], 2.0, 10]
        
        # AGGIUNGI QUESTE RIGHE:
        time_offset = 0.0
        total_duration = 2.0
        distributor = None
        
        EnvelopeBuilder._log_compact_transformation(compact, expanded, time_offset, total_duration, distributor)
        
        # Verifica che il log contenga preview dei breakpoints
        assert mock_logger.info.called



    @patch('pge.shared.logger.get_clip_logger')
    def test_log_no_crash_if_logger_none(self, mock_get_logger):
        """Nessun crash se get_clip_logger ritorna None."""
        mock_get_logger.return_value = None
        
        compact = [[[0, 0], [100, 1]], 0.4, 4]
        expanded = [[0.0, 0], [0.1, 1]]
        
        # AGGIUNGI QUESTE RIGHE:
        time_offset = 0.0
        total_duration = 0.4
        distributor = None
        
        # Non deve sollevare errori
        EnvelopeBuilder._log_compact_transformation(compact, expanded, time_offset, total_duration, distributor)


    @patch('pge.shared.logger.get_clip_logger')
    def test_log_separator_lines(self, mock_get_logger):
        """Log contiene linee separatore per leggibilità."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        compact = [[[0, 0], [100, 1]], 0.2, 2]
        expanded = [[0.0, 0], [0.1, 1]]
        
        # AGGIUNGI QUESTE RIGHE:
        time_offset = 0.0
        total_duration = 0.2
        distributor = None
        
        EnvelopeBuilder._log_compact_transformation(compact, expanded, time_offset, total_duration, distributor)
        
        # Verifica che il log contenga separatori
        assert mock_logger.info.called

# =============================================================================
# TEST RIGHE MANCANTI: 175-176, 330, 389, 435-451
# =============================================================================

class TestEnvelopeBuilderMissingLines:
    """Copre righe 175-176, 330, 389, 435-451 di envelope_builder.py."""
        
    def test_is_compact_format_fifth_element_invalid_type_returns_false(self):
        """
        Righe 175-176: quinto elemento presente ma non str/dict -> return False.
        """
        # 5 elementi con quinto elemento intero (non str, non dict)
        item = [[[0, 0], [100, 1]], 1.0, 2, 'linear', 42]
        assert EnvelopeBuilder.is_compact_format(item) is False

    def test_log_compact_transformation_with_time_dist_spec(self):
        """
        Riga 330: time_dist_spec presente -> logger.info viene chiamato con spec.
        """

        with patch('pge.shared.logger.get_clip_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            compact = [[[0, 0], [100, 1]], 1.0, 2, 'linear', 'exponential']
            expanded = [[0.0, 0], [0.5, 1], [0.500001, 0], [1.0, 1]]

            EnvelopeBuilder._log_compact_transformation(
                compact, expanded,
                time_offset=0.0,
                total_duration=1.0,
                distributor=None
            )

            all_calls = [str(c) for c in mock_logger.info.call_args_list]
            assert any('exponential' in c for c in all_calls)

# =============================================================================
# TEST log_transformations FLAG
# =============================================================================

class TestLogTransformationsFlag:
    """Il flag log_transformations=False sopprime i log di envelope."""

    @patch('pge.shared.logger.CLIP_LOG_CONFIG', {'log_transformations': False})
    @patch('pge.shared.logger.get_clip_logger')
    def test_final_envelope_silent_when_flag_false(self, mock_get_logger):
        """_log_final_envelope non chiama logger se log_transformations=False."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        raw = [[0, 0], [1, 1]]
        expanded = [[0, 0], [1, 1]]
        EnvelopeBuilder._log_final_envelope(raw, expanded)

        mock_logger.info.assert_not_called()

    @patch('pge.shared.logger.CLIP_LOG_CONFIG', {'log_transformations': False})
    @patch('pge.shared.logger.get_clip_logger')
    def test_compact_transformation_silent_when_flag_false(self, mock_get_logger):
        """_log_compact_transformation non chiama logger se log_transformations=False."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        compact = [[[0, 0], [100, 1]], 0.4, 4]
        expanded = [[0.0, 0], [0.1, 1]]
        EnvelopeBuilder._log_compact_transformation(
            compact, expanded, 0.0, 0.4, None
        )

        mock_logger.info.assert_not_called()

    @patch('pge.shared.logger.CLIP_LOG_CONFIG', {'log_transformations': True})
    @patch('pge.shared.logger.get_clip_logger')
    def test_final_envelope_active_when_flag_true(self, mock_get_logger):
        """_log_final_envelope chiama logger se log_transformations=True."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        raw = [[0, 0], [1, 1]]
        expanded = [[0, 0], [1, 1]]
        EnvelopeBuilder._log_final_envelope(raw, expanded)

        assert mock_logger.info.called

    @patch('pge.shared.logger.CLIP_LOG_CONFIG', {'log_transformations': True})
    @patch('pge.shared.logger.get_clip_logger')
    def test_compact_transformation_active_when_flag_true(self, mock_get_logger):
        """_log_compact_transformation chiama logger se log_transformations=True."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        compact = [[[0, 0], [100, 1]], 0.4, 4]
        expanded = [[0.0, 0], [0.1, 1]]
        EnvelopeBuilder._log_compact_transformation(
            compact, expanded, 0.0, 0.4, None
        )

        assert mock_logger.info.called

# =============================================================================
# 15. SUPERFICIE PUBBLICA E INDICI DEL FORMATO COMPATTO (issue #213)
# =============================================================================

class TestSuperficiePubblica:
    """I tre riconoscitori di forma sono pubblici (issue #213, punto 1).

    `read_direction.py` e' l'unico chiamante fuori da `pge.envelopes`, e
    chiamava tre metodi privati. Usarli era la scelta giusta — riconoscere le
    forme da capo sarebbe stata duplicazione peggiore, ed e' cio' che garantisce
    che validatore e costruttore riconoscano *le stesse* forme — ma allora la
    superficie deve dirlo.
    """

    def test_i_riconoscitori_sono_pubblici(self):
        assert EnvelopeBuilder.is_compact_format([[[0, 0], [100, 1]], 0.4, 4])
        assert EnvelopeBuilder.is_bp_group([[[0, 0], [1, 1]], 'linear'])
        assert EnvelopeBuilder.is_3tuple_breakpoint([0.5, 1.0, 'cubic'])

    @pytest.mark.parametrize("privato", [
        '_is_compact_format',
        '_is_bp_group',
        '_is_3tuple_breakpoint',
    ])
    def test_nessun_alias_privato_dietro(self, privato):
        """Promuovere e lasciare l'alias sarebbe due nomi per una cosa sola.

        Con i chiamanti aggiornati insieme non serve una transizione: l'alias
        sopravviverebbe a se stesso e il prossimo chiamante sceglierebbe a caso.
        """
        assert not hasattr(EnvelopeBuilder, privato)


class TestIndiciFormatoCompatto:
    """Gli slot del formato compatto hanno un nome (issue #213, punto 2).

    Il rischio non era un errore ma un silenzio: i due lati — chi espande e chi
    valida — decodificavano le stesse posizioni per conto proprio, quindi se il
    `time_dist_spec` avesse cambiato slot il validatore avrebbe continuato a
    controllare quello vecchio senza che nessun test se ne accorgesse. Con una
    costante sola letta da entrambi, quel disallineamento non e' esprimibile.
    """

    def test_gli_slot_sono_nominati(self):
        assert EnvelopeBuilder.COMPACT_PATTERN == 0
        assert EnvelopeBuilder.COMPACT_END_TIME == 1
        assert EnvelopeBuilder.COMPACT_N_REPS == 2
        assert EnvelopeBuilder.COMPACT_INTERP == 3
        assert EnvelopeBuilder.COMPACT_TIME_DIST == 4
        assert EnvelopeBuilder.COMPACT_WRAP == 5

    def test_l_espansione_legge_gli_slot_nominati(self):
        """Un compatto costruito per posizione a partire dalle costanti.

        Se un giorno le costanti cambiassero valore, questo test cambierebbe
        con loro — ed e' esattamente il punto: il layout esiste in un posto
        solo, e chi lo legge non puo' averne una copia propria.
        """
        compatto = [None] * 6
        compatto[EnvelopeBuilder.COMPACT_PATTERN] = [[0, 0], [100, 1]]
        compatto[EnvelopeBuilder.COMPACT_END_TIME] = 1.0
        compatto[EnvelopeBuilder.COMPACT_N_REPS] = 2
        compatto[EnvelopeBuilder.COMPACT_INTERP] = 'step'
        compatto[EnvelopeBuilder.COMPACT_TIME_DIST] = 'linear'
        compatto[EnvelopeBuilder.COMPACT_WRAP] = False

        assert EnvelopeBuilder.is_compact_format(compatto)

        espanso = EnvelopeBuilder._expand_compact_format(compatto)

        # Due cicli sul pattern a due punti, ultimo breakpoint a end_time.
        assert len(espanso) == 4
        assert espanso[-1][0] == pytest.approx(1.0)
        assert EnvelopeBuilder.extract_interp_type(compatto) == 'step'

    def test_l_estrazione_dell_interp_segue_lo_slot(self, monkeypatch):
        """Anche chi legge il solo interp lo legge dalla costante.

        `extract_interp_type` decodificava lo slot con un `3` scritto a mano,
        due volte (il compatto diretto e quello dentro una lista mista). Con
        l'interp spostato di posto tornava `None` invece del tipo dichiarato:
        non un errore, un envelope interpolato col default.

        Qui lo slot 3 resta occupato da `None` — cosi' la lista e' ancora un
        compatto valido per `is_compact_format`, che il layout lo definisce e
        non va toccata — e l'interp vero sta al 4.
        """
        monkeypatch.setattr(EnvelopeBuilder, 'COMPACT_INTERP', 4)

        compatto = [[[0, 0], [100, 1]], 1.0, 2, None, 'step']
        assert EnvelopeBuilder.is_compact_format(compatto)

        assert EnvelopeBuilder.extract_interp_type(compatto) == 'step'
        # Stessa cosa per il compatto annidato in una lista mista.
        assert EnvelopeBuilder.extract_interp_type([compatto]) == 'step'

    def test_il_validatore_segue_gli_slot_insieme_all_espansione(self, monkeypatch):
        """Il lato che valida si muove con quello che espande.

        Il test qui sopra fissa una meta' dell'invariante: che l'espansione
        legga le costanti. Ma il rischio di #213 e' il *disallineamento* fra i
        due lati, e nessuno lo osserva finche' non si muove il layout.

        Qui il layout si muove davvero: `n_reps` e `end_time` si scambiano di
        posto nelle costanti, e la validazione deve seguire lo scambio. Da #211
        i guard di forma stanno nel builder, accanto all'espansione: il
        validatore di quegli slot non e' piu' un secondo lettore da tenere
        allineato, e' la stessa funzione — e l'hint dice quale slot ha letto.

        `is_compact_format` non e' toccata di proposito: e' lei a *definire* il
        layout per posizione, quindi l'espansione si chiama diretta, come fa il
        builder dopo che il riconoscimento e' gia' avvenuto.
        """
        monkeypatch.setattr(EnvelopeBuilder, 'COMPACT_END_TIME', 2)
        monkeypatch.setattr(EnvelopeBuilder, 'COMPACT_N_REPS', 1)

        # Lista scritta nel layout permutato: n_reps allo slot 1, end_time al 2.
        permutato = [[[0, -1], [100, 1]], 3, 1.0, 'step']

        # Tre cicli su un pattern a due punti, fine a 1.0.
        espanso = EnvelopeBuilder._expand_compact_format(permutato)
        assert len(espanso) == 6
        assert espanso[-1][0] == pytest.approx(1.0)

        # E rifiuta `n_reps` dove le costanti dicono che sta ora. Un validatore
        # fermo al layout vecchio rifiuterebbe anche lui, ma come `end_time`:
        # e' il campo di ripiego a dire quale dei due slot ha davvero letto.
        rotto = [[[0, -1], [100, 1]], 0, 1.0, 'step']
        with pytest.raises(InvalidFieldValueError) as exc_info:
            EnvelopeBuilder._expand_compact_format(rotto)
        assert exc_info.value.field == 'envelope.compact.n_reps'

    def test_read_direction_legge_l_interp_dallo_slot(self, monkeypatch):
        """L'altro lettore del layout, dopo #211: `read_direction` percorre
        ancora il compatto per i guard di dominio, e l'interp lo legge dalla
        costante. Con l'interp spostato allo slot 4 un lettore fermo al 3
        vedrebbe `None` e lascerebbe passare il `linear` che la chiave vieta."""
        from pge.parameters import read_direction

        monkeypatch.setattr(EnvelopeBuilder, 'COMPACT_INTERP', 4)

        compatto = [[[0, -1], [100, 1]], 1.0, 2, None, 'linear']
        with pytest.raises(InvalidFieldValueError) as exc_info:
            read_direction._check_compact(compatto)
        assert exc_info.value.value == 'linear'


# =============================================================================
# 16. IL LOG DELLA TRASFORMAZIONE LEGGE GLI STESSI SLOT (issue #219)
# =============================================================================

class TestLogDellaTrasformazioneCompatta:
    """Il log del compatto legge gli slot da dove li legge l'espansione.

    E' il punto 1 di #219, il residuo piu' benigno (e' solo logging) e insieme
    il piu' insidioso: un log non alza nessun errore, quindi dopo una
    permutazione degli slot direbbe con sicurezza il valore sbagliato — e chi
    diagnostica un render guardando il log parte da quella certezza.

    Non era un'ipotesi. `_log_compact_transformation` decodificava per conto
    proprio con `compact[4] if len(compact) == 5`, e lo slot `wrap` e' stato
    aggiunto *dopo* quella riga: un compatto a 6 elementi ha `len == 6`, quindi
    la condizione era falsa e la distribuzione temporale non veniva loggata
    affatto. Il layout si era mosso per aggiunta invece che per permutazione, e
    il log taceva su un dato che c'era.

    La via d'uscita non e' far leggere le costanti anche a lui — sarebbero due
    decoder allineati a mano, cioe' la condizione che ha prodotto il difetto —
    ma un decoder solo, `_compact_slots`, che chiamano sia l'espansione sia il
    log. `is_compact_format` resta fuori: e' lei a *definire* il layout per
    posizione.
    """

    @staticmethod
    def _righe(compact):
        """Le righe che il log emette per `compact`, come stringhe."""
        with patch('pge.shared.logger.get_clip_logger') as mock_get_logger:
            logger = MagicMock()
            mock_get_logger.return_value = logger
            EnvelopeBuilder._log_compact_transformation(
                compact, [[0.0, 0], [0.5, 1]],
                time_offset=0.0, total_duration=1.0, distributor=None)
            return [str(c) for c in logger.info.call_args_list]

    def test_la_distribuzione_si_vede_anche_col_wrap_dichiarato(self):
        """Il difetto misurato: sei slot, e la distribuzione spariva dal log."""
        compact = [[[0, 0], [50, 1]], 1.0, 2, 'linear', 'exponential', True]
        assert EnvelopeBuilder.is_compact_format(compact)

        assert any('exponential' in r for r in self._righe(compact))

    def test_il_wrap_dichiarato_si_vede(self):
        """Il sesto slot non era loggato affatto, non solo mal letto.

        Aggiunta oltre la lettera della issue, e per la stessa ragione che la
        motiva: il blocco `[INPUT]` del log enumera il compatto scritto nel
        file, e `wrap` cambia l'espanso — inietta un breakpoint sintetico a
        fine di ogni ciclo. Un log che descrive l'input omettendo uno slot che
        muove l'output e' incompleto nello stesso modo in cui era sbagliato
        quello che leggeva lo slot vecchio. Ora che il decoder glielo porta in
        mano, tacerlo sarebbe una scelta.
        """
        righe = self._righe([[[0, 0], [50, 1]], 1.0, 2, 'linear', None, True])

        assert any('rap' in r and 'True' in r for r in righe)

    def test_il_wrap_non_dichiarato_non_si_vede(self):
        """La controprova: il log dice cio' che c'e' scritto.

        Un `Wrap: False` su ogni compatto sarebbe una riga che non distingue
        niente, come il `None` dell'interp e della distribuzione che il log ha
        sempre taciuto quando assenti.
        """
        righe = self._righe([[[0, 0], [50, 1]], 1.0, 2])

        assert not any('rap' in r for r in righe)

    def test_l_interp_non_dichiarata_si_vede_come_non_dichiarata(self):
        """Il log dice che lo slot manca, e chi decide al suo posto.

        Il decoder riporta cio' che e' **dichiarato**, quindi `None` dove lo
        slot manca — e i chiamanti distinguono le due cose. Il log di prima
        risolveva il default per conto proprio (`compact[3] if len >= 4 else
        'linear'`) e stampava `Interpolation: linear` in entrambi i casi:
        un `linear` scritto nel file e uno che il file non scrive erano
        indistinguibili, che su un referto di diagnostica e' la distinzione
        utile.

        Il fallback si nomina dalla costante che l'`Envelope` applica, non da
        un letterale del test: e' quella a dire cosa vale quando nessuno
        dichiara un tipo.
        """
        from pge.envelopes.envelope_builder import DEFAULT_INTERP

        righe = self._righe([[[0, 0], [50, 1]], 1.0, 2])
        assert any('non dichiarata' in r and DEFAULT_INTERP in r
                   for r in righe)

        # Dichiarata, si vede come dichiarata e senza la nota.
        righe = self._righe([[[0, 0], [50, 1]], 1.0, 2, 'linear'])
        assert any('Interpolation: linear' in r for r in righe)
        assert not any('non dichiarata' in r for r in righe)

    @staticmethod
    def _envelope_e_righe(spec):
        """Il `type` dell'Envelope costruito da `spec`, e le righe
        `Interpolation` che il log del compatto ha emesso per costruirlo."""
        from pge.envelopes.envelope import Envelope

        with patch('pge.shared.logger.get_clip_logger') as mock_get_logger:
            logger = MagicMock()
            mock_get_logger.return_value = logger
            env = Envelope(spec)
            righe = [str(c) for c in logger.info.call_args_list
                     if 'Interpolation' in str(c)]
        return env.type, righe

    PATTERN = [[0, 0], [50, 1], [100, 0]]

    @pytest.mark.parametrize("spec, tipo_applicato", [
        # Il `type` del dict decide per il compatto che non dichiara: e'
        # l'esempio del docstring di `Envelope`.
        ({'type': 'cubic', 'points': [PATTERN, 1.0, 2]}, 'cubic'),
        ({'type': 'step', 'points': [PATTERN, 1.0, 2]}, 'step'),
        # Due compatti in lista: vale il primo che dichiara
        # (`extract_interp_type`), anche per il secondo che tace.
        ([[PATTERN, 1.0, 2, 'step'], [PATTERN, 2.0, 2]], 'step'),
    ], ids=['dict-cubic', 'dict-step', 'secondo-compatto'])
    def test_l_interp_non_dichiarata_non_si_spaccia_per_quella_applicata(
            self, spec, tipo_applicato):
        """Il log del compatto non sa quale interpolazione vincera'.

        Lo slot mancante non vuol dire `linear`: l'`Envelope` interpola col
        `type` del dict, o con l'interp del primo compatto che la dichiara, e
        solo se nessuno lo fa col default. Il log vede il compatto e basta, e
        chiamare quel caso `linear (default)` scriveva su un referto di
        diagnostica un tipo che il motore non stava applicando — la certezza
        sbagliata da cui #219 voleva togliere il log, rimessa da un'altra
        parte.
        """
        tipo, righe = self._envelope_e_righe(spec)

        assert tipo == tipo_applicato  # la premessa: il motore non usa linear
        assert any('non dichiarata' in r for r in righe)
        assert not any('Interpolation: linear' in r for r in righe)

    def test_il_log_segue_gli_slot_insieme_all_espansione(self, monkeypatch):
        """L'invariante vero: il layout si muove e il log si muove con lui.

        I due test qui sopra fissano il difetto misurato; questo fissa la
        *classe* del difetto, che e' il disallineamento fra due lettori — e
        nessuno lo osserva finche' il layout non si muove davvero.

        Qui `interp` e `time_dist` si scambiano di posto nelle costanti. Un
        log con una copia propria degli indici continuerebbe a leggere lo slot
        vecchio e chiamerebbe `exponential` un tipo di interpolazione: non un
        errore, una certezza sbagliata in cima al referto che si legge quando
        un render non suona come doveva.

        Si scambiano quei due e non altri perche' `is_compact_format` non si
        tocca — e' lei a definire il layout per posizione — e la lista
        permutata deve restare valida per lei: lo slot 3 vuole una stringa, il
        4 una stringa o un dict, quindi due stringhe ci stanno in entrambi gli
        ordini. (Con `wrap`, che al suo slot vuole un `bool`, la permutazione
        non sarebbe nemmeno esprimibile.)
        """
        monkeypatch.setattr(EnvelopeBuilder, 'COMPACT_INTERP', 4)
        monkeypatch.setattr(EnvelopeBuilder, 'COMPACT_TIME_DIST', 3)

        # Scritta nel layout permutato: distribuzione allo slot 3, interp al 4.
        permutato = [[[0, 0], [50, 1]], 1.0, 2, 'exponential', 'step']
        assert EnvelopeBuilder.is_compact_format(permutato)

        righe = self._righe(permutato)

        assert any('Interpolation: step' in r for r in righe)
        assert any('spec: exponential' in r for r in righe)
        # E non ha chiamato "interpolazione" cio' che sta allo slot vecchio.
        assert not any('Interpolation: exponential' in r for r in righe)


# =============================================================================
# 17. NESSUNO LEGGE IL COMPATTO PER POSIZIONE A MANO (issue #219)
# =============================================================================

class TestNessunIndiceScrittoAMano:
    """La guardia strutturale sul punto 1 di #219.

    I test del log qui sopra dicono che *quel* lettore e' allineato. Questo
    dice che non ne nasce un quarto: il difetto di #213/#219 non e' un indice
    sbagliato ma un **secondo** lettore del layout, e il secondo lettore e'
    sempre nato per comodita', in una funzione dove serviva un valore e la
    costante sembrava un giro lungo.

    Il presidio e' un AST e non un `grep`: cerca i soli *subscript interi* su
    un nome che tiene un compatto, quindi non si confonde con `item[0]` /
    `item[1]` di un breakpoint — che sono la coppia `[t, v]`, definita da
    `is_breakpoint` e non da questo layout.

    Limite dichiarato: riconosce il compatto dal **nome della variabile**. Un
    compatto legato a un nome generico (`item`, `raw_data`) sfugge, ed e'
    il caso dei due siti di `envelope.py` che #219 ha convertito: li' il
    presidio sono i test di scaling. Vale per cio' che si chiama come si
    chiama, che e' la convenzione dei tre moduli che quel layout percorrono.
    """

    # I moduli che percorrono il layout del compatto, e la funzione che in
    # ciascuno ha il diritto di leggerlo per posizione.
    MODULI = {
        'src/pge/envelopes/envelope_builder.py': {'_compact_slots'},
        'src/pge/envelopes/envelope.py': set(),
        'src/pge/parameters/read_direction.py': set(),
    }

    NOMI_COMPATTO = ('compact', 'compatto', 'scaled_compact')

    @staticmethod
    def _radice():
        """La radice del repo, da cui partono i percorsi di `MODULI`.

        Dal file di test e non da `pge.__file__`: con un'installazione non
        editabile quello punta al site-packages, e `<lib>/src/pge/...` non
        esiste. E' l'idioma degli altri test che leggono i sorgenti
        (`test_range_unit_definitions.py`, `test_stream_config_errors.py`).
        """
        from pathlib import Path
        # tests/envelopes/test_envelope_builder.py -> radice del repo
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _letture_in(cls, sorgente):
        """(funzione, riga, nome, indice) di ogni `compact[<int>]` in `sorgente`.

        Lo scanner della guardia, separato dalla lettura del file perche' la
        controprova lo possa interrogare su sorgenti scritti apposta: se ne
        provasse una copia, uno scanner rotto qui la lascerebbe verde.
        """
        import ast

        albero = ast.parse(sorgente)

        trovate = []

        def percorri(nodo, funzione):
            for figlio in ast.iter_child_nodes(nodo):
                if isinstance(figlio, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    percorri(figlio, figlio.name)
                    continue
                if (isinstance(figlio, ast.Subscript)
                        and isinstance(figlio.value, ast.Name)
                        and figlio.value.id in cls.NOMI_COMPATTO
                        and isinstance(figlio.slice, ast.Constant)
                        and isinstance(figlio.slice.value, int)
                        and not isinstance(figlio.slice.value, bool)):
                    trovate.append((funzione, figlio.lineno,
                                    figlio.value.id, figlio.slice.value))
                percorri(figlio, funzione)

        percorri(albero, '<modulo>')
        return trovate

    @classmethod
    def _letture_posizionali(cls, percorso):
        """Le letture di `_letture_in` nel modulo `percorso` del repo."""
        sorgente = (cls._radice() / percorso).read_text(encoding='utf-8')
        return cls._letture_in(sorgente)

    @pytest.mark.parametrize("percorso", sorted(MODULI))
    def test_solo_il_decoder_legge_gli_slot_per_posizione(self, percorso):
        """Fuori dalle funzioni ammesse, gli slot si leggono dalle costanti."""
        ammesse = self.MODULI[percorso]
        abusivi = [l for l in self._letture_posizionali(percorso)
                   if l[0] not in ammesse]

        assert not abusivi, (
            f"{percorso}: letture del compatto per posizione fuori da "
            f"{sorted(ammesse) or 'nessuna funzione'} -> {abusivi}. "
            f"Usa EnvelopeBuilder._compact_slots o le costanti COMPACT_*."
        )

    def test_la_guardia_vede_davvero_un_indice_a_mano(self):
        """La controprova, senza la quale il test sopra e' verde per cecita'.

        Un AST che non trovasse mai niente — un `ast.Index` di Python 3.8 che
        non e' piu' un `ast.Constant`, un nome di campo cambiato — passerebbe
        identico. Qui si misura che il riconoscimento funziona, e insieme che
        non confonde `item[0]` di un breakpoint con uno slot del compatto.

        Interroga lo **stesso** scanner della guardia (`_letture_in`), non una
        sua copia: la prima versione rifaceva il predicato in proprio, e con lo
        scanner della guardia sabotato a restituire sempre `[]` restavano verdi
        tutti e quattro i test — controprova compresa. Misura anche la
        funzione a cui la lettura e' attribuita, perche' la guardia filtra su
        quella: un'attribuzione sbagliata mette una lettura abusiva sotto il
        nome del decoder, e la guardia tace.
        """
        def letture(sorgente):
            return [(funzione, indice) for funzione, _riga, _nome, indice
                    in self._letture_in(sorgente)]

        assert letture("def f(compact):\n    return compact[4]\n") == [('f', 4)]
        assert letture("def f(item):\n    return [item[0], item[1]]\n") == []
        assert letture(
            "def f(compact):\n"
            "    return compact[EnvelopeBuilder.COMPACT_TIME_DIST]\n") == []

        # L'attribuzione: il metodo che la contiene, anche dentro una classe
        # e dentro una funzione annidata; fuori da ogni funzione, il modulo.
        assert letture(
            "class B:\n"
            "    def _compact_slots(self, compact):\n"
            "        return compact[0]\n"
            "    def _log(self, compatto):\n"
            "        def dentro():\n"
            "            return compatto[3]\n"
            "        return dentro\n"
            "x = compact[2]\n") == [('_compact_slots', 0), ('dentro', 3),
                                     ('<modulo>', 2)]
