/* Gemelo digital 3D · Chasis 2WD + MeArm v1 · Three.js */

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { MeArmTwin } from "./mearm-kinematics.js";

/** Calibración gemelo ↔ carro real (open-loop; sube distanceScale si aún va corto) */
const CAR = {
  maxSpeed: 0.52,
  maxOmega: 0.38,
  distanceScale: 2.8,
  trailMax: 200,
  track: 0.52,
  wheelbase: 0.68,
  msPerDeg: 18,
  maneuverDriveMs: 950,
  pwmRef: 70,
  /** Tras un clic en el dashboard, seguir integrando aunque la telemetría tarde ~1.5 s */
  defaultDriveMs: 2200,
  turnDriveMs: 1800,
};

const MOTOR_PWM_THRESHOLD = 3;

// MANEUVER_SPECS — referencia de parámetros de maniobra (modo diferencial).
// En modo tanque la física real viene de maneuverTwinMotion + arcFromWheelPwm.
// lFwd/rFwd: 1=adelante, -1=atrás.  Positivo omega=giro derecha (Three.js).
const MANEUVER_SPECS = {
  FR45: { l: 78, r: 28, lFwd: 1,  rFwd: 1  },  // arco adelante-derecha
  FL45: { l: 28, r: 78, lFwd: 1,  rFwd: 1  },  // arco adelante-izquierda
  RR45: { l: 28, r: 78, lFwd: -1, rFwd: -1 },  // arco trasero-derecha
  RL45: { l: 78, r: 28, lFwd: -1, rFwd: -1 },  // arco trasero-izquierda
  FR90: { l: 55, r: 55, lFwd: 1,  rFwd: -1 },  // spin derecha
  FL90: { l: 55, r: 55, lFwd: -1, rFwd: 1  },  // spin izquierda
  BR90: { l: 55, r: 55, lFwd: -1, rFwd: 1  },  // spin izquierda (trasero)
  BL90: { l: 55, r: 55, lFwd: 1,  rFwd: -1 },  // spin derecha (trasero)
  RR90: { l: 55, r: 55, lFwd: 1,  rFwd: -1 },  // spin derecha
  RL90: { l: 55, r: 55, lFwd: -1, rFwd: 1  },  // spin izquierda
};

const COL = {
  plate: 0xececf0,
  plateShade: 0xd4d4dc,
  pin: 0x141418,
  servoBody: 0x1a72c8,
  servoCap: 0x125599,
  horn: 0xf2f2f2,
  pcb: 0x1a7a42,
  pcbSilk: 0xffffff,
  tire: 0x2a2a2a,
  rim: 0xb8b8b8,
  chassis: 0x1e1e22,
  deck: 0x2d4a3e,
  accent: 0xff6b35,
  battery: 0x3a3a40,
};

const TWIN = {
  exactSync: true,
  lastDrive: null,
  lastArm: null,
  car: { x: 0, z: 0, heading: 0, trail: [], wheelSpin: { l: 0, r: 0 } },
  display: {
    car: { x: 0, z: 0, heading: 0 },
    arm: { base: 90, shoulder: 70, elbow: 110, gripper: 50 },
  },
  maneuver: null,
  driveUntil: 0,
};

let carCtx = null;
let armCtx = null;
let inited = false;
let clock = null;

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function lerpAngle(a, b, t) {
  let d = ((b - a + Math.PI) % (Math.PI * 2)) - Math.PI;
  if (d < -Math.PI) d += Math.PI * 2;
  return a + d * t;
}

function servoRad(deg) {
  return ((deg - 90) * Math.PI) / 180;
}

function pwmGain(d) {
  const l = d?.motor_l_pwm ?? 0;
  const r = d?.motor_r_pwm ?? 0;
  const ref = CAR.pwmRef || 70;
  return Math.max(0.35, Math.max(l, r) / ref);
}

function driveHoldMs(dir) {
  const d = (dir || "STOP").toUpperCase();
  if (d === "STOP") return 0;
  if (isManeuverDirection(d)) return maneuverDurationMs(d);
  if (d === "LEFT" || d === "RIGHT") return CAR.turnDriveMs;
  return CAR.defaultDriveMs;
}

