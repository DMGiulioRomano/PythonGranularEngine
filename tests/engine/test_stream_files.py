# tests/engine/test_stream_files.py
"""
Lo stream come file (issue #290): `- file: <path>` nella lista `streams:` del
master importa uno stream scritto in un altro documento YAML.

La regola di fondo e' che dopo `Generator.load_yaml` il motore veda una lista
di stream come prima: cache, fingerprint e solo/mute lavorano sullo stream gia'
risolto. Per questo i test passano tutti dall'interfaccia pubblica
(`load_yaml`, `create_elements`, gli errori) su file veri in `tmp_path`, mai
dalla funzione di risoluzione: e' il comportamento del master che conta, non
come ci si arriva.
"""
import numpy as np
import pytest
import soundfile as sf
import yaml

from pge.engine.generator import Generator
from pge.engine.stream_files import CHIAVI_DI_PIAZZAMENTO, StreamFileOrigin


SAMPLE = 'tono.wav'

# Lo stream che il laboratorio scrive: un documento che si rende anche da solo,
# quindi con `onset: 0`, il suo `stream_id` e i top-level del laboratorio.
STREAM_DEL_LABORATORIO = {
    'stream_id': 'risacca',
    'onset': 0.0,
    'duration': 1.5,
    'sample': SAMPLE,
    'density': 30,
    'distribution': 0.7,
    'pitch': {'ratio': 1.0, 'range': 0.3},
    'grain': {'duration': 0.04, 'duration_range': 0.02},
    'pan': 0,
    'pan_range': 40,
}


def _documento_del_laboratorio(stream=None, **top):
    """Un documento del laboratorio: top-level piu' un solo stream."""
    doc = {'seed': 1441, 'duration': 1.5, 'bpm': 60}
    doc.update(top)
    doc['streams'] = [dict(stream or STREAM_DEL_LABORATORIO)]
    return doc


@pytest.fixture
def brano(tmp_path):
    """Una cartella di brano: `refs/` col sample, `streams/` per i file.

    Il master sta nella radice del brano, i file importati in `streams/`:
    il path di `file:` e' relativo alla cartella del master (regola 2).
    """
    refs = tmp_path / 'refs'
    refs.mkdir()
    sr = 48000
    t = np.arange(sr * 2) / sr
    sf.write(str(refs / SAMPLE),
             (0.3 * np.sin(2 * np.pi * 220 * t)).astype('float32'), sr)
    (tmp_path / 'streams').mkdir()

    class Brano:
        root = tmp_path
        samples_dir = str(refs) + '/'

        def scrivi(self, relpath, data):
            path = tmp_path / relpath
            path.parent.mkdir(parents=True, exist_ok=True)
            text = data if isinstance(data, str) else yaml.safe_dump(
                data, sort_keys=False)
            path.write_text(text, encoding='utf-8')
            return str(path)

        def generator(self, master_relpath='brano.yml'):
            return Generator(str(tmp_path / master_relpath),
                             samples_dir=self.samples_dir)

    return Brano()


def _grani(gen):
    """I grani di ogni stream, voce per voce, come tuple confrontabili."""
    return {
        s.stream_id: [
            [(g.onset, g.duration, g.pointer_pos, g.pitch_ratio, g.volume,
              g.pan) for g in voce]
            for voce in s.voices
        ]
        for s in gen.streams
    }


# =============================================================================
# Regola 1 — dopo load_yaml il motore vede una lista di stream come prima
# =============================================================================

def test_lo_stream_importato_suona_come_lo_stesso_stream_scritto_nel_master(
        brano):
    """Stesso seed, stesso id: stessi grani, uno per uno.

    E' l'identita' del suono dichiarata dalla issue: l'RNG e'
    `(seed, rng_group o stream_id, componente)`, e il file non aggiunge niente
    a nessuno dei tre.
    """
    brano.scrivi('streams/risacca.yml', _documento_del_laboratorio())
    brano.scrivi('importa.yml', {
        'seed': 1441,
        'streams': [{'file': 'streams/risacca.yml', 'onset': 0.0}],
    })
    brano.scrivi('inline.yml', {
        'seed': 1441,
        'streams': [dict(STREAM_DEL_LABORATORIO)],
    })

    importa = brano.generator('importa.yml')
    importa.load_yaml()
    importa.create_elements()
    inline = brano.generator('inline.yml')
    inline.load_yaml()
    inline.create_elements()

    grani = _grani(importa)
    assert list(grani) == ['risacca']
    assert sum(len(v) for v in grani['risacca']) > 0
    assert grani == _grani(inline)


