"""
example_minimal.py
==================
Score mínimo: uma melodia de flauta com tercina e glissando.
Demonstra a API básica do GrammarComposer.

Uso:
    python examples/example_minimal.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from note_event import (
    NoteEvent, TupletGroup, EventSequence,
    ExtendedTechnique, GlissandoType, HairpinType,
)
from abjad_engine import AbjadEngine


def main():
    # ── Cria uma sequência para flauta ───────────────────────────────────────
    seq = EventSequence("flauta", time_signature=(4, 4), tempo_bpm=72)

    # Nota com dinâmica
    seq.append(NoteEvent.note(72, 1.0, dynamic="mp"))

    # Tercina com técnica estendida
    seq.append(TupletGroup.triplet([
        NoteEvent.note(71, 0.5, technique=ExtendedTechnique.SUL_PONTICELLO),
        NoteEvent.note(69, 0.5),
        NoteEvent.note(67, 0.5, hairpin_end=True),
    ]))

    # Nota com glissando e crescendo
    seq.append(NoteEvent.note(65, 1.0, hairpin=HairpinType.CRESCENDO))
    seq.append(NoteEvent.note(
        64, 1.0,
        dynamic="f",
        glissando=GlissandoType.NORMAL,
        hairpin_end=True,
    ))

    # Nota com microtone (quarto de tom acima)
    n = NoteEvent.note(62, 1.0, dynamic="pp")
    n.microtone_offset = 0.5  # +1/4 tom
    seq.append(n)

    # ── Renderiza ────────────────────────────────────────────────────────────
    engine = AbjadEngine(title="Miniatura para Flauta", composer_name="Ivan Simurra")
    engine.build_score([seq])

    os.makedirs("output", exist_ok=True)
    ly_path = engine.save_ly("output/example_minimal.ly")
    print(f"LilyPond salvo: {ly_path}")
    print("Para gerar PDF: lilypond -o output/example_minimal output/example_minimal.ly")


if __name__ == "__main__":
    main()
