from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

OUT = Path('/work/TRACE-Tutor-Work-Log-2026-10-07.docx')
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
sec.top_margin = sec.bottom_margin = sec.left_margin = sec.right_margin = Inches(1)
sec.header_distance = sec.footer_distance = Inches(.492)

# compact_reference_guide; named overrides: Code (9pt Consolas/1.05),
# TableBody (9.5pt/1.1), Caption (9pt), Title (26pt), Footer (8pt).
def style(name, size, color='243447', before=0, after=6, line=1.25, bold=False, font='Calibri'):
    s = doc.styles[name] if name in doc.styles else doc.styles.add_style(name, 1)
    s.font.name = font
    s.font.size = Pt(size)
    s.font.color.rgb = RGBColor.from_string(color)
    s.font.bold = bold
    s.paragraph_format.space_before = Pt(before)
    s.paragraph_format.space_after = Pt(after)
    s.paragraph_format.line_spacing = line
    s.paragraph_format.widow_control = True
    return s

style('Normal', 11)
style('Title', 26, '0B2545', after=10, line=1.1, bold=True)
style('Subtitle', 12, '586779', after=8)
for name, size, color, before, after in [
    ('Heading 1',16,'2E74B5',18,10), ('Heading 2',13,'2E74B5',14,7),
    ('Heading 3',12,'1F4D78',10,5)]:
    s = style(name,size,color,before,after,bold=True)
    s.paragraph_format.keep_with_next = True
style('Code',9,'243447',after=3,line=1.05,font='Consolas')
style('Spacer',3,after=4,line=1)
style('TableBody',9.5,after=3,line=1.1)
style('Caption',9,'586779',before=4,after=4)
style('Header',8,'586779',after=0,line=1)
style('Footer',8,'586779',after=0,line=1)
for name in ['List Bullet','List Number']:
    s=style(name,11,after=4)
    s.paragraph_format.left_indent=Inches(.375)
    s.paragraph_format.first_line_indent=Inches(-.188)

numbering=doc.part.numbering_part.element
for abstract in numbering.findall(qn('w:abstractNum')):
    for lvl in abstract.findall(qn('w:lvl')):
        pp=lvl.find(qn('w:pPr'))
        if pp is None: pp=OxmlElement('w:pPr'); lvl.append(pp)
        ind=pp.find(qn('w:ind'))
        if ind is None: ind=OxmlElement('w:ind'); pp.append(ind)
        ind.set(qn('w:left'),'540'); ind.set(qn('w:hanging'),'270')
        tabs=pp.find(qn('w:tabs'))
        if tabs is None: tabs=OxmlElement('w:tabs'); pp.append(tabs)
        for child in list(tabs): tabs.remove(child)
        tab=OxmlElement('w:tab'); tab.set(qn('w:val'),'num'); tab.set(qn('w:pos'),'540'); tabs.append(tab)

hp=sec.header.paragraphs[0]
hp.style=doc.styles['Header']; hp.text='TRACE TUTOR  |  ENGINEERING WORK LOG'
fp=sec.footer.paragraphs[0]; fp.style=doc.styles['Footer']
fp.alignment=WD_ALIGN_PARAGRAPH.RIGHT
fp.add_run('07 October 2026  |  Page ')
fld=OxmlElement('w:fldSimple'); fld.set(qn('w:instr'),'PAGE'); fp._p.append(fld)
doc.core_properties.title='TRACE Tutor — Work Log and Learning Guide'
doc.core_properties.subject='Settings layout, Docker sandbox, deployment, and profile pictures'
doc.core_properties.author='TRACE Tutor'

def p(text, st=None): return doc.add_paragraph(text,style=st)
def h(text,level=1): return doc.add_heading(text,level)
def bullet(text): return p(text,'List Bullet')
def code(text):
    lines=text.strip('\n').split('\n')
    for i,line in enumerate(lines):
        para=p(line,'Code')
        para.paragraph_format.keep_with_next=i<len(lines)-1
        para.paragraph_format.keep_together=True
        shade=OxmlElement('w:shd'); shade.set(qn('w:fill'),'F2F4F7'); para._p.get_or_add_pPr().append(shade)
    p('', 'Spacer')
def page(title):
    h(title)
