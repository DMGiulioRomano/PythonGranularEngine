"""
test_ftable_manager.py

Suite completa di test per il modulo ftable_manager.py.

Coverage target: 100%

Sezioni:
1.  Test __init__() - costruzione e stato iniziale
2.  Test register_sample() - registrazione sample con deduplicazione
3.  Test register_window() - registrazione window con deduplicazione e validazione
4.  Test get_sample_table_num() - lookup sample registrati
5.  Test get_window_table_num() - lookup window registrate
6.  Test get_all_tables() - ritorno copia tabelle
7.  Test __repr__() - rappresentazione per debugging
8.  Test numerazione progressiva - coerenza allocazione tabelle
9.  Test integrazione - workflow completi multi-tipo
10. Test edge cases e boundary conditions
11. Test parametrizzati per copertura sistematica

Strategia di mocking:
- WindowRegistry viene mockato per isolare FtableManager dalla
  dipendenza esterna. Si usa patch('ftable_manager.WindowRegistry')
  per iniettare comportamenti controllati.

Il manager alloca numeri di tabella e basta: la sintassi Csound che li
materializza sta in CsoundEmitter (issue #203), e i suoi test in
tests/rendering/test_csound_emitter.py.
"""

import pytest
import io
import sys
from unittest.mock import patch, MagicMock, call
from dataclasses import dataclass
from typing import Optional, List

from pge.controllers.window_registry import WindowRegistry, WindowSpec
from pge.rendering.ftable_manager import FtableManager


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def fm():
    """FtableManager con start_num=1 e WindowRegistry mockato."""
    return FtableManager(start_num=1)


@pytest.fixture
def fm_offset():
    """FtableManager con start_num=100 per test di offset."""
    return FtableManager(start_num=100)


@pytest.fixture
def fm_populated(fm):
    """FtableManager pre-popolato con sample e window miste."""
    fm.register_sample("/audio/voice.wav")
    fm.register_window("hanning")
    fm.register_sample("/audio/drums.wav")
    fm.register_window("expodec")
    return fm


# =============================================================================
# 1. TEST __init__() - COSTRUZIONE E STATO INIZIALE
# =============================================================================

class TestFtableManagerInit:
    """Test per il costruttore __init__."""

    def test_default_start_num(self):
        """start_num=1 di default."""
        fm = FtableManager()
        assert fm.next_num == 1

    def test_custom_start_num(self):
        """start_num custom viene rispettato."""

        fm = FtableManager(start_num=50)
        assert fm.next_num == 50

    def test_tables_empty_at_init(self, fm):
        """tables dict vuoto all'inizializzazione."""
        assert fm.tables == {}

    def test_sample_cache_empty_at_init(self, fm):
        """_sample_cache vuoto all'inizializzazione."""
        assert fm._sample_cache == {}

    def test_window_cache_empty_at_init(self, fm):
        """_window_cache vuoto all'inizializzazione."""
        assert fm._window_cache == {}

    def test_tables_is_dict(self, fm):
        """tables e' un dizionario."""
        assert isinstance(fm.tables, dict)

    def test_start_num_zero(self):
        """start_num=0 e' accettato."""

        fm = FtableManager(start_num=0)
        assert fm.next_num == 0

    def test_start_num_negative(self):
        """start_num negativo e' accettato (non validato)."""

        fm = FtableManager(start_num=-5)
        assert fm.next_num == -5


# =============================================================================
# 2. TEST register_sample() - REGISTRAZIONE SAMPLE
# =============================================================================

