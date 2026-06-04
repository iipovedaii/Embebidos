/* ============================================================
 * SISEMB · Robot Telemetry Dashboard
 * Cliente simpleBroker (WebSocket JSON-line).
 * Sin frameworks: solo DOM nativo + Chart.js.
 * ============================================================ */

"use strict";

/* ---------- Configuracion ---------- */
/** WS al broker en la misma máquina que sirve el dashboard (hostname del navegador). */
const BROKER_WS_HOST =
  (typeof window !== "undefined" && window.location?.hostname) || "127.0.0.1";

const CONFIG = {
  BROKER_WS_URL: `ws://${BROKER_WS_HOST}:5052`,
  TOPIC: "robot/telemetry",
  TOPIC_CMD: "robot/commands",
  TOPIC_CAMERA: "robot/camera",
  DRIVE_PWM: 70,
  DRIVE_TURN_INNER_PWM: 5,
  DRIVE_TURN_OUTER_PWM: 100,
  MEARM_STEP_DEG: 5,
  /** Velocidad al mantener +/− (grados por segundo) */
  MEARM_SMOOTH_SPEED_DEG_S: 95,
  /** Mínimo entre comandos MQTT al broker durante el arrastre (ms) */
  MEARM_PUBLISH_INTERVAL_MS: 45,
  LATENCY_REFRESH_MS: 1000,
  PICO_OFFLINE_MS: 2000,
  MAX_IR_LINES: 50,
};

const COLOR_TABLE = {
  RED:    { hex: "#ef4444" },
  GREEN:  { hex: "#22c55e" },
  BLUE:   { hex: "#3b82f6" },
  YELLOW: { hex: "#eab308" },
  CYAN:   { hex: "#06b6d4" },
  MAGENTA:{ hex: "#d946ef" },
  WHITE:  { hex: "#e5e7eb" },
  BLACK:  { hex: "#0f172a" },
  ORANGE: { hex: "#f97316" },
  PURPLE: { hex: "#a855f7" },
};

const USONIC = {
  MIN_CM: 2,
  MAX_CM: 400,
  THRESHOLDS: { CRITICAL: 15, WARNING: 35, OK: 120 },
  HISTORY_MAX: 120,
  ZONES: {
    CRITICAL:     { label: "CRITICO",   hint: "Objeto muy cerca — detener o retroceder", state: "error",    bar: "bg-neon-red",    color: "#ff3b3b" },
    WARNING:      { label: "CERCA",     hint: "Precaucion — reducir velocidad",          state: "warn",     bar: "bg-neon-amber",  color: "#ff9f1c" },
    OK:           { label: "SEGURA",    hint: "Distancia operativa normal",              state: "active",   bar: "bg-neon-orange", color: "#ff6b35" },
    CLEAR:        { label: "LEJOS",     hint: "Sin obstaculos cercanos",               state: "forward",  bar: "bg-neon-orange", color: "#fb923c" },
    OUT_OF_RANGE: { label: "FUERA RANGO", hint: "Sin eco valido o fuera de 2–400 cm",  state: "idle",     bar: "bg-red-900",     color: "#64748b" },
  },
};

const SERVO_RANGES = {
  base:     { min: 0, max: 180, color: "bg-neon-orange", label: "Base", glyph: "↻" },
  shoulder: { min: 0, max: 180, color: "bg-neon-red",    label: "Hombro", glyph: "⌒" },
  elbow:    { min: 100, max: 150, color: "bg-neon-amber",  label: "Codo", glyph: "∠" },
  gripper:  { min: 0, max: 180, color: "bg-neon-ember",  label: "Pinza", glyph: "◧" },
};

/* ---------- Estado global ---------- */
const state = {
  ws: null,
  wsConnected: false,
  pingTimer: null,
  lastIrTs: 0,
  irCount: 0,
  chart: null,
  lastTelemetry: null,
  lastTelemetryAt: 0,
  hasTelemetry: false,
  picoOnline: false,
  lastMeArm: null,
  lastVision: null,
  lastTelemetryVision: null,
  visionFromCamera: null,
  visionFromCameraAt: 0,
  lastCameraPayload: null,
  lastGridMix: null,
  lastCameraAt: 0,
  lastCameraFrameId: -1,
  lastCameraTs: -1,
  usonicHistory: [],
  usonicPrev: null,
  usonicZonesReady: false,
};

/* ============================================================
 * Inicializacion
 * ============================================================ */
document.addEventListener("DOMContentLoaded", () => {
  buildServos();
  buildChart();
  drawStreamPlaceholder();
  bindDriveControls();
  bindMeArmControls();
  startPicoWatchdog();
  tryConnectMqtt();
  if (window.lucide) lucide.createIcons();
  if (window.initTwin) window.initTwin();
  initUsonicZoneArcs(USONIC.MIN_CM, USONIC.MAX_CM);
  drawUsonicHistory();
});

/* ============================================================
 * Servos: construye dinamicamente las 4 barras
 * ============================================================ */
function buildServos() {
  const grid = document.getElementById("servoGrid");
  if (!grid) return;
  grid.innerHTML = "";
  for (const name of Object.keys(SERVO_RANGES)) {
    const range = SERVO_RANGES[name];
    const el = document.createElement("div");
    el.className = `servo servo--${name}`;
    el.innerHTML = `
      <div class="servo__top">
        <div class="servo__identity">
          <span class="servo__glyph" aria-hidden="true">${range.glyph}</span>
          <div>
            <span class="servo-name">${range.label}</span>
            <span class="servo__axis">${name}</span>
          </div>
        </div>
        <div class="servo__dial">
          <button type="button" class="servo-step" data-servo-dec="${name}" title="-${CONFIG.MEARM_STEP_DEG}°">−</button>
          <span class="servo-val"><span data-servo-val="${name}">--</span><small>°</small></span>
          <button type="button" class="servo-step" data-servo-inc="${name}" title="+${CONFIG.MEARM_STEP_DEG}°">+</button>
        </div>
      </div>
      <div class="servo__track">
        <div class="bar bar--servo">
          <div class="bar-fill ${range.color}" data-servo-bar="${name}"></div>
        </div>
        <span class="servo__range">${range.min}–${range.max}°</span>
      </div>
      <div class="servo__target">
        <label class="servo__target-label">Objetivo</label>
        <input type="number" class="servo-angle-in" data-servo-input="${name}" min="${range.min}" max="${range.max}" step="1" placeholder="0–180" aria-label="${range.label} ángulo" />
        <button type="button" class="servo-angle-apply" data-servo-apply="${name}">Ir</button>
      </div>
    `;
    grid.appendChild(el);
  }
}

/* ============================================================
 * Chart.js: barra horizontal para analisis de color
 * ============================================================ */
