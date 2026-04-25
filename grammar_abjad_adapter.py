"""
grammar_abjad_adapter.py  v2
============================
Adaptador entre o GenerativeGrammarComposer e o AbjadEngine v2.

v2 acrescenta:
  • Geração de tuplas estocástica com nível de complexidade configurável
    (1=tercinas … 5=Ferneyhough)
  • Configuração do grand staff (split point + histerese)
  • Funções de conveniência para quick_score e quick_png

Autor: Ivan Simurra / NICS-UNICAMP
"""

from __future__ import annotations

import os
import random
from typing import Optional

from note_event import (
    NoteEvent,
    TupletGroup,
    EventSequence,
    ExtendedTechnique,
    ArticulationType,
    HairpinType,
    GlissandoType,
    get_instrument,
    INSTRUMENT_CATALOG,
)

from fractions import Fraction as _Frac

def _beats_for_ts(ts_str: str) -> _Frac:
    """Duração de um compasso em quarter-beats como Fraction."""
    try:
        num, den = map(int, ts_str.split("/"))
        return _Frac(num) * _Frac(4, den)
    except Exception:
        return _Frac(4)

def _fill_measure(target_beats: _Frac, rhythm_patterns: dict,
                  rng=None) -> list:
    """
    Gera durações (floats) que somam EXATAMENTE target_beats.
    Usa rhythm_patterns para escolher padrões estocasicamente
    e clipa o último evento para preencher o compasso exato.
    """
    import random as _random
    _r = rng or _random
    patterns = [p for p in rhythm_patterns if
                all(isinstance(x,(int,float)) or
                    (isinstance(x,str) and x.replace('.','',1).lstrip('-').isdigit())
                    for x in p)]
    if not patterns:
        patterns = [(1.0,)]
    weights  = [rhythm_patterns[p] for p in patterns]
    # Normalise pattern values to floats
    fpatterns = [tuple(float(x) for x in p) for p in patterns]

    result = []
    remaining = target_beats
    MIN_DUR = _Frac(1, 16)   # semiquáver = mínimo

    while remaining > 0:
        if remaining <= MIN_DUR:
            result.append(float(remaining))
            break
        pat = _r.choices(fpatterns, weights=weights)[0]
        for dur in pat:
            dur_f = _Frac(dur).limit_denominator(32)
            if dur_f <= 0:
                continue
            if dur_f <= remaining:
                result.append(float(dur_f))
                remaining -= dur_f
            else:
                # Clipa para preencher exatamente
                result.append(float(remaining))
                remaining = _Frac(0)
                break
            if remaining == 0:
                break

    return result

