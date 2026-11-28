// Confetti floor for the home hero: a dense blanket of paper strips, chips and
// stars in the logo's colours lies over the headline like confetti on a GA pit
// floor after a show. Move the cursor (or swipe a finger) through it to sweep pieces aside.
//
// Canvas 2D with pre-rendered sprites; the loop sleeps whenever nothing moves.
// Usage: mountConfettiFloor(canvas, { focus, avoid, blockedBy }) -> cleanup()
//   focus: () => DOMRect, the area to pile confetti around (the headline)
//   avoid: () => DOMRect[], boxes to keep clear at first (description, buttons)
//   blockedBy: (x, y, radius) => bool, canvas-local test for exact letter shapes to keep clear at first

// Pinks, blues, purples and mint from the logo. No orange or yellow.
const PALETTE = [
  ['#ffb3e3', 20], ['#ff9fd6', 12],   // pinks
  ['#9ed9ff', 18], ['#b5c7ff', 10],   // baby blue, periwinkle
  ['#cdb4ff', 14], ['#e2b8ff', 9],    // lavender, lilac
  ['#a8ecd0', 12], ['#c2f5e1', 5]     // mint, pale mint
];
const COLORS = PALETTE.map(([c]) => c);
const COLOR_BAG = PALETTE.flatMap(([c, w]) => Array(w).fill(c));
const KINDS = ['star', 'star', 'rect', 'rect', 'rect'];   // ~40% stars, ~60% cut-paper rectangles
const TONES = [0, 0.14];                                   // true pastel / a touch lighter (never darker: no muddy browns)
const SPRITE = 140; // px, drawn once per kind/colour/face at device resolution
const FRICTION = 6.5; // how fast sliding pieces stop (per second, exponential)
const SPIN_FRICTION = 4.5;
const FLIP_FRICTION = 3.2;
const MAX_SPEED = 2600;

const rand = (a, b) => a + Math.random() * (b - a);
const pick = list => list[(Math.random() * list.length) | 0];

// Mix a colour toward white by `amount` (0 = unchanged, 1 = white).
function lighten(hex, amount) {
  const n = parseInt(hex.slice(1), 16), c = v => Math.round(v + (255 - v) * amount);
  const r = c((n >> 16) & 255), g = c((n >> 8) & 255), b = c(n & 255);
  return `rgb(${r},${g},${b})`;
}

function tracePath(ctx, kind, s) {
  ctx.beginPath();
  if (kind === 'star') {
    for (let i = 0; i < 10; i += 1) {
      const r = i % 2 ? s * 0.22 : s * 0.48, a = -Math.PI / 2 + (i * Math.PI) / 5;
      ctx[i ? 'lineTo' : 'moveTo'](Math.cos(a) * r, Math.sin(a) * r);
    }
    ctx.closePath();
  } else {
    // a full square of paper; each piece stretches it into a strip or a chip
    ctx.roundRect(-s / 2, -s / 2, s, s, s * 0.06);
  }
}

function makeSprites(dpr) {
  const size = Math.ceil(SPRITE * dpr);
  const sprites = {};
  for (const kind of new Set(KINDS)) {
    for (const color of COLORS) {
     for (const tone of TONES) {
      for (const face of ['front', 'back']) {
        const c = document.createElement('canvas');
        c.width = c.height = size;
        const g = c.getContext('2d');
        g.translate(size / 2, size / 2);
        g.scale(dpr, dpr);
        tracePath(g, kind, SPRITE * 0.92);
        g.fillStyle = lighten(color, face === 'front' ? tone : tone + 0.32);   // the back of the paper is paler
        g.fill();
        if (kind === 'star') { g.lineJoin = 'round'; g.lineWidth = 2.4; g.strokeStyle = g.fillStyle; g.stroke(); }
        sprites[`${kind}|${color}|${tone}|${face}`] = c;
      }
     }
    }
  }
  return sprites;
}

