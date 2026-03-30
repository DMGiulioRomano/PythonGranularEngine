# New Feature

Avvia il workflow completo per una nuova funzionalita o refactoring.

## Procedura obbligatoria

1. **Branch**: crea un feature branch con nome `feature/$ARGUMENTS`
   ```bash
   git checkout -b feature/$ARGUMENTS
   ```

2. **Impact analysis**: leggi i moduli coinvolti e identifica dipendenze

3. **Design**: proponi il design della soluzione in italiano.
   Attendi approvazione esplicita prima di procedere.

4. **Test suite**: elenca le suite di test da scrivere (red phase).
   Attendi conferma prima di scrivere i test.

5. **Red phase**: scrivi i test failing. Verifica che falliscano con
   `make tests` o pytest sul file specifico.

6. **Green phase**: implementa il codice di produzione minimo per far
   passare i test.

7. **Refactor**: migliora il codice mantenendo i test verdi.

**Non saltare nessun passaggio. Non generare codice di produzione prima
del passaggio 4.**
Lingua: italiano.