function extendDriveMotion(dir) {
  const ms = driveHoldMs(dir);
  if (ms > 0) TWIN.driveUntil = Math.max(TWIN.driveUntil, performance.now() + ms);
}

function applyDriveCalibration(drive) {
  if (!drive) return;
  if (drive.ms_per_deg != null) CAR.msPerDeg = Number(drive.ms_per_deg) || CAR.msPerDeg;
  if (drive.maneuver_drive_ms != null) {
    CAR.maneuverDriveMs = Number(drive.maneuver_drive_ms) || CAR.maneuverDriveMs;
  }
}

/* ---------- Viewport ---------- */
export function initTwin() {
  if (inited) {
    resizeViewport(carCtx);
    resizeViewport(armCtx);
    return;
  }

  const carEl = document.getElementById("twinCar");
  const armEl = document.getElementById("twinArm");
  if (!carEl || !armEl) return;

  try {
    clock = new THREE.Clock();
    carCtx = createViewport(carEl, {
      bg: 0x0e0608,
      camPos: [1.85, 1.35, 2.05],
      target: [0, 0.18, 0],
      exposure: 1.35,
    });
    armCtx = createViewport(armEl, {
      bg: 0x101018,
      camPos: [0.19, 0.13, 0.21],
      target: [0, 0.1, 0],
      exposure: 1.55,
      minDistance: 0.42,
      maxDistance: 3.2,
    });

    buildCarScene(carCtx);
    buildArmScene(armCtx);
    seedTwinIdle();
    wireArmThemeToggle();

    const ro = new ResizeObserver(() => {
      resizeViewport(carCtx);
      resizeViewport(armCtx);
    });
    ro.observe(carEl);
    ro.observe(armEl);
    window.addEventListener("resize", () => {
      resizeViewport(carCtx);
      resizeViewport(armCtx);
    });

    requestAnimationFrame(() => {
      resizeViewport(carCtx);
      resizeViewport(armCtx);
      animate();
    });

    inited = true;
  } catch (err) {
    console.error("[twin] init error", err);
    showTwinStatus(carEl, err.message);
    showTwinStatus(armEl, err.message);
  }
}

function showTwinStatus(el, msg) {
  if (!el || !msg) return;
  const note = document.createElement("p");
  note.className = "twin-error font-mono text-[10px] text-red-400 p-2";
  note.textContent = "3D: " + msg;
  el.appendChild(note);
}

function createViewport(container, opts) {
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(opts.bg, 8, 22);

  const camera = new THREE.PerspectiveCamera(38, 1, 0.04, 30);
  camera.position.set(...opts.camPos);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(opts.bg, 1);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = opts.exposure ?? 1.4;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  controls.target.set(...opts.target);
  controls.minDistance = opts.minDistance ?? 0.85;
  controls.maxDistance = opts.maxDistance ?? 5.5;
  controls.maxPolarAngle = Math.PI * 0.49;
  controls.enablePan = false;

  scene.add(new THREE.AmbientLight(0xffffff, 0.65));
  scene.add(new THREE.HemisphereLight(0xffffff, 0x202028, 0.55));

  const key = new THREE.DirectionalLight(0xffffff, 1.35);
  key.position.set(2, 4, 3);
  scene.add(key);

  const fill = new THREE.DirectionalLight(0xdde8ff, 0.55);
  fill.position.set(-3, 2, 1);
  scene.add(fill);

  const rim = new THREE.DirectionalLight(0xffeedd, 0.35);
  rim.position.set(0, 1, -3);
  scene.add(rim);

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(6, 6),
    pbr(0x141418, { rough: 0.92, emissive: 0x060608, emissiveI: 0.2 })
  );
  floor.rotation.x = -Math.PI / 2;
  scene.add(floor);

  const grid = new THREE.GridHelper(5, 20, 0x444450, 0x282830);
  grid.position.y = 0.008;
  scene.add(grid);

  return { scene, camera, renderer, controls, container };
}

function resizeViewport(ctx) {
  if (!ctx?.container || !ctx.renderer || !ctx.camera) return;
  const w = ctx.container.clientWidth;
  const h = ctx.container.clientHeight;
  if (w < 2 || h < 2) return;
  ctx.camera.aspect = w / h;
  ctx.camera.updateProjectionMatrix();
  ctx.renderer.setSize(w, h, false);
}

