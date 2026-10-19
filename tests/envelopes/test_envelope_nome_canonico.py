"""
test_envelope_nome_canonico.py

Il nome dell'interpolazione che `Envelope` tiene e' quello canonico, non
quello scritto (issue #300).

`InterpolationStrategyFactory` legge il nome senza badare a maiuscole e spazi
attorno, quindi `{type: Cubic, points: ...}` si costruisce e rende. Ma
`Envelope` teneva il nome com'era scritto e lo confrontava alla lettera nei due
punti che decidono le tangenti della cubica: con `Cubic` la strategy era
`CubicInterpolation`, ma senza le tangenti di Fritsch-Carlson, e ogni segmento
diventava uno smoothstep piatto su ogni breakpoint. Nessun errore e nessun
avviso: il render partiva, e la curva era un'altra.

I numeri di riferimento sono quelli misurati nella issue, su `cubic` scritto
canonico: e' la curva che tutte le grafie devono rendere.

Organizzazione:
1. La forma dict: `type` con maiuscole o spazi
2. Lo slot interp del compatto, che l'envelope prende come proprio tipo
3. Il nome che l'envelope tiene
4. Attraverso lo Stream, dove la issue ha misurato

I due lettori fuori da `Envelope` — lo stile dell'export SV e il ramo a
gradini della partitura — sono provati accanto ai loro test:
`tests/export/test_sv_exporter.py` e
`tests/rendering/test_score_visualizer_per_segment.py`.
"""

import pytest

from pge.envelopes.envelope import Envelope

PUNTI = [[0, 10], [0.6, 40], [1.2, 15], [2.0, 30]]
ISTANTI = (0.3, 0.45, 1.5, 1.8)

# Le grafie che la factory legge come `cubic` e che `Envelope` confrontava
# alla lettera.
GRAFIE_CUBIC = ('Cubic', ' cubic ', 'CUBIC', '\tCuBiC\n')


def _valori(env):
    return [env.evaluate(t) for t in ISTANTI]


# =============================================================================
# 1. LA FORMA DICT
# =============================================================================

class TestFormaDict:
    """Il `type` del dict e' il tipo di ogni segmento senza un tipo proprio."""

    @pytest.mark.parametrize('grafia', GRAFIE_CUBIC)
    def test_rende_la_curva_di_cubic(self, grafia):
        canonico = Envelope({'type': 'cubic', 'points': PUNTI})
        scritto = Envelope({'type': grafia, 'points': PUNTI})

        assert _valori(scritto) == pytest.approx(_valori(canonico))
        assert scritto.integrate(0, 2.0) == pytest.approx(
            canonico.integrate(0, 2.0))


# =============================================================================
# 2. LO SLOT INTERP DEL COMPATTO
# =============================================================================

# Lo stesso pattern dei PUNTI: un ciclo solo su 2 s rimette i breakpoint agli
# stessi istanti, quindi la curva di riferimento e' la stessa.
PATTERN = [[0, 10], [30, 40], [60, 15], [100, 30]]


def _compatto(interp):
    return [PATTERN, 2.0, 1, interp]


class TestSlotDelCompatto:
    """Lo slot interp del compatto diventa il tipo dell'envelope: nella forma
    diretta, o dal primo compatto di una lista che lo dichiara."""

    @pytest.mark.parametrize('grafia', GRAFIE_CUBIC)
    def test_forma_diretta(self, grafia):
        canonico = Envelope(_compatto('cubic'))
        scritto = Envelope(_compatto(grafia))

        assert _valori(scritto) == pytest.approx(_valori(canonico))
        assert scritto.integrate(0, 2.0) == pytest.approx(
            canonico.integrate(0, 2.0))

    @pytest.mark.parametrize('grafia', GRAFIE_CUBIC)
    def test_dentro_una_lista(self, grafia):
        coda = [[2.5, 20], [3.0, 10]]
        canonico = Envelope([_compatto('cubic')] + coda)
        scritto = Envelope([_compatto(grafia)] + coda)

        istanti = ISTANTI + (2.25, 2.75)
        assert ([scritto.evaluate(t) for t in istanti]
                == pytest.approx([canonico.evaluate(t) for t in istanti]))
        assert scritto.integrate(0, 3.0) == pytest.approx(
            canonico.integrate(0, 3.0))


