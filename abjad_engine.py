"""
abjad_engine.py  v2
===================
Motor de notação Abjad para o Symbolic Grammar Composer.

v2 acrescenta:
  • Etapa 6 — Tuplas complexas: suporte a TupletGroup com aninhamento
    estilo Ferneyhough (3:2, 5:4, 7:4, 7:8, 11:8, …)
  • Etapa 7 — Grand staff refinado para piano/cravo: divisão por frase
    (registros adjacentes mantidos na mesma mão), sem pausas duplicadas
    desnecessárias, com cruzamento de mãos
  • Etapa 8 — Preview PNG: geração de imagem raster da partitura via
    LilyPond --png, para exibição na GUI sem abrir PDF

Requer: abjad >= 3.20, LilyPond instalado localmente

Autor: Ivan Simurra / NICS-UNICAMP
"""

from __future__ import annotations

import os
import subprocess
from fractions import Fraction
from typing import Optional

import abjad

from note_event import (
    NoteEvent,
    TupletGroup,
    EventSequence,
    InstrumentConfig,
    ExtendedTechnique,
    ArticulationType,
    HairpinType,
    GlissandoType,
    SlurRole,
    get_instrument,
    INSTRUMENT_CATALOG,
)

# Mapa auxiliar: instrument_id -> drum_note_name (pré-computado para velocidade)
_DRUM_NOTE_MAP: dict = {
    k: v.drum_note_name
    for k, v in INSTRUMENT_CATALOG.items()
    if v.is_percussion and v.drum_note_name
}


# ---------------------------------------------------------------------------
# Mapeamento de durações
# ---------------------------------------------------------------------------

DUR_TO_LILY: dict = {
    (1,32):"32", (1,16):"16", (3,16):"8.",
    (1,8):"8",   (3,8):"4.",  (1,4):"4",
    (3,4):"2.",  (1,2):"2",   (3,2):"1.", (1,1):"1",
}

BEATS_TO_DUR_PAIR: dict = {
    0.125:(1,32), 0.25:(1,16), 0.375:(3,16),
    0.5:(1,8),    0.75:(3,8),  1.0:(1,4),
    1.5:(3,8),    2.0:(1,2),   3.0:(3,4),
    4.0:(1,1),    6.0:(3,2),
}


def beats_to_lily_dur(beats: float) -> str:
    key = round(beats, 4)
    if key in BEATS_TO_DUR_PAIR:
        return DUR_TO_LILY.get(BEATS_TO_DUR_PAIR[key], "4")
    for b, pair in BEATS_TO_DUR_PAIR.items():
        if abs(b - beats) < 0.01:
            return DUR_TO_LILY.get(pair, "4")
    frac = Fraction(beats / 4).limit_denominator(32)
    pair = (frac.numerator, frac.denominator)
    return DUR_TO_LILY.get(pair, "4")


# ---------------------------------------------------------------------------
# Conversão MIDI → string de altura LilyPond
# ---------------------------------------------------------------------------

# Tabelas de normalização enarmônica para microtonalismo
# (evita duplos-acidentes como csqf, efqs)
_SHARP_UP   = {"cs":"d","ds":"e","es":"f","fs":"g","gs":"a","as":"b","bs":"c"}
_SHARP_DOWN = {"cs":"c","ds":"d","es":"e","fs":"f","gs":"g","as":"a","bs":"b"}
_FLAT_UP    = {"cf":"c","df":"d","ef":"e","ff":"f","gf":"g","af":"a","bf":"b"}
_FLAT_DOWN  = {"cf":"b","df":"c","ef":"d","ff":"e","gf":"f","af":"g","bf":"a"}


def midi_to_pitch_str(midi: int, microtone: float = 0.0) -> str:
    """MIDI + offset microtonal → string de altura LilyPond."""
    abjad_num = midi - 60
    base = abjad.NamedPitch(abjad.NumberedPitch(abjad_num))
    raw = repr(base)[len("NamedPitch("):-1]
    base_str = raw[1:-1]

    if abs(microtone) < 0.05:
        return base_str

    note_part = ""
    octave_part = ""
    for ch in base_str:
        if ch in ("'", ","):
            octave_part += ch
        else:
            note_part += ch

    is_sharp = len(note_part) == 2 and note_part[1] == "s"
    is_flat  = len(note_part) == 2 and note_part[1] == "f"

    if abs(microtone - 0.5) < 0.05:
        if is_sharp:  note_part = _SHARP_UP.get(note_part, note_part[0])
        elif is_flat: note_part = _FLAT_UP.get(note_part, note_part[0])
        suffix = "qs"
    elif abs(microtone + 0.5) < 0.05:
        if is_sharp:  note_part = _SHARP_DOWN.get(note_part, note_part[0])
        elif is_flat: note_part = _FLAT_DOWN.get(note_part, note_part[0])
        suffix = "qf"
    elif abs(microtone - 0.25) < 0.05:
        suffix = "es"
    elif abs(microtone + 0.25) < 0.05:
        suffix = "ef"
    else:
        suffix = "qs" if microtone > 0 else "qf"

    return note_part + suffix + octave_part


# ---------------------------------------------------------------------------
# Indicadores
# ---------------------------------------------------------------------------

# Técnicas como Markup ANEXADO à nota com direction=DOWN.
# abjad.attach(Markup, leaf, direction=DOWN) gera: nota _ markup
# NUNCA usa LilyPondLiteral site='before' para markup de texto:
# isso falha quando a nota com técnica é a primeira (markup aparece
# entre \clef/\time e a nota, causando 'markup outside text script').
TECHNIQUE_MARKUPS: dict = {
    # Strings incluem \markup { } explicitamente porque abjad.Markup
    # não adiciona o prefixo \markup automaticamente.
    ExtendedTechnique.SUL_PONTICELLO: r'\markup { \italic "sul pont." }',
    ExtendedTechnique.SUL_TASTO:      r'\markup { \italic "sul tasto" }',
    ExtendedTechnique.COL_LEGNO:      r'\markup { \italic "col legno" }',
    ExtendedTechnique.MULTIPHONIC:    r'\markup { \circle \finger "M" }',
    ExtendedTechnique.ORDINARIO:      r'\markup { \italic "ord." }',
}
# Técnicas pós-nota: LilyPondLiteral site='after' (sempre válido)
TECHNIQUE_POST_LITERALS: dict = {
    ExtendedTechnique.HARMONICS:      r'\flageolet',
    ExtendedTechnique.SNAP_PIZZICATO: r'\snappizzicato',
}
TECHNIQUE_LITERALS: dict = {}  # mantido para compatibilidade

ARTICULATION_MAP: dict = {
    ArticulationType.ACCENT:        "accent",
    ArticulationType.STACCATO:      "staccato",
    ArticulationType.TENUTO:        "tenuto",
    ArticulationType.MARCATO:       "marcato",
    ArticulationType.STACCATISSIMO: "staccatissimo",
    ArticulationType.PORTATO:       "portato",
}

VALID_DYNAMICS = {"ppp","pp","p","mp","mf","f","ff","fff","fp","sfz","sff","rfz"}

HAIRPIN_SHAPES: dict = {
    HairpinType.CRESCENDO:   "<",
    HairpinType.DECRESCENDO: ">",
    HairpinType.NIENTE_IN:   "o<",
    HairpinType.NIENTE_OUT:  ">o",
}

