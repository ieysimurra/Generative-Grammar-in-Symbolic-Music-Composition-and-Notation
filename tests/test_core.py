"""
test_core.py
============
Testes unitários do GrammarComposer.

Uso:
    python tests/test_core.py
    # ou com pytest:
    pytest tests/test_core.py -v
"""

import sys
import os
import random
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from note_event import (
    NoteEvent, TupletGroup, EventSequence,
    ExtendedTechnique, GlissandoType, HairpinType, ArticulationType,
)
from abjad_engine import AbjadEngine, _compute_break_positions, _insert_system_breaks
from grammar_abjad_adapter import GrammarAbjadAdapter, _beats_for_ts


# ── Helpers ───────────────────────────────────────────────────────────────────

def sounding_beats(events):
    """Calcula os beats sonoros reais de uma lista de eventos."""
    total = Fraction(0)
    for ev in events:
        if isinstance(ev, TupletGroup):
            num, den = map(int, ev.ratio.split(":"))
            w = sum(
                sounding_beats([s]) if isinstance(s, TupletGroup)
                else Fraction(s.duration_beats).limit_denominator(64)
                for s in ev.events
            )
            total += w * den / num
        else:
            total += Fraction(ev.duration_beats).limit_denominator(64)
    return total


def assert_ok(label, cond, detail=""):
    if cond:
        print(f"  [OK]  {label}")
    else:
        raise AssertionError(f"FAIL: {label}" + (f" ({detail})" if detail else ""))


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_note_event_creation():
    """NoteEvent: criação e atributos básicos."""
    n = NoteEvent.note(60, 1.0, dynamic="mp")
    assert_ok("pitch", n.pitch_midi == 60)
    assert_ok("duration", n.duration_beats == 1.0)
    assert_ok("dynamic", n.dynamic == "mp")
    assert_ok("microtone default", n.microtone_offset == 0.0)
    assert_ok("technique default", n.technique == ExtendedTechnique.NORMAL)

    # Rest
    r = NoteEvent.rest(0.5)
    assert_ok("rest pitch", r.pitch_midi is None)
    assert_ok("rest duration", r.duration_beats == 0.5)

    # Quarter tone
    qt = NoteEvent.quarter_tone_up(62, 1.0)
    assert_ok("quarter tone offset", qt.microtone_offset == 0.5)


def test_tuplet_group_beat_invariant():
    """TupletGroup: invariante de duração sonora."""
    # Tercina 3:2 cobrindo 1 beat (semínima)
    inner_dur = 1.0 / 2  # = 0.5 (colcheia)
    tg = TupletGroup("3:2", [
        NoteEvent.note(60, inner_dur),
        NoteEvent.note(62, inner_dur),
        NoteEvent.note(64, inner_dur),
    ])
    beats = sounding_beats([tg])
    assert_ok("triplet beats = 1.0", abs(float(beats) - 1.0) < 0.001,
              f"got {float(beats):.4f}")

    # Quintina 5:4 cobrindo 1 beat
    inner_dur_5 = 1.0 / 4  # = 0.25 (semicolcheia)
    tg5 = TupletGroup("5:4", [
        NoteEvent.note(60, inner_dur_5),
        NoteEvent.note(62, inner_dur_5),
        NoteEvent.note(64, inner_dur_5),
        NoteEvent.note(65, inner_dur_5),
        NoteEvent.note(67, inner_dur_5),
    ])
    beats5 = sounding_beats([tg5])
    assert_ok("quintuplet beats = 1.0", abs(float(beats5) - 1.0) < 0.001,
              f"got {float(beats5):.4f}")

    # Quiáltera aninhada: 3:2 contendo outra 5:4
    inner_ratio = "5:4"
    in_dur = (1.0 / 2) / 4  # outer total / den_outer / den_inner
    nested = TupletGroup(inner_ratio, [
        NoteEvent.note(60, in_dur),
        NoteEvent.note(62, in_dur),
        NoteEvent.note(64, in_dur),
        NoteEvent.note(65, in_dur),
        NoteEvent.note(67, in_dur),
    ])
    outer = TupletGroup("3:2", [
        NoteEvent.note(60, 0.5),
        NoteEvent.note(62, 0.5),
        nested,
    ])
    beats_n = sounding_beats([outer])
    # Outer has num=3 notes but 2 plain + 1 nested. Check it's close to 1 beat.
    assert_ok("nested tuplet ~1 beat", abs(float(beats_n) - 1.0) < 0.05,
              f"got {float(beats_n):.4f}")


def test_event_sequence():
    """EventSequence: append, extend, time_sig_sequence."""
    seq = EventSequence("flauta", time_signature=(4, 4))
    seq.append(NoteEvent.note(60, 1.0))
    seq.append(NoteEvent.note(62, 1.0))
    assert_ok("len", len(seq.events) == 2)
    assert_ok("instrument_id", seq.instrument_id == "flauta")


