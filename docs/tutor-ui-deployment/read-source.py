from pathlib import Path
import json
root=Path("/srv/trace-tutor")
paths=["backend/logging_app/views.py","frontend/src/pages/Workspace.jsx","frontend/src/components/TutorPanel/AnswerOnlyPanel.jsx","frontend/src/components/TutorPanel/ReasoningTracePanel.jsx","frontend/src/services/api.js","frontend/eslint.config.js","frontend/package.json","frontend/package-lock.json"]
print(json.dumps({p:(root/p).read_text() for p in paths}))
