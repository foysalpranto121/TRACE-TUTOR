import os
import re
import json
import logging

logger = logging.getLogger(__name__)

_client = None


def api_key():
    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('AGENT_API_KEY') or ''
    if not key or key.startswith('YOUR_'):
        return None
    return key


def model_name():
    return os.environ.get('GEMINI_MODEL', 'gemini-3.6-flash')


def embed_model_name():
    return os.environ.get('GEMINI_EMBED_MODEL', 'gemini-embedding-001')


EMBED_DIMENSIONS = int(os.environ.get('GEMINI_EMBED_DIMENSIONS', '768'))


def get_client():
    global _client
    if _client is not None:
        return _client
    key = api_key()
    if not key:
        return None
    from google import genai
    _client = genai.Client(api_key=key)
    return _client


def _strip_code_fence(text):
    t = (text or '').strip()
    if t.startswith('```'):
        t = t.split('\n', 1)[1] if '\n' in t else ''
        if t.rstrip().endswith('```'):
            t = t.rstrip()[:-3]
    return t.strip()


_CONTROL_ESCAPES = {'\n': '\\n', '\r': '\\r', '\t': '\\t'}
_JSON_DELIMITERS = ' \t\r\n,}]'
_NUMBER = re.compile(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?')


def _starts_json_value(t, j):
    """Whether position j begins something that can follow a comma in JSON: a string, an
    object, an array, a number or a literal. `n)` and `5)` do not (that is C after a
    printf), `"next_key"` and `true}` do."""
    if j >= len(t):
        return False
    ch = t[j]
    if ch in '"{[':
        return True
    for literal in ('true', 'false', 'null'):
        if t.startswith(literal, j):
            k = j + len(literal)
            return k >= len(t) or t[k] in _JSON_DELIMITERS
    m = _NUMBER.match(t, j)
    if m:
        return m.end() >= len(t) or t[m.end()] in _JSON_DELIMITERS
    return False


def _closes_string(t, j):
    """Whether a quote at j-1 (inside a string) is its closing quote, judged by what
    follows: a colon, a closing bracket or the end always is; a comma is only when a JSON
    value comes after it."""
    while j < len(t) and t[j] in ' \t\r\n':
        j += 1
    if j >= len(t) or t[j] in ':}]':
        return True
    if t[j] == ',':
        k = j + 1
        while k < len(t) and t[k] in ' \t\r\n':
            k += 1
        # A trailing comma (",}" or ",]") is dropped later; it still ends the string.
        return (k < len(t) and t[k] in '}]') or _starts_json_value(t, k)
    return False


def repair_json(text):
    """Best-effort repair of the JSON a model returns when it drifts from the format.

    The tutor prompt asks for a C program inside a JSON string, and the two ways models
    break that are (a) a real newline instead of "\\n" inside the string and (b) a quote
    character in the code (printf("...")) left unescaped. Both leave the parser stuck in
    the middle of a string value, so the whole tutor turn used to degrade to the
    textbook-only fallback. This walks the text once, tracking whether it is inside a
    string: control characters inside a string are escaped, and a quote inside a string is
    treated as the closing quote only when what follows (after whitespace) is JSON
    structure - a colon, a closing bracket, the end, or a comma followed by a JSON value -
    and escaped otherwise. Trailing commas before a closing bracket are dropped, and prose
    around the object is cut away. It is a heuristic: a C string literal that is itself
    followed by a comma and another string literal (printf("%s", "hi")) still defeats it,
    which is why the schema, not this, is the real fix.
    """
    t = (text or '').strip()
    start, end = t.find('{'), t.rfind('}')
    if start == -1 or end == -1 or end < start:
        raise ValueError('no JSON object in the response')
    t = t[start:end + 1]
    out = []
    in_string = False
    i, n = 0, len(t)
    while i < n:
        ch = t[i]
        if in_string:
            if ch == '\\':
                out.append(t[i:i + 2])
                i += 2
                continue
            if ch == '"':
                if _closes_string(t, i + 1):
                    in_string = False
                    out.append(ch)
                else:
                    out.append('\\"')
                i += 1
                continue
            out.append(_CONTROL_ESCAPES.get(ch, ch if ch >= ' ' else ''))
            i += 1
            continue
        if ch == '"':
            in_string = True
        elif ch == ',':
            j = i + 1
            while j < n and t[j] in ' \t\r\n':
                j += 1
            if j < n and t[j] in '}]':
                i += 1
                continue
        out.append(ch)
        i += 1
    return json.loads(''.join(out))


def parse_json_response(text):
    """json.loads with the repair pass behind it. Raises ValueError when neither works."""
    text = _strip_code_fence(text)
    if not text:
        raise RuntimeError('Gemini returned an empty response')
    try:
        return json.loads(text)
    except json.JSONDecodeError as first:
        try:
            parsed = repair_json(text)
        except (ValueError, json.JSONDecodeError):
            raise ValueError(f'Gemini returned malformed JSON: {first}') from first
        logger.warning('Gemini returned malformed JSON (%s); repaired it', first)
        return parsed


def model_chain():
    """Primary model, followed by any configured fallbacks.

    Fallbacks are tried when a model is quota-exhausted (429) or unavailable (404/503).
    They default to EMPTY: a participant served by a different model than the rest of the
    cohort is a confound, and a confound that only appears under load is one nobody
    notices until analysis. Opt into availability explicitly with GEMINI_FALLBACK_MODELS
    if you would rather the tutor degrade than fail.
    """
    fallbacks = os.environ.get('GEMINI_FALLBACK_MODELS', '')
    chain = [model_name()] + [m.strip() for m in fallbacks.split(',') if m.strip()]
    seen, out = set(), []
    for m in chain:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _is_quota_or_unavailable(err):
    s = str(err)
    return any(code in s for code in ('429', '503', '404', 'RESOURCE_EXHAUSTED', 'UNAVAILABLE', 'NOT_FOUND'))


def generate_content(contents, config, retries_per_model=2):
    """Try each model in the chain; returns (response, model_used)."""
    import time
    client = get_client()
    if client is None:
        raise RuntimeError('GEMINI_API_KEY is not configured')
    last = None
    for model in model_chain():
        for attempt in range(retries_per_model):
            try:
                return client.models.generate_content(model=model, contents=contents, config=config), model
            except Exception as e:
                last = e
                if not _is_quota_or_unavailable(e):
                    raise
                daily = 'PerDay' in str(e) or 'NOT_FOUND' in str(e)
                if daily or attempt == retries_per_model - 1:
                    logger.warning(f'{model} unavailable ({str(e)[:120]}), trying next model')
                    break
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f'All Gemini models exhausted or unavailable: {str(last)[:300]}')


