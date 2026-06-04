/* vision_color.js — Análisis de composición RGB por pixel con clasificación HSV */

"use strict";

/**
 * COLOR_RANGES se mantiene para compatibilidad con código externo, pero la
 * clasificación real usa HSV (más robusta con la OV7670 y variaciones de luz).
 */
const COLOR_RANGES = {
  RED:     { rgbMin: [120, 0, 0],     rgbMax: [255, 100, 100] },
  ORANGE:  { rgbMin: [160, 60, 0],    rgbMax: [255, 180, 90] },
  YELLOW:  { rgbMin: [120, 120, 0],   rgbMax: [255, 255, 120] },
  GREEN:   { rgbMin: [0, 90, 0],      rgbMax: [120, 255, 120] },
  CYAN:    { rgbMin: [0, 120, 120],   rgbMax: [120, 255, 255] },
  BLUE:    { rgbMin: [0, 0, 90],      rgbMax: [100, 120, 255] },
  MAGENTA: { rgbMin: [120, 0, 120],   rgbMax: [255, 100, 255] },
  WHITE:   { rgbMin: [170, 170, 170], rgbMax: [255, 255, 255] },
  BLACK:   { rgbMin: [0, 0, 0],       rgbMax: [55, 55, 55] },
};

const COLOR_ORDER = [
  "RED", "ORANGE", "YELLOW", "GREEN", "CYAN", "BLUE", "MAGENTA", "WHITE", "BLACK",
];

/** Porcentaje minimo para considerar que hay un objetivo detectable */
const TARGET_MIN_PCT = 3;
const ANALYSIS_TOP_N = 4;
const CAMERA_VISION_TTL_MS = 4000;

function rgb565ToRgb(c0, c1) {
  const v = c0 | (c1 << 8);
  return [
    ((v >> 11) & 0x1f) << 3,
    ((v >> 5) & 0x3f) << 2,
    (v & 0x1f) << 3,
  ];
}

/**
 * Convierte RGB (0-255 cada uno) a HSV.
 * Devuelve [h (0-360), s (0-1), v (0-1)].
 */
