"""HTML diagnostics for the student editor.

Three layers, all reported with line/column so the editor can show squiggles:
1. html5lib parse errors (real HTML5 tokenizer/tree-builder), mapped to student-friendly messages
2. vocabulary lint: unknown tag names and unknown attributes, with "did you mean" suggestions
3. task requirement checks (CSS selectors evaluated on the parsed document) - the HTML equivalent of test cases
"""
import difflib
import re

import html5lib
from html5lib.constants import E as HTML5LIB_MESSAGES

HTML_TAGS = set('''
a abbr acronym address applet area article aside audio b base basefont bdi bdo big blink blockquote body br button
canvas caption center cite code col colgroup data datalist dd del details dfn dialog dir div dl dt em embed fieldset
figcaption figure font footer form frame frameset h1 h2 h3 h4 h5 h6 head header hgroup hr html i iframe img input ins
kbd keygen label legend li link listing main map mark marquee menu menuitem meta meter nav nobr noembed noframes
noscript object ol optgroup option output p param picture plaintext pre progress q rb rp rt rtc ruby s samp script
search section select slot small source spacer span strike strong style sub summary sup table tbody td template
textarea tfoot th thead time title tr track tt u ul var video wbr xmp
'''.split())

SVG_MATHML_TAGS = set('''
svg path circle rect line polyline polygon ellipse g defs use symbol text tspan textpath lineargradient radialgradient
stop clippath mask pattern filter foreignobject image marker animate animatetransform animatemotion set desc metadata
switch view feblend fecolormatrix fecomponenttransfer fecomposite feconvolvematrix fediffuselighting fedisplacementmap
fedropshadow feflood fegaussianblur feimage femerge femergenode femorphology feoffset fespecularlighting fetile
feturbulence math mi mo mn ms mtext mrow mfrac msup msub msubsup msqrt mroot mtable mtr mtd mover munder munderover
annotation semantics
'''.split())

KNOWN_TAGS = HTML_TAGS | SVG_MATHML_TAGS

VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr', 'basefont', 'frame', 'keygen'}
OPTIONAL_END_TAGS = {'html', 'head', 'body', 'p', 'li', 'dt', 'dd', 'option', 'optgroup', 'tbody', 'thead', 'tfoot', 'tr', 'td', 'th', 'colgroup', 'caption', 'rt', 'rp'}

GLOBAL_ATTRS = set('''
id class style title lang dir hidden tabindex accesskey contenteditable draggable spellcheck translate role slot is
part exportparts itemprop itemscope itemtype itemid itemref autocapitalize enterkeyhint inputmode nonce popover inert
autofocus writingsuggestions virtualkeyboardpolicy anchor align bgcolor background xmlns
'''.split())

