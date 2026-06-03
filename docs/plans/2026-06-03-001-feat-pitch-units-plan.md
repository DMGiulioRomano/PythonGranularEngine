# Piano 2026-06-03-001 — Sistema di unità di misura per il pitch (`PitchUnit`)

> Branch: `feat/pitch-units`

## Context

Oggi la conversione del pitch è frammentata e a due velocità:

- **Pitch base/per-grano** ([`PitchController`](../../src/controllers/pitch_controller.py)) ha già *due* unità — semitoni e ratio — implementate come Strategy separate ([`SemitonesStrategy`/`RatioStrategy`](../../src/strategies/strategie.py)) dietro il gruppo esclusivo `pitch_mode`.
- **Pitch delle voci** è invece **solo semitoni, hardcoded**: le strategy di distribuzione producono un numero "in semitoni" e l'unico punto di conversione è [`stream.py:446-449`](../../src/core/stream.py) con `2 ** (offset / 12.0)`.

Risultato: due implementazioni separate dello stesso concetto (`2^(n/12)` in almeno due punti) e nessun modo di esprimere cents, quarti/ottavi di tono, EDO arbitrari, o ratio sulle voci.

Questo piano introduce un'astrazione unica — `PitchUnit.to_ratio(value)` — riusata in **entrambi** i contesti, ed espone via YAML un set di unità: `semitones | cents | quarter_tone | eighth_tone | {edo: N} | ratio`.

## Decisioni concordate (locked)

| Decisione | Scelta |
|-----------|--------|
| Scope unità v1 | Famiglia esponenziale **+ ratio** |
| Unificazione | **Entrambi**: base/per-grano E voci condividono `PitchUnit` |
| Preset nominali | `semitones`, `cents`, `quarter_tone`, `eighth_tone` |
| Unità parametrica | `edo` (Equal Division of the Octave) |
| Forma YAML edo | **Forma A — dict/mapping**: `{edo: N}` |

## Modello matematico

Famiglia esponenziale = `2^(v/N)` con N = divisioni per ottava:

```
semitones    -> EdoUnit(12)     2^(v/12)
quarter_tone -> EdoUnit(24)     2^(v/24)
eighth_tone  -> EdoUnit(48)     2^(v/48)
cents        -> EdoUnit(1200)   2^(v/1200)
edo: N       -> EdoUnit(N)      2^(v/N)
ratio        -> RatioUnit       v            (moltiplicativo, non esponenziale)
```

`EdoUnit` generalizza i quattro preset: alias con N fisso.

### Gotcha voce-0 / ratio (gestito)

L'invariante voce-0 restituisce `offset = 0.0`. La giunzione voci è già guardata da `if voice_config.pitch_offset != 0.0:` → con offset 0 la moltiplicazione viene **saltata**, quindi voce-0 resta sul ratio base per *tutte* le unità, ratio inclusa. Nessun rischio `*0 = silenzio` per voce-0. Per voci ≠ 0 sotto `ratio` l'offset è usato come ratio diretto (`step: 1.5` → voci a ratio 1.5, 3.0, ...): comportamento definito, da documentare. **Non rimuovere la guardia `!= 0.0`.**

### Vincolo: distribuzioni semitoni-locked (v1)

- **Unit-agnostiche** — `step`, `range`, `stochastic`: numero puro, ogni unità valida.
- **Semitoni-locked** — `chord`, `spectral`: intervalli intrinsecamente in semitoni (interi da `CHORD_INTERVALS` / `12*log2`). Un `dom7` a `edo:24` non è più un dom7.

**v1:** `chord`/`spectral` accettano **solo** `semitones` (o `unit` assente); altra unità → errore esplicito. Espandibile in futuro, fuori scope ora. `SEMITONE_LOCKED = {'chord', 'spectral'}` come singola fonte di verità.

## Architettura

Nuovo modulo `src/parameters/pitch_unit.py`:

```python
class PitchUnit(ABC):
    symbol: str
    @abstractmethod
    def to_ratio(self, value: float) -> float: ...

class EdoUnit(PitchUnit):
    def __init__(self, divisions: int):  # > 0, validato
        ...
    def to_ratio(self, v): return 2 ** (v / self.divisions)

class RatioUnit(PitchUnit):
    def to_ratio(self, v): return v

def make_pitch_unit(spec) -> PitchUnit
    # spec: str preset | {'edo': N} -> EdoUnit(N) | None -> EdoUnit(12) (retrocompat)
    # errori dominio -> InvalidStrategyConfigError / InvalidFieldValueError
```

## Fasi (TDD: ogni fase rosso → verde prima della successiva)

### Fase 0 — setup
- `git checkout -b feat/pitch-units`; scrivere questo plan; commit.

### Fase 1 — `PitchUnit` isolato
- **Test** `tests/parameters/test_pitch_unit.py`: `to_ratio` per ogni preset (semitone 12→2.0; cents 1200→2.0; quarter 24; eighth 48), `EdoUnit(31)`, `RatioUnit` identità, `make_pitch_unit` da str / `{edo:N}` / default, errori (`edo:0`, `edo:-1`, preset sconosciuto).
- **Impl** `src/parameters/pitch_unit.py`. Nessun altro file toccato.

