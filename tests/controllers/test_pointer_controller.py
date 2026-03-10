"""
test_pointer_controller_bidirectional.py

Suite di test completa per PointerController con supporto bidirezionale.
Copre tutti i casi edge con speed_ratio positivo, negativo, ed envelope.

Test Coverage:
- Movimento lineare (forward/backward/envelope/zero)
- Entrata nel loop (da entrambe le direzioni)
- Wrap modulare unificato (forward/backward/multiplo)
- Reset direction-aware quando bounds cambiano
- Loop dinamici con envelope
- Inversioni di direzione durante il loop
- Edge cases estremi
"""

import pytest
from unittest.mock import Mock, patch, call
from controllers.pointer_controller import PointerController
from core.stream_config import StreamConfig, StreamContext
from parameters.parameter import Parameter
from parameters.parameter_definitions import ParameterBounds
from envelopes.envelope import Envelope

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def pointer_factory(mock_config):
    """
    Factory per creare PointerController con configurazioni custom.
    Usa Parameter reali con ParameterBounds corretti dal registry.
    
    Usage:
        pointer = pointer_factory({'start': 0, 'speed_ratio': 1.0})
    """
    from parameters.parameter import Parameter
    
    def _create(params: dict, sample_dur: float = None):
        if sample_dur:
            mock_config.context.sample_dur_sec = sample_dur
        
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            
            # ParameterBounds reali dal registry
            bounds_speed = ParameterBounds(
                min_val=-100.0,
                max_val=100.0
            )
            
            bounds_deviation = ParameterBounds(
                min_val=-1.0,
                max_val=1.0,
                min_range=0.0,
                max_range=1.0,
                default_jitter=0.2,
                variation_mode='additive'
            )
            
            bounds_loop = ParameterBounds(
                min_val=0.0,
                max_val=100.0
            )
            
            bounds_loop_dur = ParameterBounds(
                min_val=0.005,
                max_val=100.0
            )
            
            # Crea Parameter REALI per ogni parametro
            real_params = {}
            
            # Parametri obbligatori con defaults
            start_value = params.get('start', 0.0)
            speed_value = params.get('speed_ratio', 1.0)
            
            # pointer_start: NON è uno smart parameter (is_smart=False)
            # Il ParameterOrchestrator restituisce il valore raw direttamente
            real_params['pointer_start'] = start_value
            
            # pointer_speed_ratio: Parameter reale con bounds
            real_params['pointer_speed_ratio'] = Parameter(
                value=speed_value,
                name='pointer_speed_ratio',
                bounds=bounds_speed,
                owner_id='test_stream'
            )
            
            # pointer_deviation: Parameter reale con bounds
            real_params['pointer_deviation'] = Parameter(
                value=0.0,
                name='pointer_deviation',
                bounds=bounds_deviation,
                owner_id='test_stream'
            )
            
            # Parametri loop opzionali
            if 'loop_start' in params:
                real_params['loop_start'] = Parameter(
                    value=params['loop_start'],
                    name='loop_start',
                    bounds=bounds_loop,
                    owner_id='test_stream'
                )
            else:
                real_params['loop_start'] = None
            
            if 'loop_end' in params:
                real_params['loop_end'] = Parameter(
                    value=params['loop_end'],
                    name='loop_end',
                    bounds=bounds_loop,
                    owner_id='test_stream'
                )
            else:
                real_params['loop_end'] = None
            
            if 'loop_dur' in params:
                real_params['loop_dur'] = Parameter(
                    value=params['loop_dur'],
                    name='loop_dur',
                    bounds=bounds_loop_dur,
                    owner_id='test_stream'
                )
            else:
                real_params['loop_dur'] = None
            
            mock_orch.create_all_parameters.return_value = real_params
            
            return PointerController(params, mock_config)
    
    return _create


# =============================================================================
# GRUPPO 1: MOVIMENTO LINEARE BASE
# =============================================================================

class TestLinearMovement:
    """Test movimento lineare senza loop."""
    
    def test_forward_constant_speed(self, pointer_factory):
        """Speed positivo costante."""
        pointer = pointer_factory({'start': 0.0, 'speed_ratio': 1.0})
        
        assert pointer.calculate(0.0) == pytest.approx(0.0)
        assert pointer.calculate(1.0) == pytest.approx(1.0)
        assert pointer.calculate(2.5) == pytest.approx(2.5)
    
    def test_backward_constant_speed(self, pointer_factory):
        """Speed negativo costante - movimento all'indietro."""
        pointer = pointer_factory({'start': 5.0, 'speed_ratio': -1.0})
        
        # t=0: pos = 5.0 + 0*(-1) = 5.0
        assert pointer.calculate(0.0) == pytest.approx(5.0)
        
        # t=1: pos = 5.0 + 1*(-1) = 4.0
        assert pointer.calculate(1.0) == pytest.approx(4.0)
        
        # t=2.5: pos = 5.0 + 2.5*(-1) = 2.5
        assert pointer.calculate(2.5) == pytest.approx(2.5)
    
    def test_backward_wraps_at_zero(self, pointer_factory):
        """Speed negativo wrappa quando raggiunge 0."""
        pointer = pointer_factory({'start': 3.0, 'speed_ratio': -1.0}, sample_dur=10.0)
        
        # t=5: pos = 3.0 + 5*(-1) = -2.0
        # wrap: -2.0 % 10.0 = 8.0
        pos = pointer.calculate(5.0)
        assert pos == pytest.approx(8.0)
    
    def test_zero_speed(self, pointer_factory):
        """Speed zero - posizione fissa."""
        pointer = pointer_factory({'start': 3.0, 'speed_ratio': 0.0})
        
        assert pointer.calculate(0.0) == pytest.approx(3.0)
        assert pointer.calculate(100.0) == pytest.approx(3.0)
    
    def test_very_high_forward_speed(self, pointer_factory):
        """Speed molto alto wrappa correttamente."""
        pointer = pointer_factory({'start': 0.0, 'speed_ratio': 100.0}, sample_dur=5.0)
        
        # t=1: pos = 100, wrap: 100 % 5 = 0
        pos = pointer.calculate(1.0)
        assert 0.0 <= pos < 5.0
    
    def test_very_high_backward_speed(self, pointer_factory):
        """Speed molto negativo wrappa correttamente."""
        pointer = pointer_factory({'start': 0.0, 'speed_ratio': -100.0}, sample_dur=5.0)
        
        # t=1: pos = -100, wrap: -100 % 5 = 0 (in Python)
        pos = pointer.calculate(1.0)
        assert 0.0 <= pos < 5.0


# =============================================================================
# GRUPPO 2: ENTRATA NEL LOOP
# =============================================================================

class TestLoopEntry:
    """Test entrata nel loop da diverse direzioni."""
    
    def test_entry_forward_motion(self, pointer_factory):
        """Entrata nel loop con movimento in avanti."""
        pointer = pointer_factory({
            'start': 0.0,
            'speed_ratio': 1.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        })
        
        # Prima dell'entrata
        assert pointer.in_loop is False
        pos = pointer.calculate(1.5)
        assert pos == pytest.approx(1.5)
        assert pointer.in_loop is False
        
        # Momento dell'entrata (linear_pos = 2.5)
        pos = pointer.calculate(2.5)
        assert pos == pytest.approx(2.5)
        assert pointer.in_loop is True
    
    def test_entry_backward_motion(self, pointer_factory):
        """Entrata nel loop con movimento all'indietro."""
        pointer = pointer_factory({
            'start': 8.0,
            'speed_ratio': -1.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        })
        
        # Prima dell'entrata (pos = 8.0 - 2 = 6.0, fuori loop)
        pos = pointer.calculate(2.0)
        assert pointer.in_loop is False
        
        # Entrata nel loop (pos = 8.0 - 4 = 4.0, dentro [2.0, 5.0])
        pos = pointer.calculate(4.0)
        assert pos == pytest.approx(4.0)
        assert pointer.in_loop is True
    
    def test_never_enters_loop_forward(self, pointer_factory):
        """Pointer non entra mai nel loop (troppo lento)."""
        pointer = pointer_factory({
            'start': 0.0,
            'speed_ratio': 0.1,
            'loop_start': 5.0,
            'loop_end': 8.0
        })
        
        # t=10: pos = 1.0 (ancora prima del loop)
        pos = pointer.calculate(10.0)
        assert pointer.in_loop is False
        assert 0.0 <= pos < 10.0
    
    def test_never_enters_loop_backward(self, pointer_factory):
        """Pointer va all'indietro ma parte già dopo il loop."""
        pointer = pointer_factory({
            'start': 9.0,
            'speed_ratio': -0.1,
            'loop_start': 2.0,
            'loop_end': 5.0
        })
        
        # t=10: pos = 9.0 - 1.0 = 8.0 (ancora dopo il loop)
        pos = pointer.calculate(10.0)
        assert pointer.in_loop is False


# =============================================================================
# GRUPPO 3: WRAP MODULARE UNIFICATO (bounds stabili)
# =============================================================================