class TestRegisterSample:
    """Test per register_sample() - allocazione e deduplicazione."""

    def test_register_first_sample_returns_start_num(self, fm):
        """Primo sample riceve start_num."""
        num = fm.register_sample("/audio/test.wav")
        assert num == 1

    def test_register_sample_increments_next_num(self, fm):
        """next_num incrementato dopo registrazione."""
        fm.register_sample("/audio/test.wav")
        assert fm.next_num == 2

    def test_register_sample_stored_in_tables(self, fm):
        """Sample appare nel dict tables."""
        num = fm.register_sample("/audio/test.wav")
        assert num in fm.tables
        assert fm.tables[num] == ('sample', '/audio/test.wav')

    def test_register_sample_stored_in_cache(self, fm):
        """Sample appare nel _sample_cache."""
        num = fm.register_sample("/audio/test.wav")
        assert fm._sample_cache["/audio/test.wav"] == num

    def test_register_duplicate_sample_returns_same_num(self, fm):
        """Stesso sample registrato due volte ritorna stesso numero."""
        num1 = fm.register_sample("/audio/test.wav")
        num2 = fm.register_sample("/audio/test.wav")
        assert num1 == num2

    def test_register_duplicate_sample_no_increment(self, fm):
        """Duplicato non incrementa next_num."""
        fm.register_sample("/audio/test.wav")
        next_after_first = fm.next_num
        fm.register_sample("/audio/test.wav")
        assert fm.next_num == next_after_first

    def test_register_duplicate_sample_no_extra_table(self, fm):
        """Duplicato non aggiunge entry in tables."""
        fm.register_sample("/audio/test.wav")
        fm.register_sample("/audio/test.wav")
        assert len(fm.tables) == 1

    def test_register_multiple_different_samples(self, fm):
        """Sample diversi ricevono numeri diversi."""
        num1 = fm.register_sample("/audio/a.wav")
        num2 = fm.register_sample("/audio/b.wav")
        num3 = fm.register_sample("/audio/c.wav")

        assert num1 == 1
        assert num2 == 2
        assert num3 == 3
        assert len(fm.tables) == 3

    def test_register_sample_with_offset(self, fm_offset):
        """Sample con start_num=100."""
        num = fm_offset.register_sample("/audio/test.wav")
        assert num == 100
        assert fm_offset.next_num == 101

    def test_register_sample_path_types(self, fm):
        """Vari formati di path sono trattati come stringhe distinte."""
        num1 = fm.register_sample("test.wav")
        num2 = fm.register_sample("./test.wav")
        num3 = fm.register_sample("/absolute/test.wav")

        # Sono tutti path diversi come stringhe
        assert num1 != num2
        assert num2 != num3

    def test_register_sample_empty_string(self, fm):
        """Stringa vuota e' accettata (nessuna validazione path)."""
        num = fm.register_sample("")
        assert num == 1
        assert fm.tables[num] == ('sample', '')

    def test_register_sample_with_spaces(self, fm):
        """Path con spazi funziona correttamente."""
        num = fm.register_sample("/audio/my file.wav")
        assert fm.tables[num] == ('sample', '/audio/my file.wav')

    def test_deduplication_is_exact_match(self, fm):
        """Deduplicazione usa match esatto sulla stringa."""
        num1 = fm.register_sample("/audio/Test.wav")
        num2 = fm.register_sample("/audio/test.wav")
        # Case-sensitive: sono path diversi
        assert num1 != num2


# =============================================================================
# 3. TEST register_window() - REGISTRAZIONE WINDOW
# =============================================================================

class TestRegisterWindow:
    """Test per register_window() - registrazione, deduplicazione, validazione."""

    def test_register_valid_window(self, fm):
        """Window valida viene registrata."""
        num = fm.register_window("hanning")
        assert num == 1

    def test_register_window_increments_next_num(self, fm):
        """next_num incrementato dopo registrazione window."""
        fm.register_window("hanning")
        assert fm.next_num == 2

    def test_register_window_stored_in_tables(self, fm):
        """Window appare nel dict tables con tipo 'window'."""
        num = fm.register_window("hanning")
        assert fm.tables[num] == ('window', 'hanning')

    def test_register_window_stored_in_window_cache(self, fm):
        """Window appare nel _window_cache."""
        num = fm.register_window("hanning")
        assert fm._window_cache["hanning"] == num

    def test_register_window_not_in_sample_cache(self, fm):
        """Window non inquina _sample_cache."""
        fm.register_window("hanning")
        assert len(fm._sample_cache) == 0

    def test_register_duplicate_window_returns_same_num(self, fm):
        """Stessa window registrata due volte ritorna stesso numero."""
        num1 = fm.register_window("hanning")
        num2 = fm.register_window("hanning")
        assert num1 == num2

    def test_register_duplicate_window_no_increment(self, fm):
        """Duplicato window non incrementa next_num."""
        fm.register_window("hanning")
        next_after = fm.next_num
        fm.register_window("hanning")
        assert fm.next_num == next_after

    def test_register_multiple_different_windows(self, fm):
        """Window diverse ricevono numeri diversi."""
        num1 = fm.register_window("hanning")
        num2 = fm.register_window("hamming")
        num3 = fm.register_window("expodec")

        assert num1 == 1
        assert num2 == 2
        assert num3 == 3

    def test_register_invalid_window_raises_valueerror(self, fm):
        """Window non esistente solleva ValueError (InvalidWindowError eredita ValueError)."""
        with pytest.raises(ValueError, match="non trovata"):
            fm.register_window("nonexistent_window")

    def test_register_invalid_window_error_message_contains_valid_names(self, fm):
        """Messaggio di errore elenca i nomi validi."""
        with pytest.raises(ValueError, match="Disponibili"):
            fm.register_window("invalid")

    def test_register_invalid_window_no_side_effects(self, fm):
        """Registrazione fallita non modifica lo stato."""
        original_next = fm.next_num
        original_tables = len(fm.tables)

        with pytest.raises(ValueError):
            fm.register_window("invalid")

        assert fm.next_num == original_next
        assert len(fm.tables) == original_tables
        assert len(fm._window_cache) == 0

    def test_register_window_case_sensitive(self, fm):
        """Registrazione e' case-sensitive (HANNING != hanning)."""
        # 'HANNING' non esiste nel registry mock
        with pytest.raises(ValueError):
            fm.register_window("HANNING")

    def test_register_window_empty_string_raises(self, fm):
        """Stringa vuota come window solleva ValueError."""
        with pytest.raises(ValueError):
            fm.register_window("")

    @pytest.mark.parametrize("window_name", [
        'hanning', 'hamming', 'bartlett', 'blackman',
        'gaussian', 'kaiser', 'rectangle', 'sinc',
        'half_sine', 'expodec', 'expodec_strong',
        'exporise', 'exporise_strong', 'rexpodec', 'rexporise',
    ])
    def test_register_all_valid_windows(self, fm, window_name):
        """Tutte le window del registry sono registrabili."""
        num = fm.register_window(window_name)
        assert isinstance(num, int)
        assert fm.tables[num] == ('window', window_name)