function buildChart() {
  const ctx = document.getElementById("colorChart");
  if (!ctx) return;
  state.chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: [],
      datasets: [
        {
          label: "Presencia (%)",
          data: [],
          backgroundColor: [],
          borderRadius: 6,
          borderSkipped: false,
        },
      ],
    },
    options: {
      indexAxis: "y",
      animation: { duration: 400, easing: "easeOutCubic" },
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(12,4,6,0.95)",
          borderColor: "rgba(255,107,53,0.35)",
          borderWidth: 1,
          titleColor: "#fecaca",
          bodyColor: "#fca5a5",
        },
      },
      scales: {
        x: {
          max: 100,
          grid: { color: "rgba(255,59,59,0.08)" },
          ticks: {
            color: "#a8a29e",
            font: { family: "JetBrains Mono", size: 10 },
            callback: (v) => v + "%",
          },
        },
        y: {
          grid: { display: false },
          ticks: {
            color: "#fecaca",
            font: { family: "JetBrains Mono", size: 11 },
          },
        },
      },
    },
  });
}

function hexToRgba(hex, alpha) {
  const h = (hex || "#000").replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(full, 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}

function getEffectiveVision(telemetryVision) {
  const cam = state.visionFromCamera;
  const ttl = window.VisionColor?.CAMERA_VISION_TTL_MS ?? 4000;
  if (cam && state.visionFromCameraAt && Date.now() - state.visionFromCameraAt < ttl) {
    return cam;
  }
  return telemetryVision || state.lastTelemetryVision || state.lastVision;
}

function colorForCell(gx, gy, analysis, dominant) {
  const items = (analysis || []).filter((a) => (a.pct ?? 0) > 0);
  if (!items.length) {
    const dom = (dominant || "RED").toUpperCase();
    return COLOR_TABLE[dom]?.hex || "#ef4444";
  }
  const seed = gx * 17 + gy * 31;
  let acc = 0;
  const target = (seed % 100) + 1;
  for (const a of items) {
    acc += a.pct ?? 0;
    if (target <= acc) return COLOR_TABLE[(a.color || "").toUpperCase()]?.hex || "#94a3b8";
  }
  const last = items[items.length - 1].color || dominant || "RED";
  return COLOR_TABLE[last.toUpperCase()]?.hex || "#94a3b8";
}

function drawVisionOverlay(v) {
  const stream = document.getElementById("streamCanvas");
  const overlay = document.getElementById("visionOverlayCanvas");
  if (!stream || !overlay || !v) return;

  const ctx = overlay.getContext("2d");
  const W = overlay.width;
  const H = overlay.height;

  // Base: copia el frame actual de la camara
  ctx.drawImage(stream, 0, 0, W, H);

  const blobs = v.blobs || [];
  ctx.save();

  for (const blob of blobs) {
    const { color, rect, centroid, pct } = blob;
    const name = (color || "").toUpperCase();
    const hex = COLOR_TABLE[name]?.hex || "#94a3b8";
    const { x, y, w, h } = rect;

    // Relleno semitransparente
    ctx.fillStyle = hexToRgba(hex, 0.18);
    ctx.fillRect(x, y, w, h);

    // Borde del rectangulo
    ctx.strokeStyle = hex;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([]);
    ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);

    // Esquinas decorativas (estilo HUD tecnico)
    const cs = Math.min(12, Math.floor(Math.min(w, h) * 0.25));
    ctx.strokeStyle = hex;
    ctx.lineWidth = 2.5;
    // Superior izquierda
    ctx.beginPath();
    ctx.moveTo(x, y + cs); ctx.lineTo(x, y); ctx.lineTo(x + cs, y);
    ctx.stroke();
    // Superior derecha
    ctx.beginPath();
    ctx.moveTo(x + w - cs, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + cs);
    ctx.stroke();
    // Inferior izquierda
    ctx.beginPath();
    ctx.moveTo(x, y + h - cs); ctx.lineTo(x, y + h); ctx.lineTo(x + cs, y + h);
    ctx.stroke();
    // Inferior derecha
    ctx.beginPath();
    ctx.moveTo(x + w - cs, y + h); ctx.lineTo(x + w, y + h); ctx.lineTo(x + w, y + h - cs);
    ctx.stroke();

    // Etiqueta: color + %
    const labelText = `${name} ${pct}%`;
    ctx.font = "bold 10px JetBrains Mono, monospace";
    const textMetrics = ctx.measureText(labelText);
    const lw = textMetrics.width + 8;
    const lh = 14;
    const lx = x;
    const ly = y >= lh + 2 ? y - lh - 2 : y + h + 2;

    ctx.fillStyle = hexToRgba(hex, 0.88);
    ctx.beginPath();
    ctx.roundRect(lx, ly, lw, lh, 3);
    ctx.fill();
    ctx.fillStyle = "#0a0a0a";
    ctx.fillText(labelText, lx + 4, ly + lh - 3);

    // Punto de centroide
    ctx.fillStyle = hex;
    ctx.beginPath();
    ctx.arc(centroid.x, centroid.y, 3.5, 0, Math.PI * 2);
    ctx.fill();

    // Cruz en centroide (micro crosshair)
    ctx.strokeStyle = hexToRgba(hex, 0.75);
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.moveTo(centroid.x - 9, centroid.y);
    ctx.lineTo(centroid.x + 9, centroid.y);
    ctx.moveTo(centroid.x, centroid.y - 9);
    ctx.lineTo(centroid.x, centroid.y + 9);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  ctx.restore();

  // Leyenda inferior
  const legend = document.getElementById("visionLegend");
  if (legend) {
    legend.innerHTML = (v.analysis || [])
      .map((a) => {
        const name = (a.color || "").toUpperCase();
        const hex = COLOR_TABLE[name]?.hex || "#94a3b8";
        const pct = Math.round(a.pct ?? 0);
        return `<span class="vision-legend-item" style="--chip:${hex}"><i></i>${name} ${pct}%</span>`;
      })
      .join("");
  }
}

function encodePacket(action, topic, data) {
  return JSON.stringify({ action, topic, data });
}

function sendPacket(action, topic, data) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return false;
  state.ws.send(encodePacket(action, topic, data) + "\n");
  return true;
}

/** Extrae líneas JSON del buffer WS (con o sin \\n final por mensaje). */
function drainBrokerLines(rxBuf) {
  const lines = [];
  let rest = rxBuf;
  for (;;) {
    const nl = rest.indexOf("\n");
    if (nl >= 0) {
      const line = rest.slice(0, nl).trim();
      rest = rest.slice(nl + 1);
      if (line) lines.push(line);
      continue;
    }
    const trimmed = rest.trim();
    if (trimmed.startsWith("{")) {
      try {
        JSON.parse(trimmed);
        lines.push(trimmed);
        rest = "";
      } catch {
        /* JSON incompleto, esperar más datos */
      }
    }
    break;
  }
  return { lines, rest };
}

function normalizeBrokerData(data) {
  if (typeof data === "string") {
    try {
      return JSON.parse(data);
    } catch {
      return null;
    }
  }
  return data;
}