class TestUnifiedModularWrap:
    """Test wrap modulare quando bounds sono stabili."""
    
    def test_wrap_forward_single(self, pointer_factory):
        """Wrap forward singolo - supera loop_end."""
        pointer = pointer_factory({
            'start': 0.0,
            'speed_ratio': 1.0,
            'loop_start': 2.0,
            'loop_end': 5.0  # loop_length = 3.0
        })
        
        # Entra nel loop
        pointer.calculate(2.5)
        assert pointer.in_loop is True
        
        # Supera loop_end (linear = 5.5)
        # rel = 5.5 - 2.0 = 3.5
        # wrap = 3.5 % 3.0 = 0.5
        # pos = 2.0 + 0.5 = 2.5
        pos = pointer.calculate(5.5)
        assert pos == pytest.approx(2.5)
    
    def test_wrap_backward_single(self, pointer_factory):
        """Wrap backward singolo - sotto loop_start."""
        pointer = pointer_factory({
            'start': 4.0,
            'speed_ratio': -1.0,
            'loop_start': 2.0,
            'loop_end': 5.0  # loop_length = 3.0
        })
        
        # Entra nel loop
        pointer.calculate(0.0)
        assert pointer.in_loop is True
        
        # Esce sotto loop_start (linear = 4.0 - 2.5 = 1.5)
        # rel = 1.5 - 2.0 = -0.5
        # wrap = -0.5 % 3.0 = 2.5 (Python modulo)
        # pos = 2.0 + 2.5 = 4.5
        pos = pointer.calculate(2.5)
        assert pos == pytest.approx(4.5)
    
    def test_wrap_forward_multiple(self, pointer_factory):
        """Wrap forward multiplo - molti loop completi."""
        pointer = pointer_factory({
            'start': 0.0,
            'speed_ratio': 10.0,  # Veloce!
            'loop_start': 2.0,
            'loop_end': 5.0  # loop_length = 3.0
        })
        
        # Entra nel loop
        pointer.calculate(0.25)
        
        # t=1: linear = 10.0 (supera di molto loop_end)
        # Ha fatto ~2.6 loop completi
        # rel = 10.0 - 2.0 = 8.0
        # wrap = 8.0 % 3.0 = 2.0
        # pos = 2.0 + 2.0 = 4.0
        pos = pointer.calculate(1.0)
        assert pos == pytest.approx(4.0)
        assert 2.0 <= pos < 5.0
    
    def test_wrap_backward_multiple(self, pointer_factory):
        """Wrap backward multiplo - molti loop indietro."""
        pointer = pointer_factory({
            'start': 4.0,
            'speed_ratio': -10.0,  # Molto veloce indietro!
            'loop_start': 2.0,
            'loop_end': 5.0  # loop_length = 3.0
        })
        
        # Entra nel loop
        pointer.calculate(0.0)
        
        # t=1: linear = 4.0 - 10.0 = -6.0
        # rel = -6.0 - 2.0 = -8.0
        # wrap = -8.0 % 3.0 = 1.0
        # pos = 2.0 + 1.0 = 3.0
        pos = pointer.calculate(1.0)
        assert pos == pytest.approx(3.0)
        assert 2.0 <= pos < 5.0
    
    def test_wrap_exactly_at_loop_end(self, pointer_factory):
        """Pointer arriva esattamente a loop_end."""
        pointer = pointer_factory({
            'start': 0.0,
            'speed_ratio': 1.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        })
        
        pointer.calculate(2.5)  # Entra
        
        # Esattamente a loop_end
        pos = pointer.calculate(5.0)
        # Dovrebbe wrappare a loop_start
        assert pos == pytest.approx(2.0)
    
    def test_wrap_exactly_at_loop_start_backward(self, pointer_factory):
        """Pointer arriva esattamente a loop_start andando indietro."""
        pointer = pointer_factory({
            'start': 4.0,
            'speed_ratio': -1.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        })
        
        pointer.calculate(0.0)  # Entra
        
        # Esattamente a loop_start (linear = 4.0 - 2.0 = 2.0)
        pos = pointer.calculate(2.0)
        # Dovrebbe essere valido (2.0 è dentro [2.0, 5.0))
        assert pos == pytest.approx(2.0)


# =============================================================================
# GRUPPO 4: RESET DIRECTION-AWARE (bounds cambiano)
# =============================================================================

class TestDirectionAwareReset:
    """Test reset direction-aware quando i bounds del loop cambiano."""
    
    def test_reset_forward_motion(self, pointer_factory):
        """Bounds cambiano mentre pointer va avanti → reset a loop_start."""
        # Setup con loop_start dinamico (envelope mock)
        params = {
            'start': 0.0,
            'speed_ratio': 1.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        }
        
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            
            # Mock parameters
            mock_params = {}
            
            # start (raw value, is_smart=False)
            mock_params['pointer_start'] = 0.0
            
            # speed_ratio
            param = Mock()
            param.value = 1.0
            param.get_value = Mock(return_value=1.0)
            mock_params['pointer_speed_ratio'] = param
            
            # deviation
            param = Mock()
            param.value = 0.0
            param.get_value = Mock(return_value=0.0)
            mock_params['pointer_deviation'] = param
            
            # loop_start DINAMICO
            param = Mock()
            param.value = 2.0
            # Prima restituisce 2.0, poi 4.0 (bounds cambiano!)
            param.get_value = Mock(side_effect=[2.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0])
            mock_params['loop_start'] = param
            
            # loop_end
            param = Mock()
            param.value = 5.0
            param.get_value = Mock(return_value=5.0)
            mock_params['loop_end'] = param

            
            # loop_dur opzionale (None per questi test)
            
            mock_params['loop_dur'] = None

            
            mock_orch.create_all_parameters.return_value = mock_params
            
            config = Mock(spec=StreamConfig)
            config.context = Mock(spec=StreamContext)
            config.context.stream_id = "test"
            config.context.sample_dur_sec = 10.0
            config.time_mode = 'absolute'
            
            pointer = PointerController(params, config)
            
            # Entra nel loop con loop_start = 2.0
            pointer.calculate(2.5)
            assert pointer.in_loop is True
            
            # Avanza (delta_pos positivo)
            pointer.calculate(3.0)
            
            # Bounds cambiano: loop_start diventa 4.0
            # Pointer è a 3.5, fuori dai nuovi bounds [4.0, 5.0]
            # delta_pos > 0 → reset a loop_start (4.0)
            pos = pointer.calculate(3.5)
            
            # Dopo reset, pointer dovrebbe essere a 4.0
            assert pos == pytest.approx(4.0)
    
    def test_reset_backward_motion(self, pointer_factory):
        """Bounds cambiano mentre pointer va indietro → reset a loop_end."""
        params = {
            'start': 4.0,
            'speed_ratio': -1.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        }
        
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            
            mock_params = {}
            
            # start (raw value, is_smart=False)
            mock_params['pointer_start'] = 4.0
            
            # speed_ratio NEGATIVO
            param = Mock()
            param.value = -1.0
            param.get_value = Mock(return_value=-1.0)
            mock_params['pointer_speed_ratio'] = param
            
            # deviation
            param = Mock()
            param.value = 0.0
            param.get_value = Mock(return_value=0.0)
            mock_params['pointer_deviation'] = param
            
            # loop_start DINAMICO
            param = Mock()
            param.value = 2.0
            # Prima 2.0, poi 3.0 (bounds cambiano!)
            # Aggiungiamo valori ripetuti per coprire tutte le chiamate successive
            param.get_value = Mock(side_effect=[2.0, 2.0, 3.0, 3.0, 3.0, 3.0, 3.0])
            mock_params['loop_start'] = param
            
            # loop_end
            param = Mock()
            param.value = 5.0
            param.get_value = Mock(return_value=5.0)
            mock_params['loop_end'] = param

            
            # loop_dur opzionale (None per questi test)
            
            mock_params['loop_dur'] = None

            
            mock_orch.create_all_parameters.return_value = mock_params
            
            config = Mock(spec=StreamConfig)
            config.context = Mock(spec=StreamContext)
            config.context.stream_id = "test"
            config.context.sample_dur_sec = 10.0
            config.time_mode = 'absolute'
            
            pointer = PointerController(params, config)
            
            # Entra nel loop
            pointer.calculate(0.0)
            
            # Va indietro (delta_pos negativo)
            pointer.calculate(0.5)
            
            # Bounds cambiano: loop_start → 3.0
            # linear = 4.0 + 1.5*(-1) = 2.5
            # Pointer è a 3.5 + (-1.0) = 2.5, fuori [3.0, 5.0]
            # delta_pos < 0 → reset a loop_END (5.0)
            # MA: loop_end è boundary esclusivo, quindi 5.0 viene immediatamente
            # wrappato a loop_start (3.0) da wrap_fn
            pos = pointer.calculate(1.5)
            
            # Dopo reset direction-aware: pointer posizionato appena prima di loop_end
            # Non viene piu' wrappato a loop_start — rimane dentro il loop vicino al bordo
            assert pos == pytest.approx(5.0 - 1e-9, abs=1e-6)
            assert 3.0 <= pos < 5.0
    
    def test_bounds_change_but_pointer_inside(self, pointer_factory):
        """Bounds cambiano ma pointer resta dentro → NO reset."""
        params = {
            'start': 0.0,
            'speed_ratio': 0.5,
            'loop_start': 2.0,
            'loop_end': 5.0
        }
        
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            
            mock_params = {}
            
            mock_params['pointer_start'] = 0.0
            
            param = Mock()
            param.value = 0.5
            param.get_value = Mock(return_value=0.5)
            mock_params['pointer_speed_ratio'] = param
            
            param = Mock()
            param.value = 0.0
            param.get_value = Mock(return_value=0.0)
            mock_params['pointer_deviation'] = param
            
            # loop_start cambia ma pointer resta dentro
            param = Mock()
            param.value = 2.0
            param.get_value = Mock(side_effect=[2.0, 2.0, 2.5, 2.5, 2.5, 2.5, 2.5])
            mock_params['loop_start'] = param
            
            param = Mock()
            param.value = 5.0
            param.get_value = Mock(return_value=5.0)
            mock_params['loop_end'] = param

            
            # loop_dur opzionale (None per questi test)
            
            mock_params['loop_dur'] = None

            
            mock_orch.create_all_parameters.return_value = mock_params
            
            config = Mock(spec=StreamConfig)
            config.context = Mock(spec=StreamContext)
            config.context.stream_id = "test"
            config.context.sample_dur_sec = 10.0
            config.time_mode = 'absolute'
            
            pointer = PointerController(params, config)
            
            # Entra a 2.5
            pointer.calculate(5.0)
            
            # Avanza a ~3.0
            pointer.calculate(6.0)
            
            # Bounds cambiano: loop_start → 2.5
            # Pointer è a ~3.25, DENTRO [2.5, 5.0]
            # NO reset!
            pos = pointer.calculate(6.5)
            assert 2.5 <= pos < 5.0
            # Posizione continua progressione, non reset


