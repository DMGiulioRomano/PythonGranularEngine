"""
Test per `CsoundEmitter` (issue #203).

L'emitter e' l'unico posto del motore che parla sintassi Csound. Prima della
#203 le tre forme di statement stavano in tre moduli diversi, due dei quali
sotto il livello che deve restare indipendente dal target:

    i-statement del grano   ->  Grain.to_score_line          (core/)
    f-statement del sample  ->  FtableManager.write_to_file  (allocatore)
    f-statement della finestra -> WindowRegistry.generate_ftable_statement
                                                             (catalogo)

Qui si testano le tre forme nel posto dove sono finite, piu' la guardia che
impedisce loro di tornare indietro.

Contratto di formattazione: **ogni builder restituisce una riga di score
completa, newline inclusa.** Cosi' chi scrive il file concatena senza dover
sapere se lo statement finisce o no, e il grano -- che e' il caso caldo, uno
per riga per milioni di righe -- non paga una concatenazione in piu'.
"""
from __future__ import annotations

import ast
import io
import re
from pathlib import Path

import pytest

from pge.core.grain import Grain
from pge.rendering.csound_emitter import CsoundEmitter
from pge.shared.exceptions import FtableError, InvalidWindowError


@pytest.fixture
def emitter():
    return CsoundEmitter()


def _grain(**overrides):
    params = dict(
        onset=1.5, duration=0.1, pointer_pos=2.3, pitch_ratio=2.0,
        volume=-3.0, pan=0.25, sample_table=1, envelope_table=2,
    )
    params.update(overrides)
    return Grain(**params)


# =============================================================================
# 1. i-statement DEL GRANO
# =============================================================================

class TestGrainStatement:
    """Era `Grain.to_score_line`."""

    def test_format(self, emitter):
        line = emitter.grain_statement(_grain())

        assert line == (
            'i "Grain" 1.50000000 0.10000000 2.300000 2.000000 '
            '-3.00 0.250 1 2\n'
        )

    def test_ten_fields(self, emitter):
        """`i`, nome strumento e otto p-field."""
        parts = emitter.grain_statement(_grain()).strip().split()
        assert len(parts) == 10

    def test_precision_per_field(self, emitter):
        line = emitter.grain_statement(_grain(
            onset=1.23456789, duration=0.987654321,
            pointer_pos=0.123456789, pitch_ratio=1.059463094,
            volume=-6.54321, pan=0.33333333,
            sample_table=3, envelope_table=4,
        ))

        assert '1.23456789' in line   # p2: 8 decimali
        assert '0.98765432' in line   # p3: 8 decimali
        assert '0.123457' in line     # p4: 6
        assert '1.059463' in line     # p5: 6
        assert '-6.54' in line        # p6: 2
        assert '0.333' in line        # p7: 3

    def test_negative_values(self, emitter):
        line = emitter.grain_statement(_grain(
            onset=-1.0, pointer_pos=-0.5, volume=-120.0, pan=-1.0,
        ))

        assert '-1.00000000' in line
        assert '-0.500000' in line
        assert '-120.00' in line
        assert '-1.000' in line

    def test_small_values_are_decimal_not_scientific(self, emitter):
        """Csound non legge la notazione esponenziale di Python."""
        line = emitter.grain_statement(_grain(
            onset=1e-6, duration=1e-9, pointer_pos=1e-12, pitch_ratio=1e-3,
        ))

        assert 'e-' not in line
        assert '0.00000100' in line

    def test_table_numbers_are_integers(self, emitter):
        line = emitter.grain_statement(_grain(sample_table=100, envelope_table=101))
        parts = line.strip().split()

        assert parts[-2:] == ['100', '101']


class TestGrainStatementOnsetOffset:
    """`onset_offset` sottrae dall'onset: onset relativi in modalita' STEMS."""

    def test_default_is_zero(self, emitter):
        grain = _grain(onset=5.0)
        assert emitter.grain_statement(grain) == \
            emitter.grain_statement(grain, onset_offset=0.0)

    def test_subtracts_from_onset(self, emitter):
        line = emitter.grain_statement(_grain(onset=5.123456), onset_offset=5.0)

        assert '0.12345600' in line
        assert '5.123456' not in line

    def test_equal_offset_gives_zero(self, emitter):
        line = emitter.grain_statement(_grain(onset=10.0), onset_offset=10.0)
        assert line.split()[2] == '0.00000000'

    def test_partial_offset(self, emitter):
        line = emitter.grain_statement(_grain(onset=8.0), onset_offset=3.0)
        assert line.split()[2] == '5.00000000'

    def test_touches_only_onset(self, emitter):
        grain = _grain(
            onset=5.0, duration=0.07, pointer_pos=2.5, pitch_ratio=1.5,
            volume=-6.0, pan=0.3, sample_table=3, envelope_table=4,
        )
        with_offset = emitter.grain_statement(grain, onset_offset=5.0).split()
        without = emitter.grain_statement(grain).split()

        assert with_offset[3:] == without[3:]


