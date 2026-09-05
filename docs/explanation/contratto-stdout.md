---
slug: contratto-stdout
type: explanation
status: stable
tags: [logging, stdout, protocollo, pge-ui, strategie]
sources:
  - src/pge/shared/logger.py
  - src/pge/strategies/strategy_registry.py
  - src/pge/strategies/variation_registry.py
  - src/pge/strategies/voice_pan_strategy.py
  - src/pge/rendering/numpy_audio_renderer.py
  - src/pge/rendering/csound_renderer.py
  - src/pge/rendering/supercollider_renderer.py
  - src/pge/rendering/stream_cache_manager.py
  - tests/shared/test_stdout_contract.py
last_synced_commit: db08c65
---

# Il contratto di stdout — protocollo, diagnostica, interfaccia

**Documenti collegati:** [[INDEX]] · [[caching]] · [[architecture]] · [[add-renderer]]

---

## Problema

PGE ha avuto a lungo due canali diagnostici che non si parlavano: il logger di
`src/pge/shared/logger.py`, usato da parser, parameter, pointer e window, e i
`print()` sparsi nel resto del codice. Detta cosi' sembra disordine, ed e' il
motivo per cui la cosa e' rimasta com'era a lungo.

Non e' disordine. **Stdout non e' un canale libero: e' un'interfaccia.**
`render_pipeline.py` di PGE-ui legge le righe di `pge` una per una e ne ricava
gli eventi NDJSON dell'editor — la barra di avanzamento, i pallini di stato dei
singoli stem, l'indice dei file generati. Le righe che quel parser riconosce
sono un contratto fra due repository, e nessuno dei due lo dichiara: sta in una
manciata di regex da una parte e in una manciata di f-string dall'altra.

Da qui il rischio delle due direzioni opposte, che non e' simmetrico:

- portare al logger una riga che PGE-ui parsa **rompe l'interfaccia utente di
  un altro repository senza far fallire un test di PGE**;
- lasciare su stdout una riga che nessuno parsa e' materiale che ogni parser a
  valle deve attraversare — e, il giorno in cui somiglia abbastanza a una riga
  vera, che deve saper *scartare*.

## Modello

Tre categorie, per destinatario e non per contenuto:

| Categoria | Chi la legge | Canale |
|---|---|---|
| **Protocollo** | il parser di PGE-ui | stdout, con quel formato esatto |
| **Diagnostica** | uno sviluppatore che sta estendendo il motore | logger `pge.diagnostics` |
| **Interfaccia CLI** | l'utente, a schermo | stdout, ma non e' protocollo |

Il **protocollo** oggi sono le righe `[CACHE] <id>: DIRTY|clean` — da cui
l'editor deriva `stream-start` e `stream-done` — e i path del blocco
riassuntivo. Restano `print(..., flush=True)`: senza flush arriverebbero a
rendering finito, quando non hanno piu' niente da annunciare.

**A emettere quella riga sono quattro moduli, non tre.** I tre renderer la
stampano sul percorso diretto, uno stream alla volta; la pipeline in due stadi
non passa di li' — `Generator.write_sco_files` delega a
`StreamCacheManager.get_dirty_stream_dicts`, ed e' quel metodo a stampare la
riga per tutti gli stream in blocco, prima che un renderer esista. E' una
distinzione che conta perche' `stream_cache_manager.py` compare anche fra i
moduli con `print()` non ancora classificati (sotto): la sua riga per stream e'
gia' classificata, ed e' protocollo.

Il prefisso `[CACHE]` da solo non identifica il protocollo. Lo stesso metodo
stampa `[CACHE] <n>/<m> stream da ricompilare` e `Generator` stampa
`[CACHE] Stream da scrivere: [...]`: nessuna delle due e' parsata, perche' la
regex di PGE-ui vuole un token *senza spazi* seguito dai due punti. Quel che
identifica il protocollo e' la forma `[CACHE] <id>: <resto>`, ed e' su quella
che si regola la guardia.

La **diagnostica** oggi sono le registrazioni dinamiche di strategy
(`register_density_strategy`, `register_variation_strategy`,
`register_voice_pan_strategy`). Passano da `log_strategy_registration`, che
scrive sul logger `pge.diagnostics`. Quel logger e' fatto di due astensioni:

1. **nessun handler proprio oltre a un `NullHandler`.** Una libreria non
   configura il logging del suo ospite. Qui l'astensione ha anche un effetto
   concreto: `get_engine_logger()` si auto-configura, e configurarsi vuol dire
   `os.makedirs('./logs')` — una cartella materializzata sul disco di chi
   passava di li' solo per registrare una strategy. Il `NullHandler` serve al
   resto: senza handler, `logging` manda i record da WARNING in su a
   `lastResort`, che scrive su stderr;
