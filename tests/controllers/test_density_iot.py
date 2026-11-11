"""
`grain.iot` nel DensityController (issue #311, mappe caotiche 3/7).

`grain.iot` e' l'attesa fino al grano successivo: `onset[n+1] = onset[n] +
iot`. E' il terzo modo di dire quando nasce un grano, accanto a `density` e
`fill_factor`, e si sceglie per **presenza** della chiave: con `grain.iot`
scritta la densita' non si decide piu', emerge dagli onset.

Scritta insieme a `density`, `fill_factor` o `distribution` e' un **errore**,
non una priorita': dicono cose diverse (stessa regola di `grain.reverse` /
`grain.read_direction`).
"""
from unittest.mock import patch

import pytest

from pge.controllers.density_controller import (
    DENSITY_NOTICE_INTERVAL,
    DENSITY_NOTICE_THRESHOLD,
    DensityController,
)
from pge.expressions.expression import ExpressionSource
from pge.parameters.parameter import Parameter
from pge.parameters.parameter_definitions import get_parameter_definition
from pge.shared.constants import DEFAULT_OUTPUT_SR
from pge.shared.exceptions import (
    InvalidFieldValueError,
    MissingFieldError,
    ParameterBoundError,
)


@pytest.fixture
def config(mock_config):
    mock_config.context.output_sr = DEFAULT_OUTPUT_SR
    mock_config.map_set = None
    return mock_config


def _controller(config, iot=0.1, **extra):
    return DensityController(params={'grain': {'iot': iot}, **extra},
                             config=config)


class TestIlModoSiSceglieperPresenza:

    def test_con_grain_iot_il_modo_e_iot(self, config):
        controller = _controller(config)
        assert controller.mode == 'iot'
        assert isinstance(controller.iot, Parameter)

    def test_l_attesa_e_il_valore_scritto(self, config):
        controller = _controller(config, iot=0.137)
        assert controller.calculate_inter_onset(0.0, 0.05) == 0.137
        assert controller.calculate_inter_onset(7.0, 0.5) == 0.137

    def test_non_dipende_dalla_durata_del_grano(self, config):
        controller = _controller(config, iot=0.1)
        assert (controller.calculate_inter_onset(0.0, 0.001)
                == controller.calculate_inter_onset(0.0, 5.0))

    def test_un_envelope_e_un_accelerando(self, config):
        controller = _controller(config, iot=[[0, 0.2], [10, 0.1]])
        assert controller.calculate_inter_onset(0.0, 0.05) == pytest.approx(0.2)
        assert controller.calculate_inter_onset(5.0, 0.05) == pytest.approx(0.15)
        assert controller.calculate_inter_onset(10.0, 0.05) == pytest.approx(0.1)

    def test_un_espressione_si_valuta_a_ogni_chiamata(self, config):
        sorgente = ExpressionSource('(0.1 + 0.01*t)', field='grain.iot')
        controller = _controller(config, iot=sorgente)
        assert controller.calculate_inter_onset(0.0, 0.05) == pytest.approx(0.1)
        assert controller.calculate_inter_onset(3.0, 0.05) == pytest.approx(0.13)

    def test_non_c_e_niente_di_casuale(self, config):
        """Nessuna distribuzione di Truax sopra `grain.iot`: la stessa
        chiamata da' lo stesso numero."""
        controller = _controller(config, iot=0.1)
        assert len({controller.calculate_inter_onset(1.0, 0.05)
                    for _ in range(50)}) == 1

    def test_le_altre_tre_letture_non_ci_sono(self, config):
        controller = _controller(config)
        assert controller.density is None
        assert controller.fill_factor is None
        assert controller.distribution is None


class TestSenzaGrainIotValeTuttoComeOggi:

    def test_il_default_resta_fill_factor_due(self, config):
        controller = DensityController(params={}, config=config)
        assert controller.mode == 'fill_factor'
        assert controller.iot is None
        assert controller.calculate_inter_onset(0.0, 0.05) == pytest.approx(0.025)

    def test_density_resta_density(self, config):
        controller = DensityController(params={'density': 20}, config=config)
        assert controller.mode == 'density'
        assert controller.iot is None
        assert controller.calculate_inter_onset(0.0, 0.05) == pytest.approx(0.05)

    def test_un_blocco_grain_senza_iot_non_cambia_il_modo(self, config):
        controller = DensityController(
            params={'grain': {'duration': 0.05}, 'fill_factor': 4},
            config=config)
        assert controller.mode == 'fill_factor'
        assert controller.distribution is not None


