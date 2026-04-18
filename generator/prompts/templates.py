"""Static prompt template strings.

Do NOT edit the wording of these constants without checking that the LLM
output remains stable. Difficulty-dependent wording is NOT stored here —
it lives in ``generator.difficulty.DIFFICULTY_PROFILES`` and is injected
into the template via per-axis slots by ``generator.transcript``.
"""

from __future__ import annotations

PART3_ROLE_HEADER = "You are a TOEIC Part 3 (short conversations) test content creator."
PART4_ROLE_HEADER = "You are a TOEIC Part 4 (short talks) test content creator."


TRAP_GUIDANCE_BLOCK = (
    "IMPORTANT — TOEIC distractor (trap) patterns to embed in the wrong choices:\n"
    "  1. Paraphrase traps: wrong choices use synonyms or near-synonyms that sound "
    "plausible but don't match the actual meaning in the passage.\n"
    "  2. Tense confusion: wrong choices swap past/present/future or perfect aspects "
    "relative to what was actually said.\n"
    "  3. Partial-match traps: wrong choices reuse exact words from the passage but "
    "in a misleading context or combined with incorrect details.\n"
    "  4. Word-association traps: wrong choices include words thematically related "
    "to the topic but not actually mentioned or implied.\n"
    "  5. Over-generalization / over-specification: wrong choices are too broad or "
    "too narrow compared to what the passage actually states.\n"
    "The correct answer must be unambiguously supported by the passage.\n\n"
    "NATURALNESS: The passage must sound like a real conversation or announcement "
    "that could actually happen. Do NOT shoehorn business jargon or TOEIC-specific "
    "vocabulary into the passage. Use domain-appropriate language that fits the "
    "specific scenario (e.g. a museum tour should use museum vocabulary, not "
    "corporate finance terms). Vary sentence patterns and avoid formulaic structures."
)


QUESTIONS_BLOCK = (
    "Generate exactly 3 comprehension questions. Each question has 4 choices labeled "
    "A, B, C, D, with exactly one correct answer. Typical Part 3/4 question stems "
    "include: 'What are the speakers discussing?', 'Where most likely are the "
    "speakers?', 'What does the man suggest?', 'What will the woman probably do "
    "next?', 'What is the purpose of the announcement?', 'According to the speaker, "
    "what should listeners do?', etc.\n"
    "CRITICAL: When a question needs to refer to a specific speaker, use natural "
    "English role descriptions like 'the man', 'the woman', 'the first woman', "
    "'the second woman', 'the speaker', etc. NEVER use raw speaker IDs like 'W1', "
    "'W2', 'M', 'W', or 'S' in any question text, choice, or key phrase — those "
    "are internal technical markers and are unintelligible to test-takers."
)


# Passage spec templates. Use ``str.format`` with named placeholders.
PART3_PASSAGE_SPEC_TEMPLATE = (
    "- Format: realistic multi-speaker business dialogue\n"
    "- Speakers: {num_speakers} people ({speaker_list})\n"
    "- Total dialogue turns: exactly {num_turns}\n"
    "- Every speaker must appear and speak at least 2 times\n"
    "- Each line 1-2 sentences; include concrete details "
    "(names, times, numbers, places) where appropriate"
)

PART4_PASSAGE_SPEC_TEMPLATE = (
    "- Format: single-speaker narration (announcement, advertisement, news "
    "report, telephone message, or talk)\n"
    "- Speaker: 1 person ({speaker_id})\n"
    "- Length: exactly {num_turns} sentences, delivered as {num_turns} lines\n"
    "- Natural monologue flow with concrete details "
    "(names, times, numbers, places)"
)


# Full prompt template. Placeholders:
#   role_header, part, topic,
#   difficulty_passage_language, difficulty_information_density,
#   difficulty_question_abstraction, difficulty_distractor_subtlety,
#   passage_spec, questions_block, trap_block,
#   min_key_phrases, max_key_phrases, passage_key_example,
#   recent_phrases_block
PROMPT_TEMPLATE = """{role_header}

MISSION:
The artifact you produce (passage + questions + answers + key_phrases + the
resulting audio) is a learning deliverable whose sole purpose is to raise a
learner's English proficiency as measured by TOEIC and CEFR frameworks.
Learners will internalize material from the audio and redeploy it in
comparable situations; key_phrases in particular are high-value targets —
including TOEIC-characteristic frequent lexis and collocations — that the
learner has not yet mastered for production.

Generate TOEIC Part {part} listening practice content on the topic: "{topic}".

PASSAGE REQUIREMENTS:
{passage_spec}
- Language level: {difficulty_passage_language}
- Information density: {difficulty_information_density}

QUESTION REQUIREMENTS:
{questions_block}
- Abstraction level: {difficulty_question_abstraction}

{trap_block}

DISTRACTOR SUBTLETY:
{difficulty_distractor_subtlety}
{recent_phrases_block}
KEY PHRASES REQUIREMENTS:
- Select {min_key_phrases}-{max_key_phrases} expressions drawn from the
  passage, the question, or the answer options.
- FLOOR: the learner is studying at the passage's target proficiency
  level. Choose items the learner cannot yet produce at that level;
  items already producible at the target level are not key phrases.
- Non-substitutability boundary (word- and collocation-level only — never
  a clause or sentence fragment): include only the non-substitutable
  lexical core. If a modifier can be replaced by another of the same
  category and the phrase's learning value is unchanged, drop it.
  Retain elements that must co-occur to preserve meaning or idiomatic
  form: a verb with its bound preposition, a transitive verb with a
  representative object, or the fixed parts of a set expression.
- For each entry, provide a concise Japanese gloss (roughly 6-18 characters,
  no full sentences, no trailing punctuation needed). The gloss must be a
  genuine Japanese translation, not a katakana transliteration of the
  English; if no meaningful Japanese rendering exists, exclude the phrase.

Return ONLY a valid JSON object with this exact structure (no markdown, no explanation):
{{
  "title": "Short descriptive title",
  "passage": {passage_key_example},
  "questions": [
    {{
      "id": 1,
      "text": "What are the speakers discussing?",
      "choices": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "answer": "B"
    }},
    {{
      "id": 2,
      "text": "...",
      "choices": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "answer": "A"
    }},
    {{
      "id": 3,
      "text": "...",
      "choices": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "answer": "D"
    }}
  ],
  "key_phrases": [
    {{"en": "<phrase drawn from the passage>", "ja": "<6-18字の日本語訳>"}},
    {{"en": "<another phrase from the passage>", "ja": "<6-18字の日本語訳>"}},
    {{"en": "<another phrase from the passage>", "ja": "<6-18字の日本語訳>"}}
  ]
}}

Rules:
- "answer" must be exactly one of "A", "B", "C", "D"
- All 3 questions must be answerable from the passage alone
- Wrong choices must apply the trap patterns described above
- "key_phrases" length must be between {min_key_phrases} and {max_key_phrases}
- Each key_phrase "en" must be drawn from or directly grounded in the passage
- Do NOT copy the angle-bracketed placeholder values (e.g. "<...>") into
  your output. Treat the example JSON as a structural template only.
- Do NOT include any fields other than the ones shown"""
