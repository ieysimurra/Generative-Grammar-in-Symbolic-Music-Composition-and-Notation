# Guia de Uso

## Iniciando a aplicação

```bash
python composicao_algoritmica_atualizado.py   # Windows e Linux
python3 composicao_algoritmica_atualizado.py  # macOS
```

A interface principal abre com múltiplas abas.

---

## Interface principal

### Aba "Composição"

| Campo | Descrição |
|---|---|
| **Instrumentos** | Selecione 1–12 instrumentos. Múltiplas instâncias do mesmo instrumento são suportadas (ex: Violino 1, Violino 2). |
| **Tonalidade / Escala** | Define o pool de alturas para a cadeia de Markov. |
| **Compasso** | Fórmula padrão. Ative "Compassos variáveis" para variar ao longo da peça. |
| **Duração total** | Em compassos. |
| **Ordem Markov** | 1 = completamente estocástico; 3–5 = mais memória/repetição. |
| **Tempo (BPM)** | Afeta a duração real em segundos; não altera a notação. |

### Aba "Notação Contemporânea (Abjad)"

| Controle | Descrição |
|---|---|
| **Probabilidade de quiálteras** | 0.0–1.0. Chance de um grupo de notas se tornar uma quiáltera. |
| **Complexidade** | 1 = tercinas (3:2); 2 = quintinas (5:4); 3 = sétimas (7:4); 4–5 = Ferneyhough. |
| **Quiálteras aninhadas** | Probabilidade de criar quiálteras dentro de quiálteras. |
| **Técnicas estendidas** | Probabilidade de aplicar sul ponticello, col legno, flutter-tongue, etc. |
| **Glissandos** | Probabilidade de adicionar glissandos entre notas. |
| **Microtonalismo** | Probabilidade de deflexões de 1/4 de tom. |
| **Notação proporcional** | Ativa o modo Feldman/Cardew: sem barras, sem fórmulas de compasso. |
| **Caminho LilyPond** | Deixe em branco para auto-detecção, ou informe o caminho completo. |

### Aba "Motor LilyPond"

Permite testar a detecção do LilyPond e visualizar o preview PNG diretamente na interface.

---

## Gerando uma composição

1. Configure os instrumentos na aba **Composição**
2. Ajuste os parâmetros de notação na aba **Notação Contemporânea**
3. Clique em **"Gerar Composição"**
4. Aguarde a compilação (pode levar 5–30 segundos dependendo da complexidade)
5. O PDF abre automaticamente; o arquivo `.ly` fica na pasta `output/`

---

## Exportação

### Formatos disponíveis

| Formato | Como exportar | Uso |
|---|---|---|
| **PDF** | Botão "Exportar PDF" | Impressão, visualização |
| **LilyPond (.ly)** | Botão "Salvar .ly" | Edição manual na notação |
| **MIDI** | Botão "Exportar MIDI" | Playback, DAW |
| **MusicXML** | Botão "Exportar MusicXML" | Troca com Sibelius, Finale, MuseScore |
| **PNG** | Botão "Preview PNG" | Visualização rápida |

### Pasta de saída padrão

```
# Windows
C:\Users\<usuario>\musica_gerada\

# macOS / Linux
~/musica_gerada/
```

---

## Usando via API (sem GUI)

Para scripts e integração em outros projetos:

```python
from note_event import NoteEvent, TupletGroup, EventSequence
from note_event import ExtendedTechnique, GlissandoType, HairpinType
from grammar_abjad_adapter import GrammarAbjadAdapter
from abjad_engine import AbjadEngine

# ── Crie sequências manualmente ──────────────────────────────────────────────
seq = EventSequence('flauta', time_signature=(4, 4), tempo_bpm=72)

seq.append(NoteEvent.note(72, 1.0, dynamic='mp'))
seq.append(TupletGroup.triplet([
    NoteEvent.note(71, 0.5, technique=ExtendedTechnique.SUL_PONTICELLO),
    NoteEvent.note(69, 0.5),
    NoteEvent.note(67, 0.5, hairpin_end=True),
]))
seq.append(NoteEvent.note(65, 2.0, dynamic='pp',
                           hairpin=HairpinType.NIENTE_OUT))

# ── Renderiza ────────────────────────────────────────────────────────────────
engine = AbjadEngine(title='Miniatura', composer_name='Ivan Simurra')
engine.build_score([seq])
engine.save_pdf('miniatura.pdf')
engine.save_ly('miniatura.ly')
```

---

## Parâmetros do GrammarAbjadAdapter

```python
adapter = GrammarAbjadAdapter(composer_instance)

# Quiálteras
adapter.tuplet_probability   = 0.30    # [0.0 – 1.0]
adapter.tuplet_complexity    = 3       # [1–5]: tercinas→Ferneyhough
adapter.tuplet_nesting_prob  = 0.20    # [0.0 – 1.0]

# Notação estendida
adapter.technique_probability = 0.25  # [0.0 – 1.0]
adapter.glissando_probability = 0.10  # [0.0 – 1.0]
adapter.microtone_probability = 0.08  # [0.0 – 1.0]

# Geração
sequences = adapter.build_sequences_from_composer(
    instrument_ids=['flauta', 'viola', 'violoncelo'],
    style='balanced'    # 'balanced' | 'sparse' | 'dense'
)
```

---

## Dicas de composição

### Para notação Feldman-style
- Ative **Notação proporcional** na GUI
- Use probabilidade de quiálteras baixa (0.10–0.20)
- Dinâmicas suaves: `min_dynamic='ppp'`, `max_dynamic='mp'`
- Muitos silêncios: aumente a probabilidade de pausas

### Para complexidade Ferneyhough
- `tuplet_complexity = 5` (onzenas: 11:8)
- `tuplet_nesting_prob = 0.40`
- `tuplet_probability = 0.50`
- Use time signatures complexas: 5/8, 7/8, 11/16

### Para fluidez microton-glissando
- `microtone_probability = 0.20`
- `glissando_probability = 0.25`
- `technique_probability = 0.15`
- Time signatures simples: 4/4, 3/4

---

## Editando o arquivo .ly gerado

O arquivo `.ly` pode ser editado manualmente em qualquer editor de texto ou no [Frescobaldi](https://frescobaldi.org/) (IDE dedicado ao LilyPond).

Para recompilar após editar:
```bash
lilypond -o output/minha_peca output/minha_peca.ly
```
