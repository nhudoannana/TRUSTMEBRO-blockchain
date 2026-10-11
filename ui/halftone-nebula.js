/* ==========================================================================
   TrustMeBro — Halftone Nebula WebGL2 Background (Clean Minimal Starfield)
   Pure starry sky + Planet + Interactive Cursor/Ripples — Zero blotches.
   Zero dependencies, hardware-accelerated, theme-reactive, battery-friendly.
   ========================================================================== */

(function initHalftoneNebula() {
  const MAX_SPARKS = 16;
  const MAX_RIPPLES = 4;

  const NEBULA_DARK = {
    pixel: 6,
    dotMin: 0.10,
    dotMax: 0.48,
    levels: 7,
    scale: 1.7,
    warp: 1.0,
    drift: 0.038,
    density: 0.0,
    threshold: 0.54,
    softness: 0.5,
    band: 0.0,
    bandAngle: 0.85,
    bandOffset: 0.38,
    bandWidth: 0.35,
    haze: 0.0,
    stars: 1.6,       // Bầu trời sao phong phú, lấp lánh rõ nét
    twinkle: 1.8,     // Tần số nhấp nháy sống động
    starDrift: 1.3,   // Vận tốc trôi dạt êm dịu
    sparkles: 9,      // Các ngôi sao 4 cánh kim sắc nét
    seed: 14,
    spikeWidth: 1,
    planet: true,     // Giữ lại hành tinh
    planetX: 0.84,    // Đặt hành tinh ở góc trời bên phải để không che khuất chữ
    planetY: 0.22,
    planetRadius: 0.075,
    parallax: 1.0,
    lens: 0.55,
    lensRadius: 180,
    lensPush: 0.28,
    rippleSpeed: 440,
    speed: 1.05,
    vignette: 0.0,    // Không làm tối góc
    grain: 0.0,       // Không nhiễu lem
    lightMode: 0.0,
    // TrustMeBro Dark: Nền đêm Midnight thăm thẳm + Ánh sao Vàng Gold TrustMeBro
    voidColor: "#060911",
    hazeColor: "#10192a",
    duskColor: "#1d2c47",
    wineColor: "#4a3821",
    crimsonColor: "#a67c38",
    hotColor: "#d4a855",
    starColor: "#fff2d6"
  };

  const NEBULA_LIGHT = {
    pixel: 6,
    dotMin: 0.08,
    dotMax: 0.36,
    levels: 6,
    scale: 1.7,
    warp: 1.0,
    drift: 0.026,
    density: 0.0,
    threshold: 0.50,
    softness: 0.55,
    band: 0.0,
    bandAngle: 0.85,
    bandOffset: 0.38,
    bandWidth: 0.35,
    haze: 0.0,
    stars: 0.9,
    twinkle: 1.4,
    starDrift: 1.0,
    sparkles: 8,
    seed: 14,
    spikeWidth: 1,
    planet: false,    // Chế độ sáng tắt hành tinh tối
    planetX: 0.84,
    planetY: 0.22,
    planetRadius: 0.075,
    parallax: 0.8,
    lens: 0.45,
    lensRadius: 160,
    lensPush: 0.25,
    rippleSpeed: 420,
    speed: 0.95,
    vignette: 0.0,
    grain: 0.0,
    lightMode: 1.0,
    // Tông VÀNG CHANH TƯƠI SÁNG (Lemon Yellow / Citrus Clean) — Tuyệt đối không xám, không nâu:
    voidColor: "#ffffff",
    hazeColor: "#fffde7",
    duskColor: "#fff9c4",
    wineColor: "#fff59d",
    crimsonColor: "#ffee58",
    hotColor: "#fdd835",
    starColor: "#fbc02d"
  };

  const UNIFORM_SLOTS = [
    ["pixel", "f"], ["dotMin", "f"], ["dotMax", "f"], ["levels", "f"],
    ["scale", "f"], ["warp", "f"], ["drift", "f"], ["density", "f"],
    ["threshold", "f"], ["softness", "f"],
    ["band", "f"], ["bandAngle", "f"], ["bandOffset", "f"], ["bandWidth", "f"], ["haze", "f"],
    ["stars", "f"], ["twinkle", "f"], ["starDrift", "f"], ["spikeWidth", "f"],
    ["parallax", "f"], ["lens", "f"], ["lensRadius", "f"], ["lensPush", "f"], ["rippleSpeed", "f"],
    ["vignette", "f"], ["grain", "f"], ["lightMode", "f"],
    ["voidColor", "c"], ["hazeColor", "c"], ["duskColor", "c"], ["wineColor", "c"],
    ["crimsonColor", "c"], ["hotColor", "c"], ["starColor", "c"]
  ];

  const uName = k => "u" + k[0].toUpperCase() + k.slice(1);
  const glslType = kind => (kind === "c" ? "vec3" : kind === "i" || kind === "b" ? "int" : "float");
  const declareUniforms = slots => slots.map(([k, kind]) => "uniform " + glslType(kind) + " " + uName(k) + ";").join("\n");

  const VERT = `#version 300 es
void main(){
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

  const FRAG = `#version 300 es
precision highp float;
uniform vec2 uRes;
uniform float uDpr;
uniform float uTime;
uniform vec2 uPointer;
uniform float uPointerOn;
uniform vec2 uLook;
uniform int uSparkCount;
uniform vec4 uSpark[${MAX_SPARKS}];
uniform vec4 uSparkB[${MAX_SPARKS}];
uniform vec4 uRipple[${MAX_RIPPLES}];
uniform vec4 uPlanet;
${declareUniforms(UNIFORM_SLOTS)}
out vec4 frag;

float hash12(vec2 p){
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}
float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash12(i), b = hash12(i + vec2(1.0, 0.0));
  float c = hash12(i + vec2(0.0, 1.0)), d = hash12(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}
float fbm(vec2 p){
  float s = 0.0, a = 0.5;
  mat2 r = mat2(0.8, -0.6, 0.6, 0.8);
  for (int i = 0; i < 5; i++) { s += a * vnoise(p); p = r * p * 2.03 + 17.1; a *= 0.5; }
  return s / 0.96875;
}
float bayer4(vec2 c){
  vec2 m = mod(c, 4.0);
  int i = int(m.x) + int(m.y) * 4;
  int b[16] = int[16](0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5);
  return (float(b[i]) + 0.5) / 16.0;
}
vec3 ramp(float d, vec3 haze){
  vec3 c = mix(uVoidColor, haze, smoothstep(0.0, 0.22, d));
  c = mix(c, uWineColor, smoothstep(0.18, 0.44, d));
  c = mix(c, uCrimsonColor, smoothstep(0.42, 0.72, d));
  return mix(c, uHotColor, smoothstep(0.7, 0.96, d));
}
vec2 shift(float depth){
  return floor(uLook * uParallax * depth * 28.0);
}

// Bỏ toàn bộ các vết mây tĩnh trôi nổi (static noisy gas clouds).
// Nền hoàn toàn sạch sẽ; hiệu ứng chấm halftone chỉ xuất hiện khi rê chuột hoặc click sóng xung kích!
vec3 field(vec2 pos, vec2 resCss){
  vec2 toP = pos - uPointer;
  float lamp = exp(-dot(toP, toP) / (uLensRadius * uLensRadius)) * uPointerOn;

  float ring = 0.0;
  for (int i = 0; i < ${MAX_RIPPLES}; i++) {
    vec4 r = uRipple[i];
    float age = uTime - r.z;
    if (r.w <= 0.0 || age < 0.0 || age > 2.4) continue;
    vec2 dv = pos - r.xy;
    float dist = length(dv);
    float w = 14.0 + age * 26.0;
    float k = exp(-pow((dist - age * uRippleSpeed) / w, 2.0)) * (1.0 - age / 2.4) * r.w;
    ring += k;
  }

  for (int i = 0; i < ${MAX_SPARKS}; i++) {
    if (i >= uSparkCount) break;
    vec4 s = uSpark[i];
    vec4 b = uSparkB[i];
    float grow = smoothstep(0.0, 0.6, uTime - s.w);
    float dist = length(pos - s.xy - shift(1.2));
    ring += exp(-dist / max(b.w * 2.2 * (1.0 + b.z * 0.6), 1.0)) * 0.35 * grow;
  }

  float d = clamp(lamp * uLens * 0.32 + ring * 0.45, 0.0, 1.0);
  return vec3(d, 0.0, 0.0);
}

void main(){
  vec2 resCss = uRes / uDpr;
  vec2 css = gl_FragCoord.xy / uDpr;
  float px = max(uPixel, 1.0);
  vec2 cell = floor(css / px);
  vec2 cellC = (cell + 0.5) * px;
  vec2 f = fract(css / px) - 0.5;
  float L = max(uLevels, 2.0);
  float dith = bayer4(cell);

  vec3 g = field(cellC, resCss);
  float dq = clamp(floor(g.x * L + dith) / L, 0.0, 1.0);
  // Không vẽ chấm halftone bừa bãi khi không có tương tác:
  float r = dq < 0.02 ? 0.0 : mix(uDotMin, uDotMax, sqrt(dq));
  float dotMask = step(length(f), r);

  vec3 col;
  if (uLightMode > 0.5) {
    vec3 bg = uVoidColor;
    vec3 dotCol = mix(uCrimsonColor, uHotColor, smoothstep(0.05, 0.85, dq));
    col = mix(bg, dotCol, dotMask);
  } else {
    vec3 bg = uVoidColor;
    vec3 dotCol = ramp(min(dq + 0.1, 1.0), uHazeColor);
    col = mix(bg, dotCol, dotMask);
  }

  // ---- pixel stars, three parallax depths (Tinh tế, trôi dạt êm đềm) --------------------
  vec3 starAcc = vec3(0.0);
  float starA = 0.0;
  for (int l = 0; l < 3; l++) {
    float fl = float(l);
    float depth = 0.3 + fl * 0.4;
    float gpx = px * (l == 2 ? 2.0 : 1.0);
    vec2 sp = css + shift(depth) + vec2(0.0, floor(uTime * uStarDrift * depth));
    vec2 id = floor(sp / gpx);
    vec2 fr = fract(sp / gpx) - 0.5;
    float prob = uStars * (l == 0 ? 0.009 : l == 1 ? 0.014 : 0.01);
    float h = hash12(id + fl * 71.3);
    if (h > 1.0 - prob) {
      float h2 = hash12(id * 1.7 + 3.1 + fl);
      float tw = 0.45 + 0.55 * (0.5 + 0.5 * sin(uTime * uTwinkle * (0.6 + h2 * 2.5) + h2 * 40.0));
      float rad = l == 2 ? 0.42 : 0.26 + h2 * 0.22;
      float m = step(length(fr), rad);
      vec3 c = (l == 0 || h2 > 0.82) ? uStarColor : uHotColor;
      starAcc = max(starAcc, c * m * tw);
      starA = max(starA, m * tw);
    }
  }

  if (uLightMode > 0.5) {
    col = mix(col, starAcc, starA * 0.85);
  } else {
    col = mix(col, starAcc / max(starA, 1e-3), starA);
  }

  // ---- the planet (Hành tinh ở góc trời bên phải) --------------------
  if (uPlanet.w > 0.5) {
    vec2 pc = uPlanet.xy + shift(0.8);
    float R = uPlanet.z;
    vec2 dc = cellC - pc;
    if (length(dc) < R) {
      vec2 n2 = dc / R;
      float z = sqrt(max(1.0 - dot(n2, n2), 0.0));
      float lit = clamp(dot(vec3(n2, z), normalize(vec3(-0.45, 0.55, 0.7))), 0.0, 1.0);
      float surf = fbm(vec2(n2.x * 1.4 + uTime * 0.015, n2.y * 4.2) * 1.6 + 9.0);
      float pd = clamp(lit * 1.05 - smoothstep(0.55, 0.75, surf) * 0.45 * (1.0 - lit * 0.5) + 0.05, 0.0, 1.0);
      float pq = floor(pd * L + dith) / L;
      vec3 pbg = mix(mix(uVoidColor, uWineColor, 0.35), uWineColor, pq);
      float pr = mix(0.2, 0.62, sqrt(pq));
      vec3 pdot = ramp(min(pq * 0.85 + 0.25, 1.0), uHazeColor);
      col = mix(pbg, pdot, step(length(f), pr));
    }
  }

  // ---- sparkle stars: chunky core, needle spikes -----------------------------
  vec2 sh = shift(1.2);
  for (int i = 0; i < ${MAX_SPARKS}; i++) {
    if (i >= uSparkCount) break;
    vec4 s = uSpark[i];
    vec4 b = uSparkB[i];
    float age = uTime - s.w;
    if (age < 0.0) continue;
    float grow = smoothstep(0.0, 0.55, age) * (1.0 + 0.3 * exp(-age * 3.0) * sin(age * 13.0));
    float tw = 0.84 + 0.16 * sin(uTime * uTwinkle * 1.7 + b.y);
    float flare = 1.0 + b.z * 0.6;
    float reach = s.z * grow * tw * flare;
    float core = b.w * grow * flare;
    vec3 tint = mix(uHotColor, uStarColor, b.x);
    vec2 c = s.xy + sh;
    vec2 d = css - c;
    float th = uSpikeWidth * 0.5 + 0.25;
    float hx = step(abs(d.y), th) * pow(max(1.0 - abs(d.x) / max(reach, 1.0), 0.0), 1.1);
    float vy = step(abs(d.x), th) * pow(max(1.0 - abs(d.y) / max(reach, 1.0), 0.0), 1.1);
    vec2 rd = vec2(d.x + d.y, d.x - d.y) * 0.7071;
    float diag = step(0.5, core / px - 1.5) * 0.45 * max(
      step(abs(rd.y), th) * pow(max(1.0 - abs(rd.x) / max(reach * 0.22, 1.0), 0.0), 2.0),
      step(abs(rd.x), th) * pow(max(1.0 - abs(rd.y) / max(reach * 0.22, 1.0), 0.0), 2.0));
    
    if (uLightMode > 0.5) {
      col = mix(col, tint, clamp(max(max(hx, vy), diag) * 0.8, 0.0, 1.0));
      float hp = px * 0.5;
      vec2 dcell = (floor(css / hp) + 0.5) * hp - (floor(c / hp) + 0.5) * hp;
      float disc = step(length(dcell), core);
      col = mix(col, tint, disc * 0.85);
    } else {
      col = mix(col, tint, clamp(max(max(hx, vy), diag), 0.0, 1.0));
      float hp = px * 0.5;
      vec2 dcell = (floor(css / hp) + 0.5) * hp - (floor(c / hp) + 0.5) * hp;
      float disc = step(length(dcell), core);
      float glow = exp(-length(d) / max(core * 1.4, 1.0)) * (1.0 - disc);
      col += tint * glow * 0.35;
      col = mix(col, tint, disc);
      float cross = max(step(abs(d.y), th) * step(abs(d.x), core * 0.85),
                        step(abs(d.x), th) * step(abs(d.y), core * 0.85));
      col = mix(col, uStarColor, cross * disc * 0.9);
    }
  }

  frag = vec4(clamp(col, 0.0, 1.0), 1.0);
}`;

  function mulberry32(seed) {
    let a = seed >>> 0;
    return () => {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function layoutSparkles(seed, count) {
    const rand = mulberry32(seed);
    const out = [];
    const n = Math.max(0, Math.min(Math.floor(count), MAX_SPARKS));
    for (let i = 0; i < n; i++) {
      const hero = i === 0;
      const pale = i === 1;
      let x = 0.5;
      let y = 0.5;
      for (let tries = 0; tries < 40; tries++) {
        x = 0.08 + 0.84 * rand();
        y = hero ? 0.58 + 0.28 * rand() : 0.08 + 0.84 * rand();
        const clear = out.every(s => Math.hypot(s.x - x, s.y - y) > (hero ? 0.2 : 0.13));
        if (clear) break;
      }
      out.push({
        x,
        y,
        reach: hero ? 0.2 + 0.05 * rand() : pale ? 0.08 + 0.03 * rand() : 0.025 + 0.055 * rand(),
        core: hero ? 0.024 : pale ? 0.011 : 0.004 + 0.006 * rand(),
        tint: pale ? 1 : 0,
        phase: rand() * 6.283,
        born: -10,
        user: false
      });
    }
    return out;
  }

  function pushSparkle(list, next, max = MAX_SPARKS) {
    if (list.length < max) return [...list, next];
    const oldest = list.findIndex(s => s.user);
    if (oldest === -1) return list;
    return [...list.slice(0, oldest), ...list.slice(oldest + 1), next];
  }

  function hexToRgb(hex) {
    let h = hex.trim().replace(/^#/, "");
    if (h.length === 3) h = h.split("").map(c => c + c).join("");
    if (!/^[0-9a-fA-F]{6}$/.test(h)) return [0, 0, 0];
    const v = parseInt(h, 16);
    return [((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255];
  }

  function driftPos(t) {
    const x = 0.5 + 0.32 * Math.sin(t * 0.21) + 0.1 * Math.sin(t * 0.077 + 1.3);
    const y = 0.5 + 0.26 * Math.cos(t * 0.17) + 0.12 * Math.cos(t * 0.053 + 4.2);
    return [Math.min(Math.max(x, 0.05), 0.95), Math.min(Math.max(y, 0.05), 0.95)];
  }

  function getCanvas() {
    let canvas = document.getElementById('nebula-canvas');
    if (!canvas) {
      let container = document.getElementById('nebula-bg');
      if (!container) {
        container = document.createElement('div');
        container.id = 'nebula-bg';
        container.className = 'nebula-bg';
        container.setAttribute('aria-hidden', 'true');
        document.body.prepend(container);
      }
      canvas = document.createElement('canvas');
      canvas.id = 'nebula-canvas';
      canvas.className = 'nebula-canvas';
      container.appendChild(canvas);

      if (!container.querySelector('.nebula-vignette')) {
        const vignette = document.createElement('div');
        vignette.className = 'nebula-vignette';
        container.appendChild(vignette);
      }
    }
    return canvas;
  }

  function start() {
    const canvas = getCanvas();
    if (!canvas) return;

    let gl = null;
    try {
      gl = canvas.getContext("webgl2", {
        antialias: false,
        alpha: false,
        depth: false,
        powerPreference: "high-performance"
      });
    } catch (e) {
      gl = null;
    }

    if (!gl) {
      console.info("[HalftoneNebula] WebGL2 not supported, falling back to CSS.");
      return;
    }

    function compile(type, src) {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        console.warn("[HalftoneNebula] Shader compile error:", gl.getShaderInfoLog(s));
        gl.deleteShader(s);
        return null;
      }
      return s;
    }

    const vs = compile(gl.VERTEX_SHADER, VERT);
    const fs = compile(gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return;

    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    gl.deleteShader(vs);
    gl.deleteShader(fs);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.warn("[HalftoneNebula] Link error:", gl.getProgramInfoLog(program));
      return;
    }

    const loc = n => gl.getUniformLocation(program, n);
    const tuned = UNIFORM_SLOTS.map(([k, kind]) => [loc(uName(k)), k, kind]);
    const U = {
      res: loc("uRes"), dpr: loc("uDpr"), time: loc("uTime"),
      pointer: loc("uPointer"), pointerOn: loc("uPointerOn"), look: loc("uLook"),
      sparkCount: loc("uSparkCount"), spark: loc("uSpark"), sparkB: loc("uSparkB"),
      ripple: loc("uRipple"), planet: loc("uPlanet")
    };
    const vao = gl.createVertexArray();

    let currentParams = document.documentElement.dataset.theme === 'light' ? NEBULA_LIGHT : NEBULA_DARK;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    let reduced = mq.matches;
    mq.addEventListener("change", () => { reduced = mq.matches; });

    let cssW = window.innerWidth;
    let cssH = window.innerHeight;
    let dpr = 1;
    const maxDpr = 2;

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, maxDpr);
      cssW = Math.max(window.innerWidth, 1);
      cssH = Math.max(window.innerHeight, 1);
      const w = Math.floor(cssW * dpr);
      const h = Math.floor(cssH * dpr);
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      if (reduced) paint();
    }

    let sparks = layoutSparkles(currentParams.seed, currentParams.sparkles);
    let laidOut = currentParams.seed + ":" + currentParams.sparkles;
    const flare = new Float32Array(MAX_SPARKS);
    const sparkA = new Float32Array(MAX_SPARKS * 4);
    const sparkB = new Float32Array(MAX_SPARKS * 4);
    const ripples = new Float32Array(MAX_RIPPLES * 4);
    let rippleNext = 0;

    const t0 = performance.now();
    const clock = () => (reduced ? 14 : ((performance.now() - t0) / 1000) * currentParams.speed);
    let lastClock = 0;

    let targetX = 0.5, targetY = 0.5;
    let lampX = 0.5, lampY = 0.5;
    let lookX = 0, lookY = 0;
    let lampOn = 0;
    let inside = false;
    let lastTouched = -1e9;

    function toUv(e) {
      return [
        Math.min(Math.max(e.clientX / Math.max(window.innerWidth, 1), 0), 1),
        Math.min(Math.max(1 - (e.clientY / Math.max(window.innerHeight, 1)), 0), 1)
      ];
    }

    window.addEventListener("pointermove", e => {
      [targetX, targetY] = toUv(e);
      inside = true;
      lastTouched = performance.now() / 1000;
    }, { passive: true });

    window.addEventListener("pointerleave", () => { inside = false; });
    window.addEventListener("pointercancel", () => { inside = false; });

    window.addEventListener("pointerdown", e => {
      if (e.button > 0) return;
      if (e.target && e.target.closest("a, button, input, textarea, select, label, [role=button], .mode-card, .panel, .masthead")) {
        return;
      }
      const [x, y] = toUv(e);
      targetX = x; targetY = y;
      inside = true;
      lastTouched = performance.now() / 1000;
      const now = clock();
      const rand = Math.random();
      sparks = pushSparkle(sparks, {
        x, y,
        reach: 0.045 + 0.08 * rand,
        core: 0.006 + 0.008 * rand,
        tint: Math.random() < 0.2 ? 1 : 0,
        phase: Math.random() * 6.283,
        born: reduced ? now - 10 : now,
        user: true
      });
      ripples.set([x * cssW, y * cssH, now, reduced ? 0 : 1], rippleNext * 4);
      rippleNext = (rippleNext + 1) % MAX_RIPPLES;
      if (reduced) paint();
    });

    function applyTheme() {
      const isLight = document.documentElement.dataset.theme === 'light';
      currentParams = isLight ? NEBULA_LIGHT : NEBULA_DARK;
      paint();
    }
    new MutationObserver(applyTheme).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme']
    });

    function paint() {
      const p = currentParams;
      const key = p.seed + ":" + p.sparkles;
      if (key !== laidOut) {
        sparks = [...layoutSparkles(p.seed, p.sparkles), ...sparks.filter(s => s.user)].slice(0, MAX_SPARKS);
        laidOut = key;
      }
      const t = clock();
      const dt = Math.min(Math.max(t - lastClock, 0), 0.1);
      lastClock = t;

      const idle = !inside || (performance.now() / 1000 - lastTouched > 5);
      const [gx, gy] = driftPos(t * 0.6);
      const wantX = idle ? gx : targetX;
      const wantY = idle ? gy : targetY;
      const k = reduced ? 1 : 1 - Math.exp(-dt * (idle ? 1.5 : 7));
      lampX += (wantX - lampX) * k;
      lampY += (wantY - lampY) * k;
      lookX += ((wantX - 0.5) * 2 - lookX) * k;
      lookY += ((wantY - 0.5) * 2 - lookY) * k;
      const onTarget = !reduced ? (idle ? 0.6 : 1) : 0;
      lampOn += (onTarget - lampOn) * (reduced ? 1 : 1 - Math.exp(-dt * 3));

      const minSide = Math.min(cssW, cssH);
      const n = Math.min(sparks.length, MAX_SPARKS);
      for (let i = 0; i < n; i++) {
        const s = sparks[i];
        const reach = s.reach * minSide;
        const d = Math.hypot(s.x * cssW - lampX * cssW, s.y * cssH - lampY * cssH);
        const want = !reduced ? Math.exp(-(d * d) / Math.max(reach * reach * 0.6, 400)) : 0;
        flare[i] += (want - flare[i]) * (reduced ? 1 : 1 - Math.exp(-dt * 6));
        sparkA.set([s.x * cssW, s.y * cssH, reach, s.born], i * 4);
        sparkB.set([s.tint, s.phase, flare[i], Math.max(s.core * minSide, 1.5)], i * 4);
      }

      gl.useProgram(program);
      gl.bindVertexArray(vao);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, canvas.width, canvas.height);

      for (const [l, key, kind] of tuned) {
        const v = p[key];
        if (kind === "c") gl.uniform3fv(l, hexToRgb(v));
        else if (kind === "i" || kind === "b") gl.uniform1i(l, Number(v) | 0);
        else gl.uniform1f(l, v);
      }
      gl.uniform2f(U.res, canvas.width, canvas.height);
      gl.uniform1f(U.dpr, canvas.width / cssW);
      gl.uniform1f(U.time, t);
      gl.uniform2f(U.pointer, lampX * cssW, lampY * cssH);
      gl.uniform1f(U.pointerOn, lampOn);
      gl.uniform2f(U.look, lookX, lookY);
      gl.uniform1i(U.sparkCount, n);
      gl.uniform4fv(U.spark, sparkA);
      gl.uniform4fv(U.sparkB, sparkB);
      gl.uniform4fv(U.ripple, ripples);
      gl.uniform4f(U.planet, p.planetX * cssW, p.planetY * cssH, p.planetRadius * minSide, p.planet ? 1 : 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    let raf = 0;
    let visible = true;
    function frame() {
      raf = 0;
      paint();
      if (visible && !document.hidden && !reduced) {
        raf = requestAnimationFrame(frame);
      }
    }
    function wake() {
      if (!reduced && !raf && visible && !document.hidden) {
        raf = requestAnimationFrame(frame);
      }
    }

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) wake();
      else if (raf) { cancelAnimationFrame(raf); raf = 0; }
    });

    window.addEventListener("resize", () => {
      resize();
      if (reduced) paint();
    });

    resize();
    paint();
    wake();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