def generation_temperature():
    """Sampling temperature for tutor turns.

    Zero by default. The tutor is the experimental manipulation, so two participants
    asking the same question about the same code should receive the same explanation;
    at 0.4 they did not, and the variation was invisible in the logs. Raise it only if
    you can argue the variability is part of what you are studying.
    """
    try:
        return float(os.environ.get('GEMINI_TEMPERATURE', '0'))
    except ValueError:
        return 0.0


def generate_json(system_instruction, contents, temperature=None, schema=None):
    """Returns (parsed_json, model_used).

    With a JSON schema the model is held to it by constrained decoding, so the reply is
    valid JSON of the expected shape rather than the model's best effort at one. Without
    a schema, JSON mode alone is requested and the repair pass covers the rest.
    """
    config = {
        'system_instruction': system_instruction,
        'response_mime_type': 'application/json',
        'temperature': generation_temperature() if temperature is None else temperature,
    }
    if schema is not None:
        config['response_json_schema'] = schema
    response, model = generate_content(contents, config)
    return parse_json_response(response.text), model


def generate_text(contents, temperature=0.0, system_instruction=None):
    config = {'temperature': temperature}
    if system_instruction:
        config['system_instruction'] = system_instruction
    response, _ = generate_content(contents, config)
    return response.text or ''


def embed_texts(texts, task_type='RETRIEVAL_DOCUMENT', batch_size=32):
    client = get_client()
    if client is None:
        raise RuntimeError('GEMINI_API_KEY is not configured')
    import time
    from google.genai import types
    vectors = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBED_DIMENSIONS)
        for attempt, wait in enumerate((5, 15, 30, 60, 0)):
            try:
                result = client.models.embed_content(model=embed_model_name(), contents=batch, config=config)
                break
            except Exception as e:
                if not _is_quota_or_unavailable(e) or wait == 0 or 'PerDay' in str(e):
                    raise
                logger.warning(f'Embedding rate-limited ({str(e)[:80]}), retrying in {wait}s')
                time.sleep(wait)
        vectors.extend([list(e.values) for e in result.embeddings])
    return vectors
