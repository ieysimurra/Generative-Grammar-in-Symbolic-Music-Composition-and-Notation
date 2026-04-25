"""
musicxml_export.py
==================
Converte EventSequence → MusicXML via music21.

CONTEÚDO PRESERVADO
────────────────────
  ✓ Alturas exatas (incluindo microtons ±50 cents)
  ✓ Ordenamento idêntico ao LilyPond
  ✓ Dinâmicas (ppp–fff, hairpins crescendo/decrescendo)
  ✓ Técnicas estendidas como texto itálico (sul pont., col legno, etc.)
  ✓ Articulações (staccato, acento, tenuto, marcato)
  ✓ Glissandos
  ✓ Pausas em qualquer posição
  ✓ Mudanças de fórmula de compasso
  ✓ Compassos sempre exatos — sem notas fantasma ou overfull

QUIÁLTERAS
───────────
Ratios complexos (9:8, 11:4, 13:8...) e quiálteras aninhadas causam erros
aritméticos internos no music21 / MusicXML quando usados com Tuplet brackets.

Estratégia: usar durações SOANTES para todas as notas (sem brackets).
  • Cada nota recebe sua duração soante real: written × den/num
  • Budget-constrained: a última nota do compasso absorve o resíduo de arredondamento
  • Compassos sempre somam exatamente ao valor correto

O LilyPond continua sendo a partitura de referência.
"""

from __future__ import annotations
import os, subprocess, sys
from fractions import Fraction
from typing import Optional

try:
    import music21 as m21
    _M21_AVAILABLE = True
except ImportError:
    _M21_AVAILABLE = False

from note_event import (
    NoteEvent, TupletGroup, EventSequence,
    ExtendedTechnique, HairpinType, GlissandoType, ArticulationType,
)

# ── Constantes ────────────────────────────────────────────────────────────────

TECHNIQUE_TEXT = {
    ExtendedTechnique.SUL_PONTICELLO: "sul pont.",
    ExtendedTechnique.SUL_TASTO:      "sul tasto",
    ExtendedTechnique.COL_LEGNO:      "col legno",
    ExtendedTechnique.FLUTTER_TONGUE: "flutter-tongue",
    ExtendedTechnique.MULTIPHONIC:    "multif.",
    ExtendedTechnique.HARMONICS:      "harm.",
    ExtendedTechnique.SNAP_PIZZICATO: "snap pizz.",
    ExtendedTechnique.ORDINARIO:      "ord.",
}

INSTRUMENT_NAMES = {
    "flauta": "Flute", "clarinete": "Clarinet", "oboé": "Oboe",
    "fagote": "Bassoon", "trompa": "Horn", "trompete": "Trumpet",
    "trombone": "Trombone", "tuba": "Tuba", "violino": "Violin",
    "viola": "Viola", "violoncelo": "Cello", "contrabaixo": "Contrabass",
    "piano": "Piano", "cravo": "Harpsichord", "harpa": "Harp",
    "percussão": "Percussion", "marimba": "Marimba", "vibrafone": "Vibraphone",
}

# Durações padrão para quantização (Fraction, em quarterLength)
_STANDARD_QLS = [
    Fraction(4), Fraction(3), Fraction(2), Fraction(3,2),
    Fraction(1), Fraction(3,4), Fraction(1,2), Fraction(3,8),
    Fraction(1,4), Fraction(3,16), Fraction(1,8), Fraction(3,32), Fraction(1,16),
]
_MIN_QL = Fraction(1, 16)  # 64th note


# ── Flat event ────────────────────────────────────────────────────────────────

class _FlatEvent:
    """NoteEvent com duração soante exata (Fraction, sem quantização)."""
    __slots__ = ("ev", "exact_sounding")

    def __init__(self, ev: NoteEvent, exact_sounding: Fraction):
        self.ev             = ev
        self.exact_sounding = exact_sounding


def _flatten(events: list, ratio_stack: list = None) -> list:
    """
    Achata a árvore em lista de _FlatEvent com duração soante exata.
    Para tuplets simples ou aninhados: sounding = written × Π(den/num).
    """
    if ratio_stack is None:
        ratio_stack = []
    result = []
    for ev in events:
        if isinstance(ev, TupletGroup):
            num, den = map(int, ev.ratio.split(":"))
            result.extend(_flatten(ev.events, ratio_stack + [(num, den)]))
        else:
            written  = Fraction(ev.duration_beats).limit_denominator(64)
            sounding = written
            for num, den in ratio_stack:
                sounding = sounding * Fraction(den, num)
            result.append(_FlatEvent(ev, sounding))
    return result


