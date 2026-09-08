# src/generator.py
"""
Generator: orchestratore principale del sistema di sintesi granulare.

Refactored per separare le responsabilità:
- FtableManager: gestione function tables
- ScoreWriter: scrittura file .sco
- Generator: orchestrazione e coordinamento

Mantiene backward compatibility con l'API pubblica esistente.
"""
from __future__ import annotations

import yaml
import re
import math
from typing import List, Dict, Any

from pge.core.stream import Stream
from pge.rendering.ftable_manager import FtableManager
from pge.rendering.score_writer import ScoreWriter
from pge.controllers.window_controller import WindowController
from pge.shared.exceptions import (
    ConfigError, ConfigFileNotFoundError, SampleNotFoundError,
    config_parse_error, config_read_error,
)
from pge.shared.seeding import session_seed

class Generator:
    """
    Orchestratore principale per generazione score Csound.

    Responsabilita:
    - Caricare e preprocessare configurazione YAML
    - Creare Stream dai dati YAML
    - Coordinare FtableManager e ScoreWriter
    - Applicare logica solo/mute

    Public API:
    - load_yaml() -> dict
    - create_elements() -> List[Stream]
    - generate_score_file(output_path: str) -> None

    Attributes:
        yaml_path: path file configurazione YAML
        data: dati YAML preprocessati
        streams: lista Stream creati
        ftable_manager: gestore function tables
        score_writer: scrittore file score
    """
    
    def __init__(self, yaml_path: str, samples_dir=None):
        """
        Inizializza il Generator.

        Args:
            yaml_path: percorso file YAML di configurazione
            samples_dir: directory dei sample audio, propagata agli Stream
                (Fase 2 refactor library/CLI). None (default) → fallback
                sul globale PATHSAMPLES (comportamento legacy).
        """
        self.yaml_path = yaml_path
        self.samples_dir = samples_dir
        self.data: Dict[str, Any] = None
        self.streams: List[Stream] = []
        # Seed di riproducibilità (issue #81/#154): popolato da load_yaml dalla
        # chiave top-level `seed`. Se assente, create_elements genera un seed
        # di sessione (loggato) e lo assegna qui: seed_is_session=True.
        self.seed = None
        self.seed_is_session = False

        # Delegati specializzati
        self.ftable_manager = FtableManager(start_num=1)
        self.score_writer = ScoreWriter(self.ftable_manager)
        self.stream_data_map: Dict[str, dict] = {}
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def load_yaml(self) -> dict:
        """
        Carica e preprocessa il file YAML.
        
        Valuta espressioni matematiche nelle stringhe (e.g., "(pi)", "(10/2)").
        
        Returns:
            dict: dati YAML preprocessati
            
        Raises:
            ConfigFileNotFoundError: se il file YAML non esiste. Eredita
                anche FileNotFoundError (issue #257), quindi chi catturava
                il builtin continua a catturarlo.
            ConfigParseError: se il file YAML è malformato o non
                decodificabile in UTF-8 (l'encoding della specifica YAML,
                dichiarato esplicitamente nell'open). Eredita anche
                yaml.YAMLError, per la stessa ragione.
            ConfigReadError: se il file c'è ma il sistema operativo non lo
                apre — una directory al posto del file, permessi negati.
                Eredita anche OSError, per la stessa ragione.
        """
        # Il try avvolge il solo caricamento dello YAML, e questo e' un
        # vincolo, non una comodita': ogni altro `open()` che finisse qui
        # dentro uscirebbe travestito da configurazione mancante o
        # illeggibile -- e da qui esce ogni `OSError`, non piu' il solo
        # `FileNotFoundError`, quindi il vincolo e' piu' stretto di prima.
        # E' la forma
        # esatta del difetto che la #257 chiude un livello piu' su, dove
        # `cli.main()` catturava il builtin per estensione del blocco.
        try:
            # `encoding` esplicito, non il preferito del processo: lo YAML e'
            # UTF-8 per specifica, `open(path, 'r')` no -- decodifica nel
            # locale, che su Windows e' cp1252 e sotto un locale C senza PEP
            # 540 e' ascii. La differenza non e' teorica: tredici dei
            # `configs/*.yml` di questo repository portano byte non-ASCII, e
            # senza questa parola un file valido usciva di qui come
            # `ConfigParseError` -- «File di configurazione malformato» su un
            # file che non ha niente che non va, cioe' la peggiore delle due
            # diagnosi possibili. Su cp1252, che ogni byte lo decodifica, non
            # c'e' nemmeno l'errore: i valori stringa arrivano storpiati in
            # silenzio.
            with open(self.yaml_path, 'r', encoding='utf-8') as f:
                raw_data = yaml.safe_load(f)
        except FileNotFoundError as err:
            raise ConfigFileNotFoundError(self.yaml_path) from err
        except yaml.YAMLError as err:
            # Le factory, non il costruttore: la sottoclasse restituita eredita
            # anche il tipo *concreto* della causa, cosi' un
            # `isinstance(e, yaml.MarkedYAMLError)` o un
            # `except IsADirectoryError` scritti a valle continuano a
            # funzionare come quando `load_yaml` lasciava salire il builtin.
            raise config_parse_error(self.yaml_path, err) from err
        except UnicodeDecodeError as err:
            # Il terzo modo in cui un file di config non si legge. `open()` e'
            # in modalita' testo e su UTF-8, quindi la decodifica la fa Python
            # e un file salvato in latin-1 esce di qui prima che PyYAML veda
            # un byte;
            # aperto in binario sarebbe stato PyYAML a rifiutarlo, con un
            # `yaml.reader.ReaderError` -- cioe' un `yaml.YAMLError`. Stesso
            # guasto, stesso tipo.
            raise config_parse_error(self.yaml_path, err) from err
        except OSError as err:
            # E tutti gli altri: `IsADirectoryError` (`pge configs/ out.wav`,
            # il typo che la tab-completion fabbrica da sola),
            # `PermissionError`, il resto di `OSError`. Sta dopo il ramo
            # `FileNotFoundError`, che di `OSError` e' una sottoclasse: erano
            # gli ultimi del percorso di caricamento a uscire come traceback
            # dal ramo generico della CLI, cioe' l'enumerazione dei modi in
            # cui un file di config non si legge era incompleta proprio sul
            # caso piu' probabile.
            raise config_read_error(self.yaml_path, err) from err

        self.data = self._eval_math_expressions(raw_data)
        # Seed top-level opzionale (issue #81): None se assente (il session
        # seed viene derivato in create_elements, non qui).
        self.seed = self.data.get('seed') if isinstance(self.data, dict) else None
        self.seed_is_session = False
        return self.data
    
    def create_elements(self) -> List[Stream]:
        """
        Crea Stream dai dati YAML.

        Applica logica solo/mute, registra ftables, genera grani.

        Returns:
            List[Stream]: stream creati

        Raises:
            ValueError: se load_yaml() non è stato chiamato
        """
        if self.data is None:
            raise ValueError("Devi prima caricare il YAML con load_yaml()")

        # Seed effettivo del run (issue #154): niente random globale. Ogni sito
        # stocastico riceve un RNG derivato per (seed, stream_id, componente)
        # via shared.seeding.component_rng — solo/mute, cache stems e ordine di
        # materializzazione non alterano i grani degli altri stream. Senza
        # `seed:` nello YAML si genera un seed di sessione, loggato: il run
        # resta ricostruibile a posteriori copiandolo nello YAML.
        if self.seed is None:
            self.seed = session_seed()
            self.seed_is_session = True
            print(
                f"[SEED] Nessun seed nello YAML: seed di sessione {self.seed}. "
                f"Per riprodurre questo run aggiungi 'seed: {self.seed}' allo YAML.",
                flush=True,
            )

        # Estrai e filtra stream
        stream_data_list = self.data.get('streams', [])
        filtered_streams = self._filter_solo_mute(stream_data_list)

        # Crea stream (QUI viene chiamato _register_stream_windows)
        try:
            self._create_streams(filtered_streams)
        except (SampleNotFoundError, ConfigError) as err:
            err.config_file = self.yaml_path
            raise

        return self.streams


    def generate_score_file(self, output_path: str = 'output.sco'):
        """
        Genera il file score Csound completo.
        
        Delega la scrittura a ScoreWriter.
        
        Args:
            output_path: percorso file .sco output
        """
        self.score_writer.write_score(
            filepath=output_path,
            streams=self.streams,
            yaml_source=self.yaml_path
        )

    def generate_score_files_per_stream(
        self,
        output_dir: str = '.',
        base_name: str = None,
        cache_manager=None,
        aif_dir: str = None,
        aif_prefix: str = None,   
    ) -> List[str]:
        """
        Genera un file .sco separato per ogni stream.

        Il nome file e' derivato da stream_id.
        Se base_name e' fornito: {base_name}_{stream_id}.sco
        Altrimenti: {stream_id}.sco

        Se cache_manager e' fornito, vengono scritti solo gli stream dirty.

        Args:
            output_dir: directory di output
            base_name: prefisso opzionale per i nomi file
            cache_manager: StreamCacheManager opzionale per build incrementale
            aif_dir: directory dei .aif, passata a cache_manager per check esistenza

        Returns:
            Lista dei path file .sco generati
        """
        import os
        os.makedirs(output_dir, exist_ok=True)
        generated = []

        # --- Determina quali stream scrivere ---
        if cache_manager is not None:
            raw_dicts = [
                self.stream_data_map[s.stream_id]
                for s in self.streams
                if s.stream_id in self.stream_data_map
            ]
            dirty_dicts = cache_manager.get_dirty_stream_dicts(
                raw_dicts,
                aif_dir=aif_dir,
                aif_prefix=aif_prefix,
            )
            dirty_ids = {d['stream_id'] for d in dirty_dicts}
            streams_to_write = [s for s in self.streams if s.stream_id in dirty_ids]
            print(f"[CACHE] Stream da scrivere: {[s.stream_id for s in streams_to_write]}", flush=True)
        else:
            streams_to_write = self.streams
            dirty_dicts = None

        # --- Scrivi stream ---
        for stream in streams_to_write:
            filename = (
                f"{base_name}_{stream.stream_id}.sco"
                if base_name
                else f"{stream.stream_id}.sco"
            )
            filepath = os.path.join(output_dir, filename)

            self.score_writer.write_score(
                filepath=filepath,
                streams=[stream],
                yaml_source=self.yaml_path
            )
            generated.append(filepath)

        # --- Aggiorna cache dopo scrittura ---
        if cache_manager is not None and dirty_dicts:
            cache_manager.update_after_build(dirty_dicts)

        return generated

    # =========================================================================
    # CREAZIONE STREAM
    # =========================================================================
    
    def _create_streams(self, stream_data_list: list):
        """
        Crea gli stream granulari applicando logica solo/mute.
        
        Args:
            stream_data_list: lista dizionari parametri stream da YAML
        """        
        print(f"Creazione di {len(stream_data_list)} stream...")
        
        for stream_data in stream_data_list:
            # 1. Crea stream
            #import json
            #print(f"[DEBUG] PRIMA Stream({stream_data.get('stream_id')}): {json.dumps(stream_data, default=str)[:200]}", flush=True)

            stream = Stream(stream_data, seed=self.seed,
                            samples_dir=self.samples_dir)
            #print(f"[DEBUG] DOPO  Stream({stream_data.get('stream_id')}): {json.dumps(stream_data, default=str)[:200]}", flush=True)
            self.stream_data_map[stream_data['stream_id']] = stream_data
            # 2. Registra ftable sample
            stream.sample_table_num = self.ftable_manager.register_sample(stream.sample)
            
            # 3. Pre-registra tutte le finestre possibili
            # CHIAMATA QUI ↓
            stream.window_table_map = self._register_stream_windows(stream_data)

            # 4. Generazione grani LAZY (issue #117): NON si chiama qui
            # generate_grains(). I grani si materializzano al primo accesso a
            # stream.voices/.grains (renderer dirty, visualizer, export). Gli
            # stream cache-clean, che il renderer salta su is_dirty prima di
            # leggere .voices, non generano mai i grani. Tabelle e costruzione
            # Stream restano invece eager (numerazione FtableManager).
            self.streams.append(stream)
            print(f"  → Stream '{stream.stream_id}': {stream}")
    
    def _filter_solo_mute(self, stream_data_list: list) -> list:
        """
        Applica logica solo/mute agli stream.
        
        Regole:
        - Se almeno uno stream ha 'solo' → prendi SOLO quelli con 'solo'
        - Altrimenti → prendi tutti TRANNE quelli con 'mute'
        
        Args:
            stream_data_list: lista dizionari stream
            
        Returns:
            list: stream filtrati
        """
        # Controlla se c'è almeno un solo
        solo_mode = any('solo' in s for s in stream_data_list)
        
        if solo_mode:
            # Modalità SOLO: prendi solo quelli con flag 'solo'
            filtered = [s for s in stream_data_list if 'solo' in s]
            print(
                f"⚡ SOLO MODE: creazione di {len(filtered)} stream "
                f"(su {len(stream_data_list)} totali)"
            )
        else:
            # Modalità normale: escludi solo quelli muted
            filtered = [s for s in stream_data_list if 'mute' not in s]
            muted_count = len(stream_data_list) - len(filtered)
            
            if muted_count > 0:
                print(f"🔇 {muted_count} stream muted")
        
        return filtered
    
    # =========================================================================
    # PREPROCESSING YAML
    # =========================================================================
    
    def _eval_math_expressions(self, obj):
        """
        Valuta espressioni matematiche nei valori YAML.
        
        Riconosce pattern "(espressione)" e valuta l'espressione.
        Supporta: operatori aritmetici, costanti (pi, e), funzioni base.
        
        Args:
            obj: oggetto da preprocessare (dict, list, str, number)
            
        Returns:
            oggetto con espressioni valutate
            
        Examples:
            "(10 + 5)" → 15
            "(pi * 2)" → 6.283...
            "(max(3, 7))" → 7
        """
        # Ricorsione su dict
        if isinstance(obj, dict):
            return {
                k: self._eval_math_expressions(v) 
                for k, v in obj.items()
            }
        
        # Ricorsione su list
        elif isinstance(obj, list):
            return [self._eval_math_expressions(item) for item in obj]
        
        # Valutazione stringhe con pattern (...)
        elif isinstance(obj, str):
            # Regex: cattura espressioni tra parentesi
            # Supporta lettere per costanti (pi, e) e funzioni
            pattern = r'\(([a-zA-Z0-9+\-*/.() ]+)\)'
            
            def evaluate_match(match):
                expr = match.group(1)
                try:
                    # Dizionario funzioni/costanti sicure
                    safe_dict = {
                        'abs': abs,
                        'int': int,
                        'float': float,
                        'min': min,
                        'max': max,
                        'pow': pow,
                        'pi': math.pi,
                        'e': math.e
                    }
                    
                    # Valuta espressione in ambiente sicuro
                    result = eval(expr, {"__builtins__": {}}, safe_dict)
                    return str(result)
                    
                except Exception as e:
                    print(
                        f"⚠️  Warning: impossibile valutare '{expr}': {e}"
                    )
                    # Ritorna espressione originale se fallisce
                    return match.group(0)
            
            # Sostituisci tutte le espressioni
            evaluated = re.sub(pattern, evaluate_match, obj)
            
            # Converti in numero se possibile
            try:
                return float(evaluated) if '.' in evaluated else int(evaluated)
            except ValueError:
                return evaluated
        
        # Altri tipi: passa through
        else:
            return obj
        
    def _register_stream_windows(self, stream_data: dict) -> dict:
        """Pre-registra tutte le finestre per questo stream."""
        stream_id = stream_data.get('stream_id', 'unknown')
        
        # USA METODO STATICO (no istanza temporanea!)
        possible_windows = WindowController.parse_window_list(
            params=stream_data.get('grain', {}),
            stream_id=stream_id
        )
        
        # Registra tutte le finestre nel FtableManager
        window_map = {}
        for window_name in possible_windows:
            table_num = self.ftable_manager.register_window(window_name)
            window_map[window_name] = table_num
        
        return window_map
        
