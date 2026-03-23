# tests/rendering/test_stream_cache_manager.py
"""
test_stream_cache_manager.py

Suite completa di test per il modulo stream_cache_manager.py.

Coverage target: 100%

Sezioni:
1.  TestFingerprintComputation   - calcolo hash SHA-256 da dict YAML
2.  TestCachePersistence         - load/save del manifest JSON su disco
3.  TestDirtyDetection           - logica dirty: hash cambiato o .aif assente
4.  TestDirtyStreamFiltering     - get_dirty_stream_dicts() su lista mista
5.  TestCacheUpdate              - aggiornamento manifest dopo build

Strategia:
- tmp_path (pytest) per tutti i file su disco: nessun side effect.
- os.path.exists mockato dove serve isolare il check del .aif.
- Nessuna dipendenza da Generator, Stream o Csound.
  StreamCacheManager e' un modulo autonomo.
"""

import json
import os
import pytest
from unittest.mock import patch

from rendering.stream_cache_manager import StreamCacheManager


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def cache_path(tmp_path):
    """Path del manifest JSON in una directory temporanea."""
    return str(tmp_path / "test_cache.json")


@pytest.fixture
def manager(cache_path):
    """StreamCacheManager fresco, nessun manifest su disco."""
    return StreamCacheManager(cache_path=cache_path)


@pytest.fixture
def simple_stream_dict():
    """Dict YAML minimale per un singolo stream."""
    return {
        'stream_id': 's1',
        'onset': 0.0,
        'duration': 10.0,
        'sample': 'piano.wav',
        'volume': -6.0,
        'pitch': {'ratio': 1.0},
    }


@pytest.fixture
def two_stream_dicts():
    """Lista di due stream dict distinti."""
    return [
        {
            'stream_id': 's1',
            'onset': 0.0,
            'duration': 10.0,
            'sample': 'piano.wav',
        },
        {
            'stream_id': 's2',
            'onset': 10.0,
            'duration': 5.0,
            'sample': 'strings.wav',
        },
    ]


# =============================================================================
# 1. FINGERPRINT COMPUTATION
# =============================================================================

class TestFingerprintComputation:
    """Test calcolo fingerprint SHA-256 da dict YAML raw."""

    def test_same_dict_produces_same_fingerprint(self, manager, simple_stream_dict):
        """Lo stesso dict produce sempre lo stesso hash."""
        fp1 = manager.compute_fingerprint(simple_stream_dict)
        fp2 = manager.compute_fingerprint(simple_stream_dict)
        assert fp1 == fp2

    def test_different_dicts_produce_different_fingerprints(self, manager):
        """Dict con valori diversi producono hash diversi."""
        d1 = {'stream_id': 's1', 'volume': -6.0}
        d2 = {'stream_id': 's1', 'volume': -12.0}
        assert manager.compute_fingerprint(d1) != manager.compute_fingerprint(d2)

    def test_key_order_does_not_affect_fingerprint(self, manager):
        """L'ordine delle chiavi nel dict non cambia il fingerprint."""
        d1 = {'stream_id': 's1', 'onset': 0.0, 'sample': 'a.wav'}
        d2 = {'sample': 'a.wav', 'stream_id': 's1', 'onset': 0.0}
        assert manager.compute_fingerprint(d1) == manager.compute_fingerprint(d2)

    def test_fingerprint_is_string(self, manager, simple_stream_dict):
        """Il fingerprint e' una stringa esadecimale."""
        fp = manager.compute_fingerprint(simple_stream_dict)
        assert isinstance(fp, str)
        assert len(fp) == 64  # SHA-256 hex digest

    def test_nested_dict_included_in_fingerprint(self, manager):
        """Strutture annidate (envelope, pitch) sono incluse nell'hash."""
        d1 = {'stream_id': 's1', 'pitch': {'ratio': 1.0}}
        d2 = {'stream_id': 's1', 'pitch': {'ratio': 2.0}}
        assert manager.compute_fingerprint(d1) != manager.compute_fingerprint(d2)

    def test_empty_dict_has_stable_fingerprint(self, manager):
        """Dict vuoto produce un fingerprint stabile."""
        fp1 = manager.compute_fingerprint({})
        fp2 = manager.compute_fingerprint({})
        assert fp1 == fp2

    def test_list_values_included_in_fingerprint(self, manager):
        """Valori lista (envelope breakpoints) sono inclusi nell'hash."""
        d1 = {'stream_id': 's1', 'volume': [0.0, 1.0, 0.5]}
        d2 = {'stream_id': 's1', 'volume': [0.0, 1.0, 0.9]}
        assert manager.compute_fingerprint(d1) != manager.compute_fingerprint(d2)


# =============================================================================
# 2. CACHE PERSISTENCE
# =============================================================================

