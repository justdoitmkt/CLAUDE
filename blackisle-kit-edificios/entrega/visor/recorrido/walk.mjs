// uso: node walk.mjs <glb relativo a glbview> <shots.json> <carpeta salida> <prefijo>
import { chromium } from 'playwright';
import fs from 'fs';
const [,, glb, shotsFile, outDir, prefix] = process.argv;
const shots = JSON.parse(fs.readFileSync(shotsFile, 'utf8'));
const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const p = await b.newPage({ viewport: { width: 1600, height: 900 } });
await p.goto(`http://127.0.0.1:8765/walk.html?glb=${glb}`);
await p.waitForFunction(() => document.title !== 'loading', null, { timeout: 900000 });
console.log('title', await p.title());
for (const s of shots) {
  const t0 = Date.now();
  const info = await p.evaluate(s => window.go(s), s);
  await p.screenshot({ path: `${outDir}/${prefix}_${s.name}.png` });
  console.log('SHOT', s.name, JSON.stringify(info), Date.now() - t0, 'ms');
}
await b.close();
