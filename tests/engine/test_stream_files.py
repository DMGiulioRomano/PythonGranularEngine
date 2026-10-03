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
import re

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


# =============================================================================
# Regola 3 — un file importato porta un solo stream, e niente catene
# =============================================================================

@pytest.mark.parametrize('contenuto,trovati', [
    ('', 'nessuno stream'),
    ('seed: 1441\nduration: 1.5\n', 'nessuno stream'),
    ('streams: []\n', 'nessuno stream'),
    (yaml.safe_dump({'streams': [STREAM_DEL_LABORATORIO,
                                 STREAM_DEL_LABORATORIO]}), '2 stream'),
    ('streams:\n  risacca: {sample: tono.wav}\n',
     "'streams' non e' una lista"),
    ('streams:\n  - risacca\n', "una voce che non e' uno stream"),
    ('- stream_id: risacca\n  sample: tono.wav\n',
     "il documento non e' una mappa"),
], ids=['vuoto', 'senza-streams', 'lista-vuota', 'due-stream',
        'streams-mappa', 'voce-stringa', 'documento-lista'])
def test_il_file_importato_deve_portare_un_solo_stream(
        brano, contenuto, trovati):
    """Uno stream come file e' un documento con **uno** stream.

    Con due non si saprebbe quale dei due il master stia piazzando, e con
    zero non c'e' niente da piazzare. Ogni forma che non e' «una lista
    `streams:` con un mapping dentro» e' lo stesso errore, e la riga
    `Trovati:` dice quale forma il motore ha letto.
    """
    from pge.shared.exceptions import StreamFileCountError, StreamFileError

    importato = brano.scrivi('streams/risacca.yml', contenuto)
    master = _master_che_importa(brano)

    with pytest.raises(StreamFileCountError) as exc:
        brano.generator().load_yaml()

    err = exc.value
    assert isinstance(err, StreamFileError)
    assert trovati in err.user_message()
    assert err.config_file == importato
    _nomina_master_e_file(err, master, 'streams/risacca.yml')


def test_un_file_dentro_un_file_importato_e_un_errore(brano):
    """Niente catene: lo stream di un file importato e' scritto per intero.

    Senza catene non ci sono cicli, e nessuno deve inseguire un `file:` per
    tre cartelle per sapere che cosa suona.
    """
    from pge.shared.exceptions import StreamFileChainError

    brano.scrivi('streams/altro.yml', _documento_del_laboratorio())
    importato = brano.scrivi('streams/risacca.yml', {
        'streams': [{'file': 'altro.yml', 'onset': 0}]})
    master = _master_che_importa(brano)

    with pytest.raises(StreamFileChainError) as exc:
        brano.generator().load_yaml()

    err = exc.value
    assert err.config_file == importato
    assert 'altro.yml' in err.user_message()
    _nomina_master_e_file(err, master, 'streams/risacca.yml')


def test_un_master_che_importa_se_stesso_e_una_catena(brano):
    """Il ciclo piu' corto possibile si ferma alla regola delle catene."""
    from pge.shared.exceptions import StreamFileChainError

    brano.scrivi('brano.yml', {'streams': [{'file': 'brano.yml'}]})

    with pytest.raises(StreamFileChainError):
        brano.generator().load_yaml()


# =============================================================================
# Regola 7 — due stream con lo stesso id, se almeno uno viene da `file:`
# =============================================================================
# Lo `stream_id` e' il nome dello stem e la chiave della cache: due stream che
# lo condividono si sovrascrivono lo stem a vicenda. Con `file:` succede senza
# che nessuno scriva due volte lo stesso id -- basta importare lo stesso file
# due volte -- ed e' per questo che il controllo nasce qui.

def _errore_di_duplicato(brano, voci):
    from pge.shared.exceptions import StreamFileDuplicateIdError

    brano.scrivi('streams/risacca.yml', _documento_del_laboratorio())
    master = brano.scrivi('brano.yml', {'seed': 1441, 'streams': voci})
    with pytest.raises(StreamFileDuplicateIdError) as exc:
        brano.generator().load_yaml()
    return master, exc.value


def test_lo_stesso_file_importato_due_volte_senza_id_e_un_errore(brano):
    master, err = _errore_di_duplicato(brano, [
        {'file': 'streams/risacca.yml', 'onset': 0},
        {'file': 'streams/risacca.yml', 'onset': 8},
    ])

    assert err.stream_id == 'risacca'
    assert err.config_file == master
    messaggio = err.user_message()
    assert "'risacca'" in messaggio
    assert 'streams[0] (file: streams/risacca.yml)' in messaggio
    assert 'streams[1] (file: streams/risacca.yml)' in messaggio
    assert master in messaggio


