# GrammarComposer

> Sistema de composição algorítmica em Python para geração de partituras contemporâneas baseado em Gramática Generativa, quiálteras complexas, técnicas estendidas e notação proporcional.

**Desenvolvido por Prof. Ivan Eiji Simurra — NICS/UNICAMP**

---

## Visão geral

O GrammarComposer é uma ferramenta de pesquisa e composição que combina algoritmos estocásticos com notação musical contemporânea. O sistema gera partituras em formato LilyPond/PDF a partir de parâmetros musicais configuráveis, integrando referências estéticas de Feldman, Ferneyhough, Ligeti, Lachenmann e Sciarrino.

```
CompositionEngine (Markov)
        ↓
  GrammarAbjadAdapter
        ↓
   AbjadEngine  →  LilyPond  →  PDF / PNG
        ↑
   NoteEvent / TupletGroup / EventSequence
```

---

## Funcionalidades

### Composição algorítmica
- **Cadeias de Markov independentes** para altura, duração e dinâmica
- **Fórmulas de compasso variáveis** com sincronização entre instrumentos
- **Quiálteras estocásticas** com nível de complexidade configurável (1–5)
- **Quiálteras aninhadas** estilo Ferneyhough (tercinas dentro de sétimas, etc.)
- **Microtonalismo**: quartos de tom via nomenclatura LilyPond (`cqs`, `dqf`, etc.)

### Notação contemporânea
- **Técnicas estendidas**: sul ponticello, sul tasto, col legno, flutter-tongue, multifônicos
- **Notação proporcional** (estilo Feldman/Cardew): sem barras, sem fórmulas de compasso
- **Glissandos**: lineares e em zigue-zague
- **Dinâmicas complexas** incluindo *niente* (hairpins com cabeça de zero)
- **Snap pizzicato** e flageolets

### Infraestrutura
- Interface desktop com **Tkinter** (multiplataforma)
- Exportação para **LilyPond, MIDI, MusicXML, PDF**
- Integração com **MuseScore** para visualização
- Compatível com **Windows, macOS e Linux** (mesmo código-fonte)
- Quebras de sistema automáticas dentro das margens de página A4

---

## Estrutura do projeto

```
GrammarComposer/
├── composicao_algoritmica_atualizado.py   # Ponto de entrada + GUI principal
├── note_event.py                          # Modelo de dados musical
├── abjad_engine.py                        # Motor de notação (Abjad/LilyPond)
├── grammar_abjad_adapter.py               # Adaptador Markov → Abjad
├── gui_abjad_tab.py                       # Aba GUI de notação contemporânea
├── requirements.txt                       # Dependências Python
├── docs/
│   ├── ARCHITECTURE.md                    # Documentação da arquitetura
│   ├── INSTALLATION.md                    # Guia de instalação por SO
│   ├── USAGE.md                           # Guia de uso da interface
│   └── LILYPOND_NOTATION.md              # Referência de notação LilyPond
├── examples/
│   ├── example_minimal.py                 # Score mínimo (3 linhas)
│   ├── example_quartet.py                 # Quarteto com todas as features
│   └── example_proportional.py           # Notação proporcional Feldman-style
├── tests/
│   └── test_core.py                       # Testes unitários
└── assets/
    └── screenshot.png                     # Screenshot da interface
```

---

## Instalação rápida

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/GrammarComposer.git
cd GrammarComposer

# 2. Instale as dependências Python
pip install -r requirements.txt

# 3. Instale o LilyPond (necessário para gerar PDF/PNG)
#    → https://lilypond.org/download.html

# 4. Execute
python composicao_algoritmica_atualizado.py
```

Consulte [`docs/INSTALLATION.md`](docs/INSTALLATION.md) para instruções detalhadas por sistema operacional.

---

## Uso rápido (API)

```python
from note_event import NoteEvent, TupletGroup, EventSequence, ExtendedTechnique
from grammar_abjad_adapter import GrammarAbjadAdapter
from abjad_engine import AbjadEngine

# Configura o adaptador
adapter = GrammarAbjadAdapter(composer)
adapter.tuplet_probability    = 0.30   # 30% de chance de quiáltera por grupo
adapter.tuplet_complexity     = 3      # até sétimas (7:4)
adapter.tuplet_nesting_prob   = 0.20   # quiálteras aninhadas (Ferneyhough)
adapter.technique_probability = 0.25   # técnicas estendidas
adapter.microtone_probability = 0.10   # microtonalismo

# Gera sequências para quarteto de cordas
sequences = adapter.build_sequences_from_composer(
    ['violino', 'viola', 'violoncelo', 'contrabaixo'],
    style='balanced'
)

# Renderiza e exporta
engine = AbjadEngine(title='Estudo I', composer_name='Ivan Simurra')
engine.build_score(sequences)
engine.save_pdf('output/estudo_I.pdf')
```

Veja mais exemplos em [`examples/`](examples/).

---

## Compatibilidade

| Sistema | Python | Tkinter | LilyPond | MuseScore |
|---------|--------|---------|----------|-----------|
| Windows 10/11 | ✅ 3.10+ | ✅ nativo | ✅ `.exe` | ✅ `.exe` |
| macOS 12+ | ✅ 3.10+ | ✅ nativo | ✅ `.dmg` / Homebrew | ✅ `.dmg` |
| Ubuntu 20.04+ | ✅ 3.10+ | ✅ nativo | ✅ apt / snap | ✅ apt / Flatpak |

---

## Referências estéticas e algorítmicas

**Compositores:** Morton Feldman, Brian Ferneyhough, György Ligeti, Helmut Lachenmann, Salvatore Sciarrino, Luigi Nono, Iannis Xenakis

**Algoritmos:** Cadeias de Markov, N-gramas, SIATEC (análise MIDI), Autômatos Celulares (Wolfram)

**Notação:** Abjad, LilyPond 2.24+

---

## Licença

MIT License — veja [`LICENSE`](LICENSE) para detalhes.

---

## Citação

```bibtex
@software{simurra2025grammarcomposer,
  author  = {Simurra, Ivan Eiji},
  title   = {GrammarComposer: Algorithmic Composition with Markov Chains and Contemporary Notation},
  year    = {2025},
  url     = {https://github.com/seu-usuario/GrammarComposer},
  institution = {NICS/UNICAMP}
}
```
