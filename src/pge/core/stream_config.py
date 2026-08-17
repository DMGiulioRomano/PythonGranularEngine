# stream_config.py
from __future__ import annotations

from dataclasses import dataclass,fields
from typing import Optional, Union

from pge.shared.constants import DEFAULT_OUTPUT_SR
from pge.shared.distribution_strategy import ANCHOR_CENTER


def stream_duration_is_implicit(yaml_data: dict) -> bool:
    """True quando lo stream non dichiara una durata propria (issue #205).

    `is None` (non la truthiness, non `setdefault`) copre sia la chiave assente
    sia `duration: null` esplicito, e lascia fuori `duration: 0`, che e' una
    dichiarazione degenere ma pur sempre una dichiarazione.

    Predicato condiviso, non solo dettaglio di resolve_stream_duration: lo usa
    anche il fingerprint della cache (rendering/stream_cache_manager.py), che
    deve registrare la durata del sample esattamente sugli stream su cui il
    motore la eredita. Se le due letture divergessero, uno stream la cui durata
    dipende dal file audio resterebbe clean al cambiare del file.
    """
    return yaml_data.get('duration') is None


def resolve_stream_duration(yaml_data: dict, sample_dur_sec: float) -> float:
    """Durata dello stream: quella dichiarata, o la durata del sample (issue #205).

    A riposo lo stream risintetizza il sample, quindi l'unica durata non
    arbitraria e' quella del file: `duration` e' un override compositivo.

    Punto unico di risoluzione: la usano sia StreamContext.from_yaml sia
    Stream._init_stream_context, che scrivono la stessa durata su due oggetti.
    """
    if stream_duration_is_implicit(yaml_data):
        return sample_dur_sec
    return yaml_data['duration']


def stream_onset_is_implicit(yaml_data: dict) -> bool:
    """True quando lo stream non dichiara una posizione propria (issue #220).

    Stesso predicato di stream_duration_is_implicit e per la stessa ragione:
    `is None` copre sia la chiave assente sia `onset: null` esplicito, e lascia
    fuori `onset: 0`, che nel risultato e' indistinguibile dal default ma
    nell'intenzione e' una dichiarazione.
    """
    return yaml_data.get('onset') is None


def resolve_stream_onset(yaml_data: dict) -> float:
    """Posizione dello stream: quella dichiarata, o l'origine (issue #220).

    Uno stream che non dichiara nulla comincia all'origine della timeline: 0
    non e' "nulla", e' l'origine. `onset` e' un override compositivo.

    A differenza di resolve_stream_duration non prende nessun dato esterno: il
    default e' la costante 0.0, non un valore derivato dal file audio. E' il
    motivo per cui qui il fingerprint della cache non si muove.

    Punto unico di risoluzione: la usano sia StreamContext.from_yaml sia
    Stream._init_stream_context, che scrivono lo stesso onset su due oggetti.
    """
    if stream_onset_is_implicit(yaml_data):
        return 0.0
    return yaml_data['onset']