CLEF_NAMES: dict = {
    "treble":"treble","bass":"bass","alto":"alto",
    "tenor":"tenor","percussion":"percussion","treble_8":"treble_8",
}


# ---------------------------------------------------------------------------
# AbjadEngine  v2
# ---------------------------------------------------------------------------


# ─── Automatic system breaks ─────────────────────────────────────────────────

def _estimate_measure_width_mm(ts_str: str, staff_size: int = 11) -> float:
    """
    Estima a largura em mm de um compasso com a fórmula ts_str.
    Baseado no tamanho do staff e na quantidade de beats.
    """
    from fractions import Fraction as _Fr
    try:
        num, den = map(int, ts_str.split("/"))
    except Exception:
        return 30.0  # fallback
    beats = float(_Fr(num) * _Fr(4, den))
    ss = staff_size * 0.353 / 4          # staff-space em mm
    note_width  = beats * 7.0 * ss       # ~7 staff-spaces por beat
    overhead    = 9.0 * ss               # barra + padding
    return note_width + overhead


def _compute_break_positions(
    ts_sequence: list,
    staff_size: int = 11,
    paper_width_mm: float = 210.0,
    left_margin_mm: float = 15.0,
    right_margin_mm: float = 15.0,
    indent_mm: float = 20.0,
    short_indent_mm: float = 8.0,
) -> list:
    """
    Calcula os índices de SEÇÃO (mudanças de fórmula de compasso) antes dos quais
    inserir \\break. Trabalha com seções porque o LilyPond só emite \\time
    quando a fórmula muda — compassos com a mesma fórmula consecutiva não geram
    novo \\time no output.

    Retorna lista de índices de seção (0-based) onde \\break deve preceder o \\time.
    Seção 0 = primeiro \\time (sempre na voz, sem break antes).
    """
    from fractions import Fraction as _Fr

    if not ts_sequence:
        return []

    # Agrupa ts_sequence em seções (grupos de compassos com a mesma fórmula)
    sections = []   # [(ts_str, n_measures)]
    prev = None
    count = 0
    for ts in ts_sequence:
        if ts == prev:
            count += 1
        else:
            if prev:
                sections.append((prev, count))
            prev = ts
            count = 1
    if prev:
        sections.append((prev, count))

    usable      = paper_width_mm - left_margin_mm - right_margin_mm
    line_first  = usable - indent_mm
    line_others = usable - short_indent_mm

    breaks_sections = []    # índices de seção (para reak antes de 	ime)
    intra_breaks = {}       # seção → lista de offsets de medida (para reak dentro da seção)
    accumulated = 0.0
    current_limit = line_first

    for i, (ts, n_measures) in enumerate(sections):
        measure_w = _estimate_measure_width_mm(ts, staff_size)
        section_w = measure_w * n_measures

        if accumulated + section_w > current_limit and accumulated > 0:
            if i > 0:
                breaks_sections.append(i)
            # Verifica se mesmo a seção sozinha excede o limite
            # (grupo longo da mesma fórmula de compasso)
            accumulated = 0.0
            current_limit = line_others

        # Dentro desta seção, verifica se há overflow intra-seção
        intra = []
        acc_in = accumulated
        for j in range(n_measures):
            if acc_in + measure_w > current_limit and acc_in > 0:
                intra.append(j)      # break antes da medida j desta seção
                acc_in = measure_w
                current_limit = line_others
            else:
                acc_in += measure_w
        if intra:
            intra_breaks[i] = intra
        accumulated = acc_in

    return breaks_sections, intra_breaks


def _insert_system_breaks(ly_str: str, ts_sequence: list, staff_size: int = 11) -> str:
    """
    Insere comandos \break no LilyPond string gerado pelo Abjad.

    Apenas na PRIMEIRA pauta — no contexto Score, \break propaga para todas as pautas.

    Dois tipos de quebras são inseridos:
      1. INTER-seção: \break antes de \time X/Y quando a seção nova causaria overflow.
      2. INTRA-seção: \break em posições absolutas dentro de seções longas (mesmo \time).
         Para intra-seção, usamos \bar "" \break que não exige \time para ancorar.
    """
    import re as _re

    if not ts_sequence:
        return ly_str

    result = _compute_break_positions(ts_sequence, staff_size=staff_size)
    if isinstance(result, tuple):
        breaks_sections, intra_breaks = result
    else:
        breaks_sections, intra_breaks = list(result), {}

    # Localiza a primeira voz
    first_voice_start = ly_str.find(r'\context Voice')
    if first_voice_start < 0:
        return ly_str

    next_staff = ly_str.find(r'\context Staff', first_voice_start + 1)
    if next_staff < 0:
        next_staff = len(ly_str)
    first_voice_block = ly_str[first_voice_start:next_staff]

    # Encontra \time commands na primeira voz
    time_matches = list(_re.finditer(r'\\time \d+/\d+', first_voice_block))
    if len(time_matches) < 1:
        return ly_str

    # === Parte 1: breaks inter-seção (antes de \time) ===
    inter_positions = []
    for b in breaks_sections:
        if 0 < b < len(time_matches):
            abs_pos = first_voice_start + time_matches[b].start()
            inter_positions.append(abs_pos)

    # === Parte 2: breaks intra-seção ===
    # Para cada seção com intra_breaks, encontramos as notas dentro da seção
    # e inserimos \break após a N-ésima nota (usando posição de barlines implícitas).
    # Estratégia simplificada: calcular quantas notas/eventos por medida média
    # e inserir \break após N medidas estimadas dentro da seção.
    # 
    # Abordagem prática: usar os \time da seção para localizar o início,
    # depois contar eventos para estimar posições de compasso.
    # Para simplificar, usamos uma abordagem por contagem de eventos.
    
    intra_positions = []
    
    # Reconstrói seções a partir de ts_sequence
    sections_list = []
    prev_ts = None; count = 0
    for ts in ts_sequence:
        if ts == prev_ts: count += 1
        else:
            if prev_ts: sections_list.append((prev_ts, count))
            prev_ts = ts; count = 1
    if prev_ts: sections_list.append((prev_ts, count))

    for sec_idx, intra_list in intra_breaks.items():
        if sec_idx >= len(time_matches):
            continue
        # Posição absoluta do início desta seção
        sec_start_abs = first_voice_start + time_matches[sec_idx].start()
        # Posição absoluta do fim desta seção (início da próxima \time ou fim do bloco)
        if sec_idx + 1 < len(time_matches):
            sec_end_abs = first_voice_start + time_matches[sec_idx + 1].start()
        else:
            sec_end_abs = first_voice_start + len(first_voice_block)

        sec_block = ly_str[sec_start_abs:sec_end_abs]
        n_measures = sections_list[sec_idx][1] if sec_idx < len(sections_list) else 1

        # Distribui as quebras intra uniformemente dentro da seção
        for intra_measure_offset in intra_list:
            # Fração da seção onde esta quebra ocorre
            frac = intra_measure_offset / n_measures
            # Posição aproximada em chars dentro da seção
            approx_char = int(len(sec_block) * frac)
            # Recua até o fim da linha mais próxima
            line_end = sec_block.find('\n', approx_char)
            if line_end < 0:
                line_end = len(sec_block) - 1
            abs_break_pos = sec_start_abs + line_end + 1
            intra_positions.append(abs_break_pos)

    # === Combina e ordena TODAS as posições de inserção ===
    all_positions = sorted(set(inter_positions + intra_positions), reverse=True)

    if not all_positions:
        return ly_str

    # Insere de trás para frente para não invalidar posições anteriores
    pieces = []
    prev = len(ly_str)
    for abs_pos in all_positions:
        # Indentação da linha que contém o ponto de inserção
        line_start = ly_str.rfind('\n', 0, abs_pos) + 1
        line_indent = abs_pos - line_start

        # Se indent=0 (ex: \time dentro de \tuplet sai em col 0 pelo Abjad),
        # usa a indentação da última linha de conteúdo significativa antes deste ponto.
        if line_indent == 0:
            search = line_start - 1
            while search > 0:
                pl_end   = search
                pl_start = ly_str.rfind('\n', 0, pl_end) + 1
                pl_text  = ly_str[pl_start:pl_end]
                stripped = pl_text.lstrip()
                il = len(pl_text) - len(stripped)
                if stripped and not stripped.startswith('\\time') and il > 0:
                    line_indent = il
                    break
                search = pl_start - 1
            line_indent = max(line_indent, 12)

        indent = ' ' * line_indent
        pieces.append(ly_str[abs_pos:prev])
        pieces.append(indent + '\\break\n')
        prev = abs_pos

    pieces.append(ly_str[:prev])
    return ''.join(reversed(pieces))