function pbr(color, { metal = 0.12, rough = 0.52, emissive = 0x000000, emissiveI = 0 } = {}) {
  return new THREE.MeshStandardMaterial({
    color,
    metalness: metal,
    roughness: rough,
    emissive: new THREE.Color(emissive),
    emissiveIntensity: emissiveI,
  });
}

function buildCarScene(ctx) {
  const root = new THREE.Group();
  const deck = new THREE.Mesh(new THREE.BoxGeometry(0.72, 0.06, 0.52), pbr(COL.deck));
  deck.position.y = 0.12;
  root.add(deck);

  const body = new THREE.Mesh(new THREE.BoxGeometry(0.58, 0.08, 0.38), pbr(COL.chassis));
  body.position.set(0, 0.2, -0.04);
  root.add(body);

  const hl = new THREE.Mesh(
    new THREE.SphereGeometry(0.04, 12, 12),
    pbr(0xfff4e0, { emissive: 0xffaa44, emissiveI: 0.35 })
  );
  hl.position.set(0, 0.22, 0.28);
  root.add(hl);

  const wheels = {};
  const wheelGeo = new THREE.CylinderGeometry(0.09, 0.09, 0.05, 16);
  const tireMat = pbr(COL.tire, { rough: 0.85 });
  const rimMat = pbr(COL.rim, { metal: 0.35 });
  const positions = {
    fl: [-0.28, 0.09, 0.22],
    fr: [0.28, 0.09, 0.22],
    rl: [-0.28, 0.09, -0.22],
    rr: [0.28, 0.09, -0.22],
  };
  for (const [key, pos] of Object.entries(positions)) {
    const g = new THREE.Group();
    g.position.set(...pos);
    const tire = new THREE.Mesh(wheelGeo, tireMat);
    tire.rotation.z = Math.PI / 2;
    const rim = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.052, 12), rimMat);
    rim.rotation.z = Math.PI / 2;
    g.add(tire, rim);
    g.userData.spinMesh = tire;
    root.add(g);
    wheels[key] = g;
  }

  const trailGeo = new THREE.BufferGeometry();
  const trailPos = new Float32Array(CAR.trailMax * 3);
  trailGeo.setAttribute("position", new THREE.BufferAttribute(trailPos, 3));
  trailGeo.setDrawRange(0, 0);
  const trail = new THREE.Line(
    trailGeo,
    new THREE.LineBasicMaterial({ color: 0xff6b35, transparent: true, opacity: 0.55 })
  );
  ctx.scene.add(trail);
  ctx.scene.add(root);

  ctx.meshes = { root, wheels, trail, headlight: hl };
}

function buildArmScene(ctx) {
  const mearm = new MeArmTwin(ctx.scene);
  ctx.meshes = { mearm };
}

function wireArmThemeToggle() {
  const btn = document.getElementById("twinArmThemeBtn");
  const twin = armCtx?.meshes?.mearm;
  if (!btn || !twin) return;

  const updateLabel = (labelText) => {
    const label = btn.querySelector("[data-theme-label]");
    if (label) label.textContent = labelText;
    btn.dataset.theme = twin.themeKey;
  };

  updateLabel("Blanco");

  btn.addEventListener("click", () => {
    const { key, label } = twin.cycleTheme();
    btn.dataset.theme = key;
    updateLabel(label.replace(" mate", ""));
  });
}

/* ---------- Telemetria ---------- */
function seedTwinIdle() {
  TWIN.lastDrive = { direction: "STOP", motor_l_pwm: 0, motor_r_pwm: 0 };
  TWIN.maneuver = null;
  TWIN.driveUntil = 0;
  TWIN.display.arm = { base: 90, shoulder: 70, elbow: 110, gripper: 50 };
}

