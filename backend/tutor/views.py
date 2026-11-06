import logging
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import STAFF_ROLES, ParticipantProfile
from assessment import sittings
from curriculum.ocr_ingest import corpus_version
from curriculum.rag_engine import rag_engine_instance
from logging_app.models import InteractionLog
from trace_backend import llm
from trace_backend.cache import cache_key, tiered_get_or_set
from trace_backend.throttles import CodeRunThrottle, TutorThrottle
from . import runner
from .hint_policy import HINT_INSTRUCTION, is_hint_request, hint_response

logger = logging.getLogger(__name__)

ARMS = ('REASONING_VISIBLE', 'ANSWER_ONLY')
# Kept in a HELP_REQUEST payload. Prompts are research data (what students ask for) but
# need not be unbounded; code is summarised by length.
MAX_LOGGED_PROMPT = 1000

SYSTEM_INSTRUCTION = """You are TRACE Tutor, an expert tutor for the Bangladesh NCTB HSC ICT syllabus (Chapter 4 HTML, Chapter 5 C programming, Chapter 6 DBMS).
You produce a DUAL answer for every student message:

The student's PRIMARY REQUEST is authoritative. Answer exactly what the student asked,
in the language they used. Assessment task/code context is supplemental: use it only
when the request explicitly refers to that question, task, code, program, output, or
error. Never replace an unrelated question with a solution to the assessment task.

1. "rag_answer" - the TEXTBOOK answer. It must be grounded ONLY in the NCTB textbook passages supplied in the user message.
   - textbook_rule: the rule / definition the textbook states that applies to the student's question (one or two sentences).
   - curriculum_citation: list the passage tags you used, e.g. "[1] NCTB HSC ICT (BV) p.146; [3] NCTB HSC ICT (EV) p.152". Never invent page numbers.
   - textbook_explanation: explain the answer using the passages, quoting short phrases from them. If the passages do not cover the question, say so honestly and set grounded=false.
   - grounded: true only if the passages actually support the answer.

2. "independent_ai_answer" - YOUR OWN independent reasoning, not limited to the textbook.
   - chat_answer: answer the student's PRIMARY REQUEST the way a top AI chat assistant would, using your full knowledge and ignoring the passages. A natural, complete, direct reply in Markdown: short paragraphs, bullet points where they help, fenced code blocks (```c or ```html) for code, no headings. Address the exact request first. Use assessment context only when it is relevant to that request.
   - concept_applied: the concept name.
   - problem_breakdown: 3-6 numbered steps that answer the student's SPECIFIC question. If student code is supplied, examine it line by line and point out any bug with the line number.
   - pedagogical_justification: why this logic is correct and the common mistakes to avoid.
   - code_solution: when the primary request asks for code or refers to the assessment task, provide a relevant complete program (C with #include <stdio.h> and int main, or full HTML). For a conceptual question that does not need code, return an empty string. Never solve an unrelated assessment task here.

3. "direct_answer": 2-5 sentences that directly answer the question (used by the answer-only mode).

Language rule: write all prose in {lang_name}. Keep code, identifiers, keywords and error messages in English.
Never return generic templates; every field must be specific to this question, task and code.
Return ONLY a JSON object with keys: rag_answer, independent_ai_answer, direct_answer."""

# The shape the model is held to. Gemini decodes against this schema, so a quote in a
# printf or a newline in a program can no longer leave the reply unparseable - which used
# to turn the whole tutor turn into the textbook-only fallback.
TUTOR_RESPONSE_SCHEMA = {
    'type': 'object',
    'properties': {
        'rag_answer': {
            'type': 'object',
            'properties': {
                'textbook_rule': {'type': 'string'},
                'curriculum_citation': {'type': 'string'},
                'textbook_explanation': {'type': 'string'},
                'grounded': {'type': 'boolean'},
            },
            'required': ['textbook_rule', 'curriculum_citation', 'textbook_explanation', 'grounded'],
        },
        'independent_ai_answer': {
            'type': 'object',
            'properties': {
                'chat_answer': {'type': 'string'},
                'concept_applied': {'type': 'string'},
                'problem_breakdown': {'type': 'array', 'items': {'type': 'string'}},
                'pedagogical_justification': {'type': 'string'},
                'code_solution': {'type': 'string'},
            },
            'required': ['chat_answer', 'concept_applied', 'problem_breakdown',
                         'pedagogical_justification', 'code_solution'],
        },
        'direct_answer': {'type': 'string'},
    },
    'required': ['rag_answer', 'independent_ai_answer', 'direct_answer'],
}