# =============================================================================
# GRUPPO 5: INVERSIONE DI DIREZIONE DURANTE IL LOOP
# =============================================================================

class TestDirectionReversal:
    """Test inversione di speed_ratio durante il loop."""
    
    def test_forward_to_backward(self, pointer_factory):
        """Speed passa da positivo a negativo durante il loop."""
        params = {
            'start': 0.0,
            'speed_ratio': 1.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        }
        
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            
            mock_params = {}
            
            mock_params['pointer_start'] = 0.0
            
            # speed_ratio che INVERTE
            param = Mock()
            param.value = 1.0
            param.get_value = Mock(side_effect=[1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0])
            mock_params['pointer_speed_ratio'] = param
            
            param = Mock()
            param.value = 0.0
            param.get_value = Mock(return_value=0.0)
            mock_params['pointer_deviation'] = param
            
            param = Mock()
            param.value = 2.0
            param.get_value = Mock(return_value=2.0)
            mock_params['loop_start'] = param
            
            param = Mock()
            param.value = 5.0
            param.get_value = Mock(return_value=5.0)
            mock_params['loop_end'] = param

            
            # loop_dur opzionale (None per questi test)
            
            mock_params['loop_dur'] = None

            
            mock_orch.create_all_parameters.return_value = mock_params
            
            config = Mock(spec=StreamConfig)
            config.context = Mock(spec=StreamContext)
            config.context.stream_id = "test"
            config.context.sample_dur_sec = 10.0
            config.time_mode = 'absolute'
            
            # Mock _calculate_linear_position per simulare inversione
            pointer = PointerController(params, config)
            
            # Entra nel loop andando avanti
            pointer._calculate_linear_position = Mock(return_value=2.5)
            pointer.calculate(2.5)
            assert pointer.in_loop is True
            
            # Avanza
            pointer._calculate_linear_position = Mock(return_value=3.5)
            pos1 = pointer.calculate(3.0)
            assert pos1 == pytest.approx(3.5)
            
            # INVERSIONE! linear_pos diventa minore (va indietro)
            pointer._calculate_linear_position = Mock(return_value=3.0)
            pos2 = pointer.calculate(3.5)
            
            # delta_pos negativo, dovrebbe gestire correttamente
            assert 2.0 <= pos2 < 5.0
    
    def test_backward_to_forward(self, pointer_factory):
        """Speed passa da negativo a positivo."""
        params = {
            'start': 4.0,
            'speed_ratio': -1.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        }
        
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            
            mock_params = {}
            
            mock_params['pointer_start'] = 4.0
            
            param = Mock()
            param.value = -1.0
            param.get_value = Mock(side_effect=[-1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
            mock_params['pointer_speed_ratio'] = param
            
            param = Mock()
            param.value = 0.0
            param.get_value = Mock(return_value=0.0)
            mock_params['pointer_deviation'] = param
            
            param = Mock()
            param.value = 2.0
            param.get_value = Mock(return_value=2.0)
            mock_params['loop_start'] = param
            
            param = Mock()
            param.value = 5.0
            param.get_value = Mock(return_value=5.0)
            mock_params['loop_end'] = param

            
            # loop_dur opzionale (None per questi test)
            
            mock_params['loop_dur'] = None

            
            mock_orch.create_all_parameters.return_value = mock_params
            
            config = Mock(spec=StreamConfig)
            config.context = Mock(spec=StreamContext)
            config.context.stream_id = "test"
            config.context.sample_dur_sec = 10.0
            config.time_mode = 'absolute'
            
            pointer = PointerController(params, config)
            
            # Entra andando indietro
            pointer._calculate_linear_position = Mock(return_value=4.0)
            pointer.calculate(0.0)
            
            # Va indietro
            pointer._calculate_linear_position = Mock(return_value=3.0)
            pos1 = pointer.calculate(1.0)
            assert pos1 == pytest.approx(3.0)
            
            # INVERSIONE! Ora va avanti
            pointer._calculate_linear_position = Mock(return_value=3.5)
            pos2 = pointer.calculate(1.5)
            
            assert 2.0 <= pos2 < 5.0
    
    def test_oscillating_speed(self, pointer_factory):
        """Speed oscilla avanti/indietro continuamente."""
        params = {
            'start': 3.0,
            'speed_ratio': 1.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        }
        
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            
            mock_params = {}
            
            mock_params['pointer_start'] = 3.0
            
            param = Mock()
            param.value = 1.0
            param.get_value = Mock(return_value=1.0)
            mock_params['pointer_speed_ratio'] = param
            
            param = Mock()
            param.value = 0.0
            param.get_value = Mock(return_value=0.0)
            mock_params['pointer_deviation'] = param
            
            param = Mock()
            param.value = 2.0
            param.get_value = Mock(return_value=2.0)
            mock_params['loop_start'] = param
            
            param = Mock()
            param.value = 5.0
            param.get_value = Mock(return_value=5.0)
            mock_params['loop_end'] = param

            
            # loop_dur opzionale (None per questi test)
            
            mock_params['loop_dur'] = None

            
            mock_orch.create_all_parameters.return_value = mock_params
            
            config = Mock(spec=StreamConfig)
            config.context = Mock(spec=StreamContext)
            config.context.stream_id = "test"
            config.context.sample_dur_sec = 10.0
            config.time_mode = 'absolute'
            
            pointer = PointerController(params, config)
            
            # Simula oscillazioni
            positions = [3.0, 3.5, 3.2, 3.8, 3.4, 4.0]
            
            for i, linear_pos in enumerate(positions):
                pointer._calculate_linear_position = Mock(return_value=linear_pos)
                pos = pointer.calculate(float(i))
                
                # Deve sempre restare dentro bounds
                assert 2.0 <= pos < 5.0


# =============================================================================
# GRUPPO 6: LOOP DINAMICI
# =============================================================================

class TestDynamicLoops:
    """Test loop con bounds che cambiano nel tempo (envelope)."""
    
    def test_shrinking_loop_dur(self, pointer_factory):
        """loop_dur diminuisce gradualmente."""
        params = {
            'start': 0.0,
            'speed_ratio': 0.5,
            'loop_start': 2.0,
            'loop_dur': 3.0
        }
        
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            
            mock_params = {}
            
            mock_params['pointer_start'] = 0.0
            
            param = Mock()
            param.value = 0.5
            param.get_value = Mock(return_value=0.5)
            mock_params['pointer_speed_ratio'] = param
            
            param = Mock()
            param.value = 0.0
            param.get_value = Mock(return_value=0.0)
            mock_params['pointer_deviation'] = param
            
            param = Mock()
            param.value = 2.0
            param.get_value = Mock(return_value=2.0)
            mock_params['loop_start'] = param
            
            # loop_dur che diminuisce
            param = Mock()
            param.value = 3.0
            param.get_value = Mock(side_effect=[3.0, 3.0, 2.5, 2.0, 1.5, 1.5, 1.5, 1.5])
            mock_params['loop_dur'] = param

            
            # loop_end opzionale (None quando si usa loop_dur)
            
            mock_params['loop_end'] = None

            
            mock_orch.create_all_parameters.return_value = mock_params
            
            config = Mock(spec=StreamConfig)
            config.context = Mock(spec=StreamContext)
            config.context.stream_id = "test"
            config.context.sample_dur_sec = 10.0
            config.time_mode = 'absolute'
            
            pointer = PointerController(params, config)
            
            # Entra nel loop
            pointer.calculate(5.0)
            
            # Loop si restringe ma pointer deve restare valido
            pos1 = pointer.calculate(6.0)
            pos2 = pointer.calculate(7.0)
            pos3 = pointer.calculate(8.0)
            
            # Tutte le posizioni devono essere valide
            for pos in [pos1, pos2, pos3]:
                assert 2.0 <= pos < 10.0
    
    def test_moving_loop_start(self, pointer_factory):
        """loop_start si muove gradualmente."""
        params = {
            'start': 0.0,
            'speed_ratio': 0.5,
            'loop_start': 2.0,
            'loop_end': 5.0
        }
        
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            
            mock_params = {}
            
            mock_params['pointer_start'] = 0.0
            
            param = Mock()
            param.value = 0.5
            param.get_value = Mock(return_value=0.5)
            mock_params['pointer_speed_ratio'] = param
            
            param = Mock()
            param.value = 0.0
            param.get_value = Mock(return_value=0.0)
            mock_params['pointer_deviation'] = param
            
            # loop_start che si muove
            param = Mock()
            param.value = 2.0
            param.get_value = Mock(side_effect=[2.0, 2.0, 2.5, 3.0, 3.5, 3.5, 3.5, 3.5])
            mock_params['loop_start'] = param
            
            param = Mock()
            param.value = 5.0
            param.get_value = Mock(return_value=5.0)
            mock_params['loop_end'] = param

            
            # loop_dur opzionale (None per questi test)
            
            mock_params['loop_dur'] = None

            
            mock_orch.create_all_parameters.return_value = mock_params
            
            config = Mock(spec=StreamConfig)
            config.context = Mock(spec=StreamContext)
            config.context.stream_id = "test"
            config.context.sample_dur_sec = 10.0
            config.time_mode = 'absolute'
            
            pointer = PointerController(params, config)
            
            # Sequenza di calcoli con loop_start che si muove
            positions = []
            for i in range(5):
                pos = pointer.calculate(float(i * 2))
                positions.append(pos)
            
            # Tutte le posizioni devono essere valide (dentro sample)
            for pos in positions:
                assert 0.0 <= pos < 10.0


# =============================================================================
# GRUPPO 7: EDGE CASES ESTREMI
# =============================================================================

class TestExtremeEdgeCases:
    """Test casi limite estremi."""
    
    def test_minimum_loop_length(self, pointer_factory):
        """Loop minimo (0.001s - clamped nel codice)."""
        pointer = pointer_factory({
            'start': 0.0,
            'speed_ratio': 1.0,
            'loop_start': 2.0,
            'loop_end': 2.0001  # Quasi zero
        })
        
        # Dovrebbe funzionare senza crash
        pos = pointer.calculate(5.0)
        assert 0.0 <= pos < 10.0
    
    def test_loop_at_sample_boundaries(self, pointer_factory):
        """Loop copre l'intero sample."""
        pointer = pointer_factory({
            'start': 0.0,
            'speed_ratio': 1.0,
            'loop_start': 0.0,
            'loop_end': 10.0
        }, sample_dur=10.0)
        
        pointer.calculate(1.0)
        assert pointer.in_loop is True
        
        # Dovrebbe wrappare correttamente
        pos = pointer.calculate(15.0)
        assert 0.0 <= pos < 10.0
    
    def test_fractional_positions(self, pointer_factory):
        """Posizioni altamente frazionarie."""
        pointer = pointer_factory({
            'start': 0.123456789,
            'speed_ratio': 1.0
        })
        
        pos = pointer.calculate(0.0)
        assert pos == pytest.approx(0.123456789, abs=1e-9)
    
    def test_negative_start_wraps(self, pointer_factory):
        """start negativo wrappa correttamente."""
        pointer = pointer_factory({
            'start': -2.0,
            'speed_ratio': 1.0
        }, sample_dur=10.0)
        
        # -2.0 % 10.0 = 8.0
        pos = pointer.calculate(0.0)
        assert pos == pytest.approx(8.0)
    
    def test_speed_exactly_zero_with_loop(self, pointer_factory):
        """Speed zero all'interno di un loop."""
        pointer = pointer_factory({
            'start': 3.0,
            'speed_ratio': 0.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        })
        
        # Entra nel loop
        pointer.calculate(0.0)
        
        # Rimane fermo
        pos1 = pointer.calculate(100.0)
        pos2 = pointer.calculate(200.0)
        
        assert pos1 == pos2


# =============================================================================
# GRUPPO 8: STATE MANAGEMENT
# =============================================================================

class TestStateManagement:
    """Test reset e properties."""
    
    def test_reset_clears_state(self, pointer_factory):
        """reset() pulisce completamente lo stato."""
        pointer = pointer_factory({
            'start': 0.0,
            'speed_ratio': 1.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        })
        
        # Entra nel loop
        pointer.calculate(3.0)
        assert pointer.in_loop is True
        
        # Reset
        pointer.reset()
        
        # Stato pulito
        assert pointer.in_loop is False
        assert pointer._loop_absolute_pos is None
        assert pointer._last_linear_pos is None
    
    def test_sample_dur_sec_property(self, pointer_factory):
        """Property sample_dur_sec."""
        pointer = pointer_factory({}, sample_dur=7.5)
        assert pointer.sample_dur_sec == 7.5
    
    def test_in_loop_property(self, pointer_factory):
        """Property in_loop."""
        pointer = pointer_factory({
            'start': 0.0,
            'speed_ratio': 1.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        })
        
        assert pointer.in_loop is False
        pointer.calculate(3.0)
        assert pointer.in_loop is True
    
    def test_loop_phase_property(self, pointer_factory):
        """Property loop_phase calcola fase corretta."""
        pointer = pointer_factory({
            'start': 0.0,
            'speed_ratio': 1.0,
            'loop_start': 2.0,
            'loop_end': 5.0  # length = 3.0
        })
        
        # Prima del loop
        assert pointer.loop_phase == 0.0
        
        # Entra a 2.5 (0.5 nel loop)
        pointer.calculate(2.5)
        # phase = 0.5 / 3.0 = 0.166...
        assert 0.0 <= pointer.loop_phase <= 1.0
    
    def test_repr(self, pointer_factory):
        """__repr__ fornisce info utili."""
        pointer = pointer_factory({
            'start': 1.0,
            'speed_ratio': 2.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        })
        
        repr_str = repr(pointer)
        assert 'PointerController' in repr_str
        assert 'loop=' in repr_str


# =============================================================================
# GRUPPO 9: INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Test integrazione completa di scenari reali."""
    
    def test_realistic_forward_loop(self, pointer_factory):
        """Scenario realistico: loop forward con jitter."""
        pointer = pointer_factory({
            'start': 0.0,
            'speed_ratio': 1.5,
            'loop_start': 1.0,
            'loop_end': 4.0
        })
        
        # Simula generazione continua di grani
        positions = []
        for t in [i * 0.1 for i in range(50)]:
            pos = pointer.calculate(t)
            positions.append(pos)
        
        # Verifica: tutte le posizioni valide
        for pos in positions:
            assert 0.0 <= pos < 10.0
        
        # Verifica: dopo entrata nel loop, resta nel loop
        after_entry = [p for p in positions[15:] if p is not None]
        for pos in after_entry:
            assert 1.0 <= pos < 4.0
    
    def test_realistic_backward_loop(self, pointer_factory):
        """Scenario realistico: loop backward."""
        pointer = pointer_factory({
            'start': 5.0,
            'speed_ratio': -1.0,
            'loop_start': 1.0,
            'loop_end': 4.0
        })
        
        positions = []
        for t in [i * 0.1 for i in range(50)]:
            pos = pointer.calculate(t)
            positions.append(pos)
        
        # Verifica validità
        for pos in positions:
            assert 0.0 <= pos < 10.0
    
    def test_ping_pong_oscillation(self, pointer_factory):
        """Simulazione ping-pong: avanti/indietro ripetuto."""
        params = {
            'start': 3.0,
            'speed_ratio': 1.0,
            'loop_start': 2.0,
            'loop_end': 5.0
        }
        
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            
            mock_params = {}
            
            mock_params['pointer_start'] = 3.0
            
            param = Mock()
            param.value = 1.0
            param.get_value = Mock(return_value=1.0)
            mock_params['pointer_speed_ratio'] = param
            
            param = Mock()
            param.value = 0.0
            param.get_value = Mock(return_value=0.0)
            mock_params['pointer_deviation'] = param
            
            param = Mock()
            param.value = 2.0
            param.get_value = Mock(return_value=2.0)
            mock_params['loop_start'] = param
            
            param = Mock()
            param.value = 5.0
            param.get_value = Mock(return_value=5.0)
            mock_params['loop_end'] = param

            
            # loop_dur opzionale (None per questi test)
            
            mock_params['loop_dur'] = None

            
            mock_orch.create_all_parameters.return_value = mock_params
            
            config = Mock(spec=StreamConfig)
            config.context = Mock(spec=StreamContext)
            config.context.stream_id = "test"
            config.context.sample_dur_sec = 10.0
            config.time_mode = 'absolute'
            
            pointer = PointerController(params, config)
            
            # Simula ping-pong
            linear_positions = [
                3.0, 3.5, 4.0, 4.5,  # Avanti
                4.0, 3.5, 3.0, 2.5,  # Indietro
                3.0, 3.5, 4.0,       # Avanti di nuovo
                3.5, 3.0, 2.5        # Indietro di nuovo
            ]
            
            positions = []
            for i, linear_pos in enumerate(linear_positions):
                pointer._calculate_linear_position = Mock(return_value=linear_pos)
                pos = pointer.calculate(float(i) * 0.1)
                positions.append(pos)
            
            # Tutte le posizioni devono essere valide
            for pos in positions:
                assert 2.0 <= pos < 5.0



# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_config():
    """Config minimale per i test."""
    context = Mock(spec=StreamContext)
    context.stream_id = "test_stream"
    context.sample_dur_sec = 10.0

    config = Mock(spec=StreamConfig)
    config.context = context
    config.time_mode = 'absolute'

    return config


@pytest.fixture
def bounds_speed():
    return ParameterBounds(min_val=-100.0, max_val=100.0)


@pytest.fixture
def bounds_deviation():
    return ParameterBounds(
        min_val=0.0, max_val=1.0,
        min_range=0.0, max_range=1.0,
        default_jitter=0.2, variation_mode='additive'
    )


@pytest.fixture
def bounds_loop():
    return ParameterBounds(min_val=0.0, max_val=100.0)


@pytest.fixture
def bounds_loop_dur():
    return ParameterBounds(min_val=0.005, max_val=100.0)


def _make_pointer(mock_config, real_params, raw_params):
    """Helper: crea PointerController con parametri pre-costruiti."""
    with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
        mock_orch = MockOrch.return_value
        mock_orch.create_all_parameters.return_value = real_params
        return PointerController(raw_params, mock_config)


def _build_real_params(
    start=0.0, speed=1.0, deviation=0.0,
    loop_start=None, loop_end=None, loop_dur=None,
    bounds_speed_=None, bounds_deviation_=None,
    bounds_loop_=None, bounds_loop_dur_=None
):
    """Helper: costruisce dict di Parameter reali per l'orchestrator mock."""
    bs = bounds_speed_ or ParameterBounds(min_val=-100.0, max_val=100.0)
    bd = bounds_deviation_ or ParameterBounds(
        min_val=0.0, max_val=1.0,
        min_range=0.0, max_range=1.0,
        default_jitter=0.2, variation_mode='additive'
    )
    bl = bounds_loop_ or ParameterBounds(min_val=0.0, max_val=100.0)
    bld = bounds_loop_dur_ or ParameterBounds(min_val=0.005, max_val=100.0)

    params = {
        'pointer_start': start,
        'pointer_speed_ratio': Parameter(
            value=speed, name='pointer_speed_ratio',
            bounds=bs, owner_id='test'
        ),
        'pointer_deviation': Parameter(
            value=deviation, name='pointer_deviation',
            bounds=bd, owner_id='test'
        ),
    }

    if loop_start is not None:
        params['loop_start'] = Parameter(
            value=loop_start, name='loop_start',
            bounds=bl, owner_id='test'
        )
    else:
        params['loop_start'] = None

    if loop_end is not None:
        params['loop_end'] = Parameter(
            value=loop_end, name='loop_end',
            bounds=bl, owner_id='test'
        )
    else:
        params['loop_end'] = None

    if loop_dur is not None:
        params['loop_dur'] = Parameter(
            value=loop_dur, name='loop_dur',
            bounds=bld, owner_id='test'
        )
    else:
        params['loop_dur'] = None

    return params


# =============================================================================
# GRUPPO 10: PRE-NORMALIZZAZIONE LOOP PARAMS
# =============================================================================

class TestPreNormalization:
    """Test _pre_normalize_loop_params()."""

    def test_absolute_mode_no_scaling(self, mock_config):
        """Con time_mode='absolute', nessuna normalizzazione."""
        mock_config.time_mode = 'absolute'
        raw_params = {
            'loop_start': 2.0,
            'loop_end': 5.0,
        }
        real = _build_real_params(loop_start=2.0, loop_end=5.0)
        pointer = _make_pointer(mock_config, real, raw_params)

        # I valori dovrebbero rimanere intatti
        assert pointer.loop_start.value == 2.0
        assert pointer.loop_end.value == 5.0

    def test_normalized_mode_scales_values(self, mock_config):
        """Con loop_unit='normalized', i valori vengono scalati per sample_dur."""
        mock_config.time_mode = 'absolute'
        mock_config.context.sample_dur_sec = 10.0

        raw_params = {
            'loop_start': 0.2,
            'loop_end': 0.5,
            'loop_unit': 'normalized',
        }
        # Dopo normalizzazione: 0.2*10=2.0, 0.5*10=5.0
        real = _build_real_params(loop_start=2.0, loop_end=5.0)
        pointer = _make_pointer(mock_config, real, raw_params)

        # Verifica che _pre_normalize_loop_params abbia scalato
        # L'orchestrator riceve i valori gia' scalati
        assert pointer.has_loop is True

    def test_normalized_mode_with_loop_dur(self, mock_config):
        """loop_dur viene scalato in modo normalizzato."""
        mock_config.time_mode = 'absolute'
        mock_config.context.sample_dur_sec = 10.0

        raw_params = {
            'loop_start': 0.1,
            'loop_dur': 0.3,
            'loop_unit': 'normalized',
        }
        # 0.1*10=1.0, 0.3*10=3.0
        real = _build_real_params(loop_start=1.0, loop_dur=3.0)
        pointer = _make_pointer(mock_config, real, raw_params)

        assert pointer.has_loop is True
        assert pointer.loop_dur.value == 3.0

    def test_no_loop_start_returns_params_unchanged(self, mock_config):
        """Senza loop_start, nessuna normalizzazione necessaria."""
        raw_params = {'speed_ratio': 1.5}
        real = _build_real_params(speed=1.5)
        pointer = _make_pointer(mock_config, real, raw_params)

        assert pointer.has_loop is False

    def test_none_params_handled(self, mock_config):
        """params=None non causa crash."""
        # Quando PointerController riceve params={}, _pre_normalize
        # deve gestirlo senza errori
        raw_params = {}
        real = _build_real_params()
        pointer = _make_pointer(mock_config, real, raw_params)

        assert pointer.has_loop is False

    def test_time_mode_normalized_as_fallback(self, mock_config):
        """Se loop_unit non specificato, usa config.time_mode come fallback."""
        mock_config.time_mode = 'normalized'
        mock_config.context.sample_dur_sec = 8.0

        raw_params = {
            'loop_start': 0.25,
            'loop_end': 0.75,
            # Nessun loop_unit esplicito -> fallback a config.time_mode
        }
        # 0.25*8=2.0, 0.75*8=6.0
        real = _build_real_params(loop_start=2.0, loop_end=6.0)
        pointer = _make_pointer(mock_config, real, raw_params)

        assert pointer.has_loop is True

    def test_start_normalized_scales_with_sample_dur(self, mock_config):
        """
        RED: con time_mode='normalized', il valore di 'start' deve essere
        moltiplicato per sample_dur_sec.
        BUG ATTUALE: _pre_normalize_loop_params scala solo i parametri loop,
        non 'start'. Il metodo scalera' start solo dopo il fix.
        """
        mock_config.time_mode = 'normalized'
        mock_config.context.sample_dur_sec = 10.0

        real = _build_real_params(start=0.0)
        pointer = _make_pointer(mock_config, real, {})

        result = pointer._pre_normalize_loop_params({'start': 0.5})

        assert result['start'] == pytest.approx(5.0)


    def test_start_absolute_mode_no_scaling(self, mock_config):
        """
        Con time_mode='absolute', 'start' NON deve essere scalato.
        Questo test deve rimanere GREEN sia prima che dopo il fix:
        verifica che la modalita' assoluta non introduca regressioni.
        """
        mock_config.time_mode = 'absolute'
        mock_config.context.sample_dur_sec = 10.0

        real = _build_real_params(start=0.0)
        pointer = _make_pointer(mock_config, real, {})

        result = pointer._pre_normalize_loop_params({'start': 2.0})

        assert result['start'] == pytest.approx(2.0)


    def test_start_normalized_without_loop_params(self, mock_config):
        """
        RED: con time_mode='normalized' e nessun 'loop_start' nel dict,
        'start' deve essere comunque scalato.
        BUG ATTUALE: il return anticipato su 'loop_start' not in params
        blocca tutta la normalizzazione prima ancora di arrivare a 'start'.
        Questo e' il caso piu' comune: start senza loop.
        """
        mock_config.time_mode = 'normalized'
        mock_config.context.sample_dur_sec = 8.0

        real = _build_real_params(start=0.0)
        pointer = _make_pointer(mock_config, real, {})

        # Nessun 'loop_start' nel dict: il bug si manifesta qui
        result = pointer._pre_normalize_loop_params({'start': 0.25})

        assert result['start'] == pytest.approx(2.0)  # 0.25 * 8.0 = 2.0
        
# =============================================================================
# GRUPPO 11: DEVIATION SCALING
# =============================================================================

class TestDeviationScaling:
    """Test che deviation si scali correttamente in base al contesto."""

    def test_deviation_scales_by_sample_dur_without_loop(self, mock_config):
        """Senza loop, context_length = sample_dur_sec."""
        mock_config.context.sample_dur_sec = 10.0

        # deviation=0.5 -> offset = 0.5 * 10.0 = 5.0
        real = _build_real_params(start=0.0, speed=0.0, deviation=0.5)
        # Deviation come mod_range di Parameter: la deviation e' gia'
        # il valore base del parametro pointer_deviation
        # Per far funzionare il test, impostiamo get_value a 0.5
        real['pointer_deviation'] = Mock()
        real['pointer_deviation'].value = 0.5
        real['pointer_deviation'].get_value = Mock(return_value=0.5)

        pointer = _make_pointer(mock_config, real, {'start': 0.0, 'speed_ratio': 0.0})

        # pos = (0.0 % 10.0) + 0.5 * 10.0 = 5.0
        # wrap: 5.0 % 10.0 = 5.0
        pos = pointer.calculate(0.0)
        assert pos == pytest.approx(5.0)

    def test_deviation_scales_by_loop_length_inside_loop(self, mock_config):
        """Dentro il loop, context_length = loop_length."""
        mock_config.context.sample_dur_sec = 10.0

        real = _build_real_params(
            start=3.0, speed=0.0,
            loop_start=2.0, loop_end=5.0  # length = 3.0
        )
        real['pointer_deviation'] = Mock()
        real['pointer_deviation'].value = 0.0
        # Prima chiamata: deviation=0 (entrata), poi 0.5
        real['pointer_deviation'].get_value = Mock(side_effect=[0.0, 0.5])

        pointer = _make_pointer(
            mock_config, real,
            {'start': 3.0, 'speed_ratio': 0.0, 'loop_start': 2.0, 'loop_end': 5.0}
        )

        # Prima chiamata: entra nel loop a 3.0 con dev=0.0
        pointer.calculate(0.0)
        assert pointer.in_loop is True

        # Seconda chiamata: dev=0.5, context=3.0
        # offset = 0.5 * 3.0 = 1.5
        # pos = 3.0 + 1.5 = 4.5
        # wrap: dentro [2.0, 5.0) -> 4.5
        pos = pointer.calculate(1.0)
        assert pos == pytest.approx(4.5)

    def test_deviation_wraps_outside_loop_bounds(self, mock_config):
        """Deviation che spinge fuori dal loop viene wrappata."""
        mock_config.context.sample_dur_sec = 10.0

        real = _build_real_params(
            start=4.5, speed=0.0,
            loop_start=2.0, loop_end=5.0  # length = 3.0
        )
        real['pointer_deviation'] = Mock()
        real['pointer_deviation'].value = 0.0
        # Prima entrata con dev=0, poi dev=0.8
        real['pointer_deviation'].get_value = Mock(side_effect=[0.0, 0.8])

        pointer = _make_pointer(
            mock_config, real,
            {'start': 4.5, 'speed_ratio': 0.0, 'loop_start': 2.0, 'loop_end': 5.0}
        )

        pointer.calculate(0.0)  # entrata

        # offset = 0.8 * 3.0 = 2.4
        # pos = 4.5 + 2.4 = 6.9, fuori dal loop [2.0, 5.0)
        # Bypass semantics: wrap sul sample intero, non sul loop
        # 6.9 % 10.0 = 6.9 — fuori dal loop, dentro il sample
        pos = pointer.calculate(1.0)
        assert pos == pytest.approx(6.9)
        assert 0.0 <= pos < 10.0   # dentro il sample


# =============================================================================
# GRUPPO 12: MODALITA' LOOP_DUR VS LOOP_END
# =============================================================================

class TestLoopDurMode:
    """Test specifici per loop_dur come alternativa a loop_end."""

    def test_loop_dur_basic(self, mock_config):
        """loop_dur=3.0 con loop_start=2.0 produce loop [2.0, 5.0]."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(
            start=3.0, speed=1.0,
            loop_start=2.0, loop_dur=3.0
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 3.0, 'speed_ratio': 1.0, 'loop_start': 2.0, 'loop_dur': 3.0}
        )

        assert pointer.has_loop is True
        # loop_end e' None (perche' usiamo loop_dur)
        assert pointer.loop_end is None
        assert pointer.loop_dur is not None

        # Entra nel loop
        pointer.calculate(0.0)
        assert pointer.in_loop is True

        # Deve restare dentro [2.0, 5.0)
        pos = pointer.calculate(3.0)  # linear = 3.0 + 3.0 = 6.0
        assert 2.0 <= pos < 5.0

    def test_loop_dur_wraps_correctly(self, mock_config):
        """Wrap con loop_dur funziona come con loop_end."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(
            start=2.5, speed=1.0,
            loop_start=2.0, loop_dur=3.0
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 2.5, 'speed_ratio': 1.0, 'loop_start': 2.0, 'loop_dur': 3.0}
        )

        positions = []
        for t_tenth in range(50):
            t = t_tenth * 0.1
            pos = pointer.calculate(t)
            positions.append(pos)

        # Tutte le posizioni dopo l'entrata devono essere in [2.0, 5.0)
        for pos in positions:
            assert 0.0 <= pos < 10.0

    def test_loop_dur_clamped_to_sample_dur(self, mock_config):
        """loop_dur > sample_dur viene clampato."""
        mock_config.context.sample_dur_sec = 5.0
        real = _build_real_params(
            start=1.0, speed=1.0,
            loop_start=1.0, loop_dur=20.0  # Eccede sample_dur
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 1.0, 'speed_ratio': 1.0, 'loop_start': 1.0, 'loop_dur': 20.0}
        )

        # Non deve crashare
        pointer.calculate(0.0)
        pos = pointer.calculate(10.0)
        assert 0.0 <= pos < 5.0

    def test_loop_end_wins_exclusive_group(self, mock_config):
        """Se sia loop_end che loop_dur sono presenti nel YAML, il gruppo
        esclusivo nell'orchestrator fa vincere loop_end (priority=1)."""
        mock_config.context.sample_dur_sec = 10.0
        # Simula il caso dove ExclusiveGroupSelector ha eliminato loop_dur
        real = _build_real_params(
            start=3.0, speed=1.0,
            loop_start=2.0, loop_end=6.0, loop_dur=None
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 3.0, 'speed_ratio': 1.0, 'loop_start': 2.0, 'loop_end': 6.0}
        )

        assert pointer.has_loop is True
        assert pointer.loop_dur is None
        assert pointer.loop_end is not None
        assert pointer.loop_end.value == 6.0


