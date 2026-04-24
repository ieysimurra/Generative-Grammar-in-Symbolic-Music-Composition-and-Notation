# Guia de Instalação

## Requisitos gerais

- Python **3.10 ou superior**
- pip (incluído com Python)
- LilyPond **2.24 ou superior** (para exportar PDF e PNG)
- MuseScore 3 ou 4 (opcional — para visualizar partituras)

---

## Windows

### 1. Python

Baixe o instalador em [python.org](https://www.python.org/downloads/).

> ⚠️ Durante a instalação, marque a opção **"Add Python to PATH"**.

Verifique:
```cmd
python --version
```

### 2. Dependências Python

```cmd
cd GrammarComposer
pip install -r requirements.txt
```

### 3. LilyPond

Baixe o instalador `.exe` em [lilypond.org/download](https://lilypond.org/download.html).

O GrammarComposer detecta automaticamente os caminhos de instalação padrão:
- `C:\Program Files (x86)\LilyPond\usr\bin\lilypond.exe`
- `C:\Program Files\LilyPond\usr\bin\lilypond.exe`

Se instalou em outro local, informe o caminho na GUI (campo **"Caminho LilyPond"** na aba de notação).

### 4. MuseScore (opcional)

Baixe em [musescore.org](https://musescore.org). O sistema detecta automaticamente:
- `C:\Program Files\MuseScore 4\bin\MuseScore4.exe`
- `C:\Program Files\MuseScore 3\bin\MuseScore3.exe`

### 5. Executar

```cmd
python composicao_algoritmica_atualizado.py
```

---

## macOS

### 1. Python

**Via Homebrew (recomendado):**
```bash
brew install python
```

**Ou via instalador** em [python.org](https://www.python.org/downloads/).

### 2. Dependências Python

```bash
cd GrammarComposer
pip3 install -r requirements.txt
```

> Se encontrar problemas com Tkinter no macOS: `brew install python-tk`

### 3. LilyPond

**Via Homebrew:**
```bash
brew install lilypond
```

**Via instalador `.dmg`:** baixe em [lilypond.org/download](https://lilypond.org/download.html).

O sistema detecta automaticamente:
- `/opt/homebrew/bin/lilypond` (Apple Silicon)
- `/usr/local/bin/lilypond` (Intel)
- `/Applications/LilyPond.app/Contents/Resources/bin/lilypond`

### 4. MuseScore (opcional)

```bash
brew install --cask musescore
```

Ou baixe o `.dmg` em [musescore.org](https://musescore.org).

### 5. Executar

```bash
python3 composicao_algoritmica_atualizado.py
```

---

## Linux (Ubuntu/Debian)

### 1. Python e Tkinter

```bash
sudo apt update
sudo apt install python3 python3-pip python3-tk
```

### 2. Dependências Python

```bash
cd GrammarComposer
pip3 install -r requirements.txt
```

### 3. LilyPond

```bash
sudo apt install lilypond
```

Ou via Snap (versão mais recente):
```bash
sudo snap install lilypond
```

### 4. MuseScore (opcional)

```bash
sudo apt install musescore3
# ou
flatpak install flathub org.musescore.MuseScore
```

### 5. Executar

```bash
python3 composicao_algoritmica_atualizado.py
```

---

## Verificação da instalação

Execute o script de teste:

```bash
python tests/test_core.py
```

Saída esperada:
```
[OK] NoteEvent creation
[OK] TupletGroup beat invariant
[OK] GrammarAbjadAdapter — 4 instruments
[OK] AbjadEngine — LilyPond string generation
[OK] System breaks inserted
All tests passed.
```

---

## Resolução de problemas

### `ModuleNotFoundError: No module named 'abjad'`
```bash
pip install abjad
```

### LilyPond não encontrado
Configure o caminho manualmente na GUI (aba **Motor LilyPond** → campo **Caminho LilyPond**), ou adicione ao PATH do sistema:

```bash
# Linux/macOS — adicione ao ~/.bashrc ou ~/.zshrc:
export PATH="/caminho/para/lilypond/bin:$PATH"
```

```cmd
# Windows — via Painel de Controle > Sistema > Variáveis de Ambiente
# Adicione o caminho bin do LilyPond à variável PATH
```

### Erro de Tkinter no macOS
```bash
brew install python-tk@3.11   # ajuste a versão conforme necessário
```
