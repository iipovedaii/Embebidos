/* MeArm v1 · cinemática linkage paralelo (GerardoMunoz/embedded) + visuals SISEMB */

import * as THREE from "three";

/** Modelo paramétrico MeArm — 3 servos cinemáticos + pinza (4º servo) */
export const MEARM_MODEL = {
  cte: {
    beta1: 180,
    beta2: 90,
    beta3: 90,
    num_servos: 3,
    alpha0_min: -90,
    alpha1_min: 0,
    alpha2_min: -90,
  },
  var: { alpha0: 0, alpha1: 90, alpha2: 20 },
  li: {
    A: { nodes: ["a", "b"], l: 0.4, w: 0.1, p: 0.05 },
    B: { nodes: ["a", "d"], l: 0.8, w: 0.1, p: 0.05 },
    C: { nodes: ["d", "c"], l: 0.4, w: 0.1, p: 0.05 },
    D: { nodes: ["c", "b"], l: 0.8, w: 0.1, p: 0.05 },
    E: { nodes: ["d", "f"], l: 0.35, w: 0.1, p: 0.05 },
    F: { nodes: ["f", "e"], l: 0.8, w: 0.1, p: 0.05 },
    G: { nodes: ["a", "e"], l: 0.35, w: 0.1, p: 0.05 },
    H: { nodes: ["c", "g"], l: 0.45, w: 0.1, p: 0.05 },
    I: { nodes: ["d", "g"], l: 0.2, w: 0.1, p: 0.05 },
    J: { nodes: ["d", "i"], l: 0.8, w: 0.1, p: 0.05 },
    K: { nodes: ["i", "h"], l: 0.2, w: 0.1, p: 0.05 },
    L: { nodes: ["g", "h"], l: 0.8, w: 0.1, p: 0.05 },
    M: { nodes: ["i", "j"], l: 0.25, w: 0.1, p: 0.05 },
  },
  jo: {
    a: { transforms: [{ parent: null }] },
    b: { transforms: [{ parent: "a" }, { Rz: "@cte.beta1" }, { T: "@li.A" }] },
    d: { transform: [{ parent: "a" }, { Rz: "@var.alpha1" }, { T: "@li.B" }] },
    c: { fbl: "a,b,d,D,C" },
    e: { transform: [{ parent: "a" }, { Rz: "@var.alpha2" }, { T: "@li.G" }] },
    f: { fbl: "a,d,e,E,F" },
    g: { transform: [{ parent: "d" }, { Rz: "@ang(c,d) + @cte.beta2" }, { T: "@li.I" }] },
    i: { transform: [{ parent: "d" }, { Rz: "@ang(f,d)" }, { T: "@li.J" }] },
    h: { fbl: "d,g,i,L,K" },
    j: { transform: [{ parent: "i" }, { Rz: "@ang(h,i) + @cte.beta3" }, { T: "@li.M" }] },
  },
};

export const SERVO_MAP = {
  base:     { id: "S0", label: "Base",     gpio: 17, color: 0xff6b35, joint: "a", alpha: "alpha0" },
  shoulder: { id: "S1", label: "Hombro",   gpio: 18, color: 0xff3b3b, joint: "d", alpha: "alpha1" },
  elbow:    { id: "S2", label: "Codo",     gpio: 20, color: 0xff9f1c, joint: "c", alpha: "alpha2" },
  gripper:  { id: "S3", label: "Pinza",    gpio: 21, color: 0xf97316, joint: "j", alpha: null },
};

/** Temas acrílico mate — negro / blanco / rojo */
export const MEARM_THEMES = {
  white: {
    label: "Blanco mate",
    base: 0xf0f0f2,
    baseCut: 0x141418,
    linkMain: 0xfafafa,
    linkPar: 0xd4d4d8,
    linkGrip: 0xfff8f0,
    jaw: 0xe8e8ec,
    joint: 0x18181c,
  },
  black: {
    label: "Negro mate",
    base: 0x1a1a1e,
    baseCut: 0x08080a,
    linkMain: 0x2a2a30,
    linkPar: 0x1e1e24,
    linkGrip: 0x323238,
    jaw: 0x28282e,
    joint: 0x0c0c10,
  },
  red: {
    label: "Rojo mate",
    base: 0x181012,
    baseCut: 0x0a0808,
    linkMain: 0xb91c1c,
    linkPar: 0x7f1414,
    linkGrip: 0xd32f2f,
    jaw: 0x991b1b,
    joint: 0x1a0e0e,
  },
};

export const MEARM_THEME_ORDER = ["white", "black", "red"];