function rgbToHsv(r, g, b) {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const d = max - min;
  let h = 0;
  const s = max === 0 ? 0 : d / max;
  const v = max;
  if (d > 0) {
    if (max === rn)      h = ((gn - bn) / d) % 6;
    else if (max === gn) h = (bn - rn) / d + 2;
    else                 h = (rn - gn) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  return [h, s, v];
}

/** Distancia angular en la rueda de tonos (0-180) */
function hueDist(h, center) {
  let d = Math.abs(h - center);
  if (d > 180) d = 360 - d;
  return d;
}

/**
 * Prototipos HSV (centro de tono) + reglas RGB para desambiguar vecinos.
 * hueSigma: tolerancia angular; menor = mas estricto entre colores parecidos.
 */
const COLOR_PROTOTYPES = [
  { name: "RED",     hue: 0,   hueWrap: true, hueSigma: 14, sMin: 0.50, rgbHint: "red" },
  { name: "ORANGE",  hue: 24,  hueSigma: 11, sMin: 0.50, rgbHint: "orange" },
  { name: "YELLOW",  hue: 52,  hueSigma: 12, sMin: 0.48, rgbHint: "yellow" },
  { name: "GREEN",   hue: 120, hueSigma: 35, sMin: 0.22, rgbHint: "green" },
  { name: "CYAN",    hue: 185, hueSigma: 18, sMin: 0.22, rgbHint: "cyan" },
  { name: "BLUE",    hue: 225, hueSigma: 28, sMin: 0.22, rgbHint: "blue" },
  { name: "MAGENTA", hue: 310, hueSigma: 30, sMin: 0.22, rgbHint: "magenta" },
];

/** Puntuacion RGB 0..1 segun que canal domina (ayuda amarillo vs naranja vs rojo) */
function rgbChannelScore(r, g, b, hint) {
  const mx = Math.max(r, g, b, 1);
  switch (hint) {
    case "red":
      return clamp01((r - Math.max(g, b) * 0.85) / mx);
    case "orange":
      // Naranja: R alto, G medio, B bajo (R claramente > G)
      return clamp01((r - g * 0.72 - b * 0.4) / mx);
    case "yellow":
      // Amarillo: R y G altos y cercanos, B bajo
      return clamp01((Math.min(r, g) - b * 0.9) / mx);
    case "green":
      return clamp01((g - Math.max(r, b) * 0.75) / mx);
    case "cyan":
      return clamp01((Math.min(g, b) - r * 0.6) / mx);
    case "blue":
      return clamp01((b - Math.max(r, g) * 0.75) / mx);
    case "magenta":
      return clamp01((Math.min(r, b) - g * 0.55) / mx);
    default:
      return 0;
  }
}

function clamp01(x) {
  return x < 0 ? 0 : x > 1 ? 1 : x;
}

/**
 * Zona calida: reglas explicitas en el rango donde amarillo y naranja se confunden (h 18-58).
 */
function classifyWarmPixel(h, s, v, r, g, b) {
  const rg = r / Math.max(g, 1);
  const yb = Math.min(r, g) / Math.max(b, 1);

  // Rojo puro: tono muy bajo o wrap, R domina claramente
  if (h < 12 || h >= 348) {
    if (rg > 1.25 && r > b + 25) return "RED";
  }
  if (h < 18 && rg > 1.4) return "RED";

  // Amarillo: G casi al nivel de R, ambos >> B (post-it, marcador amarillo)
  if (h >= 38 && h < 62) {
    if (g >= r * 0.78 && yb > 2.2) return "YELLOW";
    if (g >= r * 0.72 && s > 0.55) return "YELLOW";
  }

  // Naranja: R > G con margen claro, tono intermedio
  if (h >= 14 && h < 40) {
    if (rg > 1.12 && rg < 1.75 && r > b + 30) return "ORANGE";
  }

  // Zona ambigua 28-48: decidir por proporcion R:G
  if (h >= 28 && h < 48) {
    if (g >= r * 0.88) return "YELLOW";
    if (rg > 1.08) return "ORANGE";
  }

  return null;
}

/**
 * Zona verde-lima vs amarillo (h 52-78) y verde vs cian (h 155-205).
 */
function classifyMidPixel(h, s, r, g, b) {
  if (h >= 52 && h < 78) {
    if (g >= r * 0.92 && g > b + 20) return "GREEN";
    if (g >= r * 0.75 && r > b) return "YELLOW";
  }
  if (h >= 155 && h < 205) {
    const gb = (g + b) / 2;
    if (b > r + 15 && b >= g * 0.85) return "CYAN";
    if (g > r + 20) return "GREEN";
  }
  return null;
}

/**
 * Elige el color con mejor puntuacion combinada (tono + saturacion + RGB).
 */
function scoreColorMatch(h, s, v, r, g, b, proto) {
  let hd = hueDist(h, proto.hue);
  if (proto.hueWrap && (h > 300 || h < 60)) {
    hd = Math.min(hd, hueDist(h, 360));
  }
  if (hd > proto.hueSigma * 1.35) return -1;

  const hueScore = 1 - hd / proto.hueSigma;
  const satScore = s >= proto.sMin ? 1 : s / proto.sMin;
  const rgbScore = rgbChannelScore(r, g, b, proto.rgbHint);
  // Peso mayor al tono; RGB desambigua amarillo/naranja/rojo
  return hueScore * 0.52 + satScore * 0.23 + rgbScore * 0.25;
}

/**
 * Clasifica un pixel: HSV + prototipos + reglas RGB para colores parecidos.
 */
function classifyPixel(r, g, b) {
  const [h, s, v] = rgbToHsv(r, g, b);

  if (v < 0.12) return "BLACK";
  if (s < 0.12 && v > 0.75) return "WHITE";
  if (s < 0.20) return "BLACK";

  const isWarm = h < 78 || h >= 338;
  if (isWarm && s < 0.48) return "BLACK";

  const warmRule = classifyWarmPixel(h, s, v, r, g, b);
  if (warmRule) return warmRule;

  const midRule = classifyMidPixel(h, s, r, g, b);
  if (midRule) return midRule;

  let best = "BLACK";
  let bestScore = -1;
  for (const proto of COLOR_PROTOTYPES) {
    if (proto.sMin > 0.45 && s < proto.sMin) continue;
    const sc = scoreColorMatch(h, s, v, r, g, b, proto);
    if (sc > bestScore) {
      bestScore = sc;
      best = proto.name;
    }
  }
  if (bestScore < 0.25) return "BLACK";
  return best;
}

/* Funciones legacy mantenidas para compatibilidad externa */
function inRangeRgb(r, g, b, spec) {
  const mn = spec.rgbMin;
  const mx = spec.rgbMax;
  return r >= mn[0] && r <= mx[0] && g >= mn[1] && g <= mx[1] && b >= mn[2] && b <= mx[2];
}
function fitScore(r, g, b, spec) {
  const mn = spec.rgbMin;
  const mx = spec.rgbMax;
  let sc = 0;
  for (let i = 0; i < 3; i++) {
    const mid = (mn[i] + mx[i]) * 0.5;
    const half = Math.max((mx[i] - mn[i]) * 0.5, 1);
    const vals = [r, g, b];
    sc += Math.abs(vals[i] - mid) / half;
  }
  return sc;
}

function decodeRgb565Base64(base64, w, h) {
  const binary = atob(base64);
  const need = w * h * 2;
  if (binary.length < need) return null;
  const pixels = new Uint8Array(w * h * 3);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const si = (y * w + x) * 2;
      const [r, g, b] = rgb565ToRgb(binary.charCodeAt(si), binary.charCodeAt(si + 1));
      const pi = (y * w + x) * 3;
      pixels[pi] = r;
      pixels[pi + 1] = g;
      pixels[pi + 2] = b;
    }
  }
  return pixels;
}

