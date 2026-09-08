# tests/rendering/test_csound_renderer.py
"""
TDD suite per CsoundRenderer e RendererFactory.

CsoundRenderer: Adapter che wrappa ScoreWriter + subprocess csound
nell'interfaccia AudioRenderer ABC.

RendererFactory: Factory Method che crea il renderer giusto da stringa CLI.

Coverage:
1. TestCsoundRendererInit                - costruzione e ereditarieta' ABC
2. TestCsoundRendererRenderStream        - delega a ScoreWriter + subprocess (singolo stream)
3. TestCsoundRendererRenderMergedStreams - delega a ScoreWriter + subprocess (piu' stream)
4. TestCsoundRendererErrors              - gestione errori subprocess
5. TestRendererFactoryCreate             - creazione renderer da stringa
6. TestRendererFactoryValidation         - validazione input
"""

import os

import pytest
from unittest.mock import MagicMock, patch, call

from pge.rendering.audio_renderer import AudioRenderer
from pge.rendering.csound_renderer import CsoundRenderer
from pge.rendering.renderer_factory import RendererFactory


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_score_writer():
    """Mock ScoreWriter."""
    sw = MagicMock()
    sw.ftable_manager = MagicMock()
    return sw


@pytest.fixture
def csound_config():
    """Configurazione Csound minimale."""
    return {
        'orc_path': 'csound/main.orc',
        'env_vars': {
            'INCDIR': '/project/src',
            'SSDIR': '/project/refs',
            'SFDIR': '/project/output',
        },
        'log_dir': '/project/logs',
        'message_level': 134,
    }


@pytest.fixture
def renderer(mock_score_writer, csound_config):
    """CsoundRenderer configurato con mock."""
    return CsoundRenderer(
        score_writer=mock_score_writer,
        csound_config=csound_config,
    )


@pytest.fixture
def mock_stream():
    """Mock Stream minimale."""
    stream = MagicMock()
    stream.stream_id = 'test_stream'
    stream.voices = [[]]
    return stream


# =============================================================================
# 1. TEST CSOUND RENDERER INIT
# =============================================================================

class TestCsoundRendererInit:
    """Test per la costruzione e l'ereditarieta' ABC."""

    def test_creates_instance(self, renderer):
        """CsoundRenderer si puo' istanziare."""
        assert renderer is not None

    def test_inherits_from_audio_renderer(self, renderer):
        """CsoundRenderer e' sottoclasse di AudioRenderer."""
        assert isinstance(renderer, AudioRenderer)

    def test_stores_score_writer(self, renderer, mock_score_writer):
        """score_writer viene conservato."""
        assert renderer.score_writer is mock_score_writer

    def test_stores_csound_config(self, renderer, csound_config):
        """csound_config viene conservato."""
        assert renderer.csound_config is csound_config


# =============================================================================
# 2. TEST RENDER STREAM
# =============================================================================

