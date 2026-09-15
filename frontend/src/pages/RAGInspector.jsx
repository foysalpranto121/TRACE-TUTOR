import { useState, useEffect, useRef } from 'react';
import { apiService } from '../services/api';
import { BookOpen, Search, RefreshCw, Sparkles, CheckCircle2, FileText, AlertTriangle, Database, Cpu } from 'lucide-react';

export const RAGInspector = () => {
  const [searchQuery, setSearchQuery] = useState('for loop C programming');
  const [selectedLang, setSelectedLang] = useState('all');
  const [searchResults, setSearchResults] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState(null);
  const [searchError, setSearchError] = useState(null);
  const [ingestMessage, setIngestMessage] = useState(null);
  const pollRef = useRef(null);

  const refreshStatus = async () => {
    try {
      const s = await apiService.getRagStatus();
      setStatus(s);
      setStatusError(null);
      return s;
    } catch (err) {
      setStatusError(err.message);
      return null;
    }
  };

  // searchCurriculum is strict, so a failed retrieval rejects. Without this catch the
  // rejection was unhandled and the spinner stayed up for good.
  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    if (!searchQuery.trim()) return;
    setIsLoading(true);
    try {
      const langParam = selectedLang === 'all' ? null : selectedLang;
      setSearchResults(await apiService.searchCurriculum(searchQuery, langParam));
      setSearchError(null);
    } catch (err) {
      setSearchError(err.message);
      setSearchResults(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    // Wrapped so state is written after an await rather than during the effect.
    (async () => { await Promise.all([refreshStatus(), handleSearch()]); })();
    return () => clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // searchQuery is deliberately not a dependency: typing must not fire a request,
    // only submitting the form or changing the language filter does.
    (async () => { await handleSearch(); })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLang]);

  const running = status?.ingest?.running;

  useEffect(() => {
    clearInterval(pollRef.current);
    if (running) {
      pollRef.current = setInterval(async () => {
        const s = await refreshStatus();
        if (s && !s.ingest.running) {
          clearInterval(pollRef.current);
          setIngestMessage(s.ingest.error ? `Ingestion failed: ${s.ingest.error}` : `Ingestion finished. ${s.engine.vector_count} chunks are now searchable.`);
          handleSearch();
        }
      }, 3000);
    }
    return () => clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);

  const handleIngestBooks = async () => {
    setIngestMessage(null);
    try {
      const res = await apiService.ingestCurriculum({ workers: 3 });
      setIngestMessage(res.status === 'started' ? 'Started Gemini OCR + embedding of the RAG/ PDFs in the background. This takes a while for full books; progress updates below.' : 'Ingestion is already running.');
      refreshStatus();
    } catch (err) {
      setIngestMessage(`Could not start ingestion: ${err.message}`);
    }
  };

  const ingest = status?.ingest;
  const engine = status?.engine;
  const progressPct = ingest?.total_pages ? Math.round((ingest.done_pages / ingest.total_pages) * 100) : 0;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-on-surface flex items-center gap-2">
            <BookOpen className="w-7 h-7 text-primary" /> RAG Curriculum Vector Store Inspector
          </h1>
          <p className="text-xs text-on-surface-variant">
            Scanned NCTB PDFs in <code className="font-mono text-primary bg-primary/10 px-2 py-0.5 rounded border border-primary/30">RAG/</code> are OCR-transcribed with Gemini, chunked, embedded and stored in ChromaDB.
          </p>
        </div>

        <button
          onClick={handleIngestBooks}
          disabled={running}
          className="px-5 py-2.5 rounded-xl bg-primary hover:bg-primary-container text-on-primary font-bold text-xs flex items-center gap-2 shadow-lg shadow-primary/20 transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${running ? 'animate-spin' : ''}`} />
          {running ? `Ingesting... ${progressPct}%` : 'OCR + Index RAG Folder PDFs'}
        </button>
      </div>

      {statusError && (
        <div className="bg-rose-500/10 border border-rose-500/30 p-4 rounded-xl text-xs text-rose-400 font-mono flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" /> Backend status unavailable: {statusError}
        </div>
      )}

      {engine && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-surface-container p-4 rounded-xl border border-outline-variant/30">
            <div className="text-[10px] font-mono uppercase text-on-surface-variant flex items-center gap-1"><Database className="w-3 h-3" /> Vector chunks</div>
            <div className="text-xl font-extrabold text-primary">{engine.vector_count}</div>
          </div>
          <div className="bg-surface-container p-4 rounded-xl border border-outline-variant/30">
            <div className="text-[10px] font-mono uppercase text-on-surface-variant">DB passages</div>
            <div className="text-xl font-extrabold text-on-surface">{engine.db_passage_count}</div>
          </div>
          <div className="bg-surface-container p-4 rounded-xl border border-outline-variant/30">
            <div className="text-[10px] font-mono uppercase text-on-surface-variant flex items-center gap-1"><Cpu className="w-3 h-3" /> Models</div>
            <div className="text-[11px] font-mono text-on-surface">{engine.llm_model}</div>
            <div className="text-[11px] font-mono text-on-surface-variant">{engine.embedding_model}</div>
          </div>
          <div className="bg-surface-container p-4 rounded-xl border border-outline-variant/30">
            <div className="text-[10px] font-mono uppercase text-on-surface-variant">Gemini key</div>
            <div className={`text-sm font-extrabold ${engine.gemini_configured ? 'text-emerald-400' : 'text-rose-400'}`}>{engine.gemini_configured ? 'Configured' : 'Missing'}</div>
            <div className="text-[11px] font-mono text-on-surface-variant">retrieval: {engine.last_retrieval_backend}</div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {(status?.documents || []).map((doc) => (
          <div key={doc.name} className="bg-surface-container p-4 rounded-xl border border-outline-variant/30 flex items-start gap-3">
            <FileText className={`w-8 h-8 shrink-0 mt-0.5 ${doc.exists ? (doc.language === 'bn' ? 'text-emerald-400' : 'text-primary') : 'text-rose-400'}`} />
            <div className="min-w-0">
              <span className="text-xs font-bold text-on-surface block truncate">{doc.name}</span>
              <span className="text-[10px] font-mono text-on-surface-variant">{doc.exists ? `${doc.size_mb} MB` : 'missing'} - {doc.language === 'bn' ? 'Bangla' : 'English'}</span>
              <span className="text-[10px] text-on-surface-variant block mt-1">
                OCR pages cached: <strong className="text-on-surface">{doc.ocr_pages_cached}</strong> - indexed chunks: <strong className="text-on-surface">{doc.db_chunks}</strong>
              </span>
            </div>
          </div>
        ))}
      </div>

      {(ingestMessage || running || ingest?.error) && (
        <div className={`border p-4 rounded-xl text-xs font-mono space-y-2 ${ingest?.error ? 'bg-rose-500/10 border-rose-500/30 text-rose-400' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'}`}>
          <div className="flex items-center gap-2">
            {ingest?.error ? <AlertTriangle className="w-4 h-4 shrink-0" /> : <CheckCircle2 className="w-4 h-4 shrink-0" />}
            {ingestMessage || `Stage: ${ingest?.stage}`}
          </div>
          {running && (
            <div>
              <div className="flex justify-between text-[10px] mb-1"><span>{ingest.stage} - {ingest.current_doc}</span><span>{ingest.done_pages}/{ingest.total_pages} pages, {ingest.indexed_chunks} chunks</span></div>
              <div className="h-2 rounded-full bg-surface-container overflow-hidden"><div className="h-full bg-emerald-500 transition-all" style={{ width: `${progressPct}%` }} /></div>
            </div>
          )}
          {ingest?.log?.length > 0 && (
            <pre className="text-[10px] text-on-surface-variant max-h-32 overflow-y-auto whitespace-pre-wrap">{ingest.log.slice(-8).join('\n')}</pre>
          )}
        </div>
      )}

      <form onSubmit={handleSearch} className="bg-surface-container p-6 rounded-2xl border border-outline-variant/30 space-y-4 shadow-xl">
        <div className="flex flex-col md:flex-row gap-3">
          <div className="flex-1 flex items-center bg-surface-container-high rounded-xl px-4 py-3 border border-outline-variant/30 focus-within:border-primary">
            <Search className="w-5 h-5 text-on-surface-variant mr-3" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search NCTB concepts in Bangla (লুপ) or English (for loop)..."
              aria-label="Search NCTB curriculum passages"
              className="bg-transparent border-none outline-none text-sm text-on-surface w-full placeholder:text-outline"
            />
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 bg-surface-container-high p-1 rounded-xl border border-outline-variant/30 text-xs">
              {[['all', 'All Corpus'], ['bn', 'বাংলা (BV)'], ['en', 'English (EV)']].map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setSelectedLang(val)}
                  className={`px-3 py-2 rounded-lg font-semibold transition-colors ${selectedLang === val ? 'bg-primary text-on-primary' : 'text-on-surface-variant hover:text-on-surface'}`}
                >
                  {label}
                </button>
              ))}
            </div>
            <button type="submit" disabled={isLoading} className="px-6 py-3 rounded-xl bg-primary hover:bg-primary-container text-on-primary font-bold text-xs shadow-md shadow-primary/20 disabled:opacity-50">
              Search RAG
            </button>
          </div>
        </div>
      </form>

      <div className="space-y-4">
        <h3 className="text-xs font-bold text-on-surface uppercase tracking-wider flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" /> Retrieved passages
          </span>
          {searchResults && (
            <span className="font-mono text-primary font-normal">
              {searchResults.results_count} passages - {searchResults.retrieval_backend || 'keyword'} search
            </span>
          )}
        </h3>

        {isLoading && <div className="py-12 text-center text-xs text-primary font-mono animate-pulse">Embedding query and searching the vector store...</div>}

        {!isLoading && searchError && (
          <div className="bg-rose-500/10 border border-rose-500/30 p-4 rounded-xl text-xs text-rose-400 font-mono flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" /> Search failed: {searchError}
          </div>
        )}

        {!isLoading && !searchError && searchResults?.passages?.length === 0 && (
          <div className="text-xs text-on-surface-variant italic">No passages matched. If the index is empty, run the OCR + Index button above.</div>
        )}

        {!isLoading && !searchError && searchResults?.passages?.map((item) => (
          <div key={item.id} className="bg-surface-container p-6 rounded-2xl border border-outline-variant/30 hover:border-primary/40 transition-colors space-y-3 shadow-md">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className={`px-2 py-0.5 rounded font-mono text-[10px] font-bold shrink-0 ${item.language === 'bn' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' : 'bg-secondary/10 text-secondary border border-secondary/30'}`}>
                  {item.doc || (item.language === 'bn' ? 'Bangla' : 'English')}
                </span>
                <span className="text-xs font-bold text-on-surface truncate">{item.chapter}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono text-primary font-bold bg-primary/10 px-2 py-0.5 rounded border border-primary/30">
                  Similarity: {(item.similarity_score * 100).toFixed(0)}%
                </span>
                <span className="text-[11px] font-mono text-on-surface-variant">{item.source_ref}</span>
              </div>
            </div>
            <blockquote className="text-xs text-on-surface-variant leading-relaxed bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/20 whitespace-pre-wrap">
              {item.passage}
            </blockquote>
          </div>
        ))}
      </div>
    </div>
  );
};
