# =============================================================================
# tests/controllers/test_density_uncapped.py
# =============================================================================
"""La density non ha piu' un tetto, e la saturazione non e' piu' muta (#272).

Fino a qui `density` aveva `max_val=4000.0` e `FillFactorStrategy._clamp`
richiudeva li' dentro il quoziente `fill_factor / grain_duration`. Il taglio
non passava da `log_clip_warning` — quello vive dentro `Parameter._clamp`, e
la density derivata non e' un Parameter — quindi era invisibile: nessuna riga
di log, nessun errore, solo un fill_factor piu' basso di quello scritto.

La regola implicita era `grain.duration >= fill_factor / 4000`, cioe' 1 ms
esatti con `fill_factor: 4`. Sotto, il motore onorava un fill_factor che
nessuno aveva chiesto: `fill_factor: 8` con grani da 1 ms rendeva 4.

Questa suite fissa il contratto nuovo:

1. il tetto non c'e' piu' — `density.max_val is None`, la grafia che il
   registry usa gia' per `loop_dur`;
2. il pavimento resta, e non e' un limite musicale: `avg_iot = 1.0 / density`
   divide per quel numero, e una density nulla o negativa e' un cursore che
   non avanza — cioe' `generate_grains` che non termina;
3. cio' che il tetto nascondeva adesso si vede: sopra la soglia storica il
   motore scrive una riga sul clip log, con rate limiting, perche' a density
   alta si passa di li' migliaia di volte al secondo.

Il punto 3 non cambia una virgola dell'audio: e' il taglio a essere sparito,
non un taglio nuovo a essere comparso.
"""
import math

import pytest

from pge.controllers.density_controller import (
    DENSITY_NOTICE_THRESHOLD,
    DensityController,
)
from pge.parameters.parameter import Parameter
from pge.parameters.parameter_definitions import (
    ParameterBounds,
    get_parameter_definition,
)
from pge.strategies.strategie import FillFactorStrategy


# =============================================================================
# HELPERS
# =============================================================================

def _param(value, name, bounds=None):
    return Parameter(
        value=value,
        name=name,
        bounds=bounds or get_parameter_definition(name),
        owner_id='test',
    )


def _fill_factor_params(fill_factor=2.0, distribution=0.0):
    return {
        'fill_factor': _param(fill_factor, 'fill_factor'),
        'density': None,
        'distribution': _param(distribution, 'distribution'),
    }


def _direct_density_params(density=20.0, distribution=0.0):
    return {
        'fill_factor': None,
        'density': _param(density, 'density'),
        'distribution': _param(distribution, 'distribution'),
    }


def _controller(mock_config, params):
    dc = object.__new__(DensityController)
    dc._rng = __import__('random').Random(0)
    dc._loaded_params = params
    selected = dc._find_selected_param()
    from pge.strategies.strategy_registry import StrategyFactory
    dc._strategy = StrategyFactory.create_density_strategy(
        selected, params[selected], params)
    dc.distribution_param = params['distribution']
    dc._init_density_notice(mock_config)
    return dc


def _strategy(fill_factor):
    return FillFactorStrategy(_param(fill_factor, 'fill_factor'),
                              _param(0.0, 'distribution'))


@pytest.fixture
def rendered_stream(tmp_path):
    """Uno Stream costruito dal Generator, con i grani davvero generati.

    Non usa `build_stream`: quella fixture non passa da `Generator`, quindi
    lo Stream nasce senza `window_table_map` e `generate_grains` muore sulla
    finestra. Qui serve il percorso vero, perche' la misura e' sui grani.
    """
    import numpy as np
    import soundfile as sf
    import yaml as _yaml

    sf.write(str(tmp_path / 'silence.wav'),
             np.zeros(48000, dtype='float32'), 48000)

    def build(**stream_params):
        from pge.engine.generator import Generator

        params = {
            'stream_id': 'probe',
            'onset': 0.0,
            'duration': 2.0,
            'sample': 'silence.wav',
            'distribution': 0.0,
        }
        params.update(stream_params)
        path = tmp_path / 'probe.yml'
        path.write_text(_yaml.safe_dump(
            {'composition': {'title': 'probe'}, 'seed': 7,
             'streams': [params]}))

        generator = Generator(str(path), samples_dir=str(tmp_path))
        generator.data = generator.load_yaml()
        return generator.create_elements()[0]

    return build