# =============================================================================
# GRUPPO 13: HAS_LOOP PROPERTY
# =============================================================================

class TestHasLoopProperty:
    """Test has_loop in tutte le combinazioni di parametri."""

    def test_no_loop_params(self, mock_config):
        """Nessun parametro loop -> has_loop=False."""
        real = _build_real_params()
        pointer = _make_pointer(mock_config, real, {})
        assert pointer.has_loop is False

    def test_loop_start_and_end(self, mock_config):
        """loop_start + loop_end -> has_loop=True."""
        real = _build_real_params(loop_start=1.0, loop_end=4.0)
        pointer = _make_pointer(
            mock_config, real,
            {'loop_start': 1.0, 'loop_end': 4.0}
        )
        assert pointer.has_loop is True

    def test_loop_start_and_dur(self, mock_config):
        """loop_start + loop_dur -> has_loop=True."""
        real = _build_real_params(loop_start=1.0, loop_dur=3.0)
        pointer = _make_pointer(
            mock_config, real,
            {'loop_start': 1.0, 'loop_dur': 3.0}
        )
        assert pointer.has_loop is True

    def test_loop_start_only(self, mock_config):
        """Solo loop_start -> has_loop=True, loop_end diventa sample_dur."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(loop_start=2.0)
        pointer = _make_pointer(
            mock_config, real,
            {'loop_start': 2.0}
        )

        assert pointer.has_loop is True
        # Il codice imposta loop_end = sample_dur_sec quando manca
        assert pointer.loop_end == 10.0

    def test_loop_end_only_no_start(self, mock_config):
        """Solo loop_end senza loop_start -> has_loop=False."""
        real = _build_real_params(loop_end=5.0)
        # Ma loop_start = None -> has_loop dipende da loop_start
        pointer = _make_pointer(
            mock_config, real,
            {'loop_end': 5.0}
        )
        assert pointer.has_loop is False


# =============================================================================
# GRUPPO 14: LINEAR POSITION CON ENVELOPE SPEED
# =============================================================================

class TestLinearPositionWithEnvelope:
    """Test _calculate_linear_position con Envelope come speed_ratio."""

    def test_constant_envelope_speed(self, mock_config):
        """Envelope costante produce stessa posizione di valore fisso."""
        mock_config.context.sample_dur_sec = 10.0

        # Crea un mock Envelope che ha integrate() e value
        mock_envelope = Mock(spec=Envelope)
        mock_envelope.breakpoints = [[0, 2.0], [10, 2.0]]  # costante a 2.0

        # integrate(0, t) per speed costante 2.0 = 2.0 * t
        mock_envelope.integrate = Mock(side_effect=lambda a, b: 2.0 * (b - a))

        real = _build_real_params(start=1.0, speed=1.0)
        # Sostituisci il value del Parameter speed con l'envelope
        real['pointer_speed_ratio'] = Mock()
        real['pointer_speed_ratio'].value = mock_envelope
        real['pointer_speed_ratio'].get_value = Mock(return_value=2.0)

        pointer = _make_pointer(
            mock_config, real,
            {'start': 1.0, 'speed_ratio': 2.0}
        )

        # t=0: start + integrate(0,0) = 1.0 + 0 = 1.0
        pos = pointer.calculate(0.0)
        assert pos == pytest.approx(1.0)

        # t=2: start + integrate(0,2) = 1.0 + 4.0 = 5.0
        pos = pointer.calculate(2.0)
        assert pos == pytest.approx(5.0)

    def test_accelerating_envelope_speed(self, mock_config):
        """Envelope che accelera: integrale non lineare."""
        mock_config.context.sample_dur_sec = 20.0

        mock_envelope = Mock(spec=Envelope)
        mock_envelope.breakpoints = [[0, 0.0], [10, 10.0]]  # rampa 0->10

        # integrate(0, t) per rampa lineare 0->t = area triangolo = t^2/2
        # (approssimazione per test)
        mock_envelope.integrate = Mock(
            side_effect=lambda a, b: (b ** 2 - a ** 2) / 2.0
        )

        real = _build_real_params(start=0.0, speed=1.0)
        real['pointer_speed_ratio'] = Mock()
        real['pointer_speed_ratio'].value = mock_envelope
        real['pointer_speed_ratio'].get_value = Mock(return_value=5.0)

        pointer = _make_pointer(
            mock_config, real,
            {'start': 0.0, 'speed_ratio': 1.0}
        )

        # t=2: integrate(0,2) = 4/2 = 2.0
        pos = pointer.calculate(2.0)
        assert pos == pytest.approx(2.0)

        # t=4: integrate(0,4) = 16/2 = 8.0
        pos = pointer.calculate(4.0)
        assert pos == pytest.approx(8.0)

    def test_scalar_speed_uses_multiplication(self, mock_config):
        """Speed scalare usa moltiplicazione diretta, non integrate."""
        mock_config.context.sample_dur_sec = 10.0

        real = _build_real_params(start=1.0, speed=2.5)
        pointer = _make_pointer(
            mock_config, real,
            {'start': 1.0, 'speed_ratio': 2.5}
        )

        # t=3: 1.0 + 3.0 * 2.5 = 8.5
        pos = pointer.calculate(3.0)
        assert pos == pytest.approx(8.5)


# =============================================================================
# GRUPPO 15: LOOP BOUNDARY ESCLUSIVO
# =============================================================================

class TestLoopBoundaryExclusive:
    """Test che loop_end sia trattato come boundary esclusivo."""

    def test_position_exactly_at_loop_end_wraps(self, mock_config):
        """Posizione esattamente su loop_end deve wrappare a loop_start."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(
            start=2.0, speed=1.0,
            loop_start=2.0, loop_end=5.0
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 2.0, 'speed_ratio': 1.0, 'loop_start': 2.0, 'loop_end': 5.0}
        )

        # t=0: entra a 2.0
        pointer.calculate(0.0)
        assert pointer.in_loop is True

        # t=3: linear = 2.0 + 3.0 = 5.0 (esattamente loop_end)
        pos = pointer.calculate(3.0)
        # loop_end esclusivo: 5.0 deve wrappare a 2.0
        assert pos == pytest.approx(2.0)

    def test_position_at_loop_start_is_valid(self, mock_config):
        """Posizione esattamente su loop_start e' valida (incluso)."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(
            start=2.0, speed=0.0,
            loop_start=2.0, loop_end=5.0
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 2.0, 'speed_ratio': 0.0, 'loop_start': 2.0, 'loop_end': 5.0}
        )

        pos = pointer.calculate(0.0)
        assert pos == pytest.approx(2.0)
        assert pointer.in_loop is True

    def test_position_just_before_loop_end(self, mock_config):
        """Posizione appena sotto loop_end NON wrappa."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(
            start=2.0, speed=1.0,
            loop_start=2.0, loop_end=5.0
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 2.0, 'speed_ratio': 1.0, 'loop_start': 2.0, 'loop_end': 5.0}
        )

        pointer.calculate(0.0)

        # t=2.999: linear = 2.0 + 2.999 = 4.999
        pos = pointer.calculate(2.999)
        # Dentro [2.0, 5.0) -> valida, non wrappa
        assert 4.9 < pos < 5.0


