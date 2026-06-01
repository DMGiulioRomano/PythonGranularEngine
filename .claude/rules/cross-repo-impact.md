# Impatto cross-repo su PGE-ls e PGE-ui

PGE non vive isolato. Due repo dipendono dalla sua superficie pubblica:

- `PGE-ls` (github.com/DMGiulioRomano/PGE-ls) — language server (pygls) che
  edita/valida lo YAML del granular engine.
- `PGE-ui` (github.com/DMGiulioRomano/PGE-ui) — interfaccia utente del granular
  engine.

## Quando applicare

Per OGNI feature, modifica o fix che tocca una superficie osservabile da quei
repo: sintassi/schema YAML, nuove chiavi o blocchi, bounds dei parametri, nomi
di strategy/window/renderer, gerarchia errori, formati di output, CLI/flag,
comportamento del rendering. Vale anche per refactoring che rinomina simboli
pubblici o cambia messaggi d'errore parsati a valle.

## Procedura

1. Identifica cosa cambia nella superficie pubblica (YAML, errori, CLI, formati).
2. Verifica se `PGE-ls` deve aggiornarsi (autocomplete, validazione, hover,
   diagnostica, snippet) e se `PGE-ui` deve aggiornarsi (controlli, form,
   visualizzazioni, default).
3. Se c'è impatto, apri una issue nel repo interessato — una per repo:
   ```bash
   gh issue create -R DMGiulioRomano/PGE-ls  --title ... --body ...
   gh issue create -R DMGiulioRomano/PGE-ui  --title ... --body ...
   ```
   La issue descrive la modifica PGE, il riferimento (issue/PR), e cosa va
   aggiornato.
4. Se non c'è impatto, dichiaralo esplicitamente nel riepilogo (niente issue).