# =============================================================================
# 4. TEST get_sample_table_num() - LOOKUP SAMPLE
# =============================================================================

class TestGetSampleTableNum:
    """Test per get_sample_table_num()."""

    def test_get_registered_sample(self, fm):
        """Ritorna numero tabella per sample registrato."""
        num = fm.register_sample("/audio/test.wav")
        assert fm.get_sample_table_num("/audio/test.wav") == num

    def test_get_unregistered_sample_returns_none(self, fm):
        """Ritorna None per sample non registrato."""
        assert fm.get_sample_table_num("/audio/unknown.wav") is None

    def test_get_sample_empty_manager(self, fm):
        """None su manager vuoto."""
        assert fm.get_sample_table_num("/audio/test.wav") is None

    def test_get_sample_does_not_match_window(self, fm):
        """get_sample_table_num non trova window."""
        fm.register_window("hanning")
        assert fm.get_sample_table_num("hanning") is None

    def test_get_sample_after_multiple_registrations(self, fm):
        """Lookup corretto con multiple registrazioni."""
        num_a = fm.register_sample("/a.wav")
        num_b = fm.register_sample("/b.wav")
        num_c = fm.register_sample("/c.wav")

        assert fm.get_sample_table_num("/a.wav") == num_a
        assert fm.get_sample_table_num("/b.wav") == num_b
        assert fm.get_sample_table_num("/c.wav") == num_c


# =============================================================================
# 5. TEST get_window_table_num() - LOOKUP WINDOW
# =============================================================================

class TestGetWindowTableNum:
    """Test per get_window_table_num()."""

    def test_get_registered_window(self, fm):
        """Ritorna numero tabella per window registrata."""
        num = fm.register_window("hanning")
        assert fm.get_window_table_num("hanning") == num

    def test_get_unregistered_window_returns_none(self, fm):
        """Ritorna None per window non registrata."""
        assert fm.get_window_table_num("hanning") is None

    def test_get_window_empty_manager(self, fm):
        """None su manager vuoto."""
        assert fm.get_window_table_num("hanning") is None

    def test_get_window_does_not_match_sample(self, fm):
        """get_window_table_num non trova sample."""
        fm.register_sample("hanning")  # registrato come sample!
        assert fm.get_window_table_num("hanning") is None

    def test_get_window_after_multiple_registrations(self, fm):
        """Lookup corretto con multiple window."""
        num_h = fm.register_window("hanning")
        num_e = fm.register_window("expodec")

        assert fm.get_window_table_num("hanning") == num_h
        assert fm.get_window_table_num("expodec") == num_e


# =============================================================================
# 6. TEST get_all_tables() - RITORNO COPIA
# =============================================================================