function handleBrokerPub(pkt) {
  const topic = pkt.topic;
  let data = normalizeBrokerData(pkt.data);
  if (!data) return;
  if (topic === CONFIG.TOPIC_CAMERA) {
    handleCameraMessage(data);
  } else if (topic === CONFIG.TOPIC) {
    state.lastTelemetry = data;
    render(data);
    updateLatencyFromTelemetry();
  } else if (topic === "robot/heartbeat") {
    touchTelemetry();
  }
}

function drawRgb565ToCanvas(ctx, base64, w, h, destW, destH) {
  const binary = atob(base64);
  const len = w * h * 2;
  if (binary.length < len) return;
  const img = ctx.createImageData(destW, destH);
  for (let y = 0; y < destH; y++) {
    const sy = Math.floor((y * h) / destH);
    for (let x = 0; x < destW; x++) {
      const sx = Math.floor((x * w) / destW);
      const si = (sy * w + sx) * 2;
      const c0 = binary.charCodeAt(si);
      const c1 = binary.charCodeAt(si + 1);
      // Firmware publica RGB565 little-endian (tras swap wire OV7670)
      const v = c0 | (c1 << 8);
      const di = (y * destW + x) * 4;
      img.data[di] = ((v >> 11) & 0x1f) << 3;
      img.data[di + 1] = ((v >> 5) & 0x3f) << 2;
      img.data[di + 2] = (v & 0x1f) << 3;
      img.data[di + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
}

function runCameraColorAnalysis(cam) {
  if (!window.VisionColor || !cam?.data) return null;
  const fmt = (cam.format || "rgb565").toLowerCase();
  if (fmt !== "rgb565") return null;

  const stream = document.getElementById("streamCanvas");
  const dw = stream?.width || 320;
  const dh = stream?.height || 240;
  const w = cam.width || 80;
  const h = cam.height || 60;

  const vision = window.VisionColor.analyzeFromCameraPayload(cam, dw, dh);
  if (!vision) return null;

  state.visionFromCamera = vision;
  state.visionFromCameraAt = Date.now();
  state.lastCameraPayload = cam;
  state.lastGridMix = window.VisionColor.gridColorMix(cam.data, w, h, 10, 8);
  return vision;
}

function refreshVisionUi() {
  const v = getEffectiveVision(state.lastTelemetryVision);
  if (v) renderVision(v);
}

function dbgCamLog(hypothesisId, location, message, data) {
  const entry = {
    sessionId: "9facb1",
    runId: "post-fix",
    hypothesisId,
    location,
    message,
    data: data || {},
    timestamp: Date.now(),
  };
  try {
    const logs = JSON.parse(sessionStorage.getItem("dbgCam9facb1") || "[]");
    logs.push(entry);
    if (logs.length > 80) logs.splice(0, logs.length - 80);
    sessionStorage.setItem("dbgCam9facb1", JSON.stringify(logs));
  } catch (_) {}
  console.log("[DBG_CAM]", message, data);
  // #region agent log
  fetch("http://127.0.0.1:7565/ingest/2ef15bf1-7a17-49be-859e-1135742a761d", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "9facb1" },
    body: JSON.stringify({
      sessionId: "9facb1",
      runId: "post-fix",
      hypothesisId,
      location,
      message,
      data: data || {},
      timestamp: Date.now(),
    }),
  }).catch(() => {});
  // #endregion
}

function drawCameraFrame(cam) {
  const stream = document.getElementById("streamCanvas");
  const overlay = document.getElementById("visionOverlayCanvas");
  if (!stream || !cam?.data) {
    dbgCamLog("D", "app.js:drawCameraFrame", "skip no canvas or data", {
      hasStream: !!stream,
      hasData: !!cam?.data,
      source: cam?.source,
    });
    return;
  }

  const src = (cam.source || "").toLowerCase();
  const isStub = src === "ov7670_stub";

  const fid = cam.frame_id;
  const ts = cam.ts;
  if (
    fid != null &&
    fid === state.lastCameraFrameId &&
    ts != null &&
    ts === state.lastCameraTs
  ) {
    dbgCamLog("D", "app.js:drawCameraFrame", "duplicate frame skipped", { frame_id: fid, ts });
    return;
  }
  if (fid != null) state.lastCameraFrameId = fid;
  if (ts != null) state.lastCameraTs = ts;

  const W = stream.width;
  const H = stream.height;
  const ctx = stream.getContext("2d");
  const fmt = (cam.format || "jpeg").toLowerCase();

  const afterDraw = () => {
    state.lastCameraAt = Date.now();
    state.lastCameraSource = src || "ov7670";
    runCameraColorAnalysis(cam);
    refreshVisionUi();
    if (isStub) {
      const octx = document.getElementById("visionOverlayCanvas")?.getContext("2d");
      if (octx) {
        octx.fillStyle = "rgba(255, 107, 53, 0.9)";
        octx.font = "10px JetBrains Mono, monospace";
        octx.fillText("MODO PRUEBA (sin OV7670 I2C)", 10, 18);
      }
    }
  };

  if (fmt === "jpeg") {
    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, 0, 0, W, H);
      afterDraw();
    };
    img.onerror = () => console.warn("[camera] JPEG invalido");
    img.src = "data:image/jpeg;base64," + cam.data;
    return;
  }

  if (fmt === "rgb565") {
    dbgCamLog("C", "app.js:drawCameraFrame", "drawing rgb565", {
      w: cam.width,
      h: cam.height,
      b64_len: cam.data?.length,
      source: src,
      dbg: cam.dbg,
    });
    drawRgb565ToCanvas(ctx, cam.data, cam.width || 80, cam.height || 60, W, H);
    afterDraw();
    return;
  }

  dbgCamLog("C", "app.js:drawCameraFrame", "unknown format", { format: fmt, source: src });
}

function handleCameraMessage(cam) {
  try {
    dbgCamLog("C", "app.js:handleCameraMessage", "mqtt camera rx", {
      format: cam?.format,
      source: cam?.source,
      w: cam?.width,
      h: cam?.height,
      b64_len: cam?.data?.length,
      frame_id: cam?.frame_id,
      dbg: cam?.dbg,
    });
    drawCameraFrame(cam);
  } catch (e) {
    dbgCamLog("C", "app.js:handleCameraMessage", "draw error", { err: String(e) });
    console.warn("[camera] frame:", e);
  }
}

function drawWaitingCanvas(ctx, W, H, message) {
  ctx.fillStyle = "rgba(12, 4, 6, 0.98)";
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = "rgba(255, 107, 53, 0.85)";
  ctx.font = "11px JetBrains Mono, monospace";
  ctx.fillText(message, 12, H - 14);
}

