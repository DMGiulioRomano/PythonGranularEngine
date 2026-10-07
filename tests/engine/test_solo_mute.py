# =============================================================================
# tests/engine/test_solo_mute.py
# =============================================================================
"""
La regola solo/mute come modulo a se', e perche' (issue #246).

La regola e' una riga di logica su una lista di dizionari: se almeno uno
stream dichiara `solo`, si rendono quelli; altrimenti tutti tranne i `mute`.
Non tocca niente del motore -- ne' uno Stream, ne' un renderer, ne' numpy -- e
stava dentro `Generator` come metodo che non usava `self`.

Il prezzo lo pagava un altro repository. PGE-ui ne tiene un mirror JS
(`PGEBackend.streamsEngineBuilds`) perche' il suo `done` di fine render non
pretenda di avere scritto lo stem di uno stream che il motore non ha costruito
-- un 🟢 su un file che nessuno ha riscritto, il caso che la sua suite
chiama per nome. Per confrontare mirror e originale, l'oracolo di parita'
(`tests/parity/engine_oracle.py`) deve chiamare la regola vera; ma
`import pge.engine.generator` tira dentro `Stream` e i renderer, cioe' numpy,
e il job node della sua CI il venv del motore non lo costruisce. Cercava
percio' il `FunctionDef` di `_filter_solo_mute` dentro il `ClassDef` di
`Generator` nell'AST del file, lo compilava e lo eseguiva come funzione libera
con `self` a None. Funzionava, ed era vero; ma pinnava il nome privato di un
metodo *e* il nome della classe che lo conteneva.

Come funzione libera di un modulo senza dipendenze si importa col python nudo
di qualunque runner, e quella deroga non serve piu'.

**Le due righe stampate restano quelle, sullo stesso canale.** Sono interfaccia
(`CLASSIFICAZIONE` in `tests/shared/test_stdout_contract.py`) e `api.py` le
elenca fra cio' che un host vede passare: dicono a chi ha lanciato il render
perche' sta sentendo meno stream di quelli che ha scritto. Il censimento le
segue nel nuovo modulo, canale e forma invariati.

I casi qui sotto sono quelli che stavano nella sezione 4 di
`tests/engine/test_generator.py`, chiamati sulla funzione invece che sul
metodo: non avevano mai avuto bisogno di un `Generator`.
"""

import ast

import pytest

from pge.engine.solo_mute import filter_solo_mute


class TestRegole:
    """Le regole, invariate dallo spostamento della #246."""

    def test_no_solo_no_mute_returns_all(self):
        """Senza solo ne' mute, ritorna tutti gli stream."""
        streams = [
            {'stream_id': 'a'},
            {'stream_id': 'b'},
            {'stream_id': 'c'},
        ]
        result = filter_solo_mute(streams)
        assert len(result) == 3

    def test_solo_mode_returns_only_solo(self):
        """In modalita' solo, ritorna solo gli stream con flag 'solo'."""
        streams = [
            {'stream_id': 'a', 'solo': True},
            {'stream_id': 'b'},
            {'stream_id': 'c'},
        ]
        result = filter_solo_mute(streams)
        assert len(result) == 1
        assert result[0]['stream_id'] == 'a'

    def test_solo_multiple(self):
        """Piu' stream con solo sono tutti inclusi."""
        streams = [
            {'stream_id': 'a', 'solo': True},
            {'stream_id': 'b', 'solo': True},
            {'stream_id': 'c'},
        ]
        result = filter_solo_mute(streams)
        assert len(result) == 2

    def test_mute_excludes_muted(self):
        """Mute esclude gli stream con flag 'mute'."""
        streams = [
            {'stream_id': 'a'},
            {'stream_id': 'b', 'mute': True},
            {'stream_id': 'c'},
        ]
        result = filter_solo_mute(streams)
        assert len(result) == 2
        assert all(s['stream_id'] != 'b' for s in result)

    def test_solo_overrides_mute(self):
        """Solo ha priorita' su mute: in solo mode solo quelli con 'solo'."""
        streams = [
            {'stream_id': 'a', 'solo': True},
            {'stream_id': 'b', 'mute': True},
            {'stream_id': 'c'},
        ]
        result = filter_solo_mute(streams)
        assert len(result) == 1
        assert result[0]['stream_id'] == 'a'

    def test_all_muted_returns_empty(self):
        """Tutti muted ritorna lista vuota."""
        streams = [
            {'stream_id': 'a', 'mute': True},
            {'stream_id': 'b', 'mute': True},
        ]
        result = filter_solo_mute(streams)
        assert len(result) == 0

    def test_empty_list_returns_empty(self):
        """Lista vuota ritorna lista vuota."""
        result = filter_solo_mute([])
        assert result == []

    def test_solo_checks_key_presence_not_value(self):
        """Solo controlla la presenza della chiave, non il valore."""
        streams = [
            {'stream_id': 'a', 'solo': False},  # chiave presente!
            {'stream_id': 'b'},
        ]
        result = filter_solo_mute(streams)
        assert len(result) == 1
        assert result[0]['stream_id'] == 'a'

    def test_mute_checks_key_presence_not_value(self):
        """Mute controlla la presenza della chiave, non il valore."""
        streams = [
            {'stream_id': 'a', 'mute': False},  # chiave presente!
            {'stream_id': 'b'},
        ]
        result = filter_solo_mute(streams)
        assert len(result) == 1
        assert result[0]['stream_id'] == 'b'

    def test_solo_with_value_none(self):
        """Solo con valore None e' ancora rilevato."""
        streams = [
            {'stream_id': 'a', 'solo': None},
            {'stream_id': 'b'},
        ]
        result = filter_solo_mute(streams)
        assert len(result) == 1

    def test_preserves_order(self):
        """filter_solo_mute preserva l'ordine originale."""
        streams = [
            {'stream_id': 'c'},
            {'stream_id': 'a'},
            {'stream_id': 'b', 'mute': True},
        ]
        result = filter_solo_mute(streams)
        assert [s['stream_id'] for s in result] == ['c', 'a']

    def test_solo_and_mute_on_same_stream(self):
        """Stream con sia solo che mute: solo mode include chi ha solo."""
        streams = [
            {'stream_id': 'a', 'solo': True, 'mute': True},
            {'stream_id': 'b'},
        ]
        result = filter_solo_mute(streams)
        # Solo mode attivo perche' c'e' almeno un 'solo'
        # In solo mode, prende chi ha 'solo' -> 'a' ce l'ha
        assert len(result) == 1
        assert result[0]['stream_id'] == 'a'


