"""Difficulty profile definitions.

Single source of truth for item difficulty. A ``DifficultyProfile``
describes the target difficulty of generated test items along five
axes. The profile is injected into the prompt template as per-axis
slots so that passage, questions, distractors, and key phrases are all
shaped by the declared item difficulty.

Tiers are aligned with CEFR / TOEIC / Eiken bands:

    beginner     CEFR A2  /  TOEIC 400-550  /  Eiken 3-Pre2
    intermediate CEFR B1  /  TOEIC 550-780  /  Eiken Pre2-2
    advanced     CEFR B2  /  TOEIC 780-860  /  Eiken 2-Pre1
    expert       CEFR C1  /  TOEIC 860+     /  Eiken Pre1-1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class DifficultyProfile:
    tier_id: str
    tier_label: str
    cefr_level: str
    toeic_range: str
    passage_language: str
    information_density: str
    question_abstraction: str
    distractor_subtlety: str


DIFFICULTY_PROFILES: Dict[str, DifficultyProfile] = {
    "beginner": DifficultyProfile(
        tier_id="beginner",
        tier_label="BEGINNER",
        cefr_level="A2",
        toeic_range="400-550",
        passage_language=(
            "Use simple present and simple past tense with straightforward "
            "subject-verb-object sentences. Restrict vocabulary to a core "
            "1000-2000 word range. Avoid phrasal verbs, idioms, and passive "
            "voice. Keep every sentence short and unambiguous."
        ),
        information_density=(
            "Include only 1-2 concrete details total (for example one name "
            "and one time). Tell the story linearly with no forward or "
            "backward references. Every new fact should be stated once and "
            "not require the listener to connect it to earlier information."
        ),
        question_abstraction=(
            "Ask strictly literal fact questions that can be answered by "
            "directly matching words from the passage (What did X say? "
            "Where is Y? When will Z happen?). Do not ask about inference, "
            "speaker intent, or implied meaning."
        ),
        distractor_subtlety=(
            "Wrong choices should be clearly off-topic or directly "
            "contradicted by the passage. A careful listener should be able "
            "to eliminate them immediately. The margin between the correct "
            "answer and the wrong choices can be wide."
        ),
    ),
    "intermediate": DifficultyProfile(
        tier_id="intermediate",
        tier_label="INTERMEDIATE",
        cefr_level="B1",
        toeic_range="550-780",
        passage_language=(
            "Use common business vocabulary such as 'schedule', 'deadline', "
            "'meeting', 'budget', 'client'. Mix simple and compound "
            "sentences; a few basic phrasal verbs are fine. The result "
            "should sound natural but not complex."
        ),
        information_density=(
            "Include 3-5 concrete details (names, times, numbers, places) "
            "spread through the passage. Some details may be referenced "
            "again one or two sentences later, requiring the listener to "
            "hold them in working memory briefly."
        ),
        question_abstraction=(
            "Ask mostly literal questions, with light paraphrase allowed. "
            "A question may ask what the speaker means in straightforward "
            "terms, but avoid deep inference. Wording in the question "
            "should still map closely to the passage."
        ),
        distractor_subtlety=(
            "Wrong choices share thematic vocabulary with the passage but "
            "mismatch on one concrete key detail (tense, number, actor, "
            "timing, or location). A careful listener can eliminate them "
            "by catching that single mismatch."
        ),
    ),
    "advanced": DifficultyProfile(
        tier_id="advanced",
        tier_label="ADVANCED",
        cefr_level="B2",
        toeic_range="780-860",
        passage_language=(
            "Use fluent professional business English with subordinate "
            "clauses, passive voice, and varied sentence patterns. Weave "
            "formal business verbs (e.g. 'finalize', 'allocate', "
            "'delegate', 'coordinate') and less common phrasal verbs into "
            "the speakers' natural speech. Do NOT replace such expressions "
            "with simpler near-synonyms for readability."
        ),
        information_density=(
            "Pack 5-8 concrete details densely through the passage, with "
            "multiple references back to earlier mentions. Some connections "
            "between facts should be implicit, requiring the listener to "
            "track threads actively rather than just hear them once."
        ),
        question_abstraction=(
            "Mix literal fact questions, paraphrase questions, and "
            "inference questions (What does the speaker imply? What will "
            "most likely happen next?). Roughly one in three questions "
            "should require inference rather than direct matching."
        ),
        distractor_subtlety=(
            "Wrong choices subtly paraphrase near-synonyms of the correct "
            "answer, or recombine surface details from the passage in "
            "incorrect ways. The margin is tight and careful listening is "
            "required to reject them."
        ),
    ),
    "expert": DifficultyProfile(
        tier_id="expert",
        tier_label="EXPERT",
        cefr_level="C1",
        toeic_range="860+",
        passage_language=(
            "Use a near-native register with complex rhetorical structures, "
            "understatement, and nuanced tone. Weave low-frequency formal "
            "verbs (e.g. 'mitigate', 'reconcile', 'substantiate') and "
            "multi-word idioms into the speakers' natural speech wherever "
            "they would realistically use them. Do NOT replace such "
            "expressions with simpler near-synonyms for readability — let "
            "the hard words stand."
        ),
        information_density=(
            "Include 8 or more details with layered references: concurrent "
            "threads of information, implicit causal chains, and details "
            "mentioned only once that later become pivotal. The listener "
            "must synthesize across the whole passage, not just catch "
            "individual facts."
        ),
        question_abstraction=(
            "Emphasize inference, speaker intent, implied attitude, and "
            "synthesis across multiple parts of the passage. At least two "
            "of three questions should require reading between the lines "
            "rather than direct fact extraction."
        ),
        distractor_subtlety=(
            "Wrong choices are plausible partial matches that require "
            "precise understanding to reject. A single-word distinction "
            "may separate correct from incorrect. Several wrong choices "
            "should feel 'almost right' on first pass."
        ),
    ),
}