/** Límites por defecto (alineados con firmware/config.py) */
export const MEARM_DEFAULT_LIMITS = {
  base: [0, 180],
  shoulder: [20, 160],
  elbow: [100, 150],
  gripper: [0, 180],
};

export const MEARM_DEFAULT_HOME = {
  base: 90,
  shoulder: 70,
  elbow: 110,
  gripper: 50,
};

function clampJoint(name, deg, limits) {
  const lim = limits?.[name] || MEARM_DEFAULT_LIMITS[name] || [0, 180];
  const lo = lim[0] ?? 0;
  const hi = lim[1] ?? 180;
  return Math.max(lo, Math.min(hi, Number(deg)));
}

/** Ángulos firmware (°) → variables cinemáticas del modelo */
export function firmwareToKinematics(servos, meta = null) {
  const limits = meta?.limits || MEARM_DEFAULT_LIMITS;
  const s = {
    base: clampJoint("base", servos.base ?? MEARM_DEFAULT_HOME.base, limits),
    shoulder: clampJoint("shoulder", servos.shoulder ?? MEARM_DEFAULT_HOME.shoulder, limits),
    elbow: clampJoint("elbow", servos.elbow ?? MEARM_DEFAULT_HOME.elbow, limits),
    gripper: clampJoint("gripper", servos.gripper ?? MEARM_DEFAULT_HOME.gripper, limits),
  };
  const gOpen = meta?.gripper_open ?? 25;
  const gClose = meta?.gripper_close ?? 155;
  const span = Math.max(1, gClose - gOpen);
  const gNorm = (s.gripper - gOpen) / span;
  const shLo = limits.shoulder?.[0] ?? MEARM_DEFAULT_LIMITS.shoulder[0];
  const shHi = limits.shoulder?.[1] ?? MEARM_DEFAULT_LIMITS.shoulder[1];
  const eLo = limits.elbow?.[0] ?? MEARM_DEFAULT_LIMITS.elbow[0];
  const eHi = limits.elbow?.[1] ?? MEARM_DEFAULT_LIMITS.elbow[1];
  // Modelo linkage: Rz positivo ≠ sentido de los ° lógicos del firmware → espejo en el rango
  const alpha1 = shLo + shHi - s.shoulder;
  const alpha2 = eHi - s.elbow;
  return {
    servos: s,
    alpha0: s.base - 90,
    alpha1,
    alpha2,
    elbowSpan: Math.max(1, eHi - eLo),
    beta3: 90 + gNorm * 40,
    jawSpread: (s.gripper - gOpen) * 1.15,
  };
}

const PARALLEL_LINKS = new Set(["E", "F", "G", "H", "I", "J", "K", "L"]);
const GRIPPER_LINKS = new Set(["M"]);

function matteMat(color, emissive = 0x000000, emissiveI = 0) {
  return new THREE.MeshStandardMaterial({
    color,
    metalness: 0.03,
    roughness: 0.92,
    emissive: new THREE.Color(emissive),
    emissiveIntensity: emissiveI,
  });
}

function makeLabel(text, color = "#ffffff") {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "rgba(8,4,6,0.82)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.strokeRect(2, 2, canvas.width - 4, canvas.height - 4);
  ctx.fillStyle = color;
  ctx.font = "bold 22px JetBrains Mono, monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  text.split("\n").forEach((line, i, arr) => {
    ctx.fillText(line, canvas.width / 2, canvas.height / 2 + (i - (arr.length - 1) / 2) * 24);
  });
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(0.22, 0.055, 1);
  sprite.renderOrder = 10;
  return sprite;
}

function buildSg90Mesh(accent) {
  const g = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.09, 0.11, 0.05),
    matteMat(0x1a72c8)
  );
  const cap = new THREE.Mesh(
    new THREE.BoxGeometry(0.075, 0.018, 0.042),
    matteMat(0x125599)
  );
  cap.position.y = 0.064;
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(0.048, 0.008, 8, 20),
    matteMat(accent, accent, 0.12)
  );
  ring.rotation.x = Math.PI / 2;
  ring.position.y = 0.072;
  g.add(body, cap, ring);
  g.userData.ring = ring;
  g.userData.body = body;
  return g;
}