def table(heads,rows,widths):
    t=doc.add_table(rows=1,cols=len(heads)); t.autofit=False
    t.alignment=WD_TABLE_ALIGNMENT.LEFT
    pr=t._tbl.tblPr
    tw=pr.find(qn('w:tblW')); tw.set(qn('w:type'),'dxa'); tw.set(qn('w:w'),'9360')
    ind=OxmlElement('w:tblInd'); ind.set(qn('w:w'),'120'); ind.set(qn('w:type'),'dxa'); pr.append(ind)
    margins=OxmlElement('w:tblCellMar')
    for edge,value in [('top',80),('bottom',80),('start',120),('end',120)]:
        e=OxmlElement('w:'+edge); e.set(qn('w:w'),str(value)); e.set(qn('w:type'),'dxa'); margins.append(e)
    pr.append(margins)
    borders=OxmlElement('w:tblBorders')
    for edge in ['top','bottom','left','right','insideH','insideV']:
        e=OxmlElement('w:'+edge)
        for key,val in [('val','single'),('sz','4'),('color','D8DEE7')]: e.set(qn('w:'+key),val)
        borders.append(e)
    pr.append(borders)
    for child in list(t._tbl.tblGrid): t._tbl.tblGrid.remove(child)
    for width in widths:
        e=OxmlElement('w:gridCol');e.set(qn('w:w'),str(width));t._tbl.tblGrid.append(e)
    for cells,values,header in [(t.rows[0].cells,heads,True)]+[(t.add_row().cells,row,False) for row in rows]:
        for cell,text,width in zip(cells,values,widths):
            cell.width=Inches(width/1440)
            cell._tc.get_or_add_tcPr().find(qn('w:tcW')).set(qn('w:w'),str(width))
            cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            para=cell.paragraphs[0];para.style=doc.styles['TableBody'];run=para.add_run(text)
            if header:
                run.bold=True
                shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E8EEF5');cell._tc.get_or_add_tcPr().append(shade)
    repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in t.rows:
        no_split=OxmlElement('w:cantSplit');row._tr.get_or_add_trPr().append(no_split)
    p('','Caption')
    return t

p('TRACE Tutor','Title')
p('Today’s work & learning guide','Subtitle')
p('07 October 2026 • Asia/Dhaka','Subtitle')
p('Purpose: understand what changed, why the fixes work, which commands belong on your laptop or server, and how to verify the result.')
h('What we worked on')
table(['Area','Result at the end of this session'],[
    ('Settings page','Layout fix implemented locally; build and lint passed. Live deployment and visual confirmation remain pending.'),
    ('Code execution','Docker permissions and wrapper compatibility repaired. Your server reported Docker containment active and execution allowed; PM2 was online.'),
    ('Profile picture','SERVE_MEDIA=1 added in nano. The last screenshot still showed unsaved changes; save, restart and visual confirmation remain pending.')
],[2300,7060])
h('Your deployment')
p('The live site is https://trace.musfiqurtuhin.me. The server is Ubuntu at 89.167.59.65, with the application in /srv/trace-tutor. Your SSH account is shihab.')
p('The backend runs under PM2 using Waitress on 127.0.0.1:3010. nginx provides HTTPS. Student programs run in separate Docker containers through a restricted wrapper.')
h('The key lesson')
p('A change on your Windows laptop does not automatically update the Ubuntu server. Code must be transferred or deployed, configuration saved, and the correct server process restarted.')
p('This document contains no API keys, database passwords, or secret values. Screenshots containing .env secrets are intentionally omitted.','Caption')

page('Settings page: layout and scrolling')
h('The symptom',2)
p('The profile/settings screenshots showed cards cut off, the sidebar moving upward, and a large blank area below the visible content. This pointed to scrolling and sizing in the app shell.')
h('The code changes',2)
p('In frontend/src/components/Layout/AppShell.jsx, the outer shell changed from a viewport-height block to a fixed viewport shell:')
code('Before: h-screen w-screen overflow-hidden\nAfter:  fixed inset-0 overflow-hidden')
p('The main content gained overscroll-contain. This keeps a scroll gesture at the edge of the content from passing into outer scrolling.')
p('In frontend/src/pages/Profile.jsx, the profile’s root element gained shrink-0. This prevents a long settings form from being compressed by its flex parent.')
h('Checks run locally',2)
code('cd frontend\nnpm run build\nnpm run lint')
p('Both passed. The first build attempt failed because the filesystem sandbox denied an ancestor-directory lookup; the same build succeeded outside that restriction. No connected browser was available for visual QA.')
h('What still needs deployment',2)
p('Only the two backend runner files were shown being uploaded to the live server. There is no evidence that the frontend layout changes have been deployed yet.')
p('For a future frontend deployment, transfer those two changed frontend source files using your normal deployment method. From the server’s frontend directory, build with:')
code('cd /srv/trace-tutor/frontend\nnpm run build')
p('Then refresh the live profile page. Keep the sidebar/header visible and scroll to the final settings card. The server build and visual check above are follow-up steps, not commands confirmed executed today.','Caption')