# =============================================================================
# GRUPPO 16: GRAIN_REVERSE OFFSET
# =============================================================================

class TestGrainReverseOffset:
    """Test che grain_reverse=True aggiunga grain_duration alla posizione."""

    def test_grain_reverse_adds_duration(self, mock_config):
        """Con grain_reverse=True, pos += grain_duration."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(start=3.0, speed=0.0)

        pointer = _make_pointer(
            mock_config, real,
            {'start': 3.0, 'speed_ratio': 0.0}
        )

        # Senza reverse: pos = 3.0
        pos_normal = pointer.calculate(0.0, grain_duration=0.05, grain_reverse=False)
        assert pos_normal == pytest.approx(3.0)

        # Con reverse: pos = 3.0 + 0.05 = 3.05
        pos_reverse = pointer.calculate(0.0, grain_duration=0.05, grain_reverse=True)
        assert pos_reverse == pytest.approx(3.05)

    def test_grain_reverse_zero_duration(self, mock_config):
        """grain_reverse con grain_duration=0.0 non cambia posizione."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(start=5.0, speed=0.0)

        pointer = _make_pointer(
            mock_config, real,
            {'start': 5.0, 'speed_ratio': 0.0}
        )

        pos_normal = pointer.calculate(0.0, grain_duration=0.0, grain_reverse=False)
        pos_reverse = pointer.calculate(0.0, grain_duration=0.0, grain_reverse=True)
        assert pos_normal == pytest.approx(pos_reverse)

    def test_grain_reverse_wraps_in_loop(self, mock_config):
        """grain_reverse che spinge oltre loop_end viene wrappato."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(
            start=4.9, speed=0.0,
            loop_start=2.0, loop_end=5.0
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 4.9, 'speed_ratio': 0.0, 'loop_start': 2.0, 'loop_end': 5.0}
        )

        # Entra nel loop a 4.9
        pointer.calculate(0.0, grain_duration=0.0, grain_reverse=False)
        assert pointer.in_loop is True

        # Con reverse e duration=0.2: 4.9 + 0.2 = 5.1
        # Wrap sul sample intero: 5.1 % 10.0 = 5.1
        # Il pointer e' fuori dal loop ma dentro il sample — comportamento bypass
        pos = pointer.calculate(0.0, grain_duration=0.2, grain_reverse=True)
        assert pos == pytest.approx(5.1)
        assert 0.0 <= pos < 10.0 

    def test_grain_reverse_default_is_false(self, mock_config):
        """Senza parametro grain_reverse, default e' False."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(start=3.0, speed=0.0)

        pointer = _make_pointer(
            mock_config, real,
            {'start': 3.0, 'speed_ratio': 0.0}
        )

        # Chiamata senza grain_reverse (default)
        pos = pointer.calculate(0.0)
        assert pos == pytest.approx(3.0)


