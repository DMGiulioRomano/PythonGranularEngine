# Impatto cross-repo su PGE-ls, PGE-ui e gl-ls

PGE non vive isolato. Tre repo dipendono dalla sua superficie pubblica:

- `PGE-ls` (github.com/DMGiulioRomano/PGE-ls) — language server (pygls) che
  edita/valida lo YAML del granular engine.
- `PGE-ui` (github.com/DMGiulioRomano/PGE-ui) — interfaccia utente del granular
  engine.
- `gl-ls` (github.com/DMGiulioRomano/gl-ls) — language server degli `study.yml`
  di `granulation-studies`, che **incapsulano** la superficie YAML di PGE: il
  blocco `base:` di uno studio e' un blocco stream engine. Ne tiene percio' un
  mirror proprio — registry di chiavi per contesto (`schema.py`, dove
  `grain`/`pointer`/`pitch`/`voices` hanno vocabolario **chiuso**: una chiave
  che il registry non conosce diventa `unknown-key` con quick fix di rename),
  bounds dei parametri e delle bande (`engine_info.py`), e la riscrittura delle
  unita' che l'engine fa al parse (`diagnostics._UNIT_SCALED`, mirror di
  `Stream._pre_normalize_grain_params`).

Le tre superfici non coincidono, e la copertura di una non implica quella delle
altre: una chiave nuova dentro un blocco engine resta muta in PGE-ui finche'
l'editor non la espone, ma in gl-ls e' **subito un falso rosso** su YAML
valido, perche' li' il vocabolario e' chiuso per costruzione.

## Quando applicare

Per OGNI feature, modifica o fix che tocca una superficie osservabile da quei
repo: sintassi/schema YAML, nuove chiavi o blocchi, bounds dei parametri e
delle bande, nomi di strategy/window/renderer, gerarchia errori, formati di
output, CLI/flag, comportamento del rendering. Vale anche per refactoring che
rinomina simboli pubblici o cambia messaggi d'errore parsati a valle.

Per `gl-ls` valgono in piu' due domande, perche' mirrora codice PGE invece di
leggerlo dal vivo:

- la chiave nuova va aggiunta al registry del suo contesto? (altrimenti
  `unknown-key` piu' un rename che riscrive YAML corretto);
- la modifica cambia **se** o **come** l'engine riscala/valida un valore al
  parse? (allora il mirror in `diagnostics.py` divergerebbe in silenzio).

## Procedura

1. Identifica cosa cambia nella superficie pubblica (YAML, errori, CLI, formati).
2. Verifica se `PGE-ls` deve aggiornarsi (autocomplete, validazione, hover,
   diagnostica, snippet), se `PGE-ui` deve aggiornarsi (controlli, form,
   visualizzazioni, default) e se `gl-ls` deve aggiornarsi (registry di chiavi,
   bounds, mirror delle conversioni, hover).
3. Se c'è impatto, apri una issue nel repo interessato — una per repo:
   ```bash
   gh issue create -R DMGiulioRomano/PGE-ls  --title ... --body ...
   gh issue create -R DMGiulioRomano/PGE-ui  --title ... --body ...
   gh issue create -R DMGiulioRomano/gl-ls   --title ... --body ...
   ```
   La issue descrive la modifica PGE, il riferimento (issue/PR), e cosa va
   aggiornato.
4. Se non c'è impatto, dichiaralo esplicitamente nel riepilogo (niente issue) —
   repo per repo, non in blocco.