# Pool de padrões rítmicos para percussão sem altura
# (geração autónoma quando não há dados de análise melódica)
PERCUSSION_RHYTHM_PATTERNS: list = [
    # Padrões simples
    [1.0, 1.0, 1.0, 1.0],
    [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
    [0.5, 0.5, 1.0, 1.0, 1.0],
    [1.0, 0.5, 0.5, 1.0, 1.0],
    [0.25, 0.25, 0.5, 0.5, 0.5, 0.5, 1.0],
    # Padrões com pausas
    [1.0, None, 1.0, 1.0],
    [0.5, 0.5, None, 0.5, 0.5, 1.0],
    # Padrões com sincopas
    [0.5, 1.0, 0.5, 1.0, 1.0],
    [0.25, 0.75, 0.5, 0.5, 1.0, 1.0],
]
from abjad_engine import AbjadEngine, generate_tuplet_rhythm


# ---------------------------------------------------------------------------
# Pools de técnicas por família
# ---------------------------------------------------------------------------

TECHNIQUE_POOL_BY_FAMILY: dict = {
    "cordas":   [ExtendedTechnique.NORMAL, ExtendedTechnique.SUL_PONTICELLO,
                 ExtendedTechnique.SUL_TASTO, ExtendedTechnique.COL_LEGNO,
                 ExtendedTechnique.HARMONICS, ExtendedTechnique.SNAP_PIZZICATO],
    "madeiras": [ExtendedTechnique.NORMAL, ExtendedTechnique.FLUTTER_TONGUE,
                 ExtendedTechnique.MULTIPHONIC, ExtendedTechnique.HARMONICS],
    "metais":   [ExtendedTechnique.NORMAL, ExtendedTechnique.FLUTTER_TONGUE,
                 ExtendedTechnique.MULTIPHONIC],
    "teclado":  [ExtendedTechnique.NORMAL],
    "voz":      [ExtendedTechnique.NORMAL],
}

INSTRUMENT_FAMILY: dict = {
    "flauta":"madeiras","flauta_piccolo":"madeiras","oboé":"madeiras",
    "corne_inglês":"madeiras","clarinete":"madeiras","clarinete_baixo":"madeiras",
    "fagote":"madeiras","contrafagote":"madeiras",
    "trompa":"metais","trompete":"metais","trombone":"metais",
    "trombone_baixo":"metais","tuba":"metais",
    "violino":"cordas","viola":"cordas","violoncelo":"cordas","contrabaixo":"cordas",
    "piano":"teclado","piano_direita":"teclado","piano_esquerda":"teclado",
    "cravo":"teclado","marimba":"teclado","vibrafone":"teclado",
    "soprano":"voz","mezzo":"voz","contralto":"voz",
    "tenor":"voz","barítono":"voz","baixo_voz":"voz",
}

# Ratios de tupla por nível de complexidade
# ─── Pool de quiálteras disponíveis ──────────────────────────────────────────
#
# TUPLET_RATIOS_PRESETS: pools pré-definidos por nível de complexidade estética.
# O usuário pode usar tuplet_complexity (1-5) para selecionar um preset,
# ou definir tuplet_pool diretamente com qualquer subconjunto de ratios.
#
# Ratios suportados (todos com configs limpas — inner_dur representável):
#   (3,2)  tercina         (4,3)  quartina       (5,3)  quint./colch.
#   (5,4)  quintina        (5,6)  quint.expand.  (6,4)  sêxtupla
#   (7,4)  sétima          (7,6)  sét./colch.    (7,8)  sét.expand.
#   (8,6)  óctupla/colch.  (9,4)  nônupla        (9,8)  nôn./colch.
#  (10,8)  décupla/colch. (11,4)  onzena        (11,8)  onz./colch.
#  (12,8)  duodécupla     (13,8)  terzadécima (Ferneyhough extremo)

TUPLET_RATIOS_PRESETS: dict = {
    1: [(3, 2)],
    2: [(3, 2), (5, 4)],
    3: [(3, 2), (4, 3), (5, 4), (6, 4), (7, 4)],
    4: [(3, 2), (4, 3), (5, 4), (5, 3), (6, 4), (7, 4), (7, 6), (9, 8)],
    5: [(3, 2), (4, 3), (5, 4), (5, 3), (6, 4), (7, 4), (7, 6),
        (8, 6), (9, 8), (11, 4), (11, 8), (13, 8)],
}

# Mantido por compatibilidade com código que usa TUPLET_RATIOS diretamente.
TUPLET_RATIOS = TUPLET_RATIOS_PRESETS[5]

# CLEAN_TUPLET_CONFIGS: para cada ratio (num, den), lista de (total_outer, inner_dur)
# onde inner_dur é sempre uma duração musical padrão (sem ties automáticos).
# Invariante: num × inner_dur × (den/num) = total_outer  ✓
# Ordenados por total_outer crescente.
CLEAN_TUPLET_CONFIGS: dict = {
    (3, 2): [
        (_Frac(1,4), _Frac(1,8)),   # \tuplet 3/2 { 3×fusa }          → 0.25b
        (_Frac(1,2), _Frac(1,4)),   # \tuplet 3/2 { 3×semicolcheia }  → 0.50b
        (_Frac(3,4), _Frac(3,8)),   # \tuplet 3/2 { 3×sc.pont. }      → 0.75b
        (_Frac(1,1), _Frac(1,2)),   # \tuplet 3/2 { 3×colcheia }      → 1.00b
        (_Frac(3,2), _Frac(3,4)),   # \tuplet 3/2 { 3×col.pont. }     → 1.50b
        (_Frac(2,1), _Frac(1,1)),   # \tuplet 3/2 { 3×semínima }      → 2.00b
    ],
    (4, 3): [
        (_Frac(3,8), _Frac(1,8)),   # \tuplet 4/3 { 4×fusa }          → 0.375b
        (_Frac(3,4), _Frac(1,4)),   # \tuplet 4/3 { 4×semicolcheia }  → 0.75b
        (_Frac(9,8), _Frac(3,8)),   # \tuplet 4/3 { 4×sc.pont. }      → 1.125b
        (_Frac(3,2), _Frac(1,2)),   # \tuplet 4/3 { 4×colcheia }      → 1.50b
        (_Frac(9,4), _Frac(3,4)),   # \tuplet 4/3 { 4×col.pont. }     → 2.25b
        (_Frac(3,1), _Frac(1,1)),   # \tuplet 4/3 { 4×semínima }      → 3.00b
    ],
    (5, 3): [
        (_Frac(3,8), _Frac(1,8)),   # \tuplet 5/3 { 5×fusa }          → 0.375b
        (_Frac(3,4), _Frac(1,4)),   # \tuplet 5/3 { 5×semicolcheia }  → 0.75b
        (_Frac(9,8), _Frac(3,8)),   # \tuplet 5/3 { 5×sc.pont. }      → 1.125b
        (_Frac(3,2), _Frac(1,2)),   # \tuplet 5/3 { 5×colcheia }      → 1.50b
        (_Frac(9,4), _Frac(3,4)),   # \tuplet 5/3 { 5×col.pont. }     → 2.25b
    ],
    (5, 4): [
        (_Frac(1,2), _Frac(1,8)),   # \tuplet 5/4 { 5×fusa }          → 0.50b
        (_Frac(1,1), _Frac(1,4)),   # \tuplet 5/4 { 5×semicolcheia }  → 1.00b
        (_Frac(3,2), _Frac(3,8)),   # \tuplet 5/4 { 5×sc.pont. }      → 1.50b
        (_Frac(2,1), _Frac(1,2)),   # \tuplet 5/4 { 5×colcheia }      → 2.00b
        (_Frac(3,1), _Frac(3,4)),   # \tuplet 5/4 { 5×col.pont. }     → 3.00b
    ],
    (5, 6): [
        (_Frac(3,4), _Frac(1,8)),   # \tuplet 5/6 { 5×fusa }          → 0.75b
        (_Frac(3,2), _Frac(1,4)),   # \tuplet 5/6 { 5×semicolcheia }  → 1.50b
        (_Frac(9,4), _Frac(3,8)),   # \tuplet 5/6 { 5×sc.pont. }      → 2.25b
        (_Frac(3,1), _Frac(1,2)),   # \tuplet 5/6 { 5×colcheia }      → 3.00b
    ],
    (6, 4): [
        (_Frac(1,2), _Frac(1,8)),   # \tuplet 6/4 { 6×fusa }          → 0.50b
        (_Frac(1,1), _Frac(1,4)),   # \tuplet 6/4 { 6×semicolcheia }  → 1.00b
        (_Frac(3,2), _Frac(3,8)),   # \tuplet 6/4 { 6×sc.pont. }      → 1.50b
        (_Frac(2,1), _Frac(1,2)),   # \tuplet 6/4 { 6×colcheia }      → 2.00b
        (_Frac(3,1), _Frac(3,4)),   # \tuplet 6/4 { 6×col.pont. }     → 3.00b
    ],
    (7, 4): [
        (_Frac(1,2), _Frac(1,8)),   # \tuplet 7/4 { 7×fusa }          → 0.50b
        (_Frac(1,1), _Frac(1,4)),   # \tuplet 7/4 { 7×semicolcheia }  → 1.00b
        (_Frac(3,2), _Frac(3,8)),   # \tuplet 7/4 { 7×sc.pont. }      → 1.50b
        (_Frac(2,1), _Frac(1,2)),   # \tuplet 7/4 { 7×colcheia }      → 2.00b
        (_Frac(3,1), _Frac(3,4)),   # \tuplet 7/4 { 7×col.pont. }     → 3.00b
    ],
    (7, 6): [
        (_Frac(3,4), _Frac(1,8)),   # \tuplet 7/6 { 7×fusa }          → 0.75b
        (_Frac(3,2), _Frac(1,4)),   # \tuplet 7/6 { 7×semicolcheia }  → 1.50b
        (_Frac(9,4), _Frac(3,8)),   # \tuplet 7/6 { 7×sc.pont. }      → 2.25b
        (_Frac(3,1), _Frac(1,2)),   # \tuplet 7/6 { 7×colcheia }      → 3.00b
    ],
    (7, 8): [
        (_Frac(1,1), _Frac(1,8)),   # \tuplet 7/8 { 7×fusa }          → 1.00b
        (_Frac(2,1), _Frac(1,4)),   # \tuplet 7/8 { 7×semicolcheia }  → 2.00b
        (_Frac(3,1), _Frac(3,8)),   # \tuplet 7/8 { 7×sc.pont. }      → 3.00b
    ],
    (8, 6): [
        (_Frac(3,4), _Frac(1,8)),   # \tuplet 8/6 { 8×fusa }          → 0.75b
        (_Frac(3,2), _Frac(1,4)),   # \tuplet 8/6 { 8×semicolcheia }  → 1.50b
        (_Frac(9,4), _Frac(3,8)),   # \tuplet 8/6 { 8×sc.pont. }      → 2.25b
        (_Frac(3,1), _Frac(1,2)),   # \tuplet 8/6 { 8×colcheia }      → 3.00b
    ],
    (9, 4): [
        (_Frac(1,2), _Frac(1,8)),   # \tuplet 9/4 { 9×fusa }          → 0.50b
        (_Frac(1,1), _Frac(1,4)),   # \tuplet 9/4 { 9×semicolcheia }  → 1.00b
        (_Frac(3,2), _Frac(3,8)),   # \tuplet 9/4 { 9×sc.pont. }      → 1.50b
        (_Frac(2,1), _Frac(1,2)),   # \tuplet 9/4 { 9×colcheia }      → 2.00b
        (_Frac(3,1), _Frac(3,4)),   # \tuplet 9/4 { 9×col.pont. }     → 3.00b
    ],
    (9, 8): [
        (_Frac(1,1), _Frac(1,8)),   # \tuplet 9/8 { 9×fusa }          → 1.00b
        (_Frac(2,1), _Frac(1,4)),   # \tuplet 9/8 { 9×semicolcheia }  → 2.00b
        (_Frac(3,1), _Frac(3,8)),   # \tuplet 9/8 { 9×sc.pont. }      → 3.00b
    ],
    (10, 8): [
        (_Frac(1,1), _Frac(1,8)),   # \tuplet 10/8 { 10×fusa }        → 1.00b
        (_Frac(2,1), _Frac(1,4)),   # \tuplet 10/8 { 10×semicolcheia }→ 2.00b
        (_Frac(3,1), _Frac(3,8)),   # \tuplet 10/8 { 10×sc.pont. }    → 3.00b
    ],
    (11, 4): [
        (_Frac(1,2), _Frac(1,8)),   # \tuplet 11/4 { 11×fusa }        → 0.50b
        (_Frac(1,1), _Frac(1,4)),   # \tuplet 11/4 { 11×semicolcheia }→ 1.00b
        (_Frac(3,2), _Frac(3,8)),   # \tuplet 11/4 { 11×sc.pont. }    → 1.50b
        (_Frac(2,1), _Frac(1,2)),   # \tuplet 11/4 { 11×colcheia }    → 2.00b
        (_Frac(3,1), _Frac(3,4)),   # \tuplet 11/4 { 11×col.pont. }   → 3.00b
    ],
    (11, 8): [
        (_Frac(1,1), _Frac(1,8)),   # \tuplet 11/8 { 11×fusa }        → 1.00b
        (_Frac(2,1), _Frac(1,4)),   # \tuplet 11/8 { 11×semicolcheia }→ 2.00b
        (_Frac(3,1), _Frac(3,8)),   # \tuplet 11/8 { 11×sc.pont. }    → 3.00b
    ],
    (12, 8): [
        (_Frac(1,1), _Frac(1,8)),   # \tuplet 12/8 { 12×fusa }        → 1.00b
        (_Frac(2,1), _Frac(1,4)),   # \tuplet 12/8 { 12×semicolcheia }→ 2.00b
        (_Frac(3,1), _Frac(3,8)),   # \tuplet 12/8 { 12×sc.pont. }    → 3.00b
    ],
    (13, 8): [
        (_Frac(1,1), _Frac(1,8)),   # \tuplet 13/8 { 13×fusa }        → 1.00b
        (_Frac(2,1), _Frac(1,4)),   # \tuplet 13/8 { 13×semicolcheia }→ 2.00b
        (_Frac(3,1), _Frac(3,8)),   # \tuplet 13/8 { 13×sc.pont. }    → 3.00b
    ],
}

def _make_tuplet_group(
    note_data: list,
    ratio: tuple,
    instrument_id: str,
) -> "TupletGroup":
    """
    Cria um TupletGroup a partir de uma lista de tuplas de dados de nota.
    
    Cada elemento de note_data é:
      (pitch, microtone, dur_interna, technique, glissando, dyn, hp, hp_end)
    
    dur_interna = duração nominal da nota DENTRO da quiáltera
    (a duração soada real é dur_interna * den/num, calculada pelo LilyPond).
    
    ratio = (num, den): ex. (3,2) = 3 notas no espaço de 2 unidades.
    O LilyPond renderiza como \tuplet num/den { ... }.
    """
    events = []
    for (pitch, microtone, dur, tech, gliss, dyn, hp, hp_end) in note_data:
        ev = NoteEvent(
            pitch_midi=pitch,
            microtone_offset=microtone,
            duration_beats=dur,
            dynamic=dyn,
            hairpin=hp,
            hairpin_end=hp_end,
            technique=tech,
            glissando=gliss,
            instrument_id=instrument_id,
        )
        events.append(ev)
    ratio_str = f"{ratio[0]}:{ratio[1]}"
    return TupletGroup(ratio_str, events, instrument_id=instrument_id)




def get_family(instrument_id: str) -> str:
    base = instrument_id.rsplit("_", 1)[0]
    return INSTRUMENT_FAMILY.get(instrument_id,
           INSTRUMENT_FAMILY.get(base, "teclado"))


# ---------------------------------------------------------------------------
# GrammarAbjadAdapter v2
# ---------------------------------------------------------------------------

class GrammarAbjadAdapter:
    """
    Ponte entre o GenerativeGrammarComposer e o AbjadEngine.

    Parâmetros de notação contemporânea (todos 0.0–1.0):
        microtone_probability   — chance de quarto-de-tom por nota
        technique_probability   — chance de técnica estendida por nota
        glissando_probability   — chance de glissando por nota
        tuplet_probability      — chance de um grupo de notas virar tupla
        tuplet_complexity       — nível 1–5 (1=tercinas, 5=Ferneyhough)
        tuplet_nesting_prob     — chance de uma tupla conter outra (aninhamento)
    """

    def __init__(self, grammar_composer=None):
        self.composer = grammar_composer
        self.output_dir: str        = "output"
        self.lilypond_path: Optional[str] = None

        # Notação contemporânea
        self.use_proportional: bool     = False
        self.proportional_moment: str   = "1/16"
        self.microtone_probability: float   = 0.0
        self.technique_probability: float   = 0.0
        self.glissando_probability: float   = 0.0
        self.tuplet_probability:  float      = 0.0
        self.tuplet_complexity:   int         = 1    # 1–5 (seleciona preset pool)
        self.tuplet_nesting_prob: float       = 0.0  # prob. de aninhar quiálteras

        # ── Pool de ratios ──────────────────────────────────────────────────
        # tuplet_pool: lista explícita de (num,den) disponíveis para sorteio.
        #   None → usa o preset definido por tuplet_complexity.
        # tuplet_weights: dict opcional (num,den) → float com pesos relativos.
        #   None → distribuição uniforme entre os ratios do pool.
        # nest_pool: ratios elegíveis para a camada interna do aninhamento.
        #   None → usa os ratios do pool com num <= 5 (ratios mais simples).
        self.tuplet_pool:    "list | None"   = None
        self.tuplet_weights: "dict | None"   = None
        self.nest_pool:      "list | None"   = None

        # ── Pausas ─────────────────────────────────────────────────────────
        # rest_probability  : fração de notas que se tornam pausas (0.0–1.0)
        # rest_mode         : estratégia de distribuição
        #   'uniform' — pausas espalhadas aleatoriamente (texturas, Lachenmann)
        #   'phrase'  — pausas agrupadas no final de frases (escrita melódica)
        #   'breath'  — pausas após notas longas (sopros, cordas com arco)
        #   'sparse'  — pausas longas e raras por compasso (estilo Feldman)
        # rest_max_duration : duração máxima de uma pausa em beats (0 = livre)
        # rest_phrase_length: comprimento de frase em notas para o modo 'phrase'
        self.rest_probability:   float = 0.0
        self.rest_mode:          str   = 'uniform'
        self.rest_max_duration:  float = 0.0
        self.rest_phrase_length: int   = 6

        # Grand staff
        self.piano_split_midi: int          = 60
        self.piano_split_hysteresis: int    = 4

        self.paper_size: str = "a4"

    # ------------------------------------------------------------------
    # Construção de sequências a partir do composer legado
    # ------------------------------------------------------------------

    def build_sequences_from_composer(
        self, instruments: list = None, style: str = "balanced"
    ) -> list:
        if self.composer is None:
            raise RuntimeError("grammar_composer não foi fornecido.")
        insts = instruments or list(getattr(self.composer, "active_instruments", []))
        return [s for i in insts
                if (s := self._build_sequence(i, style)) is not None]

    def _build_sequence(
        self, inst_id: str, style: str
    ) -> Optional[EventSequence]:
        c   = self.composer
        cfg = get_instrument(inst_id)
        if cfg is None:
            print(f"[Adapter] '{inst_id}' não encontrado no catálogo.")
            return None

        # Percussão sem altura: fluxo próprio
        if cfg.is_percussion:
            return self._build_percussion_sequence(inst_id, cfg, style)

        style_params = getattr(c, "composition_templates", {}).get(
            style, {"min_pitch":48,"max_pitch":84,"rhythm_complexity":0.6}
        )
        min_p = max(cfg.tessitura_min_midi, style_params.get("min_pitch", 48))
        max_p = min(cfg.tessitura_max_midi, style_params.get("max_pitch", 84))
        complexity = style_params.get("rhythm_complexity", 0.6)
        family     = get_family(inst_id)
        tech_pool  = TECHNIQUE_POOL_BY_FAMILY.get(family, [ExtendedTechnique.NORMAL])

        # ── Sequência de fórmulas de compasso ────────────────────────────
        target_measures = getattr(c, "_abjad_target_measures", None)
        if target_measures:
            ts_seq = self._get_time_sig_sequence(c, int(target_measures))
            # Garante que a sequência tem exatamente target_measures compassos
            while len(ts_seq) < target_measures:
                ts_seq = ts_seq + ts_seq  # repete até ter o suficiente
            ts_seq = ts_seq[:int(target_measures)]
        else:
            # Modo eventos: estima compassos a partir do comprimento
            length_ev = max(8, int(getattr(c, "composition_length", 32)))
            est_measures = max(4, length_ev // 4)
            ts_seq = self._get_time_sig_sequence(c, est_measures)

        first_ts = self._parse_ts(ts_seq[0]) if ts_seq else self._parse_ts(
            getattr(c, "time_signature", "4/4")
        )

        # ── Geração compasso a compasso ───────────────────────────────────
        # Gera durações que preenchem EXATAMENTE cada compasso da sequência.
        # Isso garante que o número de compassos no .ly seja exatamente
        # o solicitado, sem compassos incompletos ou overflow.
        rhythm_patterns = getattr(c, "rhythm_patterns", {(1.0,):1})

        seq = EventSequence(
            instrument_id=inst_id,
            tempo_bpm=getattr(c, "tempo", 90.0),
            time_signature=first_ts,
            use_proportional=self.use_proportional,
            time_sig_sequence=ts_seq,
        )

        # Pré-computa plano de hairpins (por índice de evento)
        total_ev_estimate = sum(
            max(1, int(_beats_for_ts(ts) / 0.5))
            for ts in ts_seq
        )
        hairpin_plan   = self._generate_hairpin_plan(total_ev_estimate, style_params)
        hairpin_starts = {s: hp for s, e, hp in hairpin_plan}
        hairpin_ends   = {e for _, e, _ in hairpin_plan}

        dynamics_list  = self._generate_dynamics(total_ev_estimate, style_params)
        prev_tech      = ExtendedTechnique.NORMAL
        ev_idx         = 0   # global event counter for hairpin/dynamics lookup

        for ts_str in ts_seq:
            measure_beats = _beats_for_ts(ts_str)
            durations = _fill_measure(measure_beats, rhythm_patterns)

            # Gera alturas para este compasso
            n_pitches = len(durations)
            try:
                pitches = c._generate_pitch_sequence(n_pitches, min_p, max_p)
            except Exception:
                pitches = [random.randint(min_p, max_p) for _ in range(n_pitches)]
            # Transposição
            tr = cfg.transpose_semitones
            if tr:
                pitches = [p + tr if isinstance(p, int) else p for p in pitches]

            # ── Constrói lista de dados brutos para o compasso ──────────
            raw_notes = []   # (pitch, microtone, dur, tech, gliss, dyn, hp, hp_end)
            for dur, pitch in zip(durations, pitches):
                dyn    = dynamics_list[ev_idx] if ev_idx < len(dynamics_list) else None
                hp     = hairpin_starts.get(ev_idx)
                hp_end = ev_idx in hairpin_ends

                microtone = 0.0
                if pitch is not None and random.random() < self.microtone_probability:
                    microtone = random.choice([0.5, -0.5])

                technique = ExtendedTechnique.NORMAL
                if pitch is not None and random.random() < self.technique_probability:
                    candidates = [t for t in tech_pool if t != prev_tech]
                    if candidates:
                        technique = random.choice(candidates)
                elif prev_tech not in (ExtendedTechnique.NORMAL,
                                       ExtendedTechnique.ORDINARIO):
                    technique = ExtendedTechnique.ORDINARIO
                prev_tech = technique

                glissando = GlissandoType.NONE
                if (pitch is not None and ev_idx < total_ev_estimate - 1
                        and random.random() < self.glissando_probability):
                    glissando = (GlissandoType.WAVY
                                 if random.random() < 0.25
                                 else GlissandoType.NORMAL)

                raw_notes.append((pitch, microtone, dur, technique, glissando,
                                   dyn, hp, hp_end))
                ev_idx += 1

            # ── Injeta pausas (antes do agrupamento em quiálteras) ───────
            # Substitui pitches por None sem alterar durações → beat-invariant.
            # Pausas dentro de quiálteras são notação válida em LilyPond.
            raw_notes = self._inject_rests(raw_notes, measure_beats)

            # ── Agrupa notas em quiálteras (stochastic) ─────────────────
            items_to_add = self._group_into_tuplets(
                raw_notes, inst_id, measure_beats
            )
            for item in items_to_add:
                seq.append(item)

        return seq

    def _inject_rests(
        self,
        raw_notes: list,
        measure_beats: "_Frac",
    ) -> list:
        """
        Substitui alturas por pausas em raw_notes de acordo com rest_mode.

        O beat-invariant do compasso é SEMPRE preservado: apenas pitch_midi
        é setado para None; durações são mantidas intactas.

        Modos:
          'uniform' — cada nota tem independentemente probabilidade
                      rest_probability de virar pausa. Bom para texturas
                      esparsas e campos sonoros (Lachenmann, música espectral).
          'phrase'  — pausas agrupadas ao fim de frases. A cada
                      rest_phrase_length notas acumuladas, o final do compasso
                      recebe pausas. Bom para escrita melódica estruturada.
          'breath'  — pausas após notas longas (>= 0.75 beat). Probabilidade
                      elevada para notas longas, baixa para curtas. Simula
                      o fôlego natural de sopros e arco.
          'sparse'  — no máximo UMA pausa longa por compasso, com duração
                      controlada por rest_max_duration. Estilo Feldman:
                      silêncio como elemento estrutural.
        """
        if self.rest_probability <= 0.0 or not raw_notes:
            return raw_notes

        prob  = self.rest_probability
        mode  = self.rest_mode
        notes = list(raw_notes)

        def silence(n):
            """Mantém todos os atributos exceto pitch_midi → None."""
            return (None, n[1], n[2], n[3], n[4], n[5], n[6], n[7])

        if mode == 'uniform':
            # Cada nota: probabilidade independente de virar pausa
            for i, n in enumerate(notes):
                if n[0] is not None and random.random() < prob:
                    notes[i] = silence(n)

        elif mode == 'phrase':
            # Pausas ao final de frases (contador cross-compasso)
            self._rest_phrase_counter = getattr(self, '_rest_phrase_counter', 0)
            self._rest_phrase_counter += len(notes)
            if self._rest_phrase_counter >= self.rest_phrase_length:
                self._rest_phrase_counter = 0
                n_rests = max(1, round(len(notes) * prob))
                for i in range(max(0, len(notes) - n_rests), len(notes)):
                    notes[i] = silence(notes[i])
            else:
                # Fora do ponto de frase: pausa ocasional muito baixa
                for i, n in enumerate(notes):
                    if n[0] is not None and random.random() < prob * 0.15:
                        notes[i] = silence(n)

        elif mode == 'breath':
            # Pausas preferencialmente após notas longas
            LONG = 0.75
            for i in range(len(notes) - 1):  # última nota nunca vira pausa
                n = notes[i]
                if n[0] is None:
                    continue
                p = prob * 2.0 if float(n[2]) >= LONG else prob * 0.25
                if random.random() < p:
                    notes[i] = silence(n)

        elif mode == 'sparse':
            # Uma pausa longa por compasso, com probabilidade rest_probability
            if random.random() < prob:
                pos = random.randint(0, max(0, len(notes) - 1))
                remaining = sum(
                    _Frac(n[2]).limit_denominator(32) for n in notes[pos:]
                )
                if self.rest_max_duration > 0:
                    target = min(
                        _Frac(self.rest_max_duration).limit_denominator(32),
                        remaining
                    )
                else:
                    # Pausa de 0.5 a 2 beats (ou até o fim do compasso)
                    max_t = min(remaining, _Frac(2, 1))
                    target = _Frac(
                        random.uniform(0.5, max(0.5, float(max_t)))
                    ).limit_denominator(8)

                accum = _Frac(0)
                j = pos
                while j < len(notes) and accum < target - _Frac(1, 32):
                    accum += _Frac(notes[j][2]).limit_denominator(32)
                    notes[j] = silence(notes[j])
                    j += 1

        else:
            # Fallback: trata como 'uniform'
            for i, n in enumerate(notes):
                if n[0] is not None and random.random() < prob:
                    notes[i] = silence(n)

        return notes


    def _resolve_pool(self) -> "list[tuple]":
        """
        Retorna o pool de ratios ativo:
          • Se tuplet_pool foi definido explicitamente, usa-o.
          • Senão, usa TUPLET_RATIOS_PRESETS[tuplet_complexity].
        """
        if self.tuplet_pool is not None:
            return [tuple(r) for r in self.tuplet_pool]
        idx = max(1, min(5, self.tuplet_complexity))
        return list(TUPLET_RATIOS_PRESETS[idx])

    def _resolve_nest_pool(self, outer_pool: list) -> "list[tuple]":
        """
        Retorna o pool de ratios para a camada interna do aninhamento.
          • Se nest_pool foi definido, usa-o.
          • Senão, usa os ratios do pool com num <= 5 (mais simples).
            Fallback para (3,2) se nenhum qualifica.
        """
        if self.nest_pool is not None:
            return [tuple(r) for r in self.nest_pool]
        simple = [r for r in outer_pool if r[0] <= 5]
        return simple if simple else [(3, 2)]

    def _weighted_choice(self, pool: list) -> tuple:
        """
        Sorteia um ratio do pool com pesos opcionais (tuplet_weights).
        Se tuplet_weights não está definido, distribuição uniforme.
        """
        if not self.tuplet_weights:
            return random.choice(pool)
        weights = [float(self.tuplet_weights.get(r, 1.0)) for r in pool]
        total   = sum(weights)
        r_val   = random.uniform(0, total)
        accum   = 0.0
        for ratio, w in zip(pool, weights):
            accum += w
            if r_val <= accum:
                return ratio
        return pool[-1]

    def _group_into_tuplets(
        self,
        raw_notes: list,
        inst_id: str,
        measure_beats: "_Frac",
    ) -> list:
        """
        Agrupa estocasticamente raw_notes em TupletGroups com BEAT-BUDGET EXATO.

        ARQUITETURA CLEAN-ANCHOR + CONSUME-BY-DURATION:
        ─────────────────────────────────────────────────────────────────
        1. Decide SE e QUAL quiáltera criar nesta posição.
        2. Escolhe âncora limpa (total_outer, inner_dur) via CLEAN_TUPLET_CONFIGS:
             • total_outer ≤ remaining_beats
             • inner_dur é duração musical padrão (sem ties automáticos)
        3. Consome raw_notes até que a soma de suas durações originais
           alcance total_outer (usando _consume_until para alinhamento exato).
        4. Gera num notas com inner_dur — pitch/técnica da raw_notes consumidas.
        5. consumed += total_outer → orçamento do compasso preservado.

        Para quiálteras ANINHADAS:
          A quiáltera interna também usa âncora limpa com total <= inner_dur_outer.
          O número de notas brutas consumidas é calculado para o total combinado.

        INVARIANTE:
          sum(sounding_beats(ev) for ev in result) == measure_beats  ✓
        """
        result    = []
        i         = 0
        consumed  = _Frac(0)

        while i < len(raw_notes):
            note      = raw_notes[i]
            note_dur  = _Frac(note[2]).limit_denominator(64)
            remaining = measure_beats - consumed

            # ── Tenta criar quiáltera ────────────────────────────────────
            can_try = (
                self.tuplet_probability > 0
                and random.random() < self.tuplet_probability
                and remaining >= _Frac(1, 2)
            )

            if can_try:
                # ── Seleciona ratio do pool ──────────────────────────
                active_pool = self._resolve_pool()
                # Filtra para ratios com ao menos uma âncora limpa que cabe
                valid_pool = [
                    r for r in active_pool
                    if GrammarAbjadAdapter._best_clean_config(r, remaining) is not None
                ]
                if not valid_pool:
                    result.append(self._raw_to_event(note, inst_id))
                    consumed += note_dur
                    i += 1
                    continue

                ratio    = self._weighted_choice(valid_pool)
                num, den = ratio

                config = GrammarAbjadAdapter._best_clean_config(ratio, remaining)
                if config is None:
                    result.append(self._raw_to_event(note, inst_id))
                    consumed += note_dur
                    i += 1
                    continue

                total_outer, inner_dur = config

                # Determina quantas notas brutas cobrem total_outer
                k, raw_slice, remainder = GrammarAbjadAdapter._consume_until(
                    raw_notes, i, total_outer
                )
                if k is None or k < 2:
                    result.append(self._raw_to_event(note, inst_id))
                    consumed += note_dur
                    i += 1
                    continue

                # ── Decide: simples ou aninhada ──────────────────────────
                do_nest = (
                    self.tuplet_nesting_prob > 0
                    and random.random() < self.tuplet_nesting_prob
                    and (self.tuplet_complexity >= 3 or self.tuplet_pool is not None)
                )

                if do_nest:
                    tg, _ = self._build_nested_tuplet(
                        ratio, total_outer, inner_dur,
                        raw_notes, i, inst_id
                    )
                    if tg is None:
                        do_nest = False

                if not do_nest:
                    # Gera num notas com inner_dur, usando pitches de raw_slice
                    # (src repete as notas se raw_slice < num — pitches são fonte, não budget)
                    src = (raw_slice * ((num // max(len(raw_slice), 1)) + 1))[:num]
                    tg = self._build_simple_from_slice(
                        ratio, inner_dur, src, inst_id
                    )

                # notes_used é SEMPRE k — o número de notas brutas
                # coberto por total_outer via _consume_until.
                # O ratio num:den pode ter mais notas que k; elas são geradas
                # com pitches repetidos de raw_slice, não consumindo raw_notes adicionais.
                notes_used = k

                if tg is None:
                    result.append(self._raw_to_event(note, inst_id))
                    consumed += note_dur
                    i += 1
                    continue

                result.append(tg)
                consumed += total_outer
                i += notes_used
                # Se uma nota foi partida, inserimos o resto de volta na lista
                if remainder is not None:
                    raw_notes = list(raw_notes)
                    raw_notes.insert(i, remainder)
                continue

            # ── Nota normal ─────────────────────────────────────────────
            result.append(self._raw_to_event(note, inst_id))
            consumed += note_dur
            i += 1

        return result

    @staticmethod
    def _consume_until(raw_notes: list, start: int, target: "_Frac"):
        """
        Consome raw_notes[start:] até que a soma de durações ≈ target.

        Retorna (k, slice, remainder) onde:
          • k         = número de raw_notes originais consumidas
          • slice     = lista de raw_notes com durações ajustadas (soma == target)
          • remainder = raw_note com a duração sobrante se a última nota foi
                        partida no meio, ou None se não houve divisão.

        O chamador deve inserir remainder de volta em raw_notes[start+k:]
        para que o budget do compasso seja preservado.

        Retorna (None, None, None) se impossível.
        """
        target = _Frac(target).limit_denominator(64)
        accum  = _Frac(0)
        notes  = raw_notes[start:]

        for j, n in enumerate(notes):
            dur = _Frac(n[2]).limit_denominator(64)
            if accum + dur <= target + _Frac(1, 128):
                accum += dur
                if abs(accum - target) <= _Frac(1, 128):
                    return j + 1, list(notes[:j + 1]), None
            else:
                needed = target - accum
                if needed >= _Frac(1, 64):
                    # Parte a nota: usa 'needed' para o tuplet, devolve o resto
                    leftover = dur - needed
                    consumed_note  = (n[0], n[1], float(needed),  n[3], n[4], n[5], n[6], n[7])
                    remainder_note = (n[0], n[1], float(leftover), n[3], n[4], False, None, False)
                    return j + 1, list(notes[:j]) + [consumed_note], remainder_note
                break  # needed too small — cannot split cleanly

        k = len(notes)
        if k >= 2 and abs(accum - target) <= _Frac(1, 64):
            return k, list(notes), None
        return None, None, None

    @staticmethod
    def _best_clean_config(
        ratio: tuple,
        remaining: "_Frac",
        min_beats: "_Frac" = _Frac(1, 2),
    ):
        """
        Retorna (total_outer, inner_dur) para o ratio,
        com total_outer ≤ remaining e inner_dur duração musical padrão.
        Escolhe o maior total_outer válido. Retorna None se impossível.
        """
        configs = CLEAN_TUPLET_CONFIGS.get(ratio, [])
        valid   = [
            (t, i) for t, i in configs
            if min_beats <= t <= remaining + _Frac(1, 128)
        ]
        return max(valid, key=lambda x: x[0]) if valid else None

    @staticmethod
    def _build_simple_from_slice(
        ratio: tuple,
        inner_dur: "_Frac",
        src_notes: list,
        inst_id: str,
    ) -> "TupletGroup | None":
        """
        Cria TupletGroup simples com exatamente num notas de inner_dur.
        Pitches/técnicas retirados de src_notes (que já tem exatamente num elementos).
        """
        num, den = ratio
        if len(src_notes) < num:
            return None
        inner_data = [
            (n[0], n[1], float(inner_dur), n[3], n[4], n[5], n[6], n[7])
            for n in src_notes[:num]
        ]
        return _make_tuplet_group(inner_data, ratio, inst_id)


    @staticmethod
    def _best_clean_config(
        ratio: tuple,
        remaining: "_Frac",
        min_beats: "_Frac" = _Frac(1, 2),
    ):
        """
        Retorna (total_outer, inner_dur) para o ratio dado,
        com total_outer ≤ remaining e inner_dur representável.
        Escolhe o maior total_outer válido (quiáltera "mais cheia").
        Retorna None se nenhuma configuração cabe.
        """
        configs = CLEAN_TUPLET_CONFIGS.get(ratio, [])
        valid = [
            (t, i) for t, i in configs
            if min_beats <= t <= remaining + _Frac(1, 128)
        ]
        if not valid:
            return None
        return max(valid, key=lambda x: x[0])

    @staticmethod
    def _exact_clean_config(ratio: tuple, target: "_Frac"):
        """
        Retorna (total, inner) onde total == target exato.
        Usado no aninhamento para garantir que nested_total == inner_dur_outer,
        o que é necessário para que o sounding da quiáltera externa seja correto.
        Retorna None se não houver match exato dentro de tolerância 1/128.
        """
        configs = CLEAN_TUPLET_CONFIGS.get(ratio, [])
        tol = _Frac(1, 128)
        for t, i in configs:
            if abs(t - target) <= tol:
                return (t, i)
        return None

    def _build_simple_tuplet(
        self,
        ratio: tuple,
        total_outer: "_Frac",
        inner_dur: "_Frac",
        raw_notes: list,
        start_idx: int,
        inst_id: str,
    ) -> "TupletGroup | None":
        """
        Cria um TupletGroup simples com exatamente num notas de inner_dur.
        Usa as alturas/técnicas das raw_notes a partir de start_idx.
        Se não há raw_notes suficientes, retorna None.
        """
        num, den = ratio
        if start_idx + num > len(raw_notes):
            return None

        inner_data = []
        for k in range(num):
            n = raw_notes[start_idx + k]
            inner_data.append((n[0], n[1], float(inner_dur), n[3], n[4], n[5], n[6], n[7]))

        return _make_tuplet_group(inner_data, ratio, inst_id)

    def _build_nested_tuplet(
        self,
        outer_ratio: tuple,
        total_outer: "_Frac",
        inner_dur_outer: "_Frac",
        raw_notes: list,
        start_idx: int,
        inst_id: str,
    ) -> "tuple[TupletGroup | None, int]":
        """
        Cria uma quiáltera aninhada estilo Ferneyhough:

            \tuplet out_num/out_den {
                note note ... note        ← (out_num - 1) notas com inner_dur_outer
                \tuplet 3/2 { note note note }   ← sempre (3,2) internamente
            }

        A quiáltera interna é SEMPRE (3,2) — produz complexidade Ferneyhough
        genuína sem exigir dezenas de notas por compasso.

        A quiáltera interna ocupa inner_dur_outer beats sonoros.
        Suas 3 notas têm inner_dur_nested = inner_dur_outer / 2 (colcheia ou semínima).

        Retorna (tg, notes_used) onde notes_used = k (gerenciado pelo chamador).
        Se não houver âncora limpa para o nesting, retorna (None, 0).
        """
        out_num, out_den = outer_ratio

        # A quiáltera interna é sorteada do nest_pool — não mais fixada em (3,2).
        # Isso permite, ex., 	uplet 7/4 { ... 	uplet 5/4 { ... } ... }
        # ou 	uplet 13/8 { ... 	uplet 4/3 { ... } ... }
        outer_pool  = self._resolve_pool()
        inner_pool  = self._resolve_nest_pool(outer_pool)

        # Filtra inner_pool para ratios com âncora que cabe em inner_dur_outer
        valid_inner = [
            r for r in inner_pool
            if GrammarAbjadAdapter._best_clean_config(
                r, inner_dur_outer, min_beats=_Frac(1, 8)) is not None
        ]
        if not valid_inner:
            return None, 0

        inner_ratio = self._weighted_choice(valid_inner)
        in_num, in_den = inner_ratio

        # Âncora para a quiáltera interna: total deve ser EXATAMENTE inner_dur_outer.
        # Prova da invariante:
        #   sounding_outer = [(out_num-1)×inner_dur_outer + nested_total] × out_den/out_num
        #   Para que sounding_outer = total_outer = out_num × inner_dur_outer:
        #   nested_total DEVE ser = inner_dur_outer.
        nested_config = GrammarAbjadAdapter._exact_clean_config(
            inner_ratio,
            target=inner_dur_outer,
        )
        if nested_config is None:
            # Não existe config exata para este inner_ratio neste espaço → aborta
            return None, 0

        nested_total, nested_inner = nested_config

        # Coleta notas brutas: (out_num-1) para a camada externa + 3 para interna
        # Usa raw_notes com wrap circular se necessário
        all_notes = raw_notes[start_idx:]
        total_needed = (out_num - 1) + in_num

        def get_note(j):
            return all_notes[j % len(all_notes)] if all_notes else raw_notes[start_idx]

        # Notas externas: (out_num - 1) × inner_dur_outer
        outer_events = [
            self._raw_to_event(
                (get_note(k)[0], get_note(k)[1], float(inner_dur_outer),
                 get_note(k)[3], get_note(k)[4], get_note(k)[5],
                 get_note(k)[6], get_note(k)[7]),
                inst_id
            )
            for k in range(out_num - 1)
        ]

        # Quiáltera interna: 3 notas × nested_inner
        nested_data = [
            (get_note(out_num - 1 + k)[0], get_note(out_num - 1 + k)[1],
             float(nested_inner),
             get_note(out_num - 1 + k)[3], get_note(out_num - 1 + k)[4],
             get_note(out_num - 1 + k)[5], get_note(out_num - 1 + k)[6],
             get_note(out_num - 1 + k)[7])
            for k in range(in_num)
        ]
        nested_tg  = _make_tuplet_group(nested_data, inner_ratio, inst_id)
        outer_events.append(nested_tg)

        ratio_str = f"{out_num}:{out_den}"
        tg = TupletGroup(ratio_str, outer_events, instrument_id=inst_id)
        return tg, 0   # notes_used gerenciado pelo chamador (= k)


    @staticmethod
    def _raw_to_event(raw: tuple, inst_id: str) -> "NoteEvent":
        """Converte uma tupla raw_note em NoteEvent."""
        pitch, microtone, dur, tech, gliss, dyn, hp, hp_end = raw
        return NoteEvent(
            pitch_midi=pitch,
            microtone_offset=microtone,
            duration_beats=dur,
            dynamic=dyn,
            hairpin=hp,
            hairpin_end=hp_end,
            technique=tech,
            glissando=gliss,
            instrument_id=inst_id,
        )

    # ------------------------------------------------------------------
    # Helpers de comprimento e fórmulas de compasso
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_length(c) -> int:
        """
        Calcula o número de EVENTOS a gerar para atingir o alvo em beats/compassos.

        Problema: 1 evento != 1 beat.
        Os padrões rítmicos geram notas de 0.25, 0.5, 1.0, 1.5, 2.0 beats.
        Gerando N eventos ≠ N beats → compassos ficam curtos.

        Solução:
        - Calcula target_beats = compassos × beats/compasso
        - Estima avg_beat/event a partir de composer.rhythm_patterns
        - events = ceil(target_beats / avg_beat_per_event × 1.15) + margem
        """
        target_measures = getattr(c, "_abjad_target_measures", None)
        if target_measures:
            # Calcula beats por compasso (usa sequência variável se disponível)
            ts_seq = getattr(c, "_current_time_sig_sequence", None)
            if ts_seq:
                total_beats = 0.0
                for ts in ts_seq[:int(target_measures)]:
                    try:
                        num, den = map(int, ts.split("/"))
                        total_beats += num * (4.0 / den)
                    except Exception:
                        total_beats += 4.0
                # Se a sequência tem menos compassos que o alvo, extrapola
                if len(ts_seq) < target_measures:
                    avg_b = total_beats / max(1, len(ts_seq))
                    total_beats = avg_b * target_measures
            else:
                ts_str = getattr(c, "time_signature", "4/4")
                try:
                    num, den = map(int, ts_str.split("/"))
                    total_beats = target_measures * num * (4.0 / den)
                except Exception:
                    total_beats = target_measures * 4.0

            # Estima duração média por evento a partir dos padrões do composer.
            # Filtra tuplas que possam conter strings (padrões não-numéricos
            # do _extract_pattern_from_string do composer original).
            rhythm_patterns = getattr(c, "rhythm_patterns", {})
            tot_b = tot_e = 0.0
            for pat, w in rhythm_patterns.items():
                try:
                    # Extrai apenas elementos numéricos da tupla
                    nums = [float(x) for x in pat if isinstance(x, (int, float))
                            or (isinstance(x, str) and x.replace('.','',1).lstrip('-').isdigit())]
                    if nums:
                        tot_b += sum(nums) * float(w)
                        tot_e += len(nums) * float(w)
                except (TypeError, ValueError):
                    continue  # ignora padrões inválidos
            avg_dur = (tot_b / tot_e) if tot_e > 0 else 0.75

            # Margem de 20% + mínimo de 8 eventos
            needed = int(total_beats / max(0.1, avg_dur) * 1.20) + 8
            return max(8, needed)

        return max(8, int(getattr(c, "composition_length", 32)))

    @staticmethod
    def _get_time_sig_sequence(c, length: int) -> list:
        """
        Retorna a sequência de fórmulas de compasso.

        Usa _current_time_sig_sequence do composer se disponível
        (já gerada pela música21), senão gera nova via
        generate_time_signature_sequence, senão retorna lista fixa.
        """
        # 1. Sequência já calculada pelo composer (mais precisa)
        existing = getattr(c, "_current_time_sig_sequence", None)
        if existing:
            return existing

        # 2. Gera nova sequência se o método existe
        num_measures = max(4, length // 4)
        if hasattr(c, "generate_time_signature_sequence"):
            try:
                return c.generate_time_signature_sequence(num_measures)
            except Exception:
                pass

        # 3. Fallback: fórmula fixa
        ts = getattr(c, "time_signature", "4/4")
        return [ts] * num_measures

    def _build_percussion_sequence(
        self, inst_id: str, cfg, style: str
    ) -> EventSequence:
        """
        Gera uma EventSequence para percussão sem altura.

        Para instrumentos individuais (caixa, bumbo, etc.):
          usa o drum_note_name do InstrumentConfig.

        Para bateria completa (inst_id == 'bateria'):
          gera padrão rítmico com drum_instrument variado.

        Ritmos: extraídos do composer se disponíveis,
                senão usa PERCUSSION_RHYTHM_PATTERNS.
        """
        c = self.composer
        length = getattr(c, "composition_length", 32)
        style_params = getattr(c, "composition_templates", {}).get(
            style, {"rhythm_complexity": 0.6, "min_dynamic": "mp", "max_dynamic": "f"}
        )
        complexity = style_params.get("rhythm_complexity", 0.6)

        # Gera ritmos via composer se possível, senão usa padrões internos
        try:
            rhythm_raw = c._generate_rhythm_sequence(length, complexity)
        except Exception:
            pattern = random.choice(PERCUSSION_RHYTHM_PATTERNS)
            rhythm_raw = (pattern * (length // len(pattern) + 1))[:length]

        dynamics = self._generate_dynamics(length, style_params)

        seq = EventSequence(
            instrument_id=inst_id,
            tempo_bpm=getattr(c, "tempo", 90.0),
            time_signature=self._parse_ts(getattr(c, "time_signature", "4/4")),
            use_proportional=self.use_proportional,
        )

        # Bateria multi-som: rotaciona entre sons padrão
        BATERIA_CYCLE = [
            "closedhihat", "closedhihat", "snare", "closedhihat",
            "bassdrum",    "closedhihat", "snare", "closedhihat",
        ]

        is_bateria = (inst_id == "bateria" or
                      inst_id.startswith("bateria_"))

        for i, dur in enumerate(rhythm_raw):
            dyn = dynamics[i] if i < len(dynamics) else None

            # Tupla estocástica em percussão
            if (self.tuplet_probability > 0
                    and random.random() < self.tuplet_probability
                    and dur >= 0.5):
                ratio = ["3:2","5:4","7:4","7:8","11:8"][
                    min(self.tuplet_complexity - 1, 4)]
                n = int(ratio.split(":")[0])
                sub_dur = dur / n
                sub_events = []
                for j in range(n):
                    sub_dyn = dyn if j == 0 else None
                    if is_bateria:
                        drum = BATERIA_CYCLE[(i + j) % len(BATERIA_CYCLE)]
                        sub_events.append(NoteEvent(
                            pitch_midi=60, duration_beats=sub_dur,
                            dynamic=sub_dyn, drum_instrument=drum,
                            instrument_id=inst_id))
                    else:
                        sub_events.append(NoteEvent(
                            pitch_midi=60, duration_beats=sub_dur,
                            dynamic=sub_dyn, instrument_id=inst_id))
                seq.append(TupletGroup(ratio, sub_events,
                                       instrument_id=inst_id))
                continue

            # Nota ou pausa normal
            if is_bateria:
                drum = BATERIA_CYCLE[i % len(BATERIA_CYCLE)]
                ev = NoteEvent(pitch_midi=60, duration_beats=dur,
                               dynamic=dyn, drum_instrument=drum,
                               instrument_id=inst_id)
            else:
                ev = NoteEvent(pitch_midi=60, duration_beats=dur,
                               dynamic=dyn, instrument_id=inst_id)
            seq.append(ev)

        return seq

    # ------------------------------------------------------------------
    # Construção de sequências a partir de dados brutos
    # ------------------------------------------------------------------

    def build_sequences_from_data(
        self,
        instrument_data: dict,
        tempo_bpm: float = 90.0,
        time_signature: tuple = (4, 4),
    ) -> list:
        """
        instrument_data = {
          "violino": {
            "pitches":    [int|None, ...],
            "durations":  [float, ...],
            "dynamics":   [str|None, ...],   # opcional
            "microtones": [float, ...],      # opcional
            "techniques": [ExtendedTechnique, ...],  # opcional
            "hairpins":   [HairpinType, ...],# opcional
            "proportional": bool,            # opcional
          }, ...
        }
        """
        sequences = []
        for inst_id, data in instrument_data.items():
            pitches   = data.get("pitches", [])
            durations = data.get("durations", [])
            dynamics  = data.get("dynamics")
            microtones = data.get("microtones")
            techniques = data.get("techniques")
            hairpins  = data.get("hairpins")
            prop      = data.get("proportional", self.use_proportional)

            seq = EventSequence(
                instrument_id=inst_id,
                tempo_bpm=tempo_bpm,
                time_signature=time_signature,
                use_proportional=prop,
            )
            for i, (pitch, dur) in enumerate(zip(pitches, durations)):
                event = NoteEvent(
                    pitch_midi=pitch,
                    microtone_offset=microtones[i] if microtones and i < len(microtones) else 0.0,
                    duration_beats=dur,
                    dynamic=dynamics[i] if dynamics and i < len(dynamics) else None,
                    technique=techniques[i] if techniques and i < len(techniques)
                              else ExtendedTechnique.NORMAL,
                    hairpin=hairpins[i] if hairpins and i < len(hairpins)
                            else HairpinType.NONE,
                    instrument_id=inst_id,
                )
                seq.append(event)
            sequences.append(seq)
        return sequences

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def generate_and_export(
        self,
        sequences: list = None,
        title: str = "Composição",
        filename: str = "composicao",
        export_ly: bool = True,
        export_pdf: bool = True,
        export_png: bool = False,
        png_dpi: int = 150,
    ) -> dict:
        if sequences is None:
            sequences = self.build_sequences_from_composer()
        if not sequences:
            print("[Adapter] Nenhuma sequência para exportar.")
            return {}

        comp_name = "GrammarComposer"
        if self.composer:
            comp_name = getattr(
                getattr(self.composer, "metadata", None), "composer", comp_name
            )

        engine = AbjadEngine(
            title=title,
            composer_name=comp_name,
            use_proportional=self.use_proportional,
            proportional_moment=self.proportional_moment,
            lilypond_path=self.lilypond_path,
            paper_size=self.paper_size,
            piano_split_midi=self.piano_split_midi,
            piano_split_hysteresis=self.piano_split_hysteresis,
        )
        engine.build_score(sequences)

        os.makedirs(self.output_dir, exist_ok=True)
        base = os.path.join(self.output_dir, filename)
        result: dict = {}

        if export_ly:
            result["ly"] = engine.save_ly(base + ".ly")
        if export_pdf:
            pdf = engine.save_pdf(base + ".pdf")
            result["pdf"] = pdf
        if export_png:
            png = engine.save_png(base + ".png", dpi=png_dpi)
            result["png"] = png

        # Sempre inclui sequences no resultado para uso por outros exporters (ex: MusicXML)
        result["sequences"] = sequences

        return result

    # ------------------------------------------------------------------
    # Geração de items (NoteEvent e TupletGroup) — Etapa 6
    # ------------------------------------------------------------------

    def _build_items(
        self,
        pitches: list,
        rhythms: list,
        dynamics: list,
        tech_pool: list,
        inst_id: str,
        style_params: dict = None,
    ) -> list:
        """
        Percorre as listas paralelas e constrói NoteEvents e TupletGroups.
        Grupos de notas consecutivas são encapsulados em tuplas estocáticas.
        Inclui hairpin arcs (crescendo/decrescendo) entre dinâmicas.
        """
        result = []
        i = 0
        prev_tech = ExtendedTechnique.NORMAL
        n = min(len(pitches), len(rhythms))

        # Pré-computa o plano de hairpins
        sp = style_params or {}
        hairpin_plan = self._generate_hairpin_plan(n, sp)
        # Mapeia índice → ação: 'start_<type>' ou 'end'
        hairpin_starts = {s: hp for s, e, hp in hairpin_plan}
        hairpin_ends   = {e for _, e, _ in hairpin_plan}

        while i < n:
            # Decide se inicia um grupo de tupla aqui
            if (self.tuplet_probability > 0
                    and random.random() < self.tuplet_probability
                    and i + 2 < n):  # mínimo 3 notas para uma tupla

                ratio = TUPLET_RATIOS[min(self.tuplet_complexity - 1, 4)]
                tup_n = int(ratio.split(":")[0])
                # Não ultrapassar o fim da sequência
                group_size = min(tup_n, n - i)
                if group_size >= 2:
                    group_events = []
                    for j in range(group_size):
                        ev = self._make_note_event(
                            pitches[i+j], rhythms[i+j],
                            dynamics[i+j] if i+j < len(dynamics) else None,
                            tech_pool, prev_tech, inst_id, i+j, n
                        )
                        if isinstance(ev, NoteEvent):
                            prev_tech = ev.technique
                        group_events.append(ev)

                    # Aninhamento estocástico
                    if (self.tuplet_nesting_prob > 0
                            and random.random() < self.tuplet_nesting_prob
                            and len(group_events) >= 4):
                        mid = len(group_events) // 2
                        inner_ratio = TUPLET_RATIOS[
                            min(self.tuplet_complexity, 4)
                        ]
                        inner = TupletGroup(
                            inner_ratio,
                            group_events[:mid],
                            instrument_id=inst_id
                        )
                        outer = TupletGroup(
                            ratio,
                            [inner] + group_events[mid:],
                            instrument_id=inst_id
                        )
                        result.append(outer)
                    else:
                        result.append(TupletGroup(ratio, group_events,
                                                   instrument_id=inst_id))
                    i += group_size
                    continue

            # Nota ou pausa normal
            hp      = hairpin_starts.get(i)
            hp_end  = i in hairpin_ends
            ev = self._make_note_event(
                pitches[i], rhythms[i],
                dynamics[i] if i < len(dynamics) else None,
                tech_pool, prev_tech, inst_id, i, n,
                hairpin=hp, hairpin_end=hp_end,
            )
            if isinstance(ev, NoteEvent):
                prev_tech = ev.technique
            result.append(ev)
            i += 1

        return result

    def _make_note_event(
        self, pitch, duration, dynamic, tech_pool, prev_tech, inst_id, idx, total,
        hairpin=None, hairpin_end=False
    ) -> NoteEvent:
        """Cria um NoteEvent com enriquecimento contemporâneo."""
        # Microtonalismo
        microtone = 0.0
        if pitch is not None and random.random() < self.microtone_probability:
            microtone = random.choice([0.5, -0.5])

        # Técnica estendida
        technique = ExtendedTechnique.NORMAL
        if random.random() < self.technique_probability:
            candidates = [t for t in tech_pool if t != prev_tech]
            if candidates:
                technique = random.choice(candidates)
        elif prev_tech not in (ExtendedTechnique.NORMAL, ExtendedTechnique.ORDINARIO):
            technique = ExtendedTechnique.ORDINARIO

        # Glissando (inclui wavy com baixa probabilidade)
        glissando = GlissandoType.NONE
        if (pitch is not None
                and idx < total - 1
                and random.random() < self.glissando_probability):
            glissando = (GlissandoType.WAVY
                         if random.random() < 0.25
                         else GlissandoType.NORMAL)

        return NoteEvent(
            pitch_midi=pitch,
            microtone_offset=microtone,
            duration_beats=duration,
            dynamic=dynamic,
            hairpin=hairpin,
            hairpin_end=hairpin_end,
            technique=technique,
            glissando=glissando,
            instrument_id=inst_id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_ts(ts_str: str) -> tuple:
        try:
            a, b = map(int, ts_str.split("/"))
            return (a, b)
        except Exception:
            return (4, 4)

    @staticmethod
    def _generate_dynamics(length: int, style_params: dict) -> list:
        """
        Retorna lista de dinâmicas (strings ou None) para cada evento.
        Os hairpins (crescendo/decrescendo) são gerenciados separadamente
        por _generate_hairpin_plan e injetados em _build_items.
        """
        order = ["ppp","pp","p","mp","mf","f","ff","fff"]
        lo = order.index(style_params.get("min_dynamic","p"))
        hi = order.index(style_params.get("max_dynamic","f"))
        result = [None] * length
        if length == 0:
            return result
        result[0] = order[random.randint(lo, hi)]
        step = max(4, length // 8)
        for i in range(step, length, step):
            result[i] = order[random.randint(lo, hi)]
        return result

    @staticmethod
    def _generate_hairpin_plan(length: int, style_params: dict) -> list:
        """
        Gera um plano de hairpins: lista de tuplas (start_idx, end_idx, type).
        type: HairpinType.CRESCENDO ou HairpinType.DECRESCENDO
        Arcos não se sobrepõem e duram entre 3 e 12 eventos.
        """
        from note_event import HairpinType
        plan = []
        i = 4  # leave some space at start
        while i < length - 4:
            arc_len = random.randint(3, min(12, length - i - 2))
            hp_type = random.choice([HairpinType.CRESCENDO, HairpinType.DECRESCENDO])
            plan.append((i, i + arc_len, hp_type))
            i += arc_len + random.randint(2, 6)  # gap between arcs
        return plan


# ---------------------------------------------------------------------------
# Conveniência: quick_score e quick_png
# ---------------------------------------------------------------------------

def quick_score(
    instrument_data: dict,
    title: str = "Composição",
    output_path: str = "output/composicao",
    use_proportional: bool = False,
    tempo_bpm: float = 90.0,
    time_signature: tuple = (4, 4),
    lilypond_path: Optional[str] = None,
    export_png: bool = False,
    png_dpi: int = 150,
) -> dict:
    """
    Geração rápida a partir de dicionário de dados.

    Exemplo
    -------
    result = quick_score(
        instrument_data={"violino": {"pitches":[60,62,64],"durations":[1,1,1]}},
        title="Teste",
        output_path="output/teste",
    )
    """
    adapter = GrammarAbjadAdapter()
    adapter.use_proportional = use_proportional
    adapter.lilypond_path = lilypond_path
    adapter.output_dir = os.path.dirname(output_path) or "."

    sequences = adapter.build_sequences_from_data(
        instrument_data, tempo_bpm=tempo_bpm, time_signature=time_signature
    )
    return adapter.generate_and_export(
        sequences=sequences,
        title=title,
        filename=os.path.basename(output_path),
        export_png=export_png,
        png_dpi=png_dpi,
    )


# ---------------------------------------------------------------------------
# Teste standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 55)
    print("  Teste GrammarAbjadAdapter v2")
    print("=" * 55)

    # Adapter com todas as features v2 ativas
    result = quick_score(
        instrument_data={
            "flauta": {
                "pitches":    [67, 69, 71, 72, 74, 72, None, 69],
                "durations":  [1.0, 1.0, 0.5, 0.5, 0.5, 0.5, 1.0, 1.0],
                "dynamics":   ["mp", None, None, "f", None, None, None, "pp"],
                "microtones": [0.0, 0.5, 0.0, 0.0, 0.0, -0.5, 0.0, 0.0],
                "hairpins":   [HairpinType.CRESCENDO] + [HairpinType.NONE]*5 +
                              [HairpinType.NONE, HairpinType.NONE],
            },
            "piano": {
                "pitches":    [72, 74, 71, 48, 52, 55, 67, 65, 64],
                "durations":  [1.0, 0.5, 0.5, 2.0, 0.5, 0.5, 1.0, 0.5, 0.5],
                "dynamics":   ["mf", None, None, "pp", None, None, "f", None, None],
            },
            "violoncelo": {
                "pitches":    [48, 50, 52, None, 55, 53, 50],
                "durations":  [2.0, 1.0, 0.5, 0.5, 1.5, 1.0, 2.0],
                "dynamics":   ["ppp", None, "mf", None, "f", None, "ppp"],
                "proportional": True,
            },
        },
        title="Fragmento v2 — Flauta, Piano e Violoncelo",
        output_path="output/fragmento_v2",
        tempo_bpm=63.0,
        time_signature=(4, 4),
        export_png=False,   # True se LilyPond estiver instalado
    )

    print("\nArquivos gerados:")
    for k, v in result.items():
        print(f"  {k}: {v}")
    if result.get("ly"):
        print("\n[OK] .ly gerado com sucesso.")

    # Verifica que o piano gerou PianoStaff
    if result.get("ly"):
        content = open(result["ly"]).read()
        assert "PianoStaff" in content, "PianoStaff ausente!"
        print("[OK] PianoStaff presente no .ly")
