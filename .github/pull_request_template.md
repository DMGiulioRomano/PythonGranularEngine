Closes #

<!--
  LA RIGA QUI SOPRA E' OBBLIGATORIA, e va completata col numero dell'issue.
  E' l'unica cosa che GitHub legge per chiudere l'issue quando questa PR
  entra in main: non il titolo, non un commento, non i messaggi di commit.

  Le parole chiave sono INGLESI e sono nove: close/closes/closed,
  fix/fixes/fixed, resolve/resolves/resolved. Un "Chiude #219" scritto in
  italiano non chiude niente -- e' il motivo per cui la #219 e' stata chiusa
  a mano dopo il merge della PR #293, che pure diceva «Chiude #219».

  Una riga per ogni issue: "Closes #123, #124" collega solo la prima.

      Closes #123
      Closes #124

  Solo issue DI QUESTO repo. "Closes DMGiulioRomano/PGE-ui#162" crea un
  rimando, non una chiusura: quell'issue la chiude una PR su PGE-ui. Qui
  scrivila senza parola chiave -- "Refs DMGiulioRomano/PGE-ui#162".

  Se questa PR non chiude nessuna issue, togli la riga e dichiaralo:

      No issue: refuso nel README

  Il check `closes-issue` verifica questa riga su ogni apertura e ogni
  modifica del corpo.
-->

## Cosa cambia

<!-- Il fatto misurato, non l'intenzione: cosa faceva prima, cosa fa adesso. -->

## Verifica

<!-- `make tests` (conteggio ed exit code) e `make docs-lint` se i doc cambiano. -->

## Impatto cross-repo

<!--
  Obbligatorio e repo per repo, come chiede .claude/rules/cross-repo-impact.md:
  PGE-ls, PGE-ui, gl-ls. "Nessun impatto" va dichiarato, non sottinteso, e la
  copertura di uno non implica quella degli altri. Submodule CIM 2026: bump o no.
-->