function isCarMotorsActive() {
  const now = performance.now();
  if (TWIN.driveUntil > now) return true;
  if (TWIN.maneuver && now < TWIN.maneuver.until) return true;

  const d = TWIN.lastDrive;
  if (!d) return false;
  const l = d.motor_l_pwm ?? 0;
  const r = d.motor_r_pwm ?? 0;
  const dir = (d.direction || "STOP").toUpperCase();
  if (dir !== "STOP" && (l > MOTOR_PWM_THRESHOLD || r > MOTOR_PWM_THRESHOLD)) return true;
  return l > MOTOR_PWM_THRESHOLD || r > MOTOR_PWM_THRESHOLD;
}

function isManeuverDirection(dir) {
  const d = (dir || "").toUpperCase();
  return /^(FR|FL|RR|RL|BR|BL)(45|90)$/.test(d);
}

function maneuverDurationMs(dir) {
  const d = (dir || "").toUpperCase();
  if (d.endsWith("90")) return Math.max(400, CAR.msPerDeg * 90);
  if (d.endsWith("45")) return Math.max(400, CAR.msPerDeg * 45) + CAR.maneuverDriveMs;
  return 0;
}

function scheduleManeuver(dir) {
  const d = (dir || "").toUpperCase();
  if (!isManeuverDirection(d)) {
    TWIN.maneuver = null;
    return;
  }
  const now = performance.now();
  const totalMs = maneuverDurationMs(d);
  const pivotDuration = d.endsWith("90") ? totalMs : Math.max(400, CAR.msPerDeg * 45);
  TWIN.maneuver = {
    code: d,
    until: now + totalMs,
    pivotUntil: now + pivotDuration,   // timestamp absoluto — antes era duración relativa (bug)
  };
}

/**
 * Arco de rueda diferencial (modo tanque + ENA/ENB).
 * Convención Three.js: heading aumenta = giro DERECHA (rotation.y positivo).
 * Por tanto: rueda IZQUIERDA más rápida (lN > rN) → omega POSITIVO → gira DERECHA.
 * omega = (lN - rN): RIGHT command (l=78,r=28) → +0.50 → gira derecha ✓
 *                    LEFT  command (l=28,r=78) → -0.50 → gira izquierda ✓
 * Multiplicador 1.8: calibrado para ~90° en maneuver de 1620 ms (msPerDeg=18).
 */
function arcFromWheelPwm(lPct, rPct, gain, forward = 1) {
  const lN = Math.max(0, lPct) / 100;
  const rN = Math.max(0, rPct) / 100;
  const scale = CAR.distanceScale;
  const v = ((lN + rN) / 2) * CAR.maxSpeed * gain * scale * forward;
  const omega = (lN - rN) * CAR.maxOmega * gain * scale * 1.8;
  return { v, omega };
}

function resolveDriveMotion(d) {
  const dir = (d.direction || "STOP").toUpperCase();
  let l = d.motor_l_pwm ?? 0;
  let r = d.motor_r_pwm ?? 0;
  let lSign = 1;
  let rSign = 1;

  if (dir === "LEFT" || dir === "RIGHT") {
    return { dir, l, r, lSign: 1, rSign: 1, arc: true };
  }

  const spec = MANEUVER_SPECS[dir];
  if (spec) {
    return { dir, l: spec.l, r: spec.r, lSign: spec.lFwd, rSign: spec.rFwd, pivot: null };
  }
  if (dir === "REVERSE" || dir === "REV") {
    lSign = rSign = -1;
  }
  return { dir, l, r, lSign, rSign, pivot: null };
}

/**
 * Cinemática de maniobra en el gemelo (alineada con firmware _MANEUVER_TANK).
 *
 * Convención de pivot:
 *   pivotLeft = true  → left-inner (l=28), right-outer (r=78) → omega negativo → gira IZQUIERDA
 *   pivotLeft = false → left-outer (l=78), right-inner (r=28) → omega positivo → gira DERECHA
 *
 * Maneuvers y su pivotLeft (sincronizado con firmware):
 *   FL45/FL90         → pivotLeft=true  (pivot LEFT + FORWARD)
 *   FR45/FR90         → pivotLeft=false (pivot RIGHT + FORWARD)
 *   RR45/BR45         → pivotLeft=true  (pivot LEFT + REVERSE → trayectoria trasero-derecha)
 *   RL45/BL45         → pivotLeft=false (pivot RIGHT + REVERSE → trayectoria trasero-izquierda)
 *   BR90              → pivotLeft=true  (pivot LEFT)
 *   BL90/RR90         → pivotLeft=false (pivot RIGHT)
 *   RL90              → pivotLeft=true  (pivot LEFT)
 */
