// Renders the subset of Markdown the tutor's chat answer uses - paragraphs, bullet and
// numbered lists, **bold**, `inline code` and fenced code blocks - as React nodes. The
// model's text is never handed to the DOM as markup, so nothing it writes can inject.
const FENCE = /```[^\n]*\n([\s\S]*?)```/g;
const LIST_ITEM = /^\s*(?:([-*•])|(\d+)[.)])\s+(.*)$/;
const HEADING = /^\s*#{1,6}\s+(.*)$/;

function inline(text) {
  return text
    .split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
    .filter(Boolean)
    .map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-bold text-on-surface">{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('`') && part.endsWith('`')) {
        return (
          <code key={i} className="font-mono text-[11px] px-1 py-0.5 rounded bg-surface-container-high text-primary">
            {part.slice(1, -1)}
          </code>
        );
      }
      return part;
    });
}

function blocks(segment, prefix) {
  const out = [];
  let para = [];
  let list = null;

  const flushPara = () => {
    if (!para.length) return;
    out.push(<p key={`${prefix}p${out.length}`} className="leading-relaxed">{inline(para.join(' '))}</p>);
    para = [];
  };
  const flushList = () => {
    if (!list) return;
    const Tag = list.ordered ? 'ol' : 'ul';
    out.push(
      <Tag key={`${prefix}l${out.length}`} className={`${list.ordered ? 'list-decimal' : 'list-disc'} pl-5 space-y-1`}>
        {list.items.map((item, i) => <li key={i} className="leading-relaxed">{inline(item)}</li>)}
      </Tag>
    );
    list = null;
  };

  for (const line of segment.split('\n')) {
    const item = line.match(LIST_ITEM);
    if (item) {
      flushPara();
      const ordered = Boolean(item[2]);
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push(item[3]);
      continue;
    }
    if (!line.trim()) {
      flushPara();
      flushList();
      continue;
    }
    flushList();
    const heading = line.match(HEADING);
    if (heading) {
      flushPara();
      out.push(<p key={`${prefix}h${out.length}`} className="font-bold text-on-surface">{inline(heading[1])}</p>);
      continue;
    }
    para.push(line.trim());
  }
  flushPara();
  flushList();
  return out;
}

export const ChatMarkdown = ({ text, className = '' }) => {
  if (!text) return null;
  const nodes = [];
  let last = 0;
  let n = 0;
  for (const match of text.matchAll(FENCE)) {
    if (match.index > last) nodes.push(...blocks(text.slice(last, match.index), `t${n++}`));
    nodes.push(
      <pre
        key={`c${n++}`}
        className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap bg-slate-900 dark:bg-surface-container-lowest text-cyan-300 dark:text-primary p-3 rounded-lg border border-outline-variant/30 overflow-x-auto"
      >
        {match[1].replace(/\n$/, '')}
      </pre>
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(...blocks(text.slice(last), `t${n++}`));
  return <div className={`space-y-2 ${className}`}>{nodes}</div>;
};
