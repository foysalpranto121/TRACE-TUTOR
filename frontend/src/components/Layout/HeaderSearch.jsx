import { useEffect, useId, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Search, LoaderCircle, Lock, X } from 'lucide-react';
import { useAuth } from '../../context/useAuth';
import { useResetOnChange } from '../../hooks/useResetOnChange';
import { loadLearningCatalog, searchLearningCatalog } from '../../services/learningSearch';

export function HeaderSearch() {
  const { user, role, language } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const container = useRef(null);
  const input = useRef(null);
  const listId = useId();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [catalogue, setCatalogue] = useState({ status: 'idle', items: [] });
  const authorized = Boolean(user) && ['STUDENT', 'EXPERT_TEACHER', 'RESEARCHER_ADMIN'].includes(role);
  const identity = String(user?.id || '') + ':' + role;
  const hasQuery = Boolean(query.trim());
  const results = authorized ? searchLearningCatalog(catalogue.items, query) : [];
  const expanded = open && hasQuery && authorized;

  useResetOnChange(identity, () => {
    setQuery(''); setOpen(false); setActiveIndex(-1); setCatalogue({ status: 'idle', items: [] });
  });
  useResetOnChange(location.pathname + location.search, () => {
    setOpen(false); setActiveIndex(-1);
  });

  useEffect(() => {
    if (!authorized || catalogue.status !== 'loading') return undefined;
    let current = true;
    loadLearningCatalog().then((items) => {
      if (current) setCatalogue({ status: 'ready', items });
    }).catch(() => {
      if (current) setCatalogue({ status: 'error', items: [] });
    });
    return () => { current = false; };
  }, [authorized, identity, catalogue.status]);

  useEffect(() => {
    const closeOutside = (event) => {
      if (!container.current?.contains(event.target)) { setOpen(false); setActiveIndex(-1); }
    };
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, []);

  useEffect(() => {
    if (expanded && activeIndex >= 0) document.getElementById(`${listId}-${activeIndex}`)?.scrollIntoView?.({ block: 'nearest' });
  }, [expanded, activeIndex, listId]);

  const startLoading = () => {
    if (authorized && catalogue.status === 'idle') setCatalogue({ status: 'loading', items: [] });
  };
  const select = (item) => {
    if (!authorized || !item || item.locked || !item.destination) return;
    setOpen(false); setQuery(''); setActiveIndex(-1);
    navigate(item.destination);
  };
  const handleKeyDown = (event) => {
    if (event.key === 'Escape') {
      event.preventDefault(); setOpen(false); setActiveIndex(-1); return;
    }
    if (!hasQuery || !authorized || !['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key)) return;
    event.preventDefault(); setOpen(true); startLoading();
    if (catalogue.status !== 'ready' || !results.length) return;
    if (event.key === 'Enter') {
      select(activeIndex < 0 ? results.find((item) => !item.locked && item.destination) : results[activeIndex]);
      return;
    }
    setActiveIndex((previous) => {
      if (previous < 0) return event.key === 'ArrowDown' ? 0 : results.length - 1;
      return (previous + (event.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length;
    });
  };

  return (
    <div ref={container} className="relative min-w-0 flex-1 md:flex-none md:w-72"
      onBlur={(event) => {
        if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) { setOpen(false); setActiveIndex(-1); }
      }}>
      <div className="flex items-center bg-surface-container rounded-xl px-3 py-2 border border-outline-variant/40 focus-within:border-primary/60 transition-colors">
        <Search className="w-3.5 h-3.5 text-on-surface-variant mr-2 shrink-0" aria-hidden="true" />
        <input ref={input} type="search" role="combobox" aria-label="Search topics and tasks"
          placeholder={language === 'bn' ? 'টপিক বা টাস্ক খুঁজুন...' : 'Search topics or tasks…'}
          autoComplete="off" aria-autocomplete="list" aria-haspopup="listbox" aria-expanded={expanded}
          aria-controls={expanded && catalogue.status === 'ready' && results.length ? listId : undefined}
          aria-activedescendant={expanded && results[activeIndex] ? `${listId}-${activeIndex}` : undefined}
          disabled={!authorized} value={query}
          onChange={(event) => {
            const value = event.target.value;
            setQuery(value); setActiveIndex(-1); setOpen(Boolean(value.trim()));
            if (value.trim()) startLoading();
          }}
          onFocus={() => { if (hasQuery) { setOpen(true); startLoading(); } }}
          onKeyDown={handleKeyDown}
          className="bg-transparent border-none outline-none text-xs w-full min-w-0 placeholder:text-outline" />
        {query && <button type="button" aria-label="Clear search" className="p-1 -mr-1 shrink-0 text-on-surface-variant hover:text-on-surface"
          onClick={() => { setQuery(''); setOpen(false); setActiveIndex(-1); input.current?.focus(); }}>
          <X className="w-3.5 h-3.5" aria-hidden="true" />
        </button>}
      </div>
      {expanded && <div className="absolute right-0 top-full mt-2 w-full md:w-96 max-w-[calc(100vw-1.5rem)] rounded-xl border border-outline-variant/40 bg-surface-container shadow-lift z-50 overflow-hidden">
        {catalogue.status === 'loading' || catalogue.status === 'idle' ? (
          <p role="status" className="p-3 text-xs text-on-surface-variant flex items-center gap-2"><LoaderCircle className="w-4 h-4 animate-spin shrink-0" aria-hidden="true" />Loading topics and tasks…</p>
        ) : catalogue.status === 'error' ? (
          <div className="p-3 space-y-2 text-xs">
            <p role="alert">Search is unavailable. Please try again.</p>
            <button type="button" className="text-primary font-semibold underline" onClick={() => setCatalogue({ status: 'loading', items: [] })}>Retry</button>
          </div>
        ) : !results.length ? (
          <p role="status" className="p-3 text-xs text-on-surface-variant">No matching topics or tasks found.</p>
        ) : (
          <>
            <p role="status" className="sr-only">{results.length} matching topics and tasks.</p>
            <div id={listId} role="listbox" aria-label="Topics and tasks" className="max-h-[min(24rem,60dvh)] overflow-y-auto overscroll-contain p-1">
              {results.map((item, index) => (
                <div key={item.id} id={`${listId}-${index}`} role="option" aria-selected={activeIndex === index}
                  aria-disabled={item.locked || undefined}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseMove={() => setActiveIndex(index)} onClick={() => select(item)}
                  className={`min-h-11 p-2.5 rounded-lg text-xs break-words ${item.locked ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'} ${activeIndex === index ? 'bg-primary/12' : 'hover:bg-surface-container-high'}`}>
                  <span className="block font-semibold text-on-surface">{item.title}</span>
                  <span className="block text-[10px] text-on-surface-variant mt-1">{item.chapter}</span>
                  {item.type !== 'Topic' && <span className="block text-[10px] text-on-surface-variant">{item.topic}</span>}
                  <span className="flex items-center gap-1 text-[10px] mt-1 text-on-surface-variant">{item.type} · {item.locked ? <><Lock className="w-3 h-3" aria-hidden="true" />Locked</> : 'Available'}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>}
    </div>
  );
}
