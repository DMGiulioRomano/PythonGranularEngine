---
slug: use-as-library
type: how-to
status: stable
tags: [api, library, install, render]
sources: [src/pge/api.py, pyproject.toml]
last_synced_commit: 8c50e18
entry_for: [renderizzare da Python, integrare PGE in un altro progetto]
---

# Usare PGE come libreria Python

## Quando usarlo

Quando un altro progetto (script, notebook, tool come granulation-studies)
deve renderizzare YAML del granular engine o esportare partiture senza
passare dalla CLI né monkey-patchare i globali.

## Prerequisiti

- Install editable dal checkout: `pip install -e .` (o `-e ".[dev]"` per i
  test). In un repo che pinna PGE come submodule: `pip install -e engine/`.
- In alternativa, senza install: aggiungere `src/` a `sys.path` (lo shim
  `python src/main.py` fa esattamente questo).

## Passi

1. Render one-shot YAML → audio:

   ```python
   from pge import api

   result = api.render_file(
       'scena.yml', 'out/scena.aif',
       renderer='numpy',            # default library: nessun binario esterno
       samples_dir='refs/',         # directory dei sample, esplicita
       output_sr=48000,
   )
   print(result.audio_paths, result.elapsed_seconds, result.jobs)
   ```

2. Flusso a passi (per riusare il Generator, es. partitura + audio):

   ```python
   gen = api.load_generator('scena.yml', samples_dir='refs/')
   result = api.render(gen, 'out/scena.aif', renderer='numpy',
                       samples_dir='refs/')
   api.export_score_pdf(gen, 'out/scena.pdf', samples_dir='refs/')
   ```

3. Stdout: **la libreria non è silenziosa.** `pge.api` non stampa di suo,
   ma i componenti che orchestra sì, e chi incorpora se li ritrova sul
   proprio stdout: `Generator` annuncia il seed di sessione (`[SEED] ...`),
   quanti stream costruisce e uno per riga; i renderer scrivono `[CACHE]
   <id>: DIRTY|clean` quando c'è un `cache_manifest_path`;
   `export_score_pdf` fa parlare `ScoreVisualizer`. Il censimento completo,
   riga per riga e con chi la emette, sta nell'intestazione di
   `src/pge/api.py`. Fanno parte del contratto stdout della CLI (la riga
   `[CACHE]` la parsa PGE-ui per l'avanzamento per stream), quindi non
   spariranno da sole.

4. Stderr: **`redirect_stdout` da solo non è silenzio.** Il censimento in
   `api.py` è di stdout; gli avvisi del clip logger passano da stderr, da
   qualunque percorso che costruisca envelope — `⚠️  CLIP: ...`
   dall'handler console (attivo di default) e `CLIP: ...` dall'avviso di
   migrazione `loop_unit` (#222), che stampa proprio *quando* la console del
   clip logger è spenta. Spegnere la console non zittisce quell'ultimo: lo
   sposta.

   Chiudere entrambi i canali vuole entrambe le redirezioni, e la
   `redirect_stderr` va entrata **prima** che il clip logger si costruisca:
   `logging.StreamHandler()` cattura `sys.stderr` alla costruzione, non alla
   scrittura, quindi un handler già vivo continua a scrivere sullo stderr
   vero.

   ```python
   import contextlib, io

   fuori, errori = io.StringIO(), io.StringIO()
   with contextlib.redirect_stdout(fuori), contextlib.redirect_stderr(errori):
       result = api.render_file('scena.yml', 'out/scena.aif',
                                renderer='numpy', samples_dir='refs/')
   ```

5. Logging: i singleton restano; configurarli PRIMA di `load_generator`
   (altrimenti il primo Stream inizializza il clip logger coi default di
   modulo, file in `./logs` + la riga `📝 Clip log file: ...` su stdout):

   ```python
   from pge import configure_clip_logger, configure_engine_logger
   configure_clip_logger(enabled=False, console_enabled=False,
                         file_enabled=False)
   configure_engine_logger(yaml_name='mio_progetto', log_dir='out/logs')
   ```

6. Errori: catturare `pge.EngineError` (gerarchia con `user_message()`);
   argomenti API invalidi sollevano `ValueError` (es. `audio_format`
   stringa ignota). Il file YAML mancante è `ConfigFileNotFoundError`, quello
   malformato o non decodificabile `ConfigParseError`, e quello che il sistema
   operativo non apre — una directory al posto del file, permessi negati —
   `ConfigReadError` (#257): tutti e tre sono `EngineError`, quindi un
   solo `except` li copre insieme a tutto il resto, e tutti e tre ereditano
   anche il builtin che sostituiscono (`FileNotFoundError`, `yaml.YAMLError`,
   `OSError`) e, quando la causa ne ha uno, il suo tipo **concreto**
   (`IsADirectoryError`, `yaml.MarkedYAMLError`, `UnicodeDecodeError`) — chi
   li catturava per nome non deve cambiare niente. Sono anche picklabili, come
   i builtin che sostituiscono: attraversano un confine di processo.

7. Csound: `renderer='csound'` con knob raggruppati in
   `api.CsoundOptions(orc_path=..., ssdir=..., sco_dir=...)`;
   `ssdir=None` eredita `samples_dir`.

8. Quanti grani ha prodotto ogni stream: `result.grain_counts`, una voce per
   stream nell'ordine di `generator.streams`.

   ```python
   for stream_id, count in result.grain_counts.items():
       if count is None:
           ...            # stream saltato dalla cache: non e' "zero grani"
       else:
           print(stream_id, count.grains, count.voices)
   ```

   È una lettura fatta a render finito su chi era già materializzato, e va
   letta da lì: chiedere il conteggio a `stream.voices` prima del render
   innescherebbe la generazione lazy (#117), cioè genererebbe i grani che la
   cache stava per far risparmiare. Per lo stesso motivo `Stream.__repr__`
   dice `grains=lazy`.

## File toccati

Nessuno in PGE: si consuma `pge.api`. Nel progetto ospite: il proprio
codice di integrazione (es. `engine_bridge.py` in granulation-studies).

## Test da aggiornare

Nel progetto ospite: i test del proprio wrapper. In PGE l'API è coperta da
`tests/test_api.py` (superficie e kwargs, componenti mockati),
`tests/test_api_stdout.py` (cosa arriva davvero su stdout, componenti veri)
e il layout da `tests/test_package_layout.py`.

## Verifica

```bash
python -c "import pge, pge.api; print(pge.__version__)"
pge configs/PGE_test2.yml /tmp/out.aif --renderer numpy   # alias CLI
```