# =============================================================================
# 1. IL TETTO NON C'E' PIU'
# =============================================================================

def test_density_non_ha_un_tetto():
    """`max_val is None`: la stessa grafia di loop_dur, gia' nel registry."""
    assert get_parameter_definition('density').max_val is None


def test_effective_density_non_ha_un_tetto():
    """E' la stessa grandezza, pubblicata per la partitura: stesso dominio.

    Se restasse a 4000 il segnaposto del visualizer dichiarerebbe un limite
    che il motore non applica piu', cioe' la partitura mentirebbe proprio
    sulla curva che esiste per mostrare la density vera.
    """
    assert get_parameter_definition('effective_density').max_val is None


def test_il_pavimento_della_density_sopravvive():
    """Non e' un limite musicale: e' la guardia contro `1.0 / 0`.

    `calculate_inter_onset` divide per la density. A zero e' uno
    ZeroDivisionError, sotto zero e' un cursore che torna indietro e un
    `while` che non finisce.
    """
    assert get_parameter_definition('density').min_val == pytest.approx(0.01)


def test_il_tetto_sparito_non_tocca_grain_duration():
    """La lettura con output_sr resta quella: min = 1 campione, max = None.

    `get_parameter_definition` ricostruisce i bounds per grain_duration; il
    ramo che lo fa deve continuare a propagare gli altri campi, tetto incluso.
    """
    b = get_parameter_definition('grain_duration', output_sr=48000)
    assert b.min_val == pytest.approx(1.0 / 48000)
    assert b.max_val == pytest.approx(10.0)


# =============================================================================
# 2. UNA GRAFIA SOLA DELLA BANDA
# =============================================================================

class TestParameterBoundsClamp:
    """`ParameterBounds.clamp` e' la banda, e sa gia' che il tetto puo' mancare.

    Prima la stessa domanda aveva due risposte: `Parameter._clamp`, che il
    `None` lo gestiva, e `FillFactorStrategy._clamp`, che non lo gestiva —
    `min(None, x)` e' un TypeError. Due copie di una regola sola sono il modo
    in cui una delle due smette di valere.
    """

    def test_alza_al_pavimento(self):
        assert ParameterBounds(min_val=1.0, max_val=10.0).clamp(0.5) == 1.0

    def test_abbassa_al_tetto(self):
        assert ParameterBounds(min_val=1.0, max_val=10.0).clamp(99.0) == 10.0

    def test_dentro_la_banda_non_tocca_niente(self):
        assert ParameterBounds(min_val=1.0, max_val=10.0).clamp(5.0) == 5.0

    def test_senza_tetto_lascia_passare(self):
        assert ParameterBounds(min_val=1.0, max_val=None).clamp(1e9) == 1e9

    def test_senza_tetto_il_pavimento_resta(self):
        assert ParameterBounds(min_val=1.0, max_val=None).clamp(0.5) == 1.0


# =============================================================================
# 3. LA STRATEGY NON TAPPA PIU'
# =============================================================================

