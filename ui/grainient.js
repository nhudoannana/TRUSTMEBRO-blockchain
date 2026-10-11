/* ==========================================================================
   TrustMeBro — Grainient WebGL2 Background Module
   Pure Vanilla JS implementation of ReactBits Grainient shader.
   Zero dependencies, hardware-accelerated, theme-reactive, battery-friendly.
   ========================================================================== */

(function initGrainient() {
  function getCanvas() {
    let canvas = document.getElementById('grainient-canvas');
    if (!canvas) {
      let container = document.getElementById('grainient-bg');
      if (!container) {
        container = document.createElement('div');
        container.id = 'grainient-bg';
        container.className = 'grainient-bg';
        container.setAttribute('aria-hidden', 'true');
        document.body.prepend(container);
      }
      canvas = document.createElement('canvas');
      canvas.id = 'grainient-canvas';
      canvas.className = 'grainient-canvas';
      container.appendChild(canvas);

      if (!container.querySelector('.grainient-vignette')) {
        const vignette = document.createElement('div');
        vignette.className = 'grainient-vignette';
        container.appendChild(vignette);
      }
    }
    return canvas;
  }

  function startGrainient() {
    const canvas = getCanvas();
    if (!canvas) return;

    let gl = null;
    try {
      gl = canvas.getContext('webgl2', {
        alpha: true,
        antialias: false,
        powerPreference: 'low-power'
      });
    } catch (e) {
      gl = null;
    }

    if (!gl) {
      console.info('[Grainient] WebGL2 not supported, falling back to CSS background.');
      return;
    }

    const vertexShaderSrc = `#version 300 es
in vec2 position;
void main() {
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

    const fragmentShaderSrc = `#version 300 es
precision highp float;
uniform vec2 iResolution;
uniform float iTime;
uniform float uTimeSpeed;
uniform float uColorBalance;
uniform float uWarpStrength;
uniform float uWarpFrequency;
uniform float uWarpSpeed;
uniform float uWarpAmplitude;
uniform float uBlendAngle;
uniform float uBlendSoftness;
uniform float uRotationAmount;
uniform float uNoiseScale;
uniform float uGrainAmount;
uniform float uGrainScale;
uniform float uGrainAnimated;
uniform float uContrast;
uniform float uGamma;
uniform float uSaturation;
uniform vec2 uCenterOffset;
uniform float uZoom;
uniform vec3 uColor1;
uniform vec3 uColor2;
uniform vec3 uColor3;
uniform float uLightMode;
out vec4 fragColor;

#define S(a,b,t) smoothstep(a,b,t)

mat2 Rot(float a) {
  float s = sin(a), c = cos(a);
  return mat2(c, -s, s, c);
}

vec2 hash(vec2 p) {
  p = vec2(dot(p, vec2(2127.1, 81.17)), dot(p, vec2(1269.5, 283.37)));
  return fract(sin(p) * 43758.5453);
}

float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p), u = f * f * (3.0 - 2.0 * f);
  float n = mix(
    mix(dot(-1.0 + 2.0 * hash(i + vec2(0.0, 0.0)), f - vec2(0.0, 0.0)),
        dot(-1.0 + 2.0 * hash(i + vec2(1.0, 0.0)), f - vec2(1.0, 0.0)), u.x),
    mix(dot(-1.0 + 2.0 * hash(i + vec2(0.0, 1.0)), f - vec2(0.0, 1.0)),
        dot(-1.0 + 2.0 * hash(i + vec2(1.0, 1.0)), f - vec2(1.0, 1.0)), u.x),
    u.y
  );
  return 0.5 + 0.5 * n;
}

void mainImage(out vec4 o, vec2 C) {
  float t = iTime * uTimeSpeed;
  vec2 uv = C / iResolution.xy;
  float ratio = iResolution.x / iResolution.y;
  vec2 tuv = uv - 0.5 + uCenterOffset;
  tuv /= max(uZoom, 0.001);

  float degree = noise(vec2(t * 0.1, tuv.x * tuv.y) * uNoiseScale);
  tuv.y *= 1.0 / ratio;
  tuv *= Rot(radians((degree - 0.5) * uRotationAmount + 180.0));
  tuv.y *= ratio;

  float frequency = uWarpFrequency;
  float ws = max(uWarpStrength, 0.001);
  float amplitude = uWarpAmplitude / ws;
  float warpTime = t * uWarpSpeed;
  tuv.x += sin(tuv.y * frequency + warpTime) / amplitude;
  tuv.y += sin(tuv.x * (frequency * 1.5) + warpTime) / (amplitude * 0.5);

  vec3 colLav = uColor1;
  vec3 colOrg = uColor2;
  vec3 colDark = uColor3;
  float b = uColorBalance;
  float s = max(uBlendSoftness, 0.0);
  mat2 blendRot = Rot(radians(uBlendAngle));
  float blendX = (tuv * blendRot).x;
  float edge0 = -0.3 - b - s;
  float edge1 = 0.2 - b + s;
  float v0 = 0.5 - b + s;
  float v1 = -0.3 - b - s;
  vec3 layer1 = mix(colDark, colOrg, S(edge0, edge1, blendX));
  vec3 layer2 = mix(colOrg, colLav, S(edge0, edge1, blendX));
  vec3 col = mix(layer1, layer2, S(v0, v1, tuv.y));

  vec2 grainUv = uv * max(uGrainScale, 0.001);
  if (uGrainAnimated > 0.5) {
    grainUv += vec2(iTime * 0.05);
  }
  float grain = fract(sin(dot(grainUv, vec2(12.9898, 78.233))) * 43758.5453);
  col += (grain - 0.5) * uGrainAmount;

  col = (col - 0.5) * uContrast + 0.5;
  float luma = dot(col, vec3(0.2126, 0.7152, 0.0722));
  col = mix(vec3(luma), col, uSaturation);
  col = pow(max(col, 0.0), vec3(1.0 / max(uGamma, 0.001)));
  col = clamp(col, 0.0, 1.0);

  if (uLightMode > 0.5) {
    float energy = max(max(col.r, col.g), col.b);
    vec3 hue = col / max(energy, 0.001);
    float chroma = length(col - vec3(dot(col, vec3(0.333333))));
    float coverage = clamp(0.12 + chroma * 1.15 + energy * 0.18, 0.0, 0.88);
    col = mix(vec3(1.0), clamp(hue * 0.58 + col * 0.18, 0.0, 1.0), coverage);
  }

  o = vec4(col, 1.0);
}

void main() {
  vec4 o = vec4(0.0);
  mainImage(o, gl_FragCoord.xy);
  fragColor = o;
}
`;

    function compileShader(type, src) {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        console.warn('[Grainient] Shader compile error:', gl.getShaderInfoLog(s));
        gl.deleteShader(s);
        return null;
      }
      return s;
    }

    const vs = compileShader(gl.VERTEX_SHADER, vertexShaderSrc);
    const fs = compileShader(gl.FRAGMENT_SHADER, fragmentShaderSrc);
    if (!vs || !fs) return;

    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.warn('[Grainient] Program link error:', gl.getProgramInfoLog(program));
      return;
    }

    // Full-screen triangle covering [-1, 1] clip space
    const vertices = new Float32Array([-1, -1, 3, -1, -1, 3]);
    const vbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);

    const posLoc = gl.getAttribLocation(program, 'position');
    gl.enableVertexAttribArray(posLoc);
    gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

    const uniformNames = [
      'iResolution', 'iTime', 'uTimeSpeed', 'uColorBalance', 'uWarpStrength',
      'uWarpFrequency', 'uWarpSpeed', 'uWarpAmplitude', 'uBlendAngle', 'uBlendSoftness',
      'uRotationAmount', 'uNoiseScale', 'uGrainAmount', 'uGrainScale', 'uGrainAnimated',
      'uContrast', 'uGamma', 'uSaturation', 'uCenterOffset', 'uZoom',
      'uColor1', 'uColor2', 'uColor3', 'uLightMode'
    ];
    const u = {};
    for (const name of uniformNames) {
      u[name] = gl.getUniformLocation(program, name);
    }

    function hexToRgb(hex) {
      const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
      if (!m) return [1, 1, 1];
      return [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255];
    }

    // Set stable default uniforms
    gl.useProgram(program);
    gl.uniform1f(u.uTimeSpeed, 0.18);
    gl.uniform1f(u.uColorBalance, 0.0);
    gl.uniform1f(u.uWarpStrength, 1.0);
    gl.uniform1f(u.uWarpFrequency, 4.5);
    gl.uniform1f(u.uWarpSpeed, 1.6);
    gl.uniform1f(u.uWarpAmplitude, 48.0);
    gl.uniform1f(u.uBlendAngle, 12.0);
    gl.uniform1f(u.uBlendSoftness, 0.08);
    gl.uniform1f(u.uRotationAmount, 360.0);
    gl.uniform1f(u.uNoiseScale, 1.8);
    gl.uniform1f(u.uGrainAmount, 0.07);
    gl.uniform1f(u.uGrainScale, 2.2);
    gl.uniform1f(u.uGrainAnimated, 0.0); // Calmer static paper grain
    gl.uniform1f(u.uGamma, 1.02);
    gl.uniform1f(u.uSaturation, 1.06);
    gl.uniform2f(u.uCenterOffset, 0.0, 0.0);
    gl.uniform1f(u.uZoom, 0.95);

    function applyTheme() {
      const isLight = document.documentElement.dataset.theme === 'light';
      gl.useProgram(program);
      if (isLight) {
        gl.uniform1f(u.uLightMode, 1.0);
        gl.uniform1f(u.uContrast, 1.25);
        const c1 = hexToRgb('#d4a855'); // TrustMeBro Warm Gold
        const c2 = hexToRgb('#607995'); // Slate Blue
        const c3 = hexToRgb('#dce6f2'); // Soft Light Gray/Blue
        gl.uniform3f(u.uColor1, c1[0], c1[1], c1[2]);
        gl.uniform3f(u.uColor2, c2[0], c2[1], c2[2]);
        gl.uniform3f(u.uColor3, c3[0], c3[1], c3[2]);
      } else {
        gl.uniform1f(u.uLightMode, 0.0);
        gl.uniform1f(u.uContrast, 1.35);
        const c1 = hexToRgb('#d4a855'); // TrustMeBro Gold Accent
        const c2 = hexToRgb('#1b283d'); // Deep Indigo
        const c3 = hexToRgb('#090e17'); // Dark Background Base
        gl.uniform3f(u.uColor1, c1[0], c1[1], c1[2]);
        gl.uniform3f(u.uColor2, c2[0], c2[1], c2[2]);
        gl.uniform3f(u.uColor3, c3[0], c3[1], c3[2]);
      }
    }

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const w = window.innerWidth;
      const h = window.innerHeight;
      const dw = Math.max(1, Math.floor(w * dpr));
      const dh = Math.max(1, Math.floor(h * dpr));
      if (canvas.width !== dw || canvas.height !== dh) {
        canvas.width = dw;
        canvas.height = dh;
        gl.viewport(0, 0, dw, dh);
        gl.useProgram(program);
        gl.uniform2f(u.iResolution, dw, dh);
      }
    }

    let rafId = 0;
    let isVisible = true;
    let isPageVisible = !document.hidden;
    const t0 = performance.now();
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function render(now) {
      gl.useProgram(program);
      gl.uniform1f(u.iTime, (now - t0) * 0.001);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (!prefersReducedMotion && isVisible && isPageVisible) {
        rafId = requestAnimationFrame(render);
      }
    }

    function startLoop() {
      if (prefersReducedMotion) {
        render(performance.now());
        return;
      }
      if (rafId === 0 && isVisible && isPageVisible) {
        rafId = requestAnimationFrame(render);
      }
    }

    function stopLoop() {
      if (rafId !== 0) {
        cancelAnimationFrame(rafId);
        rafId = 0;
      }
    }

    // Visibility and battery optimizations
    document.addEventListener('visibilitychange', () => {
      isPageVisible = !document.hidden;
      if (isPageVisible) startLoop();
      else stopLoop();
    });

    window.addEventListener('resize', () => {
      resize();
      if (prefersReducedMotion) render(performance.now());
    });

    // React to theme toggling instantly
    const themeObserver = new MutationObserver(applyTheme);
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme']
    });

    // IntersectionObserver to pause when offscreen
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver(([entry]) => {
        isVisible = entry.isIntersecting;
        if (isVisible) startLoop();
        else stopLoop();
      });
      io.observe(canvas);
    }

    // Initial setup
    resize();
    applyTheme();
    startLoop();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startGrainient);
  } else {
    startGrainient();
  }
})();

