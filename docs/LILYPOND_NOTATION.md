# Referência de Notação LilyPond

Documentação das decisões de notação e da sintaxe LilyPond gerada pelo GrammarComposer.

---

## Microtonalismo

O sistema usa `\language "english"` que ativa sufixos de quarto de tom:

| Sufixo | Significado | Exemplo |
|---|---|---|
| `qs`  | quarto de tom acima | `cqs` = Dó + ¼ tom |
| `qf`  | quarto de tom abaixo | `dqf` = Ré − ¼ tom |
| `eqs` | oitavo de tom acima (3/4 tom) | `eqs` |
| `eqf` | oitavo de tom abaixo | `eqf` |

O código usa `microtone_offset = ±0.5` no `NoteEvent` para indicar ±¼ tom.

---

## Quiálteras

### Sintaxe LilyPond

```lilypond
% Tercina: 3 notas no espaço de 2 colcheias (= 1 semínima)
\tuplet 3/2 { c'8 d'8 e'8 }

% Quintina: 5 notas no espaço de 4 semicolcheias (= 1 semínima)
\tuplet 5/4 { c'16 d'16 e'16 f'16 g'16 }

% Sétima: 7 notas no espaço de 4 semicolcheias (= 1 semínima)
\tuplet 7/4 { c'16 d'16 e'16 f'16 g'16 a'16 b'16 }
```

### Quiálteras aninhadas (Ferneyhough)

```lilypond
\tuplet 5/4 {
    c'4
    d'4
    \tuplet 7/4 {
        e'8. f'8. g'8. a'8. b'8. c''8. d''8.
    }
}
```

### Fórmula de duração interna

Para uma quiáltera `num:den` cobrindo `T` beats:
```
duração_escrita_interna = T / den
```

Verificação: `num × (T/den) × (den/num) = T` ✓

| Ratio | T (beats) | Duração interna |
|---|---|---|
| 3:2 | 1.0 | 0.5 (colcheia) |
| 5:4 | 1.0 | 0.25 (semicolcheia) |
| 7:4 | 1.0 | 0.25 (semicolcheia) |
| 7:8 | 1.0 | 0.125 (fusa) |
| 11:8 | 1.0 | 0.125 (fusa) |

---

## Técnicas estendidas

Implementadas como `\markup` anexado a cada nota:

```lilypond
c'4 _ \markup { \italic "sul pont." }
d'4 _ \markup { \italic "col legno" }
e'4 _ \markup { \italic "flutter-tongue" }
f'4 _ \markup { \circle \finger "M" }   % multifônico
g'4 \flageolet                           % harmônico natural
a'4 \snappizzicato                       % snap pizzicato
```

### Tabela de técnicas

| `ExtendedTechnique` | LilyPond gerado | Significado |
|---|---|---|
| `SUL_PONTICELLO` | `\markup { \italic "sul pont." }` | Arco sobre o cavalete |
| `SUL_TASTO` | `\markup { \italic "sul tasto" }` | Arco sobre o espelho |
| `COL_LEGNO` | `\markup { \italic "col legno" }` | Com o talão do arco |
| `FLUTTER_TONGUE` | `\markup { \italic "flutter-tongue" }` | Frulato |
| `MULTIPHONIC` | `\markup { \circle \finger "M" }` | Multifônico |
| `ORDINARIO` | `\markup { \italic "ord." }` | Retorno ao ordinário |
| `FLAGEOLET` | `\flageolet` | Harmônico |
| `SNAP_PIZZICATO` | `\snappizzicato` | Bartók pizzicato |

---

## Glissandos

```lilypond
% Glissando linear
c'4 \glissando d'4

% Glissando em zigue-zague (definido UMA VEZ no \layout)
\layout {
  \context { \Voice
    \override Glissando.style = #'zigzag
  }
}
c'4 \glissando d'4   % renderiza em zigue-zague automaticamente
```

> **Regra:** `\override Glissando.style` é definido **uma vez** no bloco `\layout \context \Voice`, nunca por nota. Repetição por nota causa duplicação de engravers.

---

## Dinâmicas

```lilypond
c'4 \ppp   d'4 \pp   e'4 \p   f'4 \mp
g'4 \mf    a'4 \f    b'4 \ff  c''4 \fff

% Hairpins
c'4 \< d'4 e'4 f'4 \!     % crescendo e fechamento
c'4 \> d'4 e'4 f'4 \!     % decrescendo

% Niente (hairpin com cabeça de zero — LilyPond 2.24+)
c'4 \< \! d'2 \p           % niente crescendo
c'4 \> d'2 \! \ppp          % niente decrescendo
```

---

## Notação proporcional

Para o modo Feldman/Cardew (sem barras de compasso, sem fórmulas):

```lilypond
\layout {
  \context { \Score
    \remove "Timing_translator"
    \remove "Default_bar_line_engraver"
  }
  \context { \Staff
    \remove "Time_signature_engraver"
    \omit Staff.BarLine
    \omit Staff.TimeSignature
    \omit Staff.BarNumber
    \override SpacingSpanner.uniform-stretching = ##t
    proportionalNotationDuration = #(ly:make-moment 1/16)
  }
}
```

---

## Configurações globais de layout

### Estrutura obrigatória

```lilypond
% 1. set-global-staff-size DEVE estar ANTES de \paper (nível top-level)
#(set-global-staff-size 11)

\paper {
  #(set-paper-size "a4" (quote portrait))
  paper-width = 210\mm
  paper-height = 297\mm
  ragged-right = ##f     % força preenchimento da largura
  ragged-last = ##t      % último sistema não estica
  page-breaking = #ly:optimal-breaking
}

\layout {
  \context { \Score
    \override SpacingSpanner.base-shortest-duration = #(ly:make-moment 1/16)
    \override Glissando.style = #'zigzag   % NUNCA por nota, sempre aqui
  }
}
```

### Tamanho do staff adaptativo

| Instrumentos | staff-size |
|---|---|
| 1 | 16pt |
| 2 | 14pt |
| 3 | 12pt |
| 4–5 | 11pt |
| 6–8 | 10pt |
| 9+ | 9pt |

### Por que `base-shortest-duration = 1/16`?

Com `1/64`, notas colapsam a <1mm horizontal e tudo cabe em uma linha só (não há quebras de sistema). Com `1/16`, cada nota ocupa ao menos ~3 staff-spaces, forçando o LilyPond a distribuir corretamente em múltiplas linhas.

---

## Quebras de sistema automáticas

O pós-processador `_insert_system_breaks()` insere `\break` automaticamente no `.ly`:

1. Agrupa compassos em **seções** (runs do mesmo time signature)
2. Estima a largura de cada seção em mm: `beats × 7 staff-spaces × ss_mm + overhead`
3. Insere `\break` antes de `\time X/Y` quando a seção causaria overflow
4. Para seções longas (muitos compassos da mesma fórmula), distribui quebras internamente

`\break` é inserido apenas na **primeira pauta** — o LilyPond propaga automaticamente para todas as pautas num contexto `Score`.
