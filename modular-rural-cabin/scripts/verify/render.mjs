import { chromium } from 'playwright';
import http from 'http'; import fs from 'fs'; import path from 'path';
const root = process.cwd();
const types = { '.html': 'text/html', '.js': 'text/javascript', '.glb': 'model/gltf-binary' };
const srv = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0]));
  fs.readFile(p, (e, d) => { if (e) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'Content-Type': types[path.extname(p)] || 'application/octet-stream' }); res.end(d); });
}).listen(8766);
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
page.on('console', m => { if (m.type() === 'error') console.log('console:', m.text()); });
const out = process.argv[2]; fs.mkdirSync(out, { recursive: true });
const walk = d => fs.readdirSync(d, { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]);
const files = walk('glb').filter(f => f.endsWith('.glb')).map(f => path.relative('glb', f)).sort();
const only = process.argv[3] ? process.argv[3].split(',') : null;
const views = process.argv[4] ? JSON.parse(process.argv[4]) : [['a', 35, 20], ['b', 215, 25]];
for (const f of files) {
  const name = path.dirname(f) + '__' + path.basename(f, '.glb');
  if (only && !only.some(o => name.startsWith(o))) continue;
  for (const [tag, az, el, zoom] of views) {
    await page.goto(`http://localhost:8766/render.html?f=${encodeURIComponent(f)}&az=${az}&el=${el}&zoom=${zoom || 1}`);
    await page.waitForFunction(() => window.__done, null, { timeout: 300000 });
    const r = await page.evaluate(() => window.__done);
    await page.locator('#c').screenshot({ path: `${out}/${name}_${tag}.png` });
    console.log(f, tag, JSON.stringify(r));
  }
}
await browser.close(); srv.close();