### Fase 2 — voci usano `PitchUnit`
- **Test** `tests/core/test_stream_voices_yaml.py` + `tests/strategies/test_voice_pitch_strategy.py`: `voices.pitch` con `unit: quarter_tone`, `{edo: 31}`, `ratio` su `step`/`range`/`stochastic`; default semitones invariato; voce-0 invariata per ratio; **`unit` ≠ semitones su `chord`/`spectral` → errore**.
- **Impl**:
  - Parsing voci [`stream.py`](../../src/core/stream.py) (~240-246): `pop('unit', None)` prima della factory; costruire `PitchUnit` con `make_pitch_unit`.
  - Validazione: `name in SEMITONE_LOCKED` e unit ≠ semitones → `InvalidStrategyConfigError` (campo `voices.pitch.unit`), con `stream_id` agganciato.
  - Unit su `VoiceManager` (nuovo attr `pitch_unit`, default `EdoUnit(12)`).
  - Giunzione [`stream.py`](../../src/core/stream.py) (~446-449): `2 ** (offset/12.0)` → `self._voice_manager.pitch_unit.to_ratio(offset)`. Mantenere guardia `!= 0.0`.

### Fase 3 — pitch base/per-grano unificato
- **Test** `tests/strategies/test_strategies.py` + test `PitchController`: `pitch: {cents: 50}`, `{quarter_tone: 3}`, `{eighth_tone: 6}`, `{edo: {divisions: 31, value: 4}}`, `ratio`/`semitones` invariati.
- **Impl**:
  - `UnitPitchStrategy(param, unit)` → `unit.to_ratio(param.get_value(t))`; rimpiazza `SemitonesStrategy`/`RatioStrategy` (alias back-compat dove i test li importano).
  - Estendere [`PITCH_PARAMETER_SCHEMA`](../../src/parameters/parameter_schema.py) gruppo `pitch_mode` con `pitch_cents`/`pitch_quarter_tone`/`pitch_eighth_tone` (scalari/envelope, come `pitch_semitones`).
  - `edo` al base = `{divisions, value}` annidato: special-case in [`PitchController.__init__`](../../src/controllers/pitch_controller.py) prima dell'orchestrator (`divisions`→unit, `value`→Parameter). Unico ramo non schema-driven.
  - Aggiornare [`PITCH_STRATEGIES`](../../src/strategies/strategy_registry.py) + `create_pitch_strategy` per mappare param_name → unit.

### Fase 4 — bounds, visualizer, docs, cross-repo
- **Bounds** [`parameter_definitions.py`](../../src/parameters/parameter_definitions.py): bound scalati ±3 ottave — `pitch_cents` [-3600,3600], `pitch_quarter_tone` [-72,72], `pitch_eighth_tone` [-144,144]. `edo` base: bound dinamico ±(3·divisions). Voci: nessun clamp → nessuna modifica bounds voci.
- **Visualizer** [`score_visualizer.py`](../../src/rendering/score_visualizer.py): label simbolo nuove unità (`c`, `¼t`, `⅛t`, `edoN`). Polish.
- **Docs** (workflow update-doc): estendere [`docs/reference/yaml.md`](../reference/yaml.md) blocchi Pitch e Voices; nota in [`docs/how-to/add-voice-strategy.md`](../how-to/add-voice-strategy.md). `make docs-index` + `make docs-lint`.
- **Cross-repo** (`.claude/rules/cross-repo-impact.md`): nuove chiavi YAML pubbliche (`voices.pitch.unit`, base `cents`/`quarter_tone`/`eighth_tone`/`edo`) → una issue per repo:
  - `gh issue create -R DMGiulioRomano/PGE-ls`
  - `gh issue create -R DMGiulioRomano/PGE-ui`

## File toccati

| Area | File | Tipo |
|------|------|------|
| Nuovo modulo | `src/parameters/pitch_unit.py` | nuovo |
| Voci | `src/core/stream.py`, `src/controllers/voice_manager.py` | modifica |
| Base pitch | `src/strategies/strategie.py`, `src/strategies/strategy_registry.py`, `src/controllers/pitch_controller.py`, `src/parameters/parameter_schema.py` | modifica |
| Bounds/visual | `src/parameters/parameter_definitions.py`, `src/rendering/score_visualizer.py` | modifica |
| Test | `tests/parameters/test_pitch_unit.py` (nuovo) + voice/pitch/stream esistenti | nuovo/modifica |
| Docs | `docs/reference/yaml.md` | modifica |

## Riuso (no reinvenzione)

- `make_pitch_unit` riusato in Fase 2 e Fase 3 — unica sorgente di verità per `2^(v/N)`.
- [`ExclusiveGroupSelector`](../../src/parameters/exclusive_selector.py) riusato per i nuovi preset base (solo nuovi `ParameterSpec`).
- `_parse_strategy_kwarg` / `resolve_param` invariati.
- Errori: `InvalidStrategyConfigError` / `InvalidFieldValueError` esistenti.

## Verifica end-to-end

1. `make tests` verde dopo ogni fase.
2. YAML multi-voce con `unit: {edo: 31}` + base `pitch: {cents: 50}` → render NumPy, ispezione partitura: `pitch_ratio` = `2^(offset/31)` (voci), `2^(50/1200)` (base).
3. Regressione: score solo-semitoni → output identico a prima.
4. `make docs-lint` verde; `INDEX.md` rigenerato.

## Chiusura

Repo senza CHANGELOG (non crearne). A fine lavoro: spostare plan in `docs/plans/done/`, poi chiedere merge locale vs PR.