export class MeArmTwin {
  constructor(scene, { scale = 0.13, plateGap = 0.018 } = {}) {
    this.scale = scale;
    this.plateGap = plateGap;
    this.model = structuredClone(MEARM_MODEL);
    this.context = {
      joints: {},
      cte: { ...this.model.cte },
      var: { ...this.model.var },
    };

    this.root = new THREE.Group();
    this.armGroup = new THREE.Group();
    this.root.add(this.armGroup);
    scene.add(this.root);

    this.linkMeshes = [];
    this.jointPins = {};
    this.servoMeshes = {};
    this.jawGroup = new THREE.Group();
    this.prevServos = { ...MEARM_DEFAULT_HOME };
    this.activeServo = null;
    this._gripperSpread = 0;
    this.themeKey = "white";
    this.themeParts = { base: null, baseCut: null, links: [], joints: [], jaws: [] };

    this._buildBase();
    this._buildLinks();
    this._buildJoints();
    this._buildServos();
    this._buildJaws();

    this.root.scale.setScalar(scale);
    this.root.position.set(0, 0.004, 0);
    this.setTheme(this.themeKey);
    this.setServos(this.prevServos);
  }

  setTheme(key) {
    const theme = MEARM_THEMES[key];
    if (!theme) return this.themeKey;

    this.themeKey = key;
    if (this.themeParts.base) this.themeParts.base.color.setHex(theme.base);
    if (this.themeParts.baseCut) this.themeParts.baseCut.color.setHex(theme.baseCut);

    this.themeParts.links.forEach(({ mat, kind }) => {
      const c = kind === "par" ? theme.linkPar : kind === "grip" ? theme.linkGrip : theme.linkMain;
      mat.color.setHex(c);
    });
    this.themeParts.joints.forEach((mat) => mat.color.setHex(theme.joint));
    this.themeParts.jaws.forEach((mat) => mat.color.setHex(theme.jaw));

    return this.themeKey;
  }

  cycleTheme() {
    const i = MEARM_THEME_ORDER.indexOf(this.themeKey);
    const next = MEARM_THEME_ORDER[(i + 1) % MEARM_THEME_ORDER.length];
    this.setTheme(next);
    return { key: this.themeKey, label: MEARM_THEMES[this.themeKey].label };
  }

  _buildBase() {
    const plate = new THREE.Mesh(
      new THREE.BoxGeometry(1.05, 0.012, 0.78),
      matteMat(MEARM_THEMES.white.base)
    );
    plate.position.y = -0.006;
    this.root.add(plate);
    this.themeParts.base = plate.material;

    const cut = new THREE.Mesh(
      new THREE.BoxGeometry(0.32, 0.014, 0.32),
      matteMat(MEARM_THEMES.white.baseCut)
    );
    cut.position.set(0.12, -0.005, 0);
    this.root.add(cut);
    this.themeParts.baseCut = cut.material;
  }

  _buildLinks() {
    Object.entries(this.model.li).forEach(([name, link]) => {
      const isPar = PARALLEL_LINKS.has(name);
      const isGrip = GRIPPER_LINKS.has(name);
      const kind = isGrip ? "grip" : isPar ? "par" : "main";

      [-1, 1].forEach((side) => {
        const geo = new THREE.BoxGeometry(link.l, link.w, link.p * 0.85);
        const mat = matteMat(MEARM_THEMES.white.linkMain);
        const mesh = new THREE.Mesh(geo, mat);
        mesh.userData.link = link;
        mesh.userData.side = side;
        this.linkMeshes.push({ mesh, link });
        this.themeParts.links.push({ mat, kind });
        this.armGroup.add(mesh);
      });
    });
  }

  _buildJoints() {
    Object.keys(this.model.jo).forEach((name) => {
      const mat = matteMat(MEARM_THEMES.white.joint, 0x111111, 0.04);
      const pin = new THREE.Mesh(new THREE.SphereGeometry(0.028, 12, 12), mat);
      this.jointPins[name] = pin;
      this.themeParts.joints.push(mat);
      this.armGroup.add(pin);
    });
  }

  _buildServos() {
    Object.entries(SERVO_MAP).forEach(([key, spec]) => {
      const servo = buildSg90Mesh(spec.color);
      const hex = `#${spec.color.toString(16).padStart(6, "0")}`;
      const label = makeLabel(`${spec.id} ${spec.label}\nGPIO ${spec.gpio}`, hex);
      label.position.set(0, 0.16, 0);
      servo.add(label);
      servo.userData.servoKey = key;
      servo.userData.label = label;
      this.servoMeshes[key] = servo;
      this.armGroup.add(servo);
    });
  }

