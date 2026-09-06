---
slug: library-vs-cli
type: explanation
status: stable
tags: [api, cli, architecture, refactor]
sources: [src/pge/api.py, src/pge/cli.py, src/main.py]
last_synced_commit: 638f9d6
entry_for: [usare PGE come libreria, capire la divisione API/CLI]
---

# Library vs CLI: la divisione delle policy

## Problema

Storicamente il motore si usava in un solo modo: `python src/main.py
<file.yml>` dalla root del repo. Parsing argv, orchestrazione, print e
`sys.exit` convivevano in un'unica funzione: nessuna parte era riusabile
da codice Python, e i consumatori esterni (granulation-studies)
replicavano l'orchestrazione a mano monkey-patchando i globali.

## Modello

Dal refactor library/CLI (plans/2026-07-08-001) il sistema ha due strati:

- **`pge.api`** — API programmatica: `load_generator`, `build_renderer`,
  `collect_cache_orphans`, `collect_grain_counts`, `render`, `render_file`,
  `export_*`, con le dataclass `CsoundOptions` (input), `RenderResult`
  (output) e `StreamGrainCount` (dentro `RenderResult`). Contratto:
  nessun `print` **nel proprio modulo**, nessun `sys.exit`, nessuna lettura
  di `sys.argv`; errori come eccezioni (`EngineError` e sottoclassi,
  `ValueError`); ogni default filesystem è un parametro esplicito
  (`samples_dir`, `cache_manifest_path`, ...).
- **`pge.cli`** — shell sottile: parsing argv a mano (byte-identico allo
  storico), print, exit code, derivazione dei nomi file. Delega tutta
  l'orchestrazione all'API. `src/main.py` è lo shim permanente; il console
  script `pge` è un alias.

Divisione delle policy (chi decide cosa):

| Decisione | API (default) | CLI (policy) |
|---|---|---|
| `jobs` | `1` (deterministico) | `'auto'` (core-1) |
| renderer | `'numpy'` (nessun binario esterno) | `'csound'` (default storico) |
| path manifest cache | esplicito (`cache_manifest_path`) | `cache_dir/{yaml_basename}.json` + print |
| nomi file derivati (pdf, rpp, sv, GC prefix) | espliciti nei parametri | derivati da yaml/output basename |
| messaggi/exit | mai | sempre |

## Trade-off

- Il parsing argv resta a mano (argparse cambierebbe messaggi, exit code e
  prefix-matching: il contratto CLI è byte-identico, blindato dai golden
  test `tests/test_cli_contract.py`).
- I logger restano singleton di modulo: i `configure_*` sono API pubblica
  e la configurazione è responsabilità del chiamante — l'API non scrive
  mai in `./logs` di sua iniziativa.
- `render()` accetta sia un tipo renderer come stringa sia un'istanza già
  costruita: è il seam che permette alla CLI di costruire prima il
  renderer (per stampare manifest/jobs) senza che i consumatori library
  lo vedano mai.

## Implicazioni codice

- **`pge.api` non stampa, la libreria sì**, ed è una distinzione che conta
  per chi la incorpora (issue #189). Nessuna funzione di `api.py` contiene
  un `print()`; i componenti che orchestra ne contengono, e scrivono su
  stdout mentre lavorano: `Generator` (`[SEED]`, `Creazione di N
  stream...`, `  → Stream '<id>'`, `🔇 N stream muted`), i renderer
  (`[CACHE] <id>: DIRTY|clean`, solo con `cache_manifest_path`),
  `ScoreWriter` sul ramo Csound (`✓ Score generato`), `ScoreVisualizer` da
  `export_score_pdf` (`Analisi completata`, `Esportazione PDF`, ...) e il
  clip logger alla prima inizializzazione (`📝 Clip log file`). Il
  censimento completo, con chi emette cosa, sta nell'intestazione di
  `api.py`; `tests/test_api_stdout.py` lo verifica su output vero, in
  entrambe le direzioni.
- **Il censimento è di stdout, e c'è anche stderr.** Gli avvisi del clip
  logger passano di là (`⚠️  CLIP: ...` dall'handler console, `CLIP: ...`
  dall'avviso di migrazione `loop_unit` della #222, che parla proprio quando
  quella console è spenta), quindi `redirect_stdout` da solo non è silenzio:
  per chi incorpora servono entrambe le redirezioni. Dirlo fa parte del
  punto — un censimento di stdout letto come inventario completo rifà
  l'errore della #189 un piano sotto.
- Quelle righe restano perché fanno parte del contratto stdout della CLI, e
  una almeno è interfaccia vera: `[CACHE] <id>: DIRTY|clean` la parsa PGE-ui
  (`render_pipeline.py`) per gli eventi NDJSON `stream-start`/`stream-done`,
  cioè per l'avanzamento per stream che l'editor mostra durante un render.
  Delle altre non risulta nessun consumatore — accertarlo è la issue #178,
  portarle al logger le #187/#188. Quando succederà, il censimento in
  `api.py` va aggiornato insieme al codice, ed è il test a chiederlo.
- Il GC della cache è una funzione separata (`collect_cache_orphans`)
  perché la CLI deve stamparne l'esito PRIMA del render (ordine stdout);
  `render_file` lo esegue da sé col default `run_cache_gc=True`.
- Il conteggio dei grani (`collect_grain_counts`, issue #250) è la funzione
  speculare: separata per lo stesso motivo di ordine, ma sull'altro lato del
  render, e chiamata da `render` invece che dalla CLI perché il momento non è
  una policy — leggere `voices` prima del render genererebbe i grani in fase
  di stampa (generazione lazy, #117). `RenderResult` porta il risultato, alla
  CLI resta la prosa.
- `import pge` è economico: i simboli pesanti (ScoreVisualizer →
  matplotlib) sono lazy via `__getattr__` di modulo (PEP 562).

## Vedi anche

- [[architecture]] — facade RenderingEngine e OCP
- [[use-as-library]] — come usare PGE da Python
- [[cli]] — riferimento flag CLI
