"""
gui_abjad_tab.py  v2
====================
Aba de Notação Contemporânea para o ComposerGUI existente.

v2 acrescenta:
  • Etapa 6 — Controles de tuplas: probabilidade, nível de complexidade
    (1=tercinas … 5=Ferneyhough), probabilidade de aninhamento
  • Etapa 7 — Controles de grand staff: split point e histerese
  • Etapa 8 — Preview PNG inline: imagem da partitura dentro da aba,
    sem abrir PDF

Como acoplar ao ComposerGUI existente
--------------------------------------
No final de ComposerGUI._create_ui():

    from gui_abjad_tab import AbjadTab
    self.abjad_tab = AbjadTab(self)

Autor: Ivan Simurra / NICS-UNICAMP
"""

from __future__ import annotations

import os
import platform
import subprocess
try:
    from musicxml_export import save_musicxml, open_in_musescore as _ms_open
    _MUSICXML_EXPORT_AVAILABLE = True
except ImportError:
    _MUSICXML_EXPORT_AVAILABLE = False
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from typing import Optional

try:
    from note_event import (
        NoteEvent, EventSequence, TupletGroup,
        ExtendedTechnique, HairpinType, GlissandoType,
        get_instrument, INSTRUMENT_CATALOG,
    )
    from abjad_engine import AbjadEngine
    from grammar_abjad_adapter import GrammarAbjadAdapter
    ABJAD_AVAILABLE = True
except ImportError as _e:
    ABJAD_AVAILABLE = False
    _IMPORT_ERROR = str(_e)


# ---------------------------------------------------------------------------
# AbjadTab v2
# ---------------------------------------------------------------------------

