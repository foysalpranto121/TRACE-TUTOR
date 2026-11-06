import os, sys, json
from pathlib import Path
root=Path('/srv/trace-tutor/backend')
sys.path.insert(0,str(root))
os.chdir(root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','trace_backend.settings')
import django
django.setup()
from trace_backend import llm, gemini
from logging_app.models import InteractionLog
print(json.dumps(dict(provider=llm.provider(),model=llm.model_name(),configured=llm.configured(),fallback_chain=llm.model_chain(),embedding_model=gemini.embed_model_name())))
turn=InteractionLog.objects.filter(event_type='HELP_REQUEST',payload__ai_status='live',payload__cache_tier='computed').order_by('-timestamp').first()
print(json.dumps(dict(last_generated_model=turn.payload.get('model') if turn else None,generated_at=turn.timestamp.isoformat() if turn else None)))
