const http = require('http'); const fs = require('fs'); const path = require('path');
const root = __dirname;
const MIME = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8',
  '.json':'application/json; charset=utf-8', '.webmanifest':'application/manifest+json; charset=utf-8',
  '.css':'text/css; charset=utf-8', '.png':'image/png', '.svg':'image/svg+xml', '.md':'text/markdown; charset=utf-8' };
http.createServer((req, res) => {
  const requested = decodeURIComponent((req.url || '/').split('?')[0]);
  const file = path.join(root, requested === '/' ? 'index.html' : requested.replace(/^\//, ''));
  if (!file.startsWith(root)) { res.writeHead(403); return res.end(); }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); return res.end(); }
    const h = { 'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream' };
    if (file.endsWith('sw.js')) h['Cache-Control'] = 'no-cache';
    res.writeHead(200, h); res.end(data);
  });
}).listen(4173, '127.0.0.1');
