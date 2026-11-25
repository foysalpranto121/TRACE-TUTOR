const SUPPORT_LABELS = {
  full: 'Curriculum Grounded',
  concepts: 'Related textbook concepts',
  none: 'Not covered by passages',
};

export function describeTextbookSupport(ragAnswer, aiStatus) {
  if (aiStatus === 'fallback') {
    return { level: null, label: 'Retrieved textbook passage', tone: 'caution' };
  }

  const level = ragAnswer?.support_level;
  if (Object.hasOwn(SUPPORT_LABELS, level)) {
    return { level, label: SUPPORT_LABELS[level], tone: level === 'full' ? 'positive' : 'caution' };
  }

  // Preserve the legacy badge without treating an old boolean as a full-support assessment.
  if (ragAnswer?.grounded === true || ragAnswer?.grounded === false) {
    const uncovered = ragAnswer.grounded === false;
    return {
      level: null,
      label: uncovered ? SUPPORT_LABELS.none : SUPPORT_LABELS.full,
      tone: uncovered ? 'caution' : 'positive',
    };
  }

  return { level: null, label: 'Support not assessed', tone: 'neutral' };
}

export function hasTextbookAnswer(ragAnswer) {
  return ['textbook_rule', 'textbook_explanation', 'curriculum_citation'].some(
    (field) => typeof ragAnswer?.[field] === 'string' && ragAnswer[field].trim().length > 0
  );
}
