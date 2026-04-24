"""
example_quartet.py
==================
Quarteto de cordas gerado algoritmicamente com:
  - Cadeias de Markov para altura e duração
  - Quiálteras complexas (até sétimas aninhadas)
  - Técnicas estendidas estocásticas
  - Fórmulas de compasso variáveis
  - Microtonalismo

Uso:
    python examples/example_quartet.py
"""

import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from grammar_abjad_adapter import GrammarAbjadAdapter
from abjad_engine import AbjadEngine


# ── Composer stub (normalmente seria o CompositionEngine real) ───────────────

class QuartetComposer:
    """Composer mínimo compatível com GrammarAbjadAdapter."""

    composition_length = 20
    tempo = 60
    time_signature = "5/8"
    use_variable_time_signatures = True
    variable_time_signatures = ["5/8", "3/4", "4/4", "7/8", "6/8", "9/8"]
    time_sig_change_probability = 0.25
    _abjad_target_measures = 24
    composition_templates = {
        "balanced": {
            "min_pitch": 48,
            "max_pitch": 84,
            "rhythm_complexity": 0.7,
            "min_dynamic": "pp",
            "max_dynamic": "fff",
        }
    }

    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.rhythm_patterns = {
            (1.0,): 4,
            (0.5, 0.5): 6,
            (0.25, 0.25, 0.5): 5,
            (1.5, 0.5): 3,
            (0.5, 0.25, 0.25): 4,
        }
        self.tempo_expression = "Agitato"

    def _generate_pitch_sequence(self, length, min_p, max_p):
        return [
            random.randint(min_p, max_p) if random.random() > 0.07 else None
            for _ in range(length)
        ]

    def generate_time_signature_sequence(self, n):
        sigs = self.variable_time_signatures
        result, current, i = [], "5/8", 0
        while i < n:
            run = random.randint(1, 4)
            result.extend([current] * min(run, n - i))
            i += run
            if i < n and random.random() < 0.3:
                current = random.choice(sigs)
        return result[:n]


def main():
    composer = QuartetComposer(seed=99)
    composer._current_time_sig_sequence = composer.generate_time_signature_sequence(28)

    # ── Configura o adaptador ─────────────────────────────────────────────────
    adapter = GrammarAbjadAdapter(composer)
    adapter.tuplet_probability    = 0.30   # 30% de grupos viram quiálteras
    adapter.tuplet_complexity     = 3      # até sétimas (7:4)
    adapter.tuplet_nesting_prob   = 0.20   # quiálteras aninhadas ocasionais
    adapter.technique_probability = 0.25   # técnicas estendidas
    adapter.glissando_probability = 0.10   # glissandos
    adapter.microtone_probability = 0.08   # quartos de tom

    # ── Gera sequências para quarteto de cordas ───────────────────────────────
    sequences = adapter.build_sequences_from_composer(
        instrument_ids=["violino", "viola", "violoncelo", "contrabaixo"],
        style="balanced",
    )

    # ── Renderiza ─────────────────────────────────────────────────────────────
    engine = AbjadEngine(
        title="Estudo para Quarteto de Cordas",
        composer_name="Ivan Simurra / GrammarComposer",
    )
    engine.build_score(sequences)

    os.makedirs("output", exist_ok=True)
    ly_path = engine.save_ly("output/example_quartet.ly")

    print(f"LilyPond salvo: {ly_path}")
    print("Para gerar PDF:")
    print("  lilypond -o output/example_quartet output/example_quartet.ly")
    print("\nEstatísticas:")
    from note_event import TupletGroup
    for seq in sequences:
        tuplets = sum(1 for e in seq.events if isinstance(e, TupletGroup))
        nested  = sum(
            1 for e in seq.events
            if isinstance(e, TupletGroup)
            for sub in e.events if isinstance(sub, TupletGroup)
        )
        print(f"  {seq.instrument_id}: {len(seq.events)} eventos, "
              f"{tuplets} quiálteras ({nested} aninhadas)")


if __name__ == "__main__":
    main()
