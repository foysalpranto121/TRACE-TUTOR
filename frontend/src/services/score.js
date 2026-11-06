// Missing grades are distinct from genuine zeroes; never coerce invalid marks.
export function formatScore(value, status) {
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100) return value + '%';
  if (value == null && status === 'pending') return 'Not graded';
  if (value == null && status === 'grading') return 'Grading…';
  return 'Score unavailable';
}
