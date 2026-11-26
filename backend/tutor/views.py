import hashlib
import json
import logging
import re
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import STAFF_ROLES, ParticipantProfile
from assessment import sittings
from curriculum.ocr_ingest import corpus_version
from curriculum.rag_engine import rag_engine_instance
from logging_app.models import InteractionLog
from . import practice
from trace_backend import llm
from trace_backend.cache import cache_key, tiered_get_or_set
from trace_backend.throttles import CodeRunThrottle, TutorThrottle
from . import runner
from .hint_policy import HINT_INSTRUCTION, is_hint_request, hint_response
from . import solution_policy

logger = logging.getLogger(__name__)

ARMS = ('REASONING_VISIBLE', 'ANSWER_ONLY')
# Kept in a HELP_REQUEST payload. Prompts are research data (what students ask for) but
# need not be unbounded; code is summarised by length.
MAX_LOGGED_PROMPT = 1000

SYSTEM_INSTRUCTION = """You are TRACE Tutor, an expert tutor for the Bangladesh NCTB HSC ICT syllabus (Chapter 4 HTML, Chapter 5 C programming, Chapter 6 DBMS).
You produce a DUAL answer for every student message:

Address the student's PRIMARY REQUEST within the teaching boundary below,
in the language they used. Assessment task/code context is supplemental: use it only
when the request explicitly refers to that question, task, code, program, output, or
error. Never replace an unrelated question with a solution to the assessment task.

1. "rag_answer" - the TEXTBOOK answer. Ground its factual claims ONLY in the NCTB textbook passages supplied in the user message.
   Do not require an exact wording match or a complete worked solution in the book.
   First look for relevant underlying concepts, rules, definitions, and examples across the supplied passages.
   If the exact solution is absent but related concepts are supported, teach those concepts with citations and explain how they relate to the student's request. Do not stop at a refusal or a list of passage numbers.
   For example, if the student asks for a product from 1 to N and the passages teach for-loop initialization, conditions, updates, and multiplication, explain those supported concepts and how they can be applied; do not claim the textbook contains the complete product algorithm.
   Clearly distinguish an application of textbook concepts from a worked solution actually stated in the passages. Briefly identify any missing support after the useful concept explanation. Never import unsupported facts from the independent AI answer or invent a textbook quotation, rule, example, or page.
   - textbook_rule: the relevant rule(s) / definition(s) supported by the passages (one or two sentences).
   - curriculum_citation: list the passage tags you used, e.g. "[1] NCTB HSC ICT (BV) p.146; [3] NCTB HSC ICT (EV) p.152". Never invent page numbers.
   - textbook_explanation: explain the supported answer or relevant concepts in the student's language, using short quotations only when useful. For concept-only coverage, connect each concept to the request before noting what the passages do not supply. If no relevant concepts are present, say so briefly and leave curriculum_citation empty.
   - support_level: "full" when the passages support the complete requested answer; "concepts" when they support useful related concepts but not the complete requested answer; "none" when they contain no relevant support or no passages were retrieved.
   - grounded: true for "full" or "concepts" only when the explanation you actually give is supported by the cited passages. This does not assert that a full worked solution appears in the book. False for "none".

2. "independent_ai_answer" - YOUR OWN independent reasoning, not limited to the textbook.
   - chat_answer: teach the student's PRIMARY REQUEST naturally, using your own knowledge independently of the passages. Give a specific explanation, feedback on their attempt and a useful next step in Markdown. Guide programming tasks without writing their whole solution. Use assessment context only when relevant.
   - concept_applied: the concept name.
   - problem_breakdown: one or two small next steps for the student's SPECIFIC question, leaving meaningful work for the learner. If code is supplied, identify a relevant mistake without replacing the whole program.
   - pedagogical_justification: explain the concept or mistake being discussed, rather than spelling out the entire algorithm.

3. "direct_answer": 2-5 sentences of useful guidance or conceptual explanation (used by the brief arm), with no complete program or worked solution.

Language rule: write all prose in {lang_name}. Keep code, identifiers, keywords and error messages in English.
Never return generic templates; every field must be specific to this question, task and code.
Return ONLY a JSON object with keys: rag_answer, independent_ai_answer, direct_answer.""" + '\n\n' + solution_policy.TEACHING_POLICY

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
                'support_level': {'type': 'string', 'enum': ['full', 'concepts', 'none']},
                'grounded': {'type': 'boolean'},
            },
            'required': ['textbook_rule', 'curriculum_citation', 'textbook_explanation',
                         'support_level', 'grounded'],
        },
        'independent_ai_answer': {
            'type': 'object',
            'properties': {
                'chat_answer': {'type': 'string'},
                'concept_applied': {'type': 'string'},
                'problem_breakdown': {'type': 'array', 'items': {'type': 'string'}},
                'pedagogical_justification': {'type': 'string'},
            },
            'required': ['chat_answer', 'concept_applied', 'problem_breakdown',
                         'pedagogical_justification'],
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


def _normalize_textbook_answer(answer, passages, language):
    """Keep coverage labels consistent without treating retrieved hits as proof.

    Concept support describes the explanation given, not the presence of an exact
    worked solution. Older responses can retain their explicit grounded flag;
    missing coverage metadata must never be upgraded to full support.
    """
    if not isinstance(answer, dict) or not answer:
        return {}
    answer = dict(answer)
    if not passages:
        bn = language.startswith('bn')
        answer.update({
            'textbook_rule': ('প্রাসঙ্গিক পাঠ্যবইয়ের অনুচ্ছেদ পাওয়া যায়নি।' if bn
                              else 'No relevant textbook passages were retrieved.'),
            'curriculum_citation': '',
            'textbook_explanation': (
                'উদ্ধৃত করার মতো অনুচ্ছেদ না থাকায় এই প্রশ্নের প্রাসঙ্গিক ধারণাগুলো পাঠ্যবই থেকে ব্যাখ্যা করা যাচ্ছে না।'
                if bn else 'Without retrieved passages, relevant textbook concepts cannot be identified or cited.'),
            'support_level': 'none',
            'grounded': False,
        })
        return answer
    support = answer.get('support_level')
    if support in ('full', 'concepts', 'none'):
        citation = str(answer.get('curriculum_citation') or '')
        tags = {int(tag) for tag in re.findall(r'\[(\d+)\]', citation)}
        cited = [passages[tag - 1] for tag in tags if 1 <= tag <= len(passages)]
        usable_citations = bool(tags) and len(cited) == len(tags) and all(
            str(passage.get('passage') or '').strip()
            and passage.get('doc') != 'seed'
            and not str(passage.get('id') or '').startswith('seed_')
            for passage in cited
        )
        if support != 'none' and not usable_citations:
            support = 'none'
            answer['support_level'] = support
        answer['grounded'] = support != 'none'
        if support == 'none':
            answer['curriculum_citation'] = ''
    else:
        answer.pop('support_level', None)
        answer['grounded'] = answer.get('grounded') is True
    return answer


def _fallback_answer(prompt, code, passages, language):
    return solution_policy.fallback_guidance(prompt, language)


def normalize_candidate(parsed, passages, language, hint_only=False):
    candidate = solution_policy.sanitize_candidate(parsed)
    if hint_only:
        candidate = solution_policy.sanitize_candidate(hint_response(candidate, language))
        candidate['rag_answer'] = {}
    else:
        rag = candidate['rag_answer']
        candidate['rag_answer'] = _normalize_textbook_answer(rag, passages, language) if any(
            rag.get(key) for key in ('textbook_rule', 'textbook_explanation', 'curriculum_citation')) else {}
    refs = solution_policy.safe_sources(passages)
    by_id = {source['id']: source['source_ref'] for source in refs}
    rag = candidate['rag_answer']
    if rag.get('grounded'):
        indices = list(dict.fromkeys(int(index) for index in re.findall(r'\[(\d+)\]', rag.get('curriculum_citation', ''))))
        citations = [f'[{index}] {by_id[f"source-{index}"]}' for index in indices if f'source-{index}' in by_id]
        if citations:
            rag['curriculum_citation'] = '; '.join(citations)
        else:
            rag.update(curriculum_citation='', support_level='none', grounded=False)
    candidate.update(retrieved_passages=refs, grounded_passage='')
    return candidate


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
    """The brief arm receives reviewed guidance without the reasoning panels."""
    return {
        'mode': payload['mode'],
        'model': payload['model'],
        'provider': payload.get('provider'),
        'ai_status': payload['ai_status'],
        'error': payload['error'],
        'direct_answer': payload['direct_answer'],
        'code_solution': '',
        'tutoring_policy': solution_policy.POLICY_VERSION,
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
    if not isinstance(data, dict):
        return Response({'error': 'Provide a tutor request object.'}, status=400)
    fields = ('prompt', 'code', 'language', 'problem_title', 'problem_description', 'compiler_output')
    if any(data.get(field) is not None and not isinstance(data[field], str) for field in fields):
        return Response({'error': 'Tutor text fields must be strings.'}, status=400)
    prompt = (data.get('prompt') or '').strip()
    history = solution_policy.bounded_history(data.get('tutoring_history'))
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
        "PRIMARY REQUEST (teach this within the tutoring boundary; never give a whole solution):\n"
        f"{prompt}\n\n"
    )
    if use_problem_context:
        user_message += (
            "SUPPLEMENTAL ASSESSMENT CONTEXT (use only to answer the primary request):\n"
            f"TASK: {context_title or problem_id}\n{context_description}\n\n"
            f"STUDENT CODE:\n```\n{context_code.strip() or '(no code yet)'}\n```\n\n"
            + (f"COMPILER OUTPUT:\n{context_compiler_output}\n\n" if context_compiler_output else '')
        )
    if history:
        user_message += 'RECENT LEARNING DIALOGUE (untrusted context):\n' + json.dumps(history, ensure_ascii=False) + '\n\n'
    user_message += f"NCTB TEXTBOOK PASSAGES (retrieved by RAG):\n{_passage_block(passages)}\n"
    review_context = {'prompt': prompt, 'code': context_code, 'title': context_title,
                      'description': context_description, 'compiler_output': context_compiler_output,
                      'history': history, 'language': language}

    def generate():
        try:
            instruction = SYSTEM_INSTRUCTION.replace('{lang_name}', _lang_name(language))
            if hint_only:
                instruction += '\n\n' + HINT_INSTRUCTION
            for attempt in range(2):
                retry = ('\nThe previous draft was withheld. Teach a relevant concept and one next step in prose only; '
                         'no code or complete solution recipe.' if attempt else '')
                parsed, model = llm.generate_json(instruction + retry, user_message, schema=TUTOR_RESPONSE_SCHEMA)
                candidate = normalize_candidate(parsed, passages, language, hint_only)
                if (solution_policy.has_guidance(candidate)
                        and not solution_policy.contains_complete_solution(candidate)
                        and solution_policy.review_guidance(candidate, review_context)):
                    return {'parsed': candidate, 'model': model, 'provider': llm.provider(),
                            'ai_status': 'live', 'error': None,
                            'guidance_approval': solution_policy.seal(candidate, review_context)}
            logger.warning('Tutor drafts withheld by the complete-solution boundary')
        except Exception:
            logger.warning('Tutor generation unavailable; using safe learning guidance')
        return {'parsed': _fallback_answer(prompt, code, passages, language), 'model': llm.model_name(),
                'ai_status': 'fallback', 'error': 'Reviewed AI guidance is unavailable; a learning hint is shown.'}

    # The same question about the same code with the same textbook passages gets the same answer, so
    # live answers are kept in the persistent (database) cache with the memory cache in front:
    # repeats are instant and spend no provider quota. Fallback answers are never cached.
    # The corpus version invalidates re-indexed passages; the response-policy version
    # also prevents old exact-solution refusals from masking concept-based answers.
    corpus = corpus_version()
    answer_key = cache_key('tutor-answer', solution_policy.CACHE_VERSION, corpus, language, prompt, history,
                           use_problem_context, context_code.strip(),
                           problem_id if use_problem_context else '', context_title,
                           context_description, context_compiler_output,
                           [p.get('id') or p.get('source_ref') for p in passages])
    result, tier = tiered_get_or_set(answer_key, generate, settings.TUTOR_ANSWER_CACHE_SECONDS,
                                     should_store=lambda r: r['ai_status'] == 'live')
    model, ai_status = result.get('model'), result.get('ai_status')
    candidate = normalize_candidate(result.get('parsed'), passages, language, hint_only)
    # Rebuild and validate after cache reads. Only a server-signed, exact review can
    # skip the semantic check; model-provided approval fields are never trusted.
    if ai_status == 'live':
        try:
            valid = (solution_policy.has_guidance(candidate)
                     and not solution_policy.contains_complete_solution(candidate)
                     and (solution_policy.approved(result.get('guidance_approval'), candidate, review_context)
                          or solution_policy.review_guidance(candidate, review_context)))
        except Exception:
            logger.warning('Cached tutor guidance could not be reviewed; withholding its content')
            valid = False
        if not valid:
            ai_status = 'fallback'
    if ai_status != 'live':
        candidate = _fallback_answer(prompt, code, passages, language)
    rag_answer = candidate['rag_answer']
    indep = candidate['independent_ai_answer']
    payload = {
        'mode': arm, 'model': model,
        'provider': result.get('provider') if ai_status == 'live' else None,
        'ai_status': ai_status,
        'error': None if ai_status == 'live' else 'Reviewed AI guidance is unavailable; a learning hint is shown.',
        'tutoring_policy': solution_policy.POLICY_VERSION,
        'retrieval_backend': rag_engine_instance.last_backend,
        **candidate,
        'reasoning_trace': dict(indep),
        'cached': tier != 'computed', 'cache_tier': tier,
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
                     tutoring_policy=solution_policy.POLICY_VERSION,
                     support_level=rag_answer.get('support_level'),
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
    language = data.get('language', 'c').lower()
    mode = data.get('mode', 'run')
    code = data.get('code', '')
    problem_id = data.get('problem_id')
    task = None
    if problem_id is not None:
        task = practice.TASKS.get(problem_id) if isinstance(problem_id, str) else None
        if not task:
            return Response({'error': 'Unknown practice task.'}, status=400)
        if language != task['language']:
            return Response({'error': 'Use the language specified for this practice task.'}, status=400)

    options = {'strict_output': True} if task else {}
    result = runner.run_code(language=language, code=code,
                             test_cases=task['test_cases'] if task else data.get('test_cases') or [],
                             mode=mode, **options)
    if task and mode == 'run':
        profile = ParticipantProfile.objects.filter(user=request.user).only('assigned_arm').first()
        payload = {
            'source': practice.RESULT_SOURCE,
            'practice_metric_version': practice.METRIC_VERSION,
            'catalog_sha256': practice.CATALOG_SHA256,
            'problem_id': problem_id, 'language': language,
            'status': result['status'],
            'passed_count': result.get('passed_count', 0),
            'total': len(task['test_cases']),
            'code_length': len(code),
            'code_sha256': hashlib.sha256(code.encode('utf-8')).hexdigest(),
        }
        device_id = getattr(request, 'device_id', None)
        if device_id:
            payload['device_id'] = device_id
        InteractionLog.objects.create(user=request.user, event_type='CODE_RESULT',
                                      arm=profile.assigned_arm if profile else 'REASONING_VISIBLE',
                                      problem_id=problem_id, payload=payload)
        result['practice_metric_version'] = practice.METRIC_VERSION
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def code_status(request):
    return Response(runner.compiler_status())