class AbjadTab:
    """Aba de Notação Contemporânea acoplada ao ComposerGUI."""

    def __init__(self, gui):
        self.gui = gui
        self.notebook = gui.notebook
        self._last_ly_path:  Optional[str] = None
        self._last_pdf_path: Optional[str] = None
        self._last_png_path: Optional[str] = None
        self._generation_thread: Optional[threading.Thread] = None

        self.frame = ttk.Frame(self.notebook)
        self.notebook.add(self.frame, text="✦ Notação Abjad")

        if not ABJAD_AVAILABLE:
            self._build_unavailable_ui()
        else:
            self._build_ui()

    # ------------------------------------------------------------------
    # UI: módulos indisponíveis
    # ------------------------------------------------------------------

    def _build_unavailable_ui(self):
        ttk.Label(
            self.frame,
            text=f"Motor Abjad não disponível.\nErro: {_IMPORT_ERROR}\n\n"
                 "Verifique note_event.py, abjad_engine.py, grammar_abjad_adapter.py\n"
                 "e execute:  pip install abjad",
            justify=tk.LEFT, foreground="red"
        ).pack(padx=20, pady=20, anchor=tk.W)

    # ------------------------------------------------------------------
    # UI principal
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Layout: coluna esquerda (controles) | coluna direita (preview PNG)
        paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Painel esquerdo: controles com scroll
        left_outer = ttk.Frame(paned)
        paned.add(left_outer, weight=1)

        canvas = tk.Canvas(left_outer, borderwidth=0, width=480)
        vsb = ttk.Scrollbar(left_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _resize(e): canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _resize)

        def _fit(e): canvas.itemconfig(win_id, width=e.width)
        canvas.bind("<Configure>", _fit)

        # Mouse wheel scroll
        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Painel direito: preview PNG
        right_outer = ttk.Frame(paned)
        paned.add(right_outer, weight=1)
        self._build_preview_panel(right_outer)

        # ---- Seções de controle no painel esquerdo ----
        self._build_engine_section(inner)
        self._build_proportional_section(inner)
        self._build_contemporary_section(inner)
        self._build_tuplet_section(inner)      # Etapa 6
        self._build_rest_section(inner)        # Etapa 6b — Pausas
        self._build_grand_staff_section(inner) # Etapa 7
        self._build_instruments_section(inner)
        self._build_actions_section(inner)
        self._build_log_section(inner)

    # ------------------------------------------------------------------
    # Seção Motor
    # ------------------------------------------------------------------

    def _build_engine_section(self, parent):
        frm = ttk.LabelFrame(parent, text="Motor LilyPond")
        frm.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frm, text="Caminho LilyPond:").grid(row=0,column=0,padx=5,pady=3,sticky=tk.W)
        self._var_ly_path = tk.StringVar(value="lilypond")
        ttk.Entry(frm, textvariable=self._var_ly_path, width=34).grid(row=0,column=1,padx=5,pady=3)
        ttk.Button(frm, text="…", width=3, command=self._browse_lilypond).grid(row=0,column=2,padx=3)

        ttk.Label(frm, text="Pasta de saída:").grid(row=1,column=0,padx=5,pady=3,sticky=tk.W)
        default_out = os.path.join(os.path.expanduser("~"),"Documents","GrammarComposer_Abjad")
        self._var_out_dir = tk.StringVar(value=default_out)
        ttk.Entry(frm, textvariable=self._var_out_dir, width=34).grid(row=1,column=1,padx=5,pady=3)
        ttk.Button(frm, text="…", width=3, command=self._browse_output_dir).grid(row=1,column=2,padx=3)

        ttk.Label(frm, text="Papel:").grid(row=2,column=0,padx=5,pady=3,sticky=tk.W)
        self._var_paper = tk.StringVar(value="a4")
        ttk.Combobox(frm, textvariable=self._var_paper,
                     values=["a4","letter","a3","a5"], width=8,
                     state="readonly").grid(row=2,column=1,padx=5,pady=3,sticky=tk.W)

    # ------------------------------------------------------------------
    # Seção Notação Proporcional
    # ------------------------------------------------------------------

    def _build_proportional_section(self, parent):
        frm = ttk.LabelFrame(parent, text="Notação Proporcional")
        frm.pack(fill=tk.X, padx=10, pady=5)

        self._var_prop = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm,
            text="Ativar (remove barras, compassos e numeração)",
            variable=self._var_prop).grid(row=0,column=0,columnspan=3,padx=5,pady=3,sticky=tk.W)

        ttk.Label(frm, text="Momento:").grid(row=1,column=0,padx=5,pady=3,sticky=tk.W)
        self._var_prop_moment = tk.StringVar(value="1/16")
        ttk.Combobox(frm, textvariable=self._var_prop_moment,
                     values=["1/8","1/12","1/16","1/24","1/32"],
                     width=7, state="readonly").grid(row=1,column=1,padx=5,pady=3,sticky=tk.W)
        ttk.Label(frm,text="(menor = mais comprimido)",foreground="gray").grid(
            row=1,column=2,padx=5,pady=3,sticky=tk.W)

    # ------------------------------------------------------------------
    # Seção Notação Contemporânea (microtonalismo, técnicas, glissando)
    # ------------------------------------------------------------------

    def _build_contemporary_section(self, parent):
        frm = ttk.LabelFrame(parent, text="Parâmetros Contemporâneos")
        frm.pack(fill=tk.X, padx=10, pady=5)

        self._sliders = {}
        defs = [
            ("Microtonalismo:", "_microtone", 0.0),
            ("Técnicas estendidas:", "_technique", 0.0),
            ("Glissando:", "_glissando", 0.0),
        ]
        for row, (label, key, default) in enumerate(defs):
            ttk.Label(frm, text=label).grid(row=row,column=0,padx=5,pady=3,sticky=tk.W)
            scl = ttk.Scale(frm, from_=0.0, to=1.0, value=default,
                            length=180, orient=tk.HORIZONTAL)
            scl.grid(row=row,column=1,padx=5,pady=3)
            lbl = ttk.Label(frm, text=f"{default:.2f}", width=4)
            lbl.grid(row=row,column=2,padx=3,pady=3)
            _l = lbl
            scl.configure(command=lambda v, l=_l: l.configure(text=f"{float(v):.2f}"))
            self._sliders[key] = scl

    # ------------------------------------------------------------------
    # Etapa 6 — Seção Tuplas
    # ------------------------------------------------------------------

    def _build_tuplet_section(self, parent):
        frm = ttk.LabelFrame(parent, text="Tuplas (Etapa 6 — Ritmos Complexos)")
        frm.pack(fill=tk.X, padx=10, pady=5)

        # Probabilidade de tupla
        ttk.Label(frm, text="Probabilidade de tupla:").grid(row=0,column=0,padx=5,pady=3,sticky=tk.W)
        self._scl_tuplet = ttk.Scale(frm, from_=0.0, to=1.0, value=0.0,
                                      length=180, orient=tk.HORIZONTAL)
        self._scl_tuplet.grid(row=0,column=1,padx=5,pady=3)
        self._lbl_tuplet = ttk.Label(frm, text="0.00", width=4)
        self._lbl_tuplet.grid(row=0,column=2,padx=3)
        self._scl_tuplet.configure(
            command=lambda v: self._lbl_tuplet.configure(text=f"{float(v):.2f}"))

        # Complexidade (nível 1–5)
        ttk.Label(frm, text="Complexidade (1–5):").grid(row=1,column=0,padx=5,pady=3,sticky=tk.W)
        self._var_tuplet_complexity = tk.IntVar(value=1)
        frm_levels = ttk.Frame(frm)
        frm_levels.grid(row=1,column=1,columnspan=2,padx=5,pady=3,sticky=tk.W)
        level_descs = [
            "1 – Tercinas  (3:2)",
            "2 – Quintinas  (3:2, 5:4)",
            "3 – Sétimas  (3:2, 4:3, 5:4, 6:4, 7:4)",
            "4 – Irregular  (+ 5:3, 7:6, 9:8)",
            "5 – Ferneyhough  (+ 8:6, 11:4, 11:8, 13:8)",
        ]
        for i, desc in enumerate(level_descs):
            ttk.Radiobutton(frm_levels, text=desc,
                            variable=self._var_tuplet_complexity,
                            value=i+1).pack(anchor=tk.W)

        # Probabilidade de aninhamento
        ttk.Label(frm, text="Aninhamento:").grid(row=7,column=0,padx=5,pady=3,sticky=tk.W)
        self._scl_nesting = ttk.Scale(frm, from_=0.0, to=1.0, value=0.0,
                                       length=180, orient=tk.HORIZONTAL)
        self._scl_nesting.grid(row=7,column=1,padx=5,pady=3)
        self._lbl_nesting = ttk.Label(frm, text="0.00", width=4)
        self._lbl_nesting.grid(row=7,column=2,padx=3)
        self._scl_nesting.configure(
            command=lambda v: self._lbl_nesting.configure(text=f"{float(v):.2f}"))

        # ── Pool de quiálteras ──────────────────────────────────────────
        ttk.Separator(frm, orient=tk.HORIZONTAL).grid(
            row=8, column=0, columnspan=3, sticky=tk.EW, padx=5, pady=6)

        ttk.Label(frm, text="Pool de ratios:",
                  font=("", 9, "bold")).grid(row=9, column=0, padx=5, pady=2, sticky=tk.W)
        ttk.Label(frm, text="(deixe vazio para usar o nível acima)",
                  foreground="gray").grid(row=9, column=1, columnspan=2, padx=5, sticky=tk.W)

        # Checkbuttons para cada ratio disponível
        self._pool_vars = {}
        ALL_RATIOS = [
            (3,2,"3:2  tercina"),
            (4,3,"4:3  quartina"),
            (5,3,"5:3  quintina/colch."),
            (5,4,"5:4  quintina"),
            (5,6,"5:6  quint. expandida"),
            (6,4,"6:4  sêxtupla"),
            (7,4,"7:4  sétima"),
            (7,6,"7:6  sétima/colch."),
            (7,8,"7:8  sétima expand."),
            (8,6,"8:6  óctupla"),
            (9,4,"9:4  nônupla"),
            (9,8,"9:8  nônupla/colch."),
            (10,8,"10:8 décupla"),
            (11,4,"11:4 onzena"),
            (11,8,"11:8 onzena/colch."),
            (12,8,"12:8 duodécupla"),
            (13,8,"13:8 terzadécima"),
        ]
        frm_pool = ttk.Frame(frm)
        frm_pool.grid(row=10, column=0, columnspan=3, padx=5, pady=2, sticky=tk.W)
        for col_idx, (num, den, label) in enumerate(ALL_RATIOS):
            var = tk.BooleanVar(value=False)
            self._pool_vars[(num, den)] = var
            row_i  = col_idx // 3
            col_i  = col_idx % 3
            ttk.Checkbutton(frm_pool, text=label, variable=var).grid(
                row=row_i, column=col_i, padx=8, pady=1, sticky=tk.W)

        # Pesos relativos
        ttk.Label(frm, text="Pesos (opcional):").grid(
            row=11, column=0, padx=5, pady=3, sticky=tk.W)
        self._ent_weights = ttk.Entry(frm, width=45)
        self._ent_weights.grid(row=11, column=1, columnspan=2, padx=5, pady=3, sticky=tk.W)
        self._ent_weights.insert(0, "ex: 3:2=5, 5:4=3, 7:4=2, 13:8=1")
        self._ent_weights.bind("<FocusIn>", self._on_weights_focus)

        # Pool do aninhamento
        ttk.Label(frm, text="Pool interno:").grid(
            row=12, column=0, padx=5, pady=3, sticky=tk.W)
        self._ent_nest_pool = ttk.Entry(frm, width=45)
        self._ent_nest_pool.grid(row=12, column=1, columnspan=2, padx=5, pady=3, sticky=tk.W)
        self._ent_nest_pool.insert(0, "ex: 3:2, 4:3, 5:4  (vazio = automático)")
        self._ent_nest_pool.bind("<FocusIn>", self._on_nest_pool_focus)

    # ------------------------------------------------------------------
    # Etapa 6b — Seção de Pausas
    # ------------------------------------------------------------------

    def _build_rest_section(self, parent):
        frm = ttk.LabelFrame(parent, text="Pausas")
        frm.pack(fill=tk.X, padx=10, pady=5)

        # Probabilidade de pausa
        ttk.Label(frm, text="Probabilidade:").grid(row=0, column=0, padx=5, pady=3, sticky=tk.W)
        self._scl_rest = ttk.Scale(frm, from_=0.0, to=1.0, value=0.0,
                                    length=180, orient=tk.HORIZONTAL)
        self._scl_rest.grid(row=0, column=1, padx=5, pady=3)
        self._lbl_rest = ttk.Label(frm, text="0.00", width=4)
        self._lbl_rest.grid(row=0, column=2, padx=3)
        self._scl_rest.configure(
            command=lambda v: self._lbl_rest.configure(text=f"{float(v):.2f}"))

        # Modo de distribuição
        ttk.Label(frm, text="Modo:").grid(row=1, column=0, padx=5, pady=3, sticky=tk.W)
        self._var_rest_mode = tk.StringVar(value="uniform")
        frm_modes = ttk.Frame(frm)
        frm_modes.grid(row=1, column=1, columnspan=2, padx=5, pady=2, sticky=tk.W)
        modes = [
            ("uniform", "Uniforme — pausas distribuídas aleatoriamente"),
            ("phrase",  "Frase — pausas ao fim de frases"),
            ("breath",  "Respiração — pausas após notas longas"),
            ("sparse",  "Esparso — pausas longas e raras (Feldman)"),
        ]
        for val, label in modes:
            ttk.Radiobutton(frm_modes, text=label,
                            variable=self._var_rest_mode,
                            value=val).pack(anchor=tk.W)

        # Duração máxima (modo sparse)
        ttk.Label(frm, text="Dur. máx. (beats):").grid(row=6, column=0, padx=5, pady=3, sticky=tk.W)
        self._spin_rest_max = ttk.Spinbox(frm, from_=0.0, to=8.0,
                                           increment=0.5, width=6)
        self._spin_rest_max.set("1.5")
        self._spin_rest_max.grid(row=6, column=1, padx=5, pady=3, sticky=tk.W)
        ttk.Label(frm, text="(0 = livre; só modo Esparso)").grid(
            row=6, column=2, padx=3, sticky=tk.W)

        # Comprimento de frase (modo phrase)
        ttk.Label(frm, text="Compr. de frase:").grid(row=7, column=0, padx=5, pady=3, sticky=tk.W)
        self._spin_rest_phrase = ttk.Spinbox(frm, from_=2, to=32,
                                              increment=1, width=6)
        self._spin_rest_phrase.set("6")
        self._spin_rest_phrase.grid(row=7, column=1, padx=5, pady=3, sticky=tk.W)
        ttk.Label(frm, text="notas  (só modo Frase)").grid(
            row=7, column=2, padx=3, sticky=tk.W)

    # ------------------------------------------------------------------
    # Etapa 7 — Seção Grand Staff
    # ------------------------------------------------------------------

    def _build_grand_staff_section(self, parent):
        frm = ttk.LabelFrame(parent, text="Grand Staff — Piano/Cravo (Etapa 7)")
        frm.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frm, text="Split point (MIDI):").grid(row=0,column=0,padx=5,pady=3,sticky=tk.W)
        self._spin_split = ttk.Spinbox(frm, from_=36, to=84, increment=1, width=5)
        self._spin_split.delete(0, tk.END)
        self._spin_split.insert(0, "60")
        self._spin_split.grid(row=0,column=1,padx=5,pady=3,sticky=tk.W)
        ttk.Label(frm, text="(60 = Dó central)", foreground="gray").grid(
            row=0,column=2,padx=5,pady=3,sticky=tk.W)

        ttk.Label(frm, text="Histerese (semitons):").grid(row=1,column=0,padx=5,pady=3,sticky=tk.W)
        self._spin_hys = ttk.Spinbox(frm, from_=0, to=12, increment=1, width=5)
        self._spin_hys.delete(0, tk.END)
        self._spin_hys.insert(0, "4")
        self._spin_hys.grid(row=1,column=1,padx=5,pady=3,sticky=tk.W)
        ttk.Label(frm,
            text="(zona neutra — evita troca de mão a cada nota)",
            foreground="gray").grid(row=1,column=2,padx=5,pady=3,sticky=tk.W)

    # ------------------------------------------------------------------
    # Seção Instrumentos
    # ------------------------------------------------------------------

    def _build_instruments_section(self, parent):
        frm = ttk.LabelFrame(parent, text="Instrumentos")
        frm.pack(fill=tk.X, padx=10, pady=5)

        self._var_use_active = tk.BooleanVar(value=True)
        ttk.Radiobutton(frm, text="Usar instrumentos ativos da composição atual",
                        variable=self._var_use_active, value=True).pack(
            anchor=tk.W, padx=5, pady=2)
        ttk.Radiobutton(frm, text="Selecionar manualmente:",
                        variable=self._var_use_active, value=False).pack(
            anchor=tk.W, padx=5, pady=2)

        frm2 = ttk.Frame(frm)
        frm2.pack(fill=tk.X, padx=20, pady=3)
        self._listbox_instr = tk.Listbox(frm2, selectmode=tk.MULTIPLE,
                                          height=5, exportselection=False)
        for iid in sorted(INSTRUMENT_CATALOG.keys()):
            cfg = INSTRUMENT_CATALOG[iid]
            self._listbox_instr.insert(tk.END, f"{iid}  —  {cfg.name_full}")
        self._listbox_instr.pack(side=tk.LEFT, fill=tk.X, expand=True)
        sb = ttk.Scrollbar(frm2, orient=tk.VERTICAL,
                           command=self._listbox_instr.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox_instr.configure(yscrollcommand=sb.set)

    # ------------------------------------------------------------------
    # Seção Ações
    # ------------------------------------------------------------------

    def _build_actions_section(self, parent):
        frm = ttk.LabelFrame(parent, text="Gerar Partitura Abjad")
        frm.pack(fill=tk.X, padx=10, pady=5)

        # Checkboxes de saída
        out_row = ttk.Frame(frm)
        out_row.pack(fill=tk.X, padx=5, pady=3)
        self._var_export_ly  = tk.BooleanVar(value=True)
        self._var_export_pdf = tk.BooleanVar(value=True)
        self._var_export_png = tk.BooleanVar(value=True)  # Etapa 8
        ttk.Checkbutton(out_row, text="Salvar .ly",  variable=self._var_export_ly ).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(out_row, text="Gerar PDF",   variable=self._var_export_pdf).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(out_row, text="Preview PNG", variable=self._var_export_png).pack(side=tk.LEFT, padx=5)

        ttk.Label(out_row, text="DPI:").pack(side=tk.LEFT, padx=(15,2))
        self._spin_dpi = ttk.Spinbox(out_row, from_=72, to=300, increment=25, width=5)
        self._spin_dpi.delete(0, tk.END)
        self._spin_dpi.insert(0, "150")
        self._spin_dpi.pack(side=tk.LEFT)

        # Botões
        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X, padx=5, pady=5)
        self._btn_generate = ttk.Button(btn_row, text="⚙  Gerar",
                                         command=self._on_generate)
        self._btn_generate.pack(side=tk.LEFT, padx=4)

        self._btn_open_ly = ttk.Button(btn_row, text="Abrir .ly",
                                        state=tk.DISABLED, command=self._open_ly)
        self._btn_open_ly.pack(side=tk.LEFT, padx=4)

        self._btn_open_pdf = ttk.Button(btn_row, text="Abrir PDF",
                                         state=tk.DISABLED, command=self._open_pdf)
        self._btn_open_pdf.pack(side=tk.LEFT, padx=4)
        self._btn_open_ms = ttk.Button(btn_row, text="🎼 MuseScore",
                                        state=tk.DISABLED, command=self._open_musescore)
        self._btn_open_ms.pack(side=tk.LEFT, padx=4)

        self._btn_open_folder = ttk.Button(btn_row, text="📁 Pasta",
                                            state=tk.DISABLED, command=self._open_folder)
        self._btn_open_folder.pack(side=tk.LEFT, padx=4)

        self._progress = ttk.Progressbar(frm, mode="indeterminate", length=360)
        self._progress.pack(padx=5, pady=(0,5))

    # ------------------------------------------------------------------
    # Seção Log
    # ------------------------------------------------------------------

    def _build_log_section(self, parent):
        frm = ttk.LabelFrame(parent, text="Log")
        frm.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self._log = ScrolledText(frm, height=8, wrap=tk.WORD,
                                  state=tk.DISABLED, font=("Courier", 9))
        self._log.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        ttk.Button(frm, text="Limpar",
                   command=self._clear_log).pack(anchor=tk.E, padx=4, pady=2)

    # ------------------------------------------------------------------
    # Etapa 8 — Painel de preview PNG
    # ------------------------------------------------------------------

    def _build_preview_panel(self, parent):
        frm = ttk.LabelFrame(parent, text="Preview da Partitura (PNG)")
        frm.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._preview_label = ttk.Label(
            frm,
            text="O preview aparecerá aqui após a geração.\n"
                 "(Requer LilyPond instalado e 'Preview PNG' marcado)",
            anchor=tk.CENTER, justify=tk.CENTER, foreground="gray"
        )
        self._preview_label.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X, padx=5, pady=3)
        self._btn_refresh_png = ttk.Button(btn_row, text="↺ Atualizar preview",
                                            state=tk.DISABLED,
                                            command=self._refresh_preview)
        self._btn_refresh_png.pack(side=tk.LEFT, padx=4)
        self._btn_save_png = ttk.Button(btn_row, text="💾 Salvar PNG",
                                         state=tk.DISABLED,
                                         command=self._save_png_copy)
        self._btn_save_png.pack(side=tk.LEFT, padx=4)

        self._png_photo: Optional[object] = None   # mantém referência Tk
        self._preview_canvas = tk.Canvas(frm, bg="#f0f0f0")
        self._preview_canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _refresh_preview(self):
        """Carrega o PNG mais recente no canvas."""
        if not self._last_png_path or not os.path.exists(self._last_png_path):
            return
        try:
            from PIL import Image, ImageTk
            img = Image.open(self._last_png_path)
            # Escala para caber no canvas
            cw = self._preview_canvas.winfo_width()  or 400
            ch = self._preview_canvas.winfo_height() or 500
            img.thumbnail((cw, ch), Image.LANCZOS)
            self._png_photo = ImageTk.PhotoImage(img)
            self._preview_canvas.delete("all")
            self._preview_canvas.create_image(
                cw // 2, ch // 2, image=self._png_photo
            )
        except ImportError:
            # Pillow não disponível: mostra caminho
            self._preview_canvas.delete("all")
            self._preview_canvas.create_text(
                10, 10, anchor=tk.NW,
                text=f"Instale Pillow para preview inline:\n  pip install Pillow\n\nPNG: {self._last_png_path}",
                font=("Courier", 10), fill="#444"
            )
        except Exception as e:
            self._log_write(f"Erro ao carregar PNG: {e}\n")

    def _save_png_copy(self):
        if not self._last_png_path or not os.path.exists(self._last_png_path):
            messagebox.showwarning("PNG", "Nenhum PNG disponível.")
            return
        dest = filedialog.asksaveasfilename(
            title="Salvar PNG",
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            initialfile=os.path.basename(self._last_png_path),
        )
        if dest:
            import shutil
            shutil.copy2(self._last_png_path, dest)
            self._log_write(f"PNG copiado para: {dest}\n")

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------

    def _browse_lilypond(self):
        p = filedialog.askopenfilename(title="Localizar LilyPond",
                                       filetypes=[("Executável","*")])
        if p: self._var_ly_path.set(p)

    def _browse_output_dir(self):
        p = filedialog.askdirectory(title="Pasta de saída Abjad")
        if p: self._var_out_dir.set(p)

    # ------------------------------------------------------------------
    # Helpers — Pool de quiálteras e pausas
    # ------------------------------------------------------------------

    def _on_weights_focus(self, event):
        """Limpa placeholder na primeira edição."""
        if self._ent_weights.get().startswith("ex:"):
            self._ent_weights.delete(0, tk.END)

    def _on_nest_pool_focus(self, event):
        txt = self._ent_nest_pool.get()
        if txt.startswith("ex:") or "vazio" in txt:
            self._ent_nest_pool.delete(0, tk.END)

    def _parse_tuplet_pool(self):
        """Retorna lista de (num,den) marcados, ou None (usa preset)."""
        pool = [(num, den) for (num, den), var in self._pool_vars.items()
                if var.get()]
        return pool if pool else None

    def _parse_tuplet_weights(self):
        """
        Analisa '3:2=5, 5:4=3, 7:4=2'.
        Retorna dict {(num,den): float} ou None.
        """
        import re
        raw = self._ent_weights.get().strip()
        if not raw or raw.startswith("ex:"):
            return None
        weights = {}
        for m in re.finditer(r"(\d+):(\d+)\s*=\s*([\d.]+)", raw):
            weights[(int(m.group(1)), int(m.group(2)))] = float(m.group(3))
        return weights if weights else None

    def _parse_nest_pool(self):
        """
        Analisa '3:2, 4:3, 5:4'.
        Retorna lista de (num,den) ou None.
        """
        import re
        raw = self._ent_nest_pool.get().strip()
        if not raw or raw.startswith("ex:") or "vazio" in raw:
            return None
        pool = []
        for m in re.finditer(r"(\d+):(\d+)", raw):
            pool.append((int(m.group(1)), int(m.group(2))))
        return pool if pool else None

    # ------------------------------------------------------------------
    # Geração
    # ------------------------------------------------------------------

    def _on_generate(self):
        if not ABJAD_AVAILABLE:
            messagebox.showerror("Erro", "Motor Abjad não disponível.")
            return
        composer = self.gui.composer
        if not (getattr(composer,"rhythm_patterns",None) and
                getattr(composer,"pitch_patterns",None)):
            messagebox.showwarning("Dados não carregados",
                "Carregue os dados de análise na aba Gerador.")
            return

        self._btn_generate.configure(state=tk.DISABLED)
        self._progress.start(10)
        self._log_write("Iniciando geração Abjad v2…\n")
        self._generation_thread = threading.Thread(
            target=self._generate_worker, daemon=True
        )
        self._generation_thread.start()

    def _generate_worker(self):
        try:
            ly_path  = self._var_ly_path.get().strip() or None
            out_dir  = self._var_out_dir.get().strip() or "output_abjad"
            paper    = self._var_paper.get()
            prop     = self._var_prop.get()
            moment   = self._var_prop_moment.get()

            microtone_prob = float(self._sliders["_microtone"].get())
            technique_prob = float(self._sliders["_technique"].get())
            glissando_prob = float(self._sliders["_glissando"].get())

            tuplet_prob    = float(self._scl_tuplet.get())
            tuplet_level   = int(self._var_tuplet_complexity.get())
            nesting_prob   = float(self._scl_nesting.get())

            try:
                split_midi = int(self._spin_split.get())
                hys        = int(self._spin_hys.get())
            except ValueError:
                split_midi, hys = 60, 4

            export_ly  = self._var_export_ly.get()
            export_pdf = self._var_export_pdf.get()
            export_png = self._var_export_png.get()
            try: png_dpi = int(self._spin_dpi.get())
            except ValueError: png_dpi = 150

            composer = self.gui.composer
            title = getattr(getattr(self.gui,"entry_title",None),"get",
                            lambda: "Composição Abjad")()
            style = getattr(getattr(self.gui,"combo_style",None),"get",
                            lambda: "balanced")()
            instruments = self._resolve_instruments()
            if not instruments:
                self._log_write("Nenhum instrumento selecionado.\n")
                return

            # Lê pool e pausas ANTES do log (evita UnboundLocalError)
            custom_pool    = self._parse_tuplet_pool()
            custom_weights = self._parse_tuplet_weights()
            custom_nest    = self._parse_nest_pool()
            rest_prob   = float(self._scl_rest.get())
            rest_mode   = self._var_rest_mode.get()
            try:    rest_max = float(self._spin_rest_max.get())
            except: rest_max = 0.0
            try:    rest_phrase = int(self._spin_rest_phrase.get())
            except: rest_phrase = 6

            pool_info = (f"pool customizado ({len(custom_pool)} ratios)"
                         if custom_pool else f"preset nível {tuplet_level}")
            self._log_write(
                f"Instrumentos: {', '.join(instruments)}\n"
                f"Tuplas: prob={tuplet_prob:.2f}  {pool_info}  "
                f"aninhamento={nesting_prob:.2f}\n"
                f"Pausas: prob={rest_prob:.2f}  modo={rest_mode}\n"
                f"Grand staff: split={split_midi} histerese={hys}\n"
            )

            adapter = GrammarAbjadAdapter(composer)
            adapter.output_dir            = out_dir
            adapter.lilypond_path         = ly_path
            adapter.use_proportional      = prop
            adapter.proportional_moment   = moment
            adapter.microtone_probability = microtone_prob
            adapter.technique_probability = technique_prob
            adapter.glissando_probability = glissando_prob
            adapter.tuplet_probability    = tuplet_prob
            adapter.tuplet_complexity     = tuplet_level
            adapter.tuplet_nesting_prob   = nesting_prob

            # Pool de quiálteras
            if custom_pool is not None:
                adapter.tuplet_pool    = custom_pool
            if custom_weights is not None:
                adapter.tuplet_weights = custom_weights
            if custom_nest is not None:
                adapter.nest_pool      = custom_nest

            # Pausas
            adapter.rest_probability   = rest_prob
            adapter.rest_mode          = rest_mode
            adapter.rest_max_duration  = rest_max
            adapter.rest_phrase_length = rest_phrase

            adapter.piano_split_midi      = split_midi
            adapter.piano_split_hysteresis = hys
            adapter.paper_size            = paper

            # ── Sincroniza parâmetros da GUI com o composer ──────────────
            # Lê spin_length / length_type da aba Gerador para calcular
            # o número correto de eventos, igual ao que _generate_composition faz.
            try:
                length_val  = int(getattr(
                    getattr(self.gui, "spin_length", None), "get",
                    lambda: str(getattr(composer, "composition_length", 32))
                )())
                use_measures = getattr(
                    getattr(self.gui, "length_type", None), "get",
                    lambda: "events"
                )() == "measures"
            except Exception:
                length_val  = getattr(composer, "composition_length", 32)
                use_measures = False

            if use_measures:
                # Injeta o target de compassos para _compute_length usar
                composer._abjad_target_measures = length_val
                composer.composition_length = length_val  # fallback
                self._log_write(
                    f"Comprimento: {length_val} compassos\n"
                )
            else:
                composer._abjad_target_measures = None
                composer.composition_length = length_val
                self._log_write(
                    f"Comprimento: {length_val} eventos\n"
                )

            # Lê andamento da GUI
            try:
                tempo_val = int(getattr(
                    getattr(self.gui, "spin_tempo", None), "get",
                    lambda: str(getattr(composer, "tempo", 90))
                )())
                composer.tempo = tempo_val
            except Exception:
                pass

            # ── Sincroniza configurações de fórmula de compasso ─────────
            # Lê os mesmos widgets que _apply_time_sig_config usa,
            # sem exigir que o usuário clique "Aplicar Configuração".
            try:
                use_var = getattr(
                    getattr(self.gui, "use_variable_ts", None), "get",
                    lambda: getattr(composer, "use_variable_time_signatures", False)
                )()
                ts_vars = getattr(self.gui, "ts_vars", {})
                if ts_vars:
                    selected_ts = [ts for ts, var in ts_vars.items() if var.get()]
                else:
                    selected_ts = getattr(composer, "variable_time_signatures",
                                          ['4/4','3/4','3/8','2/4','6/8','5/4','5/8','7/8'])
                if not selected_ts:
                    selected_ts = ['4/4']
                try:
                    change_prob = float(getattr(
                        getattr(self.gui, "scale_ts_change", None), "get",
                        lambda: str(getattr(composer, "time_sig_change_probability", 0.2))
                    )())
                except Exception:
                    change_prob = getattr(composer, "time_sig_change_probability", 0.2)

                # Aplica ao composer (mesmo que set_time_signature_options)
                composer.use_variable_time_signatures = bool(use_var)
                composer.variable_time_signatures     = selected_ts
                composer.time_sig_change_probability  = change_prob

                # Pré-gera a sequência de fórmulas para que _get_time_sig_sequence
                # a encontre em _current_time_sig_sequence (evita gerar nova sequência
                # inconsistente durante a construção de cada pauta).
                if composer.use_variable_time_signatures and selected_ts:
                    if use_measures:
                        n_measures = length_val
                    else:
                        # Estima número de compassos a partir de eventos e fórmula base
                        try:
                            num, den = map(int, getattr(composer,"time_signature","4/4").split("/"))
                            beats_per_m = num * (4.0 / den)
                            n_measures = max(4, int(length_val / max(1, beats_per_m) * 1.5))
                        except Exception:
                            n_measures = max(4, length_val // 4)
                    if hasattr(composer, "generate_time_signature_sequence"):
                        composer._current_time_sig_sequence =                             composer.generate_time_signature_sequence(n_measures + 20)
                        self._log_write(
                            f"Fórmulas variáveis: {len(selected_ts)} fórmulas | "
                            f"prob={change_prob:.2f} | "
                            f"{len(composer._current_time_sig_sequence)} compassos gerados\n"
                        )
                else:
                    composer._current_time_sig_sequence = None
                    self._log_write(
                        f"Fórmula fixa: {getattr(composer,'time_signature','4/4')}\n"
                    )
            except Exception as e:
                self._log_write(f"[Aviso] Sync de fórmulas: {e}\n")

            self._log_write(
                f"Andamento: {getattr(composer,'tempo',90)} BPM | "
                f"Fórmula base: {getattr(composer,'time_signature','4/4')} | "
                f"Variável: {getattr(composer,'use_variable_time_signatures',False)}\n"
            )

            self._log_write("Construindo sequências…\n")
            sequences = adapter.build_sequences_from_composer(
                instruments=instruments, style=style
            )
            if not sequences:
                self._log_write("Erro: nenhuma sequência gerada.\n")
                return

            notes = sum(s.sounding_note_count for s in sequences)
            total_beats = sum(s.total_beats for s in sequences[:1])
            self._log_write(
                f"{len(sequences)} pautas | {notes} notas | "
                f"≈{total_beats:.0f} beats\n"
            )

            safe = "".join(
                c if c.isalnum() or c in "-_ " else "_" for c in title
            ).replace(" ","_")[:40]

            self._log_write("Exportando…\n")
            result = adapter.generate_and_export(
                sequences=sequences,
                title=title,
                filename=safe,
                export_ly=export_ly,
                export_pdf=bool(ly_path) and export_pdf,
                export_png=bool(ly_path) and export_png,
                png_dpi=png_dpi,
            )

            self._last_ly_path  = result.get("ly")
            self._last_pdf_path = result.get("pdf")
            self._last_sequences = result.get("sequences")
            self._last_gen_title = title
            self._last_png_path = result.get("png")
            self._out_dir_last  = out_dir

            if self._last_ly_path:  self._log_write(f".ly: {self._last_ly_path}\n")
            if self._last_pdf_path: self._log_write(f"PDF: {self._last_pdf_path}\n")
            if self._last_png_path: self._log_write(f"PNG: {self._last_png_path}\n")
            elif export_png and ly_path:
                self._log_write(
                    "PNG não gerado — verifique o LilyPond.\n"
                    f"Manual: lilypond --png -dresolution={png_dpi} "
                    f"-o \"{os.path.splitext(self._last_ly_path or '')[0]}\" "
                    f"\"{self._last_ly_path}\"\n"
                )

            self._log_write("Concluído.\n")

        except Exception as exc:
            import traceback
            self._log_write(f"Erro: {exc}\n{traceback.format_exc()}\n")
        finally:
            self.frame.after(0, self._generation_done)

    def _generation_done(self):
        self._progress.stop()
        self._btn_generate.configure(state=tk.NORMAL)

        has_ly  = bool(self._last_ly_path  and os.path.exists(self._last_ly_path))
        has_pdf = bool(self._last_pdf_path and os.path.exists(self._last_pdf_path))
        has_seqs = bool(getattr(self, "_last_sequences", None))
        has_png = bool(self._last_png_path and os.path.exists(self._last_png_path))

        self._btn_open_ly.configure(   state=tk.NORMAL if has_ly  else tk.DISABLED)
        self._btn_open_pdf.configure(  state=tk.NORMAL if has_pdf else tk.DISABLED)
        self._btn_open_ms.configure(   state=tk.NORMAL if has_seqs else tk.DISABLED)
        self._btn_open_folder.configure(state=tk.NORMAL if (has_ly or has_pdf) else tk.DISABLED)
        self._btn_refresh_png.configure(state=tk.NORMAL if has_png else tk.DISABLED)
        self._btn_save_png.configure(   state=tk.NORMAL if has_png else tk.DISABLED)

        # Atualiza preview automaticamente
        if has_png:
            self.frame.after(100, self._refresh_preview)
        elif has_pdf:
            if messagebox.askyesno("PDF pronto", "PDF gerado! Abrir agora?"):
                self._open_pdf()
        elif has_ly:
            messagebox.showinfo("Arquivo .ly salvo",
                f"Partitura salva em:\n{self._last_ly_path}\n\n"
                "Configure o LilyPond para gerar PDF/PNG.")

    # ------------------------------------------------------------------
    # Resolução de instrumentos
    # ------------------------------------------------------------------

    def _resolve_instruments(self) -> list:
        """
        Retorna IDs dos instrumentos a usar na geração Abjad.

        Modo 'ativos' (radiobutton padrão):
          1. Lê os spinboxes da aba Instrumentos diretamente (não requer
             que o usuário clique Aplicar).
          2. Fallback: composer.active_instruments.
          3. Último fallback: piano.

        Modo 'manual': usa a listbox desta aba.
        """
        if self._var_use_active.get():
            # 1. Lê instrument_vars diretamente dos spinboxes da aba Instrumentos
            instrument_vars = getattr(self.gui, "instrument_vars", {})
            if instrument_vars:
                selected = []
                for inst_id, var in instrument_vars.items():
                    try:
                        count = int(var.get())
                    except (ValueError, TypeError):
                        count = 0
                    if count > 0:
                        if count == 1:
                            selected.append(inst_id)
                        else:
                            for i in range(1, count + 1):
                                selected.append(f"{inst_id}_{i}")
                if selected:
                    self._log_write(
                        f"[Instrumentos] Lidos da aba Instrumentos: {', '.join(selected)}\n"
                    )
                    return selected

            # 2. Fallback: active_instruments
            active = list(getattr(self.gui.composer, "active_instruments", []))
            if active:
                self._log_write(
                    f"[Instrumentos] Lidos de active_instruments: {', '.join(active)}\n"
                )
                return active

            # 3. Último fallback
            self._log_write(
                "[Aviso] Nenhum instrumento selecionado. "
                "Use a aba Instrumentos para configurar.\n"
            )
            return ["piano_direita", "piano_esquerda"]

        # Modo manual: listbox desta aba
        selected = []
        for idx in self._listbox_instr.curselection():
            line = self._listbox_instr.get(idx)
            selected.append(line.split("  —  ")[0].strip())
        return selected

    # ------------------------------------------------------------------
    # Abertura de arquivos
    # ------------------------------------------------------------------

    def _open_ly(self):
        if self._last_ly_path and os.path.exists(self._last_ly_path):
            self._open_file(self._last_ly_path)
        else:
            messagebox.showwarning("Não encontrado", "Arquivo .ly não disponível.")

    def _open_pdf(self):
        if self._last_pdf_path and os.path.exists(self._last_pdf_path):
            self._open_file(self._last_pdf_path)
        else:
            messagebox.showwarning("PDF não encontrado",
                "PDF não gerado. Verifique o LilyPond.")

    def _open_musescore(self):
        """
        Exporta as sequências para MusicXML (via musicxml_export.py) e
        abre no MuseScore. Garante que o MuseScore exibe o mesmo conteúdo
        que o LilyPond: mesmas notas, durações, dinâmicas, quiálteras,
        pausas e técnicas estendidas como texto.
        """
        seqs = getattr(self, "_last_sequences", None)
        if not seqs:
            messagebox.showwarning("Sem partitura",
                "Gere uma partitura antes de abrir no MuseScore.")
            return

        if not _MUSICXML_EXPORT_AVAILABLE:
            messagebox.showerror("Módulo ausente",
                "musicxml_export.py não encontrado.\n"
                "Coloque-o na mesma pasta do projeto.")
            return

        title = getattr(self, "_last_gen_title", "Composição")

        # Exporta para pasta de saída do projeto
        out_dir = getattr(self, "_out_dir_last", None)
        if not out_dir:
            import tempfile
            out_dir = tempfile.mkdtemp()

        safe = "".join(c if c.isalnum() or c in "-_ " else "_"
                       for c in title).replace(" ", "_")[:40]
        filepath = os.path.join(out_dir, f"{safe}_musescore.musicxml")

        self._log_write("Exportando MusicXML para MuseScore…\n")

        path = save_musicxml(
            seqs,
            filepath,
            title=title,
            composer_name="GrammarComposer",
        )

        if not path:
            messagebox.showerror("Erro", "Falha ao gerar MusicXML.")
            return

        self._log_write(f"MusicXML: {path}\n")
        self._open_file(path)

    def _open_folder(self):
        path = self._last_pdf_path or self._last_ly_path
        if path:
            self._open_file(os.path.dirname(os.path.abspath(path)))

    @staticmethod
    def _open_file(path: str):
        system = platform.system()
        try:
            if system == "Windows": os.startfile(path)
            elif system == "Darwin": subprocess.Popen(["open", path])
            else: subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Erro ao abrir", str(e))

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def _log_write(self, text: str):
        def _w():
            self._log.configure(state=tk.NORMAL)
            self._log.insert(tk.END, text)
            self._log.see(tk.END)
            self._log.configure(state=tk.DISABLED)
        try: self.frame.after(0, _w)
        except Exception: pass

    def _clear_log(self):
        self._log.configure(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        self._log.configure(state=tk.DISABLED)


# ---------------------------------------------------------------------------
# Teste standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    class _MockComposer:
        active_instruments = ["flauta","violoncelo","piano"]
        tempo = 72; time_signature = "4/4"; composition_length = 20
        composition_templates = {
            "balanced":{"min_pitch":55,"max_pitch":79,"rhythm_complexity":0.6,
                        "min_dynamic":"mp","max_dynamic":"mf"},
        }
        def __init__(self):
            import random
            self.rhythm_patterns = {(1.0,):10,(0.5,0.5):8}
            self.pitch_patterns  = {(60,62,64):10}
            self.tempo_expression = "Moderato"
        def _generate_rhythm_sequence(self, l, c):
            import random
            return [random.choice([1.0,0.5,0.5,0.25,1.5]) for _ in range(l)]
        def _generate_pitch_sequence(self, l, mn, mx):
            import random
            return [random.randint(mn,mx) if random.random()>0.1 else None for _ in range(l)]

    class _MockGUI:
        def __init__(self, root):
            self.notebook = ttk.Notebook(root)
            self.notebook.pack(fill=tk.BOTH, expand=True)
            self.composer = _MockComposer()
            self.current_composition = None
            f = ttk.Frame(self.notebook)
            self.notebook.add(f, text="(stub)")
            self.entry_title = tk.Entry(f)
            self.entry_title.insert(0, "Teste v2 Standalone")
            self.combo_style = ttk.Combobox(f, values=["balanced"])
            self.combo_style.current(0)

    root = tk.Tk()
    root.title("AbjadTab v2 — Standalone")
    root.geometry("1100x750")
    mock = _MockGUI(root)
    tab = AbjadTab(mock)
    root.mainloop()