_TABLE_CELL = 'colspan rowspan headers scope abbr axis align valign bgcolor background bordercolor width height nowrap char charoff'
TAG_ATTRS = {k: set(v.split()) for k, v in {
    'a': 'href target download rel hreflang type referrerpolicy ping charset coords shape rev name media',
    'img': 'src alt width height srcset sizes loading decoding usemap ismap crossorigin referrerpolicy border hspace vspace longdesc fetchpriority elementtiming name lowsrc',
    'table': 'border cellpadding cellspacing width height bgcolor background bordercolor bordercolorlight bordercolordark frame rules summary align cols',
    'td': _TABLE_CELL, 'th': _TABLE_CELL,
    'tr': 'align valign bgcolor char charoff height bordercolor',
    'col': 'span align valign width char charoff', 'colgroup': 'span align valign width char charoff',
    'thead': 'align valign char charoff', 'tbody': 'align valign char charoff', 'tfoot': 'align valign char charoff',
    'caption': 'align',
    'ol': 'type start reversed compact', 'ul': 'type compact', 'li': 'value type', 'dl': 'compact', 'menu': 'type label compact',
    'font': 'face size color', 'basefont': 'face size color',
    'body': 'text link vlink alink bgcolor background topmargin leftmargin rightmargin bottommargin marginwidth marginheight onload onunload',
    'html': 'lang manifest xmlns version', 'head': 'profile',
    'meta': 'charset name content http-equiv scheme property media',
    'link': 'href rel type media sizes as crossorigin hreflang integrity referrerpolicy disabled imagesizes imagesrcset blocking fetchpriority',
    'script': 'src type async defer charset crossorigin integrity nomodule referrerpolicy language blocking fetchpriority',
    'style': 'type media blocking', 'base': 'href target',
    'form': 'action method enctype target name autocomplete novalidate accept-charset rel',
    'input': 'type name value placeholder required disabled readonly checked min max step maxlength minlength size pattern list multiple accept autocomplete alt src width height form formaction formmethod formenctype formtarget formnovalidate dirname capture popovertarget popovertargetaction',
    'button': 'type name value disabled form formaction formmethod formenctype formtarget formnovalidate popovertarget popovertargetaction',
    'select': 'name multiple size required disabled form autocomplete',
    'option': 'value selected disabled label', 'optgroup': 'label disabled',
    'textarea': 'name rows cols placeholder required disabled readonly maxlength minlength wrap form autocomplete dirname',
    'label': 'for form', 'fieldset': 'disabled form name', 'legend': 'align', 'output': 'for form name',
    'iframe': 'src srcdoc name width height sandbox allow allowfullscreen loading referrerpolicy frameborder scrolling marginwidth marginheight align longdesc',
    'video': 'src controls autoplay loop muted poster preload width height playsinline crossorigin controlslist disablepictureinpicture',
    'audio': 'src controls autoplay loop muted preload crossorigin controlslist',
    'source': 'src type srcset sizes media width height', 'track': 'src kind srclang label default',
    'embed': 'src type width height', 'object': 'data type width height name form usemap classid codebase archive standby align',
    'param': 'name value valuetype type', 'area': 'shape coords href alt target download rel ping referrerpolicy nohref', 'map': 'name',
    'canvas': 'width height', 'hr': 'align noshade size width color', 'br': 'clear', 'pre': 'width',
    'p': 'align', 'div': 'align', 'h1': 'align', 'h2': 'align', 'h3': 'align', 'h4': 'align', 'h5': 'align', 'h6': 'align',
    'blockquote': 'cite', 'q': 'cite', 'ins': 'cite datetime', 'del': 'cite datetime', 'time': 'datetime', 'data': 'value',
    'meter': 'value min max low high optimum form', 'progress': 'value max', 'details': 'open name', 'dialog': 'open',
    'marquee': 'behavior direction loop scrollamount scrolldelay bgcolor width height hspace vspace truespeed',
    'frameset': 'rows cols border frameborder framespacing',
    'frame': 'src name scrolling noresize frameborder marginwidth marginheight longdesc',
    'applet': 'code codebase archive object width height alt name hspace vspace',
    'abbr': '', 'acronym': '', 'bdo': '', 'center': '', 'span': '', 'title': '', 'main': '', 'section': '', 'nav': '', 'article': '', 'aside': '',
}.items()}

# html5lib error code -> (severity, student-friendly message). {placeholders} are filled from the error's datavars.
_DOCTYPE_MISSING = ('warning', 'Missing <!DOCTYPE html> declaration at the top of the document.')
_DOCTYPE_BAD = ('error', 'Malformed DOCTYPE - write exactly <!DOCTYPE html>.')
_UNFINISHED_TAG = ('error', "A tag is left unfinished at the end of the document - missing '>' or a closing quote.")
_NO_MATCHING_OPEN = ('error', 'Closing tag </{name}> has no matching open <{name}> - check the spelling, order and nesting of your tags.')
_AFTER_BODY = ('warning', 'Content after </body> - everything should be inside <body> ... </body>.')
_AFTER_HTML = ('warning', 'Content after </html> - nothing should come after the closing </html> tag.')
_ENTITY = ('warning', "Use &amp; for a literal '&', or finish the entity with ';' (e.g. &lt; &gt; &nbsp;).")
_TOO_EARLY = ('error', '</{name}> was found while an inner tag is still open - close the inner tag first (e.g. </b>, </a>, </i>).')

