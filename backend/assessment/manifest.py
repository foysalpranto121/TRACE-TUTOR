"""The study manifest: exactly which configuration produced a dataset.

A result is only reproducible if you can say which model answered the tutor turns, at
what temperature, with which fallbacks, under which switching policy, against which
version of the item bank and which revision of the code. Those live in six different
places; this collects them into one JSON document to file with the exported dataset.
"""
import hashlib
import platform
import subprocess
import sys
from importlib import metadata

from django.conf import settings
from django.utils import timezone

from trace_backend import gemini

from . import scoring

PACKAGES = ('Django', 'djangorestframework', 'google-genai', 'chromadb', 'ziglang', 'html5lib')


def _git(*args):
    try:
        result = subprocess.run(['git', *args], cwd=settings.BASE_DIR.parent,
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _item_bank():
    try:
        raw = scoring.ITEM_BANK_PATH.read_bytes()
    except OSError:
        return {'path': str(scoring.ITEM_BANK_PATH), 'sha256': None, 'items': None}
    try:
        count = len(scoring.all_items())
    except scoring.ItemBankError:
        count = None
    return {'path': scoring.ITEM_BANK_PATH.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'items': count}


def _versions():
    out = {'python': sys.version.split()[0], 'platform': platform.platform()}
    for name in PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def build():
    from tutor import sandbox
    from trace_backend import llm
    dirty = _git('status', '--porcelain')
    return {
        'generated_at': timezone.now().isoformat(),
        'code': {
            'commit': _git('rev-parse', 'HEAD'),
            'branch': _git('rev-parse', '--abbrev-ref', 'HEAD'),
            'uncommitted_changes': bool(dirty) if dirty is not None else None,
        },
        'tutor': {
            'provider': llm.provider(),
            'model': llm.model_name(),
            'model_chain': llm.model_chain(),
            'temperature': llm.generation_temperature(),
            # Parameters the model refused in this process (GPT-5-class models reject
            # temperature): the configured value above was NOT applied for those models.
            'parameters_rejected_by_model': llm.rejected_parameters(),
            'embedding_model': gemini.embed_model_name(),
            'embedding_dimensions': gemini.EMBED_DIMENSIONS,
            'answer_cache_seconds': settings.TUTOR_ANSWER_CACHE_SECONDS,
        },
        'protocol': {
            'arm_switch_policy': settings.ARM_SWITCH_POLICY,
            'no_ai_papers': list(getattr(settings, 'NO_AI_PAPERS', ('pre', 'withdrawal'))),
            'paper_sitting_ttl_hours': getattr(settings, 'PAPER_SITTING_TTL_HOURS', 4),
            'grading_mode': settings.GRADING_MODE,
        },
        'execution': {
            'sandbox_tier': sandbox.status()['tier'],
            'sandbox_required': sandbox.required(),
            'sandbox_min_tier': sandbox.minimum_tier() if sandbox.required() else None,
            'sandbox_allowed': sandbox.status()['allowed'],
            'debug': settings.DEBUG,
        },
        'item_bank': _item_bank(),
        'versions': _versions(),
    }