class TestGrainStatementSamplePrecision:
    """p2/p3 a 8 decimali: un grano da 1 campione deve sopravvivere al
    roundtrip testo -> float senza errori percettibili. Con 6 decimali
    l'errore era ~0.8% a 48 kHz e ~4% a 96 kHz."""

    @pytest.mark.parametrize("sr", [48000, 96000, 192000])
    def test_one_sample_duration_roundtrip(self, emitter, sr):
        dur = 1.0 / sr
        p3 = float(emitter.grain_statement(_grain(duration=dur)).split()[3])

        assert abs(p3 - dur) / dur < 0.001
        assert round(p3 * sr) == 1

    def test_adjacent_one_sample_onsets_stay_distinct(self, emitter):
        sr = 48000
        p2_a = float(emitter.grain_statement(_grain(onset=1.0 / sr)).split()[2])
        p2_b = float(emitter.grain_statement(_grain(onset=2.0 / sr)).split()[2])

        assert p2_a != p2_b
        assert round((p2_b - p2_a) * sr) == 1


# =============================================================================
# 2. f-statement DEL SAMPLE (GEN01)
# =============================================================================

class TestSampleFtable:
    """Era il letterale dentro `FtableManager.write_to_file`.

    GEN01 legge un file audio nella tabella:
        f NUM TIME SIZE GEN "filename" SKIPTIME FORMAT CHANNEL
    con SIZE=0 = dimensione dedotta dal file.
    """

    def test_format(self, emitter):
        assert emitter.sample_ftable(1, '/audio/voice.wav') == \
            'f 1 0 0 1 "/audio/voice.wav" 0 0 1\n'

    def test_table_number_is_used(self, emitter):
        assert emitter.sample_ftable(42, '/a.wav').startswith('f 42 ')

    def test_path_is_quoted(self, emitter):
        assert '"path/to/file.wav"' in emitter.sample_ftable(1, 'path/to/file.wav')

    def test_path_with_spaces_survives_quoting(self, emitter):
        assert '"/a b/c d.wav"' in emitter.sample_ftable(1, '/a b/c d.wav')


# =============================================================================
# 3. f-statement DELLA FINESTRA
# =============================================================================