# Which panel view the student asked from. Kept in the HELP_REQUEST payload: whether a
# participant reaches for the textbook answer or the free AI answer is behavioural data.
TUTOR_VIEWS = ('dual', 'rag', 'independent')


def _lang_name(code):
    return 'Bangla (বাংলা)' if (code or 'bn').lower().startswith('bn') else 'English'


def _passage_block(passages):
    if not passages:
        return '(No textbook passages were retrieved - the RAG index is empty. Say so in rag_answer and set grounded=false.)'
    lines = []
    for i, p in enumerate(passages, 1):
        lines.append(f"[{i}] {p['source_ref']} | {p['chapter']}\n{p['passage'].strip()}")
    return '\n\n'.join(lines)


# Below this similarity the top passage is a keyword-overlap or seed-passage fallback, not a
# retrieval hit, and the offline answer must not present it as textbook grounding.
FALLBACK_GROUNDED_MIN_SIMILARITY = 0.5


def _fallback_answer(prompt, code, passages, language):
    top = passages[0] if passages else None
    bn = language == 'bn'
    return {
        'rag_answer': {
            'textbook_rule': top['chapter'] if top else ('পাঠ্যবই থেকে কোনো অনুচ্ছেদ পাওয়া যায়নি' if bn else 'No textbook passage retrieved'),
            'curriculum_citation': f"[1] {top['source_ref']}" if top else 'RAG index empty',
            'textbook_explanation': top['passage'][:700] if top else ('RAG ইনডেক্স এখনো তৈরি হয়নি।' if bn else 'The RAG index has not been built yet.'),
            'grounded': bool(top) and float(top.get('similarity_score') or 0) >= FALLBACK_GROUNDED_MIN_SIMILARITY,
        },
        'independent_ai_answer': {
            'chat_answer': '',
            'concept_applied': prompt[:60] or 'C programming',
            'problem_breakdown': [
                ('AI মডেল উত্তর দিতে পারেনি, তাই এখানে কেবল পাঠ্যবইয়ের অনুচ্ছেদ দেখানো হচ্ছে।' if bn else 'The AI model did not respond, so only the textbook passage is shown.'),
                ('আপনার কোডটি কম্পাইল করে Problems ট্যাবে ত্রুটিগুলো দেখুন।' if bn else 'Compile your code and review the Problems tab for errors.'),
            ],
            'pedagogical_justification': '',
            'code_solution': code or '',
        },
        'direct_answer': ('AI সহকারী এখন উপলব্ধ নয়। পাঠ্যবইয়ের অনুচ্ছেদটি দেখুন।' if bn else 'The AI assistant is unavailable right now. See the textbook passage.'),
    }


def resolve_arm(user, requested=None):
    """The tutor mode this caller is entitled to.

    For a participant that is the arm on their profile - the client's claim is ignored,
    because the arm decides what the response contains and a request body is the one
    thing a curious student can edit. Staff (who are not observations) may name an arm
    to preview either condition.
    """
    profile = ParticipantProfile.objects.filter(user=user).only('role', 'assigned_arm').first()
    if profile is None:
        return 'REASONING_VISIBLE'
    if profile.role in STAFF_ROLES and requested in ARMS:
        return requested
    return profile.assigned_arm if profile.assigned_arm in ARMS else 'REASONING_VISIBLE'


def answer_only_payload(payload):
    """What the control arm receives: the direct answer and the code fix, nothing that
    shows the working. The dual answer is generated and cached once for both arms and
    reduced here, after the cache read, so the two conditions differ only in what is
    shown - not in the model call that produced it."""
    indep = payload.get('independent_ai_answer') or {}
    return {
        'mode': payload['mode'],
        'model': payload['model'],
        'provider': payload.get('provider'),
        'ai_status': payload['ai_status'],
        'error': payload['error'],
        'direct_answer': payload['direct_answer'],
        'code_solution': indep.get('code_solution') or '',
        'cached': payload['cached'],
        'cache_tier': payload['cache_tier'],
    }


