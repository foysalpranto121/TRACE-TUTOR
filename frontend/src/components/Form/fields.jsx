import { useId, useState } from 'react';
import { Eye, EyeOff, Check } from 'lucide-react';

/**
 * Form primitives.
 *
 * Every control is programmatically associated with its label and its error text:
 * `<label for>` + `id`, plus `aria-invalid` and `aria-describedby` when a field is
 * rejected. Without that pairing a screen reader announces an unlabelled edit box, and
 * tapping the label does not focus the field - which matters here because registration
 * and the profile are long forms filled in on phones.
 */

export const inputClass = (error) =>
  `w-full bg-surface-container-high rounded-xl px-3.5 py-2.5 text-sm text-on-surface border outline-none transition placeholder:text-outline focus:ring-2 focus:ring-primary/20 ${
    error ? 'border-rose-500/60 focus:border-rose-500' : 'border-outline-variant/40 focus:border-primary'
  }`;

export const Label = ({ children, required, hint, htmlFor, id }) => (
  <label
    htmlFor={htmlFor}
    id={id}
    className="block text-[11px] font-extrabold text-on-surface uppercase tracking-wider mb-1.5"
  >
    {children}
    {required && <span className="text-rose-400" aria-hidden="true"> *</span>}
    {required && <span className="sr-only"> (required)</span>}
    {hint && <span className="ml-2 normal-case tracking-normal font-medium text-on-surface-variant">{hint}</span>}
  </label>
);

export const FieldError = ({ error, id }) =>
  error ? (
    <p id={id} role="alert" className="text-[11px] text-rose-400 mt-1 font-medium">
      {error}
    </p>
  ) : null;

/** Shared wiring: a stable id, and the aria attributes that depend on the error state. */
function useField(error, explicitId) {
  const generated = useId();
  const id = explicitId || generated;
  const errorId = `${id}-error`;
  return {
    id,
    errorId,
    aria: {
      'aria-invalid': error ? true : undefined,
      'aria-describedby': error ? errorId : undefined,
    },
  };
}

export const TextField = ({ label, hint, error, required, icon, list, className = '', id: explicitId, ...props }) => {
  const { id, errorId, aria } = useField(error, explicitId);
  return (
    <div className={className}>
      {label && <Label htmlFor={id} required={required} hint={hint}>{label}</Label>}
      <div className="relative">
        {icon && (
          <span aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">
            {icon}
          </span>
        )}
        <input
          id={id}
          required={required}
          className={`${inputClass(error)} ${icon ? 'pl-10' : ''}`}
          list={list}
          {...aria}
          {...props}
        />
      </div>
      <FieldError error={error} id={errorId} />
    </div>
  );
};

export const PasswordField = ({ label, error, required, hint, className = '', id: explicitId, ...props }) => {
  const [show, setShow] = useState(false);
  const { id, errorId, aria } = useField(error, explicitId);
  return (
    <div className={className}>
      {label && <Label htmlFor={id} required={required} hint={hint}>{label}</Label>}
      <div className="relative">
        <input
          id={id}
          required={required}
          type={show ? 'text' : 'password'}
          className={`${inputClass(error)} pr-11`}
          {...aria}
          {...props}
        />
        <button
          type="button"
          onClick={() => setShow(!show)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-on-surface"
          aria-label={show ? 'Hide password' : 'Show password'}
          aria-pressed={show}
          aria-controls={id}
          tabIndex={-1}
        >
          {show ? <EyeOff className="w-4 h-4" aria-hidden="true" /> : <Eye className="w-4 h-4" aria-hidden="true" />}
        </button>
      </div>
      <FieldError error={error} id={errorId} />
    </div>
  );
};

export const SelectField = ({ label, error, required, hint, options, placeholder = 'Select...', className = '', id: explicitId, ...props }) => {
  const { id, errorId, aria } = useField(error, explicitId);
  return (
    <div className={className}>
      {label && <Label htmlFor={id} required={required} hint={hint}>{label}</Label>}
      <select id={id} required={required} className={`${inputClass(error)} cursor-pointer`} {...aria} {...props}>
        <option value="" className="bg-surface-container text-on-surface">{placeholder}</option>
        {options.map(([value, text]) => (
          <option key={value} value={value} className="bg-surface-container text-on-surface">{text}</option>
        ))}
      </select>
      <FieldError error={error} id={errorId} />
    </div>
  );
};

export const ChipGroup = ({ label, options, value, onChange, multi = false, error, required, hint, className = '' }) => {
  const { id, errorId, aria } = useField(error);
  const labelId = `${id}-label`;
  const selected = multi ? value || [] : value;
  const toggle = (v) => {
    if (multi) onChange(selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]);
    else onChange(v === selected ? '' : v);
  };
  return (
    <div className={className}>
      {label && <Label id={labelId} required={required} hint={hint}>{label}</Label>}
      {/* A labelled group of toggles: each chip reports its own pressed state, so a
          screen reader announces both the question and which answers are chosen. */}
      <div
        role="group"
        aria-labelledby={label ? labelId : undefined}
        {...aria}
        className="flex flex-wrap gap-2"
      >
        {options.map(([v, text]) => {
          const active = multi ? selected.includes(v) : selected === v;
          return (
            <button
              key={v}
              type="button"
              onClick={() => toggle(v)}
              aria-pressed={active}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all flex items-center gap-1.5 ${
                active ? 'bg-primary/15 border-primary text-primary shadow-sm' : 'bg-surface-container-high border-outline-variant/40 text-on-surface-variant hover:text-on-surface hover:border-outline'
              }`}
            >
              {active && <Check className="w-3 h-3" aria-hidden="true" />}
              {text}
            </button>
          );
        })}
      </div>
      <FieldError error={error} id={errorId} />
    </div>
  );
};

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

export const StrengthMeter = ({ password }) => {
  const s = passwordStrength(password);
  if (!password) return null;
  return (
    <div className="mt-1.5 flex items-center gap-2">
      {/* The bars are decorative; the announcement comes from the live text beside them. */}
      <div className="flex-1 flex gap-1" aria-hidden="true">
        {[1, 2, 3].map((i) => <div key={i} className={`h-1 flex-1 rounded-full ${i <= s.score ? s.tone : 'bg-surface-container-highest'}`} />)}
      </div>
      <span className="text-[10px] font-mono text-on-surface-variant" role="status">
        {s.label} password
      </span>
    </div>
  );
};
