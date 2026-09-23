# =============================================================================
# tests/strategies/test_registry.py
# =============================================================================
"""
La classe generica `StrategyRegistry` (issue #184, forma decisa in #177).

Questa suite misura la forma decisa in `docs/explanation/strategy-registry.md`
contro i vincoli che l'hanno scelta. Non e' un doppione dei test di
`voice_pan_strategy`: quelli interrogano il registry di pan attraverso la sua
superficie di modulo, questi interrogano la classe da sola, perche' e' la
classe che gli altri otto registry erediteranno.

Il documento dichiara di aver *misurato* lo scheletro contro quei vincoli
prima di prescriverlo; qui quella misura diventa eseguibile, che e' il punto
del tracer bullet: se la forma non regge, cade adesso e si torna a #177 a
cambiarla, non si aggiunge un caso speciale.
"""

import logging

import pytest

from pge.shared.exceptions import StrategyNotFoundError
from pge.shared.logger import DIAGNOSTIC_LOGGER_NAME


# =============================================================================
# DOPPI DI PROVA
# =============================================================================

class _Base:
    """ABC finta: al registry serve solo da etichetta, non la interroga."""


class _Alfa(_Base):
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _Beta(_Base):
    def __init__(self, *args):
        self.args = args


class _Muto(_Base):
    """Costruttore senza argomenti: la forma di `variation`."""


def _registry(**extra):
    from pge.strategies.registry import StrategyRegistry
    return StrategyRegistry('prova', _Base, {'alfa': _Alfa, **extra})


# =============================================================================
# 1. E' UN DIZIONARIO, E DEVE RESTARLO
# =============================================================================

class TestSuperficieDict:
    """La mappa resta un `dict` sotto il proprio nome di modulo.

    Non e' un dettaglio implementativo: e' il vincolo che ha scelto
    l'ereditarieta' da `dict` invece della composizione. Le fixture dei test
    di strategy fanno snapshot e ripristino con `dict()`/`clear()`/`update()`,
    e la parita' di PGE-ls legge `.keys()` dal modulo del motore.
    """

    def test_e_un_dict(self):
        assert isinstance(_registry(), dict)

    def test_porta_il_contenuto_iniziale(self):
        assert _registry()['alfa'] is _Alfa

    def test_conosce_il_proprio_dominio(self):
        r = _registry()
        assert r.kind == 'prova'

    def test_porta_la_propria_base(self):
        r = _registry()
        assert r.base is _Base

    def test_senza_contenuto_iniziale_nasce_vuoto(self):
        from pge.strategies.registry import StrategyRegistry
        assert StrategyRegistry('vuoto', _Base) == {}


# =============================================================================
# 2. `create()` — TRE FORME DI COSTRUZIONE, UNA PORTA SOLA
# =============================================================================

class TestCreate:
    """Il registry non guarda dentro gli argomenti: li inoltra e basta.

    Le tre forme non sono ipotetiche, sono quelle dei registry che
    convergono: `**kwargs` per le strategy voce, due posizionali per density
    — le cui due classi chiamano il primo parametro con due nomi diversi
    (`fill_factor_param`, `density_param`), quindi per parola chiave non si
    passa affatto — e nessun argomento per variation. Con `*args` la density
    entra dalla stessa porta delle altre invece di avere un `create` proprio,
    che sarebbe esattamente il caso speciale che il tracer bullet vieta.
    """

    def test_costruisce_con_kwargs(self):
        istanza = _registry().create('alfa', spread=120.0)
        assert isinstance(istanza, _Alfa)
        assert istanza.kwargs == {'spread': 120.0}

    def test_costruisce_con_posizionali(self):
        istanza = _registry(beta=_Beta).create('beta', 'param', 'distribuzione')
        assert isinstance(istanza, _Beta)
        assert istanza.args == ('param', 'distribuzione')

    def test_costruisce_senza_argomenti(self):
        assert isinstance(_registry(muto=_Muto).create('muto'), _Muto)

    def test_il_primo_parametro_si_chiama_name(self):
        """La convergenza su `name` e' meta' della issue: e' la chiave del
        registry, non la provenienza del valore."""
        assert isinstance(_registry().create(name='alfa'), _Alfa)


# =============================================================================
# 3. L'ERRORE DI LOOKUP — I TRE CAMPI RESTANO
# =============================================================================