FRIENDLY = {
    'expected-doctype-but-got-start-tag': _DOCTYPE_MISSING,
    'expected-doctype-but-got-chars': _DOCTYPE_MISSING,
    'expected-doctype-but-got-end-tag': _DOCTYPE_MISSING,
    'expected-doctype-but-got-eof': ('warning', 'The document is empty.'),
    'unknown-doctype': _DOCTYPE_BAD, 'expected-dashes-or-doctype': _DOCTYPE_BAD, 'need-space-after-doctype': _DOCTYPE_BAD,
    'expected-doctype-name-but-got-right-bracket': _DOCTYPE_BAD, 'expected-doctype-name-but-got-eof': _DOCTYPE_BAD,
    'expected-space-or-right-bracket-in-doctype': _DOCTYPE_BAD, 'unexpected-char-in-doctype': _DOCTYPE_BAD,
    'eof-in-doctype': _DOCTYPE_BAD, 'eof-in-doctype-name': _DOCTYPE_BAD, 'unexpected-end-of-doctype': _DOCTYPE_BAD,
    'unexpected-doctype': ('warning', 'DOCTYPE must be the very first line of the document.'),
    'non-html-root': ('error', 'The first tag of the document must be <html>.'),

    'unexpected-end-tag': _NO_MATCHING_OPEN,
    'unexpected-end-tag-before-html': _NO_MATCHING_OPEN, 'end-tag-after-implied-root': _NO_MATCHING_OPEN,
    'unexpected-end-tag-in-table-body': ('error', 'Closing tag </{name}> has no matching open <{name}> in this part of the table.'),
    'unexpected-end-tag-in-table-row': ('error', 'Closing tag </{name}> has no matching open <{name}> in this table row.'),
    'unexpected-end-tag-in-select': _NO_MATCHING_OPEN, 'adoption-agency-1.2': _NO_MATCHING_OPEN,
    'adoption-agency-1.3': ('error', 'Overlapping tags: </{name}> closes a tag that is not the most recently opened one. Close tags in reverse order, e.g. <b><i>text</i></b>.'),
    'adoption-agency-4.4': ('error', 'Overlapping tags around </{name}> - close tags in reverse order, e.g. <b><i>text</i></b>.'),
    'adoption-agency-1.1': _NO_MATCHING_OPEN,
    'end-tag-too-early': _TOO_EARLY, 'end-tag-too-early-ignored': _TOO_EARLY,
    'end-tag-too-early-named': ('error', 'Found </{gotName}> but </{expectedName}> is missing before it.'),
    'expected-one-end-tag-but-got-another': ('error', 'Found </{gotName}> but </{expectedName}> is missing before it.'),
    'unexpected-cell-end-tag': ('error', '</{name}> closes the cell while a tag inside it is still open - close the inner tag first.'),
    'expected-named-closing-tag-but-got-eof': ('error', 'Missing closing tag </{name}>.'),
    'missing-end-tag': ('error', 'Missing closing tag </{name}>.'), 'missing-end-tags': ('error', 'Missing closing tags: {name}.'),
    'no-end-tag': ('error', '<{name}> has no closing tag.'),
    'expected-closing-tag-but-got-eof': None,  # replaced by the open-element scan below
    'eof-in-table': None,

    'eof-in-tag-name': _UNFINISHED_TAG, 'eof-in-attribute-name': _UNFINISHED_TAG,
    'eof-in-attribute-value-double-quote': ('error', 'A double-quoted attribute value is never closed - add the missing \" and \'>\'.'),
    'eof-in-attribute-value-single-quote': ('error', "A single-quoted attribute value is never closed - add the missing ' and '>'."),
    'eof-in-attribute-value-no-quotes': _UNFINISHED_TAG, 'expected-attribute-name-but-got-eof': _UNFINISHED_TAG,
    'expected-attribute-value-but-got-eof': _UNFINISHED_TAG, 'expected-end-of-tag-name-but-got-eof': _UNFINISHED_TAG,
    'unexpected-EOF-after-solidus-in-tag': _UNFINISHED_TAG,
    'eof-in-comment': ('error', "A comment is never closed - add '-->'."), 'eof-in-comment-double-dash': ('error', "A comment is never closed - add '-->'."),
    'eof-in-comment-end-dash': ('error', "A comment is never closed - add '-->'."), 'eof-in-comment-end-bang-state': ('error', "A comment is never closed - add '-->'."),
    'eof-in-comment-end-space-state': ('error', "A comment is never closed - add '-->'."),
    'expected-tag-name-but-got-right-bracket': ('error', "Empty tag '<>' - write the tag name after '<'."),
    'expected-tag-name': ('error', "'<' must be followed by a tag name (write &lt; if you mean a literal '<')."),
    'expected-tag-name-but-got-question-mark': ('error', "'<?' is not valid in HTML."),
    'expected-closing-tag-but-got-right-bracket': ('error', "'</>' has no tag name."),
    'expected-closing-tag-but-got-char': ('error', "'</' must be followed by a tag name."),
    'expected-attribute-value-but-got-right-bracket': ('error', "An attribute has '=' but no value - write attribute=\"value\"."),
    'unexpected-character-after-attribute-value': ('error', 'Missing space between two attributes - put a space after the closing quote.'),
    'unexpected-character-in-unquoted-attribute-value': ('warning', 'Attribute value contains special characters - wrap it in double quotes.'),
    'equals-in-unquoted-attribute-value': ('warning', 'Attribute value contains "=" - wrap it in double quotes.'),
    'invalid-character-in-attribute-name': ('error', "Invalid character in an attribute name - check quotes and '=' signs."),
    'invalid-character-after-attribute-name': ('error', "Invalid character after an attribute name - expected '=' or a space."),
    'duplicate-attribute': ('warning', 'The same attribute is written twice in one tag - only the first one is used.'),
    'attributes-in-end-tag': ('error', 'Closing tags cannot have attributes - write just </tag>.'),
    'self-closing-flag-on-end-tag': ('error', "A closing tag cannot end with '/>'."),
    'non-void-element-with-trailing-solidus': ('warning', "'/>' does not close <{name}> - it needs a separate </{name}> closing tag."),
    'incorrectly-placed-solidus': ('error', "Misplaced '/' inside a tag."), 'unexpected-character-after-solidus-in-tag': ('error', "Misplaced '/' inside a tag - expected '>'."),

    'unexpected-start-tag-implies-end-tag': ('error', '<{startName}> cannot be placed inside an open <{endName}> - close </{endName}> first.'),
    'unexpected-start-tag': ('warning', 'Unexpected <{name}> tag here - a document must contain only one <{name}>.'),
    'two-heads-are-not-better-than-one': ('warning', 'Duplicate <head> tag - a document has only one <head>.'),
    'unexpected-start-tag-ignored': ('error', '<{name}> is not allowed here - it must be inside its correct parent (e.g. <tr> inside <table>, <td> inside <tr>).'),
    'unexpected-start-tag-out-of-my-head': ('warning', '<{name}> belongs inside <head> ... </head>.'),
    'unexpected-start-tag-after-body': _AFTER_BODY, 'unexpected-char-after-body': _AFTER_BODY, 'unexpected-end-tag-after-body': _AFTER_BODY,
    'expected-eof-but-got-start-tag': _AFTER_HTML, 'expected-eof-but-got-char': _AFTER_HTML, 'expected-eof-but-got-end-tag': _AFTER_HTML,
    'unexpected-start-tag-implies-table-voodoo': ('error', '<{name}> is placed directly inside <table> - it must be inside a <td>/<th> cell (or the table must be closed first).'),
    'unexpected-char-implies-table-voodoo': ('error', 'Text directly inside <table> is not allowed - put it inside a <td>/<th> cell or a <caption>.'),
    'unexpected-end-tag-implies-table-voodoo': ('error', '</{name}> appeared while a <table> is still open - add </table> before it.'),
    'unexpected-cell-in-table-body': ('warning', '<{name}> should be inside a <tr> row.'),
    'unexpected-implied-end-tag-in-table': ('warning', '</table> closed the table while a row or cell was still open.'),
    'unexpected-implied-end-tag-in-table-body': ('warning', 'A row or cell was left open before this table tag.'),
    'unexpected-implied-end-tag-in-table-row': ('warning', 'A cell was left open before this table row tag.'),
    'unexpected-form-in-table': ('warning', '<form> directly inside <table> is not allowed.'),
    'unexpected-hidden-input-in-table': ('warning', 'Hidden <input> directly inside <table>.'),
    'unexpected-end-tag-treated-as': ('warning', '</{originalName}> is treated as </{newName}>.'),
    'unexpected-start-tag-treated-as': ('warning', '<{originalName}> is not a real HTML tag - the browser treats it as <{newName}>.'),
    'deprecated-tag': ('warning', '<{name}> is obsolete.'),
    'named-entity-without-semicolon': _ENTITY, 'expected-named-entity': _ENTITY, 'numeric-entity-without-semicolon': _ENTITY,
    'expected-numeric-entity': _ENTITY, 'expected-numeric-entity-but-got-eof': _ENTITY,
}