function drawStreamPlaceholder() {
  const canvas = document.getElementById("streamCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;

  let frame = 0;
  let drewWaitTelemetry = false;
  function loop() {
    frame++;
    const hasCam = state.lastCameraAt > 0;
    const waitingTelemetry = !state.hasTelemetry;

    if (hasCam) {
      drewWaitTelemetry = false;
    } else if (waitingTelemetry) {
      if (!drewWaitTelemetry || frame % 120 === 0) {
        drawWaitingCanvas(ctx, W, H, "esperando telemetria");
        drewWaitTelemetry = true;
      }
    } else if (frame % 120 === 0) {
      const cam = state.lastTelemetry?.camera;
      let msg = "esperando robot/camera";
      if (cam?.ready && cam?.stub) msg = "sin frames · stub I2C (revisa firmware/config en Pico)";
      else if (cam?.ready === false) msg = "camara deshabilitada en firmware";
      drawWaitingCanvas(ctx, W, H, msg);
    }

    const v = getEffectiveVision(state.lastTelemetryVision);
    if (v && (state.hasTelemetry || hasCam)) {
      drawVisionOverlay(v);
    }
    requestAnimationFrame(loop);
  }
  loop();
}

/* ============================================================
 * Comandos → Pico (simpleBroker)
 * ============================================================ */
function mqttConnected() {
  return !!(state.ws && state.ws.readyState === WebSocket.OPEN && state.wsConnected);
}

function publishCommand(payload) {
  if (!mqttConnected()) {
    console.warn("[broker] no conectado");
    return false;
  }
  const msg = typeof payload === "string" ? JSON.parse(payload) : payload;
  if (!sendPacket("PUB", CONFIG.TOPIC_CMD, msg)) return false;
  console.log("[broker] →", CONFIG.TOPIC_CMD, msg);
  return true;
}

/* ============================================================
 * Comandos de conduccion (dashboard → Pico)
 * ============================================================ */
const DRIVE_CMD_MAP = {
  arrowF: "FWD",
  arrowB: "REV",
  arrowL: "LEFT",
  arrowR: "RIGHT",
  arrowS: "STOP",
};

let _driveSession = null;

function stopDriveSession() {
  if (!_driveSession) return;
  const { el } = _driveSession;
  _driveSession = null;
  el?.classList.remove("active");
  publishDriveCommand("STOP");
}

function bindDriveControls() {
  for (const [id, cmd] of Object.entries(DRIVE_CMD_MAP)) {
    const el = document.getElementById(id);
    if (!el) continue;
    el.style.cursor = "pointer";

    if (cmd === "STOP") {
      el.addEventListener("click", (e) => { e.preventDefault(); publishDriveCommand("STOP"); });
      continue;
    }

    el.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 && e.button !== undefined) return;
      e.preventDefault();
      try { el.setPointerCapture(e.pointerId); } catch (_) { /* SVG puede no tenerlo */ }
      _driveSession = { el, cmd };
      el.classList.add("active");
      publishDriveCommand(cmd);
    });

    const endDrive = () => stopDriveSession();
    el.addEventListener("pointerup", endDrive);
    el.addEventListener("pointercancel", endDrive);
    el.addEventListener("lostpointercapture", endDrive);
    el.addEventListener("contextmenu", (e) => e.preventDefault());
  }

  document.querySelectorAll("[data-maneuver]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const code = btn.getAttribute("data-maneuver");
      if (code) publishManeuverCommand(code);
    });
  });

  window.addEventListener("blur", stopDriveSession);
}

function publishDriveCommand(cmd) {
  let lPwm = CONFIG.DRIVE_PWM;
  let rPwm = CONFIG.DRIVE_PWM;
  const key = (cmd || "").toUpperCase();
  if (key === "LEFT") {
    lPwm = CONFIG.DRIVE_TURN_INNER_PWM;
    rPwm = CONFIG.DRIVE_TURN_OUTER_PWM;
  } else if (key === "RIGHT") {
    lPwm = CONFIG.DRIVE_TURN_OUTER_PWM;
    rPwm = CONFIG.DRIVE_TURN_INNER_PWM;
  } else if (key === "STOP") {
    lPwm = 0;
    rPwm = 0;
  }
  if (window.previewDriveMotion) window.previewDriveMotion(key);
  publishCommand({
    cmd: key,
    l_pwm: lPwm,
    r_pwm: rPwm,
    source: "dashboard",
  });
}

function publishManeuverCommand(code) {
  if (window.previewDriveMotion) window.previewDriveMotion(code);
  publishCommand({ cmd: code, source: "dashboard" });
}

let mearmHoldSession = null;

function getMeArmJointAngle(joint) {
  const range = SERVO_RANGES[joint];
  if (!range) return 90;
  const raw =
    state.lastMeArm?.servos?.[joint] ??
    parseInt(document.querySelector(`[data-servo-val="${joint}"]`)?.textContent || "90", 10);
  return clamp(Number(raw), range.min, range.max);
}

function setMeArmJointAngle(joint, angle, opts = {}) {
  const { publish = false, action = "MOVE", syncTwin = true } = opts;
  const range = SERVO_RANGES[joint];
  if (!range) return null;
  const clamped = clamp(angle, range.min, range.max);
  if (!state.lastMeArm) state.lastMeArm = {};
  if (!state.lastMeArm.servos) state.lastMeArm.servos = {};
  state.lastMeArm.servos = { ...state.lastMeArm.servos, [joint]: clamped };
  state.lastMeArm.status = "ACTIVE";
  updateMeArmServoDisplay(joint, clamped);
  if (syncTwin) pushTwinArmServo(joint, clamped, action);
  if (publish) {
    publishCommand({ mearm: { joint, angle: Math.round(clamped) } });
  }
  return clamped;
}

function stopMeArmHold() {
  if (!mearmHoldSession) return;
  cancelAnimationFrame(mearmHoldSession.rafId);
  const { joint, lastAngle, lastPublished } = mearmHoldSession;
  const btn = mearmHoldSession.btn;
  if (joint != null && lastAngle != null) {
    const rounded = Math.round(lastAngle);
    if (rounded !== lastPublished) {
      setMeArmJointAngle(joint, lastAngle, {
        publish: true,
        action: `HOLD_${joint.toUpperCase()}`,
      });
    }
  }
  btn?.classList.remove("servo-step--active", "mearm-tool-btn--active");
  mearmHoldSession = null;
}

function startMeArmSmoothHold(btn, joint, direction, activeClass = "servo-step--active") {
  const range = SERVO_RANGES[joint];
  if (!range || !direction) return;

  stopMeArmHold();
  const startAngle = getMeArmJointAngle(joint);
  const t0 = performance.now();
  let lastPublishMs = 0;
  let lastPublished = Math.round(startAngle);

  btn.classList.add(activeClass);
  mearmHoldSession = {
    btn,
    joint,
    direction,
    startAngle,
    t0,
    lastAngle: startAngle,
    lastPublished,
    rafId: 0,
  };

  const frame = (now) => {
    if (!mearmHoldSession || mearmHoldSession.joint !== joint) return;
    const elapsed = (now - t0) / 1000;
    const angle = clamp(
      startAngle + direction * CONFIG.MEARM_SMOOTH_SPEED_DEG_S * elapsed,
      range.min,
      range.max
    );
    mearmHoldSession.lastAngle = angle;
    setMeArmJointAngle(joint, angle, { publish: false, action: `HOLD_${joint.toUpperCase()}` });

    if (now - lastPublishMs >= CONFIG.MEARM_PUBLISH_INTERVAL_MS) {
      const rounded = Math.round(angle);
      if (rounded !== lastPublished) {
        publishCommand({ mearm: { joint, angle: rounded } });
        lastPublished = rounded;
        mearmHoldSession.lastPublished = rounded;
        lastPublishMs = now;
      }
    }

    mearmHoldSession.rafId = requestAnimationFrame(frame);
  };

  setMeArmJointAngle(joint, startAngle, {
    publish: true,
    action: `HOLD_${joint.toUpperCase()}`,
  });
  mearmHoldSession.lastPublished = Math.round(startAngle);
  lastPublishMs = performance.now();
  mearmHoldSession.rafId = requestAnimationFrame(frame);
}