class TestEnvelopePerSegmento:
    """Con un tipo sul punto l'envelope ha un segmento per coppia, e i segmenti
    senza tipo proprio prendono quello globale: la cubica li' prende le
    tangenti dal confronto `t_for_seg == 'cubic'`, che su `Cubic` era falso."""

    PUNTI_CON_ECCEZIONE = [[0, 10], [0.6, 40, 'linear'], [1.2, 15], [2.0, 30]]

    @pytest.mark.parametrize('grafia', GRAFIE_CUBIC)
    def test_type_del_dict(self, grafia):
        canonico = Envelope({'type': 'cubic',
                             'points': self.PUNTI_CON_ECCEZIONE})
        scritto = Envelope({'type': grafia,
                            'points': self.PUNTI_CON_ECCEZIONE})

        assert _valori(scritto) == pytest.approx(_valori(canonico))
        assert scritto.integrate(0, 2.0) == pytest.approx(
            canonico.integrate(0, 2.0))

    @pytest.mark.parametrize('grafia', GRAFIE_CUBIC)
    def test_slot_del_compatto(self, grafia):
        pattern = [[0, 10], [30, 40, 'linear'], [60, 15], [100, 30]]
        canonico = Envelope([pattern, 2.0, 1, 'cubic'])
        scritto = Envelope([pattern, 2.0, 1, grafia])

        assert _valori(scritto) == pytest.approx(_valori(canonico))


# =============================================================================
# 3. IL NOME CHE L'ENVELOPE TIENE
# =============================================================================

class TestIlNomeTenuto:
    """`env.type` e' la chiave del registro: chi lo legge alla lettera — le
    tangenti, l'export SV, la partitura — non deve normalizzarlo di nuovo."""

    @pytest.mark.parametrize('grafia,canonico', [
        ('Cubic', 'cubic'), (' cubic ', 'cubic'),
        ('STEP', 'step'), ('Linear', 'linear'),
    ])
    def test_dal_type_del_dict(self, grafia, canonico):
        assert Envelope({'type': grafia, 'points': PUNTI}).type == canonico

    @pytest.mark.parametrize('grafia,canonico', [
        ('CUBIC', 'cubic'), ('Step ', 'step'),
    ])
    def test_dallo_slot_del_compatto(self, grafia, canonico):
        assert Envelope(_compatto(grafia)).type == canonico
        assert Envelope([_compatto(grafia), [3.0, 10]]).type == canonico

    def test_senza_tipo_dichiarato_resta_il_default(self):
        assert Envelope(PUNTI).type == 'linear'
        assert Envelope({'points': PUNTI}).type == 'linear'
        assert Envelope(_compatto(None)).type == 'linear'


# =============================================================================
# 4. ATTRAVERSO LO STREAM
# =============================================================================

class TestAttraversoLoStream:
    """La strada dello YAML: sotto `time_mode: normalized` la scala dei tempi
    passa al costruttore il dict com'e' scritto, coi soli `points` scalati, e
    il nome deve arrivare canonico anche da li'."""

    @pytest.mark.parametrize('time_mode,punti', [
        ('absolute', PUNTI),
        ('normalized', [[t / 2.0, v] for t, v in PUNTI]),
    ])
    @pytest.mark.parametrize('grafia', ('Cubic', ' cubic '))
    def test_density_rende_la_cubica(self, build_stream, grafia,
                                     time_mode, punti):
        def density(tipo):
            stream = build_stream(time_mode=time_mode,
                                  density={'type': tipo, 'points': punti})
            return stream.density.value

        canonico, scritto = density('cubic'), density(grafia)

        assert scritto.type == 'cubic'
        assert _valori(scritto) == pytest.approx(_valori(canonico))
        assert scritto.integrate(0, 2.0) == pytest.approx(
            canonico.integrate(0, 2.0))
