const PROVIDERS = { openai: 'OpenAI', gemini: 'Gemini' };
const modelName = (value) => typeof value === 'string' ? value.trim() : '';

export function configuredTutorLabel(metadata) {
  const model = modelName(metadata?.primary_model);
  const provider = PROVIDERS[metadata?.provider];
  return metadata?.configured === true && provider && model ? provider + ' · ' + model : 'AI Tutor';
}

export function describeTutorModel(metadata, response, isLoading = false) {
  const configured = configuredTutorLabel(metadata);
  const primaryTitle = configured === 'AI Tutor' ? 'Tutor model metadata unavailable' : 'Configured primary: ' + configured;
  if (isLoading) return { label: configured + ' · pending', title: primaryTitle + '; Response pending' };
  if (response?.ai_status === 'fallback') {
    return { label: 'Textbook fallback', title: primaryTitle + '; AI generation unavailable; showing textbook material' };
  }
  const model = modelName(response?.model);
  if (response?.ai_status === 'live' && model) {
    const provider = PROVIDERS[response.provider];
    const fallback = response.provider === metadata?.provider && Array.isArray(metadata?.fallback_models) && metadata.fallback_models.includes(model);
    const label = (provider ? provider + ' · ' : '') + model + (fallback ? ' (fallback model)' : '');
    return { label, title: primaryTitle + '; Response model: ' + label + (response.cached ? '; cached answer' : '') };
  }
  // A configured model is a setting, not evidence that it answered a request.
  return { label: configured, title: primaryTitle };
}