2. **livello DEBUG.** Sotto il livello di default del root (WARNING) il record
   non viene nemmeno costruito, quindi la diagnostica muta non costa niente su
   un percorso caldo. Chi la vuole fa `logging.basicConfig(level=logging.DEBUG)`,
   e la console di `logging` e' **stderr**: nemmeno accendendola si rientra nel
   canale che PGE-ui parsa.

## Trade-off

**La conferma di registrazione diventa muta.** Prima, registrare una strategy
stampava una riga con la spunta verde; ora non stampa niente finche' l'host non
accende il logging. E' il costo accettato: la registrazione dinamica e'
un'operazione da sviluppatore che in una pipeline di rendering normale non
compare mai, e chi la sta facendo e' esattamente la persona in grado di alzare
un livello di log. Il messaggio non e' andato perso — ha cambiato canale.

**Non c'e' una `configure_diagnostic_logger()`.** Sarebbe stata simmetrica alle
due che esistono (clip ed engine), ma quelle configurano dei *file di
rendering*, cioe' un prodotto del programma; questa avrebbe configurato il
logging di chi importa `pge`, che non e' affare di `pge`.

**La classificazione e' un test, non una prosa.** `tests/shared/test_stdout_contract.py`
legge i sorgenti con `ast` e chiede due cose: che la riga `[CACHE] <id>: ...`
sia ancora un `print()` flushato in tutti e quattro i moduli che la emettono, e
che in `src/pge/strategies/` non ci sia nessun `print()`. Il primo e' l'unico
presidio che csound e supercollider abbiano su quella riga (numpy e il cache
manager hanno anche un test di comportamento); il secondo e' cio' che impedisce
alla porta di riaprirsi in silenzio.

**La guardia riconosce la forma, non il prefisso.** Le chiamate sono
ricomposte in un *template* — ogni interpolazione di una f-string diventa `{}`,
senza guardarci dentro — e cio' che si pretende e' `[CACHE] {}: `. Cercare la
sottostringa `[CACHE]` sarebbe bastato per i renderer e non per il cache
manager, dove sopravvive comunque un `[CACHE] <n>/<m> stream da ricompilare`
che nessuno parsa: la guardia sarebbe rimasta verde dopo aver spostato al
logger l'unica riga che l'editor legge davvero. Due test misurano proprio il
discrimine, cosi' che a indebolirlo qualcosa suoni.

## Implicazioni codice

- **Aggiungi una riga diagnostica** → `get_diagnostic_logger().debug(...)`, con
  formattazione `%s` pigra. Mai `print()`.
- **Aggiungi un renderer** → se dichiara lo stato della cache, la riga
  `[CACHE] <id>: <status>` va su stdout con `flush=True`, e il modulo va
  aggiunto a `MODULI_CON_PROTOCOLLO_CACHE` nella guardia. Vedi [[add-renderer]].
- **Cambi il formato di una riga di protocollo** → e' un cambio di superficie
  pubblica: serve l'analisi d'impatto su PGE-ui e PGE-ls prima, non dopo.
- **Il resto dei `print()`** (`engine/generator.py`,
  `rendering/score_visualizer.py`, `rendering/stream_cache_manager.py`,
  `rendering/score_writer.py`, `cli.py`) non e' ancora classificato: sono gli
  scaglioni successivi. Attenzione a due di quei moduli: non sono omogenei.
  `stream_cache_manager.py` e `generator.py` contengono *anche* righe gia'
  classificate — la riga per stream del primo e' protocollo e ha la sua
  guardia; quel che resta da classificare li' e' il riepilogo
  `[CACHE] <n>/<m> stream da ricompilare` e `[CACHE] Stream da scrivere: [...]`,
  che nessun parser legge. `cli.py` concentra la maggioranza del resto ed e'
  quasi tutto *interfaccia CLI*, cioe' la terza categoria — quella che resta su
  stdout pur non essendo protocollo. E' anche l'unica dove la scelta non e'
  meccanica: la riga per stream dei conteggi di grani (#250) la legge un
  compositore a schermo, non un parser, ma sta sullo stesso canale che un
  parser attraversa.

## Vedi anche

- [[caching]] — cosa dichiara la riga `[CACHE]` e perche' esiste
- [[architecture]] — dove stanno i renderer che la emettono
- [[add-renderer]] — la checklist di un backend nuovo
