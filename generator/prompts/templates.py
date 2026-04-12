"""Static prompt template strings.

Do NOT edit the wording of these constants without checking that the LLM
output remains stable. They are reproduced verbatim from the original
``build_prompt`` implementation.
"""

from __future__ import annotations

from typing import Dict

PART3_ROLE_HEADER = "You are a TOEIC Part 3 (short conversations) test content creator."
PART4_ROLE_HEADER = "You are a TOEIC Part 4 (short talks) test content creator."


DIFFICULTY_BLOCKS: Dict[str, str] = {
    "advanced": (
        "Difficulty: ADVANCED (TOEIC 800+). Use natural, professional English that "
        "a fluent business speaker would actually use. Sentence structures may include "
        "subordinate clauses, passive voice, and idiomatic expressions, but only where "
        "they arise naturally — never force sophisticated vocabulary just to sound "
        "advanced. Prioritize realistic, conversational flow over lexical showmanship."
    ),
    "intermediate": (
        "Difficulty: INTERMEDIATE (TOEIC 600-750). Use common business vocabulary "
        "(e.g. 'schedule', 'deadline', 'meeting', 'report', 'client', 'budget'). Keep "
        "sentences clear with mostly simple and compound structures. Natural but not "
        "overly complex."
    ),
}


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
#   role_header, part, topic, difficulty_block, passage_spec,
#   questions_block, trap_block, min_key_phrases, max_key_phrases,
#   passage_key_example
PROMPT_TEMPLATE = """{role_header}

Generate TOEIC Part {part} listening practice content on the topic: "{topic}".

{difficulty_block}

PASSAGE REQUIREMENTS:
{passage_spec}
- Use natural, professional English at the specified difficulty
- VARIETY: Stay closely on the given topic. Do NOT drift toward generic
  business themes (quarterly reports, budget reviews, deadline extensions)
  unless the topic specifically asks for them. Let the scenario, setting,
  and vocabulary be shaped by the topic itself

QUESTION REQUIREMENTS:
{questions_block}

{trap_block}

KEY PHRASES REQUIREMENTS:
- Select between {min_key_phrases} and {max_key_phrases} expressions from the
  passage that a learner at this level might NOT already know.
- Focus on phrases that would genuinely expand the listener's vocabulary:
  idiomatic expressions, phrasal verbs, less common collocations, or
  domain-specific terms. Skip basic words the learner already knows.
- For each entry, provide a concise Japanese gloss (roughly 6-18 characters,
  no full sentences, no trailing punctuation needed).

Return ONLY a valid JSON object with this exact structure (no markdown, no explanation):
{{
  "title": "Short descriptive title",
  "slug": "snake_case_slug",
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
    {{"en": "on short notice", "ja": "急な通知で"}},
    {{"en": "finalize the deadline", "ja": "締め切りを確定する"}},
    {{"en": "follow up with the client", "ja": "顧客に追って連絡する"}}
  ]
}}

Rules:
- "answer" must be exactly one of "A", "B", "C", "D"
- All 3 questions must be answerable from the passage alone
- Wrong choices must apply the trap patterns described above
- "key_phrases" length must be between {min_key_phrases} and {max_key_phrases}
- Each key_phrase "en" must be drawn from or directly grounded in the passage
- Do NOT include any fields other than the ones shown"""
