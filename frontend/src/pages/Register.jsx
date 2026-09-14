import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, ArrowLeft, Check, User, Brain, ShieldCheck, School, AlertTriangle, Loader2, Mail, KeyRound } from 'lucide-react';
import { useAuth, roleHome } from '../context/AuthContext';
import { AuthLayout } from '../components/Layout/AuthLayout';
import { TextField, PasswordField, SelectField, ChipGroup, StrengthMeter, Label, FieldError } from '../components/Form/fields';
import {
  ROLE_OPTIONS, DIVISIONS, SCHOOL_SUGGESTIONS, SCHOOL_TYPES, AREA_TYPES, GRADES, BATCH_YEARS, GROUPS, MEDIUMS, GENDERS,
  EXPERIENCE, LANGUAGES_KNOWN, AI_FAMILIARITY, DEVICES, INTERNET, STUDY_HOURS, GOALS, UI_LANGUAGES, CONSENT_POINTS, CONSENT_VERSION,
} from '../data/profileOptions';

const ROLE_ICONS = { STUDENT: User, EXPERT_TEACHER: Brain, RESEARCHER_ADMIN: ShieldCheck };
const USERNAME_RE = /^[A-Za-z0-9._-]{3,30}$/;
const STEP_FIELDS = {
  1: ['full_name', 'username', 'email', 'password', 'confirm', 'role', 'access_code'],
  2: ['school_name', 'school_type', 'division', 'district', 'area_type', 'grade', 'hsc_batch_year', 'academic_group', 'medium', 'gender', 'age', 'designation', 'teaching_years'],
  3: ['prior_experience', 'languages_known', 'ai_tool_familiarity', 'device_type', 'internet_access', 'has_computer_at_home', 'weekly_study_hours', 'learning_goals', 'preferred_language', 'consent_given'],
};

const suggestUsername = (name) => {
  const ascii = name.toLowerCase().replace(/[^a-z0-9\s]/g, '').trim().split(/\s+/).filter(Boolean).join('.');
  if (ascii.length >= 3) return ascii.slice(0, 30);
  return `student${Math.floor(1000 + Math.random() * 9000)}`;
};

