import os
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


def generate_json(system_instruction, contents, temperature=None):
    """Returns (parsed_json, model_used)."""
    response, model = generate_content(contents, {
        'system_instruction': system_instruction,
        'response_mime_type': 'application/json',
        'temperature': generation_temperature() if temperature is None else temperature,
    })
    text = _strip_code_fence(response.text)
    if not text:
        raise RuntimeError('Gemini returned an empty response')
    return json.loads(text), model


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
