"""
Test per il modulo grain.py
Testa la classe Grain e i suoi metodi con pytest.
"""

import pytest
from dataclasses import FrozenInstanceError
from core.grain import Grain


@pytest.fixture
def sample_grain_data():
    """Fixture con dati di esempio per creare un grano."""
    return {
        "onset": 1.5,
        "duration": 0.1,
        "pointer_pos": 2.3,
        "pitch_ratio": 2.0,
        "volume": -3.0,
        "pan": 0.25,
        "sample_table": 1,
        "envelope_table": 2,
    }


@pytest.fixture
def sample_grain(sample_grain_data):
    """Crea un oggetto Grain con dati di esempio."""
    return Grain(**sample_grain_data)


class TestGrainInitialization:
    """Test per l'inizializzazione della classe Grain."""
    
    def test_create_grain_success(self, sample_grain_data):
        """Test creazione grano con parametri validi."""
        grain = Grain(**sample_grain_data)
        
        assert grain.onset == 1.5
        assert grain.duration == 0.1
        assert grain.pointer_pos == 2.3
        assert grain.pitch_ratio == 2.0
        assert grain.volume == -3.0
        assert grain.pan == 0.25
        assert grain.sample_table == 1
        assert grain.envelope_table == 2
    
    def test_create_grain_with_defaults(self):
        """Test creazione grano con valori di default o zero."""
        grain = Grain(
            onset=0.0,
            duration=0.05,
            pointer_pos=0.0,
            pitch_ratio=1.0,
            volume=0.0,
            pan=0.0,
            sample_table=0,
            envelope_table=0,
        )
        
        assert grain.onset == 0.0
        assert grain.duration == 0.05
        assert grain.pointer_pos == 0.0
        assert grain.pitch_ratio == 1.0
        assert grain.volume == 0.0
        assert grain.pan == 0.0
        assert grain.sample_table == 0
        assert grain.envelope_table == 0
    
    def test_grain_is_dataclass(self, sample_grain):
        """Test che Grain sia una dataclass con i metodi appropriati."""
        assert hasattr(sample_grain, '__dataclass_fields__')
        
        # Test che sia frozen
        with pytest.raises(FrozenInstanceError):
            sample_grain.onset = 2.0
    
    def test_grain_has_slots(self, sample_grain):
        """Test che Grain usi slots=True per ottimizzazione memoria."""
        assert hasattr(sample_grain, '__slots__')
        assert sample_grain.__slots__ is not None


class TestGrainToScoreLine:
    """Test per il metodo to_score_line()."""
    
    def test_to_score_line_format(self, sample_grain):
        """Test che il metodo generi una stringa nel formato corretto."""
        result = sample_grain.to_score_line()
        
        # Verifica che la stringa inizi con 'i "Grain"'
        assert result.startswith('i "Grain"')
        
        # Verifica che contenga tutti i valori formattati
        assert '1.500000' in result  # onset
        assert '0.100000' in result  # duration
        assert '2.300000' in result  # pointer_pos
        assert '2.000000' in result  # pitch_ratio
        assert '-3.00' in result  # volume
        assert '0.250' in result  # pan
        assert '1' in result  # sample_table
        assert '2' in result  # envelope_table
        
        # Verifica che termini con newline
        assert result.endswith('\n')
    
    def test_to_score_line_precision(self):
        """Test che i numeri siano formattati con la precisione corretta."""
        grain = Grain(
            onset=1.23456789,
            duration=0.987654321,
            pointer_pos=0.123456789,
            pitch_ratio=1.059463094,  # 1 semitono
            volume=-6.54321,
            pan=0.33333333,
            sample_table=3,
            envelope_table=4,
        )
        
        result = grain.to_score_line()
        
        # Verifica precisione
        assert '1.234568' in result  # onset a 6 decimali
        assert '0.987654' in result  # duration a 6 decimali
        assert '0.123457' in result  # pointer_pos a 6 decimali
        assert '1.059463' in result  # pitch_ratio a 6 decimali
        assert '-6.54' in result  # volume a 2 decimali
        assert '0.333' in result  # pan a 3 decimali
    
    def test_to_score_line_negative_values(self):
        """Test formattazione valori negativi."""
        grain = Grain(
            onset=-1.0,  # onset negativo potrebbe essere valido in certi contesti
            duration=0.1,
            pointer_pos=-0.5,
            pitch_ratio=0.5,
            volume=-120.0,
            pan=-1.0,
            sample_table=1,
            envelope_table=1,
        )
        
        result = grain.to_score_line()
        
        assert '-1.000000' in result  # onset negativo
        assert '-0.500000' in result  # pointer_pos negativo
        assert '-120.00' in result  # volume minimo
        assert '-1.000' in result  # pan estremo sinistro
    
    def test_to_score_line_extreme_values(self):
        """Test con valori estremi."""
        grain = Grain(
            onset=999999.999999,
            duration=999.999999,
            pointer_pos=999999.999999,
            pitch_ratio=999.999999,
            volume=999.99,
            pan=999.999,
            sample_table=9999,
            envelope_table=9999,
        )
        
        result = grain.to_score_line()
        
        # Verifica che i valori estremi siano formattati correttamente
        assert '1000000.000000' in result or '999999.999999' in result
        assert '1000.000000' in result or '999.999999' in result