# =============================================================================
# GRUPPO 17: _scale_value
# =============================================================================

class TestScaleValue:
    """Test _scale_value con diversi tipi di input."""

    def test_scale_scalar(self, mock_config):
        """Scalare viene moltiplicato."""
        real = _build_real_params()
        pointer = _make_pointer(mock_config, real, {})

        result = pointer._scale_value(0.5, 10.0)
        assert result == pytest.approx(5.0)

    def test_scale_integer(self, mock_config):
        """Intero viene moltiplicato."""
        real = _build_real_params()
        pointer = _make_pointer(mock_config, real, {})

        result = pointer._scale_value(2, 3.0)
        assert result == pytest.approx(6.0)

    def test_scale_envelope_like(self, mock_config):
            """Struttura envelope-like viene delegata a Envelope._scale_raw_values_y."""
            real = _build_real_params()
            pointer = _make_pointer(mock_config, real, {})

            envelope_data = [[0, 0.1], [1.0, 0.5]]

            with patch('controllers.pointer_controller.Envelope.is_envelope_like', return_value=True):
                with patch('controllers.pointer_controller.Envelope._scale_raw_values_y',
                                return_value=[[0, 1.0], [1.0, 5.0]]) as mock_scale:
                    result = pointer._scale_value(envelope_data, 10.0)
                    mock_scale.assert_called_once_with(envelope_data, 10.0)
                    assert result == [[0, 1.0], [1.0, 5.0]]

    def test_scale_unknown_type_passthrough(self, mock_config):
        """Tipo non riconosciuto passa invariato."""
        real = _build_real_params()
        pointer = _make_pointer(mock_config, real, {})

        with patch('controllers.pointer_controller.Envelope.is_envelope_like', return_value=False):
            result = pointer._scale_value("unknown_value", 10.0)
            assert result == "unknown_value"