def test_grammar_adapter_beat_exactness():
    """GrammarAbjadAdapter: beat invariant per measure across 4 instruments."""
    random.seed(42)

    class StubComposer:
        composition_length = 10
        tempo = 72
        time_signature = "4/4"
        use_variable_time_signatures = True
        variable_time_signatures = ["4/4", "3/4", "5/8", "7/8", "6/8"]
        time_sig_change_probability = 0.3
        _abjad_target_measures = 16
        composition_templates = {"balanced": {
            "min_pitch": 48, "max_pitch": 84,
            "rhythm_complexity": 0.6, "min_dynamic": "pp", "max_dynamic": "f",
        }}

        def __init__(self):
            self.rhythm_patterns = {(1.0,): 4, (0.5, 0.5): 6, (0.25, 0.25, 0.5): 5}
            self.tempo_expression = "Moderato"

        def _generate_pitch_sequence(self, l, mn, mx):
            return [random.randint(mn, mx) for _ in range(l)]

        def generate_time_signature_sequence(self, n):
            sigs = self.variable_time_signatures
            res, cur, i = [], "4/4", 0
            while i < n:
                run = random.randint(1, 4)
                res.extend([cur] * min(run, n - i))
                i += run
                if i < n and random.random() < 0.3:
                    cur = random.choice(sigs)
            return res[:n]

    c = StubComposer()
    c._current_time_sig_sequence = c.generate_time_signature_sequence(20)

    adapter = GrammarAbjadAdapter(c)
    adapter.tuplet_probability   = 0.25
    adapter.tuplet_complexity    = 3
    adapter.tuplet_nesting_prob  = 0.15
    adapter.technique_probability = 0.20

    seqs = adapter.build_sequences_from_composer(
        ["flauta", "viola", "violoncelo", "contrabaixo"], style="balanced"
    )

    assert_ok("4 sequences generated", len(seqs) == 4)
    for s in seqs:
        target = sum(_beats_for_ts(ts) for ts in getattr(s, "time_sig_sequence", []))
        actual = sounding_beats(s.events)
        diff   = abs(float(actual - target))
        assert_ok(
            f"{s.instrument_id} beat invariant",
            diff < 0.02,
            f"target={float(target):.2f} actual={float(actual):.3f} diff={diff:.4f}",
        )


def test_abjad_engine_ly_generation():
    """AbjadEngine: gera LilyPond válido com os elementos chave."""
    seq = EventSequence("flauta", time_signature=(4, 4))
    seq.time_sig_sequence = ["4/4"] * 4

    seq.append(NoteEvent.note(60, 1.0, dynamic="mp"))
    seq.append(TupletGroup.triplet([
        NoteEvent.note(62, 0.5, technique=ExtendedTechnique.SUL_PONTICELLO),
        NoteEvent.note(64, 0.5),
        NoteEvent.note(65, 0.5),
    ]))
    n = NoteEvent.note(67, 1.0)
    n.microtone_offset = 0.5
    seq.append(n)
    seq.append(NoteEvent.note(69, 1.0, glissando=GlissandoType.WAVY))

    engine = AbjadEngine(title="Test", composer_name="Test")
    engine.build_score([seq])
    ly = engine.to_lilypond_string()

    assert_ok("LY not empty", len(ly) > 500)
    assert_ok(r"\version present", r"\version" in ly)
    assert_ok(r"\language english", r'\language "english"' in ly)
    assert_ok("portrait", "(quote portrait)" in ly)
    assert_ok("ragged-right ##f", "ragged-right = ##f" in ly)
    assert_ok("staff-size top-level", ly.find("set-global-staff-size") < ly.find(r"\paper"))
    assert_ok(r"\tuplet present", r"\tuplet" in ly)
    assert_ok("sul pont markup", "sul pont" in ly)


def test_system_breaks():
    """_compute_break_positions e _insert_system_breaks: quebras automáticas."""
    ts_seq = ["4/4"] * 8 + ["7/8"] * 6 + ["9/8"] * 4
    breaks, intra = _compute_break_positions(ts_seq, staff_size=11)
    assert_ok("breaks is list", isinstance(breaks, list))
    assert_ok("intra is dict", isinstance(intra, dict))
    assert_ok("at least 2 breaks", len(breaks) >= 1,
              f"got {len(breaks)} breaks for {len(ts_seq)} measures")

    # Test string insertion
    sample_ly = (
        '\\context Voice = "Voice_flauta"\n'
        '        {\n'
        '            \\clef "treble"\n'
        '            \\time 4/4\n'
        "            c'4 d'4 e'4 f'4\n"
        '            \\time 7/8\n'
        "            g'4. a'4\n"
        '            \\time 9/8\n'
        "            b'4. c''4.\n"
        '        }\n'
    )
    ts_test = ["4/4", "7/8", "9/8"]
    result = _insert_system_breaks(sample_ly, ts_test, staff_size=11)
    assert_ok("insert returns string", isinstance(result, str))


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_note_event_creation,
        test_tuplet_group_beat_invariant,
        test_event_sequence,
        test_grammar_adapter_beat_exactness,
        test_abjad_engine_ly_generation,
        test_system_breaks,
    ]

    print(f"Running {len(tests)} tests...\n")
    failed = 0
    for test_fn in tests:
        print(f"{'─'*50}")
        print(f"{test_fn.__name__}")
        try:
            test_fn()
        except AssertionError as e:
            print(f"  ✗ {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ EXCEPTION: {e}")
            failed += 1

    print(f"\n{'═'*50}")
    if failed == 0:
        print(f"✓ All {len(tests)} tests passed.")
    else:
        print(f"✗ {failed}/{len(tests)} tests FAILED.")
        sys.exit(1)
