// Jelly Leon clients — besturing van jellyfin-desktop 2.0.0 via ruwe CDP (QtWebEngine, --remote-debugging-port).
// Eén actie per aanroep; uitvoer is één JSON-regel. Alleen voor ontwikkeling (compat/desktop.py), nooit op de NAS.
// Playwright connectOverCDP werkt niet op QtWebEngine ("Browser context management is not supported"); daarom de
// Node 22-WebSocket rechtstreeks op het paginadoel.
//   node desktop_cdp.mjs '{"poort":9333,"actie":"verbind","server":"http://127.0.0.1:8096"}'
//   acties: doelen | verbind | inloggen | teksten | hash | klik | opslag | wacht_op | fouten
const cfg = JSON.parse(process.argv[2]);
const basis = `http://127.0.0.1:${cfg.poort}`;
const wacht = (ms) => new Promise((r) => setTimeout(r, ms));
const uit = { actie: cfg.actie };

async function pagina() {
  const lijst = await (await fetch(`${basis}/json/list`)).json();
  return lijst.find((d) => d.type === 'page' && (!cfg.server || d.url.startsWith(cfg.server))) ||
    lijst.find((d) => d.type === 'page');
}

async function verbind(doel) {
  const ws = new WebSocket(doel.webSocketDebuggerUrl);
  await new Promise((ok, nok) => { ws.onopen = ok; ws.onerror = nok; });
  let id = 0;
  const wachtend = new Map();
  const fouten = [];
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id && wachtend.has(d.id)) { const [ok, timer] = wachtend.get(d.id); clearTimeout(timer); wachtend.delete(d.id); ok(d); }
    if (d.method === 'Runtime.exceptionThrown') fouten.push(String(d.params.exceptionDetails?.exception?.description || d.params.exceptionDetails?.text).slice(0, 200));
    if (d.method === 'Log.entryAdded' && d.params.entry.level === 'error') fouten.push(`${d.params.entry.text} ${d.params.entry.url || ''}`.slice(0, 200));
  };
  // Elke aanroep met een time-out: tijdens een paginawissel antwoordt het oude doel niet meer. De timer wordt bij een
  // antwoord gewist (gemeten: openstaande timers hielden het Node-proces ~15 s in leven, waardoor de harnas de start
  // van het afspelen te laat zag).
  const stuur = (method, params = {}) => new Promise((ok, nok) => {
    id += 1; const mijn = id;
    const timer = setTimeout(() => { if (wachtend.delete(mijn)) nok(new Error(`CDP-time-out: ${method}`)); }, 15000);
    wachtend.set(mijn, [ok, timer]);
    ws.send(JSON.stringify({ id: mijn, method, params }));
  });
  await stuur('Runtime.enable');
  await stuur('Log.enable');
  const evalueer = async (expr) => {
    const r = await stuur('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.text);
    return r.result?.result?.value;
  };
  return { ws, stuur, evalueer, fouten };
}

async function wachtOp(c, expr, ms) {
  const einde = Date.now() + ms;
  while (Date.now() < einde) {
    try { if (await c.evalueer(expr)) return true; } catch { /* pagina wisselt */ }
    await wacht(500);
  }
  return false;
}

