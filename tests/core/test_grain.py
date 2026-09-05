"""
Test per il modulo grain.py
Testa la classe Grain e i suoi metodi con pytest.

La serializzazione in i-statement Csound non e' piu' un metodo di Grain
(issue #203): i test del formato -- precisione dei p-field, onset_offset,
grani da un campione -- stanno in tests/rendering/test_csound_emitter.py.
"""

import pytest
from dataclasses import FrozenInstanceError
from pge.core.grain import Grain


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

        assert grain.onset == 0.000001
        assert grain.pan == 0.000001
    
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
# TEST PICKLE (rendering parallelo: i Grain attraversano il confine di processo)
# =============================================================================

class TestGrainPickle:
    """Grain deve essere picklable per il rendering multi-processo.

    frozen=True + __slots__ manuale rompe il pickling di default: l'unpickle
    ripristina lo slot state via setattr, che il __setattr__ frozen rifiuta
    con FrozenInstanceError. Serve __reduce__ che ricostruisce via __init__.
    """

    def test_pickle_roundtrip_preserves_equality(self, sample_grain):
        """dumps → loads restituisce un Grain uguale all'originale."""
        import pickle
        restored = pickle.loads(pickle.dumps(sample_grain))
        assert restored == sample_grain

    def test_pickle_roundtrip_preserves_all_fields(self, sample_grain):
        """Ogni campo sopravvive al roundtrip con lo stesso valore e tipo."""
        import pickle
        restored = pickle.loads(pickle.dumps(sample_grain))
        for field in sample_grain.__slots__:
            assert getattr(restored, field) == getattr(sample_grain, field)
        assert isinstance(restored.sample_table, int)
        assert isinstance(restored.envelope_table, int)

    def test_pickled_grain_is_still_frozen(self, sample_grain):
        """Il Grain ricostruito resta immutabile."""
        import pickle
        restored = pickle.loads(pickle.dumps(sample_grain))
        with pytest.raises(FrozenInstanceError):
            restored.onset = 99.0

    def test_pickle_list_of_grains(self, sample_grain_data):
        """Una lista di Grain (payload dei worker) fa il roundtrip intera."""
        import pickle
        grains = [
            Grain(**{**sample_grain_data, 'onset': i * 0.01})
            for i in range(100)
        ]
        restored = pickle.loads(pickle.dumps(grains))
        assert restored == grains
