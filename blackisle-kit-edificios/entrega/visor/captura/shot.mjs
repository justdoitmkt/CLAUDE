// uso: node shot.mjs <glb relativo a la carpeta servida> <salida.png> [azimut] [elevación]
// Sirve la carpeta en http://127.0.0.1:8765 (python3 -m http.server 8765) con shot.html, node_modules/three y el GLB.
// Chromium por software (SwiftShader). Imprime JSON {title, info, warnings} con las métricas del cargador.
import { chromium } from 'playwright';
const [,, glb, out, az = '-35', el = '15'] = process.argv;
const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const p = await b.newPage({ viewport: { width: 1280, height: 720 } });
const warnings = [];
p.on('console', m => { if (m.type() === 'warning' || m.type() === 'error') warnings.push(m.text()); });
await p.goto(`http://127.0.0.1:8765/shot.html?glb=${glb}&az=${az}&el=${el}`);
await p.waitForFunction(() => document.title !== 'loading', null, { timeout: 900000 });
const title = await p.title();
const info = await p.evaluate(() => window.info);
if (title === 'ready') await p.screenshot({ path: out });
console.log(JSON.stringify({ title, info, warnings }));
await b.close();
if (title !== 'ready') process.exit(1);