def _log_tutor_event(user, event_type, arm, problem_id, prompt, code, language, **detail):
    """The server's own record of a tutor turn: what was asked, in which mode, during
    which paper, and whether the answer was live, cached or a fallback. The browser used
    to post this itself, which meant a page that forgot to (the assessment chat did) left
    the dependency measure without its main input.

    An answered turn is a HELP_REQUEST (the dependency covariate). A turn refused because
    a no-AI paper is open is a HELP_BLOCKED - kept in the record as an attempted use, but
    a distinct event so it never inflates the help-request count."""
    try:
        payload = {
            'prompt': prompt[:MAX_LOGGED_PROMPT],
            'code_length': len(code or ''),
            'language': language,
            **detail,
        }
        InteractionLog.objects.create(user=user, event_type=event_type, arm=arm,
                                      problem_id=str(problem_id or '')[:50] or None, payload=payload)
    except Exception:  # noqa: BLE001 - telemetry must never break the answer
        logger.exception('Could not log a %s for user %s', event_type, user.pk)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([TutorThrottle])
def query_tutor(request):
    data = request.data
    prompt = (data.get('prompt') or '').strip()
    hint_only = is_hint_request(prompt)
    code = data.get('code') or ''
    problem_id = data.get('problem_id', 'prob_assessment')
    arm = resolve_arm(request.user, data.get('arm'))
    # Body wins; otherwise the trace_lang cookie set at login/profile update; otherwise Bangla.
    language = (data.get('language') or request.COOKIES.get(settings.LANG_COOKIE_NAME) or 'bn').lower()
    problem_title = data.get('problem_title') or ''
    problem_description = data.get('problem_description') or ''
    compiler_output = data.get('compiler_output') or ''
    use_problem_context = data.get('use_problem_context') is True
    view = data.get('view') if data.get('view') in TUTOR_VIEWS else None

    if not prompt:
        return Response({'error': 'prompt is required'}, status=400)

    # The pre-test is the baseline and the withdrawal task measures dependency: while a
    # participant has either open, the tutor is off - here, not just in the page that
    # hides the chat, so a second tab on the workspace gets the same answer.
    blocking = sittings.blocking_paper(request.user)
    if blocking:
        _log_tutor_event(request.user, 'HELP_BLOCKED', arm, problem_id, prompt, code, language,
                         reason='paper_in_progress', exam_type=blocking)
        return Response({
            'error': ('The AI tutor is unavailable while your '
                      f'{"pre-test" if blocking == "pre" else "withdrawal task"} is in progress. '
                      'Submit the paper first.'),
            'reason': 'paper_in_progress',
            'exam_type': blocking,
        }, status=403)

    context_title = problem_title if use_problem_context else ''
    context_description = problem_description if use_problem_context else ''
    context_code = code if use_problem_context else ''
    context_compiler_output = compiler_output if use_problem_context else ''

    # A standalone question such as "Where is <br> used?" must retrieve for that
    # question, not for the unrelated assessment item currently visible beside chat.
    retrieval_query = ' '.join(x for x in [prompt, context_title] if x)
    passages = rag_engine_instance.retrieve(retrieval_query, k=5)

    user_message = (
        "PRIMARY REQUEST (answer this directly; do not substitute another task):\n"
        f"{prompt}\n\n"
    )
    if use_problem_context:
        user_message += (
            "SUPPLEMENTAL ASSESSMENT CONTEXT (use only to answer the primary request):\n"
            f"TASK: {context_title or problem_id}\n{context_description}\n\n"
            f"STUDENT CODE:\n```\n{context_code.strip() or '(no code yet)'}\n```\n\n"
            + (f"COMPILER OUTPUT:\n{context_compiler_output}\n\n" if context_compiler_output else '')
        )
    user_message += f"NCTB TEXTBOOK PASSAGES (retrieved by RAG):\n{_passage_block(passages)}\n"

    def generate():
        try:
            instruction = SYSTEM_INSTRUCTION.replace('{lang_name}', _lang_name(language))
            if hint_only:
                instruction += '\n\n' + HINT_INSTRUCTION
            parsed, model = llm.generate_json(instruction,
                                              user_message, schema=TUTOR_RESPONSE_SCHEMA)
            if not isinstance(parsed, dict) or 'independent_ai_answer' not in parsed:
                raise ValueError('The model returned an unexpected JSON shape')
            return {'parsed': parsed, 'model': model, 'provider': llm.provider(),
                    'ai_status': 'live', 'error': None}
        except Exception as e:
            logger.warning(f'Tutor model call ({llm.provider()}) failed: {e}')
            return {'parsed': _fallback_answer(prompt, code, passages, language), 'model': llm.model_name(),
                    'ai_status': 'fallback', 'error': str(e)[:400]}

    # The same question about the same code with the same textbook passages gets the same answer, so
    # live answers are kept in the persistent (database) cache with the memory cache in front:
    # repeats are instant and spend no Gemini quota. Fallback answers are never cached.
    # 'v3': the key also carries the corpus version (the last completed ingestion run), so an
    # answer built on passages whose text or labels have since been re-indexed is never reused.
    corpus = corpus_version()
    answer_key = cache_key('tutor-answer', 'v5-hint-policy', corpus, language, prompt,
                           use_problem_context, context_code.strip(),
                           problem_id if use_problem_context else '', context_title,
                           context_description, context_compiler_output,
                           [p.get('id') or p.get('source_ref') for p in passages])
    result, tier = tiered_get_or_set(answer_key, generate, settings.TUTOR_ANSWER_CACHE_SECONDS,
                                     should_store=lambda r: r['ai_status'] == 'live')
    parsed, model, ai_status, error = result['parsed'], result['model'], result['ai_status'], result['error']
    if hint_only:
        parsed = hint_response(parsed, language)

    rag_answer = parsed.get('rag_answer') or {}
    rag_answer.setdefault('grounded', bool(passages))
    indep = parsed.get('independent_ai_answer') or {}
    breakdown = indep.get('problem_breakdown') or []
    if isinstance(breakdown, str):
        breakdown = [breakdown]
    indep['problem_breakdown'] = [line.strip() for item in breakdown for line in str(item).split('\n') if line.strip()]
    indep['chat_answer'] = str(indep.get('chat_answer') or '').strip()
    direct = parsed.get('direct_answer') or ''

    payload = {
        'mode': arm,
        'model': model,
        # Cached answers retain the provider recorded when generated. Legacy cache
        # entries have no provider; never infer it from today's configuration.
        'provider': result.get('provider') if ai_status == 'live' else None,
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
    if arm == 'ANSWER_ONLY':
        payload = answer_only_payload(payload)

    _log_tutor_event(request.user, 'HELP_REQUEST', arm, problem_id, prompt, code, language,
                     ai_status=ai_status, cache_tier=tier, model=model, view=view,
                     use_problem_context=use_problem_context,
                     exam_type=sittings.open_paper_of(request.user),
                     # Which corpus state and which passages grounded this turn, so the answer a
                     # participant saw can be reconstructed after the corpus has moved on.
                     corpus_version=corpus,
                     passage_ids=[p.get('id') or p.get('source_ref') for p in passages],
                     retrieval_backend=rag_engine_instance.last_backend,
                     grounded=bool(rag_answer.get('grounded')))
    response = Response(payload)
    response['X-Trace-Cache'] = 'miss' if tier == 'computed' else f'hit-{tier}'
    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([CodeRunThrottle])
def run_code(request):
    """Validate the request before compiling/running under the required sandbox tier."""
    data = request.data
    if not isinstance(data, dict):
        return Response({'error': 'Provide a code execution request object.'}, status=400)
    errors = {}
    for field, default in (('language', 'c'), ('code', ''), ('mode', 'run')):
        if not isinstance(data.get(field, default), str):
            errors[field] = 'Must be a string.'
    if isinstance(data.get('mode', 'run'), str) and data.get('mode', 'run') not in ('run', 'check'):
        errors['mode'] = 'Choose run or check.'
    cases = data.get('test_cases')
    if cases is not None:
        if not isinstance(cases, list):
            errors['test_cases'] = 'Must be a list of test case objects.'
        else:
            for index, case in enumerate(cases):
                if not isinstance(case, dict):
                    errors[f'test_cases.{index}'] = 'Must be a test case object.'
                    continue
                for field in ('input', 'output', 'selector'):
                    if field in case and case[field] is not None and not isinstance(case[field], str):
                        errors[f'test_cases.{index}.{field}'] = 'Must be a string.'
    if errors:
        return Response({'error': 'Invalid code execution request.', 'fields': errors}, status=400)
    result = runner.run_code(
        language=data.get('language', 'c'),
        code=data.get('code', ''),
        test_cases=data.get('test_cases') or [],
        mode=data.get('mode', 'run'),
    )
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def code_status(request):
    return Response(runner.compiler_status())
