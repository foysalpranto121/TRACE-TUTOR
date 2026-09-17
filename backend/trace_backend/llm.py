"""The tutor's generation model, behind one call.

Two providers: OpenAI (chat completions with a strict JSON schema) and Gemini (the
original). Which one answers is `LLM_PROVIDER` - `openai`, `gemini`, or `auto`, which
picks OpenAI whenever an `OPENAI_API_KEY` is configured. Embeddings and OCR are not
routed here: the curriculum index was built with Gemini embeddings and stays on them.

Whatever the provider, the tutor gets the same contract: (parsed_json, model_used),
held to the schema it passed, or an exception the view turns into its fallback answer.
"""
import copy
import logging
import os
import time

from . import gemini

logger = logging.getLogger(__name__)

PROVIDERS = ('openai', 'gemini')
DEFAULT_OPENAI_MODEL = 'gpt-5-mini'

_openai_client = None
# model -> parameters it has rejected in this process (temperature on GPT-5-class models,
# reasoning_effort on older ones). Learned from the first 400 and not sent again, and
# reported in the study manifest so nobody reads "temperature 0" as applied when it was not.
_rejected_params = {}


def rejected_parameters():
    return {model: sorted(names) for model, names in _rejected_params.items()}


def openai_api_key():
    key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    return key or None


def provider():
    """`openai`, `gemini`, or - for `auto` and anything unrecognised - OpenAI when its key
    is configured and Gemini otherwise."""
    wanted = (os.environ.get('LLM_PROVIDER') or 'auto').strip().lower()
    if wanted in PROVIDERS:
        return wanted
    return 'openai' if openai_api_key() else 'gemini'


def model_name():
    if provider() == 'openai':
        return (os.environ.get('OPENAI_MODEL') or DEFAULT_OPENAI_MODEL).strip()
    return gemini.model_name()


def model_chain():
    """Primary model then any configured fallbacks - empty by default, for the reason
    given on gemini.model_chain: a participant served by another model is a confound."""
    if provider() != 'openai':
        return gemini.model_chain()
    fallbacks = os.environ.get('OPENAI_FALLBACK_MODELS', '')
    chain = [model_name()] + [m.strip() for m in fallbacks.split(',') if m.strip()]
    seen, out = set(), []
    for m in chain:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def generation_temperature():
    """LLM_TEMPERATURE, else the older GEMINI_TEMPERATURE, else 0 - see
    gemini.generation_temperature for why zero."""
    raw = os.environ.get('LLM_TEMPERATURE')
    if raw is None:
        return gemini.generation_temperature()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def strict_schema(schema):
    """OpenAI's strict structured output wants every object closed (`additionalProperties:
    false`) and every property required. The tutor schema already requires everything;
    this closes the objects without touching the original, which Gemini still uses."""
    def close(node):
        if isinstance(node, dict):
            if node.get('type') == 'object' and 'properties' in node:
                node.setdefault('additionalProperties', False)
                node['required'] = list(node['properties'].keys())
            for value in node.values():
                close(value)
        elif isinstance(node, list):
            for item in node:
                close(item)
        return node
    return close(copy.deepcopy(schema))


def get_openai_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    key = openai_api_key()
    if not key:
        return None
    from openai import OpenAI
    _openai_client = OpenAI(api_key=key)
    return _openai_client


def _is_quota_or_unavailable(err):
    status = getattr(err, 'status_code', None)
    if status in (404, 429) or (isinstance(status, int) and status >= 500):
        return True
    s = str(err)
    return any(code in s for code in ('429', '503', '404', 'rate_limit', 'insufficient_quota'))


def _unsupported_parameter(err, params):
    """GPT-5-class models reject `temperature`; older ones reject `reasoning_effort`. The
    error names the parameter, so drop it and try again rather than pin the code to one
    model family."""
    if getattr(err, 'status_code', None) != 400:
        return None
    s = str(err)
    for name in params:
        if name in s and ('nsupported' in s or 'not supported' in s or 'does not support' in s):
            return name
    return None


def _openai_generate_json(system_instruction, contents, schema, temperature, retries_per_model=2):
    client = get_openai_client()
    if client is None:
        raise RuntimeError('OPENAI_API_KEY is not configured')
    messages = [{'role': 'system', 'content': system_instruction},
                {'role': 'user', 'content': contents}]
    base_params = {'temperature': temperature}
    effort = (os.environ.get('OPENAI_REASONING_EFFORT') or '').strip().lower()
    if effort:
        base_params['reasoning_effort'] = effort
    if schema is not None:
        base_params['response_format'] = {
            'type': 'json_schema',
            'json_schema': {'name': 'tutor_answer', 'strict': True, 'schema': strict_schema(schema)},
        }
    else:
        base_params['response_format'] = {'type': 'json_object'}

    last = None
    for model in model_chain():
        params = {k: v for k, v in base_params.items() if k not in _rejected_params.get(model, ())}
        attempt = 0
        while attempt < retries_per_model:
            try:
                completion = client.chat.completions.create(model=model, messages=messages, **params)
                choice = completion.choices[0]
                if getattr(choice.message, 'refusal', None):
                    raise RuntimeError(f'{model} refused: {choice.message.refusal[:200]}')
                return gemini.parse_json_response(choice.message.content), model
            except Exception as e:  # noqa: BLE001 - every failure is classified below
                dropped = _unsupported_parameter(e, ('temperature', 'reasoning_effort'))
                if dropped and dropped in params:
                    logger.info('%s does not accept %s; retrying without it', model, dropped)
                    params.pop(dropped)
                    _rejected_params.setdefault(model, set()).add(dropped)
                    continue                      # same attempt, one parameter fewer
                last = e
                if not _is_quota_or_unavailable(e):
                    raise
                attempt += 1
                if attempt >= retries_per_model or getattr(e, 'status_code', None) == 404:
                    logger.warning('%s unavailable (%s), trying next model', model, str(e)[:120])
                    break
                time.sleep(3 * attempt)
    raise RuntimeError(f'All OpenAI models exhausted or unavailable: {str(last)[:300]}')


def generate_json(system_instruction, contents, schema=None, temperature=None):
    """Returns (parsed_json, model_used) from whichever provider is configured."""
    temp = generation_temperature() if temperature is None else temperature
    if provider() == 'openai':
        return _openai_generate_json(system_instruction, contents, schema, temp)
    return gemini.generate_json(system_instruction, contents, temperature=temp, schema=schema)


def configured():
    """Whether the active provider has a key - what the RAG status page reports."""
    return openai_api_key() is not None if provider() == 'openai' else gemini.api_key() is not None
