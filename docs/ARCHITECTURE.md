# Arquitetura do Sistema

## Visão geral

O GrammarComposer segue o padrão **Strategy** — o motor de composição (`CompositionEngine`) é independente do motor de notação (`AbjadEngine`). Um adaptador (`GrammarAbjadAdapter`) faz a ponte entre os dois mundos, permitindo que novos motores de notação sejam adicionados sem alterar a lógica de composição.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          GUI (Tkinter)                                  │
│   composicao_algoritmica_atualizado.py  +  gui_abjad_tab.py            │
└────────────────┬───────────────────────────────────┬────────────────────┘
                 │                                   │
    ┌────────────▼────────────┐         ┌────────────▼────────────┐
    │   CompositionEngine     │         │     GrammarAbjadAdapter  │
    │   (Markov chains)       │────────►│  grammar_abjad_adapter  │
    │                         │         └────────────┬────────────┘
    └─────────────────────────┘                      │
                                                     │ EventSequence[]
                                          ┌──────────▼──────────┐
                                          │    AbjadEngine       │
                                          │  abjad_engine.py     │
                                          └──────────┬──────────┘
                                                     │
                                          ┌──────────▼──────────┐
                                          │  LilyPond (externo) │
                                          └──────────┬──────────┘
                                                     │
                                          ┌──────────▼──────────┐
                                          │   PDF / PNG / .ly   │
                                          └─────────────────────┘
```

---

## Módulos

### `note_event.py` — Modelo de dados

Contém as estruturas de dados fundamentais. Não tem dependência de notação ou composição — é o "vocabulário" compartilhado entre todos os módulos.

```
NoteEvent
├── pitch_midi: int | None          MIDI 0-127, None = pausa
├── microtone_offset: float         0.0 = normal, ±0.5 = quarto de tom
├── duration_beats: float           em batidas (1.0 = semínima)
├── dynamic: str | None             "pp", "mf", "fff", etc.
├── hairpin: HairpinType            CRESCENDO, DECRESCENDO, NIENTE_IN/OUT
├── technique: ExtendedTechnique    SUL_PONT, COL_LEGNO, FLUTTER_TONGUE...
├── glissando: GlissandoType        NORMAL, WAVY, NONE
└── articulation: ArticulationType  STACCATO, ACCENT, TENUTO...

TupletGroup
├── ratio: str                      "3:2", "5:4", "7:4", "7:8", "11:8"
├── events: list[NoteEvent|TupletGroup]   suporta aninhamento
└── instrument_id: str

EventSequence
├── instrument_id: str
├── events: list[NoteEvent|TupletGroup]
├── time_sig_sequence: list[str]    ["4/4", "4/4", "3/4", ...]
└── use_proportional: bool          notação proporcional Feldman-style
```

**Invariante crítica dos TupletGroups:** para uma quiáltera `num:den` com `n_notes == num` notas, cada nota tem duração escrita `total_outer / den`. A duração soante real = `n_notes * inner_dur * den/num = total_outer`. Esta invariante é verificada automaticamente pelo adaptador.

---

### `grammar_abjad_adapter.py` — Adaptador

Traduz os parâmetros de alto nível do `CompositionEngine` (fórmulas de compasso, probabilidades, matrizes Markov) em `EventSequence` com `NoteEvent` e `TupletGroup`.

**Fluxo de geração (por instrumento, por compasso):**

```
ts_sequence[i]
      ↓
_beats_for_ts()           → Fraction de beats do compasso
      ↓
_fill_measure()           → lista de durações que somam exatamente os beats
      ↓
_generate_pitches()       → alturas MIDI via matriz Markov
      ↓
loop: técnica, microton, glissando, dinâmica, hairpin
      ↓
raw_notes[]               → lista de tuplas (pitch, dur, tech, ...)
      ↓
_group_into_tuplets()     → agrupa estocasticamente em TupletGroups
      ↓
