// Optional localhost preview; direct index.html opening also works without Node.
import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const port = Number(process.env.DEMO_PORT || 4173);
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.json': 'application/json; charset=utf-8' };
http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url || '/', 'http://localhost');
    const pathname = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname);
    // Serve only the demo and its fixtures; never expose .git, .env or local dependencies.
    if (!['/index.html', '/README.md'].includes(pathname) && !/^\/demo\/[a-zA-Z0-9_.-]+$/.test(pathname)) {
      response.writeHead(404); response.end('Not found'); return;
    }
    const target = path.resolve(root, '.' + pathname);
    if (!target.startsWith(path.resolve(root) + path.sep) || !(await stat(target)).isFile()) {
      response.writeHead(404); response.end('Not found'); return;
    }
    response.writeHead(200, { 'Content-Type': types[path.extname(target)] || 'text/plain; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    response.end(await readFile(target));
  } catch { response.writeHead(404); response.end('Not found'); }
}).listen(port, '127.0.0.1', () => console.log(`Offline demo: http://127.0.0.1:${port}`));