class TestInsiemeEUnErrore:

    @pytest.mark.parametrize('chiave, valore', [
        ('density', 20),
        ('fill_factor', 2),
        ('distribution', 0.5),
        ('distribution', 0),
        ('density', None),
    ])
    def test_grain_iot_con_un_altra_chiave_di_densita(self, config, chiave,
                                                       valore):
        with pytest.raises(InvalidFieldValueError) as exc:
            _controller(config, **{chiave: valore})
        assert exc.value.field == 'grain.iot'
        assert chiave in exc.value.hint
        assert exc.value.stream_id == 'test_stream'

    def test_un_espressione_impacchettata_si_mostra_col_suo_testo(self, config):
        """Il «Trovato» e' il testo dell'espressione, non il repr
        dell'oggetto che la porta al parser."""
        sorgente = ExpressionSource('(0.1 + 0.01*t)', field='grain.iot')
        with pytest.raises(InvalidFieldValueError) as exc:
            _controller(config, iot=sorgente, density=20)
        assert exc.value.value == '(0.1 + 0.01*t)'
        assert 'ExpressionSource' not in exc.value.user_message()

    def test_con_tutte_e_tre_le_nomina_tutte(self, config):
        with pytest.raises(InvalidFieldValueError) as exc:
            _controller(config, density=20, fill_factor=2, distribution=1)
        for chiave in ('density', 'fill_factor', 'distribution'):
            assert chiave in exc.value.hint

    def test_grain_iot_scritta_e_lasciata_vuota(self, config):
        """La chiave c'e': il modo e' scelto, e manca il valore. Leggerla
        come «non scritta» farebbe ripartire il default `fill_factor: 2` in
        silenzio."""
        with pytest.raises(MissingFieldError) as exc:
            _controller(config, iot=None)
        assert exc.value.fields == ['grain.iot']
        assert exc.value.stream_id == 'test_stream'


class TestLimiti:
    """Da un campione a 100 secondi. Il pavimento e' la risoluzione del
    motore, come per `grain.duration`; il tetto e' l'inverso del pavimento di
    `density` (0.01 grani/s)."""

    def test_i_bounds(self):
        bounds = get_parameter_definition(
            'grain_iot', output_sr=DEFAULT_OUTPUT_SR)
        assert bounds.min_val == 1.0 / DEFAULT_OUTPUT_SR
        assert bounds.max_val == 100.0
        assert bounds.max_val == 1.0 / get_parameter_definition('density').min_val
        assert bounds.default_jitter == 0.0

    def test_il_pavimento_di_registro_e_un_campione(self):
        """Chi legge il registro senza il sample rate (un editor) vede lo
        stesso pavimento."""
        assert get_parameter_definition('grain_iot').min_val == pytest.approx(
            1.0 / DEFAULT_OUTPUT_SR)

    @pytest.mark.parametrize('iot', [0, -0.1, 100.5, float('inf'),
                                     float('nan')])
    def test_un_numero_fuori_limite_e_un_errore_al_parse(self, config, iot):
        with pytest.raises(ParameterBoundError):
            _controller(config, iot=iot)

    def test_un_envelope_fuori_limite_e_un_errore_al_parse(self, config):
        with pytest.raises(ParameterBoundError):
            _controller(config, iot=[[0, 0.1], [10, 0]])

    def test_un_campione_e_lecito(self, config):
        controller = _controller(config, iot=1.0 / DEFAULT_OUTPUT_SR)
        with patch('pge.controllers.density_controller.log_high_density_warning'):
            assert controller.calculate_inter_onset(0.0, 0.05) == pytest.approx(
                1.0 / DEFAULT_OUTPUT_SR)

    def test_un_espressione_fuori_limite_si_taglia_e_si_scrive(self, config):
        for testo, atteso in (('(0 * t)', 1.0 / DEFAULT_OUTPUT_SR),
                              ('(0 - 1)', 1.0 / DEFAULT_OUTPUT_SR),
                              ('(500 + t)', 100.0),
                              ('(sqrt(0 - 1))', 1.0 / DEFAULT_OUTPUT_SR),
                              ('(1 / (0 * t))', 100.0)):
            controller = _controller(
                config, iot=ExpressionSource(testo, field='grain.iot'))
            with patch('pge.parameters.parameter.log_clip_warning') as clip, \
                    patch('pge.controllers.density_controller'
                          '.log_high_density_warning'):
                assert controller.calculate_inter_onset(0.0, 0.05) == atteso, testo
            assert clip.call_count == 1, testo
            assert clip.call_args.kwargs['param_name'] == 'grain_iot'


class TestDensityHigh:

    def test_sopra_la_soglia_la_riga_continua_a_uscire(self, config):
        """Un'attesa sotto 0.25 ms e' una densita' sopra 4000 grani/s."""
        controller = _controller(config, iot=0.0001)
        with patch('pge.controllers.density_controller'
                   '.log_high_density_warning') as log:
            controller.calculate_inter_onset(0.0, 0.05)
        assert log.call_count == 1
        chiamata = log.call_args.kwargs
        assert chiamata['density'] == pytest.approx(10000.0)
        assert chiamata['threshold'] == DENSITY_NOTICE_THRESHOLD
        assert chiamata['mode'] == 'iot'
        assert chiamata['is_first'] is True

    def test_col_suo_rate_limit(self, config):
        controller = _controller(config, iot=0.0001)
        with patch('pge.controllers.density_controller'
                   '.log_high_density_warning') as log:
            for n in range(1000):
                controller.calculate_inter_onset(n * 0.01, 0.05)
        assert log.call_count == round(10 / DENSITY_NOTICE_INTERVAL)

    def test_sotto_la_soglia_niente(self, config):
        controller = _controller(config, iot=0.01)
        with patch('pge.controllers.density_controller'
                   '.log_high_density_warning') as log:
            controller.calculate_inter_onset(0.0, 0.05)
        assert log.call_count == 0