export const Register = () => {
  const { register, user, ready, language } = useAuth();
  const navigate = useNavigate();
  const bn = language === 'bn';
  const submitted = useRef(false);
  const usernameTouched = useRef(false);

  const [step, setStep] = useState(1);
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    role: 'STUDENT', full_name: '', username: '', email: '', password: '', confirm: '', access_code: '',
    school_name: '', school_type: 'college', division: '', district: '', area_type: '', grade: '11', hsc_batch_year: '2027',
    academic_group: 'science', medium: 'bangla_version', gender: '', age: '', designation: '', teaching_years: '',
    prior_experience: 'novice', languages_known: [], ai_tool_familiarity: 'never', device_type: '', internet_access: '',
    has_computer_at_home: '', weekly_study_hours: '', learning_goals: [], preferred_language: language, consent_given: false,
  });

  useEffect(() => {
    if (ready && user && !submitted.current) navigate(roleHome(user.role), { replace: true });
  }, [ready]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the tutor-language default in sync with the UI language toggle until the user picks one explicitly.
  useEffect(() => {
    setForm((f) => ({ ...f, preferred_language: language }));
  }, [language]);

  const isStudent = form.role === 'STUDENT';
  const set = (field) => (e) => {
    const value = e && e.target ? (e.target.type === 'checkbox' ? e.target.checked : e.target.value) : e;
    setForm((f) => {
      const next = { ...f, [field]: value };
      if (field === 'full_name' && !usernameTouched.current) next.username = suggestUsername(value);
      if (field === 'username') usernameTouched.current = true;
      return next;
    });
    setErrors((er) => ({ ...er, [field]: undefined }));
  };

  const validate = (s) => {
    const er = {};
    if (s === 1) {
      if (!form.full_name.trim()) er.full_name = 'Full name is required.';
      if (!USERNAME_RE.test(form.username)) er.username = '3-30 letters, digits, dots, underscores or hyphens - no spaces.';
      if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) er.email = 'Enter a valid email address.';
      if (form.password.length < 8) er.password = 'Use at least 8 characters.';
      else if (/^\d+$/.test(form.password)) er.password = 'Password cannot be only numbers.';
      if (form.confirm !== form.password) er.confirm = 'Passwords do not match.';
      if (!isStudent && !form.access_code.trim()) er.access_code = 'Staff access code is required.';
    }
    if (s === 2) {
      if (!form.school_name.trim()) er.school_name = isStudent ? 'School / college name is required.' : 'Institution is required.';
      if (!form.division) er.division = 'Select your division.';
      if (isStudent) {
        if (!form.grade) er.grade = 'Select your grade.';
        if (!form.hsc_batch_year) er.hsc_batch_year = 'Select your HSC batch.';
        if (form.age && (Number(form.age) < 10 || Number(form.age) > 60)) er.age = 'Enter a realistic age.';
      } else if (!form.designation.trim()) er.designation = 'Designation is required.';
    }
    if (s === 3) {
      if (isStudent && !form.device_type) er.device_type = 'Tell us which device you mostly use.';
      if (!form.consent_given) er.consent_given = 'Consent is required to create an account.';
    }
    setErrors(er);
    return Object.keys(er).length === 0;
  };

  const nextStep = () => { if (validate(step)) setStep(step + 1); };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate(3)) return;
    setSubmitting(true);
    setServerError(null);
    const { confirm, ...payload } = form;
    payload.has_computer_at_home = form.has_computer_at_home === '' ? null : form.has_computer_at_home === 'yes';
    payload.consent_version = CONSENT_VERSION;
    try {
      submitted.current = true;
      const u = await register(payload);
      navigate(roleHome(u.role), { replace: true });
    } catch (err) {
      submitted.current = false;
      setServerError(err.message);
      if (err.fields) {
        setErrors(err.fields);
        const firstField = Object.keys(err.fields)[0];
        const target = Object.entries(STEP_FIELDS).find(([, fields]) => fields.includes(firstField));
        if (target) setStep(Number(target[0]));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const steps = [
    { n: 1, label: bn ? 'অ্যাকাউন্ট' : 'Account' },
    { n: 2, label: isStudent ? (bn ? 'প্রতিষ্ঠান ও শ্রেণি' : 'School & class') : (bn ? 'প্রতিষ্ঠান' : 'Institution') },
    { n: 3, label: bn ? 'পটভূমি ও সম্মতি' : 'Background & consent' },
  ];

  return (
    <AuthLayout width="max-w-2xl">
      <div className="bg-surface-container rounded-2xl border border-outline-variant/30 shadow-2xl p-6 sm:p-8 space-y-6">
        <div className="space-y-1">
          <div className="text-[11px] font-mono font-bold text-primary uppercase tracking-wider">{bn ? 'নিবন্ধন' : 'Create account'} · {step}/3</div>
          <h2 className="text-2xl font-extrabold text-on-surface tracking-tight">{bn ? 'TRACE Tutor অ্যাকাউন্ট তৈরি করুন' : 'Create your TRACE Tutor account'}</h2>
          <p className="text-xs text-on-surface-variant">
            {bn ? 'গবেষণার জন্য কয়েকটি তথ্য প্রয়োজন; আপনার নাম কখনো প্রকাশ করা হবে না।' : 'A few details help the study - your name is never published, only a participant code.'}
          </p>
        </div>

        {/* Stepper */}
        <ol className="flex items-center gap-2">
          {steps.map((s, i) => (
            <li key={s.n} className="flex items-center gap-2 flex-1 min-w-0">
              <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-extrabold border shrink-0 ${
                step > s.n ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400' : step === s.n ? 'bg-primary text-on-primary border-primary' : 'bg-surface-container-high border-outline-variant/40 text-on-surface-variant'
              }`}>{step > s.n ? <Check className="w-3.5 h-3.5" /> : s.n}</span>
              <span className={`text-xs font-bold truncate ${step === s.n ? 'text-on-surface' : 'text-on-surface-variant'}`}>{s.label}</span>
              {i < steps.length - 1 && <span className={`flex-1 h-px ${step > s.n ? 'bg-emerald-500/40' : 'bg-outline-variant/40'}`} />}
            </li>
          ))}
        </ol>

        {serverError && (
          <div role="alert" className="bg-rose-500/10 border border-rose-500/30 rounded-xl px-3.5 py-2.5 text-xs text-rose-400 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" /> <span>{serverError}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          {step === 1 && (
            <>
              <div>
                <Label required>{bn ? 'আমি একজন' : 'I am a'}</Label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {ROLE_OPTIONS.map((r) => {
                    const Icon = ROLE_ICONS[r.id];
                    const active = form.role === r.id;
                    return (
                      <button key={r.id} type="button" onClick={() => set('role')(r.id)} className={`text-left p-3 rounded-xl border transition-all ${active ? 'bg-primary/10 border-primary shadow-sm' : 'bg-surface-container-high border-outline-variant/40 hover:border-outline'}`}>
                        <Icon className={`w-4 h-4 mb-2.5 ${active ? 'text-primary' : 'text-on-surface-variant'}`} />
                        <div className="text-xs font-extrabold text-on-surface leading-tight">{r.title}</div>
                        <div className="text-[10px] text-on-surface-variant mt-0.5 leading-snug">{r.desc}</div>
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <TextField label={bn ? 'পূর্ণ নাম' : 'Full name'} required value={form.full_name} onChange={set('full_name')} error={errors.full_name} placeholder={bn ? 'যেমন: তানভীর রহমান' : 'e.g. Tanvir Rahman'} autoComplete="name" autoFocus />
                <TextField label={bn ? 'ইউজারনেম' : 'Username'} required hint="(login id)" value={form.username} onChange={set('username')} error={errors.username} placeholder="tanvir.rahman" autoComplete="username" />
                <TextField label={bn ? 'ইমেইল' : 'Email'} hint={bn ? '(ঐচ্ছিক)' : '(optional)'} type="email" icon={<Mail className="w-4 h-4" />} value={form.email} onChange={set('email')} error={errors.email} placeholder="tanvir@example.com" autoComplete="email" className="sm:col-span-2" />
                <div>
                  <PasswordField label={bn ? 'পাসওয়ার্ড' : 'Password'} required value={form.password} onChange={set('password')} error={errors.password} placeholder={bn ? 'কমপক্ষে ৮ অক্ষর' : 'At least 8 characters'} autoComplete="new-password" />
                  <StrengthMeter password={form.password} />
                </div>
                <PasswordField label={bn ? 'পাসওয়ার্ড নিশ্চিত করুন' : 'Confirm password'} required value={form.confirm} onChange={set('confirm')} error={errors.confirm} placeholder="••••••••" autoComplete="new-password" />
                {!isStudent && (
                  <TextField label={bn ? 'স্টাফ অ্যাক্সেস কোড' : 'Staff access code'} required icon={<KeyRound className="w-4 h-4" />} value={form.access_code} onChange={set('access_code')} error={errors.access_code} placeholder="Provided by the research coordinator" className="sm:col-span-2" />
                )}
              </div>
            </>
          )}

          {step === 2 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <TextField label={isStudent ? (bn ? 'স্কুল / কলেজের নাম' : 'School / college name') : (bn ? 'প্রতিষ্ঠান' : 'Institution')} required icon={<School className="w-4 h-4" />} list="school-suggestions" value={form.school_name} onChange={set('school_name')} error={errors.school_name} placeholder={bn ? 'যেমন: ঢাকা কলেজ' : 'e.g. Dhaka College'} className="sm:col-span-2" />
              <datalist id="school-suggestions">{SCHOOL_SUGGESTIONS.map((s) => <option key={s} value={s} />)}</datalist>
              <SelectField label={bn ? 'প্রতিষ্ঠানের ধরন' : 'Institution type'} options={SCHOOL_TYPES} value={form.school_type} onChange={set('school_type')} error={errors.school_type} />
              <SelectField label={bn ? 'বিভাগ' : 'Division'} required options={DIVISIONS.map((d) => [d, d])} value={form.division} onChange={set('division')} error={errors.division} />
              <TextField label={bn ? 'জেলা' : 'District'} value={form.district} onChange={set('district')} error={errors.district} placeholder={bn ? 'যেমন: গাজীপুর' : 'e.g. Gazipur'} />
              <SelectField label={bn ? 'এলাকার ধরন' : 'Area type'} options={AREA_TYPES} value={form.area_type} onChange={set('area_type')} error={errors.area_type} />
              {isStudent ? (
                <>
                  <SelectField label={bn ? 'শ্রেণি' : 'Class'} required options={GRADES} value={form.grade} onChange={set('grade')} error={errors.grade} />
                  <SelectField label={bn ? 'এইচএসসি ব্যাচ' : 'HSC batch'} required options={BATCH_YEARS} value={form.hsc_batch_year} onChange={set('hsc_batch_year')} error={errors.hsc_batch_year} />
                  <SelectField label={bn ? 'গ্রুপ' : 'Group'} options={GROUPS} value={form.academic_group} onChange={set('academic_group')} />
                  <SelectField label={bn ? 'মাধ্যম' : 'Medium'} options={MEDIUMS} value={form.medium} onChange={set('medium')} />
                  <SelectField label={bn ? 'লিঙ্গ' : 'Gender'} options={GENDERS} value={form.gender} onChange={set('gender')} />
                  <TextField label={bn ? 'বয়স' : 'Age'} type="number" min="10" max="60" value={form.age} onChange={set('age')} error={errors.age} placeholder="17" />
                </>
              ) : (
                <>
                  <TextField label={bn ? 'পদবি' : 'Designation'} required value={form.designation} onChange={set('designation')} error={errors.designation} placeholder={bn ? 'যেমন: সহকারী অধ্যাপক (ICT)' : 'e.g. Assistant Professor (ICT)'} />
                  <TextField label={bn ? 'শিক্ষকতার অভিজ্ঞতা (বছর)' : 'Teaching experience (years)'} type="number" min="0" max="60" value={form.teaching_years} onChange={set('teaching_years')} error={errors.teaching_years} placeholder="5" />
                  <SelectField label={bn ? 'লিঙ্গ' : 'Gender'} options={GENDERS} value={form.gender} onChange={set('gender')} />
                </>
              )}
            </div>
          )}

          {step === 3 && (
            <div className="space-y-5">
              {isStudent && (
                <>
                  <ChipGroup label={bn ? 'প্রোগ্রামিং অভিজ্ঞতা' : 'Programming experience'} options={EXPERIENCE} value={form.prior_experience} onChange={set('prior_experience')} />
                  <ChipGroup label={bn ? 'যেসব ভাষা আগে দেখেছেন' : 'Languages you have tried'} hint={bn ? '(একাধিক)' : '(any)'} options={LANGUAGES_KNOWN} value={form.languages_known} onChange={set('languages_known')} multi />
                  <ChipGroup label={bn ? 'AI টুল (ChatGPT ইত্যাদি) ব্যবহার' : 'Use of AI tools (ChatGPT etc.)'} options={AI_FAMILIARITY} value={form.ai_tool_familiarity} onChange={set('ai_tool_familiarity')} />
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <SelectField label={bn ? 'মূলত যে ডিভাইস ব্যবহার করবেন' : 'Device you mostly use'} required options={DEVICES} value={form.device_type} onChange={set('device_type')} error={errors.device_type} />
                    <SelectField label={bn ? 'ইন্টারনেট সংযোগ' : 'Internet access'} options={INTERNET} value={form.internet_access} onChange={set('internet_access')} />
                    <SelectField label={bn ? 'বাসায় কম্পিউটার আছে?' : 'Computer at home?'} options={[['yes', bn ? 'হ্যাঁ' : 'Yes'], ['no', bn ? 'না' : 'No']]} value={form.has_computer_at_home} onChange={set('has_computer_at_home')} />
                    <SelectField label={bn ? 'সাপ্তাহিক ICT পড়ার সময়' : 'Weekly ICT study time'} options={STUDY_HOURS} value={form.weekly_study_hours} onChange={set('weekly_study_hours')} />
                  </div>
                  <ChipGroup label={bn ? 'শেখার লক্ষ্য' : 'Learning goals'} hint={bn ? '(একাধিক)' : '(select all that apply)'} options={GOALS} value={form.learning_goals} onChange={set('learning_goals')} multi />
                </>
              )}
              <ChipGroup label={bn ? 'পছন্দের ভাষা' : 'Preferred tutor language'} options={UI_LANGUAGES} value={form.preferred_language} onChange={set('preferred_language')} />

              <div className={`rounded-xl border p-4 space-y-3 ${errors.consent_given ? 'border-rose-500/50 bg-rose-500/5' : 'border-outline-variant/30 bg-surface-container-lowest'}`}>
                <div className="flex items-center gap-2 text-xs font-extrabold text-on-surface uppercase tracking-wider">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" /> {bn ? 'গবেষণায় অংশগ্রহণের সম্মতি' : 'Research participation consent'} <span className="font-mono text-on-surface-variant normal-case">({CONSENT_VERSION})</span>
                </div>
                <ul className="text-[11px] text-on-surface-variant leading-relaxed space-y-1.5 list-disc pl-4">
                  {CONSENT_POINTS.map((p) => <li key={p}>{p}</li>)}
                </ul>
                <label className="flex items-start gap-2.5 text-xs text-on-surface cursor-pointer select-none pt-1">
                  <input type="checkbox" checked={form.consent_given} onChange={set('consent_given')} className="mt-0.5 w-4 h-4 rounded accent-cyan-500" />
                  <span className="font-semibold">
                    {isStudent
                      ? (bn ? 'আমি উপরের শর্তগুলো পড়েছি এবং এই গবেষণায় অংশ নিতে সম্মত।' : 'I have read the points above and agree to take part in this study.')
                      : (bn ? 'আমি বুঝেছি যে এই প্ল্যাটফর্মে আমার কার্যক্রম গবেষণার অংশ হিসেবে লগ করা হয়।' : 'I understand that my activity on this platform is logged as part of the study.')}
                  </span>
                </label>
                <FieldError error={errors.consent_given} />
              </div>
            </div>
          )}

          <div className="flex items-center justify-between gap-3 pt-2">
            {step > 1 ? (
              <button type="button" onClick={() => setStep(step - 1)} className="px-4 py-2.5 rounded-xl bg-surface-container-high border border-outline-variant/40 text-on-surface text-xs font-bold flex items-center gap-2 hover:bg-surface-container-highest transition-colors">
                <ArrowLeft className="w-4 h-4" /> {bn ? 'পেছনে' : 'Back'}
              </button>
            ) : <span />}
            {step < 3 ? (
              <button type="button" onClick={nextStep} className="px-5 py-2.5 rounded-xl bg-primary hover:bg-primary-container text-on-primary text-xs font-extrabold flex items-center gap-2 shadow-lg shadow-primary/20 transition-all">
                {bn ? 'পরবর্তী' : 'Continue'} <ArrowRight className="w-4 h-4" />
              </button>
            ) : (
              <button type="submit" disabled={submitting} className="px-5 py-2.5 rounded-xl bg-primary hover:bg-primary-container text-on-primary text-xs font-extrabold flex items-center gap-2 shadow-lg shadow-primary/20 transition-all disabled:opacity-60">
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                {submitting ? (bn ? 'অ্যাকাউন্ট তৈরি হচ্ছে...' : 'Creating account...') : (bn ? 'অ্যাকাউন্ট তৈরি করুন' : 'Create account')}
              </button>
            )}
          </div>
        </form>

        <div className="pt-4 border-t border-outline-variant/20 text-center text-xs text-on-surface-variant">
          {bn ? 'আগে থেকেই অ্যাকাউন্ট আছে?' : 'Already have an account?'}{' '}
          <Link to="/login" className="font-bold text-primary hover:underline">{bn ? 'সাইন ইন করুন' : 'Sign in'}</Link>
        </div>
      </div>
    </AuthLayout>
  );
};
