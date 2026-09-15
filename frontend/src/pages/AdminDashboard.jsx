import { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';
import { Users, Download, TrendingUp, Sliders, RefreshCw, ShieldCheck, CheckCircle2, AlertTriangle, Database, Info } from 'lucide-react';

// Every number on this page comes from the database. There are no illustrative
// defaults: when an outcome cannot be computed yet the cell shows an em dash and the
// reason, because a placeholder here would be read as a study result.
const EMPTY = '—';

const fmt = (value, digits = 2) =>
  (value === null || value === undefined || Number.isNaN(value) ? EMPTY : Number(value).toFixed(digits));

const fmtP = (p) => {
  if (p === null || p === undefined) return EMPTY;
  return p < 0.001 ? 'p < 0.001' : `p = ${p.toFixed(3)}`;
};

const OUTCOMES = [
  {
    key: 'learning_gain',
    label: 'Learning gain ⟨g⟩',
    chartLabel: 'Learning gain ⟨g⟩',
    digits: 3,
    hint: 'Normalized gain (post − pre) / (100 − pre), RQ1',
  },
  {
    key: 'transfer_performance',
    label: 'Transfer score (%)',
    chartLabel: 'Transfer score (%)',
    digits: 1,
    hint: 'Transfer form score, no tutor access, RQ2',
  },
  {
    key: 'ai_dependency_drop',
    label: 'Withdrawal drop (pp)',
    chartLabel: 'Withdrawal drop (pp)',
    digits: 1,
    hint: 'Withdrawal minus post, in percentage points. Negative = performance fell, RQ3',
  },
];

const StatCard = ({ label, value, sub, icon, tone = 'text-on-surface' }) => (
  <div className="bg-surface-container p-5 rounded-2xl border border-outline-variant/30 space-y-1 shadow-sm">
    <span className="text-[10px] font-mono text-on-surface-variant uppercase font-extrabold block">{label}</span>
    <div className={`text-2xl font-black flex items-center gap-2 ${tone}`}>
      {icon}
      {value}
    </div>
    {sub && <span className="text-[11px] text-on-surface-variant font-medium block">{sub}</span>}
  </div>
);

const OutcomeRow = ({ spec, data }) => {
  const treatment = data?.treatment;
  const control = data?.control;
  const testable = data?.p_value !== null && data?.p_value !== undefined;

  return (
    <tr className="border-t border-outline-variant/20 align-top">
      <td className="py-3 pr-4">
        <span className="block text-xs font-extrabold text-on-surface">{spec.label}</span>
        <span className="block text-[10px] text-on-surface-variant font-medium mt-0.5">{spec.hint}</span>
      </td>
      <td className="py-3 px-3 font-mono text-xs text-on-surface whitespace-nowrap">
        {fmt(treatment?.mean, spec.digits)}
        <span className="text-on-surface-variant"> ± {fmt(treatment?.sd, spec.digits)}</span>
        <span className="block text-[10px] text-on-surface-variant">n = {treatment?.n ?? 0}</span>
      </td>
      <td className="py-3 px-3 font-mono text-xs text-on-surface whitespace-nowrap">
        {fmt(control?.mean, spec.digits)}
        <span className="text-on-surface-variant"> ± {fmt(control?.sd, spec.digits)}</span>
        <span className="block text-[10px] text-on-surface-variant">n = {control?.n ?? 0}</span>
      </td>
      <td className="py-3 px-3 font-mono text-xs text-on-surface whitespace-nowrap">
        {fmt(data?.mean_difference, spec.digits)}
      </td>
      <td className="py-3 px-3 font-mono text-xs text-on-surface whitespace-nowrap">{fmt(data?.cohens_d)}</td>
      <td className="py-3 px-3 font-mono text-xs whitespace-nowrap">
        {testable ? (
          <span className={data.p_value < 0.05 ? 'text-emerald-600 dark:text-emerald-400 font-bold' : 'text-on-surface-variant'}>
            {fmtP(data.p_value)}
            <span className="block text-[10px] font-normal text-on-surface-variant">
              t({fmt(data.df, 1)}) = {fmt(data.t_statistic)}
            </span>
          </span>
        ) : (
          <span className="text-on-surface-variant">{data?.note || 'Not computable yet'}</span>
        )}
      </td>
    </tr>
  );
};

export const AdminDashboard = () => {
  const [stats, setStats] = useState(null);
  const [rag, setRag] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isIngesting, setIsIngesting] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsData, ragData] = await Promise.all([
        apiService.getAdminStats(),
        apiService.getRagStatus().catch(() => null),
      ]);
      setStats(statsData);
      setRag(ragData);
    } catch (err) {
      setError(err.message || 'Could not load study statistics.');
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleReindexRAG = async () => {
    setIsIngesting(true);
    setError(null);
    setNotice('Scanning RAG/ for source PDFs…');
    try {
      const res = await apiService.ingestCurriculum();
      const found = res.files_found || [];
      setNotice(
        res.status === 'already_running'
          ? 'An ingestion run is already in progress — watch its progress in the RAG inspector.'
          : `Ingestion started over ${found.length} PDF(s) in ${res.rag_directory}. Progress is reported in the RAG inspector.`
      );
    } catch (err) {
      setNotice(null);
      setError(err.message || 'Could not start ingestion.');
    } finally {
      setIsIngesting(false);
    }
  };

  const handleExportCSV = async () => {
    setIsExporting(true);
    setError(null);
    try {
      const { rows, filename } = await apiService.exportDataset();
      setNotice(`Exported ${rows} participant row(s) to ${filename}.`);
    } catch (err) {
      setNotice(null);
      setError(err.message || 'Export failed.');
    } finally {
      setIsExporting(false);
    }
  };

  // A metric only enters the chart once both arms actually have a mean to plot.
  const chartData = OUTCOMES.map((spec) => {
    const data = stats?.[spec.key];
    const t = data?.treatment?.mean;
    const c = data?.control?.mean;
    if (t === null || t === undefined || c === null || c === undefined) return null;
    return { metric: spec.chartLabel, Treatment: t, Control: c };
  }).filter(Boolean);

  const arms = stats?.arms || {};
  const treatmentN = arms.REASONING_VISIBLE ?? 0;
  const controlN = arms.ANSWER_ONLY ?? 0;
  const imbalance = Math.abs(treatmentN - controlN);
  const events = stats?.events || {};
  const completion = stats?.completion || {};

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-on-surface flex items-center gap-2">
            <Sliders className="w-7 h-7 text-primary" /> Researcher Dashboard
          </h1>
          <p className="text-xs text-on-surface-variant font-medium">
            Live study aggregates computed from participant submissions and interaction telemetry
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={load}
            disabled={loading}
            className="px-4 py-2.5 rounded-xl bg-surface-container hover:bg-surface-container-high text-on-surface font-bold text-xs border border-outline-variant/30 flex items-center gap-2 transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 text-primary ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>

          <button
            onClick={handleReindexRAG}
            disabled={isIngesting}
            className="px-4 py-2.5 rounded-xl bg-surface-container hover:bg-surface-container-high text-on-surface font-bold text-xs border border-outline-variant/30 flex items-center gap-2 transition-all disabled:opacity-50"
          >
            <Database className={`w-4 h-4 text-primary ${isIngesting ? 'animate-pulse' : ''}`} /> Re-index RAG PDFs
          </button>

          <button
            onClick={handleExportCSV}
            disabled={isExporting || !stats}
            className="px-4 py-2.5 rounded-xl bg-primary hover:bg-primary-container text-on-primary font-bold text-xs flex items-center gap-2 shadow-lg shadow-primary/20 transition-all disabled:opacity-50"
          >
            <Download className={`w-4 h-4 ${isExporting ? 'animate-bounce' : ''}`} /> Export dataset (CSV)
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/30 p-4 rounded-xl text-xs text-rose-600 dark:text-rose-400 font-bold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {notice && !error && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 p-4 rounded-xl text-xs text-emerald-600 dark:text-emerald-400 font-mono font-bold flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" /> {notice}
        </div>
      )}

      {loading && !stats && (
        <div className="bg-surface-container p-6 rounded-2xl border border-outline-variant/30 text-xs text-on-surface-variant font-mono">
          Loading study aggregates…
        </div>
      )}

      {stats && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
            <StatCard
              label="Enrolled participants (N)"
              value={stats.total_participants}
              sub={`${stats.consented_participants} consented · ${stats.staff_accounts} staff account(s)`}
              icon={<Users className="w-5 h-5 text-primary" />}
            />
            <StatCard
              label="Arm allocation"
              value={`${treatmentN} / ${controlN}`}
              sub={
                imbalance <= 1
                  ? 'Reasoning-visible / answer-only — balanced'
                  : `Reasoning-visible / answer-only — imbalance of ${imbalance}`
              }
              tone={imbalance <= 1 ? 'text-on-surface' : 'text-amber-500'}
            />
            <StatCard
              label="Submissions recorded"
              value={stats.submissions}
              sub={`pre ${completion.pre ?? 0} · post ${completion.post ?? 0} · transfer ${completion.transfer ?? 0} · withdrawal ${completion.withdrawal ?? 0}`}
            />
            <StatCard
              label="Telemetry events"
              value={(events.total ?? 0).toLocaleString()}
              sub={`${events.help_requests ?? 0} help · ${events.code_runs ?? 0} runs · ${events.copy_paste ?? 0} copies`}
            />
          </div>

          <div className="bg-surface-container p-6 rounded-2xl border border-outline-variant/30 space-y-4 shadow-xl">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <h3 className="text-sm font-extrabold text-on-surface flex items-center gap-2 uppercase tracking-wider">
                <TrendingUp className="w-4 h-4 text-primary" /> Arm comparison
              </h3>
              <span className="text-[10px] text-on-surface-variant font-medium flex items-center gap-1.5">
                <Info className="w-3 h-3" /> Welch&apos;s t-test, two-tailed · Cohen&apos;s d with pooled SD
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left">
                <thead>
                  <tr className="text-[10px] font-mono uppercase tracking-wider text-on-surface-variant">
                    <th className="pb-2 pr-4 font-extrabold">Outcome</th>
                    <th className="pb-2 px-3 font-extrabold">Reasoning-visible</th>
                    <th className="pb-2 px-3 font-extrabold">Answer-only</th>
                    <th className="pb-2 px-3 font-extrabold">Difference</th>
                    <th className="pb-2 px-3 font-extrabold">Cohen&apos;s d</th>
                    <th className="pb-2 px-3 font-extrabold">Significance</th>
                  </tr>
                </thead>
                <tbody>
                  {OUTCOMES.map((spec) => (
                    <OutcomeRow key={spec.key} spec={spec} data={stats[spec.key]} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-surface-container p-6 rounded-2xl border border-outline-variant/30 space-y-4 shadow-xl">
            <h3 className="text-sm font-extrabold text-on-surface flex items-center gap-2 uppercase tracking-wider">
              <TrendingUp className="w-4 h-4 text-primary" /> Outcome means by arm
            </h3>

            {chartData.length === 0 ? (
              <p className="text-xs text-on-surface-variant font-medium py-8 text-center">
                No outcome has data in both arms yet. The chart appears once participants have completed
                the matching forms.
              </p>
            ) : (
              <div className="h-72 w-full pt-4">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-outline-variant/40" />
                    <XAxis dataKey="metric" stroke="currentColor" className="text-on-surface-variant" fontSize={12} />
                    <YAxis stroke="currentColor" className="text-on-surface-variant" fontSize={12} />
                    <Tooltip
                      cursor={{ fillOpacity: 0.06 }}
                      contentStyle={{
                        backgroundColor: 'rgb(var(--surface-container-high, 23 31 51))',
                        borderColor: 'rgba(125,135,155,0.35)',
                        borderRadius: '12px',
                        fontSize: '12px',
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: '12px' }} />
                    <Bar dataKey="Treatment" fill="#0284c7" radius={[6, 6, 0, 0]} name="Reasoning-visible" />
                    <Bar dataKey="Control" fill="#4f46e5" radius={[6, 6, 0, 0]} name="Answer-only" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          <div className="bg-surface-container p-6 rounded-2xl border border-outline-variant/30 space-y-4 shadow-xl">
            <h3 className="text-sm font-extrabold text-on-surface flex items-center gap-2 uppercase tracking-wider">
              <ShieldCheck className="w-4 h-4 text-primary" /> Platform status
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-surface-container-high p-4 rounded-xl border border-outline-variant/30 space-y-1">
                <span className="text-xs font-bold text-on-surface block">Curriculum index</span>
                <span className="text-xs font-mono text-primary font-bold block">
                  {rag ? `${rag.engine?.vector_count ?? 0} vectors · ${rag.engine?.db_passage_count ?? 0} passages` : EMPTY}
                </span>
                <span className="text-[10px] text-on-surface-variant block">
                  {rag?.engine?.embedding_model || 'Embedding model unknown'}
                </span>
              </div>
              <div className="bg-surface-container-high p-4 rounded-xl border border-outline-variant/30 space-y-1">
                <span className="text-xs font-bold text-on-surface block">Tutor model</span>
                <span className="text-xs font-mono text-primary font-bold block">
                  {rag?.engine?.llm_model || EMPTY}
                </span>
                <span className="text-[10px] text-on-surface-variant block">
                  {rag?.engine?.gemini_configured ? 'API key configured' : 'No API key configured'}
                </span>
              </div>
              <div className="bg-surface-container-high p-4 rounded-xl border border-outline-variant/30 space-y-1">
                <span className="text-xs font-bold text-on-surface block">Active accounts</span>
                <span className="text-xs font-mono text-primary font-bold block">{stats.active_accounts}</span>
                <span className="text-[10px] text-on-surface-variant block">Pseudonymous participant codes in exports</span>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