class TestFillFactorSenzaTetto:

    @pytest.mark.parametrize("fill_factor,grain_duration", [
        (50.0, 0.001),          # 50000: il vecchio test dava 4000
        (2.0, 1.0 / 48000),     # 96000: grano da un campione
        (4.0, 0.0004),          # 10000: stream9 di mare-nostrum
        (8.0, 0.001),           # 8000: fill_factor 8 rendeva 4
    ])
    def test_il_quoziente_passa_intero(self, fill_factor, grain_duration):
        result = _strategy(fill_factor).calculate_density(
            0.0, grain_duration=grain_duration)
        assert result == pytest.approx(fill_factor / grain_duration)

    def test_il_pavimento_resta(self):
        """fill_factor minimo su grano massimo: 0.0001, sotto il pavimento."""
        result = _strategy(0.001).calculate_density(0.0, grain_duration=10.0)
        assert result == pytest.approx(0.01)

    def test_anche_la_curva_disegnata_dice_il_vero(self):
        """`nominal_density` alimenta la partitura: deve dire lo stesso numero.

        E' la faccia deterministica della stessa formula. Se tappasse solo
        lei, la curva `effective_density` mostrerebbe un plateau che il
        motore non suona — che e' il difetto al contrario.
        """
        result = _strategy(50.0).nominal_density(0.0, grain_duration=0.001)
        assert result == pytest.approx(50000.0)


# =============================================================================
# 4. L'IOT SEGUE
# =============================================================================

class TestInterOnsetSenzaTetto:

    def test_fill_factor_alto_su_grano_corto(self, mock_config):
        dc = _controller(mock_config, _fill_factor_params(fill_factor=50.0))
        iot = dc.calculate_inter_onset(0.0, current_grain_duration=0.001)
        assert iot == pytest.approx(1.0 / 50000.0)

    def test_density_diretta_oltre_il_vecchio_tetto(self, mock_config):
        dc = _controller(mock_config, _direct_density_params(density=96000.0))
        iot = dc.calculate_inter_onset(0.0, current_grain_duration=0.001)
        assert iot == pytest.approx(1.0 / 96000.0)

    def test_sotto_soglia_niente_cambia(self, mock_config):
        """Il grosso del repertorio non si muove di una cifra."""
        dc = _controller(mock_config, _fill_factor_params(fill_factor=2.0))
        iot = dc.calculate_inter_onset(0.0, current_grain_duration=0.05)
        assert iot == pytest.approx(0.025)


# =============================================================================
# 5. IL WARNING: CIO' CHE IL TETTO NASCONDEVA
# =============================================================================

class TestAvvisoDensitaAlta:

    def test_emette_sopra_soglia(self, mock_config, caplog):
        dc = _controller(mock_config, _fill_factor_params(fill_factor=50.0))
        with caplog.at_level('WARNING'):
            dc.calculate_inter_onset(0.0, current_grain_duration=0.001)

        assert any('50000' in r.getMessage() for r in caplog.records), \
            "la riga deve portare la density richiesta"

    def test_nomina_lo_stream(self, mock_config, caplog):
        dc = _controller(mock_config, _fill_factor_params(fill_factor=50.0))
        with caplog.at_level('WARNING'):
            dc.calculate_inter_onset(0.0, current_grain_duration=0.001)

        assert any(mock_config.context.stream_id in r.getMessage()
                   for r in caplog.records), \
            "senza stream_id l'avviso non dice dove guardare"

    def test_tace_sotto_soglia(self, mock_config, caplog):
        """Il repertorio normale non deve produrre rumore diagnostico."""
        dc = _controller(mock_config, _fill_factor_params(fill_factor=2.0))
        with caplog.at_level('WARNING'):
            dc.calculate_inter_onset(0.0, current_grain_duration=0.05)

        assert caplog.records == []

    def test_la_soglia_e_il_vecchio_tetto(self):
        """L'avviso e' il successore visibile del clamp invisibile.

        Il numero non e' nuovo: e' esattamente dove il motore tagliava prima.
        Sopra di li' si e' in territorio che non ha mai reso audio.
        """
        assert DENSITY_NOTICE_THRESHOLD == pytest.approx(4000.0)

    def test_non_spamma(self, mock_config, caplog):
        """A density 50000 si passa di qui 50000 volte al secondo.

        Senza rate limiting il log diventa il collo di bottiglia del render,
        ed e' lo stesso motivo per cui `_log_loop_drift_warning` ce l'ha.
        """
        dc = _controller(mock_config, _fill_factor_params(fill_factor=50.0))
        with caplog.at_level('WARNING'):
            for i in range(500):
                dc.calculate_inter_onset(i * 1e-5, current_grain_duration=0.001)

        assert len(caplog.records) < 10, \
            f"{len(caplog.records)} righe per 500 onset ravvicinati"

    def test_torna_a_parlare_piu_avanti_nello_stream(self, mock_config, caplog):
        """Il rate limiting non deve diventare 'una riga e poi mai piu'.

        Una density che sfonda solo a meta' stream e' precisamente il caso
        che va visto, e un avviso unico emesso all'inizio lo perderebbe.
        """
        dc = _controller(mock_config, _fill_factor_params(fill_factor=50.0))
        with caplog.at_level('WARNING'):
            dc.calculate_inter_onset(0.0, current_grain_duration=0.001)
            dc.calculate_inter_onset(600.0, current_grain_duration=0.001)

        assert len(caplog.records) >= 2