/**
 * Analiza buffer rgb565 (base64 o pixels Uint8Array RGB interleaved).
 *
 * Estrategia:
 *  1. Clasificacion HSV por pixel en un solo paso → array `classified`.
 *  2. BFS (flood-fill 4-conexo) sobre `classified` para encontrar componentes
 *     conectadas de cada color → cada grupo espacialmente separado recibe su
 *     propio bounding box (ej: mano ORANGE + barril ORANGE = dos cajas distintas).
 *  3. Solo se muestran blobs que superen MIN_BLOB_PCT del total de pixeles.
 *
 * @returns contrato vision del dashboard con array `blobs` (cuadros delimitadores)
 */
function analyzeRgb565(pixelsOrBase64, w, h, displayW, displayH, opts) {
  const o = opts || {};
  const dw = displayW || 320;
  const dh = displayH || 240;
  // Un blob debe cubrir al menos este % del frame para mostrarse
  const MIN_BLOB_PCT = o.minBlobPct ?? 2;
  // Maximo de cajas por color (las mas grandes)
  const MAX_BLOBS_PER_COLOR = 3;

  let pixels = pixelsOrBase64;
  if (typeof pixelsOrBase64 === "string") {
    pixels = decodeRgb565Base64(pixelsOrBase64, w, h);
    if (!pixels) return null;
  }

  const total = w * h;
  if (!total) return null;

  const N = COLOR_ORDER.length;

  // Mapeo nombre → indice (evita indexOf en loop)
  const colorToIdx = {};
  COLOR_ORDER.forEach((c, i) => { colorToIdx[c] = i; });
  const BLACK_IDX = colorToIdx["BLACK"];
  const WHITE_IDX = colorToIdx["WHITE"];

  // --- PASO 1: clasificar todos los pixeles ---
  const classified = new Uint8Array(total);
  const counts     = new Int32Array(N);
  const centSumX   = new Float32Array(N);
  const centSumY   = new Float32Array(N);

  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const pi = (y * w + x) * 3;
      const ci = colorToIdx[classifyPixel(pixels[pi], pixels[pi + 1], pixels[pi + 2])];
      const li = y * w + x;
      classified[li] = ci;
      counts[ci]++;
      centSumX[ci] += x;
      centSumY[ci] += y;
    }
  }

  // --- Estadisticas globales de color (para grafica y color dominante) ---
  const ranked = COLOR_ORDER.map((color, ci) => ({
    color,
    pct: Math.round((counts[ci] / total) * 100),
    n: counts[ci],
  })).filter((a) => a.n > 0).sort((a, b) => b.pct - a.pct);

  let analysis = ranked.slice(0, ANALYSIS_TOP_N).map(({ color, pct }) => ({ color, pct }));
  const sumPct = analysis.reduce((s, a) => s + a.pct, 0);
  if (analysis.length && sumPct !== 100) {
    analysis[0].pct = Math.max(0, analysis[0].pct + (100 - sumPct));
  }

  const dominant_color = ranked.length ? ranked[0].color : "BLACK";
  const domPct = ranked.length ? ranked[0].pct : 0;

  const domCi = colorToIdx[dominant_color];
  const dn = counts[domCi];
  let tx = Math.floor(dw / 2);
  let ty = Math.floor(dh / 2);
  if (dn > 0) {
    tx = Math.round((centSumX[domCi] / dn) * (dw / w));
    ty = Math.round((centSumY[domCi] / dn) * (dh / h));
  }

  const target_detected =
    domPct >= (o.minTargetPct ?? TARGET_MIN_PCT) &&
    dominant_color !== "BLACK" &&
    dn > 0;

  // --- PASO 2: BFS por color para encontrar blobs separados ---
  const scaleX  = dw / w;
  const scaleY  = dh / h;
  const visited = new Uint8Array(total);
  const blobs   = [];
  // Cola reutilizable (evita aloc en cada BFS)
  const queue   = new Int32Array(total);

  for (let ci = 0; ci < N; ci++) {
    if (ci === BLACK_IDX || ci === WHITE_IDX) continue;
    // Saltar colores con muy pocos pixeles (< 1% del frame)
    if ((counts[ci] / total) * 100 < 1) continue;

    visited.fill(0);
    const colorBlobs = [];

    for (let si = 0; si < total; si++) {
      if (classified[si] !== ci || visited[si]) continue;

      // BFS desde este pixel semilla
      queue[0] = si;
      visited[si] = 1;
      let head = 0;
      let tail = 1;

      let minX = si % w;
      let minY = (si / w) | 0;
      let maxX = minX;
      let maxY = minY;
      let sumX = 0;
      let sumY = 0;
      let count = 0;

      while (head < tail) {
        const idx = queue[head++];
        const px  = idx % w;
        const py  = (idx / w) | 0;

        if (px < minX) minX = px; else if (px > maxX) maxX = px;
        if (py < minY) minY = py; else if (py > maxY) maxY = py;
        sumX += px;
        sumY += py;
        count++;

        // 4 vecinos (sin alocacion de array)
        let n;
        if (px > 0)   { n = idx - 1; if (!visited[n] && classified[n] === ci) { visited[n] = 1; queue[tail++] = n; } }
        if (px < w-1) { n = idx + 1; if (!visited[n] && classified[n] === ci) { visited[n] = 1; queue[tail++] = n; } }
        if (py > 0)   { n = idx - w; if (!visited[n] && classified[n] === ci) { visited[n] = 1; queue[tail++] = n; } }
        if (py < h-1) { n = idx + w; if (!visited[n] && classified[n] === ci) { visited[n] = 1; queue[tail++] = n; } }
      }

      const blobPct = (count / total) * 100;
      if (blobPct >= MIN_BLOB_PCT) {
        colorBlobs.push({
          color: COLOR_ORDER[ci],
          rect: {
            x: Math.round(minX * scaleX),
            y: Math.round(minY * scaleY),
            w: Math.round((maxX - minX + 1) * scaleX),
            h: Math.round((maxY - minY + 1) * scaleY),
          },
          centroid: {
            x: Math.round((sumX / count) * scaleX),
            y: Math.round((sumY / count) * scaleY),
          },
          pct: Math.round(blobPct),
          pixelCount: count,
        });
      }
    }

    // Solo las N cajas mas grandes por color
    colorBlobs.sort((a, b) => b.pct - a.pct);
    for (let k = 0; k < Math.min(colorBlobs.length, MAX_BLOBS_PER_COLOR); k++) {
      blobs.push(colorBlobs[k]);
    }
  }

  blobs.sort((a, b) => b.pct - a.pct);

  return {
    target_detected,
    target_coords: { x: tx, y: ty },
    dominant_color,
    analysis,
    blobs,
    _meta: { frameW: w, frameH: h, analyzedAt: Date.now() },
  };
}