page('Docker sandbox: why execution failed')
h('The original errors',2)
code('cat: probe.txt: Permission denied\navailable containment (rlimit) is below the required docker')
p('These were connected. Docker failed its workspace probe, so automatic detection found only rlimit. The production policy correctly refused the weaker tier.')
h('Ownership mismatch',2)
p('Python creates temporary work directories with permission mode 0700. Only the directory’s owner can access them. The backend owned the directory, but the runner image used UID/GID 65532:65532.')
p('If those user IDs differ, the runner cannot enter the mounted directory. Source files can also become unreadable under a restrictive umask. The compiler needs permission to create its executable there, not just read a probe.')
h('The secure fix',2)
bullet('A non-root Linux backend runs the container with its effective UID and GID, explicitly using --user UID:GID.')
bullet('A root backend hands private workdirs and source/probe files to runner UID/GID 65532. Student code never runs as root.')
bullet('Workdirs stay private at 0700. Source and probe files use 0600. We did not make them world-writable.')
bullet('A random-token probe checks container reads, compiler-step writes, and whether the backend sees the written result.')
h('Host paths must mean the same directory',2)
p('A backend container and the host Docker daemon can have different filesystems. A Linux systemd service using PrivateTmp=true also has a private /tmp. A bind source is interpreted by the daemon, not by the client process.')
p('The optional shared workspace settings handle this distinction. The provided systemd unit was updated to use /run/trace-tutor-work, but your actual PM2 deployment does not use that unit.')
p('Docker containment remains enforced: no container network, dropped capabilities, no-new-privileges, resource caps, and read-only mounts/root during program execution.')

page('Files changed and wrapper compatibility')
table(['File','What changed'],[
    ('frontend/src/components/\nLayout/AppShell.jsx','Fixed viewport shell; contained content scrolling.'),
    ('frontend/src/pages/\nProfile.jsx','Prevented the settings form from shrinking.'),
    ('backend/tutor/sandbox.py','Workspace ownership; explicit non-root UID/GID; host path mapping; read/write probe; optional volume compatibility.'),
    ('backend/tutor/runner.py','Uses workspace helpers for temp dirs and C/C++/Python sources; clearer status errors.'),
    ('backend/tutor/\ntest_sandbox.py','Permissions, mapping, mounts and C regression tests; deterministic reprobe test clock.'),
    ('backend/trace_backend/\nsettings.py','Reads workspace roots and mount-style configuration.'),
    ('backend/.env.example','Documents shared workspaces and restricted-wrapper compatibility.'),
    ('deploy/linux/\ntrace-tutor.service','Shared runtime directory while preserving PrivateTmp; relevant only to the optional systemd deployment.')
],[3550,5810])
h('The first server upload exposed a second issue',2)
code('trace-docker: refused: flag not allowed: --mount')
p('You inspected the existing wrapper and shim with these read-only server commands:')
code('cat /usr/local/bin/trace-docker\ncat ~/bin/docker')
p('Your server uses /usr/local/bin/trace-docker, reached through ~/bin/docker. It allows --volume and non-root --user, but rejects --mount. The new default mount syntax was therefore incompatible with this wrapper.')
p('We added CODE_SANDBOX_MOUNT_STYLE=volume as an explicit compatibility setting. It requires a configured, existing workspace at the same absolute host/backend path. The read/write probe remains mandatory. The default elsewhere stays bind.')
p('The wrapper was not changed, and you were not added to the Docker group. Environment fallbacks let the existing server settings module read the new options without uploading the whole settings file.')
p('sandbox.Dockerfile required no code change. Its image was built locally. The server already had the runner image, so this Python-only repair required no server image rebuild.','Caption')