EventSequence.append()
```

**Controle de budget no `_group_into_tuplets`:**
O agrupamento rastreia `consumed` beats e só forma uma quiáltera se `sum(group_durations) ≤ remaining_beats`. Quiálteras devem ter exatamente `num` notas (o numerador do ratio) para preservar a invariante de duração.

---

### `abjad_engine.py` — Motor de notação

Converte `EventSequence` em código LilyPond válido via biblioteca Abjad, com pós-processamento para:

1. **Microtones** — `\language "english"` + nomes `cqs`, `dqf`, `eqs`, etc.
2. **Técnicas estendidas** — `\markup { \italic "sul pont." }` por nota
3. **Glissandos** — `\override Glissando.style = #'zigzag` no `\layout`
4. **Notação proporcional** — remove barras, fórmulas de compasso e engravers de tempo
5. **Quebras de sistema automáticas** — `_insert_system_breaks()` pós-processa o LY

**Pipeline de exportação:**
```
build_score()  →  abjad.Score
      ↓
to_lilypond_string()
      ↓
_insert_system_breaks()     ← pós-processador: insere \break
      ↓
save_ly()  →  .ly
      ↓
_run_lilypond()             ← subprocess: lilypond -o base file.ly
      ↓
save_pdf() / save_png()  →  .pdf / .png
```

**Detecção cross-platform do LilyPond:**
```python
_find_lilypond_executable()
  1. shutil.which("lilypond")          # PATH do sistema
  2. caminhos típicos por SO           # Windows/macOS/Linux
  3. fallback: "lilypond"              # usuário configura via GUI
```

---

### `gui_abjad_tab.py` — Interface Abjad

Aba dedicada na GUI principal com:
- Seletor de instrumentos
- Sliders para probabilidades (quiálteras, técnicas, glissandos, microtons)
- Campo de caminho LilyPond com auto-detecção
- Preview PNG inline
- Botões de exportação (PDF, LY, MIDI)

---

## Decisões de projeto

### Por que Abjad e não music21 para notação?

| Aspecto | music21 | Abjad |
|---|---|---|
| Notação contemporânea | Limitada | Completa (LilyPond nativo) |
| Quiálteras aninhadas | Não suportado | Nativo |
| Microtonalismo | Parcial | Total (qualquer temperamento) |
| Deploy web | ✅ (sem LilyPond) | ❌ (requer LilyPond local) |
| Qualidade gráfica | Boa | Excelente (tipografia profissional) |

O projeto usa **ambos**: music21 para a lógica de composição e exportação MIDI/MusicXML; Abjad para a notação contemporânea de alta qualidade.

### Por que geração manual de LilyPond?

`music21.lily.translate` exige LilyPond instalado localmente e adiciona overhead de parsing. A geração manual via Abjad é **66× mais rápida**, mais confiável e permite controle total sobre a sintaxe.

### Por que `Fraction` e não `float` para durações?

Aritmética de ponto flutuante acumula erros ao somar durações de compassos. `Fraction(3,8) + Fraction(1,4)` dá `Fraction(5,8)` exato; `0.375 + 0.25` pode dar `0.6249999...`. Com dezenas de compassos, erros de float produzem compassos com beat count errado, quebrando o LilyPond.

---

## Adicionando um novo instrumento

Em `composicao_algoritmica_atualizado.py`, a lista de instrumentos é definida na função `get_instrument()` de `abjad_engine.py`. Para adicionar:

```python
InstrumentConfig(
    name="Oboé",
    short_name="Ob.",
    clef="treble",
    midi_range=(58, 91),    # Si3–Sol6
    is_transposing=False,
    techniques=[
        ExtendedTechnique.SUL_PONTICELLO,
        ExtendedTechnique.FLUTTER_TONGUE,
        ExtendedTechnique.MULTIPHONIC,
    ]
)
```

---

## Adicionando um novo motor de notação

O padrão Strategy permite adicionar engines alternativas sem tocar na lógica de composição:

```python
class MyEngine:
    def build_score(self, sequences: list): ...
    def to_string(self) -> str: ...
    def save(self, path: str): ...

# Registra como alternativa ao AbjadEngine
adapter.notation_engine = MyEngine()
```