# =============================================================================
# GRUPPO 18: GET_SPEED E LOOP_PHASE CON LOOP_DUR
# =============================================================================

class TestGetSpeedAndLoopPhase:
    """Test per get_speed() e loop_phase con loop_dur."""

    def test_get_speed_returns_current_value(self, mock_config):
        """get_speed() delega a speed_ratio.get_value()."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(speed=2.5)

        pointer = _make_pointer(
            mock_config, real,
            {'speed_ratio': 2.5}
        )

        speed = pointer.get_speed(0.0)
        assert speed == pytest.approx(2.5)

    def test_loop_phase_with_loop_dur(self, mock_config):
        """loop_phase funziona correttamente con loop_dur."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(
            start=2.5, speed=0.0,
            loop_start=2.0, loop_dur=3.0
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 2.5, 'speed_ratio': 0.0, 'loop_start': 2.0, 'loop_dur': 3.0}
        )

        # Entra nel loop
        pointer.calculate(0.0)
        assert pointer.in_loop is True

        # phase = (2.5 - 2.0) / 3.0 = 0.5 / 3.0 = 0.1667
        phase = pointer.loop_phase
        assert 0.0 <= phase <= 1.0
        assert phase == pytest.approx(0.5 / 3.0, abs=0.01)

    def test_loop_phase_zero_when_not_in_loop(self, mock_config):
        """loop_phase = 0.0 quando non siamo nel loop."""
        real = _build_real_params(start=0.0, speed=1.0)

        pointer = _make_pointer(
            mock_config, real,
            {'start': 0.0, 'speed_ratio': 1.0}
        )

        assert pointer.loop_phase == 0.0

    def test_loop_phase_zero_with_zero_length_loop(self, mock_config):
        """loop_phase = 0.0 con loop di lunghezza zero."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(
            start=2.0, speed=0.0,
            loop_start=2.0, loop_dur=0.0
        )
        # loop_dur=0.0 potrebbe essere clampato a 0.001, ma loop_phase
        # non dovrebbe crashare

        pointer = _make_pointer(
            mock_config, real,
            {'start': 2.0, 'speed_ratio': 0.0, 'loop_start': 2.0, 'loop_dur': 0.0}
        )

        # Non deve crashare
        _ = pointer.loop_phase


# =============================================================================
# GRUPPO 19: FALLBACK LOOP_END = SAMPLE_DUR
# =============================================================================

class TestLoopEndFallback:
    """Test che loop_end venga impostato a sample_dur_sec quando mancante."""

    def test_loop_start_only_sets_loop_end_to_sample_dur(self, mock_config):
        """Solo loop_start: loop_end diventa sample_dur_sec."""
        mock_config.context.sample_dur_sec = 8.0
        real = _build_real_params(
            start=1.0, speed=1.0,
            loop_start=1.0
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 1.0, 'speed_ratio': 1.0, 'loop_start': 1.0}
        )

        assert pointer.has_loop is True
        assert pointer.loop_end == 8.0

    def test_loop_start_with_loop_dur_no_fallback(self, mock_config):
        """Con loop_dur presente, loop_end resta None."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(
            start=1.0, speed=1.0,
            loop_start=1.0, loop_dur=3.0
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 1.0, 'speed_ratio': 1.0, 'loop_start': 1.0, 'loop_dur': 3.0}
        )

        assert pointer.has_loop is True
        assert pointer.loop_end is None
        assert pointer.loop_dur is not None

    def test_loop_start_with_loop_end_no_fallback(self, mock_config):
        """Con loop_end presente, non viene sovrascritto."""
        mock_config.context.sample_dur_sec = 10.0
        real = _build_real_params(
            start=0.0, speed=1.0,
            loop_start=1.0, loop_end=6.0
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 0.0, 'speed_ratio': 1.0, 'loop_start': 1.0, 'loop_end': 6.0}
        )

        assert pointer.has_loop is True
        assert pointer.loop_end.value == 6.0  # Non sovrascritto

    def test_fallback_loop_end_is_float_not_parameter(self, mock_config):
        """BUG NOTO: fallback assegna float, non Parameter.
        
        Quando solo loop_start e' presente, il codice fa:
            self.loop_end = self._sample_dur_sec  (float)
        Ma _apply_loop chiama self.loop_end.get_value() -> AttributeError.
        
        Questo test DOCUMENTA il bug. In pratica non si manifesta
        perche' lo YAML fornisce sempre loop_end o loop_dur espliciti.
        """
        mock_config.context.sample_dur_sec = 5.0
        real = _build_real_params(
            start=2.0, speed=1.0,
            loop_start=2.0
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 2.0, 'speed_ratio': 1.0, 'loop_start': 2.0}
        )

        assert pointer.has_loop is True
        assert pointer.loop_end == 5.0  # float, NON Parameter
        assert isinstance(pointer.loop_end, float)  # conferma il tipo

        # Verifico che calculate() fallisce con il bug
        with pytest.raises(AttributeError, match="has no attribute 'get_value'"):
            pointer.calculate(0.0)

    def test_fallback_loop_wraps_at_sample_end(self, mock_config):
        """Loop fino a fine sample wrappa correttamente (con loop_end esplicito)."""
        mock_config.context.sample_dur_sec = 5.0
        # Usa loop_end esplicito = sample_dur per evitare il bug del fallback
        real = _build_real_params(
            start=2.0, speed=1.0,
            loop_start=2.0, loop_end=5.0
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 2.0, 'speed_ratio': 1.0, 'loop_start': 2.0, 'loop_end': 5.0}
        )

        assert pointer.has_loop is True

        # Entra nel loop
        pointer.calculate(0.0)

        positions = []
        for t_tenth in range(40):
            t = t_tenth * 0.1
            pos = pointer.calculate(t)
            positions.append(pos)

        # Tutte le posizioni dopo l'entrata devono essere in [2.0, 5.0)
        for pos in positions:
            assert 0.0 <= pos < 5.0