class TestGrainImmutability:
    """Test per l'immutabilità della classe Grain."""
    
    def test_grain_is_frozen(self, sample_grain):
        """Test che Grain sia immutabile (frozen)."""
        # Tentativo di modificare qualsiasi attributo dovrebbe fallire
        with pytest.raises(FrozenInstanceError):
            sample_grain.onset = 2.0
        
        with pytest.raises(FrozenInstanceError):
            sample_grain.duration = 0.2
        
        with pytest.raises(FrozenInstanceError):
            sample_grain.pointer_pos = 3.0
        
        with pytest.raises(FrozenInstanceError):
            sample_grain.pitch_ratio = 1.5
    
    def test_grain_hashable(self, sample_grain_data):
        """Test che Grain sia hashabile (utile per set e dict)."""
        grain1 = Grain(**sample_grain_data)
        grain2 = Grain(**sample_grain_data)
        
        # Due grani con gli stessi dati dovrebbero avere lo stesso hash
        assert hash(grain1) == hash(grain2)
        
        # Dovrebbero poter essere usati in un set
        grain_set = {grain1, grain2}
        assert len(grain_set) == 1  # Solo un elemento perché sono uguali
        
        # Dovrebbero poter essere usati come chiavi in un dict
        grain_dict = {grain1: "test"}
        assert grain_dict[grain2] == "test"  # grain2 è la stessa chiave


class TestGrainComparisons:
    """Test per i confronti tra oggetti Grain."""
    
    def test_grain_equality(self, sample_grain_data):
        """Test uguaglianza tra due grani identici."""
        grain1 = Grain(**sample_grain_data)
        grain2 = Grain(**sample_grain_data)
        
        assert grain1 == grain2
        assert not (grain1 != grain2)
    
    def test_grain_inequality(self):
        """Test disuguaglianza tra due grani diversi."""
        grain1 = Grain(
            onset=1.0,
            duration=0.1,
            pointer_pos=0.0,
            pitch_ratio=1.0,
            volume=0.0,
            pan=0.0,
            sample_table=1,
            envelope_table=1,
        )
        
        grain2 = Grain(
            onset=2.0,  # Solo onset diverso
            duration=0.1,
            pointer_pos=0.0,
            pitch_ratio=1.0,
            volume=0.0,
            pan=0.0,
            sample_table=1,
            envelope_table=1,
        )
        
        assert grain1 != grain2
        assert not (grain1 == grain2)
    
    def test_grain_repr(self, sample_grain):
        """Test che __repr__ restituisca una stringa informativa."""
        repr_str = repr(sample_grain)
        
        # Verifica che contenga il nome della classe
        assert 'Grain' in repr_str
        
        # Verifica che contenga alcuni valori
        assert '1.5' in repr_str or 'onset' in repr_str


