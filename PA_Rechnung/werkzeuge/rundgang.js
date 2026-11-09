// Pfeiffer-Audio Rechnung - Werkzeug: Rundgang v1.0.0 (Autor: T. Pfeiffer)
// Rundgang: every page in a fresh tab, year selectors, tabs/chips, first row of lists; collects JS errors, HTTP 5xx, red toasts
const { chromium } = require('playwright');
const U = process.argv[2] || 'http://127.0.0.1:8792';
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, locale: 'de-DE' });
  await ctx.addInitScript(() => { window.open = () => null; window.print = () => {}; window.close = () => {}; });
  const errs = []; let cur = 'start';
  const hook = p => {
    p.on('pageerror', e => errs.push(`[${cur}] JS: ${String(e).slice(0, 220)}`));
    p.on('dialog', d => d.dismiss().catch(() => {}));
    p.on('response', async r => { if (r.status() >= 500) { let t = ''; try { t = (await r.text()).slice(0, 220); } catch (e) {} errs.push(`[${cur}] HTTP ${r.status()} ${r.url().replace(U, '')} ${t}`); } });
  };
  let p = await ctx.newPage(); hook(p);
  const post = (u, d) => p.evaluate(async ([u, d]) => (await fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) })).json(), [u, d]);
  await p.goto(U); await post('/api/m92/unlock', { pin: '135790' });
  await p.goto(U); await p.waitForTimeout(2500);
  const navs = await p.evaluate(() => [...new Set([...document.querySelectorAll('#side [data-go]')].map(b => b.dataset.go))]);
  const extra = ['m45jahr', 'kalender', '@editor', '@neu'];
  const seen = new Set();
  const grab = async (pg) => { try { const t = await pg.evaluate(() => [...document.querySelectorAll('.tst.bad')].map(x => x.textContent)); t.forEach(x => { const k = cur + x; if (!seen.has(k)) { seen.add(k); errs.push(`[${cur}] TOAST: ${x}`); } }); } catch (e) {} };
  let n = 0;
  for (const v of [...navs, ...extra.filter(e => !navs.includes(e))]) {
    cur = v; n++;
    let pg;
    try {
      pg = await ctx.newPage(); hook(pg);
      await pg.goto(U); await pg.waitForTimeout(1200);
      if (v === '@editor') await pg.evaluate(() => { const i = (S.invoices || []).find(x => x.locked) || (S.invoices || [])[0]; openInvoice(i.id); });
      else if (v === '@neu') await pg.evaluate(() => newInvoice({ typ: 'rechnung' }));
      else await pg.evaluate(v => go(v), v);
      await pg.waitForTimeout(1500); await grab(pg);
      const ys = await pg.evaluate(() => [...document.querySelectorAll('#main select')].filter(s => [...s.options].some(o => /^20\d\d$/.test(o.value || o.text))).map(s => s.id).filter(Boolean));
      for (const id of ys.slice(0, 1)) for (const y of ['2025', '2026']) {
        await pg.evaluate(([id, y]) => { const s = document.getElementById(id); if (s && [...s.options].some(o => (o.value || o.text) == y)) { s.value = y; s.dispatchEvent(new Event('change')); } }, [id, y]);
        await pg.waitForTimeout(600); await grab(pg);
      }
      const sel = '#main .seg button, #main .chips .chip, #main .tabs button, #main [data-m45t]';
      const cnt = await pg.locator(sel).count();
      for (let i = 0; i < Math.min(cnt, 16); i++) {
        if (pg.isClosed()) break;
        try { await pg.locator(sel).nth(i).click({ timeout: 1500 }); await pg.waitForTimeout(400); await grab(pg); } catch (e) {}
        await pg.evaluate(() => document.querySelectorAll('.mb').forEach(m => m.remove())).catch(() => {});
      }
      // open first row of a list (read only: opens dialog / detail)
      if (!pg.isClosed()) {
        const row = pg.locator('#main table tbody tr[data-id], #main .list .item[data-id], #main tr.click').first();
        if (await row.count()) { try { await row.click({ timeout: 1500 }); await pg.waitForTimeout(900); await grab(pg); } catch (e) {} }
      }
    } catch (e) { errs.push(`[${cur}] RUNDGANG: ${String(e).slice(0, 160)}`); }
    try { if (pg && !pg.isClosed()) await pg.close(); } catch (e) {}
  }
  console.log(`Seiten: ${n}`);
  console.log(errs.length ? errs.join('\n') : 'KEINE FEHLER');
  await b.close();
})();