/**
 * Detecta blobs de color directamente sin calcular analisis completo.
 * Util para llamadas independientes al analisis completo.
 */
function detectColorBlobs(pixelsOrBase64, w, h, displayW, displayH, minBlobPct) {
  const result = analyzeRgb565(pixelsOrBase64, w, h, displayW, displayH, { minBlobPct: minBlobPct ?? 3 });
  return result ? result.blobs : [];
}

function analyzeFromCameraPayload(cam, displayW, displayH) {
  if (!cam || !cam.data) return null;
  const fmt = (cam.format || "rgb565").toLowerCase();
  if (fmt !== "rgb565") return null;
  const w = cam.width || 80;
  const h = cam.height || 60;
  return analyzeRgb565(cam.data, w, h, displayW, displayH);
}

/** Muestreo por celdas para overlay (cols x rows) */
function gridColorMix(pixelsOrBase64, w, h, cols, rows) {
  let pixels = pixelsOrBase64;
  if (typeof pixelsOrBase64 === "string") {
    pixels = decodeRgb565Base64(pixelsOrBase64, w, h);
    if (!pixels) return null;
  }
  const out = [];
  const cellW = w / cols;
  const cellH = h / rows;
  for (let gy = 0; gy < rows; gy++) {
    for (let gx = 0; gx < cols; gx++) {
      const counts = {};
      const x0 = Math.floor(gx * cellW);
      const x1 = Math.floor((gx + 1) * cellW);
      const y0 = Math.floor(gy * cellH);
      const y1 = Math.floor((gy + 1) * cellH);
      let n = 0;
      for (let y = y0; y < y1; y++) {
        for (let x = x0; x < x1; x++) {
          const pi = (y * w + x) * 3;
          const c = classifyPixel(pixels[pi], pixels[pi + 1], pixels[pi + 2]);
          counts[c] = (counts[c] || 0) + 1;
          n++;
        }
      }
      let dom = "BLACK";
      let best = 0;
      for (const [c, cnt] of Object.entries(counts)) {
        if (cnt > best) {
          best = cnt;
          dom = c;
        }
      }
      out.push({ gx, gy, color: dom, pct: n ? Math.round((best / n) * 100) : 0 });
    }
  }
  return out;
}

window.VisionColor = {
  COLOR_RANGES,
  COLOR_ORDER,
  COLOR_PROTOTYPES,
  TARGET_MIN_PCT,
  CAMERA_VISION_TTL_MS,
  classifyPixel,
  rgbToHsv,
  analyzeRgb565,
  analyzeFromCameraPayload,
  decodeRgb565Base64,
  gridColorMix,
  detectColorBlobs,
};