class TestCsoundRendererRenderStream:
    """Test per render_single_stream: ScoreWriter + subprocess csound (singolo stream)."""

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_calls_score_writer(self, mock_run, renderer, mock_stream):
        """render_single_stream delega la scrittura .sco a ScoreWriter."""
        mock_run.return_value = MagicMock(returncode=0)

        renderer.render_single_stream(mock_stream, '/output/test.aif')

        renderer.score_writer.write_score.assert_called_once()

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_score_writer_receives_stream(self, mock_run, renderer, mock_stream):
        """ScoreWriter riceve lo stream nella lista."""
        mock_run.return_value = MagicMock(returncode=0)

        renderer.render_single_stream(mock_stream, '/output/test.aif')

        call_kwargs = renderer.score_writer.write_score.call_args.kwargs
        assert mock_stream in call_kwargs['streams']

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_calls_subprocess_csound(self, mock_run, renderer, mock_stream):
        """render_single_stream invoca csound via subprocess."""
        mock_run.return_value = MagicMock(returncode=0)

        renderer.render_single_stream(mock_stream, '/output/test.aif')

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == 'csound'

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_csound_receives_orc_path(self, mock_run, renderer, mock_stream):
        """Il comando csound include il path dell'orchestra."""
        mock_run.return_value = MagicMock(returncode=0)

        renderer.render_single_stream(mock_stream, '/output/test.aif')

        cmd = mock_run.call_args[0][0]
        assert 'csound/main.orc' in cmd

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_csound_receives_output_flag(self, mock_run, renderer, mock_stream):
        """Il comando csound include -o con il path output."""
        mock_run.return_value = MagicMock(returncode=0)

        renderer.render_single_stream(mock_stream, '/output/test.aif')

        cmd = mock_run.call_args[0][0]
        assert '-o' in cmd
        o_idx = cmd.index('-o')
        assert cmd[o_idx + 1] == '/output/test.aif'

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_returns_output_path(self, mock_run, renderer, mock_stream):
        """render_single_stream ritorna il path del file prodotto."""
        mock_run.return_value = MagicMock(returncode=0)

        result = renderer.render_single_stream(mock_stream, '/output/test.aif')

        assert result == '/output/test.aif'


# =============================================================================
# 3. TEST RENDER MERGED STREAMS
# =============================================================================

class TestCsoundRendererRenderMergedStreams:
    """Test per render_merged_streams: ScoreWriter + subprocess csound (piu' stream)."""

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_calls_score_writer_with_all_streams(self, mock_run, renderer, mock_stream):
        """render_merged_streams passa tutti gli stream a ScoreWriter."""
        mock_run.return_value = MagicMock(returncode=0)

        streams = [mock_stream, MagicMock()]
        renderer.render_merged_streams(streams, '/output/mix.aif')

        call_kwargs = renderer.score_writer.write_score.call_args.kwargs
        assert call_kwargs['streams'] == streams

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_returns_output_path(self, mock_run, renderer, mock_stream):
        """render_merged_streams ritorna il path del file prodotto."""
        mock_run.return_value = MagicMock(returncode=0)

        result = renderer.render_merged_streams([mock_stream], '/output/mix.aif')

        assert result == '/output/mix.aif'


# =============================================================================
# 4. TEST ERRORS
# =============================================================================