class TestGrainEdgeCases:
    """Test per casi limite ed errori."""
    
    def test_very_small_values(self):
        """Test con valori molto piccoli (vicini a zero)."""
        grain = Grain(
            onset=0.000001,
            duration=0.000001,
            pointer_pos=0.000001,
            pitch_ratio=0.000001,
            volume=-120.0,
            pan=0.000001,
            sample_table=1,
            envelope_table=1,
        )
        
        result = grain.to_score_line()
        
        # Verifica che i valori molto piccoli siano formattati
        assert '0.000001' in result
    
    def test_scientific_notation_values(self):
        """Test con valori in notazione scientifica."""
        grain = Grain(
            onset=1e-6,
            duration=1e-9,
            pointer_pos=1e-12,
            pitch_ratio=1e-3,
            volume=-60.0,
            pan=0.5,
            sample_table=1,
            envelope_table=1,
        )
        
        # La creazione dovrebbe funzionare
        assert grain.onset == 1e-6
        assert grain.duration == 1e-9
        assert grain.pointer_pos == 1e-12
        assert grain.pitch_ratio == 1e-3
        
        # La formattazione dovrebbe convertire in notazione decimale
        result = grain.to_score_line()
        assert '0.000001' in result or '1e-06' in result
    
    @pytest.mark.parametrize("field_name,invalid_value", [
        ("onset", "not_a_number"),  # stringa invece di numero
        ("duration", None),  # None invece di numero
        ("pointer_pos", []),  # lista invece di numero
        ("pitch_ratio", {}),  # dict invece di numero
    ])
    def test_invalid_type_raises_error(self, sample_grain_data, field_name, invalid_value):
        """Test che valori di tipo errato causino TypeError."""
        sample_grain_data[field_name] = invalid_value
        
        with pytest.raises(TypeError):
            Grain(**sample_grain_data)


@pytest.mark.parametrize(
    "grain_params,expected_in_line",
    [
        (
            {
                "onset": 10.0,
                "duration": 0.05,
                "pointer_pos": 5.0,
                "pitch_ratio": 1.5,
                "volume": -6.0,
                "pan": 0.5,
                "sample_table": 10,
                "envelope_table": 20,
            },
            ["10.000000", "0.050000", "5.000000", "1.500000", "-6.00", "0.500", "10", "20"]
        ),
        (
            {
                "onset": 0.0,
                "duration": 1.0,
                "pointer_pos": 0.0,
                "pitch_ratio": 0.5,
                "volume": 0.0,
                "pan": 0.0,
                "sample_table": 1,
                "envelope_table": 1,
            },
            ["0.000000", "1.000000", "0.000000", "0.500000", "0.00", "0.000", "1", "1"]
        ),
        (
            {
                "onset": 100.123456,
                "duration": 0.001,
                "pointer_pos": 50.654321,
                "pitch_ratio": 2.0,
                "volume": -12.34,
                "pan": 0.123,
                "sample_table": 100,
                "envelope_table": 101,
            },
            ["100.123456", "0.001000", "50.654321", "2.000000", "-12.34", "0.123", "100", "101"]
        ),
    ]
)
def test_grain_to_score_line_parametrized(grain_params, expected_in_line):
    """Test parametrizzato per diversi set di parametri."""
    grain = Grain(**grain_params)
    result = grain.to_score_line()
    
    # Verifica che tutti i valori attesi siano nella stringa risultante
    for expected in expected_in_line:
        assert expected in result, f"Atteso '{expected}' in '{result}'"
    
    # Verifica struttura base
    assert result.startswith('i "Grain"')
    parts = result.strip().split()
    assert len(parts) == 10  # "i", "Grain", + 8 parametri


def test_grain_memory_optimization():
    """Test che Grain usi effettivamente slots per risparmiare memoria."""
    grain = Grain(
        onset=0.0,
        duration=0.1,
        pointer_pos=0.0,
        pitch_ratio=1.0,
        volume=0.0,
        pan=0.0,
        sample_table=1,
        envelope_table=1,
    )
    
    # Verifica che non abbia __dict__ (caratteristica di slots)
    assert not hasattr(grain, '__dict__')
    
    # Verifica che abbia __slots__
    assert hasattr(grain, '__slots__')
    
    # Verifica che tutti gli slot siano definiti
    expected_slots = ['onset', 'duration', 'pointer_pos', 'pitch_ratio', 
                      'volume', 'pan', 'sample_table', 'envelope_table']
    assert all(slot in grain.__slots__ for slot in expected_slots)