class TestParametrizzati:
    """Le due coperture sistematiche che stavano nella sezione 12 di
    `test_generator.py`."""

    @pytest.mark.parametrize("n_streams", [0, 1, 2, 5, 10])
    def test_filter_various_sizes(self, n_streams):
        """filter_solo_mute con varie dimensioni lista."""
        streams = [{'stream_id': f's{i}'} for i in range(n_streams)]
        result = filter_solo_mute(streams)
        assert len(result) == n_streams

    @pytest.mark.parametrize("n_muted,total,expected", [
        (0, 3, 3),
        (1, 3, 2),
        (2, 3, 1),
        (3, 3, 0),
    ])
    def test_filter_mute_counts(self, n_muted, total, expected):
        """filter_solo_mute con vari conteggi mute."""
        streams = []
        for i in range(total):
            s = {'stream_id': f's{i}'}
            if i < n_muted:
                s['mute'] = True
            streams.append(s)

        result = filter_solo_mute(streams)
        assert len(result) == expected


class TestLeDueRighe:
    """Il motore dice perche' sta rendendo meno stream di quelli scritti.

    Sono le righe che `api.py` elenca fra cio' che un host vede passare, e
    nessuna delle due va persa nello spostamento: senza, chi rende un brano
    con un `solo` dimenticato dentro sente un file corto e non sa perche'."""

    def test_la_modalita_solo_si_annuncia(self, capsys):
        filter_solo_mute([{'stream_id': 'a', 'solo': True},
                          {'stream_id': 'b'}])
        assert capsys.readouterr().out == (
            "⚡ SOLO MODE: creazione di 1 stream (su 2 totali)\n")

    def test_i_muted_si_contano(self, capsys):
        filter_solo_mute([{'stream_id': 'a'},
                          {'stream_id': 'b', 'mute': True}])
        assert capsys.readouterr().out == "🔇 1 stream muted\n"

    def test_senza_muted_non_dice_niente(self, capsys):
        """Zero muted non stampa una riga che dice zero."""
        filter_solo_mute([{'stream_id': 'a'}, {'stream_id': 'b'}])
        assert capsys.readouterr().out == ""


class TestUnSoloPosto:
    """La regola sta qui e non anche in `Generator`.

    Lo spostamento serve a chi legge: se `generator.py` riaprisse una copia
    del metodo, la lettura a valle tornerebbe a pinnare un nome privato di
    quella classe. E la guardia chiede anche che la regola sia *usata*: una
    che pretendesse la sola assenza resterebbe verde su un motore che ha
    smesso di filtrare, cioe' su un render che ignora mute e solo."""

    def _sorgente_generator(self):
        import pge.engine.generator as g
        with open(g.__file__, encoding='utf-8') as fh:
            return fh.read()

    def test_generator_non_ridefinisce_il_metodo(self):
        albero = ast.parse(self._sorgente_generator())
        definiti = [n.name for n in ast.walk(albero)
                    if isinstance(n, ast.FunctionDef)
                    and n.name in ('filter_solo_mute', '_filter_solo_mute')]
        assert not definiti, (
            "generator.py ridefinisce la regola solo/mute: sta in "
            "pge/engine/solo_mute.py, e un secondo posto e' cio' che la "
            "issue #246 ha tolto")

    def test_generator_la_chiama_importandola(self):
        sorgente = self._sorgente_generator()
        assert 'from pge.engine.solo_mute import filter_solo_mute' in sorgente
        assert 'filter_solo_mute(' in sorgente


class TestModuloLeggero:
    """Niente import fuori dalla stdlib.

    Misurata davvero in un interprete figlio con le dipendenze bloccate dentro
    `tests/shared/test_engine_exceptions.py` (`_MODULI_SENZA_TERZE_PARTI`): qui
    si guarda il sorgente, che e' la diagnosi -- dice *quale* import e'
    comparso."""

    def test_non_importa_niente(self):
        from pge.engine import solo_mute
        with open(solo_mute.__file__, encoding='utf-8') as fh:
            albero = ast.parse(fh.read())
        radici = set()
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Import):
                radici.update(a.name.split('.')[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                radici.add(nodo.module.split('.')[0])
        assert radici <= {'__future__'}, (
            f"solo_mute.py importa {sorted(radici - {'__future__'})}: il "
            f"modulo esiste per essere importabile senza il venv del motore "
            f"(issue #246)")
