"""
CsoundEmitter - l'unico posto del motore che scrive sintassi Csound.

Prima della issue #203 le tre forme di statement del `.sco` stavano in tre
moduli diversi, due dei quali sotto il livello che deve restare indipendente
dal target:

    i-statement del grano      Grain.to_score_line              core/
    f-statement del sample     FtableManager.write_to_file      allocatore
    f-statement della finestra WindowRegistry.generate_ftable_statement
                                                                catalogo

Il criterio e' che il livello che rappresenta *cosa* si deve suonare non
conosca *come* un target lo scrive: e' cio' che rende additivo aggiungere un
back-end, come `AudioRenderer`/`RenderMode` dichiarano di voler essere. Sotto
quell'astrazione la codegen era rientrata nel core, e la prova e' che una
decisione di formato -- gli otto decimali di p2/p3, necessari perche' a 96 kHz
un grano puo' durare un campione -- viveva in `core/grain.py`.

Cosa resta a chi ha ceduto il metodo:

- `Grain` e' il dato, e basta;
- `FtableManager` e' l'allocatore di numeri di tabella e la symbol table
  condivisa fra i back-end (il renderer NumPy riceve la stessa `table_map`,
  e lo score SuperCollider ne fa numeri di buffer): alloca, non scrive;
- `WindowRegistry` e' il catalogo -- decide quali nomi lo YAML puo' scrivere
  e qual e' il canonico di ciascuno. Chi materializza e' un adapter: questo
  modulo per Csound, `NumpyWindowRegistry` per l'array.

**Contratto di formattazione: ogni builder restituisce una riga di score
completa, newline inclusa.** Chi scrive il file concatena senza doversi
chiedere se lo statement finisce, e il caso caldo -- un i-statement per grano,
per milioni di grani -- non paga una concatenazione in piu' per riga.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from pge.controllers.window_registry import WindowRegistry
from pge.shared.exceptions import FtableError, InvalidWindowError

# Nome dello strumento definito in `csound/main.orc`. Lo score lo cita per
# nome in ogni i-statement: se cambia li', cambia qui.
INSTRUMENT_NAME = 'Grain'

# Dimensione di default delle tabelle di finestra, in punti.
DEFAULT_WINDOW_TABLE_SIZE = 1024

# Larghezza dei separatori di sezione, in caratteri.
_RULE_WIDTH = 77

# GEN16 e la posizione, nei suoi p-field, della durata del segmento.
_GEN16 = 16
_GEN16_DUR_INDEX = 1


class CsoundEmitter:
    """Traduce grani e symbol table in statement di score Csound."""

    instrument_name = INSTRUMENT_NAME
    default_window_table_size = DEFAULT_WINDOW_TABLE_SIZE

    # =========================================================================
    # STATEMENT
    # =========================================================================

    def grain_statement(self, grain, onset_offset: float = 0.0) -> str:
        """i-statement di un grano.

        Args:
            grain: il `Grain` da serializzare.
            onset_offset: sottratto dall'onset (onset relativi in STEMS mode).
        """
        # p2/p3 a 8 decimali: con grain.duration_unit samples un grano puo'
        # durare 1 campione (~2e-5 s); 6 decimali introducevano fino al 4%
        # di errore di quantizzazione a 96 kHz.
        return (f'i "{self.instrument_name}" '
                f'{grain.onset - onset_offset:.8f} {grain.duration:.8f} '
                f'{grain.pointer_pos:.6f} {grain.pitch_ratio:.6f} '
                f'{grain.volume:.2f} {grain.pan:.3f} '
                f'{grain.sample_table} {grain.envelope_table}\n')

    def sample_ftable(self, table_num: int, sample_path: str) -> str:
        """f-statement GEN01 di un sample.

        `f NUM TIME SIZE GEN "filename" SKIPTIME FORMAT CHANNEL`, con SIZE=0
        perche' la dimensione la deduce Csound dal file.
        """
        return f'f {table_num} 0 0 1 "{sample_path}" 0 0 1\n'

    def window_ftable(
        self,
        table_num: int,
        name: str,
        size: Optional[int] = None,
    ) -> str:
        """f-statement di una finestra del catalogo (GEN09/GEN16/GEN20).

        Args:
            table_num: numero di tabella Csound.
            name: nome della finestra, alias inclusi.
            size: dimensione della tabella in punti. `None` = il default
                dell'emitter, cosi' che una sottoclasse possa spostarlo
                dichiarando `default_window_table_size`, come fa per
                `instrument_name`.

        Raises:
            InvalidWindowError: il catalogo non conosce `name`.
        """
        spec = WindowRegistry.get(name)
        if spec is None:
            raise InvalidWindowError(
                name=name,
                available=WindowRegistry.all_names(),
            )

        return self._ftable_from_spec(table_num, spec, size)

    def _ftable_from_spec(self, table_num: int, spec, size: Optional[int]) -> str:
        """f-statement di una `WindowSpec` gia' risolta.

        Esiste perche' `write_ftables` la spec ce l'ha gia' in mano -- le
        serve `spec.description` per il commento -- e ricercarla una seconda
        volta significherebbe anche due `if spec is None` scritti separati,
        liberi di divergere.
        """
        if size is None:
            size = self.default_window_table_size

        params = list(spec.gen_params)

        # GEN16 descrive un segmento alla volta -- `val1 dur1 type1 val2`,
        # con dur1 in *punti* -- e le finestre asimmetriche del catalogo ne
        # hanno uno solo: la sua lunghezza e' la tabella intera. Il catalogo
        # dichiara la forma della curva, la dimensione la decide chi
        # materializza, altrimenti una `size` diversa dal default emette una
        # tabella da N punti con dentro un segmento da 1024.
        if spec.gen_routine == _GEN16 and len(params) > _GEN16_DUR_INDEX:
            params[_GEN16_DUR_INDEX] = size

        rendered = ' '.join(str(p) for p in params)
        return f'f {table_num} 0 {size} {spec.gen_routine} {rendered}\n'

    def end_statement(self) -> str:
        """Statement di fine score.

        E' uno statement come gli altri, e stava fuori: finche' `ScoreWriter`
        scriveva la `e` da se', l'affermazione della #203 -- la sintassi del
        target sta in un posto solo -- era falsa di una riga.
        """
        return 'e\n'

    # =========================================================================
    # COMMENTI E STRUTTURA
    # =========================================================================

    def comment(self, text: str) -> str:
        """Riga di commento.

        Il `;` e' sintassi Csound quanto un f-statement: chi dispone le
        sezioni sceglie *cosa* dire, non come si apre un commento.
        """
        return f'; {text}\n'

    def rule(self) -> str:
        """Separatore di sezione: un commento di soli `=`."""
        return self.comment('=' * _RULE_WIDTH)

    # =========================================================================
    # SEZIONE FUNCTION TABLES
    # =========================================================================

    def write_ftables(self, f, tables: Dict[int, Tuple[str, str]]) -> None:
        """Scrive la sezione FUNCTION TABLES.

        Args:
            f: file object aperto in scrittura.
            tables: la symbol table `{numero: (tipo, chiave)}`, cosi' come la
                espone `FtableManager.get_all_tables()`. E' un dict semplice
                e non il manager di proposito: l'emitter materializza dei
                simboli, non sa chi li abbia numerati.

        Raises:
            FtableError: `tables` cita una finestra che il catalogo non
                conosce -- stato incoerente, non un nome sbagliato in YAML.
        """
        f.write(self.rule())
        f.write(self.comment("FUNCTION TABLES"))
        f.write(self.rule() + "\n")

        for num, (ftype, key) in sorted(tables.items()):
            if ftype == 'sample':
                f.write(self.comment(f'Sample: {key}'))
                f.write(self.sample_ftable(num, key))
                f.write('\n')

            elif ftype == 'window':
                spec = WindowRegistry.get(key)
                if spec is None:
                    raise FtableError(
                        key=key,
                        reason=(
                            f"Window '{key}' non trovata nel WindowRegistry. "
                            f"Stato incoerente: register_window() avrebbe dovuto "
                            f"validarla."
                        ),
                    )

                f.write(self.comment(f'Window: {key} - {spec.description}'))
                f.write(self._ftable_from_spec(num, spec, None))
                f.write('\n')