  _buildJaws() {
    const jawGeo = new THREE.BoxGeometry(0.04, 0.12, 0.018);
    const matL = matteMat(MEARM_THEMES.white.jaw);
    const matR = matteMat(MEARM_THEMES.white.jaw);
    this.jawL = new THREE.Mesh(jawGeo, matL);
    this.jawR = new THREE.Mesh(jawGeo, matR);
    this.jawL.position.set(-0.03, 0.06, -0.012);
    this.jawR.position.set(0.03, 0.06, 0.012);
    this.jawGroup.add(this.jawL, this.jawR);
    this.themeParts.jaws.push(matL, matR);
    this.armGroup.add(this.jawGroup);
  }

  /** Telemetría firmware: ángulos lógicos 0–180° = mismos que sliders/dashboard */
  setServos(servos, lastAction = "", status = "IDLE", meta = null) {
    this._limits = meta?.limits || MEARM_DEFAULT_LIMITS;
    const kin = firmwareToKinematics(servos, meta);
    const s = kin.servos;

    this.context.var.alpha0 = kin.alpha0;
    this.context.var.alpha1 = kin.alpha1;
    this.context.var.alpha2 = kin.alpha2;
    this.context.cte.beta3 = kin.beta3;
    this._elbowAlpha = kin.alpha2;
    this._gripperSpread = kin.jawSpread;

    this._detectActiveServo(s, lastAction);
    this.prevServos = { ...s };

    this._updateMechanism();
    this._updateVisuals(s);
    this._updateLegend(s, status);
  }

  _detectActiveServo(s, lastAction) {
    const act = (lastAction || "").toUpperCase();
    if (act.includes("GRIPPER") || act.includes("GRIP")) {
      this.activeServo = "gripper";
      return;
    }
    if (act.includes("ELBOW") || act.includes("CODO")) {
      this.activeServo = "elbow";
      return;
    }
    if (act.includes("SHOULDER") || act.includes("HOMBRO")) {
      this.activeServo = "shoulder";
      return;
    }
    if (act.includes("HOME")) {
      this.activeServo = "base";
      return;
    }
    for (const key of ["base", "shoulder", "elbow", "gripper"]) {
      if (act.includes(key.toUpperCase())) {
        this.activeServo = key;
        return;
      }
    }
    const thresholds = { base: 0.4, shoulder: 0.4, elbow: 0.2, gripper: 0.4 };
    let maxD = 0.15;
    let active = null;
    for (const key of ["base", "shoulder", "elbow", "gripper"]) {
      const d = Math.abs(s[key] - this.prevServos[key]);
      const thr = thresholds[key] ?? 0.4;
      if (d >= thr && d > maxD) {
        maxD = d;
        active = key;
      }
    }
    this.activeServo = active;
  }

  _updateMechanism() {
    this.context.joints = {};
    this.context.joints.a = new THREE.Vector3(0, 0, 0);
    Object.keys(this.model.jo).forEach((name) => this._solveJoint(name));
  }

  _solveJoint(name) {
    if (this.context.joints[name]) return;
    const j = this.model.jo[name];

    if (j.fbl) {
      this._solveFBL(name, j);
      return;
    }

    const transforms = j.transforms || j.transform;
    if (!transforms) return;

    let parent = null;
    let angle = 0;
    let length = 0;

    transforms.forEach((t) => {
      if (t.parent) {
        parent = t.parent;
        this._solveJoint(parent);
      }
      if (t.Rz) {
        angle = THREE.MathUtils.degToRad(this._eval(t.Rz));
      }
      if (t.T) {
        length = this.model.li[t.T.replace("@li.", "")].l;
      }
    });

    const P = this.context.joints[parent];
    const x = P.x + length * Math.cos(angle);
    const y = P.y + length * Math.sin(angle);
    this.context.joints[name] = new THREE.Vector3(x, y, 0);
  }

  _solveFBL(name, j) {
    const [Aname, Bname, Dname, L2name, L3name] = j.fbl.split(",");
    this._solveJoint(Aname);
    this._solveJoint(Bname);
    this._solveJoint(Dname);

    const A = this.context.joints[Aname];
    const B = this.context.joints[Bname];
    const D = this.context.joints[Dname];
    const L2 = this.model.li[L2name].l;
    const L3 = this.model.li[L3name].l;
    this.context.joints[name] = this._fbl(A, D, B, L2, L3, -1);
  }

  _eval(expr) {
    const ctx = this.context;
    expr = expr.replace(/@ang\((\w+),(\w+)\)/g, (_, a, b) => {
      const A = ctx.joints[a];
      const B = ctx.joints[b];
      return (Math.atan2(B.y - A.y, B.x - A.x) * 180) / Math.PI;
    });
    expr = expr.replace(/@cte\.(\w+)/g, (_, n) => ctx.cte[n]);
    expr = expr.replace(/@var\.(\w+)/g, (_, n) => ctx.var[n]);
    return Function(`return ${expr}`)();
  }

