import logging
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from curriculum.rag_engine import rag_engine_instance
from trace_backend import gemini
from trace_backend.cache import cache_key, tiered_get_or_set
from . import runner

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are TRACE Tutor, an expert tutor for the Bangladesh NCTB HSC ICT syllabus (Chapter 4 HTML, Chapter 5 C programming, Chapter 6 DBMS).
You produce a DUAL answer for every student message:

1. "rag_answer" - the TEXTBOOK answer. It must be grounded ONLY in the NCTB textbook passages supplied in the user message.
   - textbook_rule: the rule / definition the textbook states that applies to the student's question (one or two sentences).
   - curriculum_citation: list the passage tags you used, e.g. "[1] NCTB HSC ICT (BV) p.146; [3] NCTB HSC ICT (EV) p.152". Never invent page numbers.
   - textbook_explanation: explain the answer using the passages, quoting short phrases from them. If the passages do not cover the question, say so honestly and set grounded=false.
   - grounded: true only if the passages actually support the answer.

2. "independent_ai_answer" - YOUR OWN independent reasoning, not limited to the textbook.
   - concept_applied: the concept name.
   - problem_breakdown: 3-6 numbered steps that answer the student's SPECIFIC question. If student code is supplied, examine it line by line and point out any bug with the line number.
   - pedagogical_justification: why this logic is correct and the common mistakes to avoid.
   - code_solution: a complete, compilable program (C with #include <stdio.h> and int main, or full HTML) that solves the task. Use the exact output format the task specifies.

3. "direct_answer": 2-5 sentences that directly answer the question (used by the answer-only mode).

Language rule: write all prose in {lang_name}. Keep code, identifiers, keywords and error messages in English.
Never return generic templates; every field must be specific to this question, task and code.
Return ONLY a JSON object with keys: rag_answer, independent_ai_answer, direct_answer."""


def _lang_name(code):
    return 'Bangla (বাংলা)' if (code or 'bn').lower().startswith('bn') else 'English'


def _passage_block(passages):
    if not passages:
        return '(No textbook passages were retrieved - the RAG index is empty. Say so in rag_answer and set grounded=false.)'
    lines = []
    for i, p in enumerate(passages, 1):
        lines.append(f"[{i}] {p['source_ref']} | {p['chapter']}\n{p['passage'].strip()}")
    return '\n\n'.join(lines)


def _fallback_answer(prompt, code, passages, language):
    top = passages[0] if passages else None
    bn = language == 'bn'
    return {
        'rag_answer': {
            'textbook_rule': top['chapter'] if top else ('পাঠ্যবই থেকে কোনো অনুচ্ছেদ পাওয়া যায়নি' if bn else 'No textbook passage retrieved'),
            'curriculum_citation': f"[1] {top['source_ref']}" if top else 'RAG index empty',
            'textbook_explanation': top['passage'][:700] if top else ('RAG ইনডেক্স এখনো তৈরি হয়নি।' if bn else 'The RAG index has not been built yet.'),
            'grounded': bool(top),
        },
        'independent_ai_answer': {
            'concept_applied': prompt[:60] or 'C programming',
            'problem_breakdown': [
                ('Gemini API উত্তর দিতে পারেনি, তাই এখানে কেবল পাঠ্যবইয়ের অনুচ্ছেদ দেখানো হচ্ছে।' if bn else 'The Gemini API did not respond, so only the textbook passage is shown.'),
                ('আপনার কোডটি কম্পাইল করে Problems ট্যাবে ত্রুটিগুলো দেখুন।' if bn else 'Compile your code and review the Problems tab for errors.'),
            ],
            'pedagogical_justification': '',
            'code_solution': code or '',
        },
        'direct_answer': ('AI সহকারী এখন উপলব্ধ নয়। পাঠ্যবইয়ের অনুচ্ছেদটি দেখুন।' if bn else 'The AI assistant is unavailable right now. See the textbook passage.'),
    }


@api_view(['POST'])
@permission_classes([AllowAny])
def query_tutor(request):
    data = request.data
    prompt = (data.get('prompt') or '').strip()
    code = data.get('code') or ''
    problem_id = data.get('problem_id', 'prob_assessment')
    arm = data.get('arm', 'REASONING_VISIBLE')
    # Body wins; otherwise the trace_lang cookie set at login/profile update; otherwise Bangla.
    language = (data.get('language') or request.COOKIES.get(settings.LANG_COOKIE_NAME) or 'bn').lower()
    problem_title = data.get('problem_title') or ''
    problem_description = data.get('problem_description') or ''
    compiler_output = data.get('compiler_output') or ''

    if not prompt:
        return Response({'error': 'prompt is required'}, status=400)

    retrieval_query = ' '.join(x for x in [prompt, problem_title] if x)
    passages = rag_engine_instance.retrieve(retrieval_query, k=5)

    user_message = (
        f"STUDENT QUESTION: {prompt}\n\n"
        f"TASK: {problem_title or problem_id}\n{problem_description}\n\n"
        f"STUDENT CODE:\n```\n{code.strip() or '(no code yet)'}\n```\n\n"
        + (f"COMPILER OUTPUT:\n{compiler_output}\n\n" if compiler_output else '')
        + f"NCTB TEXTBOOK PASSAGES (retrieved by RAG):\n{_passage_block(passages)}\n"
    )

    def generate():
        try:
            parsed, model = gemini.generate_json(SYSTEM_INSTRUCTION.replace('{lang_name}', _lang_name(language)), user_message)
            if not isinstance(parsed, dict) or 'independent_ai_answer' not in parsed:
                raise ValueError('Gemini returned an unexpected JSON shape')
            return {'parsed': parsed, 'model': model, 'ai_status': 'live', 'error': None}
        except Exception as e:
            logger.warning(f'Gemini tutor call failed: {e}')
            return {'parsed': _fallback_answer(prompt, code, passages, language), 'model': gemini.model_name(),
                    'ai_status': 'fallback', 'error': str(e)[:400]}

    # The same question about the same code with the same textbook passages gets the same answer, so
    # live answers are kept in the persistent (database) cache with the memory cache in front:
    # repeats are instant and spend no Gemini quota. Fallback answers are never cached.
    answer_key = cache_key('tutor-answer', 'v1', language, prompt, code.strip(), problem_id, problem_title,
                           problem_description, compiler_output, [p.get('id') or p.get('source_ref') for p in passages])
    result, tier = tiered_get_or_set(answer_key, generate, settings.TUTOR_ANSWER_CACHE_SECONDS,
                                     should_store=lambda r: r['ai_status'] == 'live')
    parsed, model, ai_status, error = result['parsed'], result['model'], result['ai_status'], result['error']

    rag_answer = parsed.get('rag_answer') or {}
    rag_answer.setdefault('grounded', bool(passages))
    indep = parsed.get('independent_ai_answer') or {}
    breakdown = indep.get('problem_breakdown') or []
    if isinstance(breakdown, str):
        breakdown = [breakdown]
    indep['problem_breakdown'] = [line.strip() for item in breakdown for line in str(item).split('\n') if line.strip()]
    direct = parsed.get('direct_answer') or ''

    payload = {
        'mode': arm,
        'model': model,
        'ai_status': ai_status,
        'error': error,
        'retrieval_backend': rag_engine_instance.last_backend,
        'retrieved_passages': passages,
        'grounded_passage': f"{passages[0]['passage']} [Source: {passages[0]['source_ref']}]" if passages else '',
        'rag_answer': rag_answer,
        'independent_ai_answer': indep,
        'reasoning_trace': indep,
        'direct_answer': direct,
        'cached': tier != 'computed',
        'cache_tier': tier,
    }
    response = Response(payload)
    response['X-Trace-Cache'] = 'miss' if tier == 'computed' else f'hit-{tier}'
    return response


@api_view(['POST'])
@permission_classes([AllowAny])
def run_code(request):
    data = request.data
    result = runner.run_code(
        language=data.get('language', 'c'),
        code=data.get('code', ''),
        test_cases=data.get('test_cases') or [],
        mode=data.get('mode', 'run'),
    )
    return Response(result)


@api_view(['GET'])
@permission_classes([AllowAny])
def code_status(request):
    return Response(runner.compiler_status())