class TestStrategyNotFound:
    """`StrategyNotFoundError` porta `strategy_kind`, `name`, `available`.

    Il dominio non viene ripetuto dal chiamante: e' quello che il registry ha
    ricevuto alla costruzione, quindi `create()` non ha modo di sbagliarlo.
    """

    def test_alza_strategy_not_found(self):
        with pytest.raises(StrategyNotFoundError):
            _registry().create('inesistente')

    def test_riporta_il_dominio_del_registry(self):
        with pytest.raises(StrategyNotFoundError) as exc:
            _registry().create('inesistente')
        assert exc.value.strategy_kind == 'prova'

    def test_riporta_il_nome_cercato(self):
        with pytest.raises(StrategyNotFoundError) as exc:
            _registry().create('inesistente')
        assert exc.value.name == 'inesistente'

    def test_riporta_le_chiavi_disponibili(self):
        with pytest.raises(StrategyNotFoundError) as exc:
            _registry(muto=_Muto).create('inesistente')
        assert sorted(exc.value.available) == ['alfa', 'muto']

    def test_le_disponibili_seguono_le_registrazioni_dinamiche(self):
        """`available` e' letta al momento dell'errore, non congelata alla
        costruzione: una strategy registrata a runtime deve comparire."""
        r = _registry()
        r.register('tardiva', _Muto)
        with pytest.raises(StrategyNotFoundError) as exc:
            r.create('inesistente')
        assert 'tardiva' in exc.value.available


# =============================================================================
# 4. `register()` — REGISTRA E LO DICE AL LOGGER DIAGNOSTICO
# =============================================================================

class TestRegister:
    """Registrare e annunciare la registrazione sono la stessa operazione.

    E' il prezzo dichiarato dell'uniformita': dopo la convergenza non si
    possono piu' separare per registry, che e' precisamente cio' che si
    voleva. La riga e' `DEBUG` su un logger che di default non ha handler,
    quindi non compare a nessuno che non l'abbia accesa.
    """

    def test_registra_la_classe(self):
        r = _registry()
        r.register('nuova', _Muto)
        assert r['nuova'] is _Muto

    def test_la_registrazione_sovrascrive(self):
        r = _registry()
        r.register('alfa', _Muto)
        assert r['alfa'] is _Muto

    def test_la_registrata_e_costruibile(self):
        r = _registry()
        r.register('nuova', _Alfa)
        assert isinstance(r.create('nuova', x=1), _Alfa)

    def test_emette_la_riga_diagnostica(self, caplog):
        r = _registry()
        with caplog.at_level(logging.DEBUG, logger=DIAGNOSTIC_LOGGER_NAME):
            r.register('nuova', _Muto)

        messaggi = [rec.getMessage() for rec in caplog.records
                    if rec.name == DIAGNOSTIC_LOGGER_NAME]
        assert len(messaggi) == 1
        assert 'prova' in messaggi[0]
        assert 'nuova' in messaggi[0]
        assert '_Muto' in messaggi[0]

    def test_il_dominio_della_riga_e_quello_del_registry(self, caplog):
        """Non un letterale scritto a mano accanto alla chiamata: e' `kind`.

        E' questo che uniforma le tre etichette divergenti ('pan voce',
        'density', 'variation') senza che nessun chiamante le ripeta.
        """
        from pge.strategies.registry import StrategyRegistry
        r = StrategyRegistry('dominio_suo', _Base)
        with caplog.at_level(logging.DEBUG, logger=DIAGNOSTIC_LOGGER_NAME):
            r.register('nuova', _Muto)

        messaggi = [rec.getMessage() for rec in caplog.records
                    if rec.name == DIAGNOSTIC_LOGGER_NAME]
        assert 'dominio_suo' in messaggi[0]

    def test_la_registrazione_non_stampa(self, capsys):
        """Stdout e' il canale di protocollo che PGE-ui parsa riga per riga
        (issue #178/#187): una registrazione dinamica non ha titolo a
        attraversarlo."""
        _registry().register('nuova', _Muto)
        catturato = capsys.readouterr()
        assert catturato.out == ''
        assert catturato.err == ''

    def test_la_scrittura_diretta_resta_legale_e_muta(self, caplog):
        """`registry['x'] = cls` non passa per la riga diagnostica.

        E' il costo dichiarato dell'ereditare da `dict`, ed e' voluto: la riga
        appartiene al punto d'ingresso esplicito, e la scrittura diretta e'
        quel che fanno le fixture per rimettere a posto lo stato.
        """
        r = _registry()
        with caplog.at_level(logging.DEBUG, logger=DIAGNOSTIC_LOGGER_NAME):
            r['diretta'] = _Muto

        assert r['diretta'] is _Muto
        assert [rec for rec in caplog.records
                if rec.name == DIAGNOSTIC_LOGGER_NAME] == []

    def test_register_non_verifica_issubclass(self):
        """La base e' portata, non imposta.

        Verificare `issubclass` sarebbe un rifiuto nuovo per gli otto registry
        che convergono — cioe' un cambio di superficie pubblica: chi oggi
        registra una strategy duck-typed smetterebbe di poterlo fare. Se lo si
        vuole, e' una issue sua con la sua analisi d'impatto.
        """
        class Estranea:
            pass

        r = _registry()
        r.register('estranea', Estranea)
        assert r['estranea'] is Estranea

    def test_register_accetta_un_registrabile_senza_dunder_name(self):
        """Il rifiuto non deve rientrare dalla riga diagnostica.

        Il test qui sopra misura la meta' dichiarata — nessun `issubclass` —
        con una *classe*, che `__name__` ce l'ha. La meta' non misurata era
        l'altra: `register` chiama `log_strategy_registration`, che legge
        `strategy_class.__name__`, quindi un registrabile chiamabile ma senza
        quell'attributo veniva rifiutato da una diagnostica.

        Conta dalla #185 perche' i `register_*` di pitch, onset e pointer
        prima assegnavano nel dizionario senza ispezionare niente: passando
        da qui hanno ereditato il rifiuto insieme alla riga.
        """
        import functools

        fabbrica = functools.partial(_Alfa, spread=1.0)
        assert not hasattr(fabbrica, '__name__')

        r = _registry()
        r.register('pigra', fabbrica)
        assert r['pigra'] is fabbrica
        assert isinstance(r.create('pigra'), _Alfa)