function maneuverTwinMotion(dir, nowMs) {
  const d = (dir || "").toUpperCase();
  if (!isManeuverDirection(d)) return null;

  const gain = pwmGain(TWIN.lastDrive);
  const v = CAR.maxSpeed * gain * CAR.distanceScale * 1.05;
  const mnv = TWIN.maneuver;
  const inner = 28;
  const outer = 78;

  if (d.endsWith("90")) {
    // FL90, RL90, BR90 → pivot izquierda; FR90, RR90, BL90 → pivot derecha
    const pivotLeft = d === "FL90" || d === "RL90" || d === "BR90";
    const inPivot = mnv != null && nowMs < mnv.pivotUntil;
    if (inPivot) {
      if (pivotLeft) return arcFromWheelPwm(inner, outer, gain, 1);
      return arcFromWheelPwm(outer, inner, gain, 1);
    }
    return { omega: 0, v: 0 };
  }

  if (d.endsWith("45")) {
    // RR45/BR45 → pivot izquierda + retroceso; RL45/BL45 → pivot derecha + retroceso
    const pivotLeft = d.startsWith("FL") || d.startsWith("RR") || d.startsWith("BR");
    const back = d.startsWith("RR") || d.startsWith("RL") || d.startsWith("BR") || d.startsWith("BL");
    const inPivot = mnv != null && nowMs < mnv.pivotUntil;
    if (inPivot) {
      // El firmware siempre pivota hacia ADELANTE — el back solo cambia la fase de conducción
      if (pivotLeft) return arcFromWheelPwm(inner, outer, gain, back ? -1 : 1);
      return arcFromWheelPwm(outer, inner, gain, back ? -1 : 1);
    }
    return { omega: 0, v: back ? -v : v };
  }

  return null;
}

function integrateCar(dt) {
  const d = TWIN.lastDrive;
  if (!d) return;

  const nowMs = performance.now();
  if (!isCarMotorsActive()) {
    if (TWIN.maneuver && nowMs >= TWIN.maneuver.until) TWIN.maneuver = null;
    return;
  }

  const dirU = (d.direction || "STOP").toUpperCase();
  const gain = pwmGain(d);
  let v = 0;
  let omega = 0;

  const mnv = maneuverTwinMotion(dirU, nowMs);
  if (mnv) {
    v = mnv.v;
    omega = mnv.omega;
  } else {
    const { dir, l, r, lSign, rSign, arc } = resolveDriveMotion(d);
    const lN = l / 100;
    const rN = r / 100;

    if (arc) {
      const arcM = arcFromWheelPwm(l, r, gain, dir === "REVERSE" || dir === "REV" ? -1 : 1);
      v = arcM.v;
      omega = arcM.omega;
    } else if (lSign < 0 && rSign > 0) {
      // Rueda izq atrás + der adelante → spin IZQUIERDA → omega NEGATIVO
      omega = -CAR.maxOmega * gain * Math.max(lN, rN, 0.35);
      v = 0;
    } else if (lSign > 0 && rSign < 0) {
      // Rueda izq adelante + der atrás → spin DERECHA → omega POSITIVO
      omega = CAR.maxOmega * gain * Math.max(lN, rN, 0.35);
      v = 0;
    } else {
      const fwd = lSign < 0 || rSign < 0 ? -1 : 1;
      v = ((lN + rN) / 2) * CAR.maxSpeed * gain * CAR.distanceScale * fwd;
      omega = (rN - lN) * CAR.maxOmega * gain * CAR.distanceScale * fwd * 0.5;
    }
  }

  TWIN.car.heading += omega * dt;
  TWIN.car.x += Math.sin(TWIN.car.heading) * v * dt;
  TWIN.car.z += Math.cos(TWIN.car.heading) * v * dt;

  const lim = 4.5;
  TWIN.car.x = Math.max(-lim, Math.min(lim, TWIN.car.x));
  TWIN.car.z = Math.max(-lim, Math.min(lim, TWIN.car.z));

  if (Math.abs(v) > 0.0005 || Math.abs(omega) > 0.0005) {
    TWIN.car.trail.push({ x: TWIN.car.x, z: TWIN.car.z });
    if (TWIN.car.trail.length > CAR.trailMax) TWIN.car.trail.shift();
  }

  const spinRate = 14;
  const lN = (d.motor_l_pwm ?? 0) / 100;
  const rN = (d.motor_r_pwm ?? 0) / 100;
  let spinL = lN;
  let spinR = rN;
  if (Math.abs(omega) > 0.001 && Math.abs(v) < 0.002) {
    spinL = omega > 0 ? lN : -lN * 0.5;
    spinR = omega < 0 ? rN : -rN * 0.5;
  }
  TWIN.car.wheelSpin.l += Math.abs(spinL) * spinRate * dt * Math.sign(spinL || 1);
  TWIN.car.wheelSpin.r += Math.abs(spinR) * spinRate * dt * Math.sign(spinR || 1);

  if (carCtx?.meshes.wheels) {
    const rl = carCtx.meshes.wheels.rl?.userData?.spinMesh;
    const rr = carCtx.meshes.wheels.rr?.userData?.spinMesh;
    if (rl) rl.rotation.x = TWIN.car.wheelSpin.l;
    if (rr) rr.rotation.x = TWIN.car.wheelSpin.r;
  }

  if (TWIN.maneuver && nowMs >= TWIN.maneuver.until) TWIN.maneuver = null;
}