class TestGetAllTables:
    """Test per get_all_tables()."""

    def test_empty_manager_returns_empty_dict(self, fm):
        """Manager vuoto ritorna dict vuoto."""
        result = fm.get_all_tables()
        assert result == {}

    def test_returns_dict(self, fm):
        """Ritorna un dizionario."""
        assert isinstance(fm.get_all_tables(), dict)

    def test_returns_copy_not_reference(self, fm):
        """Ritorna una copia, non il reference interno."""
        fm.register_sample("/test.wav")
        result = fm.get_all_tables()

        # Modifica la copia
        result[999] = ('fake', 'fake')

        # Originale non modificato
        assert 999 not in fm.tables

    def test_contains_all_registered_tables(self, fm_populated):
        """Contiene tutte le tabelle registrate."""
        result = fm_populated.get_all_tables()
        assert len(result) == 4  # 2 sample + 2 window

    def test_sample_entries_correct(self, fm):
        """Entry sample hanno formato corretto."""
        num = fm.register_sample("/test.wav")
        result = fm.get_all_tables()

        assert result[num] == ('sample', '/test.wav')

    def test_window_entries_correct(self, fm):
        """Entry window hanno formato corretto."""
        num = fm.register_window("hanning")
        result = fm.get_all_tables()

        assert result[num] == ('window', 'hanning')

    def test_mixed_entries(self, fm_populated):
        """Tabelle miste sample/window sono corrette."""
        result = fm_populated.get_all_tables()

        # Verifica che ci siano sia sample che window
        types = [ftype for ftype, _ in result.values()]
        assert 'sample' in types
        assert 'window' in types


# =============================================================================
# 7. TEST __repr__() - RAPPRESENTAZIONE PER DEBUGGING
# =============================================================================

class TestRepr:
    """Test per __repr__()."""

    def test_repr_empty_manager(self, fm):
        """repr su manager vuoto."""
        r = repr(fm)
        assert "FtableManager(" in r
        assert "tables=0" in r
        assert "samples=0" in r
        assert "windows=0" in r
        assert "next_num=1" in r

    def test_repr_with_samples(self, fm):
        """repr mostra conteggio sample."""
        fm.register_sample("/a.wav")
        fm.register_sample("/b.wav")

        r = repr(fm)
        assert "samples=2" in r

    def test_repr_with_windows(self, fm):
        """repr mostra conteggio window."""
        fm.register_window("hanning")
        fm.register_window("hamming")
        fm.register_window("expodec")

        r = repr(fm)
        assert "windows=3" in r

    def test_repr_total_tables(self, fm_populated):
        """repr mostra totale tabelle."""
        r = repr(fm_populated)
        assert "tables=4" in r

    def test_repr_next_num_updated(self, fm_populated):
        """repr mostra next_num corrente."""
        r = repr(fm_populated)
        assert "next_num=5" in r

    def test_repr_returns_string(self, fm):
        """repr ritorna una stringa."""
        assert isinstance(repr(fm), str)

    def test_repr_with_offset(self, fm_offset):
        """repr riflette start_num custom."""
        r = repr(fm_offset)
        assert "next_num=100" in r


# =============================================================================
# 8. TEST NUMERAZIONE PROGRESSIVA
# =============================================================================

class TestTableNumbering:
    """Test per la coerenza della numerazione progressiva delle tabelle."""

    def test_sequential_numbering_samples_only(self, fm):
        """Numerazione sequenziale per soli sample."""
        nums = [fm.register_sample(f"/s{i}.wav") for i in range(5)]
        assert nums == [1, 2, 3, 4, 5]

    def test_sequential_numbering_windows_only(self, fm):
        """Numerazione sequenziale per sole window."""
        windows = ['hanning', 'hamming', 'blackman']
        nums = [fm.register_window(w) for w in windows]
        assert nums == [1, 2, 3]

    def test_interleaved_numbering(self, fm):
        """Numerazione coerente con sample e window interleave."""
        n1 = fm.register_sample("/a.wav")      # 1
        n2 = fm.register_window("hanning")      # 2
        n3 = fm.register_sample("/b.wav")       # 3
        n4 = fm.register_window("expodec")      # 4

        assert [n1, n2, n3, n4] == [1, 2, 3, 4]

    def test_deduplication_preserves_numbering(self, fm):
        """Deduplicazione non altera la sequenza per nuovi elementi."""
        n1 = fm.register_sample("/a.wav")       # 1
        n2 = fm.register_sample("/a.wav")       # dedup -> 1
        n3 = fm.register_sample("/b.wav")       # 2 (non 3!)

        assert n1 == 1
        assert n2 == 1
        assert n3 == 2

    def test_numbering_with_offset(self, fm_offset):
        """Numerazione rispetta offset iniziale."""
        n1 = fm_offset.register_sample("/a.wav")
        n2 = fm_offset.register_window("hanning")

        assert n1 == 100
        assert n2 == 101

    def test_shared_counter_between_types(self, fm):
        """Sample e window condividono lo stesso contatore."""
        fm.register_sample("/a.wav")    # next_num: 1 -> 2
        fm.register_window("hanning")   # next_num: 2 -> 3

        assert fm.next_num == 3
        assert len(fm.tables) == 2


