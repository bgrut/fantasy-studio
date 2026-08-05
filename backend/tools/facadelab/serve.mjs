// Facade Lab dev server. Static only — the lab never talks to the game backend.
// Read the file BEFORE writing headers: doing it the other way meant a missing
// asset threw after the 200 was already sent, killing the whole process.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
const ROOT = new URL('.', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const MIME = { '.html':'text/html', '.js':'text/javascript', '.mjs':'text/javascript',
               '.json':'application/json', '.css':'text/css' };
createServer(async (req, res) => {
  // resolve the root request BEFORE normalize(): on Windows normalize('/')
  // yields a lone backslash, which join() treats as "the directory itself",
  // so readFile fails with EISDIR — a 404 on the only page there is.
  const raw = req.url.split('?')[0];
  const rel = (raw === '/' || raw === '') ? 'index.html'
    : normalize(decodeURIComponent(raw)).replace(/^[\\/]+/, '');
  const f = join(ROOT, rel);
  let buf;
  try { buf = await readFile(f); }
  catch { res.writeHead(404, { 'Content-Type': 'text/plain' }); return res.end('not found'); }
  res.writeHead(200, { 'Content-Type': MIME[extname(f)] || 'application/octet-stream' });
  res.end(buf);
}).listen(8792, () => console.log('Facade Lab → http://127.0.0.1:8791/'));