class TestCsoundRendererErrors:
    """Test per gestione errori."""

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_csound_failure_raises(self, mock_run, renderer, mock_stream):
        """Csound con returncode != 0 solleva RuntimeError."""
        mock_run.return_value = MagicMock(returncode=1, stderr='error')

        with pytest.raises(RuntimeError, match="Csound"):
            renderer.render_single_stream(mock_stream, '/output/test.aif')

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_csound_assente_e_un_errore_azionabile(self, mock_run, renderer, mock_stream):
        """Csound non installato: il messaggio nomina il binario e il rimedio
        (issue #241). Prima era il FileNotFoundError grezzo del subprocess."""
        from pge.shared.exceptions import CsoundNotFoundError
        mock_run.side_effect = FileNotFoundError("csound not found")

        with pytest.raises(CsoundNotFoundError) as exc:
            renderer.render_single_stream(mock_stream, '/output/test.aif')

        msg = exc.value.user_message()
        # Il binario, non la parola: 'csound' da sola vive gia' nell'hint,
        # quindi un `what=` svuotato lascerebbe verde l'asserzione che la
        # docstring dice di fare.
        assert "binario 'csound'" in msg
        assert '--renderer numpy' in msg

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_csound_assente_non_e_un_FileNotFoundError(self, mock_run, renderer, mock_stream):
        """Specchio di test_scsynth_assente_non_e_un_FileNotFoundError
        (issue #241): il file YAML qui esiste ed e' gia' stato letto, quindi
        per il binario assente il builtin sarebbe falso -- il file che manca
        non e' quello che il tipo lascia intendere.

        La ragione storica («la CLI intercetta FileNotFoundError per
        annunciare 'file YAML non trovato'») e' caduta con la #257, che
        quell'handler lo toglie del tutto; la regola resta, sul valore di
        verita' del tipo."""
        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(Exception) as exc:
            renderer.render_single_stream(mock_stream, '/output/test.aif')
        assert not isinstance(exc.value, FileNotFoundError)

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_csound_assente_anche_in_mix(self, mock_run, renderer, mock_stream):
        """Il MIX passa dallo stesso _run_csound: stesso errore."""
        from pge.shared.exceptions import CsoundNotFoundError
        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(CsoundNotFoundError):
            renderer.render_merged_streams([mock_stream], '/output/mix.aif')

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_csound_fallito_dice_come_riavere_lo_sco(self, mock_run, renderer, mock_stream):
        """Il messaggio di CsoundRenderError offre un `Comando:` da rieseguire,
        ma quel comando nomina il `.sco` che il `finally` ha appena cancellato:
        senza il flag, la prima azione che il messaggio suggerisce e' un
        no-op. E' lo stesso metro con cui questa PR ha riscritto l'hint di
        csound assente. Il rimedio (`--keep-sco`) lo conosce gia'
        `docs/reference/cli.md`; qui deve stare dentro il messaggio, che e'
        l'unica cosa che l'utente legge."""
        from pge.shared.exceptions import CsoundRenderError
        mock_run.return_value = MagicMock(
            returncode=2, stderr='error: undefined opcode', stdout='')

        with pytest.raises(CsoundRenderError) as exc:
            renderer.render_single_stream(mock_stream, '/output/test.aif')

        msg = exc.value.user_message()
        sco_path = renderer.score_writer.write_score.call_args.kwargs['filepath']
        assert not os.path.exists(sco_path), \
            "premessa del test: il finally lo ha cancellato"
        assert '--keep-sco' in msg

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_con_keep_sco_il_messaggio_non_promette_un_rimedio_gia_attivo(
        self, mock_run, mock_score_writer, csound_config, mock_stream, tmp_path
    ):
        """Con `--keep-sco` lo score e' li': suggerirlo sarebbe un rimedio per
        un guasto che non c'e', e manderebbe l'utente a cercare un flag che ha
        gia' passato."""
        from pge.shared.exceptions import CsoundRenderError
        mock_run.return_value = MagicMock(
            returncode=2, stderr='error: undefined opcode', stdout='')
        renderer = CsoundRenderer(
            score_writer=mock_score_writer,
            csound_config=csound_config,
            sco_dir=str(tmp_path / 'sco'),
        )

        with pytest.raises(CsoundRenderError) as exc:
            renderer.render_single_stream(mock_stream, '/out/test.aif')

        assert '--keep-sco' not in exc.value.user_message()

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_l_hint_non_promette_di_rieseguire_il_comando_del_temporaneo(
        self, mock_run, mock_score_writer, csound_config, mock_stream, tmp_path
    ):
        """`--keep-sco` non ricrea lo score cancellato: lo scrive altrove.

        Il `Comando:` del messaggio nomina il file temporaneo, che il
        `finally` ha appena rimosso e che nessun rilancio riporta a quel
        path: con `sco_dir` lo score va in una directory stabile
        (`generated/` per default, o `--sco-dir`), e senza, `mkstemp` pesca
        ogni volta un nome nuovo. Un hint che dica «rilancia con
        `--keep-sco` [...] e riesegui il comando qui sopra» manda quindi a
        una riga che non tornera' valida mai -- ed e' lo stesso metro con
        cui questa PR ha riscritto l'hint di csound assente, applicato
        all'hint che quella riscrittura ha introdotto.

        Il rimedio resta `--keep-sco`; a cambiare e' cosa il messaggio
        promette del comando che sta mostrando.
        """
        from pge.shared.exceptions import CsoundRenderError
        mock_run.return_value = MagicMock(
            returncode=2, stderr='error: undefined opcode', stdout='')

        temporaneo = CsoundRenderer(
            score_writer=mock_score_writer, csound_config=csound_config)
        with pytest.raises(CsoundRenderError) as exc:
            temporaneo.render_single_stream(mock_stream, '/out/test.aif')
        msg = exc.value.user_message()
        sco_temp = mock_score_writer.write_score.call_args.kwargs['filepath']

        # Premessa, misurata e non dichiarata: il path che il `Comando:`
        # mostra e' sparito, e il flag che il messaggio suggerisce ne
        # produce un altro.
        assert sco_temp in msg
        assert not os.path.exists(sco_temp)
        con_flag = CsoundRenderer(
            score_writer=mock_score_writer, csound_config=csound_config,
            sco_dir=str(tmp_path / 'sco'))
        with pytest.raises(CsoundRenderError):
            con_flag.render_single_stream(mock_stream, '/out/test.aif')
        assert mock_score_writer.write_score.call_args.kwargs['filepath'] != sco_temp

        # Quindi il messaggio deve dire che quella riga non si riesegue, non
        # invitare a rieseguirla.
        assert '--keep-sco' in msg
        assert "non e' piu' rieseguibile" in msg

    @pytest.mark.parametrize('mode', ['stems', 'mix'])
    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_il_sco_temporaneo_non_sopravvive_a_un_render_fallito(
            self, mock_run, renderer, mock_stream, mode):
        """Senza --keep-sco il .sco e' un file temporaneo, e la sua
        cancellazione stava dopo la chiamata a csound: ogni modo di fallire
        ne abbandonava uno in /tmp, con un nome che l'utente non puo'
        ritrovare. Con csound assente (issue #241) era ogni singolo
        tentativo."""
        from pge.shared.exceptions import CsoundNotFoundError
        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(CsoundNotFoundError):
            if mode == 'stems':
                renderer.render_single_stream(mock_stream, '/output/test.aif')
            else:
                renderer.render_merged_streams([mock_stream], '/output/mix.aif')

        # Il path arriva dalla chiamata a write_score, non da una spia su un
        # metodo interno: e' il .sco che il renderer ha davvero creato, e
        # l'asserzione non si rompe se quel metodo cambia nome.
        assert renderer.score_writer.write_score.call_args, \
            "nessun .sco scritto: il test non sta misurando nulla"
        sco_path = renderer.score_writer.write_score.call_args.kwargs['filepath']
        assert not os.path.exists(sco_path)

    @pytest.mark.parametrize('mode', ['stems', 'mix'])
    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_il_sco_temporaneo_non_sopravvive_a_uno_score_che_fallisce(
            self, mock_run, renderer, mock_stream, mode):
        """Il file temporaneo lo crea `mkstemp`, prima che ScoreWriter ci
        scriva: anche un render che muore *scrivendo* lo score ne lascia uno
        in /tmp. Non e' un caso di scuola -- i grani sono lazy (issue #117) e
        si materializzano qui, quindi ogni modo di essere invalidi che il
        parse non ha visto passa da questa riga. Il `finally` deve coprire
        anche la scrittura, come in SuperColliderRenderer._render."""
        from pge.shared.exceptions import FtableError
        mock_run.return_value = MagicMock(returncode=0)
        renderer.score_writer.write_score.side_effect = FtableError(
            key='win_hann', reason='tabella non registrata')

        with pytest.raises(FtableError):
            if mode == 'stems':
                renderer.render_single_stream(mock_stream, '/output/test.aif')
            else:
                renderer.render_merged_streams([mock_stream], '/output/mix.aif')

        sco_path = renderer.score_writer.write_score.call_args.kwargs['filepath']
        assert not os.path.exists(sco_path)