# =============================================================================
# 9. TEST INTEGRAZIONE - WORKFLOW COMPLETI
# =============================================================================

class TestIntegrationWorkflows:
    """Test di integrazione per workflow realistici."""

    def test_full_granular_workflow(self, fm):
        """
        Workflow tipico per sintesi granulare:
        1. Registra sample sorgente
        2. Registra window per inviluppo grano
        3. Verifica tabelle
        """
        sample_num = fm.register_sample("/sounds/texture.wav")
        window_num = fm.register_window("hanning")

        # Verifica numeri tabella
        assert fm.get_sample_table_num("/sounds/texture.wav") == sample_num
        assert fm.get_window_table_num("hanning") == window_num

        # Verifica tutte le tabelle
        tables = fm.get_all_tables()
        assert len(tables) == 2
        assert tables[sample_num][0] == 'sample'
        assert tables[window_num][0] == 'window'
        assert tables[sample_num][1] == "/sounds/texture.wav"
        assert tables[window_num][1] == "hanning"

    def test_multi_stream_shared_sample(self, fm):
        """
        Scenario: piu' stream condividono lo stesso sample
        ma usano window diverse.
        """
        # Stesso sample per 3 stream
        s1 = fm.register_sample("/audio/shared.wav")
        s2 = fm.register_sample("/audio/shared.wav")  # dedup
        s3 = fm.register_sample("/audio/shared.wav")  # dedup

        assert s1 == s2 == s3

        # Window diverse per ogni stream
        w1 = fm.register_window("hanning")
        w2 = fm.register_window("expodec")
        w3 = fm.register_window("gaussian")

        assert len(fm.tables) == 4  # 1 sample + 3 window

    def test_multi_stream_shared_window(self, fm):
        """
        Scenario: piu' stream condividono la stessa window
        ma usano sample diversi.
        """
        # Sample diversi
        fm.register_sample("/audio/voice.wav")
        fm.register_sample("/audio/drums.wav")
        fm.register_sample("/audio/ambient.wav")

        # Stessa window per tutti
        w1 = fm.register_window("hanning")
        w2 = fm.register_window("hanning")  # dedup
        w3 = fm.register_window("hanning")  # dedup

        assert w1 == w2 == w3
        assert len(fm.tables) == 4  # 3 sample + 1 window

    def test_lookup_after_registration_and_snapshot(self, fm):
        """Lookup funziona anche dopo aver esposto la symbol table."""
        num = fm.register_sample("/test.wav")

        fm.get_all_tables()

        # Lookup ancora valido
        assert fm.get_sample_table_num("/test.wav") == num

    def test_register_all_window_types(self, fm):
        """Una window per ogni famiglia GEN prende il suo numero."""
        nums = [
            fm.register_window("hanning"),      # GEN20
            fm.register_window("expodec"),      # GEN16
            fm.register_window("half_sine"),    # GEN09
        ]

        assert nums == [1, 2, 3]
        assert fm.get_all_tables() == {
            1: ('window', 'hanning'),
            2: ('window', 'expodec'),
            3: ('window', 'half_sine'),
        }

    def test_repr_reflects_state_throughout_workflow(self, fm):
        """repr riflette lo stato in ogni fase del workflow."""
        r0 = repr(fm)
        assert "tables=0" in r0

        fm.register_sample("/a.wav")
        r1 = repr(fm)
        assert "tables=1" in r1
        assert "samples=1" in r1

        fm.register_window("hanning")
        r2 = repr(fm)
        assert "tables=2" in r2
        assert "windows=1" in r2


# =============================================================================
# 10. TEST EDGE CASES E BOUNDARY CONDITIONS
# =============================================================================