# =============================================================================
# 5. SNAPSHOT E RIPRISTINO — IL GIRO CHE FANNO LE FIXTURE
# =============================================================================

class TestSnapshotERipristino:
    """Il giro esatto che la fixture `restore_registry` compie a ogni test.

    E' il vincolo piu' concreto fra quelli che hanno scelto l'ereditarieta' da
    `dict`, e va misurato sulla classe da sola: se cade qui, cade in ogni
    suite di strategy del repo, e conviene saperlo da un test che nomina il
    motivo invece che da venti rossi sparsi.
    """

    def test_snapshot_con_dict(self):
        r = _registry()
        originale = dict(r)
        r.register('temporanea', _Muto)
        r.clear()
        r.update(originale)
        assert dict(r) == {'alfa': _Alfa}

    def test_clear_e_update_non_perdono_il_dominio(self):
        """`clear()` svuota la mappa, non l'oggetto: `kind` e `base` restano.

        Se li perdesse, il registry sopravvivrebbe al ripristino della fixture
        come mappa e morirebbe come registry — e il primo `create()` dopo un
        test alzerebbe `AttributeError` invece dell'errore di dominio.
        """
        r = _registry()
        r.clear()
        r.update({'alfa': _Alfa})
        assert (r.kind, r.base) == ('prova', _Base)

    def test_del_rimuove(self):
        r = _registry()
        del r['alfa']
        assert 'alfa' not in r

    def test_pop_con_default_non_alza(self):
        assert _registry().pop('mai_registrata', None) is None

    def test_pop_restituisce_la_classe(self):
        assert _registry().pop('alfa') is _Alfa

    def test_appartenenza_e_indicizzazione(self):
        r = _registry()
        assert 'alfa' in r
        assert r['alfa'] is _Alfa

    def test_copy_perde_il_dominio_ed_e_voluto(self):
        """`copy()` restituisce un `dict` normale, senza `kind` ne' `create()`.

        E' il costo dichiarato del compromesso: chi vuole uno snapshot ha quel
        che gli serve, chi vuole un registry lo costruisce. Il test lo pinna
        perche' e' una trappola plausibile, non perche' sia desiderabile.
        """
        copia = _registry().copy()
        assert copia == {'alfa': _Alfa}
        assert not hasattr(copia, 'kind')
        assert not hasattr(copia, 'create')
