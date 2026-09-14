import React, { useState } from 'react';
import { Bot, CheckCircle2, Copy, Check, ShieldCheck, AlertTriangle } from 'lucide-react';
import { apiService } from '../../services/api';

export const AnswerOnlyPanel = ({
  solutionData,
  isLoading,
  error,
  onRequestHelp,
  onCopyCode,
}) => {
  const [copied, setCopied] = useState(false);
  const [queryText, setQueryText] = useState('');

  const handleCopy = (code) => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    apiService.logTelemetry('COPY_PASTE', { code_length: code.length });
    if (onCopyCode) onCopyCode(code);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleHelpSubmit = (e) => {
    e.preventDefault();
    if (!queryText.trim()) return;
    if (onRequestHelp) onRequestHelp(queryText);
    setQueryText('');
  };

  const directAnswer = solutionData?.direct_answer || '';
  const codeSolution = solutionData?.independent_ai_answer?.code_solution || solutionData?.code_solution || '';
  const modelLabel = solutionData?.model || 'Gemini';

  return (
    <div className="flex flex-col h-full bg-surface-container rounded-2xl border border-outline-variant/30 overflow-hidden shadow-2xl">
      <div className="px-5 py-4 bg-surface-container-high border-b border-outline-variant/30 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-500 shadow-sm">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-extrabold text-on-surface flex items-center gap-2">
              AI Assistant <span className="px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px] font-mono border border-amber-500/30 font-extrabold">Answer-Only Arm</span>
            </h3>
            <p className="text-[11px] text-on-surface-variant font-medium">Direct solution & code fix output</p>
          </div>
        </div>

        <div className="px-2.5 py-1 rounded-full bg-surface-container border border-outline-variant/30 text-on-surface-variant text-[11px] font-mono font-bold flex items-center gap-1 shadow-sm">
          <ShieldCheck className="w-3.5 h-3.5 text-primary" />
          {modelLabel}{solutionData?.cached ? ' · cached' : ''}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {isLoading && (
          <div className="py-12 flex flex-col items-center justify-center space-y-3">
            <div className="w-10 h-10 border-3 border-amber-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs text-amber-500 font-mono font-bold animate-pulse">Generating direct code fix...</span>
          </div>
        )}

        {!isLoading && error && (
          <div className="bg-rose-500/10 border border-rose-500/30 rounded-xl p-4 text-xs text-rose-400 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <div className="font-bold">AI request failed</div>
              <div className="font-mono mt-1">{error}</div>
            </div>
          </div>
        )}

        {!isLoading && solutionData && (
          <div className="space-y-4">
            {solutionData.ai_status === 'fallback' && (
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-3 text-[11px] text-amber-500">
                {modelLabel} did not respond: {solutionData.error}
              </div>
            )}

            {directAnswer && (
              <div className="bg-surface-container-high p-4 rounded-xl border border-outline-variant/30 text-xs text-on-surface leading-relaxed whitespace-pre-wrap">
                {directAnswer}
              </div>
            )}

            <div className="flex items-center justify-between">
              <h4 className="text-xs font-extrabold text-on-surface uppercase tracking-wider flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" /> Direct Solution Output
              </h4>
              {codeSolution && (
                <button
                  onClick={() => handleCopy(codeSolution)}
                  className="px-2.5 py-1 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-xs font-mono text-primary font-bold flex items-center gap-1 transition-colors border border-outline-variant/20 shadow-sm"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                  {copied ? 'Copied!' : 'Copy Solution'}
                </button>
              )}
            </div>

            {codeSolution && (
              <div className="bg-slate-900 dark:bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/30 overflow-x-auto shadow-inner">
                <pre className="font-mono text-xs text-amber-300 leading-relaxed whitespace-pre-wrap">{codeSolution}</pre>
              </div>
            )}
          </div>
        )}
      </div>

      <form onSubmit={handleHelpSubmit} className="p-4 bg-surface-container-high border-t border-outline-variant/30 flex gap-2">
        <input
          type="text"
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          placeholder="Ask for the direct solution or fix..."
          className="flex-1 bg-surface-container rounded-xl px-4 py-2.5 text-xs text-on-surface font-medium placeholder:text-outline border border-outline-variant/30 focus:border-amber-500 outline-none shadow-sm"
        />
        <button type="submit" disabled={!queryText.trim() || isLoading} className="px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs shadow-md disabled:opacity-50 transition-all">
          Get Fix
        </button>
      </form>
    </div>
  );
};