class AbjadEngine:
    """
    Motor de notação Abjad.

    Novidades v2
    ------------
    - Tuplas simples e aninhadas via TupletGroup
    - Grand staff piano com divisão por registro (hysteresis de 4 semitons)
    - Geração de PNG preview via LilyPond --png
    """

    def __init__(
        self,
        title: str = "Composição",
        composer_name: str = "GrammarComposer",
        use_proportional: bool = False,
        proportional_moment: str = "1/16",
        lilypond_path: Optional[str] = None,
        paper_size: str = "a4",
        # Grand staff
        piano_split_midi: int = 60,       # nota de divisão padrão
        piano_split_hysteresis: int = 4,  # semitons de histerese (evita troca a cada nota)
    ):
        self.title = title
        self.composer_name = composer_name
        self.use_proportional = use_proportional
        self.proportional_moment = proportional_moment
        self.lilypond_path = lilypond_path
        self.paper_size = paper_size
        self.piano_split_midi = piano_split_midi
        self.piano_split_hysteresis = piano_split_hysteresis

        self._score: Optional[abjad.Score] = None
        self._has_microtones: bool = False

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def build_score(self, sequences: list) -> abjad.Score:
        self._has_microtones = False
        self._needs_proportional_layout = False
        self._has_wavy_glissando = False
        # Extrai a sequência de fórmulas de compasso da primeira EventSequence
        # para uso posterior no cálculo de quebras de sistema.
        if sequences:
            self._ts_sequence_for_breaks = getattr(
                sequences[0], "time_sig_sequence", []
            )
        staves = []
        for seq in sequences:
            cfg = get_instrument(seq.instrument_id)
            if cfg and cfg.is_percussion:
                # Percussão sem altura → DrumStaff
                staves.append(self._build_drum_staff(seq, cfg))
            elif cfg and cfg.staff_count == 2:
                # Grand staff (piano/cravo)
                staves.append(self._build_grand_staff(seq, cfg))
            else:
                # Pauta normal (altura definida)
                staves.append(self._build_staff(seq, cfg))
        self._score = abjad.Score(staves, name="Score")
        self._n_staves = len(staves)
        self._apply_global_overrides()
        return self._score

    def to_lilypond_string(self) -> str:
        if self._score is None:
            raise RuntimeError("Chame build_score() antes de to_lilypond_string().")
        raw = (
            self._build_header_block()
            + "\n" + self._build_paper_block()
            + "\n" + self._build_layout_block()
            + "\n" + abjad.lilypond(self._score)
            + "\n"
        )
        # Insere \break automático para forçar quebras de sistema
        # dentro das margens da página A4.
        ts_seq = getattr(self, "_ts_sequence_for_breaks", [])
        staff_size = getattr(self, "_current_staff_size", 11)
        if ts_seq:
            raw = _insert_system_breaks(raw, ts_seq, staff_size=staff_size)
        return raw

    def save_ly(self, filepath: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_lilypond_string())
        print(f"[AbjadEngine] .ly salvo: {filepath}")
        return filepath

    def save_pdf(self, filepath: str) -> Optional[str]:
        base = os.path.splitext(filepath)[0]
        ly_path = base + ".ly"
        self.save_ly(ly_path)
        return self._run_lilypond(base, ly_path, extra_flags=[])

    def save_png(self, filepath: str, dpi: int = 150) -> Optional[str]:
        """
        Etapa 8 — Preview PNG.
        Gera imagem raster (uma .png por página) via LilyPond --png.
        Retorna o caminho do primeiro PNG gerado, ou None em caso de erro.
        """
        base = os.path.splitext(filepath)[0]
        ly_path = base + ".ly"
        self.save_ly(ly_path)
        result = self._run_lilypond(
            base, ly_path,
            extra_flags=["--png", f"-dresolution={dpi}"]
        )
        if result:
            # LilyPond gera base.png (1 página) ou base-1.png, base-2.png, …
            for candidate in [base + ".png", base + "-1.png"]:
                if os.path.exists(candidate):
                    print(f"[AbjadEngine] PNG gerado: {candidate}")
                    return candidate
        return None

    # ------------------------------------------------------------------
    # Pautas simples
    # ------------------------------------------------------------------

    def _build_staff(self, seq: EventSequence, cfg: Optional[InstrumentConfig]) -> abjad.Staff:
        items = self._build_leaf_list(seq.events)
        voice = abjad.Voice(items, name=f"Voice_{seq.instrument_id}")
        staff = abjad.Staff([voice], name=f"Staff_{seq.instrument_id}")

        all_leaves = list(abjad.iterate.leaves(staff))
        first_leaf = all_leaves[0] if all_leaves else None

        if cfg and first_leaf:
            abjad.attach(abjad.Clef(CLEF_NAMES.get(cfg.clef, "treble")), first_leaf)

        if cfg:
            abjad.setting(staff).instrument_name = rf"\markup {{ {cfg.name_full} }}"
            abjad.setting(staff).short_instrument_name = rf"\markup {{ {cfg.name_short} }}"

        prop = seq.use_proportional or self.use_proportional
        if prop and first_leaf:
            self._attach_proportional_overrides(first_leaf)
        elif first_leaf:
            # Insere fórmulas de compasso: usa sequência variável se disponível
            ts_seq = getattr(seq, "time_sig_sequence", [])
            if ts_seq:
                self._attach_time_sig_sequence(staff, ts_seq, seq.time_signature)
            else:
                abjad.attach(abjad.TimeSignature(seq.time_signature), first_leaf)

        return staff

    def _attach_time_sig_sequence(
        self, staff: abjad.Staff, ts_seq: list, default_ts: tuple,
    ) -> None:
        """
        Insere mudanças de \\time ao longo da pauta usando aritmetica Fraction.
        Os eventos sao gerados compasso a compasso com beats exatos,
        entao so precisamos inserir \\time quando a formula muda.
        """
        from fractions import Fraction
        all_leaves = list(abjad.iterate.leaves(staff))
        if not all_leaves:
            return

        def parse_ts(ts_str):
            try:
                n, d = map(int, ts_str.split('/'))
                return abjad.TimeSignature((n, d))
            except Exception:
                return abjad.TimeSignature(default_ts)

        def m_beats(ts_str):
            try:
                n, d = map(int, ts_str.split('/'))
                return Fraction(n) * Fraction(4, d)
            except Exception:
                return Fraction(default_ts[0]) * Fraction(4, default_ts[1])

        cur_ts   = ts_seq[0] if ts_seq else f'{default_ts[0]}/{default_ts[1]}'
        cur_frac = m_beats(cur_ts)
        try: abjad.attach(parse_ts(cur_ts), all_leaves[0])
        except Exception: pass

        m_idx      = 0
        beat_acc   = Fraction(0)
        last_ts    = cur_ts

        for leaf in all_leaves[1:]:
            try:
                leaf_beats = Fraction(abjad.get.duration(leaf)) * 4
            except Exception:
                leaf_beats = Fraction(1)

            beat_acc += leaf_beats

            # Advance measure(s)
            while beat_acc >= cur_frac:
                beat_acc -= cur_frac
                m_idx += 1
                if m_idx < len(ts_seq):
                    cur_ts   = ts_seq[m_idx]
                    cur_frac = m_beats(cur_ts)
                else:
                    break

            # Attach \time at start of new measure when sig changes
            if beat_acc == 0 and m_idx < len(ts_seq) and cur_ts != last_ts:
                try:
                    abjad.attach(parse_ts(cur_ts), leaf)
                    last_ts = cur_ts
                except Exception:
                    pass

        def parse_ts(ts_str: str) -> abjad.TimeSignature:
            try:
                num, den = map(int, ts_str.split("/"))
                return abjad.TimeSignature((num, den))
            except Exception:
                return abjad.TimeSignature(default_ts)

        def measure_beats(ts_str: str) -> float:
            """Duração em quarter-beats (c'4 = 1.0)."""
            try:
                num, den = map(int, ts_str.split("/"))
                return num * (4.0 / den)
            except Exception:
                return float(default_ts[0]) * (4.0 / default_ts[1])

        current_ts_str = ts_seq[0] if ts_seq else f"{default_ts[0]}/{default_ts[1]}"
        try:
            abjad.attach(parse_ts(current_ts_str), all_leaves[0])
        except Exception:
            pass

        measure_idx = 0
        beat_in_measure = 0.0
        current_measure_dur = measure_beats(current_ts_str)

        for leaf in all_leaves[1:]:
            # abjad duration is in whole-note fractions → multiply by 4 for beats
            try:
                leaf_dur_beats = float(abjad.get.duration(leaf)) * 4.0
            except Exception:
                leaf_dur_beats = 1.0

            beat_in_measure += leaf_dur_beats

            # Avança compasso(s) quando a duração acumulada atinge o limite
            while beat_in_measure >= current_measure_dur - 0.001:
                beat_in_measure -= current_measure_dur
                measure_idx += 1
                if measure_idx >= len(ts_seq):
                    break
                current_ts_str = ts_seq[measure_idx]
                current_measure_dur = measure_beats(current_ts_str)

            # Insere 	ime quando a fórmula muda no início deste leaf
            if measure_idx < len(ts_seq):
                new_ts_str = ts_seq[measure_idx]
                # Só insere se for o exato início de um novo compasso
                if abs(beat_in_measure) < 0.001 and new_ts_str != getattr(leaf, '_last_ts', None):
                    try:
                        abjad.attach(parse_ts(new_ts_str), leaf)
                        leaf._last_ts = new_ts_str
                    except Exception:
                        pass


    # ------------------------------------------------------------------
    # Percussão sem altura — DrumStaff (imagens de referência notação)
    # ------------------------------------------------------------------

    def _build_drum_staff(
        self, seq: EventSequence, cfg: Optional[InstrumentConfig]
    ) -> abjad.Staff:
        """
        Constrói um DrumStaff com DrumVoice para percussão sem altura.

        Notação conforme as imagens de referência:
          • Notas normais (preenchidas): caixa, bumbo, toms
          • Notas em ×: pratos (crash, ride, hi-hat)
          • Notas em ∆ (diamond): ride bell
          • Notas com ∧ (aberto): prato China, splash
          — Tudo é gerenciado automaticamente pelo LilyPond via drummode.

        Suporta dinâmicas, articulações, hairpins, tuplas e ligaduras.
        NÃO usa TimeSignature via abjad.attach (contexto incompatível);
        usa LilyPondLiteral em vez disso.
        """
        items = self._build_drum_leaf_list(seq.events, cfg)

        voice = abjad.Voice(items, lilypond_type="DrumVoice",
                            name=f"DrumVoice_{seq.instrument_id}")
        staff = abjad.Staff([voice], lilypond_type="DrumStaff",
                            name=f"DrumStaff_{seq.instrument_id}")

        # Nome do instrumento
        if cfg:
            abjad.setting(staff).instrument_name = (
                rf"\markup {{ {cfg.name_full} }}"
            )
            abjad.setting(staff).short_instrument_name = (
                rf"\markup {{ {cfg.name_short} }}"
            )

        # TimeSignature como LilyPondLiteral (abjad.attach não funciona em DrumVoice)
        all_leaves = list(abjad.iterate.leaves(staff))
        first_leaf = all_leaves[0] if all_leaves else None
        if first_leaf:
            prop = seq.use_proportional or self.use_proportional
            if not prop:
                num, den = seq.time_signature
                abjad.attach(
                    abjad.LilyPondLiteral(
                        rf"\time {num}/{den}", site="before"
                    ),
                    first_leaf,
                )
            else:
                # Proporcional: remove barras e compassos
                for ov in [
                    r"\omit Staff.BarLine",
                    r"\omit Staff.TimeSignature",
                    r"\override Staff.BarNumber.transparent = ##t",
                    r"\override SpacingSpanner.uniform-stretching = ##t",
                ]:
                    try:
                        abjad.attach(
                            abjad.LilyPondLiteral(ov, site="before"),
                            first_leaf,
                        )
                    except Exception:
                        pass
                self._needs_proportional_layout = True

        return staff

    def _build_drum_leaf_list(
        self, items: list, cfg: Optional[InstrumentConfig]
    ) -> list:
        """Converte NoteEvent / TupletGroup em folhas para DrumVoice."""
        result = []
        for item in items:
            if isinstance(item, TupletGroup):
                tuplet = self._drum_tuplet_to_abjad(item, cfg)
                if tuplet is not None:
                    result.append(tuplet)
            elif isinstance(item, NoteEvent):
                if item.is_chord_note:
                    continue
                leaf = self._event_to_drum_leaf(item, cfg)
                if leaf is None:
                    continue
                self._attach_all_indicators(leaf, item)
                result.append(leaf)
        return result

    def _drum_tuplet_to_abjad(
        self, tg: TupletGroup, cfg: Optional[InstrumentConfig]
    ) -> Optional[abjad.Tuplet]:
        inner = self._build_drum_leaf_list(tg.events, cfg)
        if not inner:
            return None
        ratio_str = f"{tg.n}:{tg.d}"
        try:
            tuplet = abjad.Tuplet(ratio_str, inner)
        except Exception as e:
            print(f"[AbjadEngine] Drum Tuplet inválido '{ratio_str}': {e}")
            return None
        if not tg.show_bracket:
            abjad.override(tuplet).TupletBracket.stencil = False
        if not tg.show_number:
            abjad.override(tuplet).TupletNumber.stencil = False
        return tuplet

    def _event_to_drum_leaf(
        self, event: NoteEvent, cfg: Optional[InstrumentConfig]
    ):
        """
        Converte NoteEvent em Note de percussão (LilyPond drummode).

        Resolução do nome de nota:
          1. event.drum_instrument  (sobrescreve para bateria multi-sons)
          2. cfg.drum_note_name     (padrão do instrumento)
          3. "snare"                (fallback)
        """
        dur = beats_to_lily_dur(event.duration_beats)

        if event.is_rest:
            return abjad.Rest(f"r{dur}")

        # Determina o nome da nota de percussão
        if event.drum_instrument:
            drum_name = event.drum_instrument
        elif cfg and cfg.drum_note_name:
            drum_name = cfg.drum_note_name
        else:
            drum_name = "snare"

        note_str = drum_name + dur
        try:
            return abjad.Note(note_str)
        except Exception as e:
            print(f"[AbjadEngine] Drum note inválida '{note_str}': {e}")
            return abjad.Rest(f"r{dur}")

    # ------------------------------------------------------------------
    # Etapa 7 — Grand staff refinado
    # ------------------------------------------------------------------

    def _build_grand_staff(self, seq: EventSequence, cfg: InstrumentConfig) -> abjad.StaffGroup:
        """
        Divide os eventos do piano em mão direita / esquerda usando histerese.
        O split point começa em piano_split_midi; só muda de mão quando uma
        nota está além da histerese, evitando trocas de mão a cada nota.
        """
        upper_events: list = []
        lower_events: list = []
        current_hand = "upper"  # mão inicial

        for event in seq:
            if isinstance(event, TupletGroup):
                # Grupo de tupla: decide pela nota de maior tessitura
                rep_midi = self._tuplet_representative_pitch(event)
                hand = self._grand_staff_hand(rep_midi, current_hand)
                current_hand = hand
                if hand == "upper":
                    upper_events.append(event)
                    lower_events.append(NoteEvent.rest(event.total_beats))
                else:
                    lower_events.append(event)
                    upper_events.append(NoteEvent.rest(event.total_beats))
                continue

            if event.is_rest:
                upper_events.append(event)
                lower_events.append(NoteEvent.rest(event.duration_beats))
                continue

            hand = self._grand_staff_hand(event.pitch_midi, current_hand)
            current_hand = hand
            if hand == "upper":
                upper_events.append(event)
                lower_events.append(NoteEvent.rest(event.duration_beats))
            else:
                lower_events.append(event)
                upper_events.append(NoteEvent.rest(event.duration_beats))

        # Simplifica pausas consecutivas em cada mão
        upper_events = self._merge_consecutive_rests(upper_events)
        lower_events = self._merge_consecutive_rests(lower_events)

        def _make_seq(events, suffix, clef_str):
            s = EventSequence(
                instrument_id=seq.instrument_id + suffix,
                events=events,
                tempo_bpm=seq.tempo_bpm,
                time_signature=seq.time_signature,
                use_proportional=seq.use_proportional,
            )
            # Cria config temporária com a clave correta
            import copy
            c = copy.copy(cfg)
            c.instrument_id = seq.instrument_id + suffix
            c.clef = clef_str
            c.name_full = cfg.name_full
            c.name_short = cfg.name_short
            return s, c

        seq_upper, cfg_upper = _make_seq(upper_events, "_upper", "treble")
        seq_lower, cfg_lower = _make_seq(lower_events, "_lower", cfg.secondary_clef)

        staff_upper = self._build_staff(seq_upper, cfg_upper)
        staff_lower = self._build_staff(seq_lower, cfg_lower)

        # Remove nome duplicado da pauta inferior
        abjad.setting(staff_lower).instrument_name = r"\markup { }"
        abjad.setting(staff_lower).short_instrument_name = r"\markup { }"

        group = abjad.StaffGroup(
            [staff_upper, staff_lower],
            lilypond_type="PianoStaff",
            name=f"PianoStaff_{seq.instrument_id}",
        )
        abjad.setting(group).instrument_name = rf"\markup {{ {cfg.name_full} }}"
        abjad.setting(group).short_instrument_name = rf"\markup {{ {cfg.name_short} }}"
        return group

    def _grand_staff_hand(self, pitch_midi: Optional[int], current_hand: str) -> str:
        """
        Decide a mão com base no split point + histerese.
        Só muda de mão se a nota ultrapassar a zona de histerese.
        """
        if pitch_midi is None:
            return current_hand
        split = self.piano_split_midi
        hys   = self.piano_split_hysteresis
        if current_hand == "upper":
            # Muda para lower só se bem abaixo do split
            return "lower" if pitch_midi < (split - hys) else "upper"
        else:
            # Muda para upper só se bem acima do split
            return "upper" if pitch_midi >= (split + hys) else "lower"

    @staticmethod
    def _tuplet_representative_pitch(tg: TupletGroup) -> Optional[int]:
        """Retorna o pitch MIDI médio das notas soantes de um TupletGroup."""
        pitches = []
        def _collect(items):
            for e in items:
                if isinstance(e, NoteEvent) and not e.is_rest:
                    pitches.append(e.pitch_midi)
                elif isinstance(e, TupletGroup):
                    _collect(e.events)
        _collect(tg.events)
        return int(sum(pitches) / len(pitches)) if pitches else None

    @staticmethod
    def _merge_consecutive_rests(events: list) -> list:
        """Une pausas consecutivas numa pausa de duração somada."""
        result = []
        for ev in events:
            if (isinstance(ev, NoteEvent) and ev.is_rest
                    and result
                    and isinstance(result[-1], NoteEvent)
                    and result[-1].is_rest):
                merged = NoteEvent.rest(result[-1].duration_beats + ev.duration_beats)
                result[-1] = merged
            else:
                result.append(ev)
        return result

    # ------------------------------------------------------------------
    # Etapa 6 — Construção de folhas com TupletGroup
    # ------------------------------------------------------------------

    def _build_leaf_list(self, items: list) -> list:
        """
        Converte recursivamente uma lista de NoteEvent / TupletGroup
        em folhas Abjad (Note, Rest, Chord) ou Tuplet.
        """
        result = []
        for item in items:
            if isinstance(item, TupletGroup):
                tuplet = self._tuplet_to_abjad(item)
                if tuplet is not None:
                    result.append(tuplet)
            elif isinstance(item, NoteEvent):
                if item.is_chord_note:
                    continue
                leaf = self._event_to_leaf(item)
                if leaf is None:
                    continue
                self._attach_all_indicators(leaf, item)
                result.append(leaf)
        return result

    def _tuplet_to_abjad(self, tg: TupletGroup) -> Optional[abjad.Tuplet]:
        """
        Converte TupletGroup em abjad.Tuplet, com suporte a aninhamento.
        """
        inner_items = self._build_leaf_list(tg.events)
        if not inner_items:
            return None

        ratio_str = f"{tg.n}:{tg.d}"
        try:
            tuplet = abjad.Tuplet(ratio_str, inner_items)
        except Exception as e:
            print(f"[AbjadEngine] Tuplet inválido '{ratio_str}': {e}")
            return None

        # Esconde colchete / número se solicitado
        if not tg.show_bracket:
            abjad.override(tuplet).TupletBracket.stencil = False
        if not tg.show_number:
            abjad.override(tuplet).TupletNumber.stencil = False

        return tuplet

    def _event_to_leaf(self, event: NoteEvent):
        dur = beats_to_lily_dur(event.duration_beats)
        if event.is_rest:
            return abjad.Rest(f"r{dur}")
        if event.chord_members:
            pitches = [midi_to_pitch_str(event.pitch_midi, event.microtone_offset)]
            for m in event.chord_members:
                pitches.append(midi_to_pitch_str(m, 0.0))
            chord_str = "<" + " ".join(pitches) + ">" + dur
            try:
                return abjad.Chord(chord_str)
            except Exception as e:
                print(f"[AbjadEngine] Chord inválido '{chord_str}': {e}")
                return abjad.Rest(f"r{dur}")
        pitch_str = midi_to_pitch_str(event.pitch_midi, event.microtone_offset)
        if event.has_microtone:
            self._has_microtones = True
        note_str = pitch_str + dur
        try:
            return abjad.Note(note_str)
        except Exception as e:
            print(f"[AbjadEngine] Nota inválida '{note_str}': {e}")
            return abjad.Rest(f"r{dur}")

    # ------------------------------------------------------------------
    # Indicadores
    # ------------------------------------------------------------------

    def _attach_all_indicators(self, leaf, event: NoteEvent) -> None:
        """
        Anexa indicadores ao leaf Abjad.

        Pausas (abjad.Rest) não aceitam markup textual nem articulações
        em LilyPond 2.24 — LilyPond rejeita com 'markup outside text script'.
        Dinâmicas e hairpins são válidos em pausas e permanecem ativos.
        """
        is_rest = isinstance(leaf, abjad.Rest)

        self._attach_dynamic(leaf, event)
        self._attach_hairpin_start(leaf, event)
        self._attach_hairpin_end(leaf, event)

        if not is_rest:
            self._attach_technique(leaf, event)
            self._attach_articulation(leaf, event)
            self._attach_glissando(leaf, event)
            self._attach_slur_start(leaf, event)
            self._attach_slur_end(leaf, event)

        self._attach_tie(leaf, event)
        self._attach_custom(leaf, event)


    def _attach_dynamic(self, leaf, event):
        if event.dynamic and event.dynamic in VALID_DYNAMICS:
            try: abjad.attach(abjad.Dynamic(event.dynamic), leaf)
            except Exception: pass

    def _attach_hairpin_start(self, leaf, event):
        shape = HAIRPIN_SHAPES.get(event.hairpin)
        if shape:
            try: abjad.attach(abjad.StartHairpin(shape), leaf)
            except Exception: pass

    def _attach_hairpin_end(self, leaf, event):
        if event.hairpin_end:
            try: abjad.attach(abjad.StopHairpin(), leaf)
            except Exception: pass

    def _attach_technique(self, leaf, event):
        if event.technique == ExtendedTechnique.NORMAL: return

        # Flutter tongue: StemTremolo gera nota:32 (tremolo LilyPond nativo)
        if event.technique == ExtendedTechnique.FLUTTER_TONGUE:
            try: abjad.attach(abjad.StemTremolo(32), leaf)
            except Exception: pass
            return

        # Técnicas pós-nota: LilyPondLiteral site='after' (sempre válido)
        post = TECHNIQUE_POST_LITERALS.get(event.technique)
        if post:
            try: abjad.attach(abjad.LilyPondLiteral(post, site='after'), leaf)
            except Exception: pass
            return

        # Técnicas de texto: Markup ANEXADO à nota com direction=DOWN.
        # Gera: nota _ \markup { ... }  — válido em qualquer posição,
        # inclusive quando a nota é a primeira da pauta (com \clef/\time antes).
        markup_str = TECHNIQUE_MARKUPS.get(event.technique)
        if markup_str:
            try:
                abjad.attach(abjad.Markup(markup_str), leaf, direction=abjad.DOWN)
            except Exception: pass

    def _attach_articulation(self, leaf, event):
        art = ARTICULATION_MAP.get(event.articulation)
        if art:
            try: abjad.attach(abjad.Articulation(art), leaf)
            except Exception: pass

    def _attach_glissando(self, leaf, event):
        if event.glissando == GlissandoType.NONE: return
        if event.glissando == GlissandoType.WAVY:
            # Registra que o score usa zigzag; o override vai para o \\layout
            # uma única vez, não repetido por nota (evita explosão de espaço horizontal)
            self._has_wavy_glissando = True
        try: abjad.attach(abjad.Glissando(), leaf)
        except Exception: pass

    def _attach_slur_start(self, leaf, event):
        if event.slur in (SlurRole.START, SlurRole.MIDDLE):
            try: abjad.attach(abjad.StartSlur(), leaf)
            except Exception: pass

    def _attach_slur_end(self, leaf, event):
        if event.slur == SlurRole.END:
            try: abjad.attach(abjad.StopSlur(), leaf)
            except Exception: pass

    def _attach_tie(self, leaf, event):
        if event.tie:
            try: abjad.attach(abjad.Tie(), leaf)
            except Exception: pass

    def _attach_custom(self, leaf, event):
        if event.custom_lilypond:
            try: abjad.attach(abjad.LilyPondLiteral(
                event.custom_lilypond, site="before"), leaf)
            except Exception: pass

    # ------------------------------------------------------------------
    # Notação proporcional
    # ------------------------------------------------------------------

    def _attach_proportional_overrides(self, first_leaf) -> None:
        """
        Overrides válidos DENTRO de \\Staff.
        NOTA: \\proportionalNotationDuration NÃO pode ser um LilyPondLiteral
        dentro de Staff — pertence ao bloco \\layout{\\context{\\Score}}.
        Esse ajuste é feito por _build_layout_block() quando
        _needs_proportional_layout == True.
        """
        for ov in [
            r"\omit Staff.BarLine",
            r"\omit Staff.TimeSignature",
            r"\override Staff.BarNumber.transparent = ##t",
            r"\override SpacingSpanner.uniform-stretching = ##t",
        ]:
            try: abjad.attach(abjad.LilyPondLiteral(ov, site="before"), first_leaf)
            except Exception: pass
        self._needs_proportional_layout = True

    def _apply_global_overrides(self) -> None:
        """Registra necessidade de notação proporcional no layout (sem literal inválido)."""
        if self.use_proportional:
            self._needs_proportional_layout = True

    # ------------------------------------------------------------------
    # Blocos LilyPond
    # ------------------------------------------------------------------

    def _build_header_block(self) -> str:
        # \language "english" é obrigatório para que o LilyPond 2.24 reconheça
        # os nomes de notas com microtons (qs/qf) gerados pelo Abjad.
        # Sem ele: "not a note name: dqs" / "not a note name: dqf"
        return (f'\\version "2.24.0"\n'
                f'\\language "english"\n\n'
                f'\\header {{\n  title = "{self.title}"\n'
                f'  composer = "{self.composer_name}"\n  tagline = ##f\n}}\n')

    def _build_paper_block(self) -> str:
        n = getattr(self, '_n_staves', 1)
        if   n <= 1:  staff_size = 16
        elif n <= 2:  staff_size = 14
        elif n <= 3:  staff_size = 12
        elif n <= 5:  staff_size = 11
        elif n <= 8:  staff_size = 10
        else:         staff_size = 9
        indent       = 25 if n > 4 else 20
        short_indent = 12 if n > 4 else 8
        sys_basic    = max(6, 12 - n)
        sys_str      = 60
        mm = r'\mm'

        # IMPORTANTE: set-global-staff-size deve estar NO NIVEL TOP-LEVEL
        # (antes do \paper), nao dentro do bloco \paper.
        # Em LilyPond 2.24, colocar dentro de \paper gera:
        # 'set-global-staff-size: not in toplevel scope'
        # Por isso geramos o comando separado e o concatenamos antes do \paper.
        staff_size_cmd = f'#(set-global-staff-size {staff_size})\n\n'

        paper_block = '\n'.join([
            r'\paper {',
            f'  #(set-paper-size "{self.paper_size}" (quote portrait))',
            f'  paper-width = 210{mm}',
            f'  paper-height = 297{mm}',
            f'  top-margin = 12{mm}',
            f'  bottom-margin = 12{mm}',
            f'  left-margin = 15{mm}',
            f'  right-margin = 15{mm}',
            f'  indent = {indent}{mm}',
            f'  short-indent = {short_indent}{mm}',
            r'  ragged-right = ##f',
            r'  ragged-last = ##t',
            r'  ragged-bottom = ##f',
            r'  ragged-last-bottom = ##t',
            # CORRETO: ly:optimal-breaking (nao ly:optimal-page-breaks)
            # ly:optimal-page-breaks NAO EXISTE em LilyPond 2.24
            r'  page-breaking = #ly:optimal-breaking',
            f"  system-system-spacing = #'(",
            f'    (basic-distance . {sys_basic})',
            f'    (minimum-distance . 6)',
            f'    (padding . 3)',
            f'    (stretchability . {sys_str}))',
            f"  score-system-spacing = #'(",
            f'    (basic-distance . {sys_basic + 4})',
            f'    (minimum-distance . 8)',
            f'    (padding . 5)',
            f'    (stretchability . {sys_str}))',
            r'  last-bottom-spacing.basic-distance = #6',
            r'  last-bottom-spacing.minimum-distance = #4',
            r'  last-bottom-spacing.padding = #2',
            r'  last-bottom-spacing.stretchability = #80',
            r'}',
            '',
        ]) + '\n'

        self._current_staff_size = staff_size  # para uso em _insert_system_breaks
        return staff_size_cmd + paper_block

    def _build_layout_block(self) -> str:
        n = getattr(self, '_n_staves', 1)
        # Espacamento vertical entre pautas - maior para notacao densa
        staff_pad  = max(2, 6 - n)
        staff_min  = max(6, 12 - n)
        staff_bas  = max(8, 14 - n)

        layout = '\\layout {\n'

        # Score: espacamento horizontal e vertical global
        layout += (
            '  \\context {\n'
            '    \\Score\n'
            # Mais espaco horizontal por nota - essencial para notacao densa
            '    \\override SpacingSpanner.base-shortest-duration ='
            ' #(ly:make-moment 1/16)\n'
            # Espacamento vertical entre pautas no sistema
            '    \\override StaffGrouper.staff-staff-spacing =\n'
            f"      #'((basic-distance . {staff_bas})\n"
            f"        (minimum-distance . {staff_min})\n"
            f"        (padding . {staff_pad})\n"
            '        (stretchability . 60))\n'
            '    \\override StaffGrouper.staffgroup-staff-spacing =\n'
            f"      #'((basic-distance . {staff_bas + 4})\n"
            f"        (minimum-distance . {staff_min + 2})\n"
            f"        (padding . {staff_pad + 2})\n"
            '        (stretchability . 40))\n'
            '  }\n'
        )

        # Staff: espacamento do conteudo nao-musical (markups de tecnica)
        layout += (
            '  \\context {\n'
            '    \\Staff\n'
            '    \\override VerticalAxisGroup.staff-affinity = #CENTER\n'
            f'    \\override VerticalAxisGroup.nonstaff-relatedstaff-spacing.padding = #{staff_pad}\n'
            '  }\n'
        )

        # TextScript: alinhamento dos markups de tecnica abaixo das notas.
        # self-alignment-X = LEFT: texto comeca na cabeca da nota,
        # vai para a direita -- mas nunca corta o inicio.
        # avoid-slur = #'ignore: nao desloca por causa de ligaduras.
        layout += (
            '  \\context {\n'
            '    \\Voice\n'
            # Markups nao deslocam notas adjacentes (evita explosao horizontal)
            '    \\override TextScript.staff-padding = #1\n'
            '    \\override TextScript.avoid-slur = #\'ignore\n'
            '    \\override TextScript.outside-staff-priority = ##f\n'
        )
        # Glissando zigzag: uma vez no layout
        if getattr(self, '_has_wavy_glissando', False):
            layout += (
                '    \\override Glissando.style = #\'zigzag\n'
            )
        layout += '  }\n'

        # Notacao proporcional
        if getattr(self, '_needs_proportional_layout', False) or self.use_proportional:
            moment = self.proportional_moment
            layout += (
                '  \\context {\n'
                '    \\Score\n'
                f'    proportionalNotationDuration = #(ly:make-moment {moment})\n'
                '    \\override SpacingSpanner.uniform-stretching = ##t\n'
                '  }\n'
            )

        layout += '}\n'
        return layout

    @staticmethod
    def _find_lilypond_executable() -> Optional[str]:
        """
        Localiza o executável LilyPond de forma cross-platform.
        Ordem: shutil.which → caminhos típicos por SO → None.
        """
        import shutil
        import platform

        # 1. Tenta PATH primeiro (funciona se o usuário configurou corretamente)
        found = shutil.which("lilypond")
        if found:
            return found

        system = platform.system()

        if system == "Windows":
            # Caminhos típicos de instalação no Windows
            candidates = [
                r"C:\Program Files (x86)\LilyPond\usr\bin\lilypond.exe",
                r"C:\Program Files\LilyPond\usr\bin\lilypond.exe",
                r"C:\Program Files (x86)\LilyPond 2\usr\bin\lilypond.exe",
                r"C:\Program Files\LilyPond 2\usr\bin\lilypond.exe",
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "LilyPond", "usr", "bin", "lilypond.exe"),
                os.path.join(os.environ.get("APPDATA", ""),      "LilyPond", "usr", "bin", "lilypond.exe"),
            ]
        elif system == "Darwin":
            candidates = [
                "/Applications/LilyPond.app/Contents/Resources/bin/lilypond",
                "/usr/local/bin/lilypond",
                "/opt/homebrew/bin/lilypond",
            ]
        else:  # Linux
            candidates = [
                "/usr/bin/lilypond",
                "/usr/local/bin/lilypond",
                "/snap/bin/lilypond",
            ]

        for c in candidates:
            if c and os.path.isfile(c):
                return c

        return None

    def _run_lilypond(
        self, base: str, ly_path: str, extra_flags: list
    ) -> Optional[str]:
        # Determina o executável: atributo explícito > auto-detecção > fallback "lilypond"
        if self.lilypond_path and os.path.isfile(self.lilypond_path):
            lp = self.lilypond_path
        else:
            lp = self._find_lilypond_executable() or self.lilypond_path or "lilypond"

        cmd = [lp] + extra_flags + ["-o", base, ly_path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result.returncode == 0:
                if "--png" in extra_flags:
                    for candidate in [base + ".png", base + "-1.png"]:
                        if os.path.exists(candidate):
                            return candidate
                else:
                    pdf = base + ".pdf"
                    if os.path.exists(pdf):
                        return pdf
                print(f"[AbjadEngine] LilyPond ok mas arquivo não encontrado em '{base}'")
            else:
                print(f"[AbjadEngine] Erro LilyPond:\n{result.stderr[:800]}")
        except FileNotFoundError:
            detected = self._find_lilypond_executable()
            if detected:
                print(f"[AbjadEngine] LilyPond detectado em '{detected}' mas falhou ao executar.")
            else:
                print(
                    f"[AbjadEngine] LilyPond não encontrado.\n"
                    f"  • Instale em: https://lilypond.org/download.html\n"
                    f"  • Ou configure o caminho na GUI (campo 'Caminho LilyPond')."
                )
        except subprocess.TimeoutExpired:
            print("[AbjadEngine] Timeout LilyPond (>180s).")
        return None


# ---------------------------------------------------------------------------
# Utilitário de geração rítmica com tuplas (Etapa 6)
# ---------------------------------------------------------------------------

def generate_tuplet_rhythm(
    pitches_midi: list,
    base_duration: float = 1.0,
    ratio: str = "3:2",
    dynamics: list = None,
    instrument_id: str = "default",
) -> TupletGroup:
    """
    Constrói um TupletGroup a partir de uma lista de alturas MIDI.

    Parâmetros
    ----------
    pitches_midi : list[int | None]   None = pausa
    base_duration : float             duração escrita de cada nota (ex: 1.0 = semínima)
    ratio : str                       ratio da tupla (ex: "3:2", "5:4")
    dynamics : list[str | None]       dinâmicas opcionais
    """
    events = []
    for i, pitch in enumerate(pitches_midi):
        dyn = dynamics[i] if dynamics and i < len(dynamics) else None
        events.append(NoteEvent(
            pitch_midi=pitch,
            duration_beats=base_duration,
            dynamic=dyn,
            instrument_id=instrument_id,
        ))
    return TupletGroup(ratio=ratio, events=events, instrument_id=instrument_id)


# ---------------------------------------------------------------------------
# Teste (python abjad_engine.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  Teste AbjadEngine v2  —  Etapas 6, 7, 8")
    print("=" * 60)

    # --------------------------------------------------------
    # Etapa 6: Tuplas complexas — Flauta
    # --------------------------------------------------------
    seq_flauta = EventSequence("flauta", tempo_bpm=63, time_signature=(4, 4))

    # Tercina simples
    tercina = TupletGroup.triplet([
        NoteEvent.note(67, 1.0, dynamic="mp"),
        NoteEvent.quarter_tone_up(69, 1.0),
        NoteEvent.note(71, 1.0, articulation=ArticulationType.STACCATO),
    ])
    # Quintina
    quintina = TupletGroup.quintuplet([
        NoteEvent.note(72, 0.5, dynamic="f"),
        NoteEvent.note(74, 0.5),
        NoteEvent.note(76, 0.5, technique=ExtendedTechnique.FLUTTER_TONGUE),
        NoteEvent.note(74, 0.5, hairpin=HairpinType.DECRESCENDO),
        NoteEvent.note(72, 0.5, hairpin_end=True),
    ])
    # Septina aninhada dentro de 4:3 (Ferneyhough-style)
    inner_3 = TupletGroup.triplet([
        NoteEvent.quarter_tone_down(71, 0.5),
        NoteEvent.note(69, 0.5),
        NoteEvent.note(67, 0.5),
    ])
    outer_ferneyhough = TupletGroup("4:3", [
        inner_3,
        NoteEvent.note(65, 1.0, dynamic="pp"),
    ])

    seq_flauta.extend([
        tercina,
        quintina,
        outer_ferneyhough,
        NoteEvent.rest(1.0),
    ])

    # --------------------------------------------------------
    # Etapa 7: Grand staff piano refinado
    # --------------------------------------------------------
    seq_piano = EventSequence("piano", tempo_bpm=63, time_signature=(4, 4))
    seq_piano.extend([
        # Notas agudas (mão direita)
        NoteEvent.note(72, 1.0, dynamic="mp"),
        NoteEvent.note(74, 0.5),
        NoteEvent.note(76, 0.5),
        # Cruzamento: nota na zona de histerese
        NoteEvent.note(58, 1.0),    # bem abaixo do split → mão esquerda
        NoteEvent.note(55, 1.0, dynamic="f"),
        # Volta ao agudo
        NoteEvent.note(67, 1.0, dynamic="mf"),
        NoteEvent.note(65, 0.5),
        NoteEvent.note(64, 0.5),
        # Acorde
        NoteEvent.chord([48, 52, 55], 2.0, dynamic="pp"),
    ])

    # --------------------------------------------------------
    # Viola — notação proporcional
    # --------------------------------------------------------
    seq_viola = EventSequence("viola", use_proportional=True, time_signature=(4, 4))
    seq_viola.extend([
        NoteEvent.note(48, 2.0, dynamic="ppp", hairpin=HairpinType.NIENTE_IN),
        TupletGroup.triplet([
            NoteEvent.note(50, 1.0, technique=ExtendedTechnique.COL_LEGNO),
            NoteEvent.note(52, 1.0),
            NoteEvent.note(53, 1.0, dynamic="mf", hairpin_end=True),
        ]),
        NoteEvent.note(55, 1.5, dynamic="f", hairpin=HairpinType.NIENTE_OUT),
        NoteEvent.rest(0.5, hairpin_end=True),
    ])

    # --------------------------------------------------------
    # Constrói e exporta
    # --------------------------------------------------------
    engine = AbjadEngine(
        title="Estudo Contemporâneo — Etapas 6/7/8",
        composer_name="GrammarComposer / Ivan Simurra",
        piano_split_midi=60,
        piano_split_hysteresis=4,
    )
    score = engine.build_score([seq_flauta, seq_piano, seq_viola])

    out = os.path.join(os.path.dirname(__file__) or ".", "output")
    os.makedirs(out, exist_ok=True)
    ly_path = os.path.join(out, "teste_v2.ly")
    engine.save_ly(ly_path)

    ly_content = open(ly_path, encoding="utf-8").read()
    # Verificações
    assert "tuplet" in ly_content.lower() or r"\tuplet" in ly_content, "Tuplet não encontrado!"
    assert "PianoStaff" in ly_content, "PianoStaff não encontrado!"
    assert "omit Staff.BarLine" in ly_content, "Proporcional não encontrado!"
    print("\n[OK] Tuplas no LY:", ly_content.count(r"\tuplet"))
    print("[OK] Grand staff: PianoStaff presente")
    print("[OK] Notação proporcional: \\omit Staff.BarLine presente")
    print(f"\nArquivo salvo: {ly_path}")
    print(f"Para PDF:  lilypond -o {os.path.join(out,'teste_v2')} {ly_path}")
    print(f"Para PNG:  lilypond --png -dresolution=150 -o {os.path.join(out,'teste_v2')} {ly_path}")
    print("\n--- LilyPond (primeiras 60 linhas) ---")
    for i, line in enumerate(ly_content.split("\n")[:60]):
        print(line)