# ── Budget-constrained duration ───────────────────────────────────────────────

def _fit_ql(sounding: Fraction, remaining: Fraction, n_after: int) -> Fraction:
    """
    Escolhe a duração padrão mais próxima de sounding,
    com restrição: deve caber em remaining deixando espaço para n_after notas.
    """
    headroom = remaining - n_after * _MIN_QL
    valid = [v for v in _STANDARD_QLS if _MIN_QL <= v <= headroom]
    if not valid:
        return max(remaining, _MIN_QL)
    return min(valid, key=lambda x: abs(x - sounding))


# ── Public API ────────────────────────────────────────────────────────────────

def build_score_from_sequences(
    sequences: list,
    title: str = "",
    composer_name: str = "",
) -> "m21.stream.Score":
    """Converte lista de EventSequence em music21.Score."""
    if not _M21_AVAILABLE:
        raise ImportError("music21 não instalado. Execute: pip install music21")
    score = m21.stream.Score()
    md = m21.metadata.Metadata()
    if title:         md.title = title
    if composer_name: md.composer = composer_name
    score.insert(0, md)
    for seq in sequences:
        score.append(_sequence_to_part(seq))
    return score


def save_musicxml(
    sequences: list,
    filepath: str,
    title: str = "",
    composer_name: str = "",
    compressed: bool = False,
) -> Optional[str]:
    """Exporta para .musicxml (ou .mxl). Retorna caminho ou None em caso de erro."""
    score = build_score_from_sequences(sequences, title, composer_name)
    ext = ".mxl" if compressed else ".musicxml"
    if not filepath.endswith(ext):
        filepath = os.path.splitext(filepath)[0] + ext
    try:
        score.write("mxl" if compressed else "musicxml", fp=filepath)
        return filepath
    except Exception as e:
        print(f"[musicxml_export] Erro ao salvar: {e}", file=sys.stderr)
        return None


def open_in_musescore(
    sequences: list,
    title: str = "",
    composer_name: str = "",
    musescore_path: Optional[str] = None,
    temp_dir: Optional[str] = None,
) -> bool:
    """Exporta para MusicXML e abre no MuseScore."""
    import tempfile
    out_dir  = temp_dir or tempfile.mkdtemp()
    safe     = (title or "composicao").replace(" ", "_").replace("/", "-")[:40]
    filepath = os.path.join(out_dir, f"{safe}.musicxml")
    saved    = save_musicxml(sequences, filepath, title, composer_name)
    if not saved:
        return False
    ms = musescore_path or _find_musescore()
    if not ms:
        print("[musicxml_export] MuseScore não encontrado.", file=sys.stderr)
        return False
    try:
        subprocess.Popen([ms, saved])
        return True
    except Exception as e:
        print(f"[musicxml_export] Erro ao abrir MuseScore: {e}", file=sys.stderr)
        return False


# ── Part builder ──────────────────────────────────────────────────────────────

