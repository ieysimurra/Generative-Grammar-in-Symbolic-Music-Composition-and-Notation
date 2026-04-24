"""
example_proportional.py
========================
Notação proporcional estilo Morton Feldman / Cornelius Cardew.

Características:
  - Sem barras de compasso
  - Sem fórmulas de compasso
  - Sem numeração de compassos
  - Espaçamento horizontal proporcional à duração
  - Dinâmicas suaves, muitas pausas, textura rarefeita

Uso:
    python examples/example_proportional.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from note_event import (
    NoteEvent, TupletGroup, EventSequence,
    ExtendedTechnique, HairpinType, GlissandoType,
)
from abjad_engine import AbjadEngine


def make_proportional_voice(instrument_id: str, pitches: list) -> EventSequence:
    """Cria uma voz em notação proporcional com textura Feldman."""
    seq = EventSequence(
        instrument_id,
        time_signature=(4, 4),
        tempo_bpm=52,
        use_proportional=True,  # ← ativa modo proporcional
    )

    for i, (pitch, dur, dyn) in enumerate(pitches):
        if pitch is None:
            seq.append(NoteEvent.rest(dur))
        else:
            n = NoteEvent.note(pitch, dur, dynamic=dyn)
            # Adiciona microtone ocasional
            if i % 5 == 2:
                n.microtone_offset = 0.5
            # Glissando suave ocasional
            if i % 7 == 3:
                n.glissando = GlissandoType.NORMAL
            seq.append(n)

    return seq


def main():
    # Viola — linha lenta, respirante
    viola_pitches = [
        (50, 3.0, "ppp"), (None, 1.0, None),
        (53, 2.0, "pp"),  (55, 1.5, "pp"),
        (None, 2.0, None),
        (52, 4.0, "p"),   (None, 1.5, None),
        (48, 2.0, "ppp"), (50, 3.0, "pp"),
        (None, 1.0, None), (53, 2.5, "p"),
    ]

    # Violoncelo — notas longas sustentadas
    cello_pitches = [
        (None, 2.0, None),
        (43, 4.0, "ppp"), (None, 1.0, None),
        (45, 3.0, "pp"),
        (None, 2.5, None),
        (41, 5.0, "p"),   (None, 1.0, None),
        (40, 2.0, "ppp"),
        (None, 3.0, None),
        (43, 4.0, "pp"),
    ]

    seq_viola  = make_proportional_voice("viola",      viola_pitches)
    seq_cello  = make_proportional_voice("violoncelo", cello_pitches)

    # ── Renderiza ─────────────────────────────────────────────────────────────
    engine = AbjadEngine(
        title="Fragmento Proporcional",
        composer_name="Ivan Simurra",
    )
    engine.build_score([seq_viola, seq_cello])

    os.makedirs("output", exist_ok=True)
    ly_path = engine.save_ly("output/example_proportional.ly")

    print(f"LilyPond salvo: {ly_path}")
    print("Para gerar PDF:")
    print("  lilypond -o output/example_proportional output/example_proportional.ly")
    print("\nNota: Notação proporcional não usa barras nem fórmulas de compasso.")
    print("      O espaçamento horizontal é proporcional às durações reais.")


if __name__ == "__main__":
    main()