# =============================================================================
# 5. TEST RENDERER FACTORY CREATE
# =============================================================================

class TestRendererFactoryCreate:
    """Test per RendererFactory.create()."""

    def test_create_numpy_returns_numpy_renderer(self):
        """create('numpy', ...) ritorna NumpyAudioRenderer."""
        from pge.rendering.numpy_audio_renderer import NumpyAudioRenderer
        from pge.rendering.sample_registry import SampleRegistry
        from pge.rendering.numpy_window_registry import NumpyWindowRegistry

        renderer = RendererFactory.create(
            renderer_type='numpy',
            sample_registry=SampleRegistry.__new__(SampleRegistry),
            window_registry=NumpyWindowRegistry(),
            table_map={},
            output_sr=48000,
        )
        assert isinstance(renderer, NumpyAudioRenderer)

    def test_create_csound_returns_csound_renderer(self):
        """create('csound', ...) ritorna CsoundRenderer."""
        renderer = RendererFactory.create(
            renderer_type='csound',
            score_writer=MagicMock(),
            csound_config={'orc_path': 'main.orc'},
        )
        assert isinstance(renderer, CsoundRenderer)

    def test_create_returns_audio_renderer_subclass(self):
        """Qualunque renderer creato e' sottoclasse di AudioRenderer."""
        r_numpy = RendererFactory.create(
            renderer_type='numpy',
            sample_registry=MagicMock(),
            window_registry=MagicMock(),
            table_map={},
            output_sr=48000,
        )
        r_csound = RendererFactory.create(
            renderer_type='csound',
            score_writer=MagicMock(),
            csound_config={},
        )
        assert isinstance(r_numpy, AudioRenderer)
        assert isinstance(r_csound, AudioRenderer)


