// Runs the webapp's own generator (index.html) in Node and writes the element schedule as JSON.
// Usage: node export_model.js [settings.json] [out.json]
//   settings.json: a file saved with "Save .json" in the webapp (its params + curves are used).
//   Without it, the webapp defaults are used.
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const between = (a, b) => {
  const i = html.indexOf(a), j = html.indexOf(b, i);
  if (i < 0 || j < 0) throw new Error(`Marker not found in index.html: ${i < 0 ? a : b}`);
  return html.slice(i, j);
};
const src = between('const DEFAULTS', 'const clone') +
  'const clone = o => JSON.parse(JSON.stringify(o));\nlet P, C;\n' +
  between('/* ---------- helpers', '/* ---------- theme tokens') +
  'return { DEFAULTS, DEFAULT_CURVES, run(p, c) { P = p; C = c; return generate(); } };';
const lib = new Function(src)();

const [inFile, outFile = path.join(__dirname, 'facade_model.json')] = process.argv.slice(2);
let P = Object.assign({}, lib.DEFAULTS), C = JSON.parse(JSON.stringify(lib.DEFAULT_CURVES));
if (inFile) {
  const d = JSON.parse(fs.readFileSync(inFile, 'utf8'));
  if (!d.params || !d.curves) throw new Error(`${inFile} has no params/curves. Save it from the webapp with "Save .json".`);
  Object.assign(P, d.params); C = d.curves;
}
const m = lib.run(P, C);
const r3 = v => Math.round(v * 1000) / 1000;
const out = {
  units: 'm', params: P, curves: C,
  fins: m.fins.map(f => ({ x: r3(f.x), y0: r3(f.y0), y1: r3(f.y1), width: r3(f.w), depth: r3(f.d) })),
  horizontals: m.hors.map(h => ({ x0: r3(h.x0), x1: r3(h.x1), y: r3(h.y), thickness: r3(h.h), depth: r3(h.d), z: r3(h.z) }))
};
fs.writeFileSync(outFile, JSON.stringify(out));
console.log(`${out.fins.length} fins, ${out.horizontals.length} horizontals -> ${outFile}`);
