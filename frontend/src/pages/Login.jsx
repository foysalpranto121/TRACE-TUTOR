import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, Lock, User, AlertTriangle, Loader2, HelpCircle } from 'lucide-react';
import { useAuth, roleHome } from '../context/AuthContext';
import { AuthLayout } from '../components/Layout/AuthLayout';
import { TextField, PasswordField } from '../components/Form/fields';

export const Login = () => {
  const { login, user, ready, language } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = searchParams.get('next');

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState(null);
  const [showHelp, setShowHelp] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const submitted = useRef(false);

  useEffect(() => {
    if (ready && user && !submitted.current) navigate(next || roleHome(user.role), { replace: true });
  }, [ready]); // eslint-disable-line react-hooks/exhaustive-deps

  const bn = language === 'bn';

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!identifier.trim() || !password) {
      setError(bn ? 'ইউজারনেম ও পাসওয়ার্ড দিন।' : 'Enter your username and password.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      submitted.current = true;
      const u = await login(identifier.trim(), password, remember);
      navigate(next || roleHome(u.role), { replace: true });
    } catch (err) {
      submitted.current = false;
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout>
      <div className="bg-surface-container rounded-2xl border border-outline-variant/30 shadow-2xl p-6 sm:p-8 space-y-6">
        <div className="space-y-1">
          <div className="text-[11px] font-mono font-bold text-primary uppercase tracking-wider">{bn ? 'সাইন ইন' : 'Sign in'}</div>
          <h2 className="text-2xl font-extrabold text-on-surface tracking-tight">{bn ? 'আবার স্বাগতম' : 'Welcome back'}</h2>
          <p className="text-xs text-on-surface-variant">{bn ? 'আপনার TRACE Tutor অ্যাকাউন্টে প্রবেশ করে শেখা চালিয়ে যান।' : 'Sign in to continue learning with TRACE Tutor.'}</p>
        </div>

        {error && (
          <div role="alert" className="bg-rose-500/10 border border-rose-500/30 rounded-xl px-3.5 py-2.5 text-xs text-rose-400 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" /> <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <TextField
            label={bn ? 'ইউজারনেম বা ইমেইল' : 'Username or email'}
            icon={<User className="w-4 h-4" />}
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            placeholder="e.g. tanvir.rahman"
            autoComplete="username"
            autoFocus
            required
          />
          <div>
            <PasswordField
              label={bn ? 'পাসওয়ার্ড' : 'Password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
            <div className="flex items-center justify-between mt-2">
              <label className="flex items-center gap-2 text-xs text-on-surface-variant cursor-pointer select-none">
                <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="w-3.5 h-3.5 rounded border-outline-variant accent-cyan-500" />
                {bn ? 'আমাকে মনে রাখুন' : 'Remember me'}
              </label>
              <button type="button" onClick={() => setShowHelp(!showHelp)} className="text-xs font-bold text-primary hover:underline flex items-center gap-1">
                <HelpCircle className="w-3.5 h-3.5" /> {bn ? 'পাসওয়ার্ড ভুলে গেছেন?' : 'Forgot password?'}
              </button>
            </div>
            {showHelp && (
              <p className="mt-2 text-[11px] text-on-surface-variant bg-surface-container-high border border-outline-variant/30 rounded-lg p-2.5">
                {bn
                  ? 'পাসওয়ার্ড রিসেট গবেষণা সমন্বয়ক করেন। আপনার শিক্ষক বা গবেষণা দলের সাথে যোগাযোগ করুন এবং আপনার participant code (TT-xxxx) জানান।'
                  : 'Password resets are handled by the research coordinator. Contact your teacher or the research team and quote your participant code (TT-xxxx).'}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full py-3 rounded-xl bg-primary hover:bg-primary-container text-on-primary font-extrabold text-sm flex items-center justify-center gap-2 shadow-lg shadow-primary/20 transition-all disabled:opacity-60"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
            {submitting ? (bn ? 'যাচাই করা হচ্ছে...' : 'Signing in...') : (bn ? 'সাইন ইন' : 'Sign in')}
            {!submitting && <ArrowRight className="w-4 h-4" />}
          </button>
        </form>

        <div className="pt-4 border-t border-outline-variant/20 text-center text-xs text-on-surface-variant">
          {bn ? 'অ্যাকাউন্ট নেই?' : "Don't have an account?"}{' '}
          <Link to="/register" className="font-bold text-primary hover:underline">{bn ? 'নতুন অ্যাকাউন্ট তৈরি করুন' : 'Create an account'}</Link>
        </div>
      </div>
      <p className="text-center text-[11px] text-on-surface-variant mt-4">
        {bn ? 'শিক্ষক ও গবেষকরা একই ফর্মে সাইন ইন করুন; আপনার ভূমিকা অনুযায়ী পোর্টাল খুলবে।' : 'Teachers and researchers sign in here too - the portal opens according to your role.'}
      </p>
    </AuthLayout>
  );
};
