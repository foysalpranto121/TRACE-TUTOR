"""Respect hint-only requests without returning solution fields."""
import re

HINT_INSTRUCTION = '''HINT-ONLY REQUEST: This overrides all complete-answer instructions.
Give only one small conceptual clue or guiding question, in the student's language.
Do not reveal the final answer, complete algorithm, pseudocode, or any code.
Put the clue in independent_ai_answer.chat_answer and direct_answer.
Set rag_answer to {}, code_solution and pedagogical_justification to empty strings,
and problem_breakdown to []. Do not expand the clue into a solution in other fields.'''


def is_hint_request(prompt):
    return bool(re.search(r'\bhints?\b|\bclue\b|ইঙ্গিত|হিন্ট', prompt, re.I))


def hint_response(parsed, language):
    independent = parsed.get('independent_ai_answer') or {}
    clue = str(independent.get('chat_answer') or parsed.get('direct_answer') or '').strip()
    # Do not let executable code escape through prose if the model ignores instructions.
    if not clue or re.search(r'```|#\s*include|\bmain\s*\(|\b(?:for|while|printf|scanf)\s*\(|<\s*(?:html|script)|\bdef\s+\w+\s*\(', clue, re.I):
        clue = ('আগে ভাবুন: প্রতিবার একই কাজ করার সময় কোন মানটি বদলায়, আর কোন মানটি জমা রাখতে হয়?'
                if language == 'bn' else 'Think about which value changes each time and which value you need to keep track of.')
    return {
        **parsed,
        'rag_answer': {},
        'direct_answer': clue,
        'independent_ai_answer': {
            'chat_answer': clue, 'concept_applied': '', 'problem_breakdown': [],
            'pedagogical_justification': '', 'code_solution': '',
        },
    }
