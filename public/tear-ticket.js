// TearTicket from React Bits (https://reactbits.dev), ported to plain JS so it
// runs without React or a build step. The geometry, tear simulation, fibres and
// keyboard/reduced-motion handling follow the original source line for line.
// React state becomes data attributes on the root, and the `motion` tilt
// springs are replaced by a small spring integrator with the same constants.
//
// Usage: mountTearTicket(container, { body, stub, ...props })
//   body / stub: HTML strings for the ticket body and the tear-off stub.
// Returns { destroy, setTorn(bool) }.

const TILT_SPRING = { stiffness: 220, damping: 24, mass: 0.6 };
const GRAVITY = 2400;
const ART_INSET = 8;
const ART_SPAN = 0.78;
const RETRACT = 0.17;
const SVG = 'http://www.w3.org/2000/svg';

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const rad = deg => (deg * Math.PI) / 180;
const wrap = a => Math.atan2(Math.sin(a), Math.cos(a));
const noise = seed => {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};
const f = n => n.toFixed(2);

const buildGeometry = (W, H, S, R, holes, hole, notch, rough, vertical) => {
  const main = vertical ? H : W;
  const cross = vertical ? W : H;
  const x = main - S;
  const hr = hole / 2;
  const n = Math.max(1, Math.round(holes));
  const span = cross - 2 * notch;
  const bridge = Math.max(2, (span - n * hole) / (n + 1));
  const random = noise(n * 7919 + Math.round(cross));
  const at = (u, v) => (vertical ? { x: v, y: u } : { x: u, y: v });
  const pt = (u, v) => (vertical ? `${f(v)},${f(u)}` : `${f(u)},${f(v)}`);
  const arc = (r, sweep, u, v) => `A${f(r)},${f(r)} 0 0 ${vertical ? 1 - sweep : sweep} ${pt(u, v)}`;
  const bridges = [];
  for (let i = 0; i <= n; i += 1) {
    const y0 = notch + i * (bridge + hole);
    const y1 = y0 + bridge;
    const steps = Math.max(2, Math.round(bridge / 2.2));
    const pts = [];
    for (let k = 1; k < steps; k += 1) pts.push([x + (random() - 0.5) * 2 * rough, y0 + (bridge * k) / steps]);
    bridges.push({ y0, y1, mid: (y0 + y1) / 2, pts, ...at(x, (y0 + y1) / 2) });
  }
  let body = `M${pt(R, 0)}L${pt(x - notch, 0)}${arc(notch, 0, x, notch)}`;
  bridges.forEach((b, i) => {
    b.pts.forEach(p => {
      body += `L${pt(p[0], p[1])}`;
    });
    body += `L${pt(x, b.y1)}`;
    if (i < n) body += arc(hr, 0, x, b.y1 + hole);
  });
  body += `${arc(notch, 0, x - notch, cross)}L${pt(R, cross)}${arc(R, 1, 0, cross - R)}L${pt(0, R)}${arc(R, 1, R, 0)}Z`;
  let stub = `M${pt(x + notch, 0)}L${pt(main - R, 0)}${arc(R, 1, main, R)}L${pt(main, cross - R)}${arc(R, 1, main - R, cross)}L${pt(x + notch, cross)}${arc(notch, 0, x, cross - notch)}`;
  for (let i = n; i >= 0; i -= 1) {
    const b = bridges[i];
    for (let k = b.pts.length - 1; k >= 0; k -= 1) stub += `L${pt(b.pts[k][0], b.pts[k][1])}`;
    stub += `L${pt(x, b.y0)}`;
    if (i > 0) stub += arc(hr, 0, x, b.y0 - hole);
  }
  stub += `${arc(notch, 0, x + notch, 0)}Z`;
  const ends = [
    { ...at(x, notch), v: notch },
    { ...at(x, cross - notch), v: cross - notch }
  ];
  const bodyOutline = `M${pt(x, cross - notch)}${arc(notch, 0, x - notch, cross)}L${pt(R, cross)}${arc(R, 1, 0, cross - R)}L${pt(0, R)}${arc(R, 1, R, 0)}L${pt(x - notch, 0)}${arc(notch, 0, x, notch)}`;
  const stubOutline = `M${pt(x, notch)}${arc(notch, 0, x + notch, 0)}L${pt(main - R, 0)}${arc(R, 1, main, R)}L${pt(main, cross - R)}${arc(R, 1, main - R, cross)}L${pt(x + notch, cross)}${arc(notch, 0, x, cross - notch)}`;
  return { vertical, cross, body, stub, bridges, ends, bodyOutline, stubOutline };
};