page('Deployment: Windows commands and SSH')
h('Recognize where you are',2)
table(['Terminal prompt','Machine and shell'],[
    ('PS C:\\Users\\…\\backend>','Your Windows laptop; PowerShell commands.'),
    ('shihab@…:/srv/trace-tutor/backend$','Your Ubuntu server; Bash/Linux commands.')
],[4700,4660])
p('The active Python environment shown in a terminal does not tell you which machine you are on. Read the prompt and directory before executing a command.')
h('Upload the repaired runner files',2)
p('If you are inside SSH, exit to PowerShell first. The upload commands below assume your Windows terminal is in the project’s backend folder.')
code('exit')
code('scp -i "$env:USERPROFILE/.ssh/trace_tutor" `\n  .\\tutor\\sandbox.py .\\tutor\\runner.py `\n  shihab@89.167.59.65:/srv/trace-tutor/backend/tutor/')
p('scp copies files securely over SSH. -i selects your SSH private key. The destination is the server’s tutor directory. You repeated this upload after we added wrapper compatibility.')
h('Connect to the server',2)
code('ssh -i "$env:USERPROFILE/.ssh/trace_tutor" `\n  shihab@89.167.59.65')
p('ssh opens a terminal on the remote server. It does not upload source files by itself. Commands entered after connecting run on Ubuntu until you type exit.')
h('Why local runserver did not fix the live site',2)
p('VS Code’s Run Code action first tried /usr/bin/env, a Linux path unavailable on Windows. Starting Django from the local terminal then worked:')
code('cd backend\npython manage.py runserver')
p('That started a local development server at 127.0.0.1:8000. It was useful only for local testing. Your public site continued to use PM2/Waitress on the Ubuntu server. For that deployment, restart trace-tutor through PM2.')

page('Deployment: workspace, .env and restart')
h('Prepare the shared workspace on Ubuntu',2)
code('mkdir -p /srv/trace-tutor/sandbox-work\nchmod 700 /srv/trace-tutor/sandbox-work\ncd /srv/trace-tutor/backend\nnano .env')
p('mkdir -p creates the directory if needed. chmod 700 lets its owner read, write and enter it, while denying access to other users. nano opens the deployment configuration.')
h('Final sandbox configuration',2)
p('Add or update each key once; avoid duplicate entries. Leave unrelated settings intact.')
code('CODE_SANDBOX=docker\nCODE_SANDBOX_REQUIRED=1\nCODE_SANDBOX_MIN_TIER=docker\nCODE_SANDBOX_MOUNT_STYLE=volume\nCODE_SANDBOX_WORKDIR_ROOT=/srv/trace-tutor/sandbox-work\nCODE_SANDBOX_HOST_WORKDIR_ROOT=/srv/trace-tutor/sandbox-work')
p('docker selects the container runner. REQUIRED=1 enforces containment, MIN_TIER=docker rejects rlimit, and volume selects syntax allowed by your wrapper. Both roots point to the same existing directory on this host deployment.')
h('Save in nano',2)
p('An asterisk beside .env means changes are unsaved. Press Ctrl+O, Enter to write the file, then Ctrl+X to exit. Alt+/ moves to the end of the file. Saving a file does not restart an already-running backend.')
page('Server verification and test evidence')
h('Check the sandbox and restart the application',2)
code('../venv/bin/python manage.py shell \\\n  -c "from tutor import sandbox; print(sandbox.status())"\npm2 restart trace-tutor --update-env')
p('The first command loads Django settings and runs the actual containment probe. ../venv/bin/python selects the server’s Python environment. PM2 then restarts the deployed backend; --update-env refreshes PM2 environment values.')
p('Your server screenshot confirmed:','Caption')
code("'tier': 'docker'\n'isolated': True\n'enforced': True\n'required_tier': 'docker'\n'allowed': True\n'detail': None")
p('PM2 also reported trace-tutor online. This confirms the server-side probe and restart, not the final browser C execution result.')

h('Local verification evidence',2)
table(['Test environment / revision','Result'],[
    ('Initial Windows host backend → Docker','50 tests: 42 passed, 8 skipped.'),
    ('Linux root backend container → host daemon','50 tests passed; runner UID/GID 65532:65532.'),
    ('Linux backend UID/GID 1001:1002 → host daemon','50 tests passed; restrictive umask 077.'),
    ('Final volume compatibility on Windows','54 tests: 50 passed, 4 POSIX-only tests skipped.'),
    ('Final targeted tests with older settings','25 tests passed; environment fallback verified.')
],[6450,2910])
p('These are separate runs/revisions, not a count of unique tests. The full database-backed application suite was not run. Linux isolation checks included blocked network access, denied filesystem writes, non-root execution, timeouts, memory exhaustion and fork-bomb containment.')
page('C program: execution and live-site check')
h('The requested program',2)
code('#include <stdio.h>\nint main() {\n    int n, sum = 0;\n    scanf("%d", &n);\n    for (int i = 1; i <= n; i++) sum += i;\n    printf("%d\\n", sum);\n    return 0;\n}')
code('Input: 5\nExpected output: 15')
p('The program sums 1 + 2 + 3 + 4 + 5. Local Docker runs returned SUCCESS, output 15, and exit code 0. The original Linux permission error was reproduced and then resolved. Incorrect host paths were rejected.')
h('Local verification commands',2)
p('The production runner image was built on Windows from the repository root:')
code('docker desktop start\ndocker build -f backend/tutor/sandbox.Dockerfile `\n  -t trace-tutor-runner:1 backend/tutor')
p('A trailing backtick continues a PowerShell command onto the next line. This build belongs on a host with Docker build access; your server wrapper does not grant that access.')
p('The final compatibility suite ran locally using your installed Python environment:')
code('E:/projects/anaconda/envs/trace_tutor/python.exe `\n  docs/sandbox-verification/verify_volume_compat.py')
h('The final live-site check',2)
p('Refresh the public site with Ctrl+Shift+R, open the C workspace, enter the code, give input 5 and click Run Code. Verify output 15. The conversation does not yet include that live browser result.')