// Klik zoals een gebruiker: muis-events op het midden van het eerste zichtbare element (niet element.click()).
async function muisklik(c, selector) {
  const plek = await c.evalueer(`(() => { const e = [...document.querySelectorAll(${JSON.stringify(selector)})]
    .find((x) => x.offsetParent); if (!e) return null; e.scrollIntoView({ block: 'center' });
    const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
  if (!plek) return false;
  for (const type of ['mousePressed', 'mouseReleased']) {
    await c.stuur('Input.dispatchMouseEvent', { type, x: plek.x, y: plek.y, button: 'left', clickCount: 1 });
  }
  return true;
}

async function main() {
  if (cfg.actie === 'doelen') {
    uit.doelen = (await (await fetch(`${basis}/json/list`)).json()).map((d) => ({ type: d.type, url: d.url.slice(0, 120) }));
    return;
  }
  const doel = await pagina();
  if (!doel) throw new Error('geen paginadoel');
  uit.url = doel.url.slice(0, 160);
  const c = await verbind(doel);
  try {
    if (cfg.actie === 'verbind') {
      // find-webclient.html: de knop staat uit tot er een input-event komt; daarna het formulier versturen.
      await wachtOp(c, "!!document.getElementById('address')", 30000);
      await c.evalueer(`(() => { const a = document.getElementById('address'); a.value = ${JSON.stringify(cfg.server)};
        a.dispatchEvent(new Event('input', { bubbles: true })); document.getElementById('connect-form').requestSubmit(); return 1; })()`);
      c.ws.close();
      for (let i = 0; i < 60; i += 1) {
        await wacht(1000);
        const p = await pagina();
        if (p && p.url.startsWith(cfg.server)) { uit.url = p.url.slice(0, 160); uit.ok = true; return; }
      }
      uit.ok = false;
      uit.fouten = c.fouten.slice(0, 10);
      return;
    }
    if (cfg.actie === 'inloggen') {
      uit.inlogscherm = await wachtOp(c, "!!document.querySelector('#txtManualName, .btnManual')", 60000);
      await c.evalueer("(() => { if (!document.querySelector('#txtManualName')?.offsetParent) document.querySelector('.btnManual')?.click(); return 1; })()");
      await wachtOp(c, "!!document.querySelector('#txtManualName')?.offsetParent", 15000);
      await c.evalueer(`(() => { const zet = (s, v) => { const e = document.querySelector(s); e.value = v;
        e.dispatchEvent(new Event('input', { bubbles: true })); e.dispatchEvent(new Event('change', { bubbles: true })); };
        zet('#txtManualName', ${JSON.stringify(cfg.gebruiker)}); zet('#txtManualPassword', ${JSON.stringify(cfg.wachtwoord)}); return 1; })()`);
      await muisklik(c, '.manualLoginForm button[type=submit]');
      uit.ok = await wachtOp(c, "(() => { try { return Object.values(JSON.parse(localStorage.getItem('jellyfin_credentials') || '{}').Servers || {}).some((s) => s.AccessToken); } catch { return false; } })()", 30000);
      uit.thuis = await wachtOp(c, "document.body.innerText.includes('My Media')", 30000);
      return;
    }
    if (cfg.actie === 'teksten') {
      await wacht(cfg.wacht_ms || 0);
      uit.teksten = await c.evalueer("[...new Set(document.body.innerText.split('\\n').map((t) => t.trim()).filter(Boolean))].slice(0, 200)");
      return;
    }
    if (cfg.actie === 'hash') {
      await c.evalueer(`(() => { location.hash = ${JSON.stringify(cfg.hash)}; return 1; })()`);
      await wacht(cfg.wacht_ms || 3000);
      uit.ok = true;
      return;
    }
    if (cfg.actie === 'wacht_op') {
      uit.ok = await wachtOp(c, cfg.expr, cfg.ms || 20000);
      return;
    }
    if (cfg.actie === 'klik') {
      uit.ok = await wachtOp(c, `[...document.querySelectorAll(${JSON.stringify(cfg.selector)})].some((e) => e.offsetParent)`, cfg.ms || 20000)
        && await muisklik(c, cfg.selector);
      return;
    }
    if (cfg.actie === 'opslag') {
      // Zelfde instellingen als 'Instellingen → Afspelen' van de web-client (appSettings in localStorage).
      uit.ok = await c.evalueer(`(() => { const z = ${JSON.stringify(cfg.zet || {})}; for (const [k, v] of Object.entries(z)) {
        if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } return true; })()`);
      return;
    }
    if (cfg.actie === 'fouten') {
      await wacht(cfg.wacht_ms || 1000);
      uit.fouten = c.fouten.slice(0, 20);
      return;
    }
    throw new Error(`onbekende actie ${cfg.actie}`);
  } finally {
    try { c.ws.close(); } catch { /* al dicht */ }
  }
}

main().catch((e) => { uit.ok = false; uit.fout = String(e).slice(0, 400); })
  .finally(() => { process.stdout.write(`${JSON.stringify(uit)}\n`, () => process.exit(0)); });
