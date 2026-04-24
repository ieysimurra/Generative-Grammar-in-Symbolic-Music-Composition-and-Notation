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
TUPLET_RATIOS = [
    (3, 2),    # nivel 1: tercina  — 3 notas no espaço de 2
    (5, 4),    # nivel 2: quintina — 5 no espaço de 4
    (7, 4),    # nivel 3: sétima   — 7 no espaço de 4
    (7, 8),    # nivel 4: sétima de colcheia
    (11, 8),   # nivel 5: onzena (estilo Ferneyhough)
]

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
        self.tuplet_probability: float      = 0.0
        self.tuplet_complexity: int         = 1    # 1–5
        self.tuplet_nesting_prob: float     = 0.0  # aninhamento Ferneyhough

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

            # ── Agrupa notas em quiálteras (stochastic) ─────────────────
            # Percorre raw_notes e, com probabilidade tuplet_probability,
            # agrupa N notas consecutivas num TupletGroup.
            # Restrições:
            #   • A duração total do grupo deve ser um valor rítmico
            #     representável (>= semínima, potência-de-2 de colcheia).
            #   • Mínimo de 2 notas no grupo; máximo = numerador do ratio.
            #   • Quiálteras aninhadas: se tuplet_nesting_prob > 0, a última
            #     nota do grupo pode ser substituída por uma quiáltera interna.
            items_to_add = self._group_into_tuplets(
                raw_notes, inst_id, measure_beats
            )
            for item in items_to_add:
                seq.append(item)

        return seq

    def _group_into_tuplets(
        self,
        raw_notes: list,
        inst_id: str,
        measure_beats: "_Frac",
    ) -> list:
        """
        Percorre raw_notes e agrupa estocasticamente em TupletGroups.

        Cada raw_note é uma tupla:
          (pitch, microtone, dur, technique, glissando, dyn, hp, hp_end)

        INVARIANTE: as durações originais somam exatamente measure_beats.
        O agrupamento em TupletGroups preserva esse invariante porque:
          - o TupletGroup "consome" as mesmas durações originais do compasso
          - apenas a duração escrita interna muda (inner_dur = total_outer / den)
          - LilyPond compensa com o ratio num/den ao renderizar

        Restrição crítica: um grupo só é formado se total_dur dos membros
        não ultrapassa o budget restante do compasso (remaining_beats).
        """
        result = []
        i = 0
        # Rastreia beats consumidos (para verificar que não excedemos o compasso)
        consumed = _Frac(0)

        while i < len(raw_notes):
            note = raw_notes[i]
            pitch, microtone, dur, tech, gliss, dyn, hp, hp_end = note
            note_dur = _Frac(dur).limit_denominator(64)
            remaining = measure_beats - consumed

            # Tenta criar quiáltera a partir desta posição
            can_try_tuplet = (
                self.tuplet_probability > 0
                and random.random() < self.tuplet_probability
                and i + 1 < len(raw_notes)   # precisa de ≥ 2 notas
                and remaining >= _Frac(1, 4)  # mínimo de 1/4 beat restante
            )

            if can_try_tuplet:
                ratio = TUPLET_RATIOS[min(self.tuplet_complexity - 1, 4)]
                num, den = ratio

                # A quiáltera deve ter EXATAMENTE num notas (o numerador do ratio).
                # Isso é obrigatório para que a duração sonora seja correta:
                # sounding = num * inner_dur * den/num = total_outer
                # Se n_notes != num, a fórmula quebra e o compasso fica errado.
                n_notes = num
                if i + n_notes > len(raw_notes):
                    # Notas insuficientes para completar a quiáltera
                    result.append(self._raw_to_event(note, inst_id))
                    consumed += note_dur
                    i += 1
                    continue

                # Verifica que as n_notes notas cabem no budget restante do compasso
                cand_dur = sum(
                    _Frac(raw_notes[i + k][2]).limit_denominator(64)
                    for k in range(n_notes)
                )
                if cand_dur > remaining + _Frac(1, 128):
                    # Não cabe — cria nota normal
                    result.append(self._raw_to_event(note, inst_id))
                    consumed += note_dur
                    i += 1
                    continue

                # Duração mínima do grupo: pelo menos 1 semínima
                if cand_dur < _Frac(1, 4):
                    result.append(self._raw_to_event(note, inst_id))
                    consumed += note_dur
                    i += 1
                    continue

                group = raw_notes[i:i + n_notes]
                total_dur = cand_dur

                # Duração ESCRITA de cada nota dentro da quiáltera:
                # total_sounding / den garante que 	uplet num/den { N * inner_dur }
                # soa exatamente total_dur beats.
                # Ex: 3:2 em 1.0 beat → inner = 0.5 (8ª) → 	uplet 3/2 {c8 d8 e8} ✓
                inner_dur = float(total_dur / den)

                # ── Quiáltera simples ────────────────────────────────────
                if (self.tuplet_nesting_prob <= 0
                        or random.random() > self.tuplet_nesting_prob
                        or n_notes < 4):
                    inner_data = [
                        (n[0], n[1], inner_dur, n[3], n[4], n[5], n[6], n[7])
                        for n in group
                    ]
                    tg = _make_tuplet_group(inner_data, ratio, inst_id)
                    result.append(tg)

                else:
                    # ── Quiáltera aninhada (estilo Ferneyhough) ──────────
                    # Para que a quiáltera externa seja válida (num eventos),
                    # precisamos: (num - 1) notas externas + 1 quiáltera interna.
                    # A quiáltera interna precisa de in_num notas.
                    # Total de notas necessárias = (num - 1) + in_num.
                    inner_ratio = TUPLET_RATIOS[
                        min(self.tuplet_complexity, len(TUPLET_RATIOS) - 1)
                    ]
                    in_num, in_den = inner_ratio
                    total_needed = (num - 1) + in_num

                    if total_needed > len(raw_notes) - i or total_needed > len(group):
                        # Não tem notas suficientes → quiáltera simples
                        inner_data = [
                            (n[0], n[1], inner_dur, n[3], n[4], n[5], n[6], n[7])
                            for n in group
                        ]
                        tg = _make_tuplet_group(inner_data, ratio, inst_id)
                        result.append(tg)
                    else:
                        # Verifica que total_needed notas cabem no budget
                        full_group = raw_notes[i:i + total_needed]
                        full_dur = sum(_Frac(n[2]).limit_denominator(64) for n in full_group)
                        if full_dur > remaining + _Frac(1, 128):
                            # Não cabe → quiáltera simples com as notas originais
                            inner_data = [
                                (n[0], n[1], inner_dur, n[3], n[4], n[5], n[6], n[7])
                                for n in group
                            ]
                            tg = _make_tuplet_group(inner_data, ratio, inst_id)
                            result.append(tg)
                            # Mas ainda consomemos apenas n_notes (= num)!
                        else:
                            # Usa total_needed notas (recalcula duração)
                            total_dur = full_dur
                            inner_dur = float(total_dur / den)
                            outer_plain = full_group[:num - 1]
                            inner_group = full_group[num - 1:]  # = in_num notas

                            in_total = sum(_Frac(n[2]).limit_denominator(64) for n in inner_group)
                            in_inner_dur = float(in_total / in_den)
                            nested_data = [
                                (n[0], n[1], in_inner_dur, n[3], n[4], n[5], n[6], n[7])
                                for n in inner_group
                            ]
                            nested_tg = _make_tuplet_group(nested_data, inner_ratio, inst_id)

                            outer_events = [
                                self._raw_to_event(
                                    (n[0], n[1], inner_dur, n[3], n[4], n[5], n[6], n[7]),
                                    inst_id
                                )
                                for n in outer_plain
                            ]
                            outer_events.append(nested_tg)
                            ratio_str = f"{num}:{den}"
                            tg = TupletGroup(ratio_str, outer_events,
                                             instrument_id=inst_id)
                            result.append(tg)
                            # Corrige n_notes para o total real consumido
                            n_notes = total_needed
                            total_dur = full_dur

                consumed += total_dur
                i += n_notes
                continue

            # Nota normal
            result.append(self._raw_to_event(note, inst_id))
            consumed += note_dur
            i += 1

        return result

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
