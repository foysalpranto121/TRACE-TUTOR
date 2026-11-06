import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const dist = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../frontend/dist');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2' };
http.createServer(async (req, res) => {
  const pathname = new URL(req.url, 'http://127.0.0.1').pathname;
  if (pathname.startsWith('/api/')) { res.writeHead(501, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ error: 'QA preview has no backend. Mock every API request.' })); return; }
  let file = path.resolve(dist, '.' + decodeURIComponent(pathname));
  if (file !== dist && !file.startsWith(dist + path.sep)) { res.writeHead(403); res.end(); return; }
  try {
    if (!(await fs.stat(file)).isFile()) file = path.join(dist, 'index.html');
  } catch { file = path.join(dist, 'index.html'); }
  try { res.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' }); res.end(await fs.readFile(file)); }
  catch { res.writeHead(404); res.end(); }
}).listen(4174, '127.0.0.1', () => console.log('QA static preview on http://127.0.0.1:4174 (API disabled)'));