class TestCachePersistence:
    """Test load/save del manifest JSON su disco."""

    def test_load_returns_empty_dict_when_file_absent(self, manager):
        """Se il file manifest non esiste, load() ritorna dict vuoto."""
        result = manager.load()
        assert result == {}

    def test_save_creates_file(self, manager, cache_path):
        """save() crea il file manifest su disco."""
        manager.save({'s1': 'abc123'})
        assert os.path.exists(cache_path)

    def test_round_trip_save_load(self, manager):
        """Dati salvati e ricaricati sono identici."""
        data = {'s1': 'fingerprint_a', 's2': 'fingerprint_b'}
        manager.save(data)
        loaded = manager.load()
        assert loaded == data

    def test_save_overwrites_existing(self, manager):
        """save() sovrascrive un manifest gia' esistente."""
        manager.save({'s1': 'old'})
        manager.save({'s1': 'new', 's2': 'extra'})
        loaded = manager.load()
        assert loaded == {'s1': 'new', 's2': 'extra'}

    def test_load_malformed_json_returns_empty_dict(self, cache_path, manager):
        """File manifest malformato: load() ritorna dict vuoto senza crash."""
        with open(cache_path, 'w') as f:
            f.write("{ this is not valid json }")
        result = manager.load()
        assert result == {}

    def test_save_creates_parent_directory_if_missing(self, tmp_path):
        """save() crea la directory genitore se non esiste."""
        deep_path = str(tmp_path / 'subdir' / 'cache.json')
        mgr = StreamCacheManager(cache_path=deep_path)
        mgr.save({'s1': 'fp'})
        assert os.path.exists(deep_path)

    def test_load_returns_dict_type(self, manager):
        """load() ritorna sempre un dict, mai None."""
        result = manager.load()
        assert isinstance(result, dict)


# =============================================================================
# 3. DIRTY DETECTION
# =============================================================================

class TestDirtyDetection:
    """Test logica is_dirty: fingerprint + presenza .aif su disco."""

    def test_new_stream_is_dirty(self, manager, simple_stream_dict):
        """Uno stream mai visto (non nel manifest) e' sempre dirty."""
        assert manager.is_dirty(simple_stream_dict, aif_path=None) is True

    def test_unchanged_stream_with_existing_aif_is_clean(
        self, manager, simple_stream_dict, tmp_path
    ):
        """Fingerprint invariato + .aif esistente = clean."""
        aif = str(tmp_path / 's1.aif')
        open(aif, 'w').close()  # crea file vuoto

        fp = manager.compute_fingerprint(simple_stream_dict)
        manager.save({'s1': fp})

        assert manager.is_dirty(simple_stream_dict, aif_path=aif) is False

    def test_changed_fingerprint_is_dirty(
        self, manager, simple_stream_dict, tmp_path
    ):
        """Fingerprint cambiato = dirty, anche se .aif esiste."""
        aif = str(tmp_path / 's1.aif')
        open(aif, 'w').close()

        manager.save({'s1': 'old_fingerprint_that_does_not_match'})

        assert manager.is_dirty(simple_stream_dict, aif_path=aif) is True

    def test_missing_aif_is_dirty_even_if_fingerprint_matches(
        self, manager, simple_stream_dict, tmp_path
    ):
        """Fingerprint invariato ma .aif assente = dirty."""
        aif = str(tmp_path / 's1.aif')
        # NON creiamo il file

        fp = manager.compute_fingerprint(simple_stream_dict)
        manager.save({'s1': fp})

        assert manager.is_dirty(simple_stream_dict, aif_path=aif) is True

    def test_aif_path_none_skips_file_check(
        self, manager, simple_stream_dict
    ):
        """Con aif_path=None il check sul file viene ignorato.
        Lo stream e' dirty solo se il fingerprint non corrisponde."""
        fp = manager.compute_fingerprint(simple_stream_dict)
        manager.save({'s1': fp})

        assert manager.is_dirty(simple_stream_dict, aif_path=None) is False

    def test_stream_id_key_used_for_manifest_lookup(self, manager):
        """Il lookup nel manifest usa stream_id come chiave."""
        d = {'stream_id': 'my_stream', 'volume': -6.0}
        fp = manager.compute_fingerprint(d)
        manager.save({'my_stream': fp})

        assert manager.is_dirty(d, aif_path=None) is False

    def test_stream_without_stream_id_raises(self, manager):
        """Dict senza stream_id solleva ValueError."""
        with pytest.raises(ValueError):
            manager.is_dirty({'volume': -6.0}, aif_path=None)


# =============================================================================
# 4. DIRTY STREAM FILTERING
# =============================================================================