class TestWindowFtable:
    """Era `WindowRegistry.generate_ftable_statement`."""

    def test_gen20(self, emitter):
        assert emitter.window_ftable(1, 'hanning') == 'f 1 0 1024 20 2 1\n'

    def test_gen16(self, emitter):
        assert emitter.window_ftable(3, 'expodec') == 'f 3 0 1024 16 1 1024 4 0\n'

    def test_gen09(self, emitter):
        assert emitter.window_ftable(4, 'half_sine') == 'f 4 0 1024 9 0.5 1 0\n'

    def test_gen20_with_shape_param(self, emitter):
        assert emitter.window_ftable(1, 'gaussian') == 'f 1 0 1024 20 6 1 3\n'
        assert emitter.window_ftable(1, 'kaiser') == 'f 1 0 1024 20 7 1 6\n'

    @pytest.mark.parametrize("size", [128, 512, 2048, 8192])
    def test_size_is_honoured(self, emitter, size):
        assert emitter.window_ftable(1, 'hanning', size=size) == \
            f'f 1 0 {size} 20 2 1\n'

    def test_default_size_is_1024(self, emitter):
        assert emitter.window_ftable(1, 'hanning') == \
            emitter.window_ftable(1, 'hanning', size=1024)

    @pytest.mark.parametrize("size", [128, 512, 2048, 8192])
    def test_gen16_segment_follows_the_table_size(self, emitter, size):
        """Il segmento GEN16 e' lungo quanto la tabella.

        `gen_params` del catalogo scrive 1024 come durata del segmento --
        il default -- ma quel numero e' in *punti*: lasciato fisso, una
        `size` diversa emetteva una tabella da N punti con dentro un
        segmento da 1024. Il catalogo dichiara la forma della curva, la
        dimensione la decide chi materializza.
        """
        assert emitter.window_ftable(3, 'expodec', size=size) == \
            f'f 3 0 {size} 16 1 {size} 4 0\n'

    def test_gen16_at_default_size_is_unchanged(self, emitter):
        """La derivazione non muove il caso reale: al default i due numeri
        coincidono, ed e' il byte che finisce in ogni `.sco`."""
        assert emitter.window_ftable(3, 'expodec') == 'f 3 0 1024 16 1 1024 4 0\n'

    @pytest.mark.parametrize("size", [256, 4096])
    def test_every_asymmetric_window_follows_the_size(self, emitter, size):
        """Vale per tutta la famiglia, non solo per `expodec`."""
        from pge.controllers.window_registry import WindowRegistry

        for spec in WindowRegistry.get_by_family('asymmetric'):
            fields = emitter.window_ftable(1, spec.name, size=size).split()
            assert fields[3] == str(size), spec.name       # SIZE della tabella
            assert fields[6] == str(size), spec.name       # dur1 del segmento

    def test_default_size_comes_from_the_emitter(self, emitter):
        """`default_window_table_size` e' letto via `self`, come
        `instrument_name`: era un attributo di classe che nessuno leggeva,
        quindi una sottoclasse che lo spostava non otteneva niente."""
        class WideEmitter(CsoundEmitter):
            default_window_table_size = 4096

        assert WideEmitter().window_ftable(1, 'hanning') == 'f 1 0 4096 20 2 1\n'
        assert emitter.window_ftable(1, 'hanning') == 'f 1 0 1024 20 2 1\n'

    def test_instrument_name_comes_from_the_emitter(self, emitter):
        """L'altra meta' della stessa superficie: le due dichiarazioni di
        classe si leggono in coppia, e devono funzionare in coppia."""
        class NamedEmitter(CsoundEmitter):
            instrument_name = 'Zap'

        assert NamedEmitter().grain_statement(_grain()).startswith('i "Zap" ')

    def test_alias_resolves_to_canonical(self, emitter):
        assert emitter.window_ftable(1, 'triangle') == \
            emitter.window_ftable(1, 'bartlett')

    def test_every_catalogued_window_is_emittable(self, emitter):
        """Il catalogo e l'adapter Csound non possono divergere in silenzio."""
        from pge.controllers.window_registry import WindowRegistry

        for name in WindowRegistry.all_names():
            line = emitter.window_ftable(7, name)
            assert line.startswith('f 7 0 1024 ')
            assert line.endswith('\n')

    @pytest.mark.parametrize("bad_name", [
        'nonexistent', '', 'HANNING', 'MISSING_WINDOW', 'bad_name',
    ])
    def test_unknown_name_raises(self, emitter, bad_name):
        with pytest.raises(InvalidWindowError) as exc_info:
            emitter.window_ftable(1, bad_name)

        assert exc_info.value.name == bad_name
        assert '[ERRORE]' in exc_info.value.user_message()


