/* vejkort.js - vejkort som SVG ud fra OpenStreetMap-data fra lav_vejkort.py (ingen kortfliser, virker uden internet).
   Bruges af nationale_analysekonklusioner.html (lav_konklusioner_html.py) og rapporten (byg_rapport.py).

   const k = Vejkort.lav(element, grund, omraadePunkter)
     grund: {omraade:[s,w,n,e], enhed, hentet, veje, bygninger, detaljer} fra analyser\kort\*.json / vejkort.json, eller null
     omraadePunkter: [[lat, lon], ...] bruges til kortets område, når grund er null
   k.tegn(linjer, punkter)  - lægger strækninger og punkter oven på kortet (kan kaldes igen, fx ved nyt valg)
     linjer:  [{pkt: [[lat, lon], ...], valgt: true|false, titel}]
     punkter: [{lat, lon, navn, ende: bool, farve: css-farve|null, navn_altid: bool, titel}]
   k.tilpas([[lat, lon], ...]) - zoomer, så punkterne ses
   Linje, punkter og tekst har samme størrelse på skærmen ved alle zoomniveauer. */
const Vejkort = (() => {
  const W = 640, MARGIN = 140;
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  let nr = 0;
  function omraade(pk) {
    const la = pk.map((p) => p[0]), lo = pk.map((p) => p[1]), lat0 = la.reduce((a, b) => a + b, 0) / la.length;
    const kx = 111320 * Math.cos(lat0 * Math.PI / 180), ky = 110540;
    let s = Math.min(...la) - MARGIN / ky, n = Math.max(...la) + MARGIN / ky, w = Math.min(...lo) - MARGIN / kx, e = Math.max(...lo) + MARGIN / kx;
    const b = (e - w) * kx, h = (n - s) * ky;
    if (b < h * 1.6) { const x = (h * 1.6 - b) / 2 / kx; w -= x; e += x; }
    return [s, w, n, e];
  }
  const BUS = '<rect x="-6" y="-6" width="12" height="12" rx="2.5"/><path d="M-3.5,-3.5 h7 v6 h-7 Z M-3.5,0 h7 M-2,2.5 v2 M2,2.5 v2"/>';
  const SYM = {bump: '<path class="vk-s-bump" d="M-5,3 L0,-5 L5,3 Z"/>', kryds: '<rect class="vk-s-kryds" x="-4" y="-4" width="8" height="8" rx="1"/>',
    stop: `<g class="vk-s-stop">${BUS}</g>`};
  const TEKST = {bump: 'fartdæmper i OSM', kryds: 'fodgængerfelt', stop: 'stoppested'};

  function lav(el, grund, omraadePunkter) {
    const id = 'vk' + (++nr);
    const [s, w, n, e] = grund ? grund.omraade : omraade(omraadePunkter), en = grund ? grund.enhed : 1e-5;
    const kx = 111320 * Math.cos((s + n) / 2 * Math.PI / 180), ky = 110540, SK = W / ((e - w) * kx), H = Math.round((n - s) * ky * SK);
    const X = (lon) => +((lon - w) * kx * SK).toFixed(1), Y = (lat) => +((n - lat) * ky * SK).toFixed(1);
    const U = (dy, dx) => [X(w + dx * en), Y(s + dy * en)];
    const linje = (f) => { const p = []; let y = 0, x = 0; for (let i = 0; i < f.length; i += 2) { y += f[i]; x += f[i + 1]; p.push(U(y, x)); } return p; };
    const d = (p) => 'M' + p.map(([x, y]) => `${x},${y}`).join(' L');
    const fast = (x, y, indhold, kl = '', attr = '') => `<g class="vk-fast ${kl}" data-x="${x}" data-y="${y}"${attr} transform="translate(${x} ${y})">${indhold}</g>`;
    // ---- grundkortet (tegnes én gang)
    let ind = `<rect class="vk-bg" width="${W}" height="${H}"/>`;
    const legende = new Set();
    if (grund) {
      const navne = {}, kl = {1: [], 2: [], 3: [], 4: [], 5: []};
      ind += grund.bygninger.map((b) => `<path class="vk-bygn" d="${d(linje(b))}Z"/>`).join('');
      grund.veje.forEach(([k, navn, f]) => {
        const p = linje(f); kl[k].push(d(p));
        if (navn && k <= 3) {
          const l = p.slice(1).reduce((a, q, i) => a + Math.hypot(q[0] - p[i][0], q[1] - p[i][1]), 0);
          if (!navne[navn] || l > navne[navn][0]) navne[navn] = [l, p[p.length - 1][0] < p[0][0] ? p.slice().reverse() : p];
        }
      });
      [5, 4, 3, 2, 1].forEach((k) => { if (kl[k].length) ind += `<path class="vk-vej vk-k${k}" d="${kl[k].join(' ')}"/>`; });
      Object.entries(navne).sort().forEach(([navn, [l, p]], i) => {
        if (l < navn.length * 6.5 + 20) return;
        ind += `<path id="${id}-v${i}" d="${d(p)}" fill="none"/><text class="vk-vejnavn" dy="-0.35em"><textPath href="#${id}-v${i}" startOffset="50%" text-anchor="middle">${esc(navn)}</textPath></text>`;
      });
      const stop = grund.detaljer.filter((x) => x[0] === 'stop').map(([, , dy, dx]) => U(dy, dx));
      grund.detaljer.forEach(([art, t, dy, dx]) => {
        const [x, y] = U(dy, dx); legende.add(art);
        if (art === 'bump') ind += fast(x, y, `${SYM.bump}<title>Fartdæmper i OSM: ${esc(t)}</title>`, 'vk-detalje');
        else if (art === 'kryds') ind += fast(x, y, `${SYM.kryds}<title>Fodgængerfelt (OSM)</title>`, 'vk-detalje');
        else {
          // hvert stoppested har sit navn; det står på den side, der vender væk fra nærmeste andet stoppested
          const andre = stop.filter(([x2, y2]) => x2 !== x || y2 !== y).sort((a, b) => Math.hypot(a[0] - x, a[1] - y) - Math.hypot(b[0] - x, b[1] - y));
          const side = !andre.length || andre[0][0] <= x ? 1 : -1;
          ind += fast(x, y, `<g class="vk-s-stop">${BUS}<title>Stoppested: ${esc(t)} (OSM)</title></g>`
            + (t ? `<text class="vk-stopnavn" x="${9 * side}" y="3.5" text-anchor="${side === 1 ? 'start' : 'end'}">${esc(t)}</text>` : ''), 'vk-detalje');
        }
      });
    }
    const leg = ['bump', 'kryds', 'stop'].filter((a) => legende.has(a)).map((a) => `<span><svg viewBox="-7 -7 14 14" aria-hidden="true">${SYM[a]}</svg>${TEKST[a]}</span>`).join('');
    el.classList.add('vk');
    el.innerHTML = `<svg class="vk-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Vejkort"><svg class="vk-indre" x="0" y="0" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">`
      + `${ind}<g class="vk-lag"></g></svg><g class="vk-skala"><path d=""/><text x="12" y="${H - 20}" text-anchor="middle"></text></g></svg>`
      + `<div class="vk-knapper"><button type="button" data-z="ind" aria-label="Zoom ind">+</button><button type="button" data-z="ud" aria-label="Zoom ud">−</button>`
      + `<button type="button" data-z="nul">Hele kortet</button><span class="vk-tegn">${leg}${leg ? '<span>(ved zoom)</span>' : ''}</span></div>`
      + `<p class="vk-kilde">${grund ? 'Kortdata © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>-bidragydere, hentet ' + esc(grund.hentet) + '. '
        : 'Intet vejkort (kortdata er ikke hentet); kun punkterne. '}Træk for at flytte; zoom med knapperne, eller klik i kortet og brug musehjulet.</p>`;
    // ---- zoom, træk og fast skærmstørrelse
    const ydre = el.querySelector('.vk-svg'), indre = el.querySelector('.vk-indre'), lag = el.querySelector('.vk-lag');
    const skala = el.querySelector('.vk-skala path'), skt = el.querySelector('.vk-skala text');
    let v = {x: 0, y: 0, w: W, h: H};
    const saet = () => {
      v.w = Math.min(W, Math.max(W / 16, v.w)); v.h = v.w * H / W;
      v.x = Math.min(W - v.w, Math.max(0, v.x)); v.y = Math.min(H - v.h, Math.max(0, v.y));
      indre.setAttribute('viewBox', `${v.x} ${v.y} ${v.w} ${v.h}`);
      const bredde = ydre.getBoundingClientRect().width || W, k = v.w / bredde, kyd = W / bredde;   // brugerenheder pr. skærm-pixel
      ydre.style.setProperty('--k', k); ydre.style.setProperty('--ky', kyd);
      ydre.classList.toggle('zoomet', v.w / W < 0.5);
      ydre.classList.toggle('lille', k > 1.5);            // lille kort (mobil, hele kortet): kun de vigtigste navne
      indre.querySelectorAll('.vk-fast').forEach((g) => g.setAttribute('transform', `translate(${g.dataset.x} ${g.dataset.y}) scale(${k})`));
      // et navn, der ville stikke ud over kortets kant, flyttes til den anden side af punktet
      indre.querySelectorAll('.vk-pkt[data-tb]').forEach((g) => {
        const x = +g.dataset.x, rx = +g.dataset.rx, tb = +g.dataset.tb, alt = rx >= 0 ? -10 - tb : 10;
        const ude = (r0) => x + r0 * k < v.x || x + (r0 + tb) * k > v.x + v.w;
        const brug = ude(rx) && !ude(alt) ? alt : rx;
        g.querySelector('.vk-lbg').setAttribute('x', brug); g.querySelector('.vk-lbl').setAttribute('x', brug + 5);
      });
      const pxPrM = SK * W / v.w / kyd, m = [10, 20, 25, 50, 100, 200, 500, 1000].find((x) => x * pxPrM >= 50) || 1000, L = m * pxPrM * kyd;
      skala.setAttribute('d', `M12,${H - 14} v-5 M12,${H - 14} h${L.toFixed(1)} v-5`);
      skt.setAttribute('x', (12 + L / 2).toFixed(1)); skt.textContent = `${m} m`;
    };
    const pkt = (cx, cy) => { const b = ydre.getBoundingClientRect(); return [v.x + (cx - b.left) / b.width * v.w, v.y + (cy - b.top) / b.height * v.h]; };
    const zoom = (f, px, py) => { const nw = Math.min(W, Math.max(W / 16, v.w * f)), q = nw / v.w; v.x = px - (px - v.x) * q; v.y = py - (py - v.y) * q; v.w = nw; saet(); };
    // musehjulet zoomer først, når man har klikket i kortet (ellers scroller siden som normalt)
    ydre.addEventListener('wheel', (ev) => { if (!ydre.classList.contains('aktiv') && !ev.ctrlKey) return; ev.preventDefault(); const [px, py] = pkt(ev.clientX, ev.clientY); zoom(ev.deltaY < 0 ? 0.8 : 1.25, px, py); }, {passive: false});
    ydre.addEventListener('mouseleave', () => ydre.classList.remove('aktiv'));
    const tryk = new Map();
    ydre.addEventListener('pointerdown', (ev) => { ev.preventDefault(); ydre.classList.add('aktiv'); ydre.setPointerCapture(ev.pointerId); tryk.set(ev.pointerId, [ev.clientX, ev.clientY]); });
    ydre.addEventListener('pointermove', (ev) => {
      if (!tryk.has(ev.pointerId)) return;
      const b = ydre.getBoundingClientRect(), gl = tryk.get(ev.pointerId);
      if (tryk.size === 2) {
        const [a, c] = [...tryk.values()], d0 = Math.hypot(a[0] - c[0], a[1] - c[1]);
        tryk.set(ev.pointerId, [ev.clientX, ev.clientY]);
        const [p, q] = [...tryk.values()], d1 = Math.hypot(p[0] - q[0], p[1] - q[1]);
        const [px, py] = pkt((p[0] + q[0]) / 2, (p[1] + q[1]) / 2); if (d1 > 0) zoom(d0 / d1, px, py); return;
      }
      v.x -= (ev.clientX - gl[0]) / b.width * v.w; v.y -= (ev.clientY - gl[1]) / b.height * v.h; saet();
      tryk.set(ev.pointerId, [ev.clientX, ev.clientY]);
    });
    const slip = (ev) => tryk.delete(ev.pointerId);
    ydre.addEventListener('pointerup', slip); ydre.addEventListener('pointercancel', slip);
    el.querySelectorAll('.vk-knapper button').forEach((b) => b.addEventListener('click', () => {
      if (b.dataset.z === 'nul') { v = {x: 0, y: 0, w: W, h: H}; saet(); return; }
      zoom(b.dataset.z === 'ind' ? 0.7 : 1 / 0.7, v.x + v.w / 2, v.y + v.h / 2);
    }));
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(saet).observe(ydre);

    // ---- lag oven på grundkortet: strækninger og punkter
    function tegn(linjer, punkter) {
      let o = '';
      [...linjer].sort((a, b) => !!a.valgt - !!b.valgt).forEach((l) => {
        if (l.pkt.length > 1) o += `<path class="vk-maalt${l.valgt === false ? ' vk-anden' : ''}" d="${d(l.pkt.map(([la, lo]) => [X(lo), Y(la)]))}">${l.titel ? `<title>${esc(l.titel)}</title>` : ''}</path>`;
      });
      const bokse = [];
      punkter.forEach((p) => {
        const x = X(p.lon), y = Y(p.lat), r = p.ende ? 6 : 4.5;
        const prik = `<circle class="${p.ende ? 'vk-ende' : 'vk-elem'}" r="${r}"${p.farve ? ` style="fill:${p.farve};stroke:var(--vk-papir);stroke-width:2"` : ''}>${p.titel || p.navn ? `<title>${esc(p.titel || p.navn)}</title>` : ''}</circle>`;
        if (!p.navn) { o += fast(x, y, prik, 'vk-pkt'); return; }
        const tb = p.navn.length * 6.6 + 10;
        let b;
        for (const side of [1, -1]) {
          const lx = side === 1 ? x + 10 : x - 10 - tb; b = [lx, y - 9, lx + tb, y + 9];
          if (!bokse.some((q) => !(b[2] < q[0] || b[0] > q[2] || b[3] < q[1] || b[1] > q[3]))) break;
        }
        bokse.push(b);
        const rx = +(b[0] - x).toFixed(1);
        o += fast(x, y, prik + `<rect class="vk-lbg" x="${rx}" y="-9" width="${tb.toFixed(0)}" height="18" rx="3"/><text class="vk-lbl${p.ende ? ' fed' : ''}" x="${rx + 5}" y="4">${esc(p.navn)}</text>`,
          'vk-pkt' + (p.navn_altid ? ' vk-altid' : ''), ` data-rx="${rx}" data-tb="${tb.toFixed(0)}"`);
      });
      lag.innerHTML = o;
      saet();
    }
    function tilpas(pk) {
      if (!pk.length) return;
      const xs = pk.map((p) => X(p[1])), ys = pk.map((p) => Y(p[0])), pad = 40;
      let w2 = Math.max(...xs) - Math.min(...xs) + 2 * pad, h2 = Math.max(...ys) - Math.min(...ys) + 2 * pad;
      w2 = Math.max(w2, h2 * W / H);
      v = {x: (Math.min(...xs) + Math.max(...xs)) / 2 - w2 / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2 - w2 * H / W / 2, w: w2, h: w2 * H / W};
      saet();
    }
    saet();
    return {tegn, tilpas};
  }
  return {lav, omraade};
})();