# When a container tag is misspelled (e.g. <tabel>), html5lib also rejects every child tag; hide that cascade.
CASCADE_CHILDREN = {
    'table': {'caption', 'colgroup', 'col', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th'},
    'thead': {'tr', 'td', 'th'}, 'tbody': {'tr', 'td', 'th'}, 'tfoot': {'tr', 'td', 'th'}, 'tr': {'td', 'th'},
    'ol': {'li'}, 'ul': {'li'}, 'dl': {'dt', 'dd'}, 'select': {'option', 'optgroup'}, 'optgroup': {'option'},
}
CASCADE_CODES = {
    'unexpected-start-tag-ignored', 'unexpected-end-tag', 'unexpected-end-tag-in-table-body', 'unexpected-end-tag-in-table-row',
    'unexpected-cell-in-table-body', 'unexpected-start-tag-implies-table-voodoo', 'unexpected-end-tag-implies-table-voodoo',
}
EOF_IN_TAG_CODES = {
    'eof-in-tag-name', 'eof-in-attribute-name', 'eof-in-attribute-value-double-quote', 'eof-in-attribute-value-single-quote',
    'eof-in-attribute-value-no-quotes', 'expected-attribute-name-but-got-eof', 'expected-attribute-value-but-got-eof',
    'expected-end-of-tag-name-but-got-eof', 'unexpected-EOF-after-solidus-in-tag',
}

_TAG_RE = re.compile(r'<(/?)([A-Za-z][A-Za-z0-9-]*)')
_ATTR_RE = re.compile(r'''([^\s"'<>/=]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'=<>`]+))?''')
_COMMENT_RE = re.compile(r'<!--.*?(?:-->|$)', re.S)
_RAWTEXT_RE = re.compile(r'(<(script|style|textarea)\b[^>]*>)(.*?)(</\2\s*>)', re.S | re.I)


def _line_col(text, pos):
    line = text.count('\n', 0, pos) + 1
    col = pos - (text.rfind('\n', 0, pos) + 1) + 1
    return line, col


def _blank_out(text):
    """Replace comments and script/style/textarea bodies with spaces, keeping newlines so positions stay valid."""
    def keep_newlines(m):
        return re.sub(r'[^\n]', ' ', m.group(0))
    text = _COMMENT_RE.sub(keep_newlines, text)
    text = _RAWTEXT_RE.sub(lambda m: m.group(1) + re.sub(r'[^\n]', ' ', m.group(3)) + m.group(4), text)
    return text


def _fmt(template, datavars):
    try:
        return template.format(**{k: str(v) for k, v in (datavars or {}).items()})
    except (KeyError, IndexError):
        return template


def _diag(line, column, severity, message):
    return {'line': max(1, int(line or 1)), 'column': max(1, int(column or 1)), 'severity': severity, 'message': message}


def _parse_errors(code, missing_names, lint_info):
    parser = html5lib.HTMLParser(strict=False, namespaceHTMLElements=False)
    parser.parse(code)
    suppressed_children = set()
    for suggestion in lint_info['suggestions']:
        suppressed_children |= CASCADE_CHILDREN.get(suggestion, set())
    diags = []
    for (line, col), errcode, datavars in parser.errors:
        datavars = datavars or {}
        name = str(datavars.get('name', '')).lower()
        if errcode in FRIENDLY and FRIENDLY[errcode] is None:
            continue
        if errcode in CASCADE_CODES and name in suppressed_children:
            continue
        if errcode in EOF_IN_TAG_CODES and lint_info['unfinished_tag']:
            continue
        if errcode in ('unexpected-end-tag-in-table-body', 'unexpected-end-tag-in-table-row') and name in ('body', 'html'):
            severity, message = 'error', f'</{name}> appeared while a <table> is still open - add </table> before it.'
        elif errcode in FRIENDLY:
            severity, template = FRIENDLY[errcode]
            message = _fmt(template, datavars)
        else:
            raw = HTML5LIB_MESSAGES.get(errcode, errcode)
            try:
                message = raw % datavars
            except (KeyError, TypeError, ValueError):
                message = raw
            severity = 'error'
        if errcode in ('expected-one-end-tag-but-got-another', 'end-tag-too-early-named'):
            missing_names.add(str(datavars.get('expectedName', '')).lower())
        elif errcode in ('expected-named-closing-tag-but-got-eof', 'missing-end-tag', 'no-end-tag'):
            missing_names.add(str(datavars.get('name', '')).lower())
        diags.append(_diag(line, (col or 0) + 1, severity, message))

    # Elements still open when the document ended (html5lib leaves them on the stack).
    open_names = [n.name.lower() for n in parser.tree.openElements]
    for name in reversed(open_names):
        if name in OPTIONAL_END_TAGS or name in VOID_TAGS or name in missing_names:
            continue
        missing_names.add(name)
        pos = _guess_open_position(code, name)
        diags.append(_diag(pos[0], pos[1], 'error', f'Missing closing tag </{name}> - <{name}> is opened but never closed.'))
    return diags


def _guess_open_position(code, name):
    scan = _blank_out(code)
    starts = [m.start() for m in re.finditer(r'<' + re.escape(name) + r'(?=[\s>/])', scan, re.I)]
    if not starts:
        return (1, 1)
    ends = len(re.findall(r'</' + re.escape(name) + r'\s*>', scan, re.I))
    idx = min(ends, len(starts) - 1)
    return _line_col(code, starts[idx])


def _attr_span_end(scan, start):
    """(index, reason) where the tag starting at `start` ends; reason: 'close' | 'lt' | 'eof' | 'eof_in_quote'."""
    quote = None
    i = start
    while i < len(scan):
        ch = scan[i]
        if quote:
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch == '>':
            return i, 'close'
        elif ch == '<':
            return i, 'lt'
        i += 1
    return len(scan), ('eof_in_quote' if quote else 'eof')


def _vocabulary_lint(code, lint_info):
    diags = []
    scan = _blank_out(code)
    for m in _TAG_RE.finditer(scan):
        closing, raw_name = m.group(1), m.group(2)
        name = raw_name.lower()
        line, col = _line_col(code, m.start())
        if name not in KNOWN_TAGS:
            if '-' in name:
                continue  # custom element
            suggestion = difflib.get_close_matches(name, sorted(HTML_TAGS), n=1, cutoff=0.6)
            hint = f' Did you mean <{suggestion[0]}>?' if suggestion else ''
            if suggestion:
                lint_info['suggestions'].add(suggestion[0])
            diags.append(_diag(line, col, 'error', f'Unknown tag <{"/" if closing else ""}{raw_name}> - this is not an HTML tag.{hint}'))
            continue
        if closing or name in SVG_MATHML_TAGS:
            continue
        body_start = m.end()
        body_end, reason = _attr_span_end(scan, body_start)
        if reason == 'eof_in_quote':
            lint_info['unfinished_tag'] = True
            diags.append(_diag(line, col, 'error', f'An attribute value in <{name}> is missing its closing quote, so the tag never ends.'))
            continue
        if reason == 'eof':
            lint_info['unfinished_tag'] = True
            diags.append(_diag(line, col, 'error', f"<{name}> is never closed with '>'."))
            continue
        if reason == 'lt':
            diags.append(_diag(line, col, 'error', f"<{name}> is missing its closing '>' before the next tag starts."))
            continue
        body = scan[body_start:body_end]
        allowed = GLOBAL_ATTRS | TAG_ATTRS.get(name, set())
        for am in _ATTR_RE.finditer(body):
            attr = am.group(1).lower().rstrip('/')
            if not attr or attr == '/':
                continue
            if attr in allowed or attr.startswith(('data-', 'aria-', 'on')) or ':' in attr:
                continue
            suggestion = difflib.get_close_matches(attr, sorted(allowed), n=1, cutoff=0.6)
            hint = f" Did you mean '{suggestion[0]}'?" if suggestion else ''
            aline, acol = _line_col(code, body_start + am.start(1))
            diags.append(_diag(aline, acol, 'warning', f"Unknown attribute '{am.group(1)}' on <{name}>.{hint}"))
    return diags


def _structure_lint(code):
    diags = []
    scan = _blank_out(code).lower()
    if not scan.strip():
        return diags
    if '<html' not in scan:
        diags.append(_diag(1, 1, 'warning', 'No <html> root element - wrap the document in <html> ... </html>.'))
    if '<body' not in scan:
        diags.append(_diag(1, 1, 'warning', 'No <body> element - page content belongs inside <body> ... </body>.'))
    if '<head' in scan and '<title' not in scan:
        diags.append(_diag(1, 1, 'warning', 'The <head> has no <title> - every page should have a title.'))
    return diags


def check_html(code):
    missing_names = set()
    lint_info = {'suggestions': set(), 'unfinished_tag': False}
    lint_diags = _vocabulary_lint(code, lint_info)
    diags = _parse_errors(code, missing_names, lint_info) + lint_diags + _structure_lint(code)
    seen, out = set(), []
    for d in sorted(diags, key=lambda d: (d['line'], d['column'], d['severity'] != 'error')):
        key = (d['line'], d['message'])
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out[:60]


def format_output(diagnostics):
    lines = [f"index.html:{d['line']}:{d['column']}: {d['severity']}: {d['message']}" for d in diagnostics]
    errors = sum(1 for d in diagnostics if d['severity'] == 'error')
    warnings = sum(1 for d in diagnostics if d['severity'] == 'warning')
    lines.append(f'{errors} error(s), {warnings} warning(s) generated.' if diagnostics else '[HTML5 validator] Document is well-formed. 0 errors, 0 warnings.')
    return '\n'.join(lines)


def run_checks(code, checks):
    """checks: [{name, selector, min=1, max=None, text_includes=[...]}] evaluated on the html5lib-parsed document."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(code, 'html5lib')
    results = []
    for idx, chk in enumerate(checks):
        selector = chk.get('selector', '')
        min_count = int(chk.get('min', 1))
        max_count = chk.get('max')
        name = chk.get('name') or f'Elements matching {selector}'
        expected = f'at least {min_count} element(s) matching "{selector}"' if max_count is None else f'{min_count}-{max_count} element(s) matching "{selector}"'
        try:
            matches = soup.select(selector)
        except Exception as e:
            results.append({'id': idx + 1, 'name': name, 'input': selector, 'expected': expected, 'actual': f'invalid selector: {e}', 'passed': False, 'exit_code': 1, 'timed_out': False, 'time_ms': 0})
            continue
        passed = len(matches) >= min_count and (max_count is None or len(matches) <= max_count)
        actual = f'found {len(matches)} element(s)'
        if passed and chk.get('text_includes'):
            text = ' '.join(m.get_text(' ', strip=True) for m in matches).lower()
            missing = [t for t in chk['text_includes'] if str(t).lower() not in text]
            if missing:
                passed = False
                actual += '; missing text: ' + ', '.join(f'"{t}"' for t in missing)
            else:
                actual += '; text OK'
        results.append({'id': idx + 1, 'name': name, 'input': selector, 'expected': expected, 'actual': actual, 'passed': passed, 'exit_code': 0, 'timed_out': False, 'time_ms': 0})
    return results