class TestWindowFtableCoversTheCatalogue:
    """Ogni nome che il catalogo accetta deve avere il suo statement.

    Le asserzioni girano su `WindowRegistry` invece che su una tabella di
    attesi trascritta qui: la tabella e' il test del catalogo, e sta nel file
    del catalogo. Quello che si verifica qui e' la relazione fra i due --
    l'adapter copre il catalogo, e lo traduce senza perdere niente.
    """

    VALID_GEN_ROUTINES = {9, 16, 20}

    def test_every_name_parses_as_an_ftable(self, emitter):
        from pge.controllers.window_registry import WindowRegistry

        for name in WindowRegistry.all_names():
            parts = emitter.window_ftable(1, name).split()

            assert parts[0] == 'f'
            assert int(parts[1]) >= 1
            assert parts[2] == '0'          # time
            assert int(parts[3]) > 0        # size
            assert int(parts[4]) in self.VALID_GEN_ROUTINES
            assert len(parts) >= 6

    def test_statement_carries_the_whole_spec(self, emitter):
        """GEN routine e parametri, nell'ordine in cui il catalogo li scrive."""
        from pge.controllers.window_registry import WindowRegistry

        for name in WindowRegistry.all_names():
            spec = WindowRegistry.get(name)
            parts = emitter.window_ftable(1, name).split()

            assert parts[4] == str(spec.gen_routine)
            assert parts[5:] == [str(p) for p in spec.gen_params]

    def test_asymmetric_family_is_gen16(self, emitter):
        from pge.controllers.window_registry import WindowRegistry

        for spec in WindowRegistry.get_by_family('asymmetric'):
            assert emitter.window_ftable(1, spec.name).startswith('f 1 0 1024 16')

    def test_negative_params_survive(self, emitter):
        assert '-4' in emitter.window_ftable(1, 'exporise')
        assert '-10' in emitter.window_ftable(1, 'exporise_strong')

    def test_table_numbers_give_distinct_statements(self, emitter):
        lines = {emitter.window_ftable(n, 'hanning') for n in range(1, 5)}
        assert len(lines) == 4

    def test_different_windows_give_distinct_statements(self, emitter):
        lines = {
            emitter.window_ftable(1, name)
            for name in ('hanning', 'hamming', 'expodec')
        }
        assert len(lines) == 3

    def test_catalogue_is_untouched_by_a_rejected_name(self, emitter):
        from pge.controllers.window_registry import WindowRegistry

        before = len(WindowRegistry.WINDOWS)
        with pytest.raises(InvalidWindowError):
            emitter.window_ftable(1, 'bad_name')

        assert len(WindowRegistry.WINDOWS) == before


# =============================================================================
# 4. LA SEZIONE FUNCTION TABLES
# =============================================================================

class TestWriteFtables:
    """Era `FtableManager.write_to_file`: la sezione completa, statement e
    commenti che li annotano. L'emitter la costruisce dalla symbol table --
    un dict `{num: (tipo, chiave)}` -- non dall'allocatore, cosi' non
    dipende da chi ha assegnato i numeri."""

    def _write(self, emitter, tables):
        buf = io.StringIO()
        emitter.write_ftables(buf, tables)
        return buf.getvalue()

    def test_empty_map_writes_only_the_header(self, emitter):
        content = self._write(emitter, {})

        assert '; FUNCTION TABLES' in content
        assert '=' * 77 in content
        assert 'f ' not in content

    def test_sample_entry(self, emitter):
        content = self._write(emitter, {1: ('sample', '/audio/voice.wav')})

        assert '; Sample: /audio/voice.wav' in content
        assert 'f 1 0 0 1 "/audio/voice.wav" 0 0 1' in content

    def test_window_entry_carries_its_description(self, emitter):
        content = self._write(emitter, {1: ('window', 'hanning')})

        assert '; Window: hanning - Hanning/von Hann window (GEN20 opt 2)' in content
        assert 'f 1 0 1024 20 2 1' in content

    def test_sorted_by_table_number(self, emitter):
        content = self._write(emitter, {
            3: ('window', 'hanning'),
            1: ('window', 'expodec'),
            2: ('sample', '/z.wav'),
        })

        assert content.find('f 1 ') < content.find('f 2 ') < content.find('f 3 ')

    def test_mixed_entries(self, emitter):
        content = self._write(emitter, {
            1: ('sample', '/audio/voice.wav'),
            2: ('window', 'expodec'),
        })

        assert content.count('Sample:') == 1
        assert content.count('Window:') == 1

    def test_does_not_consume_the_map(self, emitter):
        tables = {1: ('sample', '/test.wav'), 2: ('window', 'hanning')}
        before = dict(tables)

        self._write(emitter, tables)

        assert tables == before

    def test_unknown_window_in_the_map_raises_ftable_error(self, emitter):
        """Stato incoerente: la symbol table cita una finestra che il
        catalogo non conosce. E' un errore diverso da un nome sbagliato in
        YAML -- `register_window` avrebbe dovuto fermarlo -- e ha un
        messaggio suo."""
        with pytest.raises(FtableError) as exc_info:
            self._write(emitter, {1: ('window', 'nonexistent_window_xyz')})

        msg = exc_info.value.user_message()
        assert '[ERRORE]' in msg
        assert 'nonexistent_window_xyz' in msg

    def test_window_size_follows_the_emitter_default(self, emitter):
        """La sezione non passa una `size`, quindi eredita quella
        dell'emitter -- il lookup della spec e' unico ma la dimensione
        resta la stessa che darebbe `window_ftable`."""
        class WideEmitter(CsoundEmitter):
            default_window_table_size = 2048

        content = self._write(WideEmitter(), {1: ('window', 'expodec')})

        assert 'f 1 0 2048 16 1 2048 4 0' in content

    def test_unknown_entry_type_is_ignored(self, emitter):
        """Un tipo che l'emitter non conosce non fa saltare la sezione:
        era il comportamento di `write_to_file` (nessun `else`)."""
        content = self._write(emitter, {1: ('mistero', 'x'), 2: ('window', 'hanning')})

        assert 'f 2 0 1024 20 2 1' in content


