"""
note_event.py  v2
=================
Estruturas de dados neutras para o Symbolic Grammar Composer.

v2 adiciona:
  • TupletGroup — agrupa NoteEvents em tuplas simples e aninhadas
    (suporte a estilo Ferneyhough)

Autor: Ivan Simurra / NICS-UNICAMP
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# ---------------------------------------------------------------------------
# Enumerações
# ---------------------------------------------------------------------------

class ExtendedTechnique(str, Enum):
    NORMAL          = "normal"
    SUL_PONTICELLO  = "sul_ponticello"
    SUL_TASTO       = "sul_tasto"
    COL_LEGNO       = "col_legno"
    FLUTTER_TONGUE  = "flutter_tongue"
    MULTIPHONIC     = "multiphonic"
    HARMONICS       = "harmonics"
    SNAP_PIZZICATO  = "snap_pizzicato"
    ORDINARIO       = "ordinario"


class ArticulationType(str, Enum):
    NONE            = "none"
    ACCENT          = "accent"
    STACCATO        = "staccato"
    TENUTO          = "tenuto"
    MARCATO         = "marcato"
    STACCATISSIMO   = "staccatissimo"
    PORTATO         = "portato"


class HairpinType(str, Enum):
    NONE        = "none"
    CRESCENDO   = "crescendo"
    DECRESCENDO = "decrescendo"
    NIENTE_IN   = "niente_in"
    NIENTE_OUT  = "niente_out"


class GlissandoType(str, Enum):
    NONE    = "none"
    NORMAL  = "normal"
    WAVY    = "wavy"


class SlurRole(str, Enum):
    NONE    = "none"
    START   = "start"
    MIDDLE  = "middle"
    END     = "end"


# ---------------------------------------------------------------------------
# NoteEvent
# ---------------------------------------------------------------------------

@dataclass
class NoteEvent:
    """
    Evento musical atômico (nota, pausa ou acorde).

    Pitch
    -----
    pitch_midi : int | None   — None = pausa
    microtone_offset : float  — +0.5 quarto-de-tom acima, -0.5 abaixo
    duration_beats : float    — semínima = 1.0

    Dinâmica
    --------
    dynamic : str | None      — "ppp".."fff" | None = herdar
    hairpin : HairpinType     — inicia hairpin nesta nota
    hairpin_end : bool        — encerra hairpin corrente

    Técnica / Articulação
    ---------------------
    technique : ExtendedTechnique
    articulation : ArticulationType

    Conectores
    ----------
    glissando : GlissandoType   (desta nota para a próxima)
    slur : SlurRole
    tie : bool

    Acorde
    ------
    chord_members : list[int]   pitches MIDI adicionais
    is_chord_note : bool        membro secundário — ignorado na iteração

    Metadados
    ---------
    instrument_id, voice_index, measure_index, beat_position

    Extensão livre
    --------------
    custom_lilypond : str | None   código LilyPond inserido antes desta nota
    """

    pitch_midi: Optional[int]           = None
    microtone_offset: float             = 0.0
    duration_beats: float               = 1.0

    dynamic: Optional[str]              = None
    hairpin: HairpinType                = HairpinType.NONE
    hairpin_end: bool                   = False

    technique: ExtendedTechnique        = ExtendedTechnique.NORMAL
    articulation: ArticulationType      = ArticulationType.NONE

    glissando: GlissandoType            = GlissandoType.NONE
    slur: SlurRole                      = SlurRole.NONE
    tie: bool                           = False

    chord_members: list                 = field(default_factory=list)
    is_chord_note: bool                 = False

    instrument_id: str                  = "default"
    voice_index: int                    = 0
    measure_index: int                  = 0
    beat_position: float                = 0.0

    custom_lilypond: Optional[str]      = None
    # Para percussão sem altura: sobrescreve o drum_note_name do InstrumentConfig.
    # Permite que uma EventSequence de "bateria" misture vários sons.
    # Ex: drum_instrument="bassdrum" para bumbo, "snare" para caixa.
    drum_instrument: str                 = ""

    @property
    def is_rest(self) -> bool:
        return self.pitch_midi is None

    @property
    def has_microtone(self) -> bool:
        return abs(self.microtone_offset) > 0.05

    @classmethod
    def rest(cls, duration_beats: float = 1.0, **kw):
        return cls(pitch_midi=None, duration_beats=duration_beats, **kw)

    @classmethod
    def note(cls, pitch_midi: int, duration_beats: float = 1.0, **kw):
        return cls(pitch_midi=pitch_midi, duration_beats=duration_beats, **kw)

    @classmethod
    def quarter_tone_up(cls, pitch_midi: int, duration_beats: float = 1.0, **kw):
        return cls(pitch_midi=pitch_midi, microtone_offset=0.5,
                   duration_beats=duration_beats, **kw)

    @classmethod
    def quarter_tone_down(cls, pitch_midi: int, duration_beats: float = 1.0, **kw):
        return cls(pitch_midi=pitch_midi, microtone_offset=-0.5,
                   duration_beats=duration_beats, **kw)

    @classmethod
    def chord(cls, pitches_midi: list, duration_beats: float = 1.0, **kw):
        return cls(pitch_midi=pitches_midi[0],
                   chord_members=list(pitches_midi[1:]),
                   duration_beats=duration_beats, **kw)

    def __repr__(self) -> str:
        if self.is_rest:
            return f"NoteEvent(rest, dur={self.duration_beats})"
        mt = f"+{self.microtone_offset}" if self.has_microtone else ""
        dyn = f", dyn={self.dynamic}" if self.dynamic else ""
        tech = f", tech={self.technique.value}" if self.technique != ExtendedTechnique.NORMAL else ""
        return f"NoteEvent(midi={self.pitch_midi}{mt}, dur={self.duration_beats}{dyn}{tech})"


# ---------------------------------------------------------------------------
# TupletGroup  (Etapa 6)
# ---------------------------------------------------------------------------

@dataclass
class TupletGroup:
    """
    Agrupa NoteEvents (ou outros TupletGroups) em uma tupla LilyPond.

    O ratio "n:d" significa: n notas escritas ocupam o espaço de d notas.

    Exemplos
    --------
    TupletGroup("3:2", [e1, e2, e3])          # tercina
    TupletGroup("5:4", [e1, e2, e3, e4, e5])  # quintina
    TupletGroup("7:4", events)                 # septina
    TupletGroup("7:8", events)                 # Ferneyhough sub-divisão

    Aninhamento (Ferneyhough-style):
        TupletGroup("5:4", [
            TupletGroup("3:2", [e1, e2, e3]),
            e4, e5, e6, e7
        ])

    Atributos
    ---------
    ratio : str
        "n:d" — n notas escritas preenchem espaço de d.
    events : list[NoteEvent | TupletGroup]
    show_bracket : bool    — omite colchete se False
    show_number : bool     — omite número se False
    instrument_id : str
    """
    ratio: str          = "3:2"
    events: list        = field(default_factory=list)
    show_bracket: bool  = True
    show_number: bool   = True
    instrument_id: str  = "default"

    def __post_init__(self):
        parts = self.ratio.split(":")
        if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
            raise ValueError(
                f"TupletGroup.ratio deve ser 'n:d'. Recebido: '{self.ratio}'"
            )

    @property
    def n(self) -> int:
        return int(self.ratio.split(":")[0])

    @property
    def d(self) -> int:
        return int(self.ratio.split(":")[1])

    @property
    def total_beats(self) -> float:
        """Duração real em beats (espaço ocupado)."""
        from fractions import Fraction
        written = sum(
            e.duration_beats if isinstance(e, NoteEvent) else e.total_beats
            for e in self.events
        )
        return float(Fraction(written) * Fraction(self.d, self.n))

    @property
    def note_count(self) -> int:
        return sum(
            1 if isinstance(e, NoteEvent) else e.note_count
            for e in self.events
        )

    # Construtores semânticos
    @classmethod
    def triplet(cls, events: list, **kw):
        """3 notas em espaço de 2 (tercina)."""
        return cls("3:2", events, **kw)

    @classmethod
    def quintuplet(cls, events: list, **kw):
        """5 notas em espaço de 4."""
        return cls("5:4", events, **kw)

    @classmethod
    def septuplet(cls, events: list, **kw):
        """7 notas em espaço de 4."""
        return cls("7:4", events, **kw)

    @classmethod
    def from_complexity(cls, events: list, level: int = 1, **kw):
        """
        Nível 1 → 3:2  | Nível 2 → 5:4 | Nível 3 → 7:4
        Nível 4 → 7:8  | Nível 5 → 11:8 (Ferneyhough)
        """
        ratios = ["3:2", "5:4", "7:4", "7:8", "11:8"]
        return cls(ratios[min(level - 1, 4)], events, **kw)

    def __repr__(self) -> str:
        return f"TupletGroup({self.ratio}, n={len(self.events)}, beats≈{self.total_beats:.2f})"


# ---------------------------------------------------------------------------
# EventSequence
# ---------------------------------------------------------------------------

@dataclass
class EventSequence:
    """
    Sequência ordenada de NoteEvent / TupletGroup para um instrumento/voz.
    """
    instrument_id: str
    voice_index: int        = 0
    events: list            = field(default_factory=list)   # NoteEvent | TupletGroup

    tempo_bpm: float        = 90.0
    time_signature: tuple   = (4, 4)
    use_proportional: bool  = False
    title: str              = ""
    composer_name: str      = "GrammarComposer"
    # Sequência de fórmulas de compasso por compasso (opcional).
    # Quando presente, o motor Abjad insere mudanças de fórmula ao longo da pauta.
    time_sig_sequence: list = field(default_factory=list)


    def append(self, event) -> None:
        self.events.append(event)

    def extend(self, events) -> None:
        self.events.extend(events)

    def __len__(self) -> int:
        return len(self.events)

    def __iter__(self):
        return iter(self.events)

    def __getitem__(self, idx):
        return self.events[idx]

    @property
    def total_beats(self) -> float:
        return sum(
            e.duration_beats if isinstance(e, NoteEvent) else e.total_beats
            for e in self.events
        )

    @property
    def sounding_note_count(self) -> int:
        def _count(items):
            total = 0
            for e in items:
                if isinstance(e, NoteEvent):
                    total += 0 if e.is_rest else 1
                elif isinstance(e, TupletGroup):
                    total += _count(e.events)
            return total
        return _count(self.events)

    def __repr__(self) -> str:
        return (f"EventSequence({self.instrument_id!r}, "
                f"n={len(self)}, beats={self.total_beats:.1f})")


# ---------------------------------------------------------------------------
# InstrumentConfig
# ---------------------------------------------------------------------------

@dataclass
class InstrumentConfig:
    instrument_id: str
    name_full: str
    name_short: str
    clef: str                = "treble"   # treble | bass | alto | tenor | percussion
    midi_program: int        = 0
    midi_channel: int        = 0
    transpose_semitones: int = 0
    tessitura_min_midi: int  = 48
    tessitura_max_midi: int  = 84
    staff_count: int         = 1
    secondary_clef: str      = "bass"
    # Percussão sem altura definida
    is_percussion: bool      = False      # True → DrumStaff / DrumVoice
    drum_note_name: str      = ""         # nome LilyPond (ex: "snare", "bassdrum")
    # Para percussão com múltiplos sons por instrumento, o drum_note_name
    # é o padrão; o campo NoteEvent.drum_instrument substitui por nota.

    def __repr__(self) -> str:
        kind = " [perc]" if self.is_percussion else ""
        return f"InstrumentConfig({self.instrument_id}: {self.name_full}{kind})"


# ---------------------------------------------------------------------------
# Catálogo de instrumentos
# ---------------------------------------------------------------------------

INSTRUMENT_CATALOG: dict = {
    "flauta": InstrumentConfig("flauta","Flauta","Fl.",
        clef="treble",midi_program=73,tessitura_min_midi=60,tessitura_max_midi=96),
    "flauta_piccolo": InstrumentConfig("flauta_piccolo","Fl. Picc.","Picc.",
        clef="treble",midi_program=72,tessitura_min_midi=74,tessitura_max_midi=108),
    "oboé": InstrumentConfig("oboé","Oboé","Ob.",
        clef="treble",midi_program=68,tessitura_min_midi=58,tessitura_max_midi=91),
    "corne_inglês": InstrumentConfig("corne_inglês","Corne Inglês","C.I.",
        clef="treble",midi_program=69,transpose_semitones=-7,
        tessitura_min_midi=52,tessitura_max_midi=81),
    "clarinete": InstrumentConfig("clarinete","Clarinete","Cl.",
        clef="treble",midi_program=71,transpose_semitones=-2,
        tessitura_min_midi=50,tessitura_max_midi=89),
    "clarinete_baixo": InstrumentConfig("clarinete_baixo","Cl. Baixo","Cl.B.",
        clef="treble",midi_program=71,transpose_semitones=-14,
        tessitura_min_midi=38,tessitura_max_midi=77),
    "fagote": InstrumentConfig("fagote","Fagote","Fg.",
        clef="bass",midi_program=70,tessitura_min_midi=34,tessitura_max_midi=72),
    "contrafagote": InstrumentConfig("contrafagote","Contrafagote","C.Fg.",
        clef="bass",midi_program=70,transpose_semitones=-12,
        tessitura_min_midi=22,tessitura_max_midi=60),
    "trompa": InstrumentConfig("trompa","Trompa","Tpa.",
        clef="treble",midi_program=60,transpose_semitones=-7,
        tessitura_min_midi=41,tessitura_max_midi=77),
    "trompete": InstrumentConfig("trompete","Trompete","Tpt.",
        clef="treble",midi_program=56,transpose_semitones=-2,
        tessitura_min_midi=55,tessitura_max_midi=82),
    "trombone": InstrumentConfig("trombone","Trombone","Tbn.",
        clef="bass",midi_program=57,tessitura_min_midi=36,tessitura_max_midi=74),
    "trombone_baixo": InstrumentConfig("trombone_baixo","Trombone Baixo","Tbn.B.",
        clef="bass",midi_program=57,tessitura_min_midi=28,tessitura_max_midi=64),
    "tuba": InstrumentConfig("tuba","Tuba","Tba.",
        clef="bass",midi_program=58,tessitura_min_midi=28,tessitura_max_midi=58),
    "marimba": InstrumentConfig("marimba","Marimba","Mar.",
        clef="treble",midi_program=12,tessitura_min_midi=45,tessitura_max_midi=96),
    "vibrafone": InstrumentConfig("vibrafone","Vibrafone","Vib.",
        clef="treble",midi_program=11,tessitura_min_midi=53,tessitura_max_midi=89),
    "violino": InstrumentConfig("violino","Violino","Vl.",
        clef="treble",midi_program=40,tessitura_min_midi=55,tessitura_max_midi=103),
    "viola": InstrumentConfig("viola","Viola","Vla.",
        clef="alto",midi_program=41,tessitura_min_midi=48,tessitura_max_midi=91),
    "violoncelo": InstrumentConfig("violoncelo","Violoncelo","Vc.",
        clef="bass",midi_program=42,tessitura_min_midi=36,tessitura_max_midi=79),
    "contrabaixo": InstrumentConfig("contrabaixo","Contrabaixo","Cb.",
        clef="bass",midi_program=43,transpose_semitones=-12,
        tessitura_min_midi=28,tessitura_max_midi=67),
    "piano": InstrumentConfig("piano","Piano","Pno.",
        clef="treble",midi_program=0,tessitura_min_midi=21,tessitura_max_midi=108,
        staff_count=2,secondary_clef="bass"),
    "piano_direita": InstrumentConfig("piano_direita","Piano","Pno.",
        clef="treble",midi_program=0,tessitura_min_midi=60,tessitura_max_midi=108),
    "piano_esquerda": InstrumentConfig("piano_esquerda","Piano","Pno.",
        clef="bass",midi_program=0,tessitura_min_midi=21,tessitura_max_midi=59),
    "cravo": InstrumentConfig("cravo","Cravo","Crv.",
        clef="treble",midi_program=6,tessitura_min_midi=28,tessitura_max_midi=96,
        staff_count=2,secondary_clef="bass"),
    "soprano": InstrumentConfig("soprano","Soprano","S.",
        clef="treble",midi_program=52,tessitura_min_midi=60,tessitura_max_midi=84),
    "mezzo": InstrumentConfig("mezzo","Mezzo-Soprano","Mz.",
        clef="treble",midi_program=52,tessitura_min_midi=57,tessitura_max_midi=81),
    "contralto": InstrumentConfig("contralto","Contralto","A.",
        clef="treble",midi_program=52,tessitura_min_midi=53,tessitura_max_midi=77),
    "tenor": InstrumentConfig("tenor","Tenor","T.",
        clef="treble",midi_program=52,transpose_semitones=-12,
        tessitura_min_midi=48,tessitura_max_midi=72),
    "barítono": InstrumentConfig("barítono","Barítono","Bar.",
        clef="bass",midi_program=52,tessitura_min_midi=45,tessitura_max_midi=69),
    "baixo_voz": InstrumentConfig("baixo_voz","Baixo","B.",
        clef="bass",midi_program=52,tessitura_min_midi=40,tessitura_max_midi=64),

    # -----------------------------------------------------------------------
    # Percussão de altura DEFINIDA
    # -----------------------------------------------------------------------
    # (marimba e vibrafone já existem acima; adicionamos tímpano e crotales)
    "timpano": InstrumentConfig(
        "timpano", "Tímpano", "Timp.",
        clef="bass", midi_program=47,
        tessitura_min_midi=41, tessitura_max_midi=65  # Fá1–Lá4
    ),
    "crotales": InstrumentConfig(
        "crotales", "Crotales", "Crot.",
        clef="treble", midi_program=79,
        tessitura_min_midi=60, tessitura_max_midi=84   # escrito; soa 2 oitavas acima
    ),
    "xilofone": InstrumentConfig(
        "xilofone", "Xilofone", "Xil.",
        clef="treble", midi_program=13,
        tessitura_min_midi=53, tessitura_max_midi=96
    ),
    "glockenspiel": InstrumentConfig(
        "glockenspiel", "Glockenspiel", "Glock.",
        clef="treble", midi_program=9,
        tessitura_min_midi=55, tessitura_max_midi=91   # escrito; soa 2 oitavas acima
    ),

    # -----------------------------------------------------------------------
    # Percussão de altura INDEFINIDA — caixa e bumbo
    # -----------------------------------------------------------------------
    "caixa": InstrumentConfig(
        "caixa", "Caixa", "Cx.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="snare"
    ),
    "caixa_abafada": InstrumentConfig(
        "caixa_abafada", "Caixa Abafada", "Cx.Ab.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="acousticsnare"
    ),
    "rim_shot": InstrumentConfig(
        "rim_shot", "Rim Shot", "R.Shot",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="sidestick"
    ),
    "bumbo": InstrumentConfig(
        "bumbo", "Bumbo", "Bbo.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="bassdrum"
    ),
    "bumbo_acustico": InstrumentConfig(
        "bumbo_acustico", "Bumbo Acústico", "Bbo.Ac.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="acousticbassdrum"
    ),

    # -----------------------------------------------------------------------
    # Percussão de altura INDEFINIDA — tom-tons
    # -----------------------------------------------------------------------
    "tom_agudo": InstrumentConfig(
        "tom_agudo", "Tom Agudo", "Tom.A.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="hightom"
    ),
    "tom_medio_agudo": InstrumentConfig(
        "tom_medio_agudo", "Tom Médio-Agudo", "Tom.MA.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="himidtom"
    ),
    "tom_medio_grave": InstrumentConfig(
        "tom_medio_grave", "Tom Médio-Grave", "Tom.MG.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="lowmidtom"
    ),
    "tom_grave": InstrumentConfig(
        "tom_grave", "Tom Grave", "Tom.G.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="lowtom"
    ),
    "floor_tom_agudo": InstrumentConfig(
        "floor_tom_agudo", "Floor Tom Agudo", "F.Tom.A.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="highfloortom"
    ),
    "floor_tom_grave": InstrumentConfig(
        "floor_tom_grave", "Floor Tom Grave", "F.Tom.G.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="lowfloortom"
    ),

    # -----------------------------------------------------------------------
    # Percussão de altura INDEFINIDA — hi-hat
    # -----------------------------------------------------------------------
    "hihat_fechado": InstrumentConfig(
        "hihat_fechado", "Hi-Hat Fechado", "H.H.Fch.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="closedhihat"
    ),
    "hihat_aberto": InstrumentConfig(
        "hihat_aberto", "Hi-Hat Aberto", "H.H.Ab.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="openhihat"
    ),
    "hihat_pedal": InstrumentConfig(
        "hihat_pedal", "Hi-Hat Pedal", "H.H.Ped.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="pedalhihat"
    ),
    "hihat_meio_aberto": InstrumentConfig(
        "hihat_meio_aberto", "Hi-Hat Meio-Aberto", "H.H.M.Ab.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="halfopenhihat"
    ),

    # -----------------------------------------------------------------------
    # Percussão de altura INDEFINIDA — pratos
    # -----------------------------------------------------------------------
    "prato_crash": InstrumentConfig(
        "prato_crash", "Prato Crash", "Cr.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="crashcymbal"
    ),
    "prato_ride": InstrumentConfig(
        "prato_ride", "Prato Ride", "Ride",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="ridecymbal"
    ),
    "prato_ride_bell": InstrumentConfig(
        "prato_ride_bell", "Bell do Ride", "Ride.B.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="ridebell"
    ),
    "prato_china": InstrumentConfig(
        "prato_china", "Prato China", "China",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="chinesecymbal"
    ),
    "prato_splash": InstrumentConfig(
        "prato_splash", "Prato Splash", "Splash",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="splashcymbal"
    ),
    "prato_suspenso": InstrumentConfig(
        "prato_suspenso", "Prato Suspenso", "Pr.Sus.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="crashcymbal"
    ),

    # -----------------------------------------------------------------------
    # Percussão de altura INDEFINIDA — instrumentos orquestrais
    # -----------------------------------------------------------------------
    "triangulo": InstrumentConfig(
        "triangulo", "Triângulo", "Trgl.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="opentriangle"
    ),
    "triangulo_abafado": InstrumentConfig(
        "triangulo_abafado", "Triângulo Abafado", "Trgl.Ab.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="mutetriangle"
    ),
    "woodblock_agudo": InstrumentConfig(
        "woodblock_agudo", "Woodblock Agudo", "W.B.A.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="hiwoodblock"
    ),
    "woodblock_grave": InstrumentConfig(
        "woodblock_grave", "Woodblock Grave", "W.B.G.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="lowoodblock"
    ),
    "tamborim": InstrumentConfig(
        "tamborim", "Tamborim", "Tamb.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="tambourine"
    ),
    "cowbell": InstrumentConfig(
        "cowbell", "Cowbell", "Cow.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="cowbell"
    ),
    "claves": InstrumentConfig(
        "claves", "Claves", "Clav.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="claves"
    ),
    "maracas": InstrumentConfig(
        "maracas", "Maracas", "Marc.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="maracas"
    ),
    "tantã": InstrumentConfig(
        "tantã", "Tantã", "Tantã",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="lowtom"      # LilyPond aproximação
    ),
    "gongo": InstrumentConfig(
        "gongo", "Gongo", "Gongo",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="crashcymbal"  # LilyPond aproximação
    ),
    "pratos_a_2": InstrumentConfig(
        "pratos_a_2", "Pratos a 2", "Pr. a 2",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="crashcymbal"
    ),

    # -----------------------------------------------------------------------
    # Bateria completa (multi-instrumento, usa DrumStaff compartilhado)
    # -----------------------------------------------------------------------
    "bateria": InstrumentConfig(
        "bateria", "Bateria", "Bat.",
        clef="percussion", midi_program=0,
        is_percussion=True, drum_note_name="snare"  # nota padrão; eventos usam drum_instrument
    ),
}


def get_instrument(instrument_id: str) -> Optional[InstrumentConfig]:
    if instrument_id in INSTRUMENT_CATALOG:
        return INSTRUMENT_CATALOG[instrument_id]
    base = instrument_id.rsplit("_", 1)[0]
    if base in INSTRUMENT_CATALOG:
        import copy
        cfg = copy.copy(INSTRUMENT_CATALOG[base])
        cfg.instrument_id = instrument_id
        return cfg
    return None


def list_instruments() -> list:
    return list(INSTRUMENT_CATALOG.keys())