def _stream_risolto(brano, voce, master='brano.yml', **documento):
    """Lo stream che `load_yaml` mette al posto di una voce `file:`."""
    brano.scrivi('streams/risacca.yml', _documento_del_laboratorio(**documento))
    brano.scrivi(master, {'seed': 1441, 'streams': [voce]})
    gen = brano.generator(master)
    (stream,) = gen.load_yaml()['streams']
    return stream


# =============================================================================
# Regola 2 — il path e' relativo alla cartella del master
# =============================================================================

def test_il_path_e_relativo_alla_cartella_del_master_non_alla_cwd(
        brano, monkeypatch):
    """Il master in `configs/`, lanciato da un'altra cartella.

    `file: ../streams/risacca.yml` si legge da `configs/`, non da dove sta
    chi lancia: il brano si sposta intero, e chi lo apre non deve sapere da
    dove verra' lanciato.
    """
    altrove = brano.root / 'altrove'
    altrove.mkdir()
    monkeypatch.chdir(altrove)

    stream = _stream_risolto(
        brano, {'file': '../streams/risacca.yml'}, master='configs/brano.yml')

    assert stream['sample'] == SAMPLE
    assert stream['stream_id'] == 'risacca'


# =============================================================================
# Regola 5 — il master decide il piazzamento, il file tutto il resto
# =============================================================================

def test_il_piazzamento_viene_dal_master(brano):
    """`onset`, `mute`, `solo`, `stream_id`: decide il master.

    Il laboratorio scrive `onset: 0` e il proprio `stream_id` perche' il file
    si renda da solo; nel brano quelle chiavi del file non contano.
    """
    stream = _stream_risolto(brano, {
        'file': 'streams/risacca.yml',
        'stream_id': 'onda',
        'onset': 12.5,
        'mute': True,
    })

    assert stream['stream_id'] == 'onda'
    assert stream['onset'] == 12.5
    assert stream['mute'] is True


def test_le_chiavi_di_piazzamento_del_file_sono_ignorate(brano):
    """Un `solo` o un `mute` rimasti nel file non arrivano al brano.

    `_filter_solo_mute` guarda la *presenza* della chiave: un `solo` del file
    che arrivasse nel master metterebbe in solo l'intero brano su quello
    stream, e un `mute` lo zittirebbe, senza che il master dica niente.
    """
    stream = _stream_risolto(
        brano, {'file': 'streams/risacca.yml'},
        stream={**STREAM_DEL_LABORATORIO, 'onset': 3.0, 'solo': True,
                'mute': True})

    assert 'solo' not in stream
    assert 'mute' not in stream
    assert 'onset' not in stream


def test_senza_stream_id_nel_master_l_id_e_il_nome_del_file(brano):
    """Il default di `stream_id` e' il nome del file senza estensione.

    Non lo `stream_id` del file: e' una chiave di piazzamento, e il master
    che non ne scrive uno ne sceglie comunque uno, quello del file che
    importa.
    """
    stream = _stream_risolto(
        brano, {'file': 'streams/risacca.yml'},
        stream={**STREAM_DEL_LABORATORIO, 'stream_id': 'stream1'})

    assert stream['stream_id'] == 'risacca'


def test_i_top_level_del_file_sono_ignorati_la_durata_dello_stream_no(brano):
    """`duration` e `bpm` top-level del laboratorio non entrano nel brano.

    La `duration` *dello stream* si', con tutto il resto dello stream: e'
    contenuto, non piazzamento.
    """
    stream = _stream_risolto(
        brano, {'file': 'streams/risacca.yml'}, duration=99, bpm=120)

    assert stream['duration'] == STREAM_DEL_LABORATORIO['duration']
    assert 'bpm' not in stream
    assert {k: v for k, v in stream.items() if k != 'stream_id'} == {
        k: v for k, v in STREAM_DEL_LABORATORIO.items()
        if k not in ('stream_id', 'onset')}


# =============================================================================
# Regola 4 — ogni chiave ha una sola casa
# =============================================================================