function updateCarMesh(smooth) {
  if (!carCtx?.meshes.root) return;

  const dc = TWIN.display.car;
  if (TWIN.exactSync) {
    dc.x = TWIN.car.x;
    dc.z = TWIN.car.z;
    dc.heading = TWIN.car.heading;
  } else {
    dc.x = lerp(dc.x, TWIN.car.x, smooth);
    dc.z = lerp(dc.z, TWIN.car.z, smooth);
    dc.heading = lerpAngle(dc.heading, TWIN.car.heading, smooth);
  }

  carCtx.meshes.root.position.set(dc.x, 0, dc.z);
  carCtx.meshes.root.rotation.y = dc.heading;

  const trail = carCtx.meshes.trail;
  if (trail?.geometry && TWIN.car.trail.length > 1) {
    const pos = trail.geometry.attributes.position.array;
    TWIN.car.trail.forEach((p, i) => {
      pos[i * 3] = p.x;
      pos[i * 3 + 1] = 0.04;
      pos[i * 3 + 2] = p.z;
    });
    trail.geometry.setDrawRange(0, TWIN.car.trail.length);
    trail.geometry.attributes.position.needsUpdate = true;
  }

  const d = TWIN.lastDrive;
  const hud = document.getElementById("twinCarHud");
  if (hud && d) {
    hud.textContent = `${d.direction} · L${Math.round(d.motor_l_pwm ?? 0)}% · R${Math.round(d.motor_r_pwm ?? 0)}%`;
  }

  const hl = carCtx.meshes.headlight;
  if (hl?.material) {
    const on = isCarMotorsActive();
    hl.material.emissiveIntensity = on ? 1.2 : 0.35;
  }
}

function updateArmMesh(smooth) {
  const twin = armCtx?.meshes?.mearm;
  if (!twin) return;

  const arm = TWIN.lastArm;
  const target = arm?.servos || TWIN.display.arm;
  const d = TWIN.display.arm;

  if (arm?.servos) {
    Object.assign(d, {
      base: Number(arm.servos.base),
      shoulder: Number(arm.servos.shoulder),
      elbow: Number(arm.servos.elbow),
      gripper: Number(arm.servos.gripper),
    });
  } else if (!TWIN.exactSync) {
    d.base = lerp(d.base, target.base, smooth);
    d.shoulder = lerp(d.shoulder, target.shoulder, smooth);
    d.elbow = lerp(d.elbow, target.elbow, smooth);
    d.gripper = lerp(d.gripper, target.gripper, smooth);
  }

  twin.setServos(d, arm?.last_action || "", arm?.status || "IDLE", arm);

  const hud = document.getElementById("twinArmHud");
  const act = document.getElementById("twinArmAction");
  if (hud) {
    hud.textContent = `S0 base ${d.base.toFixed(0)}° · S1 hombro ${d.shoulder.toFixed(0)}° · S2 codo ${d.elbow.toFixed(0)}° · S3 pinza ${d.gripper.toFixed(0)}°`;
  }
  if (act) act.textContent = arm?.last_action || "";
}