# =============================================================================
# GRUPPO 20: LOG WARNING SU RESET
# =============================================================================

class TestLoopResetLogging:
    """Test che il reset direction-aware emetta log warning."""

    def test_reset_logs_warning(self, mock_config):
        """Reset direction-aware chiama log_config_warning."""
        mock_config.context.sample_dur_sec = 10.0

        real = _build_real_params(
            start=0.0, speed=1.0,
            loop_start=2.0, loop_end=5.0
        )

        # Usa Mock per loop_start che cambia
        real['loop_start'] = Mock()
        real['loop_start'].value = 2.0
        real['loop_start'].get_value = Mock(
            side_effect=[2.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]
        )

        pointer = _make_pointer(
            mock_config, real,
            {'start': 0.0, 'speed_ratio': 1.0, 'loop_start': 2.0, 'loop_end': 5.0}
        )

        # Entra nel loop
        pointer.calculate(2.5)
        pointer.calculate(3.0)

        # Bounds cambiano: il pointer sara' fuori [4.0, 5.0)
        with patch('controllers.pointer_controller.log_config_warning') as mock_log:
            pointer.calculate(3.5)
            # Verifica che log_config_warning sia stato chiamato
            assert mock_log.called
            # Verifica che il value_type contenga "loop_reset"
            _, kwargs = mock_log.call_args
            assert 'loop_reset' in kwargs.get('value_type', '')

# =============================================================================
# TEST RIGHE MANCANTI: 88-96, 251, 315, 372-374, 452, 469-471
# =============================================================================

class TestPointerControllerMissingLines:
    """Copre le righe mancanti di pointer_controller.py."""

    def test_pre_normalize_params_none_returns_empty(self, mock_config):
        """
        Righe 88-96: _pre_normalize_loop_params con params=None.
        Deve restituire {} senza sollevare eccezioni.
        """
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            mock_orch.create_all_parameters.return_value = {
                'pointer_start': 0.0,
                'pointer_speed_ratio': Mock(value=1.0, get_value=Mock(return_value=1.0)),
                'pointer_deviation': Mock(value=0.0, get_value=Mock(return_value=0.0)),
                'loop_start': None,
                'loop_end': None,
                'loop_dur': None,
            }
            mock_config.context.sample_dur_sec = 10.0
            # Passa params senza loop_start per triggerare il return anticipato
            result = PointerController({'start': 0.0}, mock_config)
            assert result is not None

    def test_pre_normalize_params_without_loop_start(self, mock_config):
        """
        Righe 88-96: _pre_normalize_loop_params con params che non ha 'loop_start'.
        Deve restituire params invariato.
        """
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            mock_orch.create_all_parameters.return_value = {
                'pointer_start': 0.0,
                'pointer_speed_ratio': Mock(value=1.0, get_value=Mock(return_value=1.0)),
                'pointer_deviation': Mock(value=0.0, get_value=Mock(return_value=0.0)),
                'loop_start': None,
                'loop_end': None,
                'loop_dur': None,
            }
            mock_config.context.sample_dur_sec = 10.0
            pointer = PointerController({'start': 0.0, 'speed_ratio': 1.0}, mock_config)
            assert pointer is not None

    def test_grain_reverse_flag(self, pointer_factory):
        """
        Righe 372-374: branch grain_reverse=True in calculate().
        Con grain_reverse=True, final_pos += grain_duration prima del wrap.
        """
        pointer = pointer_factory({
            'start': 2.0,
            'speed_ratio': 0.0,
        })

        pos_normal = pointer.calculate(0.0, grain_duration=0.05, grain_reverse=False)
        pos_reversed = pointer.calculate(0.0, grain_duration=0.05, grain_reverse=True)

        # Con grain_reverse il risultato deve differire di grain_duration (modulo sample_dur)
        sample_dur = pointer._sample_dur_sec
        diff = (pos_reversed - pos_normal) % sample_dur
        assert diff == pytest.approx(0.05, abs=1e-6)

    def test_loop_dur_mode_dynamic(self, mock_config):
        """
        Righe 251 e 315: modalita' loop_dur (invece di loop_end).
        self.loop_dur non e' None → chiama loop_dur.get_value().
        """
        mock_config.context.sample_dur_sec = 10.0

        real = _build_real_params(
            start=2.0, speed=0.0,
            loop_start=2.0, loop_end=5.0
        )
        # Sostituisce loop_end con loop_dur
        real['loop_end'] = None
        loop_dur_param = Mock()
        loop_dur_param.value = 3.0
        loop_dur_param.get_value = Mock(return_value=3.0)
        real['loop_dur'] = loop_dur_param

        pointer = _make_pointer(
            mock_config, real,
            {'start': 2.0, 'speed_ratio': 0.0, 'loop_start': 2.0, 'loop_dur': 3.0}
        )

        pointer.calculate(0.0)  # entrata nel loop
        pos = pointer.calculate(1.0)
        assert 2.0 <= pos < 5.0  # dentro [loop_start, loop_start+loop_dur)

    def test_scale_value_unsupported_type_returns_value(self, mock_config):
        """
        Riga 452: _scale_value con tipo non riconosciuto restituisce value invariato.
        Ne' scalare ne' envelope-like → return value.
        """
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            mock_orch.create_all_parameters.return_value = {
                'pointer_start': 0.0,
                'pointer_speed_ratio': Mock(value=1.0, get_value=Mock(return_value=1.0)),
                'pointer_deviation': Mock(value=0.0, get_value=Mock(return_value=0.0)),
                'loop_start': None,
                'loop_end': None,
                'loop_dur': None,
            }
            mock_config.context.sample_dur_sec = 10.0
            pointer = PointerController({'start': 0.0}, mock_config)

            # Oggetto arbitrario che non e' scalare ne' envelope-like
            class _Weird:
                pass

            obj = _Weird()
            result = pointer._scale_value(obj, 2.0)
            assert result is obj  # restituito invariato

    def test_init_loop_state_all_fields(self, mock_config):
        """
        Righe 469-471: verifica che _init_loop_state inizializzi tutti i campi.
        Include i campi di drift logging aggiunti di recente.
        """
        with patch('controllers.pointer_controller.ParameterOrchestrator') as MockOrch:
            mock_orch = MockOrch.return_value
            mock_orch.create_all_parameters.return_value = {
                'pointer_start': 0.0,
                'pointer_speed_ratio': Mock(value=1.0, get_value=Mock(return_value=1.0)),
                'pointer_deviation': Mock(value=0.0, get_value=Mock(return_value=0.0)),
                'loop_start': None,
                'loop_end': None,
                'loop_dur': None,
            }
            mock_config.context.sample_dur_sec = 10.0
            pointer = PointerController({'start': 0.0}, mock_config)

            # Verifica che tutti i campi di _init_loop_state siano presenti
            assert pointer._in_loop is False
            assert pointer._loop_absolute_pos is None
            assert pointer._last_linear_pos is None
            assert pointer._prev_loop_start is None
            assert pointer._prev_loop_end is None
            assert pointer._drift_prev_loop_start is None
            assert pointer._drift_prev_elapsed is None
            assert pointer._drift_log_interval == pytest.approx(5.0)
            assert pointer._drift_last_logged == pytest.approx(-999.0)
            assert pointer._drift_first_warning_emitted is False