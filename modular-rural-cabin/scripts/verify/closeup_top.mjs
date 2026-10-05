import { chromium } from 'playwright';
import http from 'http'; import fs from 'fs'; import path from 'path';
const root = process.cwd();
const srv = http.createServer((req, res) => { const p = path.join(root, decodeURIComponent(req.url.split('?')[0])); fs.readFile(p, (e, d) => { if (e) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'Content-Type': p.endsWith('.html') ? 'text/html' : p.endsWith('.js') ? 'text/javascript' : 'application/octet-stream' }); res.end(d); }); }).listen(8767);
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
fs.mkdirSync('close', { recursive: true });
for (const [f, az, el, zoom] of JSON.parse(process.argv[2])) {
  for (const flip of [0, 1]) {
    await page.goto(`http://localhost:8767/closeup.html?f=${encodeURIComponent(f)}.glb&az=${az}&el=${el}&zoom=${zoom}&l=0.6,10,1.2${flip ? '&flipy=1' : ''}`);
    await page.waitForFunction(() => window.__done, null, { timeout: 180000 });
    await page.locator('#c').screenshot({ path: `close_top/${path.basename(f)}_${flip ? 'flipped' : 'export'}.png` });
  }
  console.log('done', f);
}
await browser.close(); srv.close();