class TestDirtyStreamFiltering:
    """Test get_dirty_stream_dicts() su una lista mista di stream."""

    def test_all_new_streams_are_dirty(self, manager, two_stream_dicts):
        """Con manifest vuoto, tutti gli stream sono dirty."""
        result = manager.get_dirty_stream_dicts(two_stream_dicts, aif_dir=None)
        assert result == two_stream_dicts

    def test_all_clean_streams_are_filtered_out(
        self, manager, two_stream_dicts, tmp_path
    ):
        """Con fingerprint identici e .aif esistenti, nessuno stream e' dirty."""
        manifest = {}
        for d in two_stream_dicts:
            sid = d['stream_id']
            fp = manager.compute_fingerprint(d)
            manifest[sid] = fp
            open(str(tmp_path / f"{sid}.aif"), 'w').close()
        manager.save(manifest)

        result = manager.get_dirty_stream_dicts(
            two_stream_dicts, aif_dir=str(tmp_path)
        )
        assert result == []

    def test_mixed_list_returns_only_dirty(
        self, manager, two_stream_dicts, tmp_path
    ):
        """Lista mista: solo gli stream dirty vengono restituiti."""
        s1, s2 = two_stream_dicts

        # s1 clean: fingerprint salvato + .aif presente
        fp1 = manager.compute_fingerprint(s1)
        manager.save({'s1': fp1})
        open(str(tmp_path / 's1.aif'), 'w').close()

        # s2 dirty: non nel manifest

        result = manager.get_dirty_stream_dicts(
            two_stream_dicts, aif_dir=str(tmp_path)
        )
        assert result == [s2]

    def test_empty_input_returns_empty_list(self, manager):
        """Lista vuota in input, lista vuota in output."""
        result = manager.get_dirty_stream_dicts([], aif_dir=None)
        assert result == []

    def test_aif_dir_none_skips_file_existence_check(
        self, manager, two_stream_dicts
    ):
        """Con aif_dir=None il check sul .aif e' ignorato per tutti gli stream."""
        manifest = {}
        for d in two_stream_dicts:
            manifest[d['stream_id']] = manager.compute_fingerprint(d)
        manager.save(manifest)

        result = manager.get_dirty_stream_dicts(two_stream_dicts, aif_dir=None)
        assert result == []

    def test_aif_filename_derived_from_stream_id(
        self, manager, tmp_path
    ):
        """Il nome del .aif cercato e' {stream_id}.aif dentro aif_dir."""
        d = {'stream_id': 'my_stream', 'onset': 0.0}
        fp = manager.compute_fingerprint(d)
        manager.save({'my_stream': fp})

        # Creiamo il file con il nome atteso
        open(str(tmp_path / 'my_stream.aif'), 'w').close()

        result = manager.get_dirty_stream_dicts([d], aif_dir=str(tmp_path))
        assert result == []


# =============================================================================
# 5. CACHE UPDATE
# =============================================================================

class TestCacheUpdate:
    """Test update_after_build(): aggiorna il manifest con i fingerprint correnti."""

    def test_update_adds_new_entry(self, manager, simple_stream_dict):
        """update_after_build() aggiunge stream_id -> fingerprint al manifest."""
        manager.update_after_build([simple_stream_dict])
        loaded = manager.load()
        expected_fp = manager.compute_fingerprint(simple_stream_dict)
        assert loaded.get('s1') == expected_fp

    def test_update_overwrites_existing_entry(self, manager, simple_stream_dict):
        """update_after_build() aggiorna un fingerprint gia' presente."""
        manager.save({'s1': 'stale_fingerprint'})
        manager.update_after_build([simple_stream_dict])
        loaded = manager.load()
        expected_fp = manager.compute_fingerprint(simple_stream_dict)
        assert loaded['s1'] == expected_fp

    def test_update_preserves_other_entries(self, manager, two_stream_dicts):
        """update_after_build() non cancella gli altri stream nel manifest."""
        s1, s2 = two_stream_dicts
        fp2 = manager.compute_fingerprint(s2)
        manager.save({'s2': fp2})

        manager.update_after_build([s1])
        loaded = manager.load()

        assert 's2' in loaded
        assert loaded['s2'] == fp2

    def test_update_empty_list_does_not_corrupt_manifest(self, manager):
        """update_after_build([]) non altera un manifest gia' presente."""
        manager.save({'s1': 'existing_fp'})
        manager.update_after_build([])
        loaded = manager.load()
        assert loaded == {'s1': 'existing_fp'}

    def test_update_multiple_streams(self, manager, two_stream_dicts):
        """update_after_build() gestisce piu' stream in una sola chiamata."""
        manager.update_after_build(two_stream_dicts)
        loaded = manager.load()
        assert 's1' in loaded
        assert 's2' in loaded
        for d in two_stream_dicts:
            assert loaded[d['stream_id']] == manager.compute_fingerprint(d)