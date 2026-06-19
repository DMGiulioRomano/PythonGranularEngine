# Sync del submodule PGE nel paper CIM 2026

PGE è incluso come **git submodule** nel repo del paper accademico:

- `cim2026-granular-engine-paper`
  (github.com/DMGiulioRomano/cim2026-granular-engine-paper) — sorgente LaTeX
  della comunicazione CIM 2026. Pinna PGE come submodule in
  `raw/PythonGranularEngine` (commit fisso) e ne usa il codice per rigenerare
  gli esempi del paper (audio + partiture) via `paper/examples/render_example.py`.

Quando PGE avanza, il commit pinnato nel paper resta indietro: gli esempi
continuano a girare sul vecchio codice finché qualcuno non bumpa il submodule
a mano e fa push. Questa regola automatizza la **proposta** di quel bump.

## Quando applicare

Ogni volta che si lavora a una **PR su PGE** (apertura o dopo il merge) che
tocca qualcosa da cui dipendono gli esempi del paper:

- comportamento del rendering (renderer NumPy/Csound, finestre, envelope);
- lo **score visualizer** (`src/rendering/score_visualizer.py`) — partitura,
  legenda, opzioni di config come `font_scale`;
- superficie pubblica usata da `render_example.py` / `plot.py` (firma di
  `ScoreVisualizer`, `Generator`, `RenderingEngine`, chiavi di config);
- sintassi YAML o semantica dei parametri visibili negli esempi `exN.yml`.

Non applicare per modifiche che il paper non esercita (es. solo test interni,
tooling di sviluppo, doc che gli esempi non importano).

## Procedura

1. Identifica se la modifica PGE è osservabile dagli esempi del paper (lista
   sopra). Se non lo è, dichiaralo nel riepilogo e fermati (niente bump).
2. Se lo è, **chiedi all'utente con `AskUserQuestion`** se vuole:
   - bumpare il submodule `raw/PythonGranularEngine` nel repo
     `cim2026-granular-engine-paper` al nuovo commit PGE, e
   - aprire lì una PR con il bump (sul branch di sviluppo concordato),
   includendo nella domanda il commit/PR PGE di riferimento e una riga su cosa
   cambia per gli esempi, così la decisione è presa senza ricostruire il contesto.
3. Se l'utente conferma, nel repo del paper:
   - aggiorna il puntatore del submodule al commit PGE desiderato
     (`git -C raw/PythonGranularEngine fetch && checkout <sha>`, poi
     `git add raw/PythonGranularEngine`);
   - committa il bump con messaggio che cita il commit/PR PGE;
   - apri la PR sul branch di sviluppo del paper.
   Ricorda che dopo il bump del submodule vanno rifatti i symlink delle refs
   audio (`make link-refs`) e che gli esempi sono rigenerabili con `make examples`.
4. Se l'utente rifiuta, non fare nulla sul repo del paper.

Nota operativa: questa regola scatta quando Claude è attivo in una sessione su
PGE e nota una PR rilevante. Non è un automatismo lato server: per un trigger
"a ogni PR" indipendente dalla sessione servirebbe una GitHub Action nel repo
PGE o una sottoscrizione agli eventi PR.