function bindMeArmSmoothHoldButton(btn, joint, direction, activeClass = "servo-step--active") {
  if (!btn || !joint || !direction) return;
  btn.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    try {
      btn.setPointerCapture(e.pointerId);
    } catch (_) {
      /* ignore */
    }
    startMeArmSmoothHold(btn, joint, direction, activeClass);
  });
  const end = () => stopMeArmHold();
  btn.addEventListener("pointerup", end);
  btn.addEventListener("pointercancel", end);
  btn.addEventListener("lostpointercapture", end);
  btn.addEventListener("contextmenu", (e) => e.preventDefault());
}

function bindMeArmControls() {
  const grid = document.getElementById("servoGrid");
  if (!grid) return;

  grid.querySelectorAll("[data-servo-inc]").forEach((btn) => {
    const joint = btn.getAttribute("data-servo-inc");
    bindMeArmSmoothHoldButton(btn, joint, 1);
  });
  grid.querySelectorAll("[data-servo-dec]").forEach((btn) => {
    const joint = btn.getAttribute("data-servo-dec");
    bindMeArmSmoothHoldButton(btn, joint, -1);
  });

  bindMeArmSmoothHoldButton(
    document.getElementById("mearmGripOpen"),
    "gripper",
    -1,
    "mearm-tool-btn--active"
  );
  bindMeArmSmoothHoldButton(
    document.getElementById("mearmGripClose"),
    "gripper",
    1,
    "mearm-tool-btn--active"
  );

  document.getElementById("mearmHome")?.addEventListener("click", () => {
    const home = state.lastMeArm?.home || { base: 90, shoulder: 70, elbow: 110, gripper: 50 };
    if (window.setTwinArmServos) window.setTwinArmServos(home, "HOME_POSITION");
    publishCommand({ cmd: "HOME_POSITION" });
  });

  grid.querySelectorAll("[data-servo-apply]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const joint = btn.getAttribute("data-servo-apply");
      applyMeArmAngleFromInput(joint);
    });
  });
  grid.querySelectorAll("[data-servo-input]").forEach((input) => {
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        applyMeArmAngleFromInput(input.getAttribute("data-servo-input"));
      }
    });
  });

  window.addEventListener("blur", stopMeArmHold);
}

function updateMeArmServoDisplay(joint, val) {
  const range = SERVO_RANGES[joint];
  if (!range || val === undefined) return;
  const pct = clamp(((val - range.min) / (range.max - range.min)) * 100, 0, 100);
  const bar = document.querySelector(`[data-servo-bar="${joint}"]`);
  const txt = document.querySelector(`[data-servo-val="${joint}"]`);
  const inp = document.querySelector(`[data-servo-input="${joint}"]`);
  if (bar) bar.style.width = pct + "%";
  if (txt) txt.textContent = Math.round(val);
  if (inp && document.activeElement !== inp) inp.value = String(Math.round(val));
}

function applyMeArmAngleFromInput(joint) {
  const range = SERVO_RANGES[joint];
  if (!range) return;
  const input = document.querySelector(`[data-servo-input="${joint}"]`);
  if (!input) return;
  const angle = clamp(parseInt(input.value, 10), range.min, range.max);
  if (Number.isNaN(angle)) return;
  input.value = String(angle);
  pushTwinArmServo(joint, angle, `SET_${joint.toUpperCase()}`);
  publishCommand({ mearm: { joint, angle } });
}

function pushTwinArmServo(joint, angle, action = "") {
  if (!window.setTwinArmServos) return;
  const prev = state.lastMeArm?.servos || {};
  window.setTwinArmServos({ ...prev, [joint]: angle }, action, "ACTIVE", state.lastMeArm);
}

function nudgeMeArmJoint(joint, delta) {
  const cur = getMeArmJointAngle(joint);
  const next = cur + delta;
  if (next === cur) return;
  setMeArmJointAngle(joint, next, {
    publish: true,
    action: `NUDGE_${joint.toUpperCase()}`,
  });
}

/* ============================================================
 * simpleBroker WebSocket (modo LIVE)
 * ============================================================ */
function tryConnectMqtt() {
  if (state.ws) {
    try { state.ws.close(); } catch (e) {}
    state.ws = null;
    state.wsConnected = false;
  }

  setBrokerState("connecting");
  let ws;
  try {
    ws = new WebSocket(CONFIG.BROKER_WS_URL);
  } catch (err) {
    console.error("[broker] ws connect error:", err);
    setBrokerState("disconnected");
    return;
  }
  state.ws = ws;
  let rxBuf = "";

  ws.onopen = () => {
    state.wsConnected = true;
    setBrokerState("connected");
    sendPacket("SUB", CONFIG.TOPIC, null);
    sendPacket("SUB", CONFIG.TOPIC_CAMERA, null);
    sendPacket("SUB", "robot/heartbeat", null);
    startPing();
  };

  ws.onmessage = (ev) => {
    rxBuf += String(ev.data || "");
    const drained = drainBrokerLines(rxBuf);
    rxBuf = drained.rest;
    for (const line of drained.lines) {
      try {
        const pkt = JSON.parse(line);
        if (pkt.action === "PUB") handleBrokerPub(pkt);
      } catch (e) {
        console.warn("[broker] line parse error:", e);
      }
    }
  };

  ws.onerror = (err) => {
    console.warn("[broker] ws error:", err);
    state.wsConnected = false;
    setBrokerState("disconnected");
  };
  ws.onclose = () => {
    state.wsConnected = false;
    setBrokerState("disconnected");
    setTimeout(() => {
      if (!state.wsConnected) tryConnectMqtt();
    }, 2500);
  };
}

function updateLatencyFromTelemetry() {
  if (!state.lastTelemetryAt) return;
  setLatency(Math.min(999, Math.round(Date.now() - state.lastTelemetryAt)));
}

function startPing() {
  if (state.pingTimer) clearInterval(state.pingTimer);
  state.pingTimer = setInterval(updateLatencyFromTelemetry, CONFIG.LATENCY_REFRESH_MS);
}

/* ============================================================
 * Render principal: recibe un payload y actualiza el DOM
 * ============================================================ */
