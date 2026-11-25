// FlexCarousel's lens shader, using the supplied React Bits GLSL in the
// prototype's existing vanilla-JS shell (so the rest of the site stays intact).
const lensVertex = `#version 300 es
in vec2 position;
void main() { gl_Position = vec4(position, 0.0, 1.0); }
`;

const lensFragment = `#version 300 es
precision highp float;
uniform sampler2D tScene;
uniform vec2 uResolution;
uniform float uDpr;
uniform vec2 uCenter;
uniform vec2 uHalf;
uniform float uAngle;
uniform float uExponent;
uniform float uInner;
uniform float uOuter;
uniform float uFlow;
uniform float uCurl;
uniform float uDispersion;
uniform float uStrength;
uniform float uSceneAlpha;
out vec4 fragColor;
void main() {
  vec2 frag = gl_FragCoord.xy / uDpr;
  vec2 uv = frag / uResolution;
  vec2 rel = frag - vec2(uCenter.x, uResolution.y - uCenter.y);
  float ca = cos(uAngle);
  float sa = sin(uAngle);
  vec2 local = vec2(ca * rel.x + sa * rel.y, -sa * rel.x + ca * rel.y);
  vec2 k = max(abs(local) / uHalf, vec2(1e-5));
  float nd = pow(pow(k.x, uExponent) + pow(k.y, uExponent), 1.0 / uExponent);
  vec2 grad = pow(k, vec2(uExponent - 1.0)) * sign(local) / uHalf * pow(nd, 1.0 - uExponent);
  float glen = max(length(grad), 1e-6);
  float edge = (nd - 1.0) / glen;
  vec2 outward = grad / glen;
  vec2 normal = vec2(ca * outward.x - sa * outward.y, sa * outward.x + ca * outward.y);
  vec2 along = vec2(-normal.y, normal.x);
  float t = clamp((edge + uInner) / (uInner + uOuter), 0.0, 1.0);
  float ramp = t * t * t * (t * (t * 6.0 - 15.0) + 10.0);
  float slope = 16.0 * t * t * (1.0 - t) * (1.0 - t);
  float reachX = rel.x / (uResolution.x * 0.5);
  float side = smoothstep(0.02, 0.3, abs(reachX)) * (uCurl == 0.0 ? sign(reachX) : uCurl);
  float lift = ramp * side * uFlow * uStrength;
  vec2 swirl = along * along.y * side * slope * uFlow * uStrength * 0.35;
  vec2 drift = vec2(0.0, -lift) - swirl;
  vec2 shifted = uv + drift / uResolution;
  vec2 texels = uResolution * uDpr;
  vec2 gx = dFdx(shifted);
  vec2 gy = dFdy(shifted);
  gx *= min(1.0, 3.0 / max(length(gx * texels), 1e-4));
  gy *= min(1.0, 3.0 / max(length(gy * texels), 1e-4));
  vec4 color = textureGrad(tScene, shifted, gx, gy);
  vec2 spread = vec2(0.0, side * slope * uFlow * uStrength) / uResolution * uDispersion;
  float spreadPx = length(spread * texels);
  if (color.a > 0.002 && spreadPx > 0.25) {
    vec3 base = color.rgb / color.a;
    vec3 sumColor = vec3(0.0);
    vec3 sumWeight = vec3(0.0);
    for (int i = 0; i < 12; i++) {
      float s = (float(i) + 0.5) / 12.0;
      vec4 c = textureGrad(tScene, shifted + spread * (s - 0.5), gx, gy);
      vec3 w = max(1.0 - abs(vec3(s) - vec3(0.15, 0.5, 0.85)) * 2.6, 0.0) * c.a;
      sumColor += c.rgb * (w / max(c.a, 0.002));
      sumWeight += w;
    }
    vec3 split = mix(base, sumColor / max(sumWeight, vec3(1e-4)), clamp(sumWeight * 2.0, 0.0, 1.0));
    color.rgb = mix(color.rgb, clamp(split, 0.0, 1.0) * color.a, smoothstep(0.25, 1.5, spreadPx));
  }
  fragColor = color * uSceneAlpha;
}
`;

