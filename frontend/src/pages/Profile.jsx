import React, { useEffect, useRef, useState } from 'react';
import { User, School, BookOpen, ShieldCheck, KeyRound, Save, Loader2, CheckCircle2, AlertTriangle, Fingerprint, Calendar, Mail, Brain, Bot, Check, Palette, Sun, Moon, Sparkles, Camera, Trash2, Upload } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTheme, FX_LEVELS } from '../context/ThemeContext';
import { TextField, PasswordField, SelectField, ChipGroup, StrengthMeter } from '../components/Form/fields';
import { Avatar } from '../components/ui';
import {
  DIVISIONS, SCHOOL_SUGGESTIONS, SCHOOL_TYPES, AREA_TYPES, GRADES, BATCH_YEARS, GROUPS, MEDIUMS, GENDERS, EXPERIENCE,
  LANGUAGES_KNOWN, AI_FAMILIARITY, DEVICES, INTERNET, STUDY_HOURS, GOALS, UI_LANGUAGES, ARM_OPTIONS, armLabel,
} from '../data/profileOptions';

const EDITABLE = [
  'full_name', 'email', 'phone', 'gender', 'age', 'school_name', 'school_type', 'division', 'district', 'area_type', 'grade',
  'hsc_batch_year', 'academic_group', 'medium', 'prior_experience', 'languages_known', 'ai_tool_familiarity', 'device_type',
  'internet_access', 'has_computer_at_home', 'weekly_study_hours', 'learning_goals', 'preferred_language', 'designation', 'teaching_years',
];

const fromUser = (u) => {
  const f = {};
  EDITABLE.forEach((k) => {
    const v = u?.[k];
    if (k === 'has_computer_at_home') f[k] = v === true ? 'yes' : v === false ? 'no' : '';
    else if (Array.isArray(v)) f[k] = v;
    else f[k] = v === null || v === undefined ? '' : String(v);
  });
  return f;
};

const Section = ({ icon, title, subtitle, children }) => (
  <section className="bg-surface-container rounded-2xl border border-outline-variant/30 shadow-lg">
    <header className="px-5 py-4 border-b border-outline-variant/20">
      <h3 className="text-sm font-extrabold text-on-surface flex items-center gap-2">{icon}{title}</h3>
      {subtitle && <p className="text-xs text-on-surface-variant mt-0.5">{subtitle}</p>}
    </header>
    <div className="p-5">{children}</div>
  </section>
);

