/**
 * Plain helpers behind the form primitives.
 *
 * Separate from fields.jsx so that file exports only components - a module mixing
 * components with plain values loses React Fast Refresh, turning every edit to a
 * field into a full page reload.
 */

export const inputClass = (error) =>
  `w-full bg-surface-container-high rounded-xl px-3.5 py-2.5 text-sm text-on-surface border outline-none transition placeholder:text-outline focus:ring-2 focus:ring-primary/20 ${
    error ? 'border-rose-500/60 focus:border-rose-500' : 'border-outline-variant/40 focus:border-primary'
  }`;

export function passwordStrength(pw = '') {
  let score = 0;
  if (pw.length >= 8) score += 1;
  if (pw.length >= 12) score += 1;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score += 1;
  if (/\d/.test(pw)) score += 1;
  if (/[^A-Za-z0-9]/.test(pw)) score += 1;
  if (!pw) return { score: 0, label: '', tone: '' };
  if (score <= 1) return { score: 1, label: 'Weak', tone: 'bg-rose-500' };
  if (score <= 3) return { score: 2, label: 'Medium', tone: 'bg-amber-500' };
  return { score: 3, label: 'Strong', tone: 'bg-emerald-500' };
}
