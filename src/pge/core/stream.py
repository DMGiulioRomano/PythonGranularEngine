# src/stream.py
"""
Stream - Orchestratore per la sintesi granulare.

Fase 6 del refactoring: questa classe coordina i controller specializzati:
- ParameterEvaluator: parsing e validazione parametri
- PointerController: posizionamento testina con loop e jitter
- PitchController: trasposizione (semitoni o ratio)
- DensityController: densità e distribuzione temporale
- VoicesController: il blocco voices: — il VoiceManager delle voci multiple
  (offset pitch/onset/pointer/pan), num_voices e scatter

Mantiene backward compatibility con Generator e ScoreVisualizer.
Ispirato al DMX-1000 di Barry Truax (1988).
"""
from __future__ import annotations

import random
import warnings
from math import floor, log10
from typing import Dict, List, Optional, Union

from pge.core.grain import Grain
from pge.envelopes.envelope import Envelope, scale_raw_param_values
from pge.controllers.window_controller import WindowController
from pge.controllers.pointer_controller import PointerController
from pge.controllers.pitch_controller import PitchController
from pge.controllers.density_controller import DensityController
from pge.controllers.voices_controller import VoicesController
from pge.shared.constants import SECONDS_PER_MILLISECOND
from pge.shared.utils import get_sample_duration
from pge.shared.exceptions import (
    EngineRuntimeError,
    InvalidFieldValueError,
    MissingFieldError,
    SampleNotFoundError,
)
from pge.expressions.expression import ExpressionSource
from pge.expressions.fields import EXPRESSION_FIELDS
from pge.maps.map_set import MapSet
from pge.parameters.parameter_definitions import range_unit_is_relative
from pge.parameters.parameter_schema import STREAM_PARAMETER_SCHEMA
from pge.parameters.parameter_orchestrator import ParameterOrchestrator
from pge.parameters.read_direction import (
    READ_DIRECTION_FIELD,
    normalize_read_direction,
)
from pge.core.stream_config import StreamConfig, StreamContext
from pge.controllers.voice_manager import VoiceConfig
from pge.strategies.grain_clip_strategy import GrainClipStrategyFactory
from pge.strategies.strategie import nominal_value
from dataclasses import fields, replace, MISSING as dataclass_MISSING


# Unita' di misura ammesse per grain.duration / grain.duration_range.
# 'seconds' e' il default storico; 'samples' esprime i valori in campioni
# alla frequenza di output del motore (StreamContext.output_sr);
# 'milliseconds' e' la scala comoda per la grana udibile (1-1000 ms) e usa un
# fattore fisso, indipendente dal sample rate.
#
# Questa e l'etichetta qui sotto PGE-ls le legge dall'AST di QUESTO file, come
# letterali: spostate o scritte con un'espressione, la sua parita' salta in
# verde. Stanno nel registro di tests/test_downstream_surface_pge_ls.py (#269).
GRAIN_DURATION_UNITS = ('seconds', 'samples', 'milliseconds')

# Etichette per i messaggi d'errore: unita' -> nome dei valori attesi.
_GRAIN_DURATION_UNIT_LABELS = {
    'samples': 'campioni',
    'milliseconds': 'millisecondi',
}

_ENVELOPE_TABLE_NUM_DEPRECATO = (
    "Stream.envelope_table_num e' deprecato (issue #285) e sara' rimosso in "
    "PGE 10.0.0: il Generator non l'ha mai assegnato, e il motore non lo "
    "legge. I riferimenti che la generazione usa sono sample_table_num e "
    "window_table_map."
)