class TestEdgeCases:
    """Test per edge cases e condizioni limite."""

    def test_same_string_as_sample_and_window_name(self, fm):
        """
        Una stringa uguale puo' essere sample path e window name
        solo se la window e' valida nel registry.
        """
        # 'hanning' come sample path
        sample_num = fm.register_sample("hanning")
        # 'hanning' come window
        window_num = fm.register_window("hanning")

        # Numeri diversi, cache separate
        assert sample_num != window_num
        assert fm.get_sample_table_num("hanning") == sample_num
        assert fm.get_window_table_num("hanning") == window_num

    def test_large_number_of_registrations(self, fm):
        """Gestione di molte registrazioni (stress test leggero)."""
        for i in range(100):
            fm.register_sample(f"/audio/sample_{i}.wav")

        assert len(fm.tables) == 100
        assert fm.next_num == 101

        # Verifica primo e ultimo
        assert fm.get_sample_table_num("/audio/sample_0.wav") == 1
        assert fm.get_sample_table_num("/audio/sample_99.wav") == 100

    def test_register_after_failed_window_registration(self, fm):
        """Registrazione successiva funziona dopo un fallimento."""
        with pytest.raises(ValueError):
            fm.register_window("nonexistent")

        # La prossima registrazione valida funziona
        num = fm.register_window("hanning")
        assert num == 1
        assert fm.next_num == 2

    def test_unicode_in_sample_path(self, fm):
        """Path con caratteri unicode."""
        num = fm.register_sample("/audio/voce_italiaa.wav")
        assert fm.tables[num] == ('sample', '/audio/voce_italiaa.wav')

    def test_very_long_sample_path(self, fm):
        """Path molto lungo."""
        long_path = "/audio/" + "subdir/" * 50 + "file.wav"
        num = fm.register_sample(long_path)
        assert fm.get_sample_table_num(long_path) == num

    def test_get_all_tables_returns_new_copy_each_time(self, fm):
        """Ogni chiamata a get_all_tables ritorna una copia nuova."""
        fm.register_sample("/test.wav")

        copy1 = fm.get_all_tables()
        copy2 = fm.get_all_tables()

        assert copy1 == copy2
        assert copy1 is not copy2

    def test_materializing_the_tables_does_not_modify_state(self, fm):
        """Chi scrive gli f-statement legge la symbol table e non la tocca.

        E' l'invariante che permette a due back-end di leggere la stessa
        `table_map`: se l'emitter Csound la consumasse, il renderer NumPy
        troverebbe un manager diverso a seconda di chi ha scritto prima.
        """
        from pge.rendering.csound_emitter import CsoundEmitter

        fm.register_sample("/test.wav")
        fm.register_window("hanning")

        tables_before = fm.get_all_tables()
        next_before = fm.next_num

        buf = io.StringIO()
        CsoundEmitter().write_ftables(buf, fm.get_all_tables())

        assert fm.get_all_tables() == tables_before
        assert fm.next_num == next_before


# =============================================================================
# 11. TEST PARAMETRIZZATI
# =============================================================================

class TestParametrized:
    """Test parametrizzati per copertura sistematica."""

    @pytest.mark.parametrize("start_num", [0, 1, 10, 100, 1000])
    def test_various_start_nums(self, start_num):
        """Vari valori di start_num."""

        fm = FtableManager(start_num=start_num)
        num = fm.register_sample("/test.wav")
        assert num == start_num

    @pytest.mark.parametrize("n_samples", [1, 5, 10, 20])
    def test_various_sample_counts(self, fm, n_samples):
        """Varie quantita' di sample."""
        for i in range(n_samples):
            fm.register_sample(f"/s{i}.wav")

        assert len(fm.tables) == n_samples
        assert len(fm._sample_cache) == n_samples

    @pytest.mark.parametrize("sample_path,expected_type", [
        ("/audio/test.wav", 'sample'),
        ("relative/path.aif", 'sample'),
        ("simple.wav", 'sample'),
        ("/a/b/c/d/e.wav", 'sample'),
    ])
    def test_sample_type_always_sample(self, fm, sample_path, expected_type):
        """Tipo e' sempre 'sample' per register_sample."""
        num = fm.register_sample(sample_path)
        assert fm.tables[num][0] == expected_type

    @pytest.mark.parametrize("invalid_name", [
        "nonexistent",
        "HANNING",
        "Hanning",
        "",
        "gen20",
        "window",
        "123",
    ])
    def test_invalid_window_names_raise(self, fm, invalid_name):
        """Nomi window non validi sollevano ValueError."""
        with pytest.raises(ValueError):
            fm.register_window(invalid_name)