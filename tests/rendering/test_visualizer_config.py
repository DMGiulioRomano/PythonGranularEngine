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

from pge.rendering.envelope_extractor import ENVELOPE_COLORS
from pge.rendering.visualizer_config import ENVELOPE_RANGES, VisualizerConfig


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

    def test_partial_override_keeps_the_rest_of_a_data_dict(self):
        """Vale anche per i gruppi che NON sono dataclass ma dizionari-dato.
        Sono il caso piu' insidioso: envelope_ranges non ha un default di
        classe da cui partire (e' un default_factory), quindi un merge scritto
        leggendo l'attributo di classe li salta in silenzio — e chi ritocca il
        range del volume si ritrova senza quello di pan, che il disegno legge
        per nome (KeyError: 'pan')."""
        config = VisualizerConfig.from_overrides(
            {'envelope_ranges': {'volume': (-40, 0)}}).as_dict()
        assert config['envelope_ranges']['volume'] == (-40, 0)
        assert 'pan' in config['envelope_ranges']
        assert len(config['envelope_ranges']) == len(ENVELOPE_RANGES)

    def test_partial_override_of_the_palette_keeps_the_other_colours(self):
        """Stessa storia per i colori. Qui non si schianta: le curve rimaste
        senza colore cadono sul grigio di fallback, e la partitura esce
        monocroma senza dire perche'."""
        config = VisualizerConfig.from_overrides(
            {'envelope_colors': {'volume': '#000000'}}).as_dict()
        assert config['envelope_colors']['volume'] == '#000000'
        assert len(config['envelope_colors']) == len(ENVELOPE_COLORS)

    def test_merging_a_data_dict_does_not_touch_the_module_default(self):
        """Il merge parte da una copia: fondere una entry non deve riscrivere
        la tabella di modulo per tutti i visualizer successivi."""
        VisualizerConfig.from_overrides({'envelope_ranges': {'volume': (-1, 1)}})
        assert ENVELOPE_RANGES['volume'] == (-90, 0)


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

    def test_unknown_key_inside_a_group_is_rejected_the_same_way(self):
        """Un refuso dentro un gruppo annidato e' lo stesso errore dell'utente,
        e deve essere lo stesso errore del programma: ValueError, non il
        TypeError che verrebbe dal costruttore del gruppo. Chi intercetta
        ValueError attorno alla costruzione del visualizer non deve perdere
        meta' dei refusi."""
        with pytest.raises(ValueError):
            VisualizerConfig.from_overrides({'envelope_display': {'sampls': 4}})

    def test_the_error_names_the_group_and_the_key(self):
        """Il nome qualificato: dentro quaranta chiavi, sapere che il refuso e'
        in envelope_display fa la differenza fra cercarlo e vederlo."""
        with pytest.raises(ValueError, match='envelope_display.sampls'):
            VisualizerConfig.from_overrides({'envelope_display': {'sampls': 4}})

    def test_a_valid_group_key_still_passes(self):
        """La validazione non deve diventare un muro: le chiavi giuste del
        gruppo continuano a passare."""
        config = VisualizerConfig.from_overrides(
            {'magnify_defaults': {'zoom': 4.0, 'corner': 'top-left'}}).as_dict()
        assert config['magnify_defaults']['zoom'] == 4.0
        assert config['magnify_defaults']['corner'] == 'top-left'
        assert config['magnify_defaults']['out'] == 0.12


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

    def test_the_caller_dict_is_not_aliased(self):
        """L'isolamento che conta davvero e' su cio' che passa l'utente: i
        default sono gia' separati perche' ognuno nasce da un default_factory,
        quindi verificarli non dice niente sulla copia. Qui il dizionario e'
        dello stesso chiamante, e il visualizer non deve tenerne il
        riferimento — ne' subire una sua modifica successiva."""
        mine = {'volume': '#000000'}
        config = VisualizerConfig.from_overrides({'envelope_colors': mine})
        published = config.as_dict()['envelope_colors']

        mine['volume'] = '#ffffff'
        assert published['volume'] == '#000000'

    def test_two_views_of_the_same_config_are_independent(self):
        """Due as_dict() sulla stessa configurazione, con un dizionario
        dell'utente dentro: restano due strutture separate. Senza la copia
        condividerebbero il dizionario del chiamante e non se ne accorgerebbe
        nessuno finche' un visualizer non ritocca i propri colori."""
        config = VisualizerConfig.from_overrides(
            {'envelope_colors': {'volume': '#000000'}})
        first, second = config.as_dict(), config.as_dict()

        first['envelope_colors']['volume'] = '#123456'
        assert second['envelope_colors']['volume'] == '#000000'

    def test_a_list_from_the_caller_is_not_aliased_either(self):
        """Stessa regola per le liste: magnify_targets arriva dall'utente e
        contiene dizionari, che la copia deve raggiungere in profondita'."""
        targets = [{'t': 1.0}]
        published = VisualizerConfig.from_overrides(
            {'magnify_targets': targets}).as_dict()['magnify_targets']

        targets[0]['t'] = 99.0
        assert published[0]['t'] == 1.0