# =============================================================================
# 6. TEST RENDERER FACTORY VALIDATION
# =============================================================================

class TestRendererFactoryValidation:
    """Test per validazione input della factory."""

    def test_invalid_type_raises_value_error(self):
        """Tipo non valido solleva ValueError."""
        with pytest.raises(ValueError, match="non supportato"):
            RendererFactory.create(renderer_type='invalid')

    def test_error_message_lists_valid_types(self):
        """Il messaggio di errore elenca i tipi validi."""
        with pytest.raises(ValueError, match="csound.*numpy"):
            RendererFactory.create(renderer_type='unknown')

    def test_case_sensitive(self):
        """Il tipo e' case-sensitive."""
        with pytest.raises(ValueError):
            RendererFactory.create(renderer_type='Numpy')

    def test_empty_string_raises(self):
        """Stringa vuota solleva ValueError."""
        with pytest.raises(ValueError):
            RendererFactory.create(renderer_type='')


# =============================================================================
# 7. TEST NUOVI PARAMETRI CSOUND RENDERER
# =============================================================================

class TestCsoundRendererNewParams:
    """Test per i nuovi parametri opzionali di CsoundRenderer."""

    def test_default_cache_manager_none(self, mock_score_writer, csound_config):
        """Senza cache_manager, self.cache_manager e' None."""
        r = CsoundRenderer(score_writer=mock_score_writer, csound_config=csound_config)
        assert r.cache_manager is None

    def test_stores_cache_manager(self, mock_score_writer, csound_config):
        """cache_manager viene conservato."""
        cm = MagicMock()
        r = CsoundRenderer(
            score_writer=mock_score_writer,
            csound_config=csound_config,
            cache_manager=cm,
        )
        assert r.cache_manager is cm

    def test_default_stream_data_map_empty(self, mock_score_writer, csound_config):
        """Senza stream_data_map, self.stream_data_map e' dict vuoto."""
        r = CsoundRenderer(score_writer=mock_score_writer, csound_config=csound_config)
        assert r.stream_data_map == {}

    def test_stores_stream_data_map(self, mock_score_writer, csound_config):
        """stream_data_map viene conservato."""
        sdm = {'s1': {'stream_id': 's1', 'duration': 10}}
        r = CsoundRenderer(
            score_writer=mock_score_writer,
            csound_config=csound_config,
            stream_data_map=sdm,
        )
        assert r.stream_data_map == sdm

    def test_default_sco_dir_none(self, mock_score_writer, csound_config):
        """Senza sco_dir, self.sco_dir e' None."""
        r = CsoundRenderer(score_writer=mock_score_writer, csound_config=csound_config)
        assert r.sco_dir is None

    def test_stores_sco_dir(self, mock_score_writer, csound_config):
        """sco_dir viene conservato."""
        r = CsoundRenderer(
            score_writer=mock_score_writer,
            csound_config=csound_config,
            sco_dir='/sco',
        )
        assert r.sco_dir == '/sco'