@dataclass(frozen=True)
class StreamContext:
    stream_id: str
    onset: float
    duration: float
    sample: str
    sample_dur_sec: float
    # Sample rate di output del motore: riferimento per le conversioni
    # campioni <-> secondi (grain.duration_unit) e per il bound minimo
    # dinamico di grain_duration (1 campione).
    output_sr: int = DEFAULT_OUTPUT_SR
    # Identità RNG condivisibile (issue #169): se valorizzato, sostituisce
    # lo stream_id nella derivazione degli RNG locali (shared/seeding.py),
    # così stream diversi con lo stesso rng_group pescano le stesse sequenze.
    # None (default) → identità = stream_id, hash identico a prima di #169.
    rng_group: Optional[str] = None

    @property
    def rng_id(self) -> str:
        """Identità usata nella derivazione RNG: rng_group se dichiarato,
        altrimenti stream_id (isolamento per-stream, contratto issue #154).
        Falsy (None, stringa vuota) → fallback a stream_id: una stringa vuota
        non deve diventare un'identità condivisa accidentale."""
        return self.rng_group or self.stream_id

    @classmethod
    def from_yaml(cls, yaml_data: dict, sample_dur_sec: float, allow_none: bool = True) -> 'StreamConfig':
        """
        Contiene solo configurazioni che determinano il l'identità e il contesto dello stream.
        """
        # Campi NON letti dal dict per-stream:
        # - sample_dur_sec: derivato dal file audio, mai dal YAML.
        # - output_sr: config GLOBALE del motore. Deve restare la costante di
        #   sistema (con cui il renderer viene costruito, main.py): leggerlo
        #   dallo YAML del singolo stream farebbe divergere la conversione
        #   samples->secondi e il bound minimo dal sample rate del rendering.
        #   Resta al default finche' una vera configurabilita' globale non e'
        #   cablata su entrambi (context E renderer).
        _engine_global = {'sample_dur_sec', 'output_sr'}
        field_names = [f.name for f in fields(cls) if f.name not in _engine_global]

        
        if allow_none:
            # Includi i campi anche se il valore è None
            kwargs = {name: yaml_data[name] for name in field_names if name in yaml_data}
        else:
            # Includi solo campi con valori non-None
            kwargs = {
                name: yaml_data[name] 
                for name in field_names 
                if name in yaml_data and yaml_data[name] is not None
            }
        kwargs['sample_dur_sec'] = sample_dur_sec
        # onset assente o null -> origine della timeline (issue #220), duration
        # assente o null -> durata del sample (issue #205). Entrambe risolte
        # prima di cls(**kwargs): nessuna delle due puo' avere un default nel
        # dataclass, sono dichiarate prima di sample/sample_dur_sec che ne
        # resterebbero obbligati ad averne uno. Senza questa riga `onset: null`
        # entrerebbe nel dataclass frozen come None e l'errore riemergerebbe
        # lontano, come TypeError nell'aritmetica dei grani.
        kwargs['onset'] = resolve_stream_onset(kwargs)
        kwargs['duration'] = resolve_stream_duration(kwargs, sample_dur_sec)
        return cls(**kwargs)


@dataclass(frozen=True)
class StreamConfig:
    """
    Configurazione completa per un singolo stream.
    Contiene:
    - Regole di processo: deviation_probability, time_mode, distribution_mode, etc.
    - Contesto
    
    Condiviso tra Stream e i suoi controller (PointerController, 
    PitchController, DensityController, VoiceManager).
    """
    deviation_probability: Optional[Union[dict, bool, int, float, list]] = False
    range_always_active: bool = False
    distribution_mode: str = 'uniform'
    # Ancora dei `_range` dichiarati: 'center' (default, banda
    # [base - range/2, base + range/2]) o 'min' (banda [base, base + range]).
    # Asse ortogonale a distribution_mode: quella dice come la banda si
    # riempie, questa dove cade `base` dentro la banda. Non tocca il jitter
    # implicito, che resta centrato (non c'e' nessun range dichiarato da
    # reinterpretare). Vedi shared/distribution_strategy.py.
    range_anchor: str = ANCHOR_CENTER
    time_mode: str = 'absolute'
    time_scale: float = 1.0
    clip_strategy: str = 'overflow_margin'
    clip_margin: float = 0.0
    # Seed effettivo del run (issue #154): YAML top-level o session seed,
    # iniettato da Stream (non letto dal dict per-stream). None → fallback
    # legacy sul random globale nei componenti stocastici.
    seed: Optional[Union[int, str]] = None
    context: Optional[StreamContext] = None

    @classmethod
    def from_yaml(cls, yaml_data: dict, context: StreamContext, allow_none: bool = True,
                  seed: Optional[Union[int, str]] = None) -> 'StreamConfig':
        """
        Regole di processo per la sintesi granulare.
        
        Contiene solo configurazioni che determinano il COMPORTAMENTO
        del sistema, non l'identità o il contesto dello stream.
        
        Può essere condiviso tra più stream che utilizzano le stesse
        regole di processo (anche se tipicamente ogni stream ha il suo).
        """
        field_names = [f.name for f in fields(cls)]
        
        if allow_none:
            # Includi i campi anche se il valore è None
            kwargs = {name: yaml_data[name] for name in field_names if name in yaml_data}
        else:
            # Includi solo campi con valori non-None
            kwargs = {
                name: yaml_data[name]
                for name in field_names
                if name in yaml_data and yaml_data[name] is not None
            }
        kwargs['context'] = context
        # Il seed è top-level nello YAML (non per-stream): arriva dal chiamante
        # e sovrascrive qualsiasi chiave omonima nel dict dello stream.
        kwargs['seed'] = seed
        return cls(**kwargs)