def _sequence_to_part(seq: EventSequence) -> "m21.stream.Part":
    part = m21.stream.Part()
    part.id = seq.instrument_id

    # Instrumento
    instr_name = INSTRUMENT_NAMES.get(seq.instrument_id.lower())
    if instr_name:
        try:    instr = m21.instrument.fromString(instr_name)
        except: instr = m21.instrument.Instrument(); instr.instrumentName = instr_name
    else:
        instr = m21.instrument.Instrument()
        instr.instrumentName = seq.instrument_id.capitalize()
    part.insert(0, instr)

    ts_sequence = getattr(seq, "time_sig_sequence", ["4/4"] * 16)
    flat        = _flatten(seq.events)
    ev_pos      = 0

    # Spanners de hairpin e glissando (persistem entre compassos)
    open_hairpin: list = []
    gliss_state:  list = []

    for ts_idx, ts_str in enumerate(ts_sequence):
        num_ts, den_ts = map(int, ts_str.split("/"))
        measure_beats  = Fraction(4 * num_ts, den_ts)

        # Recolhe FlatEvents deste compasso usando sounding exato como budget
        accum     = Fraction(0)
        m_flat: list[_FlatEvent] = []
        while ev_pos < len(flat):
            fe       = flat[ev_pos]
            sounding = fe.exact_sounding
            if accum + sounding > measure_beats + Fraction(1, 128):
                break
            m_flat.append(fe)
            accum += sounding
            ev_pos += 1

        # Constrói o Measure music21
        m_obj = m21.stream.Measure(number=ts_idx + 1)
        m_obj.append(m21.meter.TimeSignature(ts_str))
        remaining = measure_beats

        for i, fe in enumerate(m_flat):
            ev      = fe.ev
            is_last = (i == len(m_flat) - 1)
            n_after = len(m_flat) - i - 1

            # Duration budget-constrained
            if is_last:
                ql = max(remaining, _MIN_QL)
            else:
                ql = _fit_ql(fe.exact_sounding, remaining, n_after)
            remaining -= ql

            dur = m21.duration.Duration(quarterLength=float(ql))

            # Nota ou pausa
            if ev.is_rest:
                note_obj = m21.note.Rest(duration=dur)
            else:
                p = m21.pitch.Pitch()
                p.midi = ev.pitch_midi
                if abs(ev.microtone_offset) > 0.01:
                    p.microtone = m21.pitch.Microtone(ev.microtone_offset * 100)
                note_obj = m21.note.Note(duration=dur)
                note_obj.pitch = p

                # Técnica como texto itálico
                tech = TECHNIQUE_TEXT.get(ev.technique)
                if tech:
                    te = m21.expressions.TextExpression(tech)
                    te.style.fontStyle = "italic"
                    te.style.fontSize  = 8
                    note_obj.expressions.append(te)

                # Articulações
                if ev.articulation == ArticulationType.STACCATO:
                    note_obj.articulations.append(m21.articulations.Staccato())
                elif ev.articulation == ArticulationType.ACCENT:
                    note_obj.articulations.append(m21.articulations.Accent())
                elif ev.articulation == ArticulationType.TENUTO:
                    note_obj.articulations.append(m21.articulations.Tenuto())
                elif ev.articulation == ArticulationType.MARCATO:
                    note_obj.articulations.append(m21.articulations.StrongAccent())

            # Hairpin
            if ev.hairpin in (HairpinType.CRESCENDO, HairpinType.NIENTE_IN):
                cresc = m21.dynamics.Crescendo()
                open_hairpin.clear(); open_hairpin.append(cresc)
                cresc.addSpannedElements(note_obj)
                part.insert(0, cresc)
            elif ev.hairpin in (HairpinType.DECRESCENDO, HairpinType.NIENTE_OUT):
                decresc = m21.dynamics.Diminuendo()
                open_hairpin.clear(); open_hairpin.append(decresc)
                decresc.addSpannedElements(note_obj)
                part.insert(0, decresc)
            elif open_hairpin:
                open_hairpin[0].addSpannedElements(note_obj)
            if ev.hairpin_end and open_hairpin:
                open_hairpin.clear()

            # Glissando
            if not ev.is_rest and ev.glissando != GlissandoType.NONE:
                g = m21.spanner.Glissando()
                g.lineType = "wavy" if ev.glissando == GlissandoType.WAVY else "solid"
                gliss_state.clear(); gliss_state.append(g)
                g.addSpannedElements(note_obj)
                part.insert(0, g)
            elif gliss_state:
                try: gliss_state[0].addSpannedElements(note_obj)
                except: pass
                gliss_state.clear()

            # Dinâmica
            if ev.dynamic and not ev.is_rest:
                m_obj.append(m21.dynamics.Dynamic(ev.dynamic))

            m_obj.append(note_obj)

        part.append(m_obj)

    return part


# ── MuseScore detection ───────────────────────────────────────────────────────

def _find_musescore() -> Optional[str]:
    import shutil, platform
    for name in ["musescore4","musescore3","musescore","mscore4","mscore3","mscore"]:
        found = shutil.which(name)
        if found: return found
    system = platform.system()
    if system == "Darwin":
        candidates = [
            "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
            "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
            "/Applications/MuseScore.app/Contents/MacOS/mscore",
        ]
    elif system == "Windows":
        candidates = [
            r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
            r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe",
            r"C:\Program Files (x86)\MuseScore 3\bin\MuseScore3.exe",
        ]
    else:
        candidates = [
            "/usr/bin/musescore4", "/usr/bin/musescore3",
            "/usr/bin/musescore", "/usr/bin/mscore", "/snap/bin/musescore",
        ]
    for path in candidates:
        if os.path.isfile(path): return path
    return None