function animate() {
  requestAnimationFrame(animate);
  if (!carCtx && !armCtx) return;

  const dt = Math.min(clock?.getDelta() ?? 0.016, 0.05);
  const smooth = 1 - Math.pow(0.001, dt);

  try {
    if (isCarMotorsActive()) integrateCar(dt);
    updateCarMesh(smooth);
    updateArmMesh(smooth);

    [carCtx, armCtx].forEach((ctx) => {
      if (!ctx) return;
      ctx.controls.update();
      ctx.renderer.render(ctx.scene, ctx.camera);
    });
  } catch (err) {
    console.error("[twin] frame error", err);
  }
}

export function updateTwin(drive, mearm) {
  if (drive) {
    applyDriveCalibration(drive);
    const dir = (drive.direction || "STOP").toUpperCase();
    if (isManeuverDirection(dir)) scheduleManeuver(dir);
    else if (dir === "STOP") {
      TWIN.maneuver = null;
      TWIN.driveUntil = 0;
    } else {
      extendDriveMotion(dir);
    }
    TWIN.lastDrive = { ...drive };
  }
  if (mearm?.servos) {
    TWIN.lastArm = {
      ...TWIN.lastArm,
      ...mearm,
      servos: { ...mearm.servos },
      limits: mearm.limits || TWIN.lastArm?.limits,
      invert: mearm.invert || TWIN.lastArm?.invert,
      home: mearm.home || TWIN.lastArm?.home,
      gripper_open: mearm.gripper_open ?? TWIN.lastArm?.gripper_open,
      gripper_close: mearm.gripper_close ?? TWIN.lastArm?.gripper_close,
    };
  }
}

/** Vista previa inmediata al pulsar flechas / maniobras en el dashboard */
export function previewDriveMotion(cmd) {
  const key = (cmd || "STOP").toUpperCase();
  let l = CAR.pwmRef;
  let r = CAR.pwmRef;

  if (key === "STOP") {
    l = 0;
    r = 0;
  } else if (key === "LEFT") {
    // Giro izquierda rapido: rueda izq muy lenta, der al maximo
    l = 5;
    r = 100;
  } else if (key === "RIGHT") {
    // Giro derecha rapido: rueda izq al maximo, der muy lenta
    l = 100;
    r = 5;
  } else if (key === "REVERSE" || key === "REV") {
    l = CAR.pwmRef;
    r = CAR.pwmRef;
  }
  updateTwin({ direction: key, motor_l_pwm: l, motor_r_pwm: r }, null);
}

/** Actualiza gemelo MeArm al instante (mismos ° que sliders/comandos) */
export function setTwinArmServos(servos, action = "", status = "ACTIVE", meta = null) {
  const prev = TWIN.lastArm?.servos || {};
  const m = meta || TWIN.lastArm || {};
  TWIN.lastArm = {
    ...TWIN.lastArm,
    servos: { ...prev, ...servos },
    last_action: action || TWIN.lastArm?.last_action || "",
    status: status || TWIN.lastArm?.status || "ACTIVE",
    limits: m.limits || TWIN.lastArm?.limits,
    invert: m.invert || TWIN.lastArm?.invert,
    home: m.home || TWIN.lastArm?.home,
    gripper_open: m.gripper_open ?? TWIN.lastArm?.gripper_open,
    gripper_close: m.gripper_close ?? TWIN.lastArm?.gripper_close,
  };
  const twin = armCtx?.meshes?.mearm;
  if (twin) {
    twin.setServos(TWIN.lastArm.servos, TWIN.lastArm.last_action, TWIN.lastArm.status, TWIN.lastArm);
  }
}

window.initTwin = initTwin;
window.updateTwin = updateTwin;
window.setTwinArmServos = setTwinArmServos;
window.previewDriveMotion = previewDriveMotion;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => requestAnimationFrame(initTwin));
} else {
  requestAnimationFrame(initTwin);
}
