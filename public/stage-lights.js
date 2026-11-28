// Stage beams for the home hero: soft cones of coloured light from above, slowly
// sweeping through haze, drawn on a canvas beneath the confetti and the headline.
// Each beam is pre-rendered once as a soft sprite; frames only rotate it. Runs at
// ~30fps (the motion is slow), pauses offscreen or in a hidden tab, and holds
// still under reduced motion.
// Usage: mountStageLights(canvas) -> cleanup()

const COLORS = ['#ff9fd6', '#9ed9ff', '#cdb4ff', '#a8ecd0', '#b5c7ff', '#e2b8ff'];
const TAU = Math.PI * 2;
// The beams are soft by design, so they render at reduced resolution; phones get more pixels
// because their 3x screens stretch a 0.4x canvas too far.
const scaleFor = w => (w < 761 ? 0.8 : 0.4);

// Built per pixel rather than with ctx.filter blur, which iOS Safari ignores (that left hard,
// jagged edges once the low-res canvas was stretched). A little noise dithers away banding.
function beamSprite(b) {
  const w = 256, h = 512, c = document.createElement('canvas');
  c.width = w; c.height = h;
  const g = c.getContext('2d'), half = Math.tan(b.spread) * h * 0.5;
  const n = parseInt(b.color.slice(1), 16), R = (n >> 16) & 255, G = (n >> 8) & 255, B = n & 255;
  const img = g.createImageData(w, h), d = img.data;
  for (let y = 0; y < h; y++) {
    const v = y / h;
    const fade = v < 0.45 ? 1.6 + (0.55 - 1.6) * (v / 0.45) : 0.55 * (1 - (v - 0.45) / 0.55);
    const rowA = b.alpha * fade * Math.min(1, v * 12 + 0.25); // soft start at the lamp
    const hw = 4 + (half - 4) * v, soft = 8 + 20 * v;
    for (let x = 0; x < w; x++) {
      let e = (hw + soft - Math.abs(x + 0.5 - w / 2)) / (2 * soft);
      e = e <= 0 ? 0 : e >= 1 ? 1 : e * e * (3 - 2 * e);
      const i = (y * w + x) * 4;
      d[i] = R; d[i + 1] = G; d[i + 2] = B;
      d[i + 3] = e ? Math.max(0, Math.min(255, rowA * e * 255 + Math.random() - 0.5)) : 0;
    }
  }
  g.putImageData(img, 0, 0);
  return c;
}

export default function mountStageLights(canvas) {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  const ctx = canvas.getContext('2d');
  let W = 0, H = 0, raf = 0, visible = true, lastDraw = 0;
  const start = performance.now();

  const rand = (a, b) => a + Math.random() * (b - a);
  const beams = Array.from({ length: 5 }, (_, i) => {
    const b = { x: (i + 0.5) / 5, color: COLORS[i % COLORS.length], spread: rand(0.27, 0.36), swing: rand(0.12, 0.22), speed: rand(0.11, 0.18), phase: rand(0, TAU), alpha: rand(0.14, 0.21) }; // wide cones; swing ≈ 7–13°
    b.sprite = beamSprite(b);
    return b;
  });

  function size() {
    const r = canvas.getBoundingClientRect();
    W = r.width; H = r.height;
    const SCALE = scaleFor(W);
    canvas.width = Math.max(1, Math.round(W * SCALE));
    canvas.height = Math.max(1, Math.round(H * SCALE));
    ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
  }

  function draw(t) {
    ctx.clearRect(0, 0, W, H);
    ctx.globalCompositeOperation = 'lighter';
    for (const b of beams) {
      const angle = Math.sin(t * b.speed + b.phase) * b.swing, len = H * 1.35, width = len * 0.5;
      ctx.save(); ctx.translate(b.x * W, -H * 0.08); ctx.rotate(-angle);
      ctx.drawImage(b.sprite, -width / 2, 0, width, len);
      ctx.restore();
    }
    ctx.globalCompositeOperation = 'source-over';
  }

  function frame(now) {
    const running = !reduce && visible && !document.hidden;
    if (running && now - lastDraw >= 30) { lastDraw = now; draw((now - start) / 1000); }
    raf = running ? requestAnimationFrame(frame) : 0;
  }
  const wake = () => { if (!raf && !reduce && visible && !document.hidden) raf = requestAnimationFrame(frame); };

  const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; wake(); });
  io.observe(canvas);
  const onVis = () => wake();
  document.addEventListener('visibilitychange', onVis);
  const ro = new ResizeObserver(() => { size(); draw(reduce ? 4 : (performance.now() - start) / 1000); });
  ro.observe(canvas);
  size();
  draw(reduce ? 4 : 0);
  wake();

  return () => { cancelAnimationFrame(raf); io.disconnect(); ro.disconnect(); document.removeEventListener('visibilitychange', onVis); };
}
