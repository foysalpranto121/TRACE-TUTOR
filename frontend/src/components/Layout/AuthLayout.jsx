import { Link } from 'react-router-dom';
import { Sun, Moon, Languages, Brain, Code2, BookOpen, ShieldCheck } from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { CodeRain } from '../ui/CodeRain';

const FEATURES = [
  { icon: Brain, bn: 'ধাপে ধাপে যুক্তি দেখানো AI টিউটর', en: 'Reasoning-visible AI tutor grounded in the NCTB textbook' },
  { icon: Code2, bn: 'রিয়েল কম্পাইলার ও টেস্ট কেস', en: 'Real C compiler, HTML validator and test cases' },
  { icon: BookOpen, bn: 'অধ্যায় ৪ ও ৫ এর অনুশীলন', en: 'Chapter 4 (HTML) & Chapter 5 (C) practice with citations' },
];

export const AuthLayout = ({ children, width = 'max-w-md' }) => {
  const { isDark, toggleTheme } = useTheme();
  const { language, setLanguage } = useAuth();

  return (
    <div className="min-h-screen bg-surface text-on-surface flex font-sans">
      <aside className="hidden lg:flex lg:w-[44%] xl:w-[40%] relative overflow-hidden flex-col justify-between p-10 bg-surface-container-low border-r border-outline-variant/20">
        <CodeRain density={0.7} opacity={0.55} />
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-32 -left-24 w-[420px] h-[420px] rounded-full bg-primary/15 blur-[110px]" />
          <div className="absolute bottom-0 right-0 w-[360px] h-[360px] rounded-full bg-secondary/15 blur-[120px]" />
          <div className="absolute inset-0 bg-grid opacity-80" />
        </div>

        <div className="relative">
          <Link to="/" className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-surface-container p-1.5 border border-primary/30 shadow-lg shadow-primary/10 flex items-center justify-center">
              <img src="/nctb_ict_logo.png" alt="NCTB ICT" className="w-full h-full object-contain" />
            </div>
            <div>
              <span className="text-lg font-extrabold tracking-tight block leading-tight">TRACE Tutor</span>
              <span className="text-[10px] font-mono text-primary font-bold uppercase tracking-widest">NCTB HSC ICT · Research Platform</span>
            </div>
          </Link>
        </div>

        <div className="relative space-y-8">
          <div className="space-y-3">
            <h1 className="text-3xl xl:text-4xl font-extrabold leading-tight tracking-tight">
              যুক্তি বুঝুন। কোড বুঝুন। <br />
              <span className="bg-gradient-to-r from-primary via-cyan-300 to-secondary bg-clip-text text-transparent">দক্ষতা গড়ুন।</span>
            </h1>
            <p className="text-sm text-on-surface-variant leading-relaxed max-w-md">
              Learn the logic, understand the code, build the skill. An AI tutor for Bangladesh&rsquo;s HSC ICT syllabus that shows its reasoning
              and cites the NCTB textbook - built for a controlled learning study.
            </p>
          </div>
          <ul className="space-y-3">
            {FEATURES.map(({ icon: Icon, bn, en }) => (
              <li key={en} className="flex items-start gap-3">
                <span className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/30 text-primary flex items-center justify-center shrink-0"><Icon className="w-4 h-4" /></span>
                <div>
                  <div className="text-sm font-bold">{bn}</div>
                  <div className="text-xs text-on-surface-variant">{en}</div>
                </div>
              </li>
            ))}
          </ul>
          <div className="rounded-xl border border-outline-variant/30 bg-surface-container/70 p-4 flex items-start gap-3">
            <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <p className="text-xs text-on-surface-variant leading-relaxed">
              Student data is stored under a pseudonymous participant code and used only for educational research under institutional ethics approval.
            </p>
          </div>
        </div>

        <div className="relative text-[11px] text-on-surface-variant font-mono flex items-center gap-4">
          <span>© 2026 TRACE Tutor Research</span>
          <span className="text-outline">·</span>
          <span>Consent v1</span>
          <span className="text-outline">·</span>
          <span>Privacy</span>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center justify-between p-4 sm:p-5">
          <Link to="/" className="flex items-center gap-2 lg:invisible">
            <img src="/nctb_ict_logo.png" alt="NCTB ICT" className="w-8 h-8 object-contain" />
            <span className="font-extrabold tracking-tight">TRACE Tutor</span>
          </Link>
          <div className="flex items-center gap-2">
            <button onClick={() => setLanguage(language === 'bn' ? 'en' : 'bn')} className="px-3 py-1.5 rounded-xl bg-surface-container border border-outline-variant/30 text-xs font-bold text-on-surface flex items-center gap-1.5 hover:bg-surface-container-high transition-colors">
              <Languages className="w-3.5 h-3.5 text-primary" /> {language === 'bn' ? 'বাংলা' : 'English'}
            </button>
            <button onClick={toggleTheme} className="p-2 rounded-xl bg-surface-container border border-outline-variant/30 text-on-surface-variant hover:bg-surface-container-high transition-colors" title="Toggle theme">
              {isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-600" />}
            </button>
          </div>
        </div>
        <div className="flex-1 flex items-start sm:items-center justify-center px-4 pb-10 sm:px-8">
          <div className={`w-full ${width}`}>{children}</div>
        </div>
      </main>
    </div>
  );
};
