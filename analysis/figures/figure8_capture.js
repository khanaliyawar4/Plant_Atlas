// Captures the panels of Figure 8 from the released portal file (Plant Bioengineering Atlas, data release v1.1).
// Usage: node figure8_capture.js <portal.html> <out_dir> [gene symbol for panels B-C; default CeWRI4]
const {chromium} = require('playwright');
const fs = require('fs');
const URL = 'file://' + process.argv[2], OUT = process.argv[3];
const DSF = 3;
const GENE = process.argv[4] || 'CeWRI4';

async function open(b, width) {
  const p = await b.newPage({viewport: {width, height: 1000}, deviceScaleFactor: DSF});
  await p.goto(URL, {waitUntil: 'load', timeout: 120000});
  await p.waitForTimeout(2500);
  await p.evaluate(() => { const o = document.getElementById('orient'); if (o) o.remove(); });
  return p;
}
const rect = (p, js) => p.evaluate(js);

(async () => {
  const b = await chromium.launch();
  const meta = {};

  // A: header; B-C: Browse with one record opened (desktop layout, 1280 px)
  let p = await open(b, 1280);
  await p.locator('header').first().screenshot({path: OUT + '/A_header.png'});
  await p.click('#nav button[data-t="explorer"]'); await p.waitForTimeout(1200);
  const got = p.locator('#panel button', {hasText: 'Got it'});
  if (await got.count()) { await got.first().click(); await p.waitForTimeout(400); }
  await p.selectOption('#etr', {label: 'Drought tolerance'});
  await p.fill('#eq', GENE); await p.waitForTimeout(1500);
  meta.first_row = await p.evaluate(() => document.querySelector('#panel table tbody tr').innerText.replace(/\s+/g, ' '));
  await p.locator('#panel table tbody tr').first().click(); await p.waitForTimeout(1200);
  const bc = await rect(p, () => {
    const eq = document.getElementById('eq'); let card = eq;
    while (card.parentElement && card.getBoundingClientRect().width < 1000) card = card.parentElement;
    const c = card.getBoundingClientRect();
    const t = document.querySelector('#panel table').getBoundingClientRect();
    const det = document.querySelector('#panel tr.detail').getBoundingClientRect();
    const blocks = [...document.querySelectorAll('#panel tr.detail .dgrid > div')];
    const cons = blocks.find(d => /^CONSTRUCT/.test(d.innerText.trim())).getBoundingClientRect();
    return {x: t.x - 6, w: t.width + 12, b_top: c.y + scrollY - 8, c_top: det.y + scrollY, c_bottom: cons.bottom + scrollY + 12};
  });
  await p.screenshot({path: OUT + '/B_browse.png', fullPage: true, clip: {x: bc.x, y: bc.b_top, width: bc.w, height: bc.c_top - bc.b_top}});
  await p.screenshot({path: OUT + '/C_record.png', fullPage: true, clip: {x: bc.x, y: bc.c_top, width: bc.w, height: bc.c_bottom - bc.c_top}});
  meta.BC = bc;
  await p.close();

  // D: gene view, E: knowledge graph (narrow layout, 760 px, for half-width panels)
  p = await open(b, 760);
  await p.click('#nav button[data-t="genes"]'); await p.waitForTimeout(1000);
  await p.fill('#gq', 'DREB2A'); await p.waitForTimeout(800); await p.keyboard.press('Enter'); await p.waitForTimeout(1500);
  const d = await rect(p, () => {
    const all = [...document.querySelectorAll('#panel *')];
    const head = all.find(e => e.children.length <= 3 && /^DREB2A\s*-\s*\d+ records/.test(e.innerText.trim()));
    const orth = all.filter(e => /^DESIGN LAUNCHPAD/.test(e.innerText.trim()) && e.innerText.length < 200).pop();
    const h = head.getBoundingClientRect(), o = orth.getBoundingClientRect();
    const panel = document.querySelector('#panel').getBoundingClientRect();
    return {x: panel.x, w: panel.width, y: h.y + scrollY - 8, bottom: o.top + scrollY - 4};
  });
  await p.screenshot({path: OUT + '/D_gene.png', fullPage: true, clip: {x: d.x, y: d.y, width: d.w, height: d.bottom - d.y}});
  meta.D = d;
  await p.click('#nav button[data-t="network"]'); await p.waitForTimeout(8000);
  await p.locator('#panel').locator('text=Drought tolerance').first().click(); await p.waitForTimeout(3000);
  const e = await rect(p, () => {
    const s = document.querySelector('#nwrap svg').getBoundingClientRect();
    const leg = [...document.querySelectorAll('#panel *')].filter(x => /best connected of/.test(x.innerText) && x.innerText.length < 200).pop().getBoundingClientRect();
    return {svg: {x: s.x, y: s.y + scrollY, w: s.width, h: s.height}, legend: {x: leg.x, y: leg.y + scrollY, w: leg.width, h: leg.height}};
  });
  await p.screenshot({path: OUT + '/E_graph_full.png', fullPage: true, clip: {x: e.svg.x, y: e.svg.y, width: e.svg.w, height: e.svg.h}});
  await p.screenshot({path: OUT + '/E_legend.png', fullPage: true, clip: {x: e.legend.x, y: e.legend.y, width: e.legend.w, height: e.legend.h}});
  meta.E = e;
  await p.close();
  await b.close();
  fs.writeFileSync(OUT + '/capture_meta.json', JSON.stringify(meta, null, 1));
  console.log(JSON.stringify(meta).slice(0, 600));
})();
