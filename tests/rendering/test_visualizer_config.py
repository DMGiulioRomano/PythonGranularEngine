# tests/rendering/test_visualizer_config.py
"""
TDD suite per rendering.visualizer_config.

Lo schema della configurazione di ScoreVisualizer: quali chiavi esistono, che
valore hanno di default, e come si combinano con quelle passate dall'utente.

Prima erano 160 righe di dizionario dentro __init__. Spostarle qui non e' solo
questione di lunghezza: un dizionario non dichiara niente, quindi una chiave
sbagliata passava in silenzio e un override parziale di un gruppo annidato ne
cancellava il resto.

Il risultato resta un dict: ScoreVisualizer(generator, config={...}) e
viz.config sono superficie pubblica, usata da api.py, dalla CLI e dagli esempi
del paper. E' lo schema a essere dichiarato, non il tipo che circola.
"""

import pytest

from pge.rendering.visualizer_config import VisualizerConfig


class TestDefaults:
    """I default, dichiarati una volta sola."""

    def test_nested_groups_are_complete(self):
        """Un gruppo annidato arriva intero, con tutti i suoi campi."""
        config = VisualizerConfig.from_overrides(None).as_dict()
        assert config['envelope_display'] == {'pad_ratio': 0.05, 'samples': 128}

    def test_scalar_override_replaces_the_default(self):
        config = VisualizerConfig.from_overrides(
            {'page_duration': 15.0}).as_dict()
        assert config['page_duration'] == 15.0

    def test_partial_override_keeps_the_rest_of_the_group(self):
        """Il bug che questo modulo chiude: con un merge superficiale, un
        override parziale di un gruppo annidato cancellava gli altri campi, e
        il primo che li leggeva sollevava KeyError."""
        config = VisualizerConfig.from_overrides(
            {'envelope_display': {'pad_ratio': 0.1}}).as_dict()
        assert config['envelope_display'] == {'pad_ratio': 0.1, 'samples': 128}


class TestUnknownKeys:
    """Una chiave che lo schema non conosce e' quasi sempre un refuso, e in un
    dizionario passava in silenzio: si vedeva solo dal fatto che l'opzione non
    aveva effetto."""

    def test_unknown_key_is_rejected(self):
        with pytest.raises(ValueError):
            VisualizerConfig.from_overrides({'font_scal': 2.0})

    def test_the_error_names_the_offending_key(self):
        """Dire quale chiave e' sbagliata e' il punto: un errore generico
        lascerebbe l'utente a cercarla fra le quaranta."""
        with pytest.raises(ValueError, match='font_scal'):
            VisualizerConfig.from_overrides({'font_scal': 2.0})


class TestIsolation:
    """Due visualizer non devono condividere strutture mutabili: uno che
    ritocca i propri colori non deve cambiarli all'altro."""

    def test_mutable_defaults_are_not_shared(self):
        a = VisualizerConfig.from_overrides(None).as_dict()
        b = VisualizerConfig.from_overrides(None).as_dict()
        a['envelope_colors']['volume'] = '#000000'
        assert b['envelope_colors']['volume'] != '#000000'

    def test_as_dict_returns_a_fresh_copy(self):
        """Anche due chiamate sulla stessa configurazione danno dizionari
        indipendenti: as_dict e' una vista, non un riferimento allo schema."""
        config = VisualizerConfig.from_overrides(None)
        first, second = config.as_dict(), config.as_dict()
        first['envelope_display']['samples'] = 999
        assert second['envelope_display']['samples'] == 128

    def test_the_palette_is_not_the_shared_module_constant(self):
        """envelope_colors parte da ENVELOPE_COLORS, che vive in
        envelope_extractor ed e' letta anche da main.py e dall'export SV:
        modificarla da un visualizer la cambierebbe per tutti."""
        from pge.rendering.envelope_extractor import ENVELOPE_COLORS

        config = VisualizerConfig.from_overrides(None).as_dict()
        assert config['envelope_colors'] == ENVELOPE_COLORS
        assert config['envelope_colors'] is not ENVELOPE_COLORS

    def test_objects_passed_in_are_not_copied(self):
        """Solo i contenitori mutabili si copiano. Un oggetto passato
        dall'utente — tipicamente una Colormap gia' costruita — deve restare LO
        STESSO oggetto: copiarlo sarebbe sprecato e sorprendente."""
        sentinel = object()
        config = VisualizerConfig.from_overrides(
            {'grain_colormap': sentinel}).as_dict()
        assert config['grain_colormap'] is sentinel