class TestGrainValidationBoolAsInt:
    """Copre la riga 35: TypeError quando si passa bool come campo int."""

    def test_bool_true_as_sample_table_raises(self, sample_grain_data):
        """bool e' subclass di int, ma deve essere rifiutato."""
        sample_grain_data['sample_table'] = True
        with pytest.raises(TypeError, match="sample_table"):
            Grain(**sample_grain_data)

    def test_bool_false_as_envelope_table_raises(self, sample_grain_data):
        """False come envelope_table deve sollevare TypeError."""
        sample_grain_data['envelope_table'] = False
        with pytest.raises(TypeError, match="envelope_table"):
            Grain(**sample_grain_data)


# =============================================================================
# TEST to_score_line CON onset_offset (RED - fix problema 1)
# =============================================================================

class TestGrainToScoreLineWithOnsetOffset:
    """Test per to_score_line(onset_offset=...) - onset relativo per STEMS mode."""

    def test_default_onset_offset_zero_unchanged(self):
        """onset_offset=0.0 (default) produce lo stesso output di prima."""
        grain = Grain(
            onset=5.0, duration=0.1, pointer_pos=0.0,
            pitch_ratio=1.0, volume=0.0, pan=0.0,
            sample_table=1, envelope_table=2,
        )
        result_no_offset = grain.to_score_line()
        result_zero_offset = grain.to_score_line(onset_offset=0.0)
        assert result_no_offset == result_zero_offset

    def test_onset_offset_subtracts_from_onset(self):
        """onset_offset=stream.onset produce onset relativo (parte da 0)."""
        grain = Grain(
            onset=5.123456, duration=0.1, pointer_pos=0.0,
            pitch_ratio=1.0, volume=0.0, pan=0.0,
            sample_table=1, envelope_table=2,
        )
        result = grain.to_score_line(onset_offset=5.0)
        assert '0.123456' in result
        assert '5.123456' not in result

    def test_onset_offset_stream_onset_gives_zero_start(self):
        """onset == stream.onset → onset relativo = 0.0."""
        grain = Grain(
            onset=10.0, duration=0.05, pointer_pos=0.0,
            pitch_ratio=1.0, volume=0.0, pan=0.0,
            sample_table=1, envelope_table=2,
        )
        result = grain.to_score_line(onset_offset=10.0)
        assert '0.000000' in result

    def test_onset_offset_does_not_affect_other_fields(self):
        """onset_offset modifica solo il campo onset, non duration/pointer/etc."""
        grain = Grain(
            onset=5.0, duration=0.07, pointer_pos=2.5,
            pitch_ratio=1.5, volume=-6.0, pan=0.3,
            sample_table=3, envelope_table=4,
        )
        result = grain.to_score_line(onset_offset=5.0)
        assert '0.070000' in result   # duration invariata
        assert '2.500000' in result   # pointer_pos invariato
        assert '1.500000' in result   # pitch_ratio invariato
        assert '-6.00' in result      # volume invariato
        assert '0.300' in result      # pan invariato
        assert '3' in result          # sample_table invariato
        assert '4' in result          # envelope_table invariato

    def test_onset_offset_partial_subtraction(self):
        """onset_offset parziale produce onset parzialmente ridotto."""
        grain = Grain(
            onset=8.0, duration=0.05, pointer_pos=0.0,
            pitch_ratio=1.0, volume=0.0, pan=0.0,
            sample_table=1, envelope_table=2,
        )
        result = grain.to_score_line(onset_offset=3.0)
        assert '5.000000' in result

    def test_score_line_format_preserved_with_offset(self):
        """Il formato della riga rimane corretto anche con onset_offset."""
        grain = Grain(
            onset=5.0, duration=0.1, pointer_pos=1.0,
            pitch_ratio=1.0, volume=-6.0, pan=0.5,
            sample_table=1, envelope_table=2,
        )
        result = grain.to_score_line(onset_offset=5.0)
        assert result.startswith('i "Grain"')
        assert result.endswith('\n')
        parts = result.strip().split()
        assert len(parts) == 10