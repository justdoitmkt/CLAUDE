import validator from 'gltf-validator';
import fs from 'fs';
import path from 'path';
const dir = process.argv[2];
const files = fs.readdirSync(dir).filter(f => f.endsWith('.glb')).sort();
let bad = 0;
for (const f of files) {
  const data = new Uint8Array(fs.readFileSync(path.join(dir, f)));
  const r = await validator.validateBytes(data, { maxIssues: 50 });
  const i = r.issues;
  const msgs = i.messages.filter(m => m.severity <= 1).map(m => `${m.severity === 0 ? 'E' : 'W'} ${m.code}: ${m.message} ${m.pointer || ''}`);
  if (i.numErrors) bad++;
  console.log(`${f.padEnd(20)} errors=${i.numErrors} warnings=${i.numWarnings} infos=${i.numInfos} hints=${i.numHints}`);
  for (const m of [...new Set(msgs)].slice(0, 8)) console.log('    ' + m);
}
process.exit(bad ? 1 : 0);