def test_un_id_importato_che_collide_con_uno_scritto_nel_master(brano):
    master, err = _errore_di_duplicato(brano, [
        {'stream_id': 'risacca', 'sample': SAMPLE},
        {'file': 'streams/risacca.yml'},
    ])

    messaggio = err.user_message()
    assert 'streams[0]' in messaggio
    assert 'streams[1] (file: streams/risacca.yml)' in messaggio


def test_l_id_effettivo_e_quello_dello_stem(brano):
    """`1` e `'1'` sono lo stesso stem: `brano__1.wav`."""
    _master, err = _errore_di_duplicato(brano, [
        {'stream_id': 1, 'sample': SAMPLE},
        {'file': 'streams/risacca.yml', 'stream_id': '1'},
    ])

    assert err.stream_id == '1'


def test_lo_stesso_file_con_due_id_e_due_stream(brano):
    """Importare due volte lo stesso file e' legittimo: due realizzazioni."""
    brano.scrivi('streams/risacca.yml', _documento_del_laboratorio())
    brano.scrivi('brano.yml', {'seed': 1441, 'streams': [
        {'file': 'streams/risacca.yml'},
        {'file': 'streams/risacca.yml', 'stream_id': 'risacca_eco',
         'onset': 0.5},
    ]})

    gen = brano.generator()
    ids = [s['stream_id'] for s in gen.load_yaml()['streams']]

    assert ids == ['risacca', 'risacca_eco']


def test_i_duplicati_fra_stream_scritti_nel_master_restano_fuori(brano):
    """Fuori scope (regola 7): oggi non si controllano, e non qui."""
    brano.scrivi('brano.yml', {'streams': [
        {'stream_id': 'doppio', 'sample': SAMPLE},
        {'stream_id': 'doppio', 'sample': SAMPLE},
    ]})

    data = brano.generator().load_yaml()

    assert [s['stream_id'] for s in data['streams']] == ['doppio', 'doppio']


@pytest.mark.parametrize('valore', [42, None, '', ['a.yml']],
                         ids=['numero', 'null', 'vuoto', 'lista'])
def test_un_file_che_non_e_un_path_e_un_valore_invalido(brano, valore):
    """`file:` vuole il path di un documento: il resto e' un valore invalido.

    Senza il controllo un numero o una lista uscivano come `TypeError` da
    `os.path.join`, fuori dalla gerarchia `EngineError`; e una stringa vuota
    finiva a leggere la cartella del master.
    """
    from pge.shared.exceptions import InvalidFieldValueError

    master = brano.scrivi('brano.yml', {'streams': [
        {'stream_id': 'altro', 'sample': SAMPLE},
        {'file': valore, 'onset': 1.0},
    ]})

    with pytest.raises(InvalidFieldValueError) as exc:
        brano.generator().load_yaml()

    err = exc.value
    assert err.field == 'streams[1].file'
    assert err.config_file == master
    assert master in err.user_message()


# =============================================================================
# Regola 6 — il seed del file importato e' ignorato, ma non in silenzio
# =============================================================================
# Lo stream importato suona come nel laboratorio solo con lo stesso seed e lo
# stesso id. Se i seed differiscono il render procede col seed del master --
# il brano ne ha uno solo -- e il motore lo dice su stderr: non e' un errore,
# e' un suono diverso da quello che il file da solo fa sentire.

# Le due forme che il parser di PGE-ui legge come protocollo
# (`tests/shared/test_stdout_contract.py`): l'avviso non deve averne nessuna,
# su nessun canale.
_FORMA_CACHE = re.compile(r"^\[CACHE\]\s+(\S+):\s+(.+)$")
_FORMA_PATH = re.compile(r"^\s+(.+__.+)\.(?:aif|aiff|wav|flac)\s*$",
                         re.IGNORECASE)


def _carica(brano, seed_master, seed_file, capsys):
    top = {} if seed_file is None else {'seed': seed_file}
    doc = _documento_del_laboratorio()
    doc.pop('seed')
    doc.update(top)
    brano.scrivi('streams/risacca.yml', doc)
    master = {'streams': [{'file': 'streams/risacca.yml'}]}
    if seed_master is not None:
        master['seed'] = seed_master
    brano.scrivi('brano.yml', master)
    gen = brano.generator()
    gen.load_yaml()
    out, err = capsys.readouterr()
    return gen, out, err