export const Profile = () => {
  const { user, updateProfile, changePassword, setArm, uploadAvatar, removeAvatar, language } = useAuth();
  const { theme, setTheme, fxChoice, setFx, systemReducedMotion } = useTheme();
  const bn = language === 'bn';
  const isStudent = user?.role === 'STUDENT';
  const [form, setForm] = useState(() => fromUser(user));
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState(null);
  const [pw, setPw] = useState({ current: '', next: '', confirm: '' });
  const [pwState, setPwState] = useState({ saving: false, error: null, ok: false });
  const [armBusy, setArmBusy] = useState(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [avatarPreview, setAvatarPreview] = useState(null);
  const fileInput = useRef(null);

  // Preview locally first so the picture appears the instant it is picked, then persist.
  const handleAvatarFile = async (file) => {
    if (!file) return;
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) {
      setNotice({ ok: false, text: bn ? 'শুধু JPG, PNG বা WebP ছবি দিন।' : 'Please choose a JPG, PNG or WebP image.' });
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setNotice({ ok: false, text: bn ? 'ছবিটি ৫ MB-এর বেশি হতে পারবে না।' : 'The image must be under 5 MB.' });
      return;
    }
    const url = URL.createObjectURL(file);
    setAvatarPreview(url);
    setAvatarBusy(true);
    setNotice(null);
    try {
      await uploadAvatar(file);
      setNotice({ ok: true, text: bn ? 'প্রোফাইল ছবি আপডেট হয়েছে।' : 'Profile picture updated.' });
    } catch (err) {
      setNotice({ ok: false, text: err.fields?.avatar || err.message });
    } finally {
      setAvatarBusy(false);
      setAvatarPreview(null);
      URL.revokeObjectURL(url);
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  const handleAvatarRemove = async () => {
    setAvatarBusy(true);
    setNotice(null);
    try {
      await removeAvatar();
      setNotice({ ok: true, text: bn ? 'প্রোফাইল ছবি সরানো হয়েছে।' : 'Profile picture removed.' });
    } catch (err) {
      setNotice({ ok: false, text: err.message });
    } finally {
      setAvatarBusy(false);
    }
  };

  const handleArm = async (armId) => {
    if (armId === user.arm) return;
    setArmBusy(armId);
    setNotice(null);
    try {
      await setArm(armId);
      setNotice({ ok: true, text: bn ? `টিউটর মোড পরিবর্তন হয়েছে: ${armLabel(armId)}` : `Tutor mode switched to ${armLabel(armId)}.` });
    } catch (err) {
      setNotice({ ok: false, text: err.message });
    } finally {
      setArmBusy(null);
    }
  };

  useEffect(() => { setForm(fromUser(user)); }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (field) => (e) => {
    const value = e && e.target ? e.target.value : e;
    setForm((f) => ({ ...f, [field]: value }));
    setErrors((er) => ({ ...er, [field]: undefined }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setNotice(null);
    const patch = { ...form, has_computer_at_home: form.has_computer_at_home === '' ? null : form.has_computer_at_home === 'yes' };
    try {
      await updateProfile(patch);
      setNotice({ ok: true, text: bn ? 'প্রোফাইল সংরক্ষিত হয়েছে।' : 'Profile saved.' });
    } catch (err) {
      setErrors(err.fields || {});
      setNotice({ ok: false, text: err.message });
    } finally {
      setSaving(false);
    }
  };

  const handlePassword = async (e) => {
    e.preventDefault();
    if (pw.next !== pw.confirm) { setPwState({ saving: false, error: 'New passwords do not match.', ok: false }); return; }
    setPwState({ saving: true, error: null, ok: false });
    try {
      await changePassword(pw.current, pw.next);
      setPw({ current: '', next: '', confirm: '' });
      setPwState({ saving: false, error: null, ok: true });
    } catch (err) {
      setPwState({ saving: false, error: err.message, ok: false });
    }
  };

  if (!user) return null;

  return (
    <div className="max-w-5xl mx-auto w-full space-y-5 pb-10">
      {/* Header card */}
      <div className="bg-surface-container rounded-2xl border border-outline-variant/30 p-5 shadow-xl flex flex-wrap items-center gap-5">
        <div className="flex flex-col items-center gap-2">
          <button
            type="button"
            onClick={() => !avatarBusy && fileInput.current?.click()}
            disabled={avatarBusy}
            title={bn ? 'প্রোফাইল ছবি বদলান' : 'Change profile picture'}
            className="group relative rounded-2xl press focus-visible:outline-none"
            aria-label={bn ? 'প্রোফাইল ছবি আপলোড করুন' : 'Upload profile picture'}
          >
            {avatarPreview
              ? <img src={avatarPreview} alt="" className="w-20 h-20 rounded-2xl object-cover ring-2 ring-primary/40" />
              : <Avatar user={user} size={80} ring />}
            <span className={`absolute inset-0 rounded-2xl flex flex-col items-center justify-center gap-0.5 bg-black/55 text-[10px] font-bold text-[#fffdf8] transition-opacity ${avatarBusy ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100'}`}>
              {avatarBusy ? <Loader2 className="w-5 h-5 animate-spin" /> : <><Camera className="w-5 h-5" />{bn ? 'ছবি বদলান' : 'Change'}</>}
            </span>
          </button>
          <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => handleAvatarFile(e.target.files?.[0])} data-testid="avatar-input" />
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => fileInput.current?.click()} disabled={avatarBusy} className="px-2 py-1 rounded-lg bg-surface-container-high border border-outline-variant/40 text-[10px] font-bold flex items-center gap-1 hover:border-primary/40 press disabled:opacity-50">
              <Upload className="w-3 h-3 text-primary" /> {bn ? 'আপলোড' : 'Upload'}
            </button>
            {user.avatar_url && (
              <button type="button" onClick={handleAvatarRemove} disabled={avatarBusy} className="px-2 py-1 rounded-lg bg-danger/10 border border-danger/30 text-danger text-[10px] font-bold flex items-center gap-1 press disabled:opacity-50" title={bn ? 'ছবি সরান' : 'Remove picture'}>
                <Trash2 className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-extrabold text-on-surface truncate">{user.full_name || user.username}</h1>
          <div className="text-xs text-on-surface-variant font-mono">@{user.username}{user.email ? ` · ${user.email}` : ''}</div>
          <div className="flex flex-wrap items-center gap-2 mt-2 text-[11px] font-mono">
            <span className="px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/30 font-bold">{user.role}</span>
            <span className={`px-2 py-0.5 rounded border font-bold ${
              user.arm === 'REASONING_VISIBLE' ? 'bg-success/10 text-success border-success/30'
                : user.arm === 'ANSWER_ONLY' ? 'bg-warning/10 text-warning border-warning/30'
                : 'bg-surface-container-high text-on-surface-variant border-outline-variant/40'
            }`}>
              {armLabel(user.arm)}
            </span>
            {user.school_name && <span className="text-on-surface-variant flex items-center gap-1"><School className="w-3 h-3" /> {user.school_name}</span>}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div className="bg-surface-container-high rounded-xl border border-outline-variant/30 px-3 py-2">
            <div className="font-mono text-on-surface-variant uppercase text-[10px] flex items-center gap-1"><Fingerprint className="w-3 h-3" /> Participant code</div>
            <div className="font-extrabold text-on-surface text-sm">{user.participant_code || '-'}</div>
          </div>
          <div className="bg-surface-container-high rounded-xl border border-outline-variant/30 px-3 py-2">
            <div className="font-mono text-on-surface-variant uppercase text-[10px] flex items-center gap-1"><Calendar className="w-3 h-3" /> Member since</div>
            <div className="font-extrabold text-on-surface text-sm">{user.joined ? new Date(user.joined).toLocaleDateString([], { day: '2-digit', month: 'short', year: 'numeric' }) : '-'}</div>
          </div>
        </div>
      </div>

      {notice && (
        <div className={`rounded-xl px-4 py-2.5 text-xs flex items-center gap-2 border ${notice.ok ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-rose-500/10 border-rose-500/30 text-rose-400'}`}>
          {notice.ok ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />} {notice.text}
        </div>
      )}

      {/* Tutor mode - switchable, and every change is written to the research log */}
      <Section
        icon={<Brain className="w-4 h-4 text-primary" />}
        title={bn ? 'টিউটর মোড' : 'Tutor mode'}
        subtitle={bn ? 'AI টিউটর আপনাকে কীভাবে সাহায্য করবে তা বেছে নিন' : 'Choose how the AI tutor helps you'}
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {ARM_OPTIONS.map((opt) => {
            const active = user.arm === opt.id;
            const busy = armBusy === opt.id;
            const Icon = opt.id === 'REASONING_VISIBLE' ? Brain : Bot;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => handleArm(opt.id)}
                disabled={!!armBusy}
                aria-pressed={active}
                className={`text-left p-4 rounded-2xl border transition-all press disabled:opacity-60 ${
                  active ? 'bg-primary/10 border-primary shadow-glow-sm' : 'bg-surface-container-high border-outline-variant/40 hover:border-primary/40'
                }`}
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <Icon className={`w-4 h-4 ${active ? 'text-primary' : 'text-on-surface-variant'}`} />
                  <span className="text-sm font-extrabold font-display">{bn ? opt.bn : opt.title}</span>
                  {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin text-primary ml-auto" />
                    : active && <span className="ml-auto flex items-center gap-1 text-[10px] font-mono font-bold text-primary"><Check className="w-3 h-3" />{bn ? 'সক্রিয়' : 'active'}</span>}
                </div>
                <p className="text-[11px] text-on-surface-variant leading-relaxed">{bn ? opt.desc_bn : opt.desc_en}</p>
                <p className="text-[10px] font-mono text-on-surface-variant/70 mt-1.5">{opt.title}</p>
              </button>
            );
          })}
        </div>
        <p className="text-[11px] text-on-surface-variant mt-3 leading-relaxed">
          {bn
            ? 'নিবন্ধনের সময় একটি মোড এলোমেলোভাবে নির্ধারিত হয়েছিল। আপনি চাইলে যেকোনো সময় পরিবর্তন করতে পারেন — প্রতিটি পরিবর্তন গবেষণার রেকর্ডে সময়সহ সংরক্ষিত হয়।'
            : 'A mode was assigned at random when you registered. You can switch at any time — each change is stored with a timestamp in the research log.'}
        </p>
      </Section>

      {/* Appearance: theme + how much motion the animated interface should use */}
      <Section
        icon={<Palette className="w-4 h-4 text-primary" />}
        title={bn ? 'চেহারা ও অ্যানিমেশন' : 'Appearance & motion'}
        subtitle={bn ? 'থিম ও অ্যানিমেশনের মাত্রা বেছে নিন' : 'Pick your theme and how animated the interface should feel'}
      >
        <div className="space-y-4">
          <div>
            <div className="text-[11px] font-extrabold text-on-surface uppercase tracking-wider mb-1.5">{bn ? 'থিম' : 'Theme'}</div>
            <div className="flex gap-2">
              {[['dark', bn ? 'ডার্ক (রাত)' : 'Dark', Moon], ['soft', bn ? 'সফট (চোখে আরাম)' : 'Soft · easy on the eyes', Sun]].map(([id, label, Icon]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setTheme(id)}
                  aria-pressed={theme === id}
                  className={`flex-1 sm:flex-none sm:w-52 px-4 py-2.5 rounded-xl border text-xs font-bold flex items-center justify-center gap-2 press transition-all ${
                    theme === id ? 'bg-primary/10 border-primary text-primary shadow-glow-sm' : 'bg-surface-container-high border-outline-variant/40 text-on-surface-variant hover:border-primary/40'
                  }`}
                >
                  <Icon className="w-4 h-4" /> {label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="text-[11px] font-extrabold text-on-surface uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-primary" /> {bn ? 'অ্যানিমেশন' : 'Animation'}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {FX_LEVELS.map((lvl) => (
                <button
                  key={lvl.id}
                  type="button"
                  onClick={() => setFx(lvl.id)}
                  aria-pressed={fxChoice === lvl.id}
                  className={`text-left p-3 rounded-xl border transition-all press ${
                    fxChoice === lvl.id ? 'bg-primary/10 border-primary shadow-glow-sm' : 'bg-surface-container-high border-outline-variant/40 hover:border-primary/40'
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-extrabold">{bn ? lvl.bn : lvl.en}</span>
                    {fxChoice === lvl.id && <Check className="w-3 h-3 text-primary ml-auto" />}
                  </div>
                  <p className="text-[10px] text-on-surface-variant leading-snug mt-0.5">{bn ? lvl.desc_bn : lvl.desc_en}</p>
                </button>
              ))}
            </div>
            {systemReducedMotion && (
              <p className="text-[11px] text-warning mt-2 flex items-start gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                {bn
                  ? 'আপনার ডিভাইসে "reduced motion" চালু আছে, তাই অ্যানিমেশন বন্ধ রাখা হয়েছে।'
                  : 'Your device asks for reduced motion, so animation stays off regardless of this setting.'}
              </p>
            )}
          </div>
        </div>
      </Section>

      <form onSubmit={handleSave} className="space-y-5">
        <Section icon={<User className="w-4 h-4 text-primary" />} title={bn ? 'অ্যাকাউন্ট' : 'Account'} subtitle={bn ? 'আপনার ব্যক্তিগত তথ্য' : 'Your personal details'}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <TextField label={bn ? 'পূর্ণ নাম' : 'Full name'} required value={form.full_name} onChange={set('full_name')} error={errors.full_name} />
            <TextField label={bn ? 'ইমেইল' : 'Email'} type="email" icon={<Mail className="w-4 h-4" />} value={form.email} onChange={set('email')} error={errors.email} placeholder="optional" />
            <TextField label={bn ? 'ফোন' : 'Phone'} value={form.phone} onChange={set('phone')} placeholder="optional" />
            <SelectField label={bn ? 'লিঙ্গ' : 'Gender'} options={GENDERS} value={form.gender} onChange={set('gender')} />
            {isStudent && <TextField label={bn ? 'বয়স' : 'Age'} type="number" min="10" max="60" value={form.age} onChange={set('age')} error={errors.age} />}
            <ChipGroup label={bn ? 'পছন্দের ভাষা' : 'Preferred language'} options={UI_LANGUAGES} value={form.preferred_language} onChange={set('preferred_language')} />
          </div>
        </Section>

        <Section icon={<School className="w-4 h-4 text-primary" />} title={isStudent ? (bn ? 'প্রতিষ্ঠান ও শ্রেণি' : 'School & class') : (bn ? 'প্রতিষ্ঠান' : 'Institution')}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <TextField label={isStudent ? (bn ? 'স্কুল / কলেজ' : 'School / college') : (bn ? 'প্রতিষ্ঠান' : 'Institution')} required list="school-suggestions-profile" value={form.school_name} onChange={set('school_name')} error={errors.school_name} className="sm:col-span-2" />
            <datalist id="school-suggestions-profile">{SCHOOL_SUGGESTIONS.map((s) => <option key={s} value={s} />)}</datalist>
            <SelectField label={bn ? 'প্রতিষ্ঠানের ধরন' : 'Institution type'} options={SCHOOL_TYPES} value={form.school_type} onChange={set('school_type')} />
            <SelectField label={bn ? 'বিভাগ' : 'Division'} options={DIVISIONS.map((d) => [d, d])} value={form.division} onChange={set('division')} />
            <TextField label={bn ? 'জেলা' : 'District'} value={form.district} onChange={set('district')} />
            <SelectField label={bn ? 'এলাকার ধরন' : 'Area type'} options={AREA_TYPES} value={form.area_type} onChange={set('area_type')} />
            {isStudent ? (
              <>
                <SelectField label={bn ? 'শ্রেণি' : 'Class'} options={GRADES} value={form.grade} onChange={set('grade')} />
                <SelectField label={bn ? 'এইচএসসি ব্যাচ' : 'HSC batch'} options={BATCH_YEARS} value={form.hsc_batch_year} onChange={set('hsc_batch_year')} />
                <SelectField label={bn ? 'গ্রুপ' : 'Group'} options={GROUPS} value={form.academic_group} onChange={set('academic_group')} />
                <SelectField label={bn ? 'মাধ্যম' : 'Medium'} options={MEDIUMS} value={form.medium} onChange={set('medium')} />
              </>
            ) : (
              <>
                <TextField label={bn ? 'পদবি' : 'Designation'} value={form.designation} onChange={set('designation')} />
                <TextField label={bn ? 'শিক্ষকতার অভিজ্ঞতা (বছর)' : 'Teaching experience (years)'} type="number" min="0" value={form.teaching_years} onChange={set('teaching_years')} />
              </>
            )}
          </div>
        </Section>

        {isStudent && (
          <Section icon={<BookOpen className="w-4 h-4 text-primary" />} title={bn ? 'শেখার পটভূমি' : 'Learning background'} subtitle={bn ? 'গবেষণায় ফলাফল ব্যাখ্যা করতে এই তথ্য কাজে লাগে' : 'Used as study covariates when analysing learning gains'}>
            <div className="space-y-4">
              <ChipGroup label={bn ? 'প্রোগ্রামিং অভিজ্ঞতা' : 'Programming experience'} options={EXPERIENCE} value={form.prior_experience} onChange={set('prior_experience')} />
              <ChipGroup label={bn ? 'যেসব ভাষা আগে দেখেছেন' : 'Languages you have tried'} options={LANGUAGES_KNOWN} value={form.languages_known} onChange={set('languages_known')} multi />
              <ChipGroup label={bn ? 'AI টুল ব্যবহার' : 'Use of AI tools'} options={AI_FAMILIARITY} value={form.ai_tool_familiarity} onChange={set('ai_tool_familiarity')} />
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <SelectField label={bn ? 'মূল ডিভাইস' : 'Main device'} options={DEVICES} value={form.device_type} onChange={set('device_type')} />
                <SelectField label={bn ? 'ইন্টারনেট সংযোগ' : 'Internet access'} options={INTERNET} value={form.internet_access} onChange={set('internet_access')} />
                <SelectField label={bn ? 'বাসায় কম্পিউটার' : 'Computer at home'} options={[['yes', bn ? 'হ্যাঁ' : 'Yes'], ['no', bn ? 'না' : 'No']]} value={form.has_computer_at_home} onChange={set('has_computer_at_home')} />
                <SelectField label={bn ? 'সাপ্তাহিক পড়ার সময়' : 'Weekly ICT study time'} options={STUDY_HOURS} value={form.weekly_study_hours} onChange={set('weekly_study_hours')} />
              </div>
              <ChipGroup label={bn ? 'শেখার লক্ষ্য' : 'Learning goals'} options={GOALS} value={form.learning_goals} onChange={set('learning_goals')} multi />
            </div>
          </Section>
        )}

        <div className="flex justify-end">
          <button type="submit" disabled={saving} className="px-5 py-2.5 rounded-xl bg-primary hover:bg-primary-container text-on-primary text-xs font-extrabold flex items-center gap-2 shadow-lg shadow-primary/20 transition-all disabled:opacity-60">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} {saving ? (bn ? 'সংরক্ষণ হচ্ছে...' : 'Saving...') : (bn ? 'পরিবর্তন সংরক্ষণ করুন' : 'Save changes')}
          </button>
        </div>
      </form>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Section icon={<ShieldCheck className="w-4 h-4 text-emerald-400" />} title={bn ? 'গবেষণায় অংশগ্রহণ' : 'Research participation'}>
          <dl className="text-xs space-y-2.5">
            <div className="flex justify-between gap-3"><dt className="text-on-surface-variant">{bn ? 'সম্মতি' : 'Consent'}</dt><dd className={`font-bold ${user.consent_given ? 'text-emerald-400' : 'text-amber-400'}`}>{user.consent_given ? `${bn ? 'প্রদত্ত' : 'Given'}${user.consent_at ? ` · ${new Date(user.consent_at).toLocaleDateString()}` : ''}` : (bn ? 'দেওয়া হয়নি' : 'Not given')}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-on-surface-variant">{bn ? 'পার্টিসিপ্যান্ট কোড' : 'Participant code'}</dt><dd className="font-mono font-bold text-on-surface">{user.participant_code}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-on-surface-variant">{bn ? 'টিউটর মোড' : 'Tutor mode'}</dt><dd className="font-bold text-on-surface">{armLabel(user.arm)}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-on-surface-variant">{bn ? 'ডেটা ব্যবহার' : 'Data use'}</dt><dd className="text-on-surface text-right max-w-[60%]">{bn ? 'কোড, প্রশ্ন ও স্কোর কেবল কোড নম্বরে সংরক্ষিত হয়' : 'Code, questions and scores are stored under your code only'}</dd></div>
          </dl>
          <p className="text-[11px] text-on-surface-variant mt-4 leading-relaxed">
            {bn ? 'গবেষণা থেকে সরে যেতে বা আপনার ডেটা মুছতে গবেষণা সমন্বয়কের সাথে যোগাযোগ করুন এবং আপনার participant code জানান।' : 'To withdraw from the study or request deletion of your data, contact the research coordinator and quote your participant code.'}
          </p>
        </Section>

        <Section icon={<KeyRound className="w-4 h-4 text-primary" />} title={bn ? 'পাসওয়ার্ড পরিবর্তন' : 'Change password'}>
          <form onSubmit={handlePassword} className="space-y-3">
            {pwState.error && <div className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded-lg px-3 py-2">{pwState.error}</div>}
            {pwState.ok && <div className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">{bn ? 'পাসওয়ার্ড পরিবর্তিত হয়েছে।' : 'Password updated.'}</div>}
            <PasswordField label={bn ? 'বর্তমান পাসওয়ার্ড' : 'Current password'} value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} autoComplete="current-password" required />
            <div>
              <PasswordField label={bn ? 'নতুন পাসওয়ার্ড' : 'New password'} value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} autoComplete="new-password" required />
              <StrengthMeter password={pw.next} />
            </div>
            <PasswordField label={bn ? 'নতুন পাসওয়ার্ড নিশ্চিত করুন' : 'Confirm new password'} value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} autoComplete="new-password" required />
            <button type="submit" disabled={pwState.saving || !pw.current || !pw.next} className="px-4 py-2 rounded-xl bg-surface-container-high border border-outline-variant/40 text-on-surface text-xs font-bold flex items-center gap-2 hover:bg-surface-container-highest transition-colors disabled:opacity-50">
              {pwState.saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4 text-primary" />} {bn ? 'পাসওয়ার্ড আপডেট' : 'Update password'}
            </button>
          </form>
        </Section>
      </div>
    </div>
  );
};