# =============================================================================
# 9. TEST CACHE IN render_single_stream
# =============================================================================

class TestCsoundRendererCache:
    """Test per il cache manager in render_single_stream."""

    def _make_renderer_with_cache(self, mock_score_writer, csound_config, cache_dirty):
        """Helper: crea renderer con cache_manager configurato."""
        cache_manager = MagicMock()
        cache_manager.is_dirty.return_value = cache_dirty
        stream_data_map = {'s1': {'stream_id': 's1', 'duration': 10}}
        renderer = CsoundRenderer(
            score_writer=mock_score_writer,
            csound_config=csound_config,
            cache_manager=cache_manager,
            stream_data_map=stream_data_map,
        )
        return renderer, cache_manager

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_render_single_stream_skips_if_cache_clean(
        self, mock_run, mock_score_writer, csound_config
    ):
        """Se il cache e' clean, non invoca csound."""
        mock_run.return_value = MagicMock(returncode=0)
        renderer, _ = self._make_renderer_with_cache(mock_score_writer, csound_config, cache_dirty=False)

        stream = MagicMock()
        stream.stream_id = 's1'

        result = renderer.render_single_stream(stream, '/out/s1.aif')

        mock_run.assert_not_called()
        assert result == '/out/s1.aif'

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_render_single_stream_renders_if_cache_dirty(
        self, mock_run, mock_score_writer, csound_config
    ):
        """Se il cache e' dirty, invoca csound."""
        mock_run.return_value = MagicMock(returncode=0)
        renderer, _ = self._make_renderer_with_cache(mock_score_writer, csound_config, cache_dirty=True)

        stream = MagicMock()
        stream.stream_id = 's1'

        renderer.render_single_stream(stream, '/out/s1.aif')

        mock_run.assert_called_once()

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_render_single_stream_updates_cache_after_build(
        self, mock_run, mock_score_writer, csound_config
    ):
        """Aggiorna il cache dopo render riuscito."""
        mock_run.return_value = MagicMock(returncode=0)
        renderer, cache_manager = self._make_renderer_with_cache(
            mock_score_writer, csound_config, cache_dirty=True
        )

        stream = MagicMock()
        stream.stream_id = 's1'

        renderer.render_single_stream(stream, '/out/s1.aif')

        cache_manager.update_after_build.assert_called_once()

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_render_single_stream_no_cache_always_renders(
        self, mock_run, mock_score_writer, csound_config, mock_stream
    ):
        """Senza cache_manager, renderizza sempre."""
        mock_run.return_value = MagicMock(returncode=0)
        renderer = CsoundRenderer(score_writer=mock_score_writer, csound_config=csound_config)

        renderer.render_single_stream(mock_stream, '/out/s1.aif')

        mock_run.assert_called_once()

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_cache_not_updated_if_skipped(
        self, mock_run, mock_score_writer, csound_config
    ):
        """Se lo stream viene skippato (cache clean), update_after_build NON viene chiamato."""
        mock_run.return_value = MagicMock(returncode=0)
        renderer, cache_manager = self._make_renderer_with_cache(
            mock_score_writer, csound_config, cache_dirty=False
        )

        stream = MagicMock()
        stream.stream_id = 's1'

        renderer.render_single_stream(stream, '/out/s1.aif')

        cache_manager.update_after_build.assert_not_called()


# =============================================================================
# 10. TEST KEEP SCO (sco_dir)
# =============================================================================

