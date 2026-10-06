# Il corpo di una PR dichiara l'issue che chiude

Quando apri una pull request su questo repo, la **prima riga del corpo** e'
una dichiarazione in inglese dell'issue che la PR chiude:

```
Closes #219
```

Non e' una convenzione estetica: e' l'unica cosa che GitHub legge per chiudere
l'issue al merge su `main`. Il titolo no, un commento no, i messaggi di commit
della branch no.

## Le regole, tutte quante

- **Le parole chiave sono inglesi** e sono nove: `close`/`closes`/`closed`,
  `fix`/`fixes`/`fixed`, `resolve`/`resolves`/`resolved`. Il resto del corpo
  resta in italiano come sempre. **Un «Chiude #219» non chiude niente**, ed e'
  il caso vero da cui nasce questa regola: la PR #293 diceva «Chiude #219,
  entrambi i punti», e' stata merged, e la #219 e' rimasta aperta.
- **Una riga per ogni issue.** `Closes #123, #124` collega solo la prima:

  ```
  Closes #123
  Closes #124
  ```

- **Fra parola chiave e numero va uno spazio**, non i due punti: `Closes #12`,
  non `Closes: #12`.
- **Solo issue di questo repo.** `Closes DMGiulioRomano/PGE-ui#162` crea un
  rimando, non una chiusura: un'issue di PGE-ui la chiude una PR su PGE-ui.
  Qui si scrive senza parola chiave — `Refs DMGiulioRomano/PGE-ui#162` — e
  l'issue che l'analisi d'impatto apre a valle (vedi
  @.claude/rules/cross-repo-impact.md) resta citata, non chiusa.
- **Niente dentro un commento HTML o un blocco di codice.** Li' GitHub non la
  legge, e nemmeno il check.
- **Se la PR non chiude nessuna issue, dichiaralo** con una riga
  `No issue: <motivo>`. Il motivo e' il punto: senza, non si distingue una PR
  che non ha un'issue da una a cui la riga e' stata tolta.

## Chi lo verifica

Il check `closes-issue`
(`.github/workflows/pr-closes-issue.yml` → `.github/scripts/check_closing_keyword.py`)
gira a ogni apertura e a ogni modifica del corpo, e il ruleset di `main` lo
pretende verde (`.github/rulesets/README.md`). Il check e' **piu' stretto di
GitHub, mai piu' largo**: se passa, GitHub collega; se rifiuta una grafia che
GitHub avrebbe collegato, si riscrive la riga e si vede subito. Il verso
opposto — verde su una riga che GitHub non collega — e' il guasto che non si
vede, e il check esiste per non averlo.

Quando apri la PR, segui `.github/pull_request_template.md`: `Closes #N` in
cima, poi `Cosa cambia`, `Verifica`, `Impatto cross-repo`.