def test_un_seed_diverso_nel_file_e_un_avviso_su_stderr(brano, capsys):
    gen, out, err = _carica(brano, 1441, 7, capsys)

    assert gen.seed == 1441
    righe = [r for r in err.splitlines() if r.strip()]
    assert len(righe) == 1, err
    (riga,) = righe
    assert 'streams/risacca.yml' in riga
    assert 'brano.yml' in riga
    assert ' 7' in riga and '1441' in riga
    assert '[SEED]' not in out, "l'avviso e' finito su stdout"
    assert not _FORMA_CACHE.match(riga) and not _FORMA_PATH.match(riga)


def test_il_master_senza_seed_e_un_seed_diverso(brano, capsys):
    """Senza `seed:` il master usa un seed di sessione: non e' quello del file."""
    gen, _out, err = _carica(brano, None, 7, capsys)

    assert gen.seed is None
    assert 'streams/risacca.yml' in err
    assert 'seed di sessione' in err


@pytest.mark.parametrize('seed_master,seed_file', [
    (1441, 1441),
    (1441, None),
    (1441, '(1000 + 441)'),
    (1441, '1441'),
], ids=['uguale', 'file-senza-seed', 'espressione', 'stringa'])
def test_nessun_avviso_se_il_seed_e_lo_stesso(
        brano, capsys, seed_master, seed_file):
    """Lo stesso seed e' quello che deriva gli stessi RNG.

    La derivazione scrive il seed in una stringa (`f"{seed}:{stream_id}:..."`)
    dopo le espressioni matematiche: `(1000 + 441)` e `'1441'` sono 1441, e
    l'avviso non deve dire che il suono cambia quando non cambia.
    """
    _gen, _out, err = _carica(brano, seed_master, seed_file, capsys)

    assert err == ''


# =============================================================================
# Gli errori del contenuto: `Config:` e' il file in cui il valore e' scritto
# =============================================================================
# `create_elements` scrive in `config_file` il master su ogni errore che sale
# dalla costruzione degli stream. Per uno stream importato quella riga mandava
# a cercare il valore sbagliato nel file che non lo contiene: il sample, la
# densita', il campo mancante stanno nel file importato.

def _crea(brano, stream):
    importato = brano.scrivi('streams/risacca.yml',
                             _documento_del_laboratorio(stream=stream))
    master = brano.scrivi('brano.yml', {'seed': 1441, 'streams': [
        {'stream_id': 'altro', 'sample': SAMPLE, 'duration': 0.5},
        {'file': 'streams/risacca.yml', 'onset': 2.0},
    ]})
    gen = brano.generator()
    gen.load_yaml()
    return gen, master, importato


def test_un_sample_mancante_nel_file_importato_nomina_il_file(brano):
    from pge.shared.exceptions import SampleNotFoundError

    gen, master, importato = _crea(
        brano, {**STREAM_DEL_LABORATORIO, 'sample': 'assente.wav'})

    with pytest.raises(SampleNotFoundError) as exc:
        gen.create_elements()

    err = exc.value
    assert err.stream_id == 'risacca'
    assert err.config_file == importato
    assert err.imported_by.master == master
    messaggio = err.user_message()
    assert f"Config:       {importato}" in messaggio
    assert f"Importato da: {master}, streams[1]" in messaggio


def test_un_campo_mancante_nel_file_importato_nomina_il_file(brano):
    from pge.shared.exceptions import MissingFieldError

    gen, master, importato = _crea(
        brano, {**STREAM_DEL_LABORATORIO, 'sample': None})

    with pytest.raises(MissingFieldError) as exc:
        gen.create_elements()

    err = exc.value
    assert err.config_file == importato
    assert f"Importato da: {master}, streams[1]" in err.user_message()


def test_un_errore_di_uno_stream_del_master_nomina_il_master(brano):
    """La meta' che non deve cambiare: lo stream scritto nel master."""
    from pge.shared.exceptions import SampleNotFoundError

    brano.scrivi('streams/risacca.yml', _documento_del_laboratorio())
    master = brano.scrivi('brano.yml', {'seed': 1441, 'streams': [
        {'file': 'streams/risacca.yml'},
        {'stream_id': 'altro', 'sample': 'assente.wav'},
    ]})
    gen = brano.generator()
    gen.load_yaml()

    with pytest.raises(SampleNotFoundError) as exc:
        gen.create_elements()

    assert exc.value.config_file == master
    assert exc.value.imported_by is None
    assert 'Importato da' not in exc.value.user_message()