export default function mountFlexCarousel({ container, items, config = {} }) {
  if (!container || !items?.length) return false;
  const previous = container.parentElement.querySelector('.home-carousel-prev');
  const next = container.parentElement.querySelector('.home-carousel-next');
  const live = container.parentElement.querySelector('.home-carousel-caption');
  const canvas = document.createElement('canvas');
  const gl = canvas.getContext('webgl2', { alpha: true, antialias: true, premultipliedAlpha: true });
  if (!gl) return false;

  const scene = document.createElement('canvas');
  const sceneCtx = scene.getContext('2d');
  if (!sceneCtx) return false;
  canvas.className = 'flex-carousel-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  const compile = (type, source) => {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
    return shader;
  };
  let program;
  try {
    program = gl.createProgram();
    gl.attachShader(program, compile(gl.VERTEX_SHADER, lensVertex));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, lensFragment));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
  } catch (error) {
    console.error('FlexCarousel lens shader could not start:', error);
    gl.getExtension('WEBGL_lose_context')?.loseContext();
    return false;
  }

  const vertices = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, vertices);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  gl.useProgram(program);
  const positionLocation = gl.getAttribLocation(program, 'position');
  gl.enableVertexAttribArray(positionLocation);
  gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);
  const texture = gl.createTexture();
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.uniform1i(gl.getUniformLocation(program, 'tScene'), 0);
  const uniform = name => gl.getUniformLocation(program, name);
  const uniforms = {
    resolution: uniform('uResolution'), dpr: uniform('uDpr'), center: uniform('uCenter'),
    half: uniform('uHalf'), angle: uniform('uAngle'), exponent: uniform('uExponent'),
    inner: uniform('uInner'), outer: uniform('uOuter'), flow: uniform('uFlow'),
    curl: uniform('uCurl'), dispersion: uniform('uDispersion'), strength: uniform('uStrength'),
    alpha: uniform('uSceneAlpha')
  };

  let width = 1, height = 1, scale = 1, active = 0, position = 0, targetPosition = 0;
  let dragging = false, downX = 0, moved = false, focused = false, raf = 0, timer = 0, destroyed = false;
  let introStart = performance.now();
  const images = items.map(item => {
    const image = new Image(); image.decoding = 'async'; image.src = item.src;
    image.addEventListener('load', wake); return { ...item, image };
  });
  const cardH = () => Math.min(height * (config.cardHeight ?? .5), height * .78);
  const cardW = i => {
    const img = images[i]?.image;
    const aspect = img?.naturalWidth && img?.naturalHeight ? img.naturalWidth / img.naturalHeight : 1;
    return Math.min(cardH() * aspect, width * .82);
  };
  const stride = i => cardW(i) + (config.gap ?? 8);
  const offsetFor = i => images.slice(0, i).reduce((sum, _, n) => sum + stride(n), 0);
  const loopWidth = () => images.reduce((sum, _, i) => sum + stride(i), 0);
  const mod = (n, m) => ((n % m) + m) % m;
  const positionFor = (index, near = targetPosition) => {
    const loop = Math.max(loopWidth(), 1), base = offsetFor(mod(index, items.length));
    return base + Math.round((near - base) / loop) * loop;
  };
  const nearest = offset => {
    const loop = Math.max(loopWidth(), 1);
    let best = 0, bestD = Infinity;
    for (let i = 0; i < items.length; i++) {
      const raw = mod(offset - offsetFor(i) + loop / 2, loop) - loop / 2;
      if (Math.abs(raw) < bestD) { best = i; bestD = Math.abs(raw); }
    }
    return best;
  };
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  const caption = () => {
    if (!live) return;
    live.firstChild.textContent = `${items[active].title || items[active].alt || 'Artist'} · Explore artist `;
    const count = live.querySelector('span');
    if (count) count.textContent = `${String(active + 1).padStart(2, '0')} / ${String(items.length).padStart(2, '0')}`;
  };
  const select = i => { active = mod(i, items.length); targetPosition = positionFor(active); focused = false; caption(); wake(); };
  const roundedRect = (ctx, x, y, w, h, r) => { ctx.beginPath(); ctx.roundRect(x, y, w, h, r); };
  const resize = () => {
    const rect = container.getBoundingClientRect();
    width = Math.max(1, rect.width); height = Math.max(1, rect.height);
    scale = Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(4500000 / (width * height)));
    canvas.width = scene.width = Math.round(width * scale);
    canvas.height = scene.height = Math.round(height * scale);
    canvas.style.width = '100%'; canvas.style.height = '100%';
    sceneCtx.setTransform(scale, 0, 0, scale, 0, 0);
    gl.viewport(0, 0, canvas.width, canvas.height);
    caption(); wake();
  };
  const renderScene = now => {
    sceneCtx.clearRect(0, 0, width, height);
    sceneCtx.fillStyle = '#080b18'; sceneCtx.fillRect(0, 0, width, height);
    const h = cardH();
    const t = clamp((now - introStart) / 1600, 0, 1);
    const intro = config.intro === 'bloom' ? t : 1;
    const squeeze = 1 - (config.squeeze ?? .1) * clamp(Math.abs(targetPosition - position) / Math.max(width, 1), 0, 1);
    const loop = Math.max(loopWidth(), 1);
    images.forEach((item, i) => {
      const image = item.image;
      if (!image.complete || !image.naturalWidth) return;
      const scaleCard = squeeze * (focused && i === active ? 1.16 : 1);
      const w = cardW(i) * scaleCard, ch = h * scaleCard;
      const y = height * .5 - ch * .5, footer = 68;
      for (let cycle = -2; cycle <= 2; cycle++) {
        const x = width * .5 + offsetFor(i) + cycle * loop - position;
        if (x + w / 2 < 0 || x - w / 2 > width) continue;
        sceneCtx.save(); sceneCtx.globalAlpha = intro;
        roundedRect(sceneCtx, x - w / 2, y, w, ch + footer, config.radius ?? 12);
        sceneCtx.clip(); sceneCtx.fillStyle = '#12152c'; sceneCtx.fillRect(x - w / 2, y, w, ch + footer);
        const aspect = image.naturalWidth / image.naturalHeight, boxAspect = w / ch;
        let sx = 0, sy = 0, sw = image.naturalWidth, sh = image.naturalHeight;
        if (aspect > boxAspect) { sw = image.naturalHeight * boxAspect; sx = (image.naturalWidth - sw) / 2; }
        else { sh = image.naturalWidth / boxAspect; sy = (image.naturalHeight - sh) / 2; }
        sceneCtx.drawImage(image, sx, sy, sw, sh, x - w / 2, y, w, ch);
        sceneCtx.fillStyle = '#12152c'; sceneCtx.fillRect(x - w / 2, y + ch, w, footer);
        sceneCtx.fillStyle = '#f2f1ff'; sceneCtx.font = '600 19px "Instrument Sans",Arial,sans-serif'; sceneCtx.textBaseline = 'top';
        sceneCtx.fillText(item.title || item.alt || 'Artist', x - w / 2 + 15, y + ch + 12, w - 30);
        sceneCtx.fillStyle = '#b2b5d1'; sceneCtx.font = '12px "Instrument Sans",Arial,sans-serif';
        sceneCtx.fillText(item.subtitle || 'Explore artist', x - w / 2 + 15, y + ch + 39, w - 30);
        sceneCtx.restore();
      }
    });
    return t;
  };
  const draw = (now = performance.now()) => {
    raf = 0; if (destroyed) return;
    position += (targetPosition - position) * .12;
    const loop = Math.max(loopWidth(), 1);
    if (Math.abs(position) > loop * 6) { const shift = Math.trunc(position / loop) * loop; position -= shift; targetPosition -= shift; }
    const t = renderScene(now);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, scene);
    gl.useProgram(program); gl.bindBuffer(gl.ARRAY_BUFFER, vertices);
    gl.enableVertexAttribArray(positionLocation); gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);
    const halfW = Math.max(width * (config.lensWidth ?? .74) / 2, 1);
    const halfH = Math.max(width * (config.lensHeight ?? 1.18) / 2, 1);
    const spanW = Math.max(halfW, 1), spanH = Math.max(halfH, 1);
    const inner = Math.max(4, (config.reach ?? .38) * (spanW + spanH) * .5);
    const strength = config.intro === 'bloom' ? clamp((t - .2) / .8, 0, 1) ** 2 * (3 - 2 * clamp((t - .2) / .8, 0, 1)) : 1;
    gl.uniform2f(uniforms.resolution, width, height);
    gl.uniform1f(uniforms.dpr, scale);
    gl.uniform2f(uniforms.center, width / 2, height / 2);
    gl.uniform2f(uniforms.half, halfW, halfH);
    gl.uniform1f(uniforms.angle, (config.tilt ?? 62) * Math.PI / 180);
    gl.uniform1f(uniforms.exponent, 2 + Math.pow(1 - clamp(config.roundness ?? 1, 0, 1), 1.5) * 10);
    gl.uniform1f(uniforms.inner, inner); gl.uniform1f(uniforms.outer, inner * 1.6);
    gl.uniform1f(uniforms.flow, (config.bend ?? .34) * (spanW + spanH) * .45);
    gl.uniform1f(uniforms.curl, config.curl === 'rise' ? 1 : config.curl === 'fall' ? -1 : 0);
    gl.uniform1f(uniforms.dispersion, (config.dispersion ?? .45) * .12);
    gl.uniform1f(uniforms.strength, strength * (focused ? 0 : 1));
    gl.uniform1f(uniforms.alpha, 1);
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT); gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (Math.abs(targetPosition - position) > .2 || t < 1) wake();
  };
  function wake() { if (!raf && !destroyed) raf = requestAnimationFrame(draw); }
  const prev = () => select(active - 1), forward = () => select(active + 1);
  const startAuto = () => { clearInterval(timer); if (config.autoplay && !matchMedia('(prefers-reduced-motion: reduce)').matches) timer = setInterval(forward, (config.interval ?? 5) * 1000); };
  const down = e => { if (e.button !== undefined && e.button !== 0) return; dragging = true; moved = false; downX = e.clientX; clearInterval(timer); container.setPointerCapture?.(e.pointerId); };
  const move = e => { if (!dragging) return; const dx = e.clientX - downX; if (Math.abs(dx) > 5) moved = true; position -= dx; targetPosition = position; downX = e.clientX; wake(); };
  const up = e => {
    if (!dragging) return; dragging = false;
    if (moved) select(nearest(position));
    else { const x = e.clientX - container.getBoundingClientRect().left, hit = nearest(targetPosition + x - width * .5); if (hit !== active) select(hit); else { focused = !focused; wake(); } }
    startAuto();
  };
  const key = e => { if (e.key === 'ArrowRight') { e.preventDefault(); forward(); } else if (e.key === 'ArrowLeft') { e.preventDefault(); prev(); } else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); focused = !focused; wake(); } else if (e.key === 'Escape') { focused = false; wake(); } };
  const visibility = () => document.hidden ? clearInterval(timer) : startAuto();
  container.prepend(canvas); container.classList.add('has-glass');
  previous?.addEventListener('click', prev); next?.addEventListener('click', forward);
  container.addEventListener('pointerdown', down); container.addEventListener('pointermove', move);
  container.addEventListener('pointerup', up); container.addEventListener('pointercancel', up); container.addEventListener('keydown', key);
  document.addEventListener('visibilitychange', visibility);
  const observer = new ResizeObserver(resize); observer.observe(container); resize(); caption(); startAuto();
  return () => {
    destroyed = true; clearInterval(timer); cancelAnimationFrame(raf); observer.disconnect();
    previous?.removeEventListener('click', prev); next?.removeEventListener('click', forward);
    container.removeEventListener('pointerdown', down); container.removeEventListener('pointermove', move);
    container.removeEventListener('pointerup', up); container.removeEventListener('pointercancel', up); container.removeEventListener('keydown', key);
    document.removeEventListener('visibilitychange', visibility); gl.deleteTexture(texture); gl.deleteProgram(program); gl.deleteBuffer(vertices);
    canvas.remove(); container.classList.remove('has-glass');
  };
}
