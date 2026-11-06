import unittest
from tutor.hint_policy import hint_response, is_hint_request


class HintPolicyTests(unittest.TestCase):
    def test_english_and_bangla_hint_intent(self):
        for prompt in ['Give me a hint without spoiling the answer', 'একটা ইঙ্গিত দাও', 'হিন্ট চাই']:
            self.assertTrue(is_hint_request(prompt))
        self.assertFalse(is_hint_request('Give me the complete code'))

    def test_removes_solution_fields_and_keeps_clue(self):
        result = hint_response({'rag_answer': {'textbook_rule': 'Full solution'},
                                'independent_ai_answer': {'chat_answer': 'Which value should you track?',
                                                          'code_solution': 'complete program',
                                                          'problem_breakdown': ['all solution steps']}}, 'en')
        self.assertEqual(result['independent_ai_answer']['code_solution'], '')
        self.assertEqual(result['independent_ai_answer']['problem_breakdown'], [])
        self.assertEqual(result['rag_answer'], {})
        self.assertEqual(result['direct_answer'], 'Which value should you track?')

    def test_code_in_prose_and_fallback_cannot_leak(self):
        for text in ['```c\nint main(){}\n```', '#include <stdio.h>\nint main(){}', '']:
            result = hint_response({'independent_ai_answer': {'chat_answer': text, 'code_solution': 'secret'}}, 'bn')
            self.assertNotIn('main', result['direct_answer'])
            self.assertEqual(result['independent_ai_answer']['code_solution'], '')