class Stream:
    """
    Orchestratore per uno stream di sintesi granulare.
    
    Coordina i controller specializzati e genera la lista di grani.
    Mantiene compatibilità con Generator e ScoreVisualizer.
    
    Attributes:
        voices: List[List[Grain]] - grani organizzati per voce, unica
                fonte di verita' su quali grani esistono
        grains: List[Grain] - vista DERIVATA di voices, flat e ordinata per
                onset (backward compatibility). Ricalcolata a ogni lettura:
                non e' un secondo stato da tenere in sync (issue #201)
    """
    
    def __init__(self, params: dict, seed=None, samples_dir=None):
        """
        Inizializza lo stream dai parametri YAML.

        Args:
            params: dizionario parametri dallo YAML
            seed: seed effettivo del run (issue #81/#154): YAML top-level o
                  session seed del Generator. Propagato, via StreamConfig,
                  alle voice strategy stocastiche e agli RNG per-componente
                  (parameter/gate/iot/window/detune). None (default) →
                  comportamento legacy (hash() per-voce, random globale
                  per i componenti).
            samples_dir: directory dei sample audio (Fase 2 refactor
                  library/CLI). None (default) → fallback sul globale
                  PATHSAMPLES (comportamento legacy).
        """
        # Seed di riproducibilità. Lo porta l'argomento, via StreamConfig, alle
        # strategy stocastiche delle voci (VoicesController, #284) e agli RNG
        # per-componente: l'attributo resta, ma il motore non lo rilegge — il
        # solo lettore era il wiring delle voci, che da #284 lo prende da
        # `config.seed` — e cambiarlo dopo la costruzione non sposta niente.
        self.seed = seed
        # Directory sample iniettata. Il sample si cerca qui sotto con
        # l'argomento, una volta sola (issue #283): l'attributo resta, ma il
        # motore non lo rilegge, e cambiarlo dopo la costruzione non sposta
        # niente.
        self.samples_dir = samples_dir
        # === 3. CONFIGURATION ===
        sample = params.get('sample')
        stream_id = params.get('stream_id', 'unknown')
        if not sample:
            err = MissingFieldError(
                field='sample',
                hint="specificare il nome del file wav (es. sample: mio_file.wav)",
            )
            err.stream_id = stream_id
            raise err
        try:
            sample_dur = get_sample_duration(sample, base_path=samples_dir)
        except SampleNotFoundError as err:
            err.stream_id = stream_id
            raise
        self._check_required_context_fields(params, stream_id)
        config = StreamConfig.from_yaml(
            params,
            StreamContext.from_yaml(params, sample_dur_sec=sample_dur),
            seed=seed,
        )
        # === 3.2. MAPPE (issue #308) ===
        # Dopo il config, perche' gli envelope di `r` e di `clock` (issue
        # #310) seguono la durata e il `time_mode` dello stream; prima di
        # tutto il resto, perche' le condividono il parser dei parametri, che
        # ci compila le espressioni, e il giro dei grani, che le muove. Il
        # config e' congelato: le mappe ci entrano con una copia.
        self._maps = self._init_maps(params, config)
        config = replace(config, map_set=self._maps)
        self._init_stream_context(config.context)
        # === 3.4. GRAIN.IOT CON UN ALTRO MODO DI DENSITA' (issue #311) ===
        # Sullo YAML grezzo, prima dei tre passi qui sotto: dopo, `grain.iot`
        # e' gia' in secondi o impacchettata come espressione, e il «Trovato»
        # dell'errore non sarebbe piu' cio' che l'utente ha scritto.
        DensityController.check_iot_exclusivity(params, config)
        # === 3.5. UNITA' DI MISURA DURATA GRANO ===
        # Da qui in poi grain.duration e' in secondi qualunque sia l'unita'
        # dichiarata nello YAML, e con lei grain.duration_range — tranne dove
        # quest'ultima e' una frazione della base (grain.duration_range_unit:
        # relative, issue #267), che adimensionale era e adimensionale resta.
        params = self._pre_normalize_grain_params(params, config.context.output_sr)
        # === 3.55. UNITA' DELL'ATTESA (issue #311) ===
        # grain.iot segue grain.duration_unit come grain.duration, in un
        # passo suo (vedi _pre_normalize_grain_iot).
        params = self._pre_normalize_grain_iot(params, config.context.output_sr)
        # === 3.6. ESPRESSIONI (issue #308) ===
        # Dove un'espressione vale, la stringa diventa un ExpressionSource col
        # fattore dell'unita': una stringa non si riscala, si riscala il suo
        # risultato.
        params = self._wrap_grain_expressions(params, config.context.output_sr)
        # === 4. PARAMETRI SPECIALI ===
        self._init_grain_reverse(params)
        # Da qui in poi grain.read_direction, se dichiarata, e' gia' validata e
        # normalizzata a interpolazione 'step'.
        params = self._normalize_read_direction(params)
        # === 5. PARAMETRI DIRETTI (riceve config) ===
        self._init_stream_parameters(params, config)
        # === 6. CONTROLLER (riceve config) ===
        self._init_controllers(params, config)
        # === 7. GRAIN CLIP STRATEGY ===
        self._clip_strategy = GrainClipStrategyFactory.create(
            config.clip_strategy,
            margin=config.clip_margin,
        )
        # === 8. RIFERIMENTI CSOUND (assegnati da Generator) ===
        # `Generator._create_stream` li assegna dopo la costruzione, e la
        # generazione dei grani li pretende entrambi: `generate_grains` dice
        # quale manca invece di morire dentro `_create_grain` (issue #283).
        self.sample_table_num: Optional[int] = None
        self.window_table_map: Optional[Dict[str, int]] = None
        # Il terzo riferimento il Generator non l'ha mai assegnato: deprecato
        # (issue #285), resta dietro la property `envelope_table_num` finche'
        # esce, in 10.0.0.
        self._envelope_table_num: Optional[int] = None
        # === 9. STATO ===
        # Generazione lazy dei grani (issue #117): i backing field restano vuoti
        # finche' qualcuno non legge le property voices/grains, che innescano
        # generate_grains() al primo accesso. Cosi' il Generator non genera i
        # grani per gli stream cache-clean (il renderer short-circuita su
        # is_dirty prima di leggere .voices), risparmiando il costo dominante.
        # _voices e' l'unico backing field: la vista flat .grains e' derivata
        # (issue #201), non un secondo campo da mantenere allineato.
        self._voices: List[List[Grain]] = []
        self.generated = False
        # Le attese della voce 0 come sono uscite, `(tempo, attesa)`, in
        # modalita' `grain.iot` (issue #311): da qui la densita' emersa
        # (effective_density_curve). Le scrive generate_grains.
        self._emerged_iot: List[tuple] = []

    @staticmethod
    def _required_context_fields() -> set:
        """Campi StreamContext che il YAML deve fornire: quelli senza default.

        Esclusi, pur non avendo un default nel dataclass:
        - sample_dur_sec: derivato dal file audio, mai dal YAML;
        - duration: se assente vale la durata del sample (issue #205), risolta
          da resolve_stream_duration invece che pretesa dallo YAML;
        - onset: se assente vale l'origine della timeline (issue #220), risolto
          da resolve_stream_onset. Restano due le condizioni di esistenza di
          uno stream: stream_id e sample.
        """
        return {
            field.name for field in fields(StreamContext)
            if field.name not in ('sample_dur_sec', 'duration', 'onset')
            and field.default is dataclass_MISSING
            and field.default_factory is dataclass_MISSING
        }

    def _check_required_context_fields(self, params, stream_id):
        """Verifica campi obbligatori StreamContext prima di StreamConfig.from_yaml.

        Oggi il ramo plurale non scatta mai da qui: i campi richiesti sono due,
        stream_id e sample, e `sample` e' controllato prima in __init__, che si
        ferma li'. Quindi `missing` e' al massimo {'stream_id'}. Il sorted() e
        il ramo plurale restano per il prossimo campo di contesto senza default.
        Nessun test li raggiunge piu' saltando __init__ (issue #283): il
        messaggio plurale lo prova `tests/shared/test_engine_exceptions.py`.
        """
        missing = self._required_context_fields() - set(params.keys())
        if missing:
            missing_list = sorted(missing)
            err = MissingFieldError(fields=missing_list)
            err.stream_id = stream_id
            raise err

    def _init_stream_context(self, context: StreamContext) -> None:
        """I campi di contesto dello Stream sono quelli del contesto che ha
        appena costruito (issue #283).

        Prima li ri-derivava dal dizionario con le stesse funzioni che
        `StreamContext.from_yaml` aveva gia' chiamato: due copie della stessa
        regola, tenute allineate chiamando lo stesso helper, e l'header del
        sample letto due volte. Qui il contesto e' gia' validato — i campi
        obbligatori li ha controllati `_check_required_context_fields` — e
        `onset` (issue #220) e `duration` (issue #205) gia' risolti.

        Restano attributi e non diventano property sul contesto, che e'
        congelato: `page_layout`, `score_visualizer`, i renderer, gli export e
        la generazione dei grani li leggono come attributi dello stream.

        I campi obbligatori si copiano dallo stesso elenco che
        `_check_required_context_fields` pretende dallo YAML: il prossimo campo
        di contesto senza default arriva sullo stream senza toccare qui.
        """
        for campo in self._required_context_fields():
            setattr(self, campo, getattr(context, campo))
        self.sample_dur_sec = context.sample_dur_sec
        self.onset = context.onset
        self.duration = context.duration

    def _init_stream_parameters(self, params: dict, config: StreamConfig) -> None:
        """
        Inizializza parametri diretti di Stream usando ParameterOrchestrator.

        Design Pattern: Data-Driven Configuration
        - Lo schema STREAM_PARAMETER_SCHEMA definisce COSA caricare
        - ParameterOrchestrator sa COME crearlo
        - Stream riceve i Parameter già pronti
        """
        _orchestrator = ParameterOrchestrator(config=config)

        # 3. Crea tutti i parametri
        parameters = _orchestrator.create_all_parameters(
            params,
            schema=STREAM_PARAMETER_SCHEMA
        )
        
        # 4. Assegna come attributi
        for name, param in parameters.items():
            setattr(self, name, param)

    # =========================================================================
    # INIZIALIZZAZIONE CONTROLLER
    # =========================================================================
    
    def _init_controllers(self, params: dict, config: StreamConfig) -> None:
        """Inizializza tutti i controller con i loro parametri."""
        # POINTER CONTROLLER
        self._pointer = PointerController(
            params=params.get('pointer', {}),
            config=config
        )
        
        # PITCH CONTROLLER
        self._pitch = PitchController(
            params=params.get('pitch', {}),
            config=config
            )
        
        # DENSITY CONTROLLER
        self._density = DensityController(
            params=params,
            config=config
        )

        self._window_controller = WindowController(
            params=params.get('grain', {}),
            config=config
        )

        # VOICES CONTROLLER (issue #284): il blocco `voices:` entra nel suo
        # controller come gli altri quattro, e lo Stream legge da lui quel che
        # il blocco produce — VoiceManager, num_voices, scatter e l'unita'
        # dell'offset di pointer — invece di scriverlo su di se'.
        self._voices_controller = VoicesController(
            params=params.get('voices', {}),
            config=config
        )

    def _pre_normalize_grain_params(self, params: dict, output_sr: int) -> dict:
        """
        Conversione di unita' per la durata del grano (modello loop_unit).

        Se grain.duration_unit non e' 'seconds', scala grain.duration e
        grain.duration_range fino ai secondi su scalari ed envelope-like (solo
        i valori Y; l'asse X resta tempo). Il fattore dipende dall'unita':
        1/output_sr per 'samples', 1e-3 per 'milliseconds'.

        `grain.duration_range_unit: relative` (issue #267) toglie il range da
        quella conversione: li' il numero non e' una durata ma una FRAZIONE
        della durata, e una frazione non ha unita' da convertire. Convertirla
        sarebbe il modo peggiore di sbagliare — `duration_range: 0.5` sotto
        `duration_unit: samples` diventerebbe 0.5/48000, la variazione
        sparirebbe, e non ci sarebbe ne' un errore ne' un warning da leggere.

        Unico punto del sistema che legge 'duration_unit' dal dizionario
        grezzo: e' un meta-parametro che controlla l'interpretazione degli
        altri, non un valore sintetizzabile. Vale anche per il secondo
        meta-parametro letto qui, 'duration_range_unit', di cui pero' questo
        metodo non e' l'unico lettore: la validazione del vocabolario e
        l'errore per un `relative` senza range stanno nell'orchestratore, che
        conosce i path YAML e sa nominarli. Qui serve solo sapere se il range
        va convertito, quindi la lettura e' pura (range_unit_is_relative).

        Il dict originale non viene mutato (cache fingerprint e
        stream_data_map leggono i dati grezzi).

        La parita' di PGE-ls estrae questo metodo dall'AST e lo esegue con un
        namespace scritto a mano: un nome globale nuovo nel corpo, di la', e'
        un NameError. Il registro di tests/test_downstream_surface_pge_ls.py
        dice quali (#269).
        """
        grain = params.get('grain')
        if not isinstance(grain, dict) or 'duration_unit' not in grain:
            return params

        unit = grain['duration_unit']
        if unit not in GRAIN_DURATION_UNITS:
            err = InvalidFieldValueError(
                field='grain.duration_unit',
                value=unit,
                hint=f"unità disponibili: {list(GRAIN_DURATION_UNITS)}",
            )
            err.stream_id = self.stream_id
            raise err

        if unit == 'seconds':
            return params

        # Unita' non-secondi: il default seconds (0.05) NON viene scalato, e
        # quindi una grain.duration implicita resterebbe in secondi mentre chi
        # ha scritto l'unita' la legge in campioni o millisecondi. Pretendi una
        # duration esplicita.
        #
        # Il vincolo riguarda la BASE, e solo lei. La ragione storica —
        # «altrimenti base e range finiscono in domini diversi» — copre un ramo
        # solo da quando il range puo' essere una frazione (issue #267): li' il
        # range e' adimensionale per costruzione, l'unita' governa la sola base,
        # e il vincolo resta in piedi lo stesso perche' e' il default in secondi
        # a non voler dire quel che l'utente intende.
        label = _GRAIN_DURATION_UNIT_LABELS[unit]
        if grain.get('duration') is None:
            err = MissingFieldError(
                field='grain.duration',
                hint=(f"con grain.duration_unit: {unit} la durata va indicata "
                      f"esplicitamente in {label} (il default 0.05 e' in "
                      "secondi e non verrebbe convertito)."),
            )
            err.stream_id = self.stream_id
            raise err

        # 'samples' dipende dal sample rate di output, 'milliseconds' no.
        factor = (
            1.0 / output_sr if unit == 'samples' else SECONDS_PER_MILLISECOND
        )
        # Il range entra nella conversione solo se e' una durata; se e' una
        # frazione della base (issue #267) resta com'e' scritto.
        keys = ('duration',) if range_unit_is_relative(
            grain.get('duration_range_unit')) else ('duration', 'duration_range')

        scaled_grain = dict(grain)
        for key in keys:
            if key in scaled_grain and scaled_grain[key] is not None:
                scaled_grain[key] = scale_raw_param_values(scaled_grain[key], factor)

        scaled_params = dict(params)
        scaled_params['grain'] = scaled_grain
        return scaled_params

    @staticmethod
    def _init_maps(params: dict, config: StreamConfig) -> MapSet:
        """Le mappe dichiarate in `maps:` (issue #308), o un insieme vuoto.

        La chiave assente e' uno stream senza mappe. La chiave scritta e
        lasciata vuota no: passa a `MapSet.from_yaml`, che la rifiuta.
        """
        stream_id = config.context.stream_id
        if 'maps' not in params:
            return MapSet(stream_id=stream_id)
        return MapSet.from_yaml(
            params['maps'],
            stream_id=stream_id,
            duration=config.context.duration,
            time_mode=config.time_mode,
            output_sr=config.context.output_sr,
        )

    @staticmethod
    def _grain_unit_factor(grain: dict, output_sr: int) -> float:
        """Il fattore che porta in secondi un valore scritto nell'unita' di
        `grain.duration_unit`, gia' validata da `_pre_normalize_grain_params`.

        Lo leggono i due passi che seguono quel metodo senza poterci stare
        dentro: PGE-ls lo estrae dall'AST e lo esegue con un namespace
        scritto a mano (#269), e un nome nuovo nel suo corpo — o una terza
        chiave fra quelle che scala — di la' e' un rosso su ogni PR.
        """
        unit = grain.get('duration_unit', 'seconds')
        if unit == 'samples':
            return 1.0 / output_sr
        if unit == 'milliseconds':
            return SECONDS_PER_MILLISECOND
        return 1.0

    def _pre_normalize_grain_iot(self, params: dict, output_sr: int) -> dict:
        """`grain.iot` segue `grain.duration_unit`, come `grain.duration`
        (issue #311): un'attesa scritta in millisecondi o in campioni arriva
        al parser in secondi.

        Scala numeri ed envelope (solo i valori Y), con la stessa funzione
        di `grain.duration`. Un'espressione no: e' una stringa, e il fattore
        lo porta al suo risultato `_wrap_grain_expressions`.

        Non muta il dict originale (il fingerprint della cache legge i dati
        grezzi).
        """
        grain = params.get('grain')
        if not isinstance(grain, dict) or grain.get('iot') is None:
            return params
        factor = self._grain_unit_factor(grain, output_sr)
        if factor == 1.0 or isinstance(grain['iot'], str):
            return params

        scaled_grain = dict(grain)
        scaled_grain['iot'] = scale_raw_param_values(grain['iot'], factor)
        scaled_params = dict(params)
        scaled_params['grain'] = scaled_grain
        return scaled_params

    def _wrap_grain_expressions(self, params: dict, output_sr: int) -> dict:
        """Riconosce le espressioni nei campi del grano in cui valgono
        (`EXPRESSION_FIELDS`) e porta loro l'unita' di misura.

        `_pre_normalize_grain_params` riscala i valori grezzi di
        `grain.duration` — numeri ed envelope — ma una stringa la lascia
        com'e': di un'espressione non si puo' riscalare il testo, si riscala
        il **risultato**. Il fattore e' lo stesso, letto dalla stessa
        `grain.duration_unit` (`_grain_unit_factor`).

        Come gli altri normalizzatori non muta il dict originale.
        """
        grain = params.get('grain')
        if not isinstance(grain, dict):
            return params

        factor = self._grain_unit_factor(grain, output_sr)

        wrapped = None
        for field in EXPRESSION_FIELDS:
            block, _, key = field.partition('.')
            if block != 'grain' or not isinstance(grain.get(key), str):
                continue
            if wrapped is None:
                wrapped = dict(grain)
            wrapped[key] = ExpressionSource(
                grain[key], field=field, scale=factor)

        if wrapped is None:
            return params
        wrapped_params = dict(params)
        wrapped_params['grain'] = wrapped
        return wrapped_params

    def _init_grain_reverse(self, params: dict) -> None:
        """
        Inizializza parametri reverse del grano.

        Semantica YAML RISTRETTA:
        - Chiave ASSENTE → 'auto' (segue pointer_speed)
        - Chiave PRESENTE (reverse:) → DEVE essere vuota, significa True (forzato reverse)
        - reverse: true/false/auto → ERRORE! Non accettati

        Examples YAML validi:
            grain:
            # reverse assente → auto mode

            grain:
                reverse:  # ← Unico modo per forzare reverse

        Examples YAML INVALIDI:
            grain:
                reverse: true    # x ERRORE
                reverse: false   # x ERRORE
                reverse: 'auto'  # x ERRORE

        Qui vive anche il rifiuto della coppia `reverse` + `read_direction`
        (issue #207): le due chiavi governano la stessa grandezza con
        semantiche opposte.

        Come `_pre_normalize_grain_params`, la parita' di PGE-ls lo estrae
        dall'AST e lo esegue con un namespace scritto a mano e un `self` che
        porta il solo `stream_id`: vedi tests/test_downstream_surface_pge_ls.py
        (#269).
        """
        grain_params = params.get('grain', {}) or {}

        # Exclusivity group 'grain_direction': entrambe presenti e' ERRORE, non
        # una priorita'. Il precedente vicino (loop_end / loop_dur) risolve per
        # priorita', ma li' le due chiavi dicono la stessa cosa in due modi;
        # qui dicono cose diverse, e scegliere in silenzio nasconderebbe
        # l'errore dell'utente invece di segnalarlo. Prima di ogni altra
        # validazione: e' il problema da risolvere per primo.
        if 'reverse' in grain_params and 'read_direction' in grain_params:
            err = InvalidFieldValueError(
                field=READ_DIRECTION_FIELD,
                value=grain_params['read_direction'],
                hint=(
                    "grain.read_direction e grain.reverse governano la stessa "
                    "grandezza — il verso di lettura del grano — con semantiche "
                    "opposte, e non possono coesistere.\n"
                    "  Tieni grain.read_direction (-1 indietro, +1 avanti, "
                    "anche come envelope) oppure grain.reverse (chiave vuota = "
                    "sempre indietro), non entrambe."
                ),
            )
            err.stream_id = self.stream_id
            raise err

        if 'reverse' in grain_params:
            # Validazione: se la chiave è presente, DEVE essere None (vuota)
            value = grain_params['reverse']
            if value is not None:
                err = InvalidFieldValueError(
                    field='grain.reverse',
                    value=value,
                    hint=(
                        "grain.reverse deve essere lasciato vuoto.\n"
                        "  Sintassi corretta:\n"
                        "    grain:\n"
                        "      reverse:  # senza valore\n"
                        "  Per seguire pointer_speed, ometti completamente 'reverse'."
                    ),
                )
                err.stream_id = self.stream_id
                raise err
            
            # Chiave presente e vuota → reverse forzato
            self.grain_reverse_mode = True
        else:
            # Chiave assente → auto mode (segue speed)
            self.grain_reverse_mode = 'auto'

    def _normalize_read_direction(self, params: dict) -> dict:
        """
        Valida `grain.read_direction` e le impone l'interpolazione `step`.

        Stesso modello di `_pre_normalize_grain_params`: legge il valore grezzo
        dal dizionario, lo riscrive per il parser a valle e non muta l'originale
        (fingerprint della cache e stream_data_map leggono i dati grezzi).

        La regola sta in `parameters/read_direction.py`; qui si attribuisce
        l'errore allo stream, cosi' un verso scritto male dice in quale stream
        cercarlo.
        """
        grain = params.get('grain')
        if not isinstance(grain, dict) or 'read_direction' not in grain:
            return params

        try:
            value = normalize_read_direction(grain['read_direction'])
        except InvalidFieldValueError as err:
            err.stream_id = self.stream_id
            raise

        normalized_grain = dict(grain)
        normalized_grain['read_direction'] = value

        normalized_params = dict(params)
        normalized_params['grain'] = normalized_grain
        return normalized_params

    # =========================================================================
    # GENERAZIONE GRANI
    # =========================================================================
    
    def generate_grains(self) -> List[List[Grain]]:
        """
        Genera grani per tutte le voci.

        Per ogni tick temporale, genera un grano per ogni voce attiva.
        La densità complessiva è density × num_voices (ogni voce ha il
        proprio loop temporale indipendente con lo stesso inter-onset).

        Returns:
            List[List[Grain]]: grani organizzati per voce (voce 0 = riferimento)

        Raises:
            EngineRuntimeError: se mancano i riferimenti alle tabelle che il
                Generator assegna dopo la costruzione (issue #283).
        """
        self._check_generator_references()
        max_v = self.voice_manager.max_voices

        # Struttura per raccogliere grani per voce (pre-allocata per max_voices)
        all_voice_grains: List[List[Grain]] = [[] for _ in range(max_v)]

        # Cursore temporale indipendente per ogni voce.
        # Con scatter=0 tutti avanzano dello stesso sync_iot → comportamento identico
        # a prima. Con scatter>0 e distribution>0 i cursori divergono nel tempo.
        voice_cursors = [0.0] * max_v

        # Le mappe dello stream (issue #308). Una mappa a `clock: grain` fa un
        # passo per grano e per voce, e lo fa QUI, in testa al giro della
        # voce: prima di ogni lettura dei parametri di quel grano — la durata
        # si legge prima di `_create_grain` — cosi' l'ordine in cui i
        # parametri la leggono non conta. Senza `maps:` l'insieme e' vuoto e
        # le due chiamate non fanno niente.
        maps = self._maps

        # In modalita' `grain.iot` (issue #311) la densita' non e' dichiarata:
        # emerge dalle attese. Quelle della voce 0 si tengono, per
        # pubblicarla come curva a grani fatti.
        record_iot = self._density.mode == 'iot'
        emerged_iot: List[tuple] = []

        while any(c < self.duration for c in voice_cursors):
            # Voice 0 è il riferimento: definisce sync_iot e il valore di scatter
            t0 = voice_cursors[0]
            # La voce 0 legge qui la durata del suo prossimo grano: il passo
            # della sua mappa viene prima. Se ha gia' finito non nasce nessun
            # grano e non c'e' nessun passo: le letture restano sul suo stato.
            if t0 < self.duration:
                maps.advance(0, t0)
            else:
                maps.select(0)
            grain_dur_0 = self.grain_duration.get_value(t0)
            sync_iot = self._density.calculate_inter_onset(t0, grain_dur_0)
            if record_iot and t0 < self.duration:
                emerged_iot.append((t0, sync_iot))
            scatter_val = self.scatter.get_value(t0)

            for voice_index in range(max_v):
                t = voice_cursors[voice_index]

                if t >= self.duration:
                    continue

                # Il giro di questa voce: la sua mappa fa il suo passo (quello
                # della voce 0 e' gia' fatto, qui sopra), e da qui le letture
                # sono le sue. Il passo si conta anche se `num_voices` tiene
                # la voce spenta: la sequenza di una voce non dipende da
                # quando viene accesa.
                if voice_index:
                    maps.advance(voice_index, t)
                else:
                    maps.select(0)

                # Voice 0 condivide già grain_dur_0 (t == t0), evita doppia chiamata
                grain_dur = grain_dur_0 if voice_index == 0 else self.grain_duration.get_value(t)

                # num_voices time-varying: la parte frazionaria del valore interpolato
                # diventa un fade di volume sulla voce di confine (quella che si
                # accende/spegne), invece di un on/off netto.
                #   n_full = floor(value)  → voci 0..n_full-1 a volume pieno
                #   frac   = value - n_full → gain della voce di confine (indice n_full)
                # value è già clampato a [1,64] dai bounds; ri-clamp a max_v. Con
                # interpolazione step (breakpoint interi) frac=0 → on/off come prima.
                value = min(float(max_v), self.num_voices.get_value(t))
                n_full = floor(value)
                frac = value - n_full

                if voice_index < n_full:
                    voice_gain = 1.0
                elif voice_index == n_full and frac > 0.0:
                    voice_gain = frac           # voce di confine: fade graduale
                else:
                    voice_gain = 0.0            # voce spenta → nessun grano

                if voice_gain > 0.0:
                    voice_config = self.voice_manager.get_voice_config(voice_index, t)
                    grain = self._create_grain(t, grain_dur, voice_config,
                                               voice_gain=voice_gain)
                    all_voice_grains[voice_index].append(grain)

                # IOT di questa voce: blend tra sync_iot (condiviso) e indep_iot
                if voice_index == 0 or scatter_val == 0.0:
                    iot = sync_iot
                else:
                    indep_iot = self._density.calculate_inter_onset(t, grain_dur)
                    iot = (1.0 - scatter_val) * sync_iot + scatter_val * indep_iot

                voice_cursors[voice_index] += iot

        # Post-process: applica GrainClipStrategy (Plan 001 U2).
        # stream.voices diventa l'unica fonte di verita' su quali grain esistono.
        # Assegna ai backing field, non alle property: il getter di .voices
        # innescherebbe ricorsivamente generate_grains (generated ancora False).
        self._voices = self._clip_strategy.apply(all_voice_grains, self)
        self._emerged_iot = emerged_iot
        self.generated = True

        return self._voices
    
    def _check_generator_references(self) -> None:
        """I riferimenti alle tabelle ci sono, o un errore dice quali mancano.

        Li assegna `Generator._create_stream` dopo la costruzione: lo stream
        non sa che numero abbiano le tabelle, lo sa il FtableManager. Uno
        Stream costruito da fuori e letto con `.voices` moriva dentro
        `_create_grain`, con un `AttributeError` sulla mappa delle finestre o,
        assegnata quella, col `TypeError` della validazione di `Grain` sulla
        sample table: due errori che non dicevano ne' cosa mancava ne' chi lo
        doveva fornire.
        """
        mancanti = []
        if self.sample_table_num is None:
            mancanti.append('sample_table_num')
        if self.window_table_map is None:
            mancanti.append('window_table_map')
        if mancanti:
            # Lo stream lo nomina il contesto (`stream_id`, la riga `Stream:`
            # di `user_message`), non la testa: errors.md vuole che il
            # contesto non ripeta la testa.
            err = EngineRuntimeError(
                f"Generazione dei grani senza {' e '.join(mancanti)}: i "
                "riferimenti alle tabelle li assegna il Generator dopo la "
                "costruzione (Generator._create_stream). Fuori dal Generator "
                "vanno assegnati prima di leggere .voices."
            )
            err.stream_id = self.stream_id
            raise err

    def _create_grain(self,
                      elapsed_time: float,
                      grain_dur: float,
                      voice_config: Optional['VoiceConfig'] = None,
                      voice_gain: float = 1.0) -> Grain:
        """
        Crea un singolo grano con tutti i parametri calcolati.

        Applica gli offset di VoiceConfig sopra i valori base:
          pitch_ratio  *= pitch_factor   # fattore già materializzato dall'unità
          pointer_pos  = confinato al loop (base + deviazione + pointer_offset)
          pan          += pan_offset
          onset        += onset_offset

        Args:
            elapsed_time: tempo trascorso dall'inizio dello stream
            grain_dur:    durata del grano
            voice_config: offset per questa voce (None = VoiceConfig(1.0,0,0,0))
            voice_gain:   scaler lineare di volume in (0,1] per il fade della voce
                          di confine (1.0 = nessuna attenuazione)

        Returns:
            Grain: oggetto grano completo
        """
        if voice_config is None:
            voice_config = VoiceConfig(1.0, 0.0, 0.0, 0.0)

        grain_reverse = self._calculate_grain_reverse(elapsed_time)

        # === 1. PITCH — base × pitch_factor ===
        # Il fattore di ratio è già materializzato dalla voice pitch strategy
        # tramite la PitchUnit attiva (voce 0 → 1.0). Identità nativa: nessun
        # guard, nessuna conversione qui.
        pitch_ratio = self._pitch.calculate(elapsed_time, grain_reverse=grain_reverse)
        pitch_ratio *= voice_config.pitch_factor

        # === 2. POINTER — base + voice_offset, confinati alla finestra di loop ===
        # Il voice offset viene passato a PointerController.calculate(): con un loop
        # attivo viene confinato DENTRO il loop (wrap modulare), altrimenti sul file
        # intero. calculate() restituisce già la posizione reale di lettura in
        # [0, sample_dur): audio e partitura usano lo stesso valore (issue #79).
        voice_pointer_offset = voice_config.pointer_offset
        if self._voices_controller.pointer_normalized:
            voice_pointer_offset *= self.sample_dur_sec
        pointer_pos = self._pointer.calculate(
            elapsed_time, grain_dur, grain_reverse, voice_offset=voice_pointer_offset
        )

        # === 3. VOLUME ===
        volume = self.volume.get_value(elapsed_time)
        # voice_gain in (0,1] dalla parte frazionaria di num_voices: fade della voce
        # di confine. Applicato in dB (riusa il path dB→lineare di NumPy e Csound,
        # nessun nuovo campo su Grain). Clamp al floor del bound volume (-120 dB) per
        # evitare valori assurdi con frac minuscoli. Il chiamante garantisce > 0.
        if voice_gain != 1.0:
            volume = max(-120.0, volume + 20.0 * log10(voice_gain))

        # === 4. PAN — base + voice_offset ===
        pan = self.pan.get_value(elapsed_time) + voice_config.pan_offset

        # === 5. ONSET — assoluto + voice_onset_offset ===
        absolute_onset = self.onset + elapsed_time + voice_config.onset_offset

        # === 6. WINDOW ===
        window_name = self._window_controller.select_window(elapsed_time)
        window_table_num = self.window_table_map[window_name]

        return Grain(
            onset=absolute_onset,
            duration=grain_dur,
            pointer_pos=pointer_pos,
            pitch_ratio=pitch_ratio,
            volume=volume,
            pan=pan,
            sample_table=self.sample_table_num,
            envelope_table=window_table_num
        )


    def _calculate_grain_reverse(self, elapsed_time: float) -> bool:
        """
        Calcola se il grano deve essere riprodotto al contrario.

        Due superfici dichiarative, mutuamente esclusive (issue #207):

        - `grain.read_direction`: il verso e' il valore dichiarato, -1 indietro
          e +1 avanti, scalare o envelope. Il gate deviation_probability e il
          flip per-grano vivono dentro il Parameter (variation_mode='negate'),
          quindi qui basta leggerne il segno: `get_value()` e' gia' la
          risposta completa.
        - `grain.reverse`: il verso base e' 'auto' (segue pointer_speed) o
          sempre indietro; il flip per-grano arriva dal gate del Parameter
          'reverse'. L'asimmetria e' nella cosa, non nel codice: in 'auto' il
          valore base non e' dichiarato ma dedotto dalla velocita' della
          testina, quindi non c'e' un Parameter da cui leggerlo.

        Args:
            elapsed_time: tempo trascorso dall'inizio dello stream

        Returns:
            bool: True se grano deve essere riprodotto al contrario
        """
        if self.read_direction is not None:
            return self.read_direction.get_value(elapsed_time) < 0

        # 1. Determina il verso base
        if self.grain_reverse_mode == 'auto':
            # Se la testina va indietro, il grano è reverse di base
            is_reverse_base = (self._pointer.get_speed(elapsed_time) < 0)
        else:
            # Chiave presente e vuota: _init_grain_reverse ha gia' rifiutato
            # ogni valore, quindi qui il verso base e' sempre "indietro".
            is_reverse_base = True

        # FASE 2: Controlliamo se dobbiamo FLIPPARE (DeviationProbability/Probabilità)
        # Usiamo il metodo interno del parametro per vedere se il "dado" vince
        # Nota: Qui stiamo "rubando" la logica probabilistica all'oggetto Parameter
        should_flip = self.reverse._probability_gate.should_apply(elapsed_time)

        if should_flip:
            return not is_reverse_base
        return is_reverse_base
    # =========================================================================
    # PROPRIETÀ PER BACKWARD COMPATIBILITY
    # =========================================================================

    @property
    def sampleDurSec(self) -> float:
        """DEPRECATA (issue #285), rimozione prevista in 10.0.0.

        Alias di `sample_dur_sec`, che nessuno legge: ne' il motore, ne' i
        repo a valle (PGE-ls, PGE-ui, gl-ls, granulation-studies, mare-nostrum,
        il paper CIM 2026).
        """
        warnings.warn(
            "Stream.sampleDurSec e' deprecata (issue #285) e sara' rimossa in "
            "PGE 10.0.0: usa Stream.sample_dur_sec, di cui e' un alias.",
            FutureWarning,
            stacklevel=2,
        )
        return self.sample_dur_sec

    @property
    def envelope_table_num(self) -> Optional[int]:
        """DEPRECATO (issue #285), rimozione prevista in 10.0.0.

        Era dichiarato fra i riferimenti Csound che assegna il Generator, che
        pero' non l'ha mai assegnato: assegna `sample_table_num` e
        `window_table_map`. Vale None, a meno che qualcuno lo scriva da fuori;
        per questo avvisa anche in scrittura, invece di sparire.
        """
        warnings.warn(_ENVELOPE_TABLE_NUM_DEPRECATO, FutureWarning, stacklevel=2)
        return self._envelope_table_num

    @envelope_table_num.setter
    def envelope_table_num(self, value: Optional[int]) -> None:
        warnings.warn(_ENVELOPE_TABLE_NUM_DEPRECATO, FutureWarning, stacklevel=2)
        self._envelope_table_num = value
        
    @property
    def density(self) -> Optional[Union[float, Envelope]]:
        """Espone density per Generator/ScoreVisualizer."""
        return self._density.density
    
    @property
    def fill_factor(self) -> Optional[Union[float, Envelope]]:
        """Espone fill_factor per Generator/ScoreVisualizer."""
        return self._density.fill_factor
    
    @property
    def distribution(self):
        """Il valore di `distribution`; None in modalita' `grain.iot` (issue
        #311), dove non e' dichiarata e non agisce."""
        return self._density.distribution.value if hasattr(self._density.distribution, 'value') else self._density.distribution

    @property
    def iot(self):
        """Il Parameter di `grain.iot`, l'attesa fino al grano successivo
        (issue #311); None se lo stream usa `density` o `fill_factor`."""
        return self._density.iot

    @property
    def density_mode(self) -> str:
        """Da dove vengono gli onset: 'fill_factor', 'density' o 'iot'.

        Con 'iot' la densita' non e' dichiarata — `density`, `fill_factor` e
        `distribution` sono None — ed emerge dalle attese: la pubblica
        `effective_density_curve`.
        """
        return self._density.mode
        
    @property
    def pointer_speed(self):
        # Il PointerController espone `speed_ratio` (Parameter), non `speed`.
        return self._pointer.speed_ratio.value

    @property
    def loop_start(self):
        """Espone loop_start del PointerController per ScoreVisualizer."""
        return self._pointer.loop_start

    @property
    def loop_end(self):
        """Espone loop_end del PointerController per ScoreVisualizer."""
        return self._pointer.loop_end

    @property
    def loop_dur(self):
        """Espone loop_dur del PointerController per ScoreVisualizer."""
        return self._pointer.loop_dur

    @property
    def pitch_range(self) -> Union[float, Envelope]:
        """DEPRECATA (issue #285), rimozione prevista in 10.0.0.

        Diceva di esporre pitch_range «per ScoreVisualizer», che pero' legge
        `config['pitch_range']`, un'altra cosa con lo stesso nome; nel motore
        non la legge nessuno, e il range del pitch non e' una curva pubblicata
        (`envelope_extractor._curve_sources`). Senza un lettore, non ha un
        sostituto.
        """
        warnings.warn(
            "Stream.pitch_range e' deprecata (issue #285) e sara' rimossa in "
            "PGE 10.0.0: nel motore non la legge nessuno (ScoreVisualizer "
            "legge config['pitch_range'], un'altra cosa con lo stesso nome) e "
            "non ha un sostituto pubblico. Se ti serve, apri una issue.",
            FutureWarning,
            stacklevel=2,
        )
        return self._pitch.range

    @property
    def pitch_unit(self):
        """Espone l'unità di pitch attiva (PitchUnit) per ScoreVisualizer."""
        return self._pitch.unit

    @property
    def pitch_value(self):
        """Espone il valore base del pitch (Envelope o scalare) per ScoreVisualizer,
        indipendentemente dall'unità (semitoni/cents/quarti/ottavi/edo/ratio)."""
        return self._pitch.value

    @property
    def num_voices(self):
        """Espone num_voices come Parameter (supporta Envelope time-varying)."""
        return self._voices_controller.num_voices

    @property
    def pointer_deviation(self):
        """Parameter della deviazione per-grano del pointer.

        Vive dentro PointerController: senza questo accessore chi legge le
        curve dello stream deve arrivarci per via privata
        (stream._pointer.deviation).
        """
        return getattr(self._pointer, 'deviation', None)

    @property
    def effective_density_curve(self):
        """La densita' reale della voce 0 in grani/secondo, come curva.

        `fill_factor` da solo non dice quanti grani al secondo si ascoltano:
        la densita' vera e' `fill_factor(t) / grain_duration(t)`, che il
        motore calcola a ogni onset (`generate_grains` -> voce 0 ->
        `calculate_inter_onset`) e non conserva. Qui viene campionata.

        Voce 0, la voce di riferimento: e' lei a definire il `sync_iot`. Con
        piu' voci i grani totali sono di piu' — `num_voices` e' una riga a
        parte della partitura.

        None in modalita' `density`: li' sarebbe la copia esatta del
        parametro `density`, gia' disegnato sotto il suo nome.

        In modalita' `grain.iot` (issue #311) e' la densita' che **emerge**:
        l'inverso dell'attesa di ogni grano della voce 0, tenuto fino al
        grano dopo. Non e' una funzione del tempo — un'attesa letta da una
        mappa dipende dai grani gia' nati — quindi non si campiona: si legge
        a grani fatti, e leggerla li genera.
        """
        if self._density.mode == 'iot':
            return self._emerged_density_curve()
        return self._density.density_curve(
            self.duration,
            grain_duration_at=lambda t: nominal_value(self.grain_duration, t),
        )

    def _emerged_density_curve(self):
        """`1 / attesa` per ogni grano della voce 0, a gradini."""
        self.voices  # la generazione e' lazy (issue #117)
        punti = [[tempo, 1.0 / attesa] for tempo, attesa in self._emerged_iot]
        if not punti:
            return None
        if len(punti) == 1:
            punti.append([max(self.duration, punti[0][0]), punti[0][1]])
        return Envelope({'type': 'step', 'points': punti})

    @property
    def map_set(self) -> MapSet:
        """Le mappe dichiarate in `maps:` (issue #308); vuoto se non ce ne
        sono."""
        return self._maps

    @property
    def voice_manager(self):
        """VoiceManager dello stream: sa campionare le curve degli offset
        per-voce (VoiceManager.offset_curves)."""
        return self._voices_controller.voice_manager

    @property
    def scatter(self):
        """Espone scatter come Parameter (supporta Envelope time-varying)."""
        return self._voices_controller.scatter

    # =========================================================================
    # GRANI LAZY (issue #117)
    # =========================================================================

    @property
    def voices(self) -> List[List[Grain]]:
        """Grani organizzati per voce. Lazy: genera al primo accesso."""
        if not self.generated:
            self.generate_grains()
        return self._voices

    @voices.setter
    def voices(self, value: List[List[Grain]]) -> None:
        """Iniezione esplicita dei grani (test/consumer): materializza lo stato.

        Assegnare voices significa "i grani sono questi": marca generated=True
        cosi' una lettura successiva non rigenera sovrascrivendo il valore.
        """
        self._voices = value
        self.generated = True

    @property
    def grains(self) -> List[Grain]:
        """DEPRECATA (issue #201), rimozione prevista in 10.0.0.

        La deprecazione e' uscita con la 9.0.0 annunciando la rimozione «in
        9.0.0», cioe' nella versione stessa che la conteneva: la promessa era
        mal posta, e la rimozione va alla major successiva, come chiede SemVer
        (issue #285).

        Vista flat dei grani, ordinata per onset. DERIVATA da `voices`, non
        memorizzata: ricalcolata a ogni lettura. Prima era un secondo campo,
        allineato solo lungo il percorso `generate_grains()`; fuori da li' le
        due viste divergevano in silenzio.

        Rimpiazzo, a seconda di cosa serve:

            [g for voice in stream.voices for g in voice]          # voice-major
            sorted(..., key=lambda g: g.onset)                     # per onset

        Non sono intercambiabili, ed e' il motivo per cui questa property se
        ne va invece di restare: `Grain` non porta l'indice di voce, quindi la
        vista flat e' lossy rispetto a `voices`, e l'ordine per onset non e'
        quello su cui i renderer sommano (l'ordine delle somme float e' quel
        che rende un rendering riproducibile). Nessun backend la legge —
        score_writer, numpy_audio_renderer, grain_visuals e grain_json_writer
        iterano tutti `voices`.

        Lazy come `voices`: la lettura genera i grani al primo accesso.
        """
        warnings.warn(
            "Stream.grains e' deprecata (issue #201) e sara' rimossa in "
            "PGE 10.0.0: e' una vista derivata di Stream.voices, lossy "
            "(il Grain non porta l'indice di voce) e ordinata per onset "
            "invece che per voce. Usa "
            "'[g for voice in stream.voices for g in voice]', aggiungendo "
            "un sorted(..., key=lambda g: g.onset) se serve l'ordine per "
            "onset.",
            # FutureWarning, non DeprecationWarning: il secondo Python lo
            # filtra di default fuori da __main__, quindi lo vedrebbe solo
            # questo repo sotto pytest — cioe' nessuno dei consumatori a cui
            # il preavviso serve.
            FutureWarning,
            stacklevel=2,
        )
        # Il sort e' stabile: a parita' di onset i grani restano in ordine
        # voice-major, come nella versione memorizzata.
        return sorted(
            (g for voice in self.voices for g in voice),
            key=lambda g: g.onset,
        )

    @grains.setter
    def grains(self, value: List[Grain]) -> None:
        """Sempre rifiutato: `voices` e' l'unico ingresso (issue #201).

        Non deprecato ma rimosso subito, senza ciclo di preavviso: un setter
        che riesce e produce silenzio non ha una versione "che avvisa".

        Il setter esisteva e marcava `generated = True` senza toccare
        `_voices`: lo stream restava senza grani da renderizzare e usciva
        muto, con `__repr__` che continuava a dichiararli presenti.
        """
        raise AttributeError(
            "Stream.grains e' una vista derivata, in sola lettura (issue #201): "
            "assegnarla lasciava .voices vuoto e lo stream renderizzava "
            "silenzio senza segnalare nulla. Per iniettare i grani usa "
            "'stream.voices = [[grano, ...], ...]', una lista per voce."
        )

    # =========================================================================
    # REPR
    # =========================================================================

    def __repr__(self) -> str:
        mode = self.density_mode
        # NON innescare la generazione lazy: _create_streams passa {stream} al
        # diagnostic logger per ogni stream (#188) -- formattato solo se un
        # handler lo chiede, ma allora leggere .grains rigenererebbe tutto.
        # Il conteggio viene da _voices: leggerlo dal vecchio campo _grains
        # faceva mentire il repr su ogni stream con le voci iniettate (#201).
        # Il 'lazy' qui non e' una mancanza: il numero vero lo dice il log a
        # valle del render, da RenderResult.grain_counts (#250).
        grain_count = (sum(len(v) for v in self._voices)
                       if self.generated else 'lazy')
        return (f"Stream(id={self.stream_id}, onset={self.onset}, "
                f"dur={self.duration}, mode={mode}, grains={grain_count})")