page('Profile picture: production media serving')
h('The symptom and likely cause',2)
p('Your uploaded avatar displayed a broken-image icon and the name text. The application generated an avatar URL, but the browser could not load the image. We inspected avatar generation, MEDIA_ROOT, MEDIA_URL, the media route and the serving flag.')
p('The code defaults SERVE_MEDIA to DEBUG. Your server has DEBUG=0, so Django’s media view returns 404 unless SERVE_MEDIA=1 or another file server serves /media/. That was the likely cause; the actual image HTTP response was not captured.')
h('The configuration change',2)
code('cd /srv/trace-tutor/backend\nnano .env')
p('Add or update:')
code('SERVE_MEDIA=1')
p('Save with Ctrl+O, Enter, exit with Ctrl+X, then restart:')
code('pm2 restart trace-tutor --update-env')
p('Refresh the live page with Ctrl+Shift+R. This configuration permits the existing media route to serve uploaded files under backend/media/. No avatar code changes or image deletion were needed.')
h('What remains to verify',2)
p('The last screenshot showed SERVE_MEDIA=1 in nano with an unsaved marker. We confirmed the line was correct and instructed you to save and restart, but no subsequent screenshot confirms that the avatar loaded.')
p('If it still fails, open the image in a new tab and note the URL and HTTP/error result. An incorrect URL, missing file, file permissions, or nginx handling can also cause broken images. Do not assume that re-uploading alone fixes a serving configuration problem.')
h('Configuration safety',2)
p('Keep DEBUG=0 in production. Serving avatars does not require turning on Django debug mode. Your .env screenshots exposed credentials; arrange rotation with the server owner. This learning document intentionally does not copy those secret values.')

page('Your reusable checklist and command glossary')
h('Repeat this workflow for a future fix',2)
bullet('Inspect the symptom and logs. Decide whether the cause is application code, environment configuration, file permissions, or deployment.')
bullet('Make the smallest relevant local change. Run appropriate checks and preserve evidence of the result.')
bullet('Confirm the target machine. Upload only the intended changed files; do not replace the server .env with your laptop .env.')
bullet('Save configuration changes. Check the service’s Python environment, workspace path, and current user permissions.')
bullet('Restart the correct deployed process. For this server, use PM2/Waitress, not manage.py runserver or the optional trace-tutor systemd unit.')
bullet('Verify server health and the actual browser action. A process being online is not proof that every feature works.')
h('Useful server commands',2)
code('pm2 list\npm2 logs trace-tutor --lines 50 --nostream\ncommand -v docker\nid\nls -ld /srv/trace-tutor/sandbox-work')
p('These are reference commands for future diagnosis; they are not all shown executed on your server during this session. The Docker command should resolve through your user shim, which uses the locked wrapper.')
table(['Term','Meaning'],[
    ('UID / GID','Numeric user/group IDs used to evaluate Linux file access.'),
    ('Bind mount','A host directory exposed at a path such as /work in a container.'),
    ('Docker versus rlimit','Docker isolates network/filesystem; rlimit primarily caps resources.'),
    ('Probe versus execution','A probe checks readiness; the live Run Code action confirms the full feature.'),
    ('Build versus restart','A frontend build creates assets; a backend restart reloads Python/configuration.')
],[2500,6860])
p('Sources: session screenshots, project diffs, sandbox verification logs, and the supplied server guide. Confirmed actions and recommended steps are identified separately.','Caption')

doc.save(OUT)

# Structural preset checks before rendering.
assert sec.page_width.twips==12240 and sec.page_height.twips==15840
for t in doc.tables:
    assert sum(int(c.get(qn('w:w'))) for c in t._tbl.tblGrid)==9360
    for row in t.rows:
        assert sum(int(c._tc.get_or_add_tcPr().find(qn('w:tcW')).get(qn('w:w'))) for c in row.cells)==9360
print(OUT)