function render(data) {
  if (!data) return;
  touchTelemetry();
  if (data.system)    renderSystem(data.system);
  if (data.mearm)     renderMeArm(data.mearm);
  if (data.drive)     renderDrive(data.drive);
  if (data.vision) {
    state.lastTelemetryVision = data.vision;
    renderVision(getEffectiveVision(data.vision));
  }
  if (data.ir_sensor) renderIR(data.ir_sensor);
  if (data.ultrasonic) renderUltrasonic(data.ultrasonic);
  if (window.updateTwin) updateTwin(data.drive, data.mearm);
}

/* ---------- ultrasonico ---------- */
const USONIC_RADAR = { cx: 110, cy: 118, r: 86, x0: 24, y0: 118 };

function usonicDistToAngle(dist, min, max) {
  const t = clamp(1 - (dist - min) / (max - min), 0, 1);
  return Math.PI * t;
}

function usonicArcPath(angleEnd, min, max) {
  const { cx, cy, r, x0, y0 } = USONIC_RADAR;
  const angle = usonicDistToAngle(angleEnd, min, max);
  const x = cx + r * Math.cos(Math.PI - angle);
  const y = cy - r * Math.sin(Math.PI - angle);
  const large = angle > Math.PI / 2 ? 1 : 0;
  return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x.toFixed(1)} ${y.toFixed(1)}`;
}

function usonicZoneSegment(dFrom, dTo, min, max) {
  const { cx, cy, r } = USONIC_RADAR;
  const a0 = usonicDistToAngle(dFrom, min, max);
  const a1 = usonicDistToAngle(dTo, min, max);
  const x0 = cx + r * Math.cos(Math.PI - a0);
  const y0 = cy - r * Math.sin(Math.PI - a0);
  const x1 = cx + r * Math.cos(Math.PI - a1);
  const y1 = cy - r * Math.sin(Math.PI - a1);
  const large = Math.abs(a1 - a0) > Math.PI / 2 ? 1 : 0;
  return `M ${x0.toFixed(1)} ${y0.toFixed(1)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`;
}

function initUsonicZoneArcs(min, max) {
  const T = USONIC.THRESHOLDS;
  const map = {
    usonicZoneCrit: [min, T.CRITICAL],
    usonicZoneWarn: [T.CRITICAL, T.WARNING],
    usonicZoneOk: [T.WARNING, T.OK],
    usonicZoneClear: [T.OK, max],
  };
  for (const [id, [a, b]] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (el) el.setAttribute("d", usonicZoneSegment(a, b, min, max));
  }
  state.usonicZonesReady = true;
}

function drawUsonicHistory() {
  const canvas = document.getElementById("usonicHistory");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;
  const hist = state.usonicHistory;
  const min = USONIC.MIN_CM;
  const max = USONIC.MAX_CM;

  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "rgba(12, 4, 6, 0.95)";
  ctx.fillRect(0, 0, W, H);

  const zones = [
    [min, USONIC.THRESHOLDS.CRITICAL, "rgba(255,59,59,0.12)"],
    [USONIC.THRESHOLDS.CRITICAL, USONIC.THRESHOLDS.WARNING, "rgba(255,159,28,0.1)"],
    [USONIC.THRESHOLDS.WARNING, USONIC.THRESHOLDS.OK, "rgba(255,107,53,0.08)"],
    [USONIC.THRESHOLDS.OK, max, "rgba(251,146,60,0.06)"],
  ];
  zones.forEach(([a, b, col]) => {
    const y0 = H - ((b - min) / (max - min)) * H;
    const y1 = H - ((a - min) / (max - min)) * H;
    ctx.fillStyle = col;
    ctx.fillRect(0, y0, W, y1 - y0);
  });

  if (hist.length < 2) return;

  ctx.strokeStyle = "rgba(255, 107, 53, 0.85)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  hist.forEach((d, i) => {
    const x = (i / (USONIC.HISTORY_MAX - 1)) * W;
    const y = H - clamp((d - min) / (max - min), 0, 1) * (H - 4) - 2;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  const last = hist[hist.length - 1];
  const lx = W - 2;
  const ly = H - clamp((last - min) / (max - min), 0, 1) * (H - 4) - 2;
  ctx.fillStyle = "#ff6b35";
  ctx.beginPath();
  ctx.arc(lx, ly, 3, 0, Math.PI * 2);
  ctx.fill();
}

function renderUltrasonic(u) {
  const min = u.min_cm ?? USONIC.MIN_CM;
  const max = u.max_cm ?? USONIC.MAX_CM;
  const dist = Number(u.distance_cm);
  const zoneKey = (u.zone || "OUT_OF_RANGE").toUpperCase();
  const zone = USONIC.ZONES[zoneKey] || USONIC.ZONES.OUT_OF_RANGE;

  if (!state.usonicZonesReady) initUsonicZoneArcs(min, max);

  setText("usonicRange", `${min}–${max}`);
  setText("usonicMaxLabel", `${max} cm`);
  setText("usonicTickMax", String(max));
  setText("usonicZoneLabel", zone.label);
  setText("usonicHint", zone.hint);
  setText("usonicArcLabel", Number.isFinite(dist) ? `${dist.toFixed(1)} cm` : "-- cm");

  const badge = document.getElementById("usonicBadge");
  const badgeLbl = document.getElementById("usonicBadgeLabel");
  if (badge && badgeLbl) {
    badge.dataset.state = zone.state;
    badgeLbl.textContent = zone.label;
  }

  const objBadge = document.getElementById("usonicObjBadge");
  const objLbl = document.getElementById("usonicObjLabel");
  if (objBadge && objLbl) {
    objBadge.dataset.state = u.object_detected ? "active" : "idle";
    objLbl.textContent = u.object_detected ? "ECO VALIDO" : "SIN ECO";
  }

  if (Number.isFinite(dist)) {
    setText("usonicDistance", dist.toFixed(1));
    state.usonicHistory.push(dist);
    if (state.usonicHistory.length > USONIC.HISTORY_MAX) state.usonicHistory.shift();

    if (state.usonicPrev != null) {
      const delta = dist - state.usonicPrev;
      const sign = delta > 0.05 ? "↑" : delta < -0.05 ? "↓" : "→";
      setText("usonicDelta", `${sign} ${Math.abs(delta).toFixed(1)} cm vs lectura anterior`);
      setText("usonicTrend", delta > 0.5 ? "Alejandose" : delta < -0.5 ? "Acercandose" : "Estable");
    }
    state.usonicPrev = dist;
  } else {
    setText("usonicDistance", "--");
    setText("usonicDelta", "--");
    setText("usonicTrend", "--");
  }

  document.querySelectorAll(".usonic-chip, .usonic-ladder-seg").forEach((el) => {
    el.classList.toggle("is-active", el.dataset.zone === zoneKey);
  });

  const readout = document.querySelector(".usonic-distance-value");
  if (readout) readout.style.color = zone.color || "";

  const pct = Number.isFinite(dist)
    ? clamp(((dist - min) / (max - min)) * 100, 0, 100)
    : 0;
  const bar = document.getElementById("usonicBar");
  if (bar) {
    bar.style.width = pct + "%";
    bar.className = `bar-fill ${zone.bar} transition-all duration-300`;
  }

  const marker = document.getElementById("usonicLadderMarker");
  if (marker) marker.style.top = `${100 - pct}%`;

  const arc = document.getElementById("usonicArc");
  const beam = document.getElementById("usonicBeam");
  const echo = document.getElementById("usonicEcho");
  const echo2 = document.getElementById("usonicEcho2");
  if (arc && beam && Number.isFinite(dist)) {
    arc.setAttribute("d", usonicArcPath(dist, min, max));
    const t = clamp(1 - (dist - min) / (max - min), 0, 1);
    const angle = Math.PI * t;
    const { cx, cy, r } = USONIC_RADAR;
    const bx = cx + r * Math.cos(Math.PI - angle);
    const by = cy - r * Math.sin(Math.PI - angle);
    beam.setAttribute("x1", cx.toFixed(1));
    beam.setAttribute("y1", cy.toFixed(1));
    beam.setAttribute("x2", bx.toFixed(1));
    beam.setAttribute("y2", by.toFixed(1));
    const stroke = zone.color || "#ff6b35";
    arc.style.stroke = stroke;
    beam.style.stroke = stroke;

    if (echo && echo2) {
      const show = u.object_detected;
      const rad = show ? 6 + (1 - t) * 10 : 0;
      echo.setAttribute("cx", bx.toFixed(1));
      echo.setAttribute("cy", by.toFixed(1));
      echo2.setAttribute("cx", bx.toFixed(1));
      echo2.setAttribute("cy", by.toFixed(1));
      echo.setAttribute("r", show ? String(rad) : "0");
      echo2.setAttribute("r", show ? String(rad * 1.6) : "0");
      echo.style.stroke = stroke;
      echo2.style.stroke = stroke;
    }
  }

  const card = document.getElementById("ultrasonicCard");
  if (card) {
    card.classList.toggle("usonic-alert", zoneKey === "CRITICAL");
    card.dataset.zone = zoneKey.toLowerCase();
  }

  drawUsonicHistory();
}

/* ---------- deteccion Pico vs broker ---------- */
function touchTelemetry() {
  state.lastTelemetryAt = Date.now();
  state.hasTelemetry = true;
  setPicoState(true);
}

function startPicoWatchdog() {
  setInterval(() => {
    const age = Date.now() - state.lastTelemetryAt;
    const brokerUp =
      state.ws && state.ws.readyState === WebSocket.OPEN && state.wsConnected;
    if (!brokerUp || !state.lastTelemetryAt) {
      setPicoState(false, "sin datos");
      return;
    }
    if (age > CONFIG.PICO_OFFLINE_MS) {
      setPicoState(false, `hace ${(age / 1000).toFixed(1)}s`);
    } else {
      setPicoState(true, `hace ${Math.round(age)}ms`);
    }
  }, 400);
}

function setPicoState(online, hint) {
  state.picoOnline = online;
  const pill = document.getElementById("picoStatus");
  const lbl = document.getElementById("picoStatusLabel");
  const seen = document.getElementById("picoLastSeen");
  if (!pill || !lbl) return;

  if (online) {
    pill.dataset.state = "connected";
    lbl.textContent = "PICO ONLINE";
    if (seen) seen.textContent = hint || "telemetria activa";
  } else {
    pill.dataset.state = "disconnected";
    lbl.textContent = "PICO OFFLINE";
    if (seen) seen.textContent = hint || "sin telemetria";
  }
}

/* ---------- system ---------- */
function renderSystem(sys) {
  const pct = clamp(sys.battery_pct, 0, 100);
  setText("batteryPct", pct);
  setText("batteryV", (sys.battery_v ?? 0).toFixed(2));
  setText("wifiRssi", sys.wifi_rssi ?? "--");
  setText("uptime", humanUptime(sys.uptime_sec));

  const pill = document.getElementById("batteryPill");
  const icon = document.getElementById("batteryIcon");
  if (pct > 60) {
    pill.dataset.state = "ok";
    if (icon) icon.setAttribute("data-lucide", "battery-full");
  } else if (pct > 25) {
    pill.dataset.state = "warn";
    if (icon) icon.setAttribute("data-lucide", "battery-medium");
  } else {
    pill.dataset.state = "error";
    if (icon) icon.setAttribute("data-lucide", "battery-low");
  }
  // Re-render lucide icon
  if (window.lucide && icon) {
    icon.classList.remove("lucide");
    lucide.createIcons({ nodes: [icon] });
  }
}

/* ---------- mearm ---------- */
function renderMeArm(arm) {
  state.lastMeArm = {
    ...state.lastMeArm,
    ...arm,
    servos: arm.servos ? { ...arm.servos } : state.lastMeArm?.servos,
  };
  // Status badge
  const badge = document.getElementById("mearmStatus");
  const lbl = document.getElementById("mearmStatusLabel");
  if (badge && lbl) {
    const isActive = (arm.status || "").toUpperCase() === "ACTIVE";
    badge.dataset.state = isActive ? "active" : "idle";
    lbl.textContent = isActive ? "ACTIVE" : "IDLE";
  }

  // Servos
  if (arm.limits) {
    for (const [name, lim] of Object.entries(arm.limits)) {
      if (SERVO_RANGES[name] && Array.isArray(lim) && lim.length >= 2) {
        SERVO_RANGES[name].min = lim[0];
        SERVO_RANGES[name].max = lim[1];
        const inp = document.querySelector(`[data-servo-input="${name}"]`);
        const rangeLbl = document.querySelector(`.servo--${name} .servo__range`);
        if (inp) {
          inp.min = String(lim[0]);
          inp.max = String(lim[1]);
        }
        if (rangeLbl) rangeLbl.textContent = `${lim[0]}–${lim[1]}°`;
      }
    }
  }

  if (arm.servos) {
    for (const name of Object.keys(SERVO_RANGES)) {
      const val = arm.servos[name];
      if (val === undefined) continue;
      const range = SERVO_RANGES[name];
      const pct = clamp(((val - range.min) / (range.max - range.min)) * 100, 0, 100);
      const bar = document.querySelector(`[data-servo-bar="${name}"]`);
      const txt = document.querySelector(`[data-servo-val="${name}"]`);
      const inp = document.querySelector(`[data-servo-input="${name}"]`);
      if (bar) bar.style.width = pct + "%";
      if (txt) txt.textContent = Math.round(val);
      if (inp && document.activeElement !== inp) inp.value = String(Math.round(val));
    }
    if (window.setTwinArmServos) {
      window.setTwinArmServos(arm.servos, arm.last_action || "", arm.status || "IDLE", arm);
    }
  }

  // Last action
  if (arm.last_action) {
    const el = document.getElementById("lastAction");
    if (el && el.textContent !== arm.last_action) {
      el.textContent = arm.last_action;
      el.setAttribute("data-fade", "1");
      setTimeout(() => el.removeAttribute("data-fade"), 400);
    }
  }
}

/* ---------- drive ---------- */
function renderDrive(drive) {
  const dir = (drive.direction || "STOP").toUpperCase();
  const badge = document.getElementById("driveDirection");
  const lbl = document.getElementById("driveDirectionLabel");
  if (badge) badge.dataset.state = dir.toLowerCase();
  if (lbl) lbl.textContent = dir;

  // Pad direccional
  ["arrowF", "arrowB", "arrowL", "arrowR"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.classList.remove("active");
  });
  document.querySelectorAll("[data-maneuver]").forEach((btn) => btn.classList.remove("active"));
  document.querySelectorAll(".tactic-btn.active").forEach((btn) => btn.classList.remove("active"));
  const center = document.getElementById("arrowS");
  if (center) center.classList.remove("active");

  const dirU = dir.toUpperCase();
  if (dirU === "FORWARD" || dirU === "FWD") document.getElementById("arrowF")?.classList.add("active");
  else if (dirU === "REVERSE" || dirU === "REV") document.getElementById("arrowB")?.classList.add("active");
  else if (dirU === "LEFT") document.getElementById("arrowL")?.classList.add("active");
  else if (dirU === "RIGHT") document.getElementById("arrowR")?.classList.add("active");
  else if (/^(FR|FL|RR|RL|BR|BL)(45|90)$/.test(dirU)) {
    const btn = document.querySelector(`[data-maneuver="${dirU}"]`);
    if (btn) btn.classList.add("active");
  } else {
    document.getElementById("arrowS")?.classList.add("active");
  }

  // PWM
  const l = clamp(drive.motor_l_pwm ?? 0, 0, 100);
  const r = clamp(drive.motor_r_pwm ?? 0, 0, 100);
  setText("motorLPct", l);
  setText("motorRPct", r);
  const lBar = document.getElementById("motorLBar");
  const rBar = document.getElementById("motorRBar");
  if (lBar) lBar.style.width = l + "%";
  if (rBar) rBar.style.width = r + "%";
}

/* ---------- vision ---------- */
function renderVision(v) {
  if (!v) return;
  state.lastVision = v;

  // Crosshair
  const ch = document.getElementById("crosshair");
  if (ch) {
    if (v.target_detected && v.target_coords) {
      const x = clamp(v.target_coords.x, 0, 320);
      const y = clamp(v.target_coords.y, 0, 240);
      ch.style.left = (x / 320) * 100 + "%";
      ch.style.top = (y / 240) * 100 + "%";
      ch.classList.remove("hidden");
      setText("targetX", x);
      setText("targetY", y);
    } else {
      ch.classList.add("hidden");
      setText("targetX", "---");
      setText("targetY", "---");
    }
  }

  // Badge objetivo
  const tBadge = document.getElementById("targetBadge");
  const tLbl = document.getElementById("targetBadgeLabel");
  if (tBadge && tLbl) {
    if (v.target_detected) {
      tBadge.dataset.state = "active";
      tLbl.textContent = "OBJETIVO";
    } else {
      tBadge.dataset.state = "idle";
      tLbl.textContent = "SIN OBJETIVO";
    }
  }

  // Color dominante
  const dom = (v.dominant_color || "").toUpperCase();
  const sw = document.getElementById("dominantSwatch");
  setText("dominantLabel", dom || "--");
  const hex = COLOR_TABLE[dom]?.hex || "#475569";
  setText("dominantHex", hex.toUpperCase());
  if (sw) sw.style.background = hex;

  // Chart (telemetria neutra puede traer analysis vacio)
  if (state.chart && Array.isArray(v.analysis) && v.analysis.length > 0) {
    const labels = v.analysis.map((a) => a.color);
    const data = v.analysis.map((a) => a.pct);
    const colors = labels.map((l) => COLOR_TABLE[l.toUpperCase()]?.hex || "#94a3b8");
    state.chart.data.labels = labels;
    state.chart.data.datasets[0].data = data;
    state.chart.data.datasets[0].backgroundColor = colors;
    state.chart.update("none");
  }

  drawVisionOverlay(v);
}

/* ---------- ir ---------- */
function renderIR(ir) {
  if (!ir || !ir.timestamp_ms) return;
  if (ir.timestamp_ms === state.lastIrTs) return; // anti-duplicado
  if (!ir.mapped_command || ir.mapped_command === "NONE") return;
  state.lastIrTs = ir.timestamp_ms;

  const log = document.getElementById("irLog");
  if (!log) return;

  const ts = formatTime(new Date());
  const line = document.createElement("div");
  line.className = "ir-line";
  line.innerHTML = `
    <span class="ts">[${ts}]</span>
    <span class="code">${escapeHtml(ir.last_raw_code || "0x------")}</span>
    <span class="arrow">→</span>
    <span class="cmd">${escapeHtml(ir.mapped_command)}</span>
  `;

  // Limpiar boot msg si sigue
  const placeholder = log.querySelector("p.text-slate-600");
  if (placeholder) placeholder.remove();

  log.appendChild(line);

  // FIFO
  while (log.children.length > CONFIG.MAX_IR_LINES) {
    log.removeChild(log.firstChild);
  }
  log.scrollTop = log.scrollHeight;

  state.irCount++;
  setText("irCount", state.irCount);
}

/* ============================================================
 * Helpers de UI
 * ============================================================ */
function setBrokerState(s) {
  const pill = document.getElementById("brokerStatus");
  const lbl = pill?.querySelector(".label");
  const hint = document.getElementById("brokerHint");
  if (!pill) return;
  if (s === "connected") {
    pill.dataset.state = "connected";
    if (lbl) lbl.textContent = "BROKER ON";
    if (hint) {
      hint.textContent = state.picoOnline ? "simpleBroker · Pico activo" : "simpleBroker · sin Pico";
    }
  } else if (s === "connecting") {
    pill.dataset.state = "warn";
    if (lbl) lbl.textContent = "BROKER...";
    if (hint) hint.textContent = "conectando";
  } else {
    pill.dataset.state = "disconnected";
    if (lbl) lbl.textContent = "BROKER OFF";
    if (hint) hint.textContent = CONFIG.BROKER_WS_URL;
  }
}

function setLatency(ms) {
  setText("latencyMs", ms);
  const pill = document.getElementById("latencyPill");
  if (!pill) return;
  if (ms < 150)      pill.dataset.state = "ok";
  else if (ms < 400) pill.dataset.state = "warn";
  else               pill.dataset.state = "error";
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el && el.textContent !== String(value)) el.textContent = value;
}

function clamp(n, lo, hi) {
  n = Number(n);
  if (Number.isNaN(n)) return lo;
  return Math.max(lo, Math.min(hi, n));
}

function humanUptime(sec) {
  sec = Math.max(0, Math.round(sec || 0));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m) return `${m}m ${String(s).padStart(2, "0")}s`;
  return `${s}s`;
}

function formatTime(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}
