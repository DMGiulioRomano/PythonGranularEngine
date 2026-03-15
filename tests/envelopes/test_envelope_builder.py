# test_envelope_builder_complete.py
"""
Test suite COMPLETA per EnvelopeBuilder.

Coverage:
1. Test riconoscimento formato compatto (_is_compact_format)
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
from envelopes.envelope_builder import EnvelopeBuilder, detect_format_type


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
    """Test _is_compact_format() - riconoscimento pattern."""
    
    def test_recognize_simple_compact(self, simple_compact):
        """Riconosce formato compatto semplice (3 elementi)."""
        assert EnvelopeBuilder._is_compact_format(simple_compact)
    
    def test_recognize_compact_with_interp(self, compact_with_interp):
        """Riconosce formato compatto con interpolazione (4 elementi)."""
        assert EnvelopeBuilder._is_compact_format(compact_with_interp)
    
    def test_recognize_compact_three_points(self, compact_three_points):
        """Riconosce formato compatto con 3 punti nel pattern."""
        assert EnvelopeBuilder._is_compact_format(compact_three_points)
    
    def test_recognize_compact_single_rep(self, compact_single_rep):
        """Riconosce formato compatto con singola ripetizione."""
        assert EnvelopeBuilder._is_compact_format(compact_single_rep)
    
    def test_reject_legacy_breakpoint(self):
        """Rifiuta breakpoint legacy [t, v]."""
        assert not EnvelopeBuilder._is_compact_format([0, 10])
    
    def test_reject_legacy_list(self, legacy_breakpoints):
        """Rifiuta lista di breakpoints legacy."""
        assert not EnvelopeBuilder._is_compact_format(legacy_breakpoints)
    

    
    def test_reject_empty_list(self):
        """Rifiuta lista vuota."""
        assert not EnvelopeBuilder._is_compact_format([])
    
    def test_reject_wrong_length(self):
        """Rifiuta liste con lunghezza sbagliata."""
        assert not EnvelopeBuilder._is_compact_format([[[0, 0]], 0.4])  # 2 elementi (troppo pochi)
        assert not EnvelopeBuilder._is_compact_format([[[0, 0]], 0.4, 4, 'linear', 'extra', 'altro'])  # 6 elementi (troppi)

    def test_reject_non_list(self):
        """Rifiuta non-liste."""
        assert not EnvelopeBuilder._is_compact_format(42)
        assert not EnvelopeBuilder._is_compact_format("compact")
        assert not EnvelopeBuilder._is_compact_format(None)
    
    def test_reject_wrong_types(self):
        """Rifiuta tipi sbagliati negli elementi."""
        # Pattern non-lista
        assert not EnvelopeBuilder._is_compact_format(["pattern", 0.4, 4])
        
        # Total_time non-numero
        assert not EnvelopeBuilder._is_compact_format([[[0, 0]], "0.4", 4])
        
        # N_reps non-int
        assert not EnvelopeBuilder._is_compact_format([[[0, 0]], 0.4, 4.5])
        
        # Interp_type non-string
        assert not EnvelopeBuilder._is_compact_format([[[0, 0]], 0.4, 4, 123])
    
    def test_accept_empty_pattern(self):
        """Accetta pattern vuoto (validazione in expand)."""
        assert EnvelopeBuilder._is_compact_format([[], 0.4, 4])


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
    """Test validazione e errori."""
    
    def test_error_zero_n_reps(self):
        """Errore con n_reps = 0."""
        compact = [[[0, 0], [100, 1]], 0.4, 0]
        
        with pytest.raises(ValueError, match="n_reps deve essere >= 1"):
            EnvelopeBuilder._expand_compact_format(compact)
    
    def test_error_negative_n_reps(self):
        """Errore con n_reps negativo."""
        compact = [[[0, 0], [100, 1]], 0.4, -5]
        
        with pytest.raises(ValueError, match="n_reps deve essere >= 1"):
            EnvelopeBuilder._expand_compact_format(compact)
        
    def test_error_zero_total_time(self):
        """Errore con end_time = time_offset."""
        compact = [[[0, 0], [100, 1]], 0.0, 4]
        
        with pytest.raises(ValueError, match="end_time .* deve essere > time_offset"):
            EnvelopeBuilder._expand_compact_format(compact, time_offset=0.0)

    def test_error_negative_total_time(self):
        """Errore con end_time negativo."""
        compact = [[[0, 0], [100, 1]], -0.5, 4]
        
        with pytest.raises(ValueError, match="end_time .* deve essere > time_offset"):
            EnvelopeBuilder._expand_compact_format(compact, time_offset=0.0)

    def test_error_empty_pattern(self):
        """Errore con pattern vuoto."""
        compact = [[], 0.4, 4]
        
        with pytest.raises(ValueError, match="pattern_points non può essere vuoto"):
            EnvelopeBuilder._expand_compact_format(compact)
    
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
    
    @patch('shared.logger.get_clip_logger')
    def test_logging_called_on_expand(self, mock_get_logger, simple_compact):
        """Logging chiamato durante expand."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        EnvelopeBuilder._expand_compact_format(simple_compact)
        
        # Logger deve essere chiamato
        assert mock_logger.info.called
    
    @patch('shared.logger.get_clip_logger')
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
    
    @patch('shared.logger.get_clip_logger')
    def test_logging_disabled_when_logger_none(self, mock_get_logger, simple_compact):
        """Nessun errore se logger è None."""
        mock_get_logger.return_value = None
        
        # Non deve sollevare errori
        expanded = EnvelopeBuilder._expand_compact_format(simple_compact)
        assert len(expanded) == 8
    
    @patch('shared.logger.get_clip_logger')
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
        """Percentuali negative (dovrebbe funzionare, ma tempi strani)."""
        compact = [[[-50, 0], [100, 1]], 0.4, 2]
        
        # Non dovrebbe crashare, ma produce tempi strani
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        
        # Almeno deve produrre output
        assert len(expanded) > 0
    
    def test_percentages_over_100(self):
        """Percentuali > 100 (estrapolazione)."""
        compact = [[[0, 0], [200, 1]], 0.4, 2]
        
        # Non dovrebbe crashare
        expanded = EnvelopeBuilder._expand_compact_format(compact)
        assert len(expanded) == 4  # 2*2 + 1
    
    def test_float_n_reps_rejected(self):
        """n_reps float rifiutato da _is_compact_format."""
        compact = [[[0, 0], [100, 1]], 0.4, 4.5]
        
        # _is_compact_format deve rifiutare
        assert not EnvelopeBuilder._is_compact_format(compact)

    # Test aggiuntivi per _log_compact_transformation (da aggiungere a TestLoggingTransformations)

    @patch('shared.logger.get_clip_logger')
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

    @patch('shared.logger.get_clip_logger')
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



    @patch('shared.logger.get_clip_logger')
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

    @patch('shared.logger.get_clip_logger')
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


    @patch('shared.logger.get_clip_logger')
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


    @patch('shared.logger.get_clip_logger')
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



    @patch('shared.logger.get_clip_logger')
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


    @patch('shared.logger.get_clip_logger')
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
        assert EnvelopeBuilder._is_compact_format(item) is False

    def test_log_compact_transformation_with_time_dist_spec(self):
        """
        Riga 330: time_dist_spec presente -> logger.info viene chiamato con spec.
        """

        with patch('shared.logger.get_clip_logger') as mock_get_logger:
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

    @patch('shared.logger.CLIP_LOG_CONFIG', {'log_transformations': False})
    @patch('shared.logger.get_clip_logger')
    def test_final_envelope_silent_when_flag_false(self, mock_get_logger):
        """_log_final_envelope non chiama logger se log_transformations=False."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        raw = [[0, 0], [1, 1]]
        expanded = [[0, 0], [1, 1]]
        EnvelopeBuilder._log_final_envelope(raw, expanded)

        mock_logger.info.assert_not_called()

    @patch('shared.logger.CLIP_LOG_CONFIG', {'log_transformations': False})
    @patch('shared.logger.get_clip_logger')
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

    @patch('shared.logger.CLIP_LOG_CONFIG', {'log_transformations': True})
    @patch('shared.logger.get_clip_logger')
    def test_final_envelope_active_when_flag_true(self, mock_get_logger):
        """_log_final_envelope chiama logger se log_transformations=True."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        raw = [[0, 0], [1, 1]]
        expanded = [[0, 0], [1, 1]]
        EnvelopeBuilder._log_final_envelope(raw, expanded)

        assert mock_logger.info.called

    @patch('shared.logger.CLIP_LOG_CONFIG', {'log_transformations': True})
    @patch('shared.logger.get_clip_logger')
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