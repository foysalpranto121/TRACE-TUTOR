import { useState, useRef, useEffect, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import {
  Play,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Terminal,
  Code2,
  Maximize2,
  Trash2,
  ChevronUp,
  ChevronDown,
  FileCode,
  Bug,
  Loader2,
  Info,
} from 'lucide-react';
import { apiService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';

const MONACO_LANG = { c: 'c', cpp: 'cpp', python: 'python', html: 'html' };

// Editor themes built from the app palette so the IDE reads as part of the product.
const MONACO_THEMES = {
  'trace-dark': {
    base: 'vs-dark',
    colors: {
      'editor.background': '#090e1e',
      'editor.lineHighlightBackground': '#111a32',
      'editorLineNumber.foreground': '#3c4c74',
      'editorLineNumber.activeForeground': '#22d3ee',
      'editorCursor.foreground': '#22d3ee',
      'editor.selectionBackground': '#22d3ee33',
      'editorIndentGuide.background1': '#1c2740',
      'editorGutter.background': '#090e1e',
    },
    rules: [
      { token: 'comment', foreground: '5b6b90', fontStyle: 'italic' },
      { token: 'keyword', foreground: 'a78bfa' },
      { token: 'string', foreground: '86efac' },
      { token: 'number', foreground: 'fbbf24' },
      { token: 'type', foreground: '22d3ee' },
      { token: 'tag', foreground: '22d3ee' },
      { token: 'attribute.name', foreground: 'a78bfa' },
    ],
  },
  'trace-soft': {
    base: 'vs',
    colors: {
      'editor.background': '#f4f0e9',
      'editor.lineHighlightBackground': '#ebe5da',
      'editorLineNumber.foreground': '#9a9180',
      'editorLineNumber.activeForeground': '#0f766e',
      'editorCursor.foreground': '#0f766e',
      'editor.selectionBackground': '#0f766e26',
      'editorGutter.background': '#f4f0e9',
    },
    rules: [
      { token: 'comment', foreground: '64748b', fontStyle: 'italic' },
      { token: 'keyword', foreground: '6d28d9' },
      { token: 'string', foreground: '047857' },
      { token: 'number', foreground: 'b45309' },
      { token: 'type', foreground: '0e7490' },
      { token: 'tag', foreground: '0e7490' },
      { token: 'attribute.name', foreground: '6d28d9' },
    ],
  },
};
const SERVER_LANGS = ['c', 'cpp', 'python', 'html'];
const CHECK_DEBOUNCE_MS = 900;

const DEFAULT_CODE = {
  c: `#include <stdio.h>\n\nint main() {\n    printf("Sum = 15\\n");\n    return 0;\n}`,
  cpp: `#include <iostream>\nusing namespace std;\n\nint main() {\n    cout << "Sum = 15" << endl;\n    return 0;\n}`,
  python: `n = 5\nprint("Sum =", sum(range(1, n + 1)))`,
  html: `<!DOCTYPE html>\n<html>\n<body>\n  <h2>NCTB HSC ICT Chapter 4</h2>\n  <p>Hello Web Design!</p>\n</body>\n</html>`,
};

export const CodeEditor = ({
  initialCode = '',
  sampleCases = [],
  htmlChecks = [],
  language = 'c',
  onCodeChange,
  onSubmit,
  onCompileResult,
  readOnly = false,
  activeProblem = null,
}) => {
  const { isDark } = useTheme();
  const { language: langPreference } = useAuth();
  const [selectedLang, setSelectedLang] = useState(language);
  const [code, setCode] = useState(initialCode || DEFAULT_CODE[language] || DEFAULT_CODE.c);
  const [isRunning, setIsRunning] = useState(false);
  const [consoleOutput, setConsoleOutput] = useState(null);
  const [editorTab, setEditorTab] = useState('code'); // 'code' | 'specs'
  const [diagnostics, setDiagnostics] = useState([]);
  const [checkState, setCheckState] = useState('idle'); // idle | checking | clean | problems | offline
  const [compilerInfo, setCompilerInfo] = useState(null);

  const [terminalHeight, setTerminalHeight] = useState(220);
  const [activeTab, setActiveTab] = useState('problems'); // problems | testcases | stdout | preview
  const [isResizing, setIsResizing] = useState(false);
  const isDragging = useRef(false);
  const startY = useRef(0);
  const startHeight = useRef(220);
  const containerRef = useRef(null);
  const editorRef = useRef(null);
  const monacoRef = useRef(null);
  const checkTimer = useRef(null);
  const checkSeq = useRef(0);
  const runTimers = useRef([]);
  const [runLog, setRunLog] = useState([]);

  // Stream fake-but-accurate build steps while the real request is in flight, so
  // running code reads like a terminal instead of a frozen spinner.
  const startRunLog = (lang) => {
    runTimers.current.forEach(clearTimeout);
    runTimers.current = [];
    const file = lang === 'html' ? 'index.html' : lang === 'cpp' ? 'main.cpp' : lang === 'python' ? 'main.py' : 'main.c';
    const steps = lang === 'html'
      ? [`$ html5validator ${file}`, '> parsing document tree...', '> checking task requirements...']
      : lang === 'python'
        ? [`$ python ${file}`, '> running...']
        : [`$ ${(compilerInfo?.c || 'cc')} -Wall ${file} -o main`, '> compiling...', '> linking...', '$ ./main'];
    setRunLog([]);
    steps.forEach((line, i) => {
      runTimers.current.push(setTimeout(() => setRunLog((l) => [...l, line]), i * 240));
    });
  };

  useEffect(() => () => runTimers.current.forEach(clearTimeout), []);

  useEffect(() => {
    setSelectedLang(language);
    setActiveTab('problems');
  }, [language]);

  useEffect(() => {
    apiService.getCodeStatus().then(setCompilerInfo).catch(() => setCompilerInfo({ ready: false, hint: 'Backend not reachable' }));
  }, []);

  const applyMarkers = useCallback((diags) => {
    const monaco = monacoRef.current;
    const editor = editorRef.current;
    if (!monaco || !editor) return;
    const model = editor.getModel();
    if (!model) return;
    const sevMap = { error: monaco.MarkerSeverity.Error, warning: monaco.MarkerSeverity.Warning, note: monaco.MarkerSeverity.Info, info: monaco.MarkerSeverity.Info };
    monaco.editor.setModelMarkers(
      model,
      'trace-tutor',
      (diags || []).map((d) => {
        const lineCount = model.getLineCount();
        const line = Math.min(Math.max(1, d.line || 1), lineCount);
        const maxCol = model.getLineMaxColumn(line);
        const col = Math.min(Math.max(1, d.column || 1), maxCol);
        return {
          startLineNumber: line,
          startColumn: col,
          endLineNumber: line,
          endColumn: maxCol,
          message: d.message,
          severity: sevMap[d.severity] || monaco.MarkerSeverity.Error,
          source: d.severity === 'error' ? 'compiler' : 'lint',
        };
      })
    );
  }, []);

  const publishDiagnostics = useCallback(
    (diags, state) => {
      setDiagnostics(diags);
      applyMarkers(diags);
      setCheckState(state ?? (diags.some((d) => d.severity === 'error') ? 'problems' : 'clean'));
    },
    [applyMarkers]
  );

  const runCheck = useCallback(
    async (source, lang) => {
      const seq = ++checkSeq.current;
      if (!SERVER_LANGS.includes(lang)) {
        publishDiagnostics([], 'idle');
        return;
      }
      try {
        const res = await apiService.runCode(lang, source, [], 'check');
        if (seq !== checkSeq.current) return;
        publishDiagnostics(res.diagnostics || []);
      } catch (_) {
        if (seq !== checkSeq.current) return;
        publishDiagnostics([], 'offline');
      }
    },
    [publishDiagnostics]
  );

  useEffect(() => {
    // initial check once the editor mounts / language changes
    if (editorRef.current) runCheck(code, selectedLang);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLang]);

  useEffect(() => () => clearTimeout(checkTimer.current), []);

  const handleEditorBeforeMount = (monaco) => {
    Object.entries(MONACO_THEMES).forEach(([name, theme]) => {
      monaco.editor.defineTheme(name, { base: theme.base, inherit: true, rules: theme.rules, colors: theme.colors });
    });
  };

  const handleEditorMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    runCheck(code, selectedLang);
  };

  const handleEditorChange = (value) => {
    const next = value || '';
    setCode(next);
    if (onCodeChange) onCodeChange(next);
    setCheckState('checking');
    clearTimeout(checkTimer.current);
    checkTimer.current = setTimeout(() => runCheck(next, selectedLang), CHECK_DEBOUNCE_MS);
  };

  const jumpTo = (d) => {
    const editor = editorRef.current;
    if (!editor) return;
    setEditorTab('code');
    editor.revealLineInCenter(d.line || 1);
    editor.setPosition({ lineNumber: d.line || 1, column: d.column || 1 });
    editor.focus();
  };

  const handleRunCode = async () => {
    setIsRunning(true);
    if (terminalHeight < 80) setTerminalHeight(220);
    clearTimeout(checkTimer.current);
    setConsoleOutput({ status: 'RUNNING', message: selectedLang === 'html' ? 'Rendering HTML5 web page...' : `Compiling with ${compilerInfo?.c || 'the C compiler'} and running test cases...` });
    startRunLog(selectedLang);
    apiService.logTelemetry('CODE_RUN', { language: selectedLang, code_length: code.length });

    if (selectedLang === 'html') {
      try {
        const res = await apiService.runCode('html', code, htmlChecks, 'run');
        const diags = res.diagnostics || [];
        publishDiagnostics(diags);
        const hasErrors = diags.some((d) => d.severity === 'error');
        const anyFailed = (res.test_results || []).some((t) => !t.passed);
        const out = {
          status: res.status,
          compiler: res.compiler,
          htmlContent: code,
          diagnostics: diags,
          compile_output: res.compile_output || '',
          testResults: res.test_results || [],
          passed_count: res.passed_count ?? 0,
        };
        setConsoleOutput(out);
        if (onCompileResult) onCompileResult(out);
        apiService.logTelemetry('CODE_RESULT', { problem_id: activeProblem?.id, language: 'html', status: res.status, passed_count: res.passed_count ?? 0, total: (res.test_results || []).length });
        setActiveTab(hasErrors ? 'problems' : anyFailed ? 'testcases' : 'preview');
      } catch (err) {
        setConsoleOutput({ status: 'SUCCESS', htmlContent: code, compile_output: `HTML validation unavailable (${err.message}) - showing the preview only.`, testResults: [] });
        setActiveTab('preview');
      } finally {
        setIsRunning(false);
      }
      return;
    }

    try {
      const res = await apiService.runCode(selectedLang, code, sampleCases, 'run');
      const diags = res.diagnostics || [];
      publishDiagnostics(diags);
      const out = {
        status: res.status,
        compiler: res.compiler,
        diagnostics: diags,
        compile_output: res.compile_output || '',
        testResults: res.test_results || [],
        passed_count: res.passed_count ?? 0,
        message: res.message,
      };
      setConsoleOutput(out);
      if (onCompileResult) onCompileResult(out);
      apiService.logTelemetry('CODE_RESULT', { problem_id: activeProblem?.id, language: selectedLang, status: res.status, passed_count: res.passed_count ?? 0, total: (res.test_results || []).length });
      setActiveTab(res.status === 'COMPILE_ERROR' ? 'problems' : 'testcases');
    } catch (err) {
      setConsoleOutput({ status: 'ERROR', stderr: err.message });
      setActiveTab('stdout');
    } finally {
      setIsRunning(false);
    }
  };

  const handleReset = () => {
    const next = initialCode || DEFAULT_CODE[selectedLang] || '';
    setCode(next);
    if (onCodeChange) onCodeChange(next);
    setConsoleOutput(null);
    runCheck(next, selectedLang);
  };

  const handleMouseDown = (e) => {
    e.preventDefault();
    e.stopPropagation();
    isDragging.current = true;
    startY.current = e.clientY;
    startHeight.current = terminalHeight;
    setIsResizing(true);

    const handleMouseMove = (moveEvent) => {
      if (!isDragging.current) return;
      const deltaY = startY.current - moveEvent.clientY;
      const containerHeight = containerRef.current ? containerRef.current.clientHeight : 600;
      const maxTerminalHeight = Math.max(300, containerHeight - 80);
      setTerminalHeight(Math.max(38, Math.min(maxTerminalHeight, startHeight.current + deltaY)));
    };
    const handleMouseUp = () => {
      isDragging.current = false;
      setIsResizing(false);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const errorCount = diagnostics.filter((d) => d.severity === 'error').length;
  const warningCount = diagnostics.filter((d) => d.severity === 'warning').length;
  const fileName = selectedLang === 'html' ? 'index.html' : selectedLang === 'cpp' ? 'main.cpp' : selectedLang === 'python' ? 'main.py' : 'main.c';

  const statusPill = (() => {
    if (checkState === 'checking') return { cls: 'text-on-surface-variant border-outline-variant/30', icon: <Loader2 className="w-3 h-3 animate-spin" />, text: 'Checking...' };
    if (checkState === 'offline') return { cls: 'text-amber-500 border-amber-500/40 bg-amber-500/10', icon: <AlertCircle className="w-3 h-3" />, text: 'Compiler offline' };
    if (checkState === 'problems' || errorCount > 0) return { cls: 'text-rose-500 border-rose-500/40 bg-rose-500/10', icon: <AlertCircle className="w-3 h-3" />, text: `${errorCount} error${errorCount === 1 ? '' : 's'}${warningCount ? `, ${warningCount} warning${warningCount === 1 ? '' : 's'}` : ''}` };
    if (checkState === 'clean') return { cls: 'text-emerald-500 border-emerald-500/40 bg-emerald-500/10', icon: <CheckCircle2 className="w-3 h-3" />, text: warningCount ? `${warningCount} warning${warningCount === 1 ? '' : 's'}` : 'No problems' };
    return { cls: 'text-on-surface-variant border-outline-variant/30', icon: <Info className="w-3 h-3" />, text: 'Ready' };
  })();

  const tabButton = (id, icon, label, badge) => (
    <button
      onClick={() => setActiveTab(id)}
      className={`px-2.5 py-1 rounded-md font-bold transition-all flex items-center gap-1.5 ${
        activeTab === id ? 'bg-primary/20 text-primary border border-primary/40' : 'text-on-surface-variant hover:text-on-surface'
      }`}
    >
      {icon}
      <span>{label}</span>
      {badge}
    </button>
  );

  return (
    <div ref={containerRef} className="flex flex-col h-full bg-surface-container rounded-2xl border border-outline-variant/30 overflow-hidden shadow-xl relative min-h-0">
      {isResizing && <div className="fixed inset-0 z-50 cursor-ns-resize select-none bg-transparent" />}

      {/* Toolbar */}
      <div className="px-3 py-2 bg-surface-container-high border-b border-outline-variant/30 flex items-center justify-between shrink-0 select-none gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <div className="flex items-center gap-1 bg-surface-container p-1 rounded-xl border border-outline-variant/30">
            <button
              onClick={() => setEditorTab('code')}
              className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-1.5 ${
                editorTab === 'code' ? 'bg-primary/20 text-primary border border-primary/40 shadow-sm' : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              <Code2 className="w-3.5 h-3.5" />
              <span>{fileName}</span>
            </button>
            {activeProblem && (
              <button
                onClick={() => setEditorTab('specs')}
                className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-1.5 ${
                  editorTab === 'specs' ? 'bg-primary/20 text-primary border border-primary/40 shadow-sm' : 'text-on-surface-variant hover:text-on-surface'
                }`}
              >
                <FileCode className="w-3.5 h-3.5" />
                <span>Task Specs</span>
              </button>
            )}
          </div>

          <div className="hidden 2xl:flex items-center gap-2 px-3 py-1 rounded-lg bg-surface-container border border-outline-variant/30 text-xs font-mono">
            <span className="text-on-surface-variant text-[11px]">Lang:</span>
            <select
              value={selectedLang}
              onChange={(e) => {
                const next = e.target.value;
                setSelectedLang(next);
                setConsoleOutput(null);
                setActiveTab('problems');
              }}
              className="bg-transparent border-none outline-none text-on-surface font-bold cursor-pointer"
            >
              <option value="c" className="bg-surface-container text-on-surface">C (NCTB)</option>
              <option value="html" className="bg-surface-container text-on-surface">HTML5 (Web Design)</option>
              <option value="cpp" className="bg-surface-container text-on-surface">C++</option>
              <option value="python" className="bg-surface-container text-on-surface">Python 3</option>
            </select>
          </div>

          <button
            onClick={() => { setActiveTab('problems'); if (terminalHeight < 80) setTerminalHeight(220); }}
            className={`px-2.5 py-1 rounded-lg text-[11px] font-mono font-bold border flex items-center gap-1.5 whitespace-nowrap shrink-0 transition-colors ${statusPill.cls}`}
            title="Live diagnostics from the real compiler (click to open Problems)"
          >
            {statusPill.icon}
            <span>{statusPill.text}</span>
          </button>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setTerminalHeight(terminalHeight < 80 ? 220 : terminalHeight === 220 ? 380 : 38)}
            className="hidden sm:flex px-2.5 py-1 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface text-xs font-mono font-bold transition-colors border border-outline-variant/30 items-center gap-1"
            title="Toggle Console Height (Min / Half / Max)"
          >
            <Terminal className="w-3.5 h-3.5 text-primary" />
            <span className="text-[10px]">{terminalHeight < 80 ? 'Min' : terminalHeight > 300 ? 'Max' : 'Half'}</span>
          </button>

          <button
            onClick={handleReset}
            className="p-1.5 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface text-xs transition-colors border border-outline-variant/20"
            title="Reset code"
          >
            <RotateCcw className="w-4 h-4" />
          </button>

          <button
            onClick={handleRunCode}
            disabled={isRunning}
            className="px-3.5 py-1.5 rounded-lg bg-primary hover:bg-primary-container text-on-primary font-bold text-xs flex items-center gap-1.5 transition-all shadow-md shadow-primary/20 disabled:opacity-60"
          >
            {isRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-current" />}
            {isRunning ? 'Running...' : selectedLang === 'html' ? 'Render HTML' : 'Run Code'}
          </button>

          {onSubmit && (
            <button
              onClick={() => onSubmit(code)}
              className="px-3.5 py-1.5 rounded-lg bg-secondary hover:bg-secondary-container text-on-secondary font-bold text-xs flex items-center gap-1.5 transition-all shadow-md shadow-secondary/20"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              Submit Solution
            </button>
          )}
        </div>
      </div>

      {/* Editor body / Task specs */}
      <div className="flex-1 min-h-0 relative overflow-hidden">
        {editorTab === 'code' ? (
          <Editor
            height="100%"
            language={MONACO_LANG[selectedLang] || 'c'}
            theme={isDark ? 'trace-dark' : 'trace-soft'}
            value={code}
            onChange={handleEditorChange}
            beforeMount={handleEditorBeforeMount}
            onMount={handleEditorMount}
            loading={
              <div className="h-full flex items-center justify-center bg-surface-container font-mono text-xs text-primary font-bold animate-pulse">
                Loading Code Editor...
              </div>
            }
            options={{
              readOnly,
              fontSize: 13,
              fontFamily: "'JetBrains Mono', monospace",
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
              lineNumbers: 'on',
              padding: { top: 10, bottom: 10 },
              renderLineHighlight: 'all',
              glyphMargin: true,
              'semanticHighlighting.enabled': true,
            }}
          />
        ) : (
          <div className="h-full overflow-y-auto p-5 bg-surface-container-lowest space-y-4">
            {activeProblem && (
              <>
                <div className="flex items-center justify-between border-b border-outline-variant/30 pb-3">
                  <div>
                    <span className="text-xs font-mono text-primary font-bold">{activeProblem.chapter}</span>
                    <h2 className="text-base font-extrabold text-on-surface">{activeProblem.title}</h2>
                  </div>
                  <span className="px-2.5 py-1 rounded bg-primary/10 text-primary font-mono text-xs font-bold border border-primary/30">{activeProblem.difficulty}</span>
                </div>
                <div className="text-xs text-on-surface leading-relaxed p-4 rounded-xl bg-surface-container border border-outline-variant/20 font-medium">
                  {langPreference === 'bn' ? activeProblem.description_bn : activeProblem.description_en}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
                  <div className="bg-surface-container p-3 rounded-xl border border-outline-variant/30">
                    <span className="text-primary font-bold block mb-1">Input Format:</span>
                    <p className="text-on-surface-variant">{activeProblem.input_format}</p>
                  </div>
                  <div className="bg-surface-container p-3 rounded-xl border border-outline-variant/30">
                    <span className="text-primary font-bold block mb-1">Output Format:</span>
                    <p className="text-on-surface-variant">{activeProblem.output_format}</p>
                  </div>
                </div>
                {activeProblem.html_checks?.length > 0 ? (
                  <div className="space-y-2">
                    <span className="text-xs font-mono font-bold text-on-surface uppercase block">Requirements (checked automatically on Render):</span>
                    <div className="space-y-1.5">
                      {activeProblem.html_checks.map((chk, idx) => (
                        <div key={idx} className="bg-surface-container p-2.5 rounded-xl border border-outline-variant/30 text-xs flex items-start gap-2">
                          <CheckCircle2 className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
                          <span className="text-on-surface font-medium">{chk.name}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <span className="text-xs font-mono font-bold text-on-surface uppercase block">Sample Test Cases:</span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {activeProblem.sample_cases?.map((sc, idx) => (
                        <div key={idx} className="bg-surface-container p-3 rounded-xl border border-outline-variant/30 font-mono text-xs space-y-1">
                          <div className="flex justify-between"><span className="text-on-surface-variant">Input:</span><span className="text-primary font-bold">{sc.input}</span></div>
                          <div className="flex justify-between"><span className="text-on-surface-variant">Output:</span><span className="text-emerald-400 font-bold">{sc.output}</span></div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* Resizable terminal drawer */}
      <div
        style={{ height: `${terminalHeight}px` }}
        className={`border-t border-outline-variant/40 bg-surface-container-high flex flex-col shrink-0 relative shadow-2xl overflow-hidden ${isResizing ? '' : 'transition-[height] duration-150'}`}
      >
        <div
          onMouseDown={handleMouseDown}
          className={`h-4 w-full cursor-ns-resize flex items-center justify-center transition-colors group shrink-0 select-none ${
            isResizing ? 'bg-primary/40 border-y border-primary/60' : 'bg-surface-container hover:bg-primary/30 border-y border-outline-variant/30'
          }`}
          title="Drag to resize console"
        >
          <div className={`h-1 w-12 rounded-full transition-colors ${isResizing ? 'bg-primary' : 'bg-on-surface-variant/40 group-hover:bg-primary'}`} />
        </div>

        <div className="px-3 py-1 bg-surface-container border-b border-outline-variant/30 flex items-center justify-between shrink-0 text-xs font-mono select-none">
          <div className="flex items-center gap-1.5">
            {tabButton(
              'problems',
              <Bug className="w-3.5 h-3.5" />,
              'Problems',
              diagnostics.length > 0 && (
                <span className={`px-1.5 rounded-full text-[10px] font-extrabold ${errorCount ? 'bg-rose-500 text-white' : 'bg-amber-500 text-black'}`}>{diagnostics.length}</span>
              )
            )}
            {selectedLang === 'html' && tabButton('preview', <Code2 className="w-3.5 h-3.5" />, 'Web Preview')}
            {tabButton('testcases', <CheckCircle2 className="w-3.5 h-3.5" />, 'Test Cases')}
            {tabButton('stdout', <Terminal className="w-3.5 h-3.5" />, selectedLang === 'html' ? 'HTML Output' : 'Compiler Output')}
          </div>

          <div className="flex items-center gap-1.5">
            {consoleOutput?.compiler && <span className="text-[10px] text-on-surface-variant font-medium mr-2 hidden sm:inline">{consoleOutput.compiler}</span>}
            {consoleOutput && (
              <button onClick={() => setConsoleOutput(null)} className="p-1 rounded hover:bg-surface-container-high text-on-surface-variant hover:text-primary transition-colors" title="Clear Terminal">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
            <button onClick={() => setTerminalHeight(38)} className={`p-1 rounded hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface transition-colors ${terminalHeight === 38 ? 'text-primary font-bold' : ''}`} title="Minimize Console">
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
            <button onClick={() => setTerminalHeight(220)} className={`p-1 rounded hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface transition-colors ${terminalHeight === 220 ? 'text-primary font-bold' : ''}`} title="Default Height">
              <ChevronUp className="w-3.5 h-3.5" />
            </button>
            <button onClick={() => setTerminalHeight(terminalHeight === 380 ? 220 : 380)} className={`p-1 rounded hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface transition-colors ${terminalHeight === 380 ? 'text-primary font-bold' : ''}`} title="Maximize Console">
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="flex-1 min-h-0 p-3 overflow-y-auto font-mono text-xs space-y-2 select-text">
          {/* PROBLEMS tab: live diagnostics like VS Code (the run log takes over while compiling) */}
          {activeTab === 'problems' && consoleOutput?.status !== 'RUNNING' && (
            <div className="space-y-1.5">
              {compilerInfo && !compilerInfo.ready && selectedLang !== 'html' && (
                <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-500 flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>{compilerInfo.hint || 'Compiler unavailable.'}</span>
                </div>
              )}
              {diagnostics.length === 0 && (
                <div className={`py-2 italic font-medium select-none ${checkState === 'clean' ? 'text-emerald-500' : 'text-on-surface-variant'}`}>
                  {checkState === 'checking' ? 'Analyzing your code...' : checkState === 'clean' ? `No problems detected in ${fileName}.` : checkState === 'offline' ? 'Live diagnostics unavailable - backend compiler is not reachable.' : 'Problems detected by the compiler will appear here as you type.'}
                </div>
              )}
              {diagnostics.map((d, i) => (
                <button
                  key={i}
                  onClick={() => jumpTo(d)}
                  className={`w-full text-left p-2 rounded-lg border flex items-start gap-2 hover:bg-surface-container transition-colors ${
                    d.severity === 'error' ? 'border-rose-500/30 bg-rose-500/5' : d.severity === 'warning' ? 'border-amber-500/30 bg-amber-500/5' : 'border-outline-variant/30'
                  }`}
                >
                  {d.severity === 'error' ? <AlertCircle className="w-3.5 h-3.5 text-rose-500 shrink-0 mt-0.5" /> : d.severity === 'warning' ? <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" /> : <Info className="w-3.5 h-3.5 text-sky-400 shrink-0 mt-0.5" />}
                  <span className="min-w-0">
                    <span className="text-on-surface font-semibold">{d.message}</span>
                    <span className="text-on-surface-variant ml-2 text-[10px]">{fileName} [Ln {d.line}, Col {d.column}]</span>
                  </span>
                </button>
              ))}
            </div>
          )}

          {activeTab !== 'problems' && !consoleOutput && (
            <div className="text-on-surface-variant py-2 italic font-medium select-none">
              {selectedLang === 'html'
                ? "Click 'Render HTML' to validate the markup, check the task requirements and preview the page."
                : "Click 'Run Code' to compile and run the sample test cases."}
            </div>
          )}

          {consoleOutput?.status === 'RUNNING' && (
            <div className="py-1 space-y-0.5 select-none font-mono text-[11px]">
              {runLog.map((line, i) => (
                <div key={i} className={`animate-fade-in ${line.startsWith('$') ? 'text-primary font-bold' : 'text-on-surface-variant'}`}>
                  <span className={i === runLog.length - 1 ? 'caret' : ''}>{line}</span>
                </div>
              ))}
              {runLog.length === 0 && <div className="text-primary font-bold"><span className="caret" /></div>}
            </div>
          )}

          {activeTab === 'preview' && consoleOutput && consoleOutput.status !== 'RUNNING' && (
            <div className="bg-white rounded-xl overflow-hidden border border-outline-variant/40 shadow-inner h-full min-h-[140px]">
              <iframe title="HTML Preview Sandbox" sandbox="" srcDoc={consoleOutput.htmlContent || code} className="w-full h-full min-h-[140px] border-none bg-white text-black" />
            </div>
          )}

          {activeTab === 'testcases' && consoleOutput && consoleOutput.status !== 'RUNNING' && (
            <div className="space-y-2">
              {consoleOutput.status === 'COMPILE_ERROR' && (
                <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 font-bold flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  {selectedLang === 'html' ? 'The HTML has syntax errors - see the Problems tab. Requirement checks below ran on the browser-repaired document.' : 'Compilation failed - fix the errors in the Problems tab first.'}
                </div>
              )}
              {consoleOutput.status === 'ERROR' && <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 font-bold">{consoleOutput.stderr}</div>}
              {consoleOutput.testResults?.length > 0 && (
                <div className="text-[11px] font-bold text-on-surface-variant">
                  {consoleOutput.passed_count ?? consoleOutput.testResults.filter((t) => t.passed).length}/{consoleOutput.testResults.length} {selectedLang === 'html' ? 'requirement checks' : 'test cases'} passed
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {(consoleOutput.testResults || []).map((tr) => (
                  <div key={tr.id} className={`bg-surface-container p-2.5 rounded-xl border shadow-sm space-y-1 ${tr.passed ? 'border-emerald-500/30' : 'border-rose-500/40 bg-rose-500/5'}`}>
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-on-surface truncate">{tr.name || `Test Case ${tr.id} (Input: ${tr.input || '-'})`}</span>
                      <span className={`px-2 py-0.5 rounded font-extrabold text-[10px] shrink-0 border ${tr.passed ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border-rose-500/40'}`}>
                        {tr.passed ? 'PASSED' : tr.timed_out ? 'TIMEOUT' : tr.exit_code && tr.exit_code !== 0 ? 'RUNTIME ERROR' : 'FAILED'}
                      </span>
                    </div>
                    <div className="text-[10px] text-on-surface-variant">Expected: <strong className="text-emerald-400">{tr.expected || '(any)'}</strong></div>
                    <div className="text-[10px] text-on-surface-variant">Actual: <strong className={tr.passed ? 'text-on-surface' : 'text-rose-400'}>{tr.actual || '(no output)'}</strong></div>
                    {tr.stderr && <pre className="text-[10px] text-rose-400 whitespace-pre-wrap">{tr.stderr}</pre>}
                    {typeof tr.time_ms === 'number' && <div className="text-[10px] text-on-surface-variant">{tr.time_ms} ms</div>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'stdout' && consoleOutput && consoleOutput.status !== 'RUNNING' && (
            <div className="bg-surface-container p-3 rounded-xl border border-outline-variant/30 text-xs space-y-2">
              {consoleOutput.status === 'ERROR' && <pre className="text-rose-400 font-semibold whitespace-pre-wrap">{consoleOutput.stderr}</pre>}
              {consoleOutput.compile_output && (
                <pre className={`whitespace-pre-wrap leading-relaxed ${consoleOutput.status === 'COMPILE_ERROR' ? 'text-rose-400' : 'text-amber-500'}`}>{consoleOutput.compile_output}</pre>
              )}
              {consoleOutput.status !== 'COMPILE_ERROR' && consoleOutput.status !== 'ERROR' && selectedLang !== 'html' && (
                <pre className="text-on-surface font-semibold whitespace-pre-wrap leading-relaxed">
                  {consoleOutput.compiler ? `[${consoleOutput.compiler}] compilation successful.\n` : ''}
                  {(consoleOutput.testResults || []).map((tr) => `\n$ input: ${tr.input || '(none)'}\n${tr.actual || ''}${tr.stderr ? `\n${tr.stderr}` : ''}\n[exit code ${tr.exit_code ?? 0}]`).join('\n')}
                </pre>
              )}
              {selectedLang === 'html' && consoleOutput.testResults?.length > 0 && (
                <pre className="text-on-surface font-semibold whitespace-pre-wrap leading-relaxed">
                  {(consoleOutput.testResults || []).map((tr) => `[${tr.passed ? 'PASS' : 'FAIL'}] ${tr.name || tr.input}: ${tr.actual}`).join('\n')}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