  _fbl(A, D, B, L2, L3, elbow = 1) {
    const AB = new THREE.Vector3().subVectors(B, A);
    const BD = new THREE.Vector3().subVectors(D, B);
    const d = BD.length();
    const ex = BD.clone().normalize();
    const a = (L2 * L2 - L3 * L3 + d * d) / (2 * d);
    const h2 = L2 * L2 - a * a;
    if (h2 < 0) return B.clone();
    const h = Math.sqrt(h2);
    const P = B.clone().add(ex.clone().multiplyScalar(a));
    const normal = new THREE.Vector3().crossVectors(AB, BD).normalize();
    const ey = new THREE.Vector3().crossVectors(normal, ex).normalize();
    return P.clone().add(ey.multiplyScalar(elbow * h));
  }

  _updateVisuals(servos) {
    Object.entries(this.context.joints).forEach(([name, pos]) => {
      if (this.jointPins[name]) {
        this.jointPins[name].position.set(pos.x, pos.y, 0);
      }
    });

    this.linkMeshes.forEach(({ mesh, link }) => {
      const A = this.context.joints[link.nodes[0]];
      const B = this.context.joints[link.nodes[1]];
      if (!A || !B) return;

      const side = mesh.userData.side ?? 1;
      const mid = new THREE.Vector3().addVectors(A, B).multiplyScalar(0.5);
      mesh.position.copy(mid);
      mesh.position.z = side * this.plateGap * 0.5;

      const dir = new THREE.Vector3().subVectors(B, A).normalize();
      const quat = new THREE.Quaternion();
      quat.setFromUnitVectors(new THREE.Vector3(1, 0, 0), dir);
      mesh.setRotationFromQuaternion(quat);
    });

    this.armGroup.rotation.y = THREE.MathUtils.degToRad(this.context.var.alpha0);

    Object.entries(SERVO_MAP).forEach(([key, spec]) => {
      const joint = this.context.joints[spec.joint];
      const mesh = this.servoMeshes[key];
      if (!joint || !mesh) return;

      mesh.position.set(joint.x, joint.y, 0);
      if (key === "shoulder") {
        const lo = this._limits?.shoulder?.[0] ?? MEARM_DEFAULT_LIMITS.shoulder[0];
        const hi = this._limits?.shoulder?.[1] ?? MEARM_DEFAULT_LIMITS.shoulder[1];
        mesh.rotation.z = THREE.MathUtils.degToRad(lo + hi - servos.shoulder - 90);
      } else if (key === "elbow") {
        mesh.rotation.z = THREE.MathUtils.degToRad(this._elbowAlpha ?? 0);
      } else if (key === "gripper") {
        mesh.rotation.z = THREE.MathUtils.degToRad((servos.gripper - 90) * 0.85);
      } else if (key === "base") {
        mesh.rotation.y = 0;
      }
      const active = this.activeServo === key;
      const em = active ? 0.45 : 0.08;
      mesh.userData.body.material.emissive.setHex(spec.color);
      mesh.userData.body.material.emissiveIntensity = em;
      mesh.userData.ring.material.emissive.setHex(spec.color);
      mesh.userData.ring.material.emissiveIntensity = active ? 0.9 : 0.2;
      mesh.scale.setScalar(active ? 1.12 : 1);
    });

    const j = this.context.joints.j;
    const i = this.context.joints.i;
    if (j && i) {
      this.jawGroup.position.copy(j);
      const ang = Math.atan2(j.y - i.y, j.x - i.x);
      this.jawGroup.rotation.z = ang;
      const spread = THREE.MathUtils.degToRad(this._gripperSpread ?? 0);
      this.jawL.rotation.z = spread;
      this.jawR.rotation.z = -spread;
    }
  }

  _updateLegend(servos, status) {
    const el = document.getElementById("twinArmLegend");
    if (!el) return;
    el.querySelectorAll("[data-servo]").forEach((item) => {
      const key = item.dataset.servo;
      const spec = SERVO_MAP[key];
      const val = servos[key];
      const active = this.activeServo === key;
      item.classList.toggle("is-active", active);
      const valEl = item.querySelector("[data-val]");
      if (valEl) valEl.textContent = `${Math.round(val)}°`;
      const idEl = item.querySelector("[data-id]");
      if (idEl) idEl.textContent = `${spec.id} · GPIO ${spec.gpio}`;
    });
    const st = document.getElementById("twinArmLegendStatus");
    if (st) st.textContent = status || "IDLE";
  }
}