class TestCsoundRendererKeepSco:
    """Test per il flag --keep-sco (sco_dir): gestione file .sco intermedi."""

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_no_sco_dir_uses_temp_file(
        self, mock_run, mock_score_writer, csound_config, mock_stream
    ):
        """Senza sco_dir, il file .sco non finisce in 'generated/'."""
        import tempfile
        mock_run.return_value = MagicMock(returncode=0)
        renderer = CsoundRenderer(score_writer=mock_score_writer, csound_config=csound_config)

        renderer.render_single_stream(mock_stream, '/out/test.aif')

        call_kwargs = mock_score_writer.write_score.call_args.kwargs
        sco_path = call_kwargs['filepath']
        # Deve essere in tempdir, non in 'generated'
        assert 'generated' not in sco_path

    @pytest.mark.parametrize('mode', ['stems', 'mix'])
    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_lo_sco_temporaneo_e_rimosso_anche_dopo_un_render_riuscito(
        self, mock_run, mock_score_writer, csound_config, mock_stream, mode
    ):
        """La regola di cancellazione ha ora una scrittura sola, e il suo ramo
        piu' battuto e' quello che finisce bene: senza rete, un render che
        smettesse di ripulire lascerebbe un `.sco` in /tmp a ogni stem, e la
        suite resterebbe verde. E' il test che
        `SuperColliderRenderer` ha da sempre (`test_score_scritto_e_poi_rimosso`),
        e che al ramo csound mancava."""
        visto = {}

        def spia(cmd, **kwargs):
            path = mock_score_writer.write_score.call_args.kwargs['filepath']
            visto['path'] = path
            visto['esisteva'] = os.path.exists(path)
            return MagicMock(returncode=0)

        mock_run.side_effect = spia
        renderer = CsoundRenderer(
            score_writer=mock_score_writer,
            csound_config=csound_config,
        )

        if mode == 'stems':
            renderer.render_single_stream(mock_stream, '/out/test.aif')
        else:
            renderer.render_merged_streams([mock_stream], '/out/mix.aif')

        assert visto['esisteva'], "lo score deve esistere quando csound parte"
        assert not os.path.exists(visto['path']), "temporaneo non ripulito"

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_sco_dir_saves_sco_with_deterministic_path(
        self, mock_run, mock_score_writer, csound_config, mock_stream, tmp_path
    ):
        """Con sco_dir, il file .sco ha path deterministico basato su output_path."""
        mock_run.return_value = MagicMock(returncode=0)
        sco_dir = str(tmp_path / 'sco')
        renderer = CsoundRenderer(
            score_writer=mock_score_writer,
            csound_config=csound_config,
            sco_dir=sco_dir,
        )

        renderer.render_single_stream(mock_stream, '/out/piece_s1.aif')

        call_kwargs = mock_score_writer.write_score.call_args.kwargs
        sco_path = call_kwargs['filepath']
        assert sco_path.startswith(sco_dir)
        assert sco_path.endswith('piece_s1.sco')

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_sco_dir_for_merged_streams(
        self, mock_run, mock_score_writer, csound_config, tmp_path
    ):
        """Con sco_dir, render_merged_streams salva .sco deterministico."""
        mock_run.return_value = MagicMock(returncode=0)
        sco_dir = str(tmp_path / 'sco')
        renderer = CsoundRenderer(
            score_writer=mock_score_writer,
            csound_config=csound_config,
            sco_dir=sco_dir,
        )

        renderer.render_merged_streams([MagicMock()], '/out/composition.aif')

        call_kwargs = mock_score_writer.write_score.call_args.kwargs
        sco_path = call_kwargs['filepath']
        assert sco_path.startswith(sco_dir)
        assert sco_path.endswith('composition.sco')

    @pytest.mark.parametrize('mode,base', [('stems', 'test'), ('mix', 'mix')])
    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_keep_sco_conserva_lo_score_di_un_render_fallito(
        self, mock_run, mock_score_writer, csound_config, mock_stream,
        tmp_path, mode, base
    ):
        """--keep-sco serve a ispezionare lo score, e lo score che si vuole
        ispezionare e' quello del render fallito.

        La cancellazione ora sta in un `finally`, cioe' passa anche di li':
        prima il ramo dei fallimenti non la eseguiva affatto e la condizione
        `not self.sco_dir` non aveva modo di sbagliare. Se qualcuno la
        perdesse, questo flag cancellerebbe il file che promette di tenere --
        e senza questo test la suite resterebbe verde."""
        from pge.shared.exceptions import CsoundNotFoundError
        mock_run.side_effect = FileNotFoundError()
        sco_dir = str(tmp_path / 'sco')

        # Il ScoreWriter e' un mock e da solo non scrive niente: senza questo
        # il file non esisterebbe comunque e l'asserzione sarebbe vuota.
        def scrive_davvero(filepath, **kwargs):
            open(filepath, 'w').close()

        mock_score_writer.write_score.side_effect = scrive_davvero
        renderer = CsoundRenderer(
            score_writer=mock_score_writer,
            csound_config=csound_config,
            sco_dir=sco_dir,
        )

        with pytest.raises(CsoundNotFoundError):
            if mode == 'stems':
                renderer.render_single_stream(mock_stream, f'/out/{base}.aif')
            else:
                renderer.render_merged_streams([mock_stream], f'/out/{base}.aif')

        assert os.path.exists(os.path.join(sco_dir, f'{base}.sco'))


