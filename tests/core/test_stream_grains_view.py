# tests/core/test_stream_grains_view.py
"""Stream.grains e' una VISTA DERIVATA, non una seconda copia dei grani (#201).

`generate_grains()` produceva due rappresentazioni degli stessi eventi tenute
in due campi distinti — `_voices` (annidata per voce) e `_grains` (flat,
ordinata per onset) — sincronizzate solo lungo il percorso di generazione.
Fuori da quel percorso divergevano in silenzio, in entrambe le direzioni:

- `stream.voices = [...]` lasciava `_grains` fermo al valore vecchio;
- `stream.grains = [...]` lasciava `_voices` VUOTO e marcava `generated=True`.

La seconda e' quella che fa danno: ogni backend legge `voices`, mai `grains`
(score_writer, numpy_audio_renderer, grain_visuals, grain_json_writer), quindi
uno stream iniettato via `.grains` renderizzava silenzio con uscita pulita e
`__repr__` che continuava a dichiarare i grani presenti. Stessa classe di
guasto di #225/#234: nessun errore, nessun avviso, un file muto.

Qui si fissa il contratto che rende la divergenza impossibile per costruzione:
una sola fonte di verita' (`_voices`) e `grains` calcolata a ogni lettura.
"""

import pytest

from pge.core.grain import Grain


@pytest.fixture
def stream(build_stream):
    """Stream vero, pronto a generare.

    `build_stream` costruisce lo Stream attraverso `__init__`; i riferimenti
    Csound (sample table, mappa finestre) li assegna normalmente il Generator,
    quindi vanno forniti qui o `_create_grain` non arriva a costruire il Grain.
    """
    s = build_stream()
    s.sample_table_num = 1
    s.envelope_table_num = 2
    s.window_table_map = {'hanning': 2}
    return s


def _grain(onset, volume=0.5):
    return Grain(onset=onset, duration=0.01, pointer_pos=0.0, pitch_ratio=1.0,
                 volume=volume, pan=0.5, sample_table=1, envelope_table=2)


# =============================================================================
# 1. NESSUNA DIVERGENZA POSSIBILE
# =============================================================================

class TestNessunaDivergenza:

    def test_grains_riflette_le_voices_iniettate(self, stream):
        """Direzione A: assegnare voices aggiorna anche la vista flat."""
        s = stream
        s.voices = [[_grain(0.0), _grain(0.1)]]

        assert s.grains == [g for voice in s.voices for g in voice]

    def test_iniezione_via_grains_rifiutata(self, stream):
        """Direzione B: il setter che ammutoliva lo stream non esiste piu'.

        Rifiutare con AttributeError e' il punto: prima l'assegnazione
        riusciva e lasciava `.voices` vuoto, cioe' zero grani da renderizzare.
        """
        s = stream
        grani = [g for voice in s.voices for g in voice]
        assert grani, "lo stream di prova deve generare almeno un grano"

        with pytest.raises(AttributeError, match="voices"):
            s.grains = grani

        # La fonte di verita' non e' stata toccata: niente stream muto.
        assert [g for voice in s.voices for g in voice] == grani

    def test_nessuno_stato_duplicato_ritenuto(self, stream):
        """La vista e' ricalcolata, non conservata: due letture, due liste."""
        s = stream

        assert s.grains == s.grains          # stesso contenuto
        assert s.grains is not s.grains      # oggetti distinti
        assert '_grains' not in vars(s)      # nessun campo di appoggio

    def test_mutare_la_vista_non_tocca_lo_stream(self, stream):
        """Una vista derivata e' una fotografia: mutarla non desincronizza."""
        s = stream
        n = len(s.grains)

        s.grains.append(_grain(999.0))

        assert len(s.grains) == n


# =============================================================================
# 2. SEMANTICA DELLA VISTA (invariata rispetto a prima)
# =============================================================================

class TestSemanticaDellaVista:

    def test_ordinata_per_onset(self, stream):
        s = stream
        s.voices = [[_grain(0.0), _grain(0.4)], [_grain(0.2), _grain(0.6)]]

        assert [g.onset for g in s.grains] == [0.0, 0.2, 0.4, 0.6]

    def test_a_parita_di_onset_resta_l_ordine_per_voce(self, stream):
        """Il sort e' stabile: i pari-merito escono in ordine voice-major.

        Non e' un dettaglio estetico — e' l'unica cosa che rende la vista
        confrontabile con il flatten voice-major che usano i renderer.
        """
        s = stream
        s.voices = [[_grain(0.0, volume=0.1)], [_grain(0.0, volume=0.2)]]

        assert [g.volume for g in s.grains] == [0.1, 0.2]

    def test_lettura_su_stream_non_generato_innesca_la_generazione(self, stream):
        s = stream
        assert s.generated is False

        grani = s.grains

        assert s.generated is True
        assert grani == [g for voice in s.voices for g in voice]


# =============================================================================
# 3. __repr__ NON MENTE PIU'
# =============================================================================

class TestRepr:

    def test_conta_dalle_voices(self, stream):
        """Prima riportava il conteggio di `_grains`, rimasto a zero."""
        s = stream
        s.voices = [[_grain(0.0), _grain(0.1)], [_grain(0.2)]]

        assert 'grains=3' in repr(s)

    def test_non_innesca_la_generazione_lazy(self, stream):
        """Vincolo #117: _create_streams stampa ogni stream appena creato."""
        s = stream

        assert 'grains=lazy' in repr(s)
        assert s.generated is False