# =============================================================================
# 6. LA PROVA CHE IL FILL_FACTOR ADESSO SI MANTIENE
# =============================================================================

class TestFillFactorRealizzato:
    """La misura end-to-end: e' il difetto per cui questa modifica esiste.

    `fill_factor` e' il rapporto di sovrapposizione in tempo di uscita: la
    somma delle durate dei grani diviso la durata dello stream. Il tetto lo
    rompeva perche' `min(4000, ff/d)` smette di essere lineare in `d`: sotto
    soglia l'IOT si blocca e non si accorcia piu' insieme al grano.
    """

    @staticmethod
    def _realized(stream):
        total = sum(g.duration for g in stream.voices[0])
        return total / stream.duration

    def test_grano_da_04ms_realizza_il_fill_dichiarato(self, rendered_stream):
        """stream9 di mare-nostrum: chiedeva 4, ne rendeva 1.6."""
        stream = rendered_stream(
            duration=2.0,
            fill_factor=4.0,
            grain={'duration': 0.0004, 'envelope': 'hanning'},
        )
        assert self._realized(stream) == pytest.approx(4.0, rel=0.02)

    def test_fill_factor_8_su_grano_da_1ms(self, rendered_stream):
        """La soglia mordeva gia' a 1 ms: 8 diventava 4."""
        stream = rendered_stream(
            duration=2.0,
            fill_factor=8.0,
            grain={'duration': 0.001, 'envelope': 'hanning'},
        )
        assert self._realized(stream) == pytest.approx(8.0, rel=0.02)

    def test_il_repertorio_normale_non_si_muove(self, rendered_stream):
        """Grani da 50 ms: sopra soglia non ci si arriva, il fill era gia' giusto."""
        stream = rendered_stream(
            duration=2.0,
            fill_factor=2.0,
            grain={'duration': 0.05, 'envelope': 'hanning'},
        )
        assert self._realized(stream) == pytest.approx(2.0, rel=0.05)

    def test_la_density_resta_finita(self, rendered_stream):
        """Senza tetto il pavimento e' l'unica garanzia che il cursore avanzi.

        `fill_factor: 0.001` su un grano da 1 s fa 0.001 g/s, sotto il
        pavimento: senza quel minimo l'IOT crescerebbe indefinitamente e la
        generazione non e' piu' una cosa che finisce. Il grano dura meno
        dello stream apposta — piu' lungo, a portarlo via sarebbe la
        GrainClipStrategy e il test misurerebbe quella.
        """
        stream = rendered_stream(
            duration=4.0,
            fill_factor=0.001,
            grain={'duration': 1.0, 'envelope': 'hanning'},
        )
        onsets = [g.onset for g in stream.voices[0]]
        assert onsets and all(math.isfinite(o) for o in onsets)