# =============================================================================
# 5. LA GUARDIA: la sintassi Csound non torna sotto il renderer
# =============================================================================

def _code_string_constants(path: Path):
    """Le stringhe che il modulo *usa*, docstring escluse.

    Legge il sorgente come codice invece che come testo: un commento non
    esiste nell'AST, e una docstring viene riconosciuta e saltata. Cosi' la
    guardia parla dei letterali che finiscono in un output, non di come il
    modulo si descrive -- che per il catalogo delle finestre e' per forza in
    termini Csound (i GEN sono la sua materia).
    """
    tree = ast.parse(path.read_text(encoding='utf-8'))

    docstring_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and \
                    isinstance(node.body[0].value, ast.Constant) and \
                    isinstance(node.body[0].value.value, str):
                docstring_nodes.add(id(node.body[0].value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstring_nodes:
            yield node.value


# Un letterale che apre una riga di score Csound: `i` (evento) o `f`
# (function table) seguiti da uno spazio o dalla virgoletta del nome, la `e`
# di fine score, il `;` di un commento.
#
# Il criterio non e' "statement": e' *sintassi del target*. Il `;` e la `e`
# non hanno un p-field, ma sono altrettanto Csound -- un secondo back-end
# testuale che li trovasse gia' scritti in `ScoreWriter` dovrebbe forkarne
# header e footer, cioe' l'accoppiamento che la #203 toglie di mezzo.
_SCORE_STATEMENT = re.compile(r'^([if][ "{]|e\n$|; )')


def _module_path(module_name: str) -> Path:
    import importlib
    return Path(importlib.import_module(module_name).__file__)


TARGET_FREE_MODULES = [
    'pge.core.grain',
    'pge.rendering.ftable_manager',
    'pge.controllers.window_registry',
    # Non ha ceduto un metodo come gli altri tre, ma e' il modulo che la
    # sintassi la aveva sotto mano: dispone le sezioni, e le scriveva.
    'pge.rendering.score_writer',
]


@pytest.mark.parametrize("module_name", TARGET_FREE_MODULES)
def test_module_emits_no_csound_statement(module_name):
    """I moduli della #203 non costruiscono piu' sintassi Csound.

    Il criterio non e' un elenco di nomi di metodi: e' che nessun letterale
    di quei moduli apra una riga di score. Un metodo rinominato o un
    letterale rimesso a mano dentro un altro metodo fallisce lo stesso.
    """
    offenders = [
        value for value in _code_string_constants(_module_path(module_name))
        if _SCORE_STATEMENT.match(value)
    ]

    assert offenders == [], (
        f"{module_name} costruisce sintassi Csound: {offenders!r}. "
        f"Gli statement di score si emettono in CsoundEmitter (issue #203)."
    )


def test_the_guard_can_actually_see_a_statement():
    """La guardia sopra non e' verde perche' cieca: sull'emitter, che gli
    statement li scrive per mestiere, trova entrambe le forme."""
    found = [
        value for value in _code_string_constants(
            _module_path('pge.rendering.csound_emitter'))
        if _SCORE_STATEMENT.match(value)
    ]

    assert any(v.startswith('i ') for v in found)
    assert any(v.startswith('f ') for v in found)
    assert any(v.startswith('; ') for v in found)
    assert 'e\n' in found


@pytest.mark.parametrize("owner,method", [
    ('pge.core.grain:Grain', 'to_score_line'),
    ('pge.rendering.ftable_manager:FtableManager', 'write_to_file'),
    ('pge.controllers.window_registry:WindowRegistry', 'generate_ftable_statement'),
])
def test_codegen_method_is_gone(owner, method):
    import importlib

    module_name, class_name = owner.split(':')
    cls = getattr(importlib.import_module(module_name), class_name)

    assert not hasattr(cls, method)