// Critically damped-ish spring standing in for motion's useSpring.
const makeSpring = ({ stiffness, damping, mass }, onChange) => {
  let x = 0, v = 0, target = 0, raf = 0, last = 0;
  const tick = now => {
    const dt = clamp((now - last) / 1000, 0.001, 0.034);
    last = now;
    v += ((-stiffness * (x - target) - damping * v) / mass) * dt;
    x += v * dt;
    if (Math.abs(x - target) < 0.001 && Math.abs(v) < 0.001) { x = target; v = 0; raf = 0; }
    else raf = requestAnimationFrame(tick);
    onChange();
  };
  return {
    get: () => x,
    set(next) {
      target = next;
      if (!raf) { last = performance.now(); raf = requestAnimationFrame(tick); }
    },
    stop() { cancelAnimationFrame(raf); raf = 0; }
  };
};

const el = (tag, className, attrs = {}) => {
  const node = tag === 'svg' || tag === 'path' || tag === 'g' ? document.createElementNS(SVG, tag) : document.createElement(tag);
  if (className) node.setAttribute('class', className);
  Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
  return node;
};

export default function mountTearTicket(container, {
  body: bodyHtml = '',
  stub: stubHtml = '',
  orientation = 'horizontal',
  defaultTorn = false,
  onTear,
  width = 460,
  height = 250,
  stubSize = 150,
  radius = 16,
  holes = 12,
  holeSize = 6,
  notch = 3,
  roughness = 0,
  tearAngle = 30,
  stretch = 30,
  resistance = 0.45,
  rotate = 4,
  tilt = true,
  tiltMax = 9,
  tiltReach = 260,
  parallax = 6,
  perspective = 1000,
  background = '#27272a',
  color = '#f5f5f5',
  border = true,
  borderColor = '',
  borderWidth = 1,
  stubBackground = '',
  recenter = true,
  disabled = false,
  ariaLabel = 'Tear off the stub',
  className = ''
} = {}) {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  const vertical = orientation === 'vertical';
  const geo = buildGeometry(width, height, stubSize, radius, holes, holeSize, notch, roughness, vertical);
  let used = defaultTorn;
  let fit = 1;
  const fibres = [];

  // ---- DOM (mirrors the React tree) ----
  const root = el('div', `tear-ticket${className ? ` ${className}` : ''}`, { 'data-orientation': orientation });
  const vars = {
    '--tt-w': `${width}px`, '--tt-h': `${height}px`, '--tt-stub': `${stubSize}px`,
    '--tt-bg': background, '--tt-stub-bg': stubBackground || background, '--tt-ink': color,
    '--tt-edge': borderColor || `color-mix(in srgb, ${color} 16%, transparent)`, '--tt-edge-w': borderWidth,
    '--tt-parallax': `${parallax}px`,
    '--tt-body-w': `${vertical ? width : width - stubSize}px`, '--tt-body-h': `${vertical ? height - stubSize : height}px`,
    '--tt-inset': `${ART_INSET}px`, '--tt-span': ART_SPAN
  };
  Object.entries(vars).forEach(([k, v]) => root.style.setProperty(k, v));
  const stage = el('div', 'tear-ticket__stage');
  const plane = el('div', 'tear-ticket__plane');
  const bodyPiece = el('div', 'tear-ticket__piece');
  const edge = d => { const s = el('svg', 'tear-ticket__edge', { viewBox: `0 0 ${width} ${height}`, 'aria-hidden': 'true' }); s.append(el('path', '', { d })); return s; };
  if (border) bodyPiece.append(edge(geo.bodyOutline));
  const bodyPaper = el('div', 'tear-ticket__paper');
  bodyPaper.style.clipPath = `path('${geo.body}')`;
  const content = el('div', 'tear-ticket__content');
  content.innerHTML = bodyHtml;
  bodyPaper.append(content);
  bodyPiece.append(bodyPaper);
  const fibreSvg = el('svg', 'tear-ticket__fibres', { 'aria-hidden': 'true' });
  geo.bridges.forEach(() => { const g = el('g'); const a = el('path'); const b = el('path'); g.append(a, b); fibres.push(a, b); fibreSvg.append(g); });
  const stubPiece = el('div', 'tear-ticket__piece tear-ticket__piece--stub', { role: 'button', 'aria-label': ariaLabel });
  if (border) stubPiece.append(edge(geo.stubOutline));
  const stubPaper = el('div', 'tear-ticket__paper tear-ticket__paper--stub');
  stubPaper.style.clipPath = `path('${geo.stub}')`;
  const stubInner = el('div', 'tear-ticket__stub');
  stubInner.innerHTML = stubHtml;
  stubPaper.append(stubInner);
  stubPiece.append(stubPaper);
  plane.append(bodyPiece, fibreSvg, stubPiece);
  stage.append(plane);
  const sr = el('span', 'tear-ticket__sr', { role: 'status' });
  root.append(stage, sr);
  container.replaceChildren(root);

  const syncUsed = () => {
    root.toggleAttribute('data-used', used);
    if (used && recenter) root.setAttribute('data-shift', vertical ? 'y' : 'x'); else root.removeAttribute('data-shift');
    stubPiece.tabIndex = disabled || used ? -1 : 0;
    if (used) stubPiece.setAttribute('aria-hidden', 'true'); else stubPiece.removeAttribute('aria-hidden');
    sr.textContent = used ? 'Used' : '';
  };
  root.toggleAttribute('data-instant', used);
  root.toggleAttribute('data-disabled', disabled);
  if (disabled) stubPiece.setAttribute('aria-disabled', 'true');
  syncUsed();

  // ---- tilt + parallax (motion springs) ----
  const depth = tiltMax > 0 ? parallax / tiltMax : 0;
  const paintPlane = () => {
    const tx = tiltX.get(), ty = tiltY.get();
    plane.style.transform = `perspective(${perspective}px) rotate(${rotate}deg) rotateX(${tx}deg) rotateY(${ty}deg)`;
    if (!reduce) content.style.transform = `translate(${ty * depth * 0.22}px, ${-tx * depth * 0.22}px)`;
  };
  const tiltX = makeSpring(TILT_SPRING, paintPlane);
  const tiltY = makeSpring(TILT_SPRING, paintPlane);
  paintPlane();

  // ---- fit to a narrower parent ----
  const measure = () => {
    fit = Math.min(1, root.clientWidth / width) || 1;
    root.style.setProperty('--tt-fit', fit);
    root.style.height = `${height * fit}px`;
  };
  measure();
  const ro = new ResizeObserver(measure);
  ro.observe(root);

  // ---- simulation ----
  const sim = {
    raf: 0, last: 0, phase: 'idle', id: null, sign: 1, hinge: { x: 0, y: 0 }, hingeV: 0,
    grab: { x: 0, y: 0 }, start: { x: 0, y: 0 }, point: { x: 0, y: 0 }, a0: 0, theta: 0, thetaV: 0,
    sx: 0, sy: 0, vx: 0, vy: 0, spin: 0, pvx: 0, pvy: 0, pt: 0, fade: 1, age: 0, bx: 0, bv: 0,
    snapped: [], snapAt: [], span: []
  };

  const paint = now => {
    const s = sim;
    stubPiece.style.transform = `translate(${s.sx.toFixed(2)}px, ${s.sy.toFixed(2)}px) rotate(${((s.theta * s.sign * 180) / Math.PI).toFixed(3)}deg)`;
    stubPiece.style.opacity = s.fade.toFixed(3);
    const up = geo.vertical;
    bodyPiece.style.transform = `translate${up ? 'Y' : 'X'}(${s.bx.toFixed(2)}px)`;
    const cos = Math.cos(s.theta * s.sign);
    const sin = Math.sin(s.theta * s.sign);
    const lx = up ? 1.6 : 0;
    const ly = up ? 0 : 1.6;
    let busy = false;
    geo.bridges.forEach((b, i) => {
      const dx = b.x - s.hinge.x;
      const dy = b.y - s.hinge.y;
      const tx = s.hinge.x + dx * cos - dy * sin + s.sx;
      const ty = s.hinge.y + dx * sin + dy * cos + s.sy;
      const ox = b.x + (up ? 0 : s.bx);
      const oy = b.y + (up ? s.bx : 0);
      const gx = tx - ox;
      const gy = ty - oy;
      const gap = Math.hypot(gx, gy);
      const near = fibres[i * 2];
      const far = fibres[i * 2 + 1];
      const live = s.phase !== 'idle' && !reduce;
      if (!s.snapped[i]) {
        if (!live || gap < 0.35) { near.style.opacity = '0'; far.style.opacity = '0'; return; }
        const k = clamp(gap / stretch, 0, 1);
        const sag = gap * 0.18;
        const w = (1.7 - 1.15 * k).toFixed(2);
        const sx = (up ? sag : 0) + gx / 2;
        const sy = (up ? 0 : sag) + gy / 2;
        near.setAttribute('d', `M${f(ox - lx)},${f(oy - ly)}Q${f(ox - lx + sx)},${f(oy - ly + sy)} ${f(tx - lx)},${f(ty - ly)}`);
        far.setAttribute('d', `M${f(ox + lx)},${f(oy + ly)}Q${f(ox + lx + gx - sx)},${f(oy + ly + gy - sy)} ${f(tx + lx)},${f(ty + ly)}`);
        near.style.strokeWidth = w; far.style.strokeWidth = w;
        near.style.opacity = '1'; far.style.opacity = '1';
        s.span[i] = gap;
        return;
      }
      const t = (now - s.snapAt[i]) / 1000 / RETRACT;
      if (!live || t >= 1 || !s.snapAt[i]) { near.style.opacity = '0'; far.style.opacity = '0'; return; }
      busy = true;
      const left = (1 - t) * (1 - t);
      const len = (s.span[i] || stretch) * 0.5 * left;
      const ux = gap > 0.01 ? gx / gap : 1;
      const uy = gap > 0.01 ? gy / gap : 0;
      near.setAttribute('d', `M${f(ox)},${f(oy)}L${f(ox + ux * len)},${f(oy + uy * len)}`);
      far.setAttribute('d', `M${f(tx)},${f(ty)}L${f(tx - ux * len)},${f(ty - uy * len)}`);
      near.style.strokeWidth = '0.9'; far.style.strokeWidth = '0.9';
      near.style.opacity = left.toFixed(2); far.style.opacity = left.toFixed(2);
    });
    return busy;
  };

  const finish = () => {
    stubPiece.style.visibility = 'hidden';
    used = true;
    syncUsed();
    onTear?.();
  };

  const step = now => {
    const s = sim;
    const dt = clamp((now - s.last) / 1000, 0.001, 0.034);
    s.last = now;
    const limit = rad(tearAngle);
    if (s.phase === 'held') {
      const count = geo.bridges.length;
      let intact = 0;
      for (let i = 0; i < count; i += 1) if (!s.snapped[i]) intact += 1;
      const hold = count ? intact / count : 0;
      const follow = 0.92 * (1 - clamp(resistance, 0, 0.95) * hold);
      const a = Math.atan2(s.point.y - s.hinge.y, s.point.x - s.hinge.x);
      const want = clamp(wrap(a - s.a0) * s.sign * follow, 0, limit + 0.1);
      s.theta += (want - s.theta) * (1 - Math.exp(-dt / 0.035));
      const up = geo.vertical;
      const away = clamp(((up ? s.point.y - s.start.y : s.point.x - s.start.x) || 0) * 0.05, -2, 4);
      const side = clamp(((up ? s.point.x - s.start.x : s.point.y - s.start.y) || 0) * 0.05, -3, 3);
      const px = up ? side : away;
      const py = up ? away : side;
      s.sx += (px - s.sx) * (1 - Math.exp(-dt / 0.05));
      s.sy += (py - s.sy) * (1 - Math.exp(-dt / 0.05));
      const slack = Math.hypot(s.sx, s.sy);
      let left = 0;
      geo.bridges.forEach((b, i) => {
        if (s.snapped[i]) return;
        const d = Math.abs(b.mid - s.hingeV);
        if (2 * d * Math.sin(s.theta / 2) + slack > stretch || s.theta >= limit) {
          s.snapped[i] = true;
          s.snapAt[i] = now;
          s.bv -= 560 / geo.bridges.length;
        } else left += 1;
      });
      if (left === 0) { s.phase = 'free'; s.bv -= 150; }
    } else if (s.phase === 'free') {
      const cos = Math.cos(s.theta * s.sign);
      const sin = Math.sin(s.theta * s.sign);
      const gx = s.grab.x - s.hinge.x;
      const gy = s.grab.y - s.hinge.y;
      const wx = s.point.x - s.hinge.x - (gx * cos - gy * sin);
      const wy = s.point.y - s.hinge.y - (gx * sin + gy * cos);
      s.sx += (wx - s.sx) * (1 - Math.exp(-dt / 0.045));
      s.sy += (wy - s.sy) * (1 - Math.exp(-dt / 0.045));
      const hang = limit * 0.55 + clamp(s.pvx * 0.0009 * s.sign, -0.3, 0.3);
      s.theta += (hang - s.theta) * (1 - Math.exp(-dt / 0.12));
    } else if (s.phase === 'drop') {
      s.age += dt;
      s.vy += GRAVITY * dt;
      s.sx += s.vx * dt;
      s.sy += s.vy * dt;
      s.theta += s.spin * dt;
      if (s.age > 0.16) s.fade = clamp(1 - (s.age - 0.16) / 0.42, 0, 1);
      if (s.fade <= 0) { s.phase = 'idle'; finish(); }
    } else if (s.phase === 'return') {
      s.thetaV += (-300 * s.theta - 24 * s.thetaV) * dt;
      s.theta += s.thetaV * dt;
      s.sx += (0 - s.sx) * (1 - Math.exp(-dt / 0.07));
      s.sy += (0 - s.sy) * (1 - Math.exp(-dt / 0.07));
      if (Math.abs(s.theta) < 0.0008 && Math.abs(s.thetaV) < 0.01 && Math.hypot(s.sx, s.sy) < 0.05) {
        s.theta = 0; s.thetaV = 0; s.sx = 0; s.sy = 0; s.phase = 'idle';
      }
    }
    s.bv += (-520 * s.bx - 30 * s.bv) * dt;
    s.bx += s.bv * dt;
    const busy = paint(now);
    const moving = Math.abs(s.bx) > 0.02 || Math.abs(s.bv) > 0.5;
    if (s.phase !== 'idle' || moving || busy) s.raf = requestAnimationFrame(step);
    else { s.bx = 0; s.bv = 0; paint(now); s.raf = 0; }
  };
  const run = () => {
    if (sim.raf) return;
    sim.last = performance.now();
    sim.raf = requestAnimationFrame(step);
  };
  const reset = () => {
    cancelAnimationFrame(sim.raf);
    Object.assign(sim, { raf: 0, phase: 'idle', id: null, theta: 0, thetaV: 0, sx: 0, sy: 0, fade: 1, age: 0, bx: 0, bv: 0 });
    sim.snapped = []; sim.snapAt = []; sim.span = [];
    stubPiece.style.visibility = '';
    paint(performance.now());
  };
  if (used) stubPiece.style.visibility = 'hidden'; else reset();

  const local = e => {
    const r = stage.getBoundingClientRect();
    const k = r.width / width || 1;
    return { x: (e.clientX - r.left) / k, y: (e.clientY - r.top) / k };
  };
  const setGrabbing = on => root.toggleAttribute('data-grabbing', on);
  const tearNow = () => {
    cancelAnimationFrame(sim.raf);
    sim.raf = 0;
    sim.phase = 'idle';
    root.setAttribute('data-instant', '');
    finish();
  };
  stubPiece.addEventListener('pointerdown', e => {
    const s = sim;
    if (disabled || used || e.button !== 0 || s.id !== null || s.phase === 'drop') return;
    try { stubPiece.setPointerCapture(e.pointerId); } catch {}
    const p = local(e);
    s.id = e.pointerId; s.start = p; s.point = p; s.pt = performance.now(); s.pvx = 0; s.pvy = 0;
    if (s.theta < 0.01) {
      const far = (geo.vertical ? p.x : p.y) < geo.cross / 2;
      const end = geo.ends[far ? 1 : 0];
      s.sign = (far ? 1 : -1) * (geo.vertical ? -1 : 1);
      s.hinge = { x: end.x, y: end.y };
      s.hingeV = end.v;
      stubPiece.style.transformOrigin = `${s.hinge.x}px ${s.hinge.y}px`;
    }
    const cos = Math.cos(-s.theta * s.sign);
    const sin = Math.sin(-s.theta * s.sign);
    const ux = p.x - s.sx - s.hinge.x;
    const uy = p.y - s.sy - s.hinge.y;
    s.grab = { x: s.hinge.x + ux * cos - uy * sin, y: s.hinge.y + ux * sin + uy * cos };
    s.a0 = Math.atan2(s.grab.y - s.hinge.y, s.grab.x - s.hinge.x) - (s.theta * s.sign) / 0.92;
    s.phase = 'held'; s.thetaV = 0;
    tiltX.set(0); tiltY.set(0);
    setGrabbing(true);
    run();
  });
  stubPiece.addEventListener('pointermove', e => {
    const s = sim;
    if (s.id !== e.pointerId) return;
    const p = local(e);
    const now = performance.now();
    const dt = Math.max(0.004, (now - s.pt) / 1000);
    s.pvx += ((p.x - s.point.x) / dt - s.pvx) * 0.35;
    s.pvy += ((p.y - s.point.y) / dt - s.pvy) * 0.35;
    s.pt = now; s.point = p;
    if (reduce && Math.hypot(p.x - s.start.x, p.y - s.start.y) > 28) { s.id = null; setGrabbing(false); tearNow(); }
  });
  const up = e => {
    const s = sim;
    if (s.id !== e.pointerId) return;
    s.id = null;
    try { if (stubPiece.hasPointerCapture(e.pointerId)) stubPiece.releasePointerCapture(e.pointerId); } catch {}
    setGrabbing(false);
    if (s.phase === 'free') {
      const still = performance.now() - s.pt > 80;
      s.vx = still ? 0 : clamp(s.pvx, -1600, 1600);
      s.vy = still ? 0 : clamp(s.pvy, -1600, 1200);
      s.spin = clamp(s.vx * 0.004, -6, 6) + 1.2 * s.sign;
      s.age = 0; s.phase = 'drop';
    } else if (s.phase === 'held') s.phase = 'return';
    run();
  };
  stubPiece.addEventListener('pointerup', up);
  stubPiece.addEventListener('pointercancel', up);
  stubPiece.addEventListener('lostpointercapture', up);
  stubPiece.addEventListener('keydown', e => {
    if (disabled || used || (e.key !== 'Enter' && e.key !== ' ')) return;
    e.preventDefault();
    if (!e.repeat) tearNow();
  });
  stubPiece.addEventListener('dragstart', e => e.preventDefault());

  const onMove = e => {
    if (!root.isConnected) { destroy(); return; }
    if (e.pointerType === 'touch' || sim.id !== null) return;
    const r = root.getBoundingClientRect();
    const nx = clamp((e.clientX - (r.left + r.width / 2)) / (r.width / 2 + tiltReach), -1, 1);
    const ny = clamp((e.clientY - (r.top + r.height / 2)) / (r.height / 2 + tiltReach), -1, 1);
    tiltY.set(nx * tiltMax);
    tiltX.set(-ny * tiltMax);
  };
  const tiltOn = tilt && !reduce && !disabled;
  if (tiltOn) window.addEventListener('pointermove', onMove);

  function destroy() {
    cancelAnimationFrame(sim.raf);
    tiltX.stop(); tiltY.stop();
    ro.disconnect();
    if (tiltOn) window.removeEventListener('pointermove', onMove);
  }
  return {
    destroy,
    setTorn(next) {
      if (next === used) return;
      if (next) { tearNow(); return; }
      used = false;
      root.removeAttribute('data-instant');
      syncUsed();
      reset();
    }
  };
}