@pytest.mark.parametrize('chiave', ['density', 'sample', 'rng_group', 'seed'])
def test_una_chiave_non_di_piazzamento_accanto_a_file_e_un_errore(
        brano, chiave):
    """Accanto a `file:` il master tiene solo il piazzamento.

    Un `density` scritto nel master accanto a `file:` non e' un override: e'
    la stessa chiave in due case, e una delle due mente. L'errore nomina il
    master, la voce e la chiave.
    """
    from pge.shared.exceptions import ConfigError, StreamFileKeyError

    brano.scrivi('streams/risacca.yml', _documento_del_laboratorio())
    master = brano.scrivi('brano.yml', {'streams': [
        {'stream_id': 'altro', 'sample': SAMPLE},
        {'file': 'streams/risacca.yml', 'onset': 2.0, chiave: 10},
    ]})

    with pytest.raises(StreamFileKeyError) as exc:
        brano.generator().load_yaml()

    err = exc.value
    assert isinstance(err, ConfigError)
    assert err.keys == [chiave]
    assert err.allowed == CHIAVI_DI_PIAZZAMENTO
    assert err.config_file == master
    messaggio = err.user_message()
    assert f"'{chiave}'" in messaggio
    assert 'streams[1]' in messaggio
    assert 'streams/risacca.yml' in messaggio
    assert master in messaggio


# =============================================================================
# Regola 8 — gli errori nominano il master e il file importato
# =============================================================================
# Un file importato che non si legge e' lo stesso guasto del master che non si
# legge, e ha gli stessi tipi (#257): chi cattura `FileNotFoundError` o
# `yaml.YAMLError` continua a farlo. Quello che cambia e' il messaggio: senza
# il master, «File di configurazione non trovato: streams/assente.yml» non dice
# chi lo stava cercando.

def _master_che_importa(brano, file='streams/risacca.yml', indice=1):
    """Un master con una voce `file:` in posizione `indice`."""
    voci = [{'stream_id': f'altro{i}', 'sample': SAMPLE}
            for i in range(indice)]
    voci.append({'file': file, 'onset': 4.0})
    return brano.scrivi('brano.yml', {'seed': 1441, 'streams': voci})


def _nomina_master_e_file(err, master, path_importato):
    messaggio = err.user_message()
    assert path_importato in messaggio, messaggio
    assert master in messaggio, messaggio
    assert 'streams[1]' in messaggio, messaggio
    assert isinstance(err.imported_by, StreamFileOrigin)
    assert err.imported_by.master == master
    assert err.imported_by.index == 1


def test_file_importato_mancante(brano):
    from pge.shared.exceptions import ConfigFileNotFoundError

    master = _master_che_importa(brano, file='streams/assente.yml')

    with pytest.raises(ConfigFileNotFoundError) as exc:
        brano.generator().load_yaml()

    err = exc.value
    assert isinstance(err, FileNotFoundError)
    assert err.path == str(brano.root / 'streams' / 'assente.yml')
    _nomina_master_e_file(err, master, 'streams/assente.yml')


def test_file_importato_illeggibile(brano):
    """Una directory al posto del file: il typo della tab-completion."""
    from pge.shared.exceptions import ConfigReadError

    (brano.root / 'streams' / 'cartella.yml').mkdir()
    master = _master_che_importa(brano, file='streams/cartella.yml')

    with pytest.raises(ConfigReadError) as exc:
        brano.generator().load_yaml()

    assert isinstance(exc.value, IsADirectoryError)
    _nomina_master_e_file(exc.value, master, 'streams/cartella.yml')


def test_file_importato_malformato(brano):
    from pge.shared.exceptions import ConfigParseError

    brano.scrivi('streams/rotto.yml', 'streams:\n  - stream_id: [a\n')
    master = _master_che_importa(brano, file='streams/rotto.yml')

    with pytest.raises(ConfigParseError) as exc:
        brano.generator().load_yaml()

    assert isinstance(exc.value, yaml.YAMLError)
    _nomina_master_e_file(exc.value, master, 'streams/rotto.yml')
    assert 'Riga/colonna' in exc.value.user_message()


def test_il_master_mancante_non_si_dichiara_importato(brano):
    """La riga `Importato da:` c'e' solo quando qualcuno ha importato."""
    from pge.shared.exceptions import ConfigFileNotFoundError

    with pytest.raises(ConfigFileNotFoundError) as exc:
        brano.generator('assente.yml').load_yaml()

    assert exc.value.imported_by is None
    assert 'Importato da' not in exc.value.user_message()