export default function mountConfettiFloor(canvas, { focus, avoid, blockedBy, scale = 1 } = {}) {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  const ctx = canvas.getContext('2d');
  let dpr = Math.min(window.devicePixelRatio || 1, 2);
  let sprites = makeSprites(dpr);
  let W = 0, H = 0, raf = 0, last = 0, introStart = 0, introDone = reduce;
  let pieces = [];
  const pointer = { x: 0, y: 0, t: 0, active: false };

  // Mostly small-to-medium pieces with the odd oversized one, like real cannon confetti.
  const sizeFor = kind => scale * (Math.random() < 0.06 ? rand(86, 124) : kind === 'star' ? rand(34, 74) : rand(32, 68));
  const aspectFor = kind => (kind === 'star' ? 1 : Math.random() < 0.55 ? rand(0.2, 0.42) : rand(0.55, 1));

  function layout() {
    const r = canvas.getBoundingClientRect();
    W = r.width; H = r.height;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    const f = focus?.();
    const box = f ? { x: f.left - r.left, y: f.top - r.top, w: f.width, h: f.height } : { x: W * 0.1, y: H * 0.25, w: W * 0.8, h: H * 0.4 };
    const pad = Math.min(60, box.w * 0.05);
    const count = Math.round(Math.min(380, Math.max(70, (W * H) / 5600 + (box.w * box.h) / 2800)));
    const clear = (avoid?.() || []).map(a => ({ x: a.left - r.left - 18, y: a.top - r.top - 14, w: a.width + 36, h: a.height + 28 }));
    const letters = blockedBy?.() || null;
    const blocked = (x, y, m) => clear.some(a => x > a.x - m && x < a.x + a.w + m && y > a.y - m && y < a.y + a.h + m) || (letters ? letters(x, y, m) : false);
    // Spread pieces evenly: each grid cell holds at most a couple of pieces at the start.
    const CELL = 64, CAP = 2, cells = new Map();
    const cellKey = (x, y) => ((x / CELL) | 0) + ',' + ((y / CELL) | 0);
    const crowded = (x, y) => (cells.get(cellKey(x, y)) || 0) >= CAP;
    pieces = [];
    for (let i = 0; i < count; i += 1) {
      const kind = pick(KINDS), onText = i < count * 0.5, s = sizeFor(kind), m = s * 0.55;
      let tx = 0, ty = 0;
      for (let tries = 0; tries < (onText ? 24 : 8); tries += 1) {
        tx = onText ? rand(box.x - pad, box.x + box.w + pad) : rand(0, W);
        ty = onText ? rand(box.y - pad * 0.6, box.y + box.h + pad * 0.6) : rand(0, H);
        if (!blocked(tx, ty, m) && !crowded(tx, ty)) break;
      }
      if (blocked(tx, ty, m) || crowded(tx, ty)) continue;
      cells.set(cellKey(tx, ty), (cells.get(cellKey(tx, ty)) || 0) + 1);
      pieces.push({
        kind, color: pick(COLOR_BAG), tone: pick(TONES), s, ar: aspectFor(kind),
        x: tx, y: ty, vx: 0, vy: 0,
        a0: rand(0, Math.PI * 2), f0: rand(-0.9, 0.9), va: 0, vf: 0,
        // intro: fall from above the hero and flutter down onto the floor
        tx, ty, sy: ty - H - rand(40, 260), delay: rand(0, 650), dur: rand(850, 1350),
        sway: rand(14, 42), phase: rand(0, Math.PI * 2), spin: rand(-7, 7), flips: rand(4, 11)
      });
    }
    for (const p of pieces) { p.a = p.a0; p.f = p.f0; if (!reduce) { p.y = p.sy; } }
    if (reduce) introDone = true;
  }

  function draw() {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const p of pieces) {
      const sy = Math.cos(p.f), face = sy < 0 ? 'back' : 'front', k = Math.max(0.24, Math.abs(sy));
      const ca = Math.cos(p.a) * dpr, sa = Math.sin(p.a) * dpr;
      ctx.setTransform(ca, sa, -sa * k, ca * k, p.x * dpr, p.y * dpr);
      const h = p.s * p.ar;
      ctx.drawImage(sprites[`${p.kind}|${p.color}|${p.tone}|${face}`], -p.s / 2, -h / 2, p.s, h);
    }
  }

  function step(now) {
    const dt = Math.min(0.034, Math.max(0.001, (now - last) / 1000));
    last = now;
    let moving = false;
    if (!introDone) {
      let landed = 0;
      const t = now - introStart;
      for (const p of pieces) {
        const q = Math.min(1, Math.max(0, (t - p.delay) / p.dur));
        const e = 1 - Math.pow(1 - q, 3), rest = 1 - e;
        p.x = p.tx + Math.sin(q * Math.PI * 2.2 + p.phase) * p.sway * rest;
        p.y = p.sy + (p.ty - p.sy) * e;
        p.a = p.a0 + p.spin * rest * rest;   // tumbles while falling, eases to its resting angle
        p.f = p.f0 + p.flips * rest * rest;  // flips over and over, settling face-up or face-down
        if (q >= 1) landed += 1;
      }
      introDone = landed === pieces.length;
      moving = true;
    } else {
      const k = Math.exp(-FRICTION * dt), ks = Math.exp(-SPIN_FRICTION * dt), kf = Math.exp(-FLIP_FRICTION * dt);
      for (const p of pieces) {
        if (!p.vx && !p.vy && !p.va && !p.vf) continue;
        p.x += p.vx * dt; p.y += p.vy * dt; p.a += p.va * dt; p.f += p.vf * dt;
        p.vx *= k; p.vy *= k; p.va *= ks; p.vf *= kf;
        const m = p.s * 0.3;
        if (p.x < m) { p.x = m; p.vx = Math.abs(p.vx) * 0.35; } else if (p.x > W - m) { p.x = W - m; p.vx = -Math.abs(p.vx) * 0.35; }
        if (p.y < m) { p.y = m; p.vy = Math.abs(p.vy) * 0.35; } else if (p.y > H - m) { p.y = H - m; p.vy = -Math.abs(p.vy) * 0.35; }
        if (Math.abs(p.vx) + Math.abs(p.vy) < 1.5 && Math.abs(p.va) < 0.05 && Math.abs(p.vf) < 0.05) { p.vx = p.vy = p.va = p.vf = 0; }
        else moving = true;
      }
    }
    draw();
    raf = moving ? requestAnimationFrame(step) : 0;
  }

  function wake() {
    if (raf) return;
    last = performance.now();
    raf = requestAnimationFrame(step);
  }

  // Sweep: everything near the path of the cursor gets pushed along with it.
  function sweep(x, y, radius) {
    const now = performance.now();
    if (!pointer.active || now - pointer.t > 120) { Object.assign(pointer, { x, y, t: now, active: true }); return; }
    const dt = Math.max(0.008, (now - pointer.t) / 1000);
    const dx = x - pointer.x, dy = y - pointer.y, len = Math.hypot(dx, dy);
    Object.assign(pointer, { x, y, t: now });
    if (len < 0.5 || !introDone) return;
    const cvx = dx / dt, cvy = dy / dt, speed = Math.min(MAX_SPEED, Math.hypot(cvx, cvy));
    const ux = dx / len, uy = dy / len;
    const minX = Math.min(x, x - dx) - radius, maxX = Math.max(x, x - dx) + radius;
    const minY = Math.min(y, y - dy) - radius, maxY = Math.max(y, y - dy) + radius;
    let hit = false;
    for (const p of pieces) {
      if (p.x < minX || p.x > maxX || p.y < minY || p.y > maxY) continue;
      // distance from the piece to the segment the cursor just travelled
      const t = Math.max(0, Math.min(1, ((p.x - (x - dx)) * ux + (p.y - (y - dy)) * uy) / len));
      const nx = x - dx + ux * len * t, ny = y - dy + uy * len * t;
      const ox = p.x - nx, oy = p.y - ny, d = Math.hypot(ox, oy);
      if (d > radius) continue;
      const w = (1 - d / radius) ** 2, push = Math.min(1, speed / 900);
      const rx = d > 0.01 ? ox / d : rand(-1, 1), ry = d > 0.01 ? oy / d : rand(-1, 1);
      p.vx += (ux * speed * 0.85 + rx * 420) * w * (0.35 + push * 0.65) * rand(0.75, 1.15);
      p.vy += (uy * speed * 0.85 + ry * 420) * w * (0.35 + push * 0.65) * rand(0.75, 1.15);
      const v = Math.hypot(p.vx, p.vy);
      if (v > MAX_SPEED) { p.vx *= MAX_SPEED / v; p.vy *= MAX_SPEED / v; }
      if (!reduce) { p.va += rand(-1, 1) * 9 * w * (0.3 + push); p.vf += rand(4, 14) * w * (0.3 + push) * (Math.random() < 0.5 ? -1 : 1); }
      hit = true;
    }
    if (hit) wake();
  }

  const local = (clientX, clientY) => { const r = canvas.getBoundingClientRect(); return [clientX - r.left, clientY - r.top, r]; };
  const onPointer = e => {
    if (e.pointerType === 'touch') return;
    const [x, y, r] = local(e.clientX, e.clientY);
    if (x < -40 || y < -40 || x > r.width + 40 || y > r.height + 40) { pointer.active = false; return; }
    sweep(x, y, 130);
  };
  const onTouch = e => { const t = e.touches[0]; if (!t) return; const [x, y] = local(t.clientX, t.clientY); sweep(x, y, 112); };
  const onTouchEnd = () => { pointer.active = false; };
  const host = canvas.parentElement;
  window.addEventListener('pointermove', onPointer, { passive: true });
  host.addEventListener('touchstart', onTouch, { passive: true });
  host.addEventListener('touchmove', onTouch, { passive: true });
  host.addEventListener('touchend', onTouchEnd, { passive: true });

  // Keep pieces where they are (proportionally) when the hero changes size.
  let lastW = 0, lastH = 0;
  const ro = new ResizeObserver(() => {
    const r = canvas.getBoundingClientRect();
    if (!lastW) { lastW = r.width; lastH = r.height; return; }
    if (Math.abs(r.width - lastW) < 1 && Math.abs(r.height - lastH) < 1) return;
    const sx = r.width / lastW, sy = r.height / lastH;
    lastW = r.width; lastH = r.height; W = r.width; H = r.height;
    const nd = Math.min(window.devicePixelRatio || 1, 2);
    if (nd !== dpr) { dpr = nd; sprites = makeSprites(dpr); }
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    for (const p of pieces) { p.x *= sx; p.y *= sy; p.tx *= sx; p.ty *= sy; }
    if (!raf) draw();
  });

  layout();
  lastW = W; lastH = H;
  ro.observe(canvas);
  introStart = performance.now();
  if (introDone) draw(); else wake();

  return () => {
    cancelAnimationFrame(raf);
    ro.disconnect();
    window.removeEventListener('pointermove', onPointer);
    host.removeEventListener('touchstart', onTouch);
    host.removeEventListener('touchmove', onTouch);
    host.removeEventListener('touchend', onTouchEnd);
  };
}