def test_il_generator_sa_da_dove_viene_ogni_stream_importato(brano):
    """`stream_origins`: id effettivo -> la voce del master che lo importa.

    E' la superficie per chi incorpora il motore (l'editor, un language
    server): lo stream risolto non porta piu' `file:`, e questa e' la sola
    traccia di dove stia scritto.
    """
    _gen, master, importato = _crea(brano, STREAM_DEL_LABORATORIO)

    assert _gen.stream_origins == {'risacca': StreamFileOrigin(
        master=master, index=1, file='streams/risacca.yml', path=importato)}


# =============================================================================
# La cache lavora sullo stream risolto (regola 1)
# =============================================================================
# Il gemello in-process dell'e2e `TestStreamFile` (tests/e2e/test_cache_e2e.py,
# che passa da `make` con csound): qui il renderer e' numpy e vero, cosi' gira
# in `make tests` senza binari esterni. La regola e' la stessa per i tre
# backend, perche' sta nel fingerprint del dict risolto, non nel renderer.

def _rendi_con_cache(brano, capsys):
    """Un render STEMS con cache; ritorna `{stream_id: 'DIRTY'|'clean'}`."""
    from pge import api

    gen = api.load_generator(str(brano.root / 'brano.yml'),
                             samples_dir=brano.samples_dir)
    api.render(gen, str(brano.root / 'out' / 'brano.wav'),
               renderer='numpy', per_stream=True,
               samples_dir=brano.samples_dir,
               cache_manifest_path=str(brano.root / 'cache' / 'brano.json'))
    out = capsys.readouterr().out
    stati = dict(_FORMA_CACHE.match(r).groups() for r in out.splitlines()
                 if _FORMA_CACHE.match(r))
    return stati


def _brano_con_cache(brano, stream_importato):
    (brano.root / 'out').mkdir(exist_ok=True)
    brano.scrivi('streams/risacca.yml',
                 _documento_del_laboratorio(stream=stream_importato))
    brano.scrivi('brano.yml', {'seed': 1441, 'streams': [
        {'file': 'streams/risacca.yml', 'onset': 0.5},
        {'stream_id': 'fermo', 'sample': SAMPLE, 'duration': 0.5,
         'density': 10},
    ]})


def test_modificare_il_file_importato_marca_dirty_solo_quello_stream(
        brano, capsys):
    _brano_con_cache(brano, STREAM_DEL_LABORATORIO)
    assert _rendi_con_cache(brano, capsys) == {
        'risacca': 'DIRTY', 'fermo': 'DIRTY'}
    assert _rendi_con_cache(brano, capsys) == {
        'risacca': 'clean', 'fermo': 'clean'}

    _brano_con_cache(brano, {**STREAM_DEL_LABORATORIO, 'density': 40})

    assert _rendi_con_cache(brano, capsys) == {
        'risacca': 'DIRTY', 'fermo': 'clean'}
    # E il GC, che legge gli id dal documento risolto, non l'ha preso per un
    # orfano: lo stem e' ancora li'.
    assert list((brano.root / 'out').glob('brano__risacca.*'))


def test_spostare_uno_stream_in_un_file_non_invalida_la_cache(brano, capsys):
    """Lo stream risolto e' lo stesso dict dello stream scritto nel master.

    Stesso id, stesso piazzamento, stesso contenuto: stesso fingerprint. Chi
    estrae uno stream del brano in un file del laboratorio non paga un
    re-render per averlo fatto.
    """
    (brano.root / 'out').mkdir(exist_ok=True)
    inline = {k: v for k, v in STREAM_DEL_LABORATORIO.items()
              if k != 'onset'}
    brano.scrivi('brano.yml', {'seed': 1441, 'streams': [
        {**inline, 'onset': 0.5}]})
    assert _rendi_con_cache(brano, capsys) == {'risacca': 'DIRTY'}

    _brano_con_cache(brano, STREAM_DEL_LABORATORIO)
    brano.scrivi('brano.yml', {'seed': 1441, 'streams': [
        {'file': 'streams/risacca.yml', 'onset': 0.5}]})

    assert _rendi_con_cache(brano, capsys) == {'risacca': 'clean'}