# =============================================================================
# 11. AGGIORNAMENTO TestRendererFactoryCreate - nuovi kwargs csound
# =============================================================================

class TestRendererFactoryCreateNewKwargs:
    """Test per i nuovi kwargs di RendererFactory.create('csound', ...)."""

    def test_create_csound_forwards_cache_manager(self):
        """create('csound') forwarda il parametro cache_manager."""
        cm = MagicMock()
        renderer = RendererFactory.create(
            renderer_type='csound',
            score_writer=MagicMock(),
            csound_config={},
            cache_manager=cm,
        )
        assert renderer.cache_manager is cm

    def test_create_csound_forwards_sco_dir(self):
        """create('csound') forwarda il parametro sco_dir."""
        renderer = RendererFactory.create(
            renderer_type='csound',
            score_writer=MagicMock(),
            csound_config={},
            sco_dir='/sco',
        )
        assert renderer.sco_dir == '/sco'

    def test_create_csound_forwards_stream_data_map(self):
        """create('csound') forwarda il parametro stream_data_map."""
        sdm = {'s1': {'stream_id': 's1'}}
        renderer = RendererFactory.create(
            renderer_type='csound',
            score_writer=MagicMock(),
            csound_config={},
            stream_data_map=sdm,
        )
        assert renderer.stream_data_map == sdm


# =============================================================================
# 12. TEST render_single_stream PASSA per_stream=True (RED - fix problema 1)
# =============================================================================

class TestCsoundRendererPerStream:
    """render_single_stream deve passare per_stream=True a score_writer.write_score."""

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_render_single_stream_passes_per_stream_true(
        self, mock_run, mock_score_writer, csound_config
    ):
        """render_single_stream: write_score viene chiamato con per_stream=True."""
        mock_run.return_value = MagicMock(returncode=0)
        renderer = CsoundRenderer(
            score_writer=mock_score_writer,
            csound_config=csound_config,
        )
        stream = MagicMock()
        stream.stream_id = 'test_stream'

        renderer.render_single_stream(stream, '/out/stem.aif')

        call_kwargs = mock_score_writer.write_score.call_args.kwargs
        assert call_kwargs.get('per_stream') is True

    @patch('pge.rendering.csound_renderer.subprocess.run')
    def test_render_merged_streams_does_not_pass_per_stream(
        self, mock_run, mock_score_writer, csound_config
    ):
        """render_merged_streams: write_score NON viene chiamato con per_stream=True."""
        mock_run.return_value = MagicMock(returncode=0)
        renderer = CsoundRenderer(
            score_writer=mock_score_writer,
            csound_config=csound_config,
        )

        renderer.render_merged_streams([MagicMock()], '/out/mix.aif')

        call_kwargs = mock_score_writer.write_score.call_args.kwargs
        assert call_kwargs.get('per_stream') is not True