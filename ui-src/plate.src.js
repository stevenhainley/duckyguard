// DuckyGuard's centrepiece, in real 3D: a cyber duck head sculpted from a depth map, floating inside a wire cage in
// front of a halo, rendered with three.js and then dithered down to two inks (plus red when it is angry).
// Every moving part is driven by keystroke timing, never by which key was pressed:
//   halo spokes = the last 64 gaps and holds     lens aperture = key hold     circuit flow, cage spin = typing rate
//   cables = variation between gaps              crest = burst length         bill = each key      eyes = verdict
// Build: `npm run build` in ui-src/ writes src/duckyguard/ui/plate.js.
import {
  AddEquation, CircleGeometry, ColorManagement, CustomBlending, CylinderGeometry, DoubleSide, Group, IcosahedronGeometry,
  InstancedMesh, LinearFilter, Matrix4, Mesh, MeshBasicMaterial, NearestFilter, OneFactor, OrthographicCamera,
  PerspectiveCamera, PlaneGeometry, Points, Quaternion, RingGeometry, Scene, ShaderMaterial, Texture, Vector3, BufferAttribute,
  Color, WebGLRenderTarget, WebGLRenderer,
} from 'three';

ColorManagement.enabled = false;                         // the scene carries tone values, not colours

const PHI = (1 + Math.sqrt(5)) / 2, ICO = [];
for (const a of [-1, 1]) for (const b of [-PHI, PHI]) ICO.push([0, a, b], [a, b, 0], [b, 0, a]);
const EDGES = [];
for (let i = 0; i < 12; i++) for (let j = i + 1; j < 12; j++) if (Math.abs(Math.hypot(ICO[i][0] - ICO[j][0], ICO[i][1] - ICO[j][1], ICO[i][2] - ICO[j][2]) - 2) < 1e-6) EDGES.push([i, j]);
const NORM = Math.hypot(1, PHI), CAGE = 1.86;
const S = 3.3, D = 1.15, BACK = 0.38, HEAD_Z = -0.45;   // head size, relief depth, back shell depth, where the relief sits
const VIEW = 4.13;                                       // world units across the plate at the origin
const EYE = [0.328, 0.336], LENS = [0.617, 0.346];       // the living eye and the mechanical one, in picture coordinates
// Where each reading lives on the head (picture coordinates), so the page can draw a line from its label to the part.
const PARTS = { burst: [0.52, 0.10], press: LENS, verdict: [0.25, 0.655], rate: [0.675, 0.47], rhythm: [0.60, 0.88] };

// ── shared GLSL: where a point of the picture sits in space, and how its parts move ──
const PLACE = `
uniform sampler2D uTex;
uniform float uTime, uCv, uBurst, uFlash, uJaw, uCalm, uBackSide;
const float S = ${S.toFixed(2)}, D = ${D.toFixed(2)}, BACK = ${BACK.toFixed(2)};
float relief(vec4 t){ return t.g * smoothstep(0., .125, t.b); }
float jawMask(vec2 q){ return smoothstep(.60, .655, q.y) * smoothstep(.80, .70, q.y) * smoothstep(.10, .22, q.x) * smoothstep(.66, .50, q.x); }
vec3 place(vec2 q, out vec4 t){
  t = texture2D(uTex, q);
  float back = 1. - min(1., t.b * 1.6);
  vec3 p = vec3((q.x - .5) * S, (.5 - q.y) * S, mix(relief(t) * D, -BACK * sqrt(1. - back * back), uBackSide));
  float cab = smoothstep(.74, .98, q.y), loose = min(1.4, .15 + uCv * 2.4) * uCalm;                        // cables hang and swing
  p.x += (sin(uTime * 1.7 + q.y * 17.) + .5 * sin(uTime * 2.9 + q.y * 31.)) * .016 * S * cab * loose;
  p.z += cos(uTime * 1.3 + q.y * 13.) * .10 * cab * loose;
  float tuft = smoothstep(.19, .03, q.y);                                                                 // the crest ruffles
  p.x += (sin(uTime * 2.4 + q.y * 20.) * (.004 + .016 * min(1., uBurst / 24.)) + uFlash * .007) * S * tuft * uCalm;
  p.z += sin(uTime * 1.9 + q.x * 24.) * .05 * tuft * min(1., .2 + uBurst / 24.) * uCalm;
  p.y -= jawMask(q) * uJaw * S;                                                                           // the bill opens
  return p;
}`;

const HEAD_VERT = `${PLACE}
varying vec2 vQ;
void main(){ vQ = vec2(uv.x, 1. - uv.y); vec4 t; gl_Position = projectionMatrix * modelViewMatrix * vec4(place(vQ, t), 1.); }`;

const HEAD_FRAG = `
uniform sampler2D uTex;
uniform vec3 uLight; uniform vec2 uLook;
uniform float uTime, uFlash, uAlert, uAnger, uHold, uSpin, uFlow, uBlink, uReveal, uBackSide;
varying vec2 vQ;
const float PI = 3.14159265, S = ${S.toFixed(2)}, D = ${D.toFixed(2)};
float relief(vec2 q){ vec4 t = texture2D(uTex, q); return t.g * smoothstep(0., .125, t.b); }
float jawMask(vec2 q){ return smoothstep(.60, .655, q.y) * smoothstep(.80, .70, q.y) * smoothstep(.10, .22, q.x) * smoothstep(.66, .50, q.x); }
void main(){
  vec2 p = vQ; vec4 t = texture2D(uTex, p);
  if (t.a < .5 || p.y > uReveal) discard;
  float edge = uReveal < 1.5 && uReveal - p.y < .012 ? 1. : 0.;                       // the line that scans the head into being
  if (uBackSide > .5) { gl_FragColor = vec4((edge > 0. ? 1.6 : .07 + .10 * step(.55, fract(p.y * 72.))) * .5, 0., 0., 1.); return; }

  float e = 4. / 512., k = D / S / (2. * e);
  vec3 n = normalize(vec3(-(relief(p + vec2(e, 0.)) - relief(p - vec2(e, 0.))) * k, (relief(p + vec2(0., e)) - relief(p - vec2(0., e))) * k, 1.));
  float lit = max(dot(n, uLight), 0.), rim = pow(1. - n.z, 2.);
  float vh = (pow(t.r, 1.35) * .92 + .055) * (.30 + .68 * lit) * (.92 + .14 * t.g) + .16 * rim * t.r;

  vec2 ld = p - vec2(${LENS[0]}, ${LENS[1]}); float lr = length(ld);                   // mechanical lens: aperture follows key hold
  float ap = mix(mix(.010, .036, clamp(uHold / 110., 0., 1.)), .007, uAlert);
  if (lr < .078) {
    if (lr < ap) vh = 1.7;
    else if (lr > .050 && lr < .066) vh = max(vh * .5, 1.25 * step(.5, fract(atan(ld.y, ld.x) * 9. / (2. * PI) + uSpin)));
    vh += uFlash * .35;
  }
  if (uAlert > .5 && abs(lr - (.09 + .05 * fract(uTime * 1.4))) < .006) vh = 1.6;     // warning rings off the lens
  vec2 cd = (p - vec2(.675, .46)) / vec2(.13, .25); float circ = 1. - smoothstep(.75, 1., length(cd));   // exposed circuitry
  float flow = mix(step(.70, fract(p.y * 21. - uFlow + sin(p.x * 55.) * .35)), 1., uAlert);
  vh += circ * pow(t.r, 1.3) * flow * 1.1;

  vec2 eye = vec2(${EYE[0]}, ${EYE[1]});                                               // the living eye: catch-light, blink
  if (length(p - eye - uLook * vec2(.010, -.008) - vec2(-.010, -.012)) < .0075) vh = 1.6;
  vec2 lid = (p - eye) / vec2(.036, .028);
  if (uBlink > 0. && dot(lid, lid) < 1. && lid.y < -1. + 2. * uBlink) vh = .26 + .22 * lit;
  vh *= 1. + .28 * jawMask(p) * uFlash;

  float browL = abs(p.y - (.268 + (p.x - .255) * .30)) - .013, browR = abs(p.y - (.300 - (p.x - .535) * .31)) - .014;   // anger: brows come down
  if ((browL < 0. && p.x > .255 && p.x < .405) || (browR < 0. && p.x > .535 && p.x < .705)) vh = mix(vh, 0., uAnger);
  if (edge > 0.) vh = 1.7;
  gl_FragColor = vec4(min(vh, 2.) * .5, 0., 0., 1.);
}`;

const CLOUD_VERT = `${PLACE}
attribute vec3 aRnd; uniform float uScatter, uPoint; varying float vTone;
void main(){
  vec2 q = vec2(uv.x, 1. - uv.y); vec4 t; vec3 p = place(q, t);
  vec3 dir = normalize(aRnd - .5); float far = uScatter * (1.1 + 2.4 * aRnd.x), a = uScatter * 2.6 * (aRnd.y - .5);
  p += dir * far; p.xz = mat2(cos(a), -sin(a), sin(a), cos(a)) * p.xz;               // they swirl in from a cloud
  gl_Position = t.a < .5 ? vec4(2., 2., 2., 1.) : projectionMatrix * modelViewMatrix * vec4(p, 1.);
  gl_PointSize = uPoint; vTone = .55 + t.r;
}`;
const CLOUD_FRAG = `varying float vTone; void main(){ gl_FragColor = vec4(min(vTone, 1.9) * .5, 0., 0., 1.); }`;

const GLOW_VERT = `varying vec2 vP; void main(){ vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.); }`;
const GLOW_FRAG = `uniform float uAnger, uTime, uCore; varying vec2 vP;
void main(){ float r = length(vP); gl_FragColor = vec4(0., (1. - r) * uAnger * (.82 + .18 * sin(uTime * 9.)), step(r, uCore) * step(.5, uAnger), 0.); }`;

// ── the print: tone -> two inks through an ordered dither, with scanlines, the inversion and the glitch ──
const POST_VERT = `void main(){ gl_Position = vec4(position.xy, 0., 1.); }`;
const POST_FRAG = `
uniform sampler2D tScene; uniform vec2 uRes; uniform vec3 uInk, uPaper, uRed;
uniform float uAlert, uInvert, uGlitch, uTime;
float bayer2(vec2 a){ a = floor(a); return fract(a.x / 2. + a.y * a.y * .75); }
float bayer4(vec2 a){ return bayer2(.5 * a) * .25 + bayer2(a); }
float bayer8(vec2 a){ return bayer4(.5 * a) * .25 + bayer2(a); }
float hash(float n){ return fract(sin(n * 12.9898) * 43758.5453); }
void main(){
  vec2 fc = gl_FragCoord.xy, uv = fc / uRes;
  float tick = floor(uTime * 28.), band = floor(uv.y * 22.);
  float torn = step(1. - .55 * uGlitch, hash(band + tick * 3.1)) * uGlitch;           // a block tears the picture sideways for a moment
  uv.x = fract(uv.x + (hash(band * 7.3 + tick) - .5) * .22 * torn);
  vec4 s = texture2D(tScene, uv);
  vec2 c = uv - .5; float v = .045 + .16 * max(0., 1. - length(c) * 2.1);
  v = mix(v, s.r * 2., s.a);
  float y = floor(fc.y);
  v *= mix(.9 + .1 * sin(y * 2.0944), mod(y, 4.) < 2. ? 1.25 : .5, step(.5, uAlert));
  if (torn > 0. && hash(band + tick) > .6) v = max(v, .8);
  bool on = v > bayer8(fc) + .008;
  vec2 cell = floor(fc / 6.);
  if (uInvert > hash(cell.x * 3.7 + cell.y * 91.3)) on = !on;                          // the plate inverts cell by cell
  vec3 col = on ? uInk : uPaper;
  if (s.g > 0. && s.g * 1.3 > bayer8(fc + 3.)) col = uRed;                             // red burns through the print
  if (s.b > .5) col = vec3(1., .93, .86);
  gl_FragColor = vec4(col, 1.);
}`;

const spring = (k, c) => ({ x: 0, v: 0, to: 0, k, c, step(dt) { this.v += (-this.k * (this.x - this.to) - this.c * this.v) * dt; this.x += this.v * dt; return this.x; } });
const clamp01 = x => Math.max(0, Math.min(1, x)), easeOut = x => 1 - (1 - clamp01(x)) ** 3, easeInOut = x => { x = clamp01(x); return x * x * (3 - 2 * x); };

// DuckPlate(canvas, { ink, paper, red, texture, onParts })
//   -> { pushKey(gapMs, holdMs, quiet), set({ alert, hold, burst }), stats(), canvas, visible(bool), mirror(bool), intro() }
// Draws only while the window is visible and something is moving; idle frames drop to a slow breathing rate.
function DuckPlate(cv, opts) {
  const renderer = new WebGLRenderer({ canvas: cv, antialias: false, alpha: false, preserveDrawingBuffer: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(1); renderer.setSize(cv.width, cv.height, false); renderer.autoClear = true;
  renderer.setClearColor(new Color(...opts.paper), 1); renderer.clear();          // paper, not black, until the first frame
  const W = cv.width, H = cv.height;
  const target = new WebGLRenderTarget(W, H, { minFilter: NearestFilter, magFilter: NearestFilter, depthBuffer: true });
  const scene = new Scene(), camera = new PerspectiveCamera(2 * Math.atan(1 / 2.35) * 180 / Math.PI, W / H, 0.5, 20);
  camera.position.set(0, 0, 4.85);
  const rig = new Group(), head = new Group(); scene.add(rig); rig.add(head);

  // the head: a relief in front, a rounded shell behind, and the same surface as a cloud of points
  const tex = new Texture(); tex.flipY = false; tex.generateMipmaps = false; tex.minFilter = tex.magFilter = LinearFilter; tex.premultiplyAlpha = false;
  const shared = { uTex: { value: tex }, uTime: { value: 0 }, uCv: { value: .4 }, uBurst: { value: 0 }, uFlash: { value: 0 }, uJaw: { value: 0 }, uCalm: { value: 1 },
    uLight: { value: new Vector3(0, 0, 1) }, uLook: { value: [0, 0] }, uAlert: { value: 0 }, uAnger: { value: 0 }, uHold: { value: 90 }, uSpin: { value: 0 },
    uFlow: { value: 0 }, uBlink: { value: 0 }, uReveal: { value: 2 }, uScatter: { value: 0 }, uPoint: { value: Math.max(1.5, W / 250) } };
  const headMat = side => new ShaderMaterial({ uniforms: { ...shared, uBackSide: { value: side } }, vertexShader: HEAD_VERT, fragmentShader: HEAD_FRAG, side: DoubleSide });
  const grid = new PlaneGeometry(1, 1, 255, 255), body = new Group(); body.position.z = HEAD_Z; head.add(body);
  const front = new Mesh(grid, headMat(0)), back = new Mesh(grid, headMat(1));
  front.frustumCulled = back.frustumCulled = false; body.add(back, front);
  const cloudGeo = new PlaneGeometry(1, 1, 159, 159), rnd = new Float32Array(cloudGeo.attributes.position.count * 3);
  for (let i = 0; i < rnd.length; i++) rnd[i] = Math.random();
  cloudGeo.setAttribute('aRnd', new BufferAttribute(rnd, 3));
  const cloud = new Points(cloudGeo, new ShaderMaterial({ uniforms: { ...shared, uBackSide: { value: 0 } }, vertexShader: CLOUD_VERT, fragmentShader: CLOUD_FRAG }));
  cloud.frustumCulled = false; cloud.visible = false; body.add(cloud);

  // red light in both eyes, placed on the surface once the picture has loaded
  const glowMat = core => new ShaderMaterial({ uniforms: { uAnger: shared.uAnger, uTime: shared.uTime, uCore: { value: core } }, vertexShader: GLOW_VERT, fragmentShader: GLOW_FRAG,
    transparent: true, depthWrite: false, blending: CustomBlending, blendEquation: AddEquation, blendSrc: OneFactor, blendDst: OneFactor, blendSrcAlpha: OneFactor, blendDstAlpha: OneFactor });
  const disc = new CircleGeometry(1, 28), glowL = new Mesh(disc, glowMat(.23)), glowR = new Mesh(disc, glowMat(.175));
  glowL.scale.setScalar(.075 * S); glowR.scale.setScalar(.115 * S); glowL.renderOrder = glowR.renderOrder = 5; body.add(glowL, glowR);
  const seat = (m, q, depth) => m.position.set((q[0] - .5) * S, (.5 - q[1]) * S, depth * D + .07);
  seat(glowL, EYE, .45); seat(glowR, LENS, .57);

  let ready = false, dirty = true, mirror = false;
  const partDepth = { burst: .44, press: .57, verdict: .8, rate: .5, rhythm: .3 };
  const art = new Image();
  art.onload = () => {
    tex.image = art; tex.needsUpdate = true;
    try { const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d', { willReadFrequently: true }); g.drawImage(art, 0, 0, 64, 64);
      const at = q => g.getImageData(Math.floor(q[0] * 64), Math.floor(q[1] * 64), 1, 1).data[1] / 255; seat(glowL, EYE, at(EYE)); seat(glowR, LENS, at(LENS));
      for (const k in PARTS) partDepth[k] = at(PARTS[k]); } catch (e) { /* keep the defaults */ }
    ready = true; dirty = true;
  };
  art.src = opts.texture;

  // the cage: thirty wires, twelve nodes, and pulses that run along the wires on every key
  const tone = v => new Color(v * .5, 0, 0), flat = v => new MeshBasicMaterial({ color: tone(v) });
  const wireMat = flat(.6), wires = new InstancedMesh(new CylinderGeometry(.010, .010, 1, 5, 1, true), wireMat, 30);
  const knots = new InstancedMesh(new IcosahedronGeometry(.036, 1), flat(1), 12), sparks = new InstancedMesh(new IcosahedronGeometry(1, 1), flat(1.5), 10);
  for (const m of [wires, knots, sparks]) { m.frustumCulled = false; rig.add(m); }

  // the halo: the last 64 keys, one spoke each, standing behind the head
  const halo = new Group(); halo.position.z = -.6; halo.scale.setScalar(1.12); rig.add(halo);
  const spokeGeo = new PlaneGeometry(1, 1); spokeGeo.translate(.5, 0, 0);
  const spokes = new InstancedMesh(spokeGeo, new MeshBasicMaterial({ color: 0xffffff, side: DoubleSide }), 64); spokes.frustumCulled = false;
  const ring = new Mesh(new RingGeometry(.3705 * VIEW, .3760 * VIEW, 96), new MeshBasicMaterial({ color: tone(.7), side: DoubleSide }));
  halo.add(ring, spokes);

  // the print pass
  const post = new ShaderMaterial({ uniforms: { tScene: { value: target.texture }, uRes: { value: [W, H] }, uInk: { value: opts.ink }, uPaper: { value: opts.paper }, uRed: { value: opts.red || [.9, .15, .1] },
    uAlert: { value: 0 }, uInvert: { value: 0 }, uGlitch: { value: 0 }, uTime: shared.uTime }, vertexShader: POST_VERT, fragmentShader: POST_FRAG, depthTest: false, depthWrite: false });
  const postScene = new Scene(), postCam = new OrthographicCamera(-1, 1, 1, -1, 0, 1), quad = new Mesh(new PlaneGeometry(2, 2), post); quad.frustumCulled = false; postScene.add(quad);

  // ── what the keys have been doing ──
  const N = 64, len = new Float32Array(N).fill(.05), wid = new Float32Array(N).fill(.005), keys = [], pulses = [];
  let slot = 0, flash = 0, alert = 0, hold = 0, burst = 0, edgeAt = 0, lastKeyAt = 0;
  const lenOf = gap => .05 + .36 * Math.min(1, Math.log2(Math.max(gap, 4) / 4) / 6.2), widOf = h => .005 + .013 * Math.min(1, h / 110);
  const yawS = spring(60, 11), pitchS = spring(60, 11), cageS = spring(120, 12), nodS = spring(180, 14); cageS.x = cageS.to = 1;
  function pushKey(gap, holdMs, quiet) {
    slot = (slot + 1) % N; len[slot] = lenOf(gap); wid[slot] = widOf(holdMs); keys.push({ gap, hold: holdMs }); if (keys.length > N) keys.shift();
    if (quiet) return;
    flash = 1; nodS.v += 1.1; edgeAt = (edgeAt + 7) % 30; lastKeyAt = performance.now(); dirty = true;
    if (pulses.length < 10) pulses.push({ e: edgeAt, t: 0, speed: Math.min(9, 420 / Math.max(gap, 30)), size: .024 + .026 * Math.min(1, holdMs / 110), hops: 2 });
  }
  function stats() {
    const k = keys.slice(-14).filter(x => x.gap < 1500); if (k.length < 2) return { rate: 0, cv: 0, hold: k.length ? k[0].hold : 0, n: keys.length };
    const g = k.map(x => x.gap), mean = g.reduce((a, b) => a + b, 0) / g.length, sd = Math.sqrt(g.reduce((a, b) => a + (b - mean) ** 2, 0) / g.length), hs = k.map(x => x.hold).sort((a, b) => a - b);
    return { rate: 1000 / mean, cv: sd / mean, hold: hs[hs.length >> 1], n: keys.length };
  }
  let glitch = 0, shake = 0, shatter = 0, igniteAt = 0, lockedAt = 0;
  function set(state) {
    const wasLocked = alert || hold, wasAlert = alert;
    if ('alert' in state) alert = state.alert ? 1 : 0; if ('hold' in state) hold = state.hold ? 1 : 0; if ('burst' in state) burst = state.burst;
    if ((alert || hold) && !wasLocked) lockedAt = performance.now();
    if (alert && !wasAlert) { glitch = 1; shake = 1; shatter = 1; igniteAt = performance.now() + 90; cageS.v -= 2.2; }   // a block: tear, flinch, then the eyes light
    else if (hold && !wasLocked) { glitch = .55; shake = .6; igniteAt = performance.now() + 140; cageS.v -= 1.2; }
    dirty = true;
  }

  // ── pointer: the head turns toward it, or you can grab it and turn it yourself ──
  let drag = null, look = [0, 0], lookTo = [.12, .03], lastPointer = 0;
  cv.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY, yaw: yawS.x, pitch: pitchS.x }; cv.setPointerCapture(e.pointerId); });
  cv.addEventListener('pointerup', () => drag = null); cv.addEventListener('pointercancel', () => drag = null);
  addEventListener('pointermove', e => {
    const r = cv.getBoundingClientRect(); lookTo = [Math.max(-1, Math.min(1, (e.clientX - r.left - r.width / 2) / r.width * 1.4)), Math.max(-1, Math.min(1, (e.clientY - r.top - r.height / 2) / r.height * 1.4))]; lastPointer = performance.now();
    if (drag) { yawS.x = Math.max(-.55, Math.min(.55, drag.yaw + (e.clientX - drag.x) * .008)); pitchS.x = Math.max(-.4, Math.min(.4, drag.pitch + (e.clientY - drag.y) * .008)); yawS.v = pitchS.v = 0; }
  });

  const motion = matchMedia('(prefers-reduced-motion: reduce)'); let still = motion.matches;
  motion.addEventListener('change', e => { still = e.matches; dirty = true; });
  const nodes = Array.from({ length: 12 }, () => new Vector3()), m4 = new Matrix4(), q4 = new Quaternion(), up = new Vector3(0, 1, 0), va = new Vector3(), vb = new Vector3(), one = new Vector3(1, 1, 1), zero = new Matrix4().makeScale(0, 0, 0), col = new Color();
  let anger = 0, invert = 0, spin = 0, lensSpin = 0, flow = 0, flex = 0, last = 0, t0 = performance.now(), sHold = 90, sCv = .4, sBurst = 0, shown = true;
  let bootAt = still ? -1 : 0, blinkAt = performance.now() + 2600, blink = 0;
  function intro() { if (!still) { bootAt = 0; dirty = true; } }

  function frame(now) {
    requestAnimationFrame(frame);
    if (!ready || !shown || document.hidden) { last = 0; return; }
    if (bootAt === 0) bootAt = now;
    const boot = bootAt < 0 ? 9 : (now - bootAt) / 1000, booting = boot < 2.3, locked = alert || hold;
    const moving = Math.abs(yawS.v) + Math.abs(pitchS.v) + Math.abs(cageS.v) + Math.abs(nodS.v) + Math.abs(nodS.x) > .002;
    const active = booting || now - lastKeyAt < 2500 || now - lastPointer < 2500 || drag || locked || pulses.length || dirty || anger > .02 || glitch > .01 || invert > .01 || blink > 0 || moving || mirror;
    if (!active && last && now - last < 250) return;
    const settled = locked && !booting && !moving && !drag && !mirror && glitch < .01 && shatter < .01 && Math.abs(alert - invert) < .01 && now - lockedAt > 2000;
    if (settled && last && now - last < 100) return;                 // a long hold only needs the eyes to flicker
    const dt = last ? Math.min(.05, (now - last) / 1000) : 0; last = now; dirty = false;
    const s = stats(), ease = k => Math.min(1, dt * k), time = still ? 0 : (now - t0) / 1000, typing = now - lastKeyAt < 1500, rate = typing ? s.rate : 0;

    // head pose: springs, so it settles with a little weight and snaps round when something is wrong
    const aim = locked ? [0, 0] : lookTo; look[0] += (aim[0] - look[0]) * ease(6); look[1] += (aim[1] - look[1]) * ease(6);
    yawS.k = pitchS.k = locked ? 230 : 60; yawS.c = pitchS.c = locked ? 17 : 11;
    yawS.to = locked ? 0 : look[0] * .34 + (still ? 0 : .05 * Math.sin(now / 2400)); pitchS.to = locked ? 0 : look[1] * .24;
    if (!drag) { yawS.step(dt); pitchS.step(dt); }
    nodS.step(dt); cageS.to = locked ? .9 : 1; cageS.step(dt);
    shake = Math.max(0, shake - dt * 2.6); glitch = Math.max(0, glitch - dt * 3.4); shatter = Math.max(0, shatter - dt * 2.9); flash = Math.max(0, flash - dt * 5);
    const lit = locked && now >= igniteAt; anger += ((lit ? 1 : 0) - anger) * ease(lit ? 14 : 3); invert += (alert - invert) * ease(9); if (Math.abs(alert - invert) < .004) invert = alert;
    if (!locked && !still) { spin += dt * (.10 + rate * .07); lensSpin += dt * (.12 + rate * .05); flow += dt * (.5 + rate * .55); }
    flex += ((locked ? 0 : Math.min(.16, s.cv * .28)) - flex) * ease(4);
    sHold += ((locked ? 1 : s.hold || 90) - sHold) * ease(6); sCv += ((locked ? 0 : s.cv) - sCv) * ease(4); sBurst += ((typing ? burst : 0) - sBurst) * ease(5);
    if (!still && !locked && now > blinkAt) { blink = 1e-3; blinkAt = now + 2400 + Math.random() * 4200; }
    if (blink > 0) { blink += dt / .16; if (blink >= 1) blink = 0; }

    const calm = 1 - invert, tremor = still ? 0 : (shake + .12 * anger) * Math.sin(time * 47);
    rig.rotation.set(pitchS.x * .45, yawS.x * .45, 0);
    head.rotation.set(pitchS.x * .5 + nodS.x * .045, yawS.x * .5, tremor * .012);
    head.position.set(tremor * .02, -.10 - (still ? 0 : .042 * Math.sin(time * 1.15) * calm) - nodS.x * .02, 0);
    head.updateMatrixWorld(true);
    q4.setFromRotationMatrix(head.matrixWorld).invert();
    shared.uLight.value.set(-.35 + look[0] * .75, .45 - look[1] * .75, .8).normalize().applyQuaternion(q4);

    // boot: points swirl in, a line scans the solid head down over them, the cage and halo draw themselves
    const assemble = booting ? 1 - easeOut(boot / 1.15) : 0, burstOut = .42 * shatter * shatter;
    shared.uScatter.value = assemble + burstOut; cloud.visible = (booting && boot < 1.75) || burstOut > .004;
    shared.uReveal.value = booting ? -.03 + 1.1 * easeInOut((boot - .55) / 1.05) : 2;
    const cageIn = booting ? boot - .35 : 9, haloIn = booting ? boot - .7 : 9;

    const u = shared; u.uTime.value = time; u.uCv.value = sCv; u.uBurst.value = sBurst; u.uFlash.value = flash; u.uJaw.value = .020 * flash + .012 * invert; u.uCalm.value = calm;
    u.uLook.value = look; u.uAlert.value = invert; u.uAnger.value = anger; u.uHold.value = sHold; u.uSpin.value = lensSpin; u.uFlow.value = flow;
    u.uBlink.value = blink > 0 ? Math.sin(Math.min(1, blink) * Math.PI) : 0;

    // cage
    const cy = Math.cos(spin), sy = Math.sin(spin), ct = Math.cos(.42), st = Math.sin(.42), R = CAGE * cageS.x;
    for (let i = 0; i < 12; i++) {
      const v = ICO[i], wob = still ? 1 : 1 + flex * Math.sin(now / 420 + i * 2.1);
      const x = v[0] / NORM * R * wob, y = v[1] / NORM * R * wob, z = v[2] / NORM * R * wob, y1 = y * ct - z * st, z1 = y * st + z * ct;
      nodes[i].set(x * cy + z1 * sy, y1, -x * sy + z1 * cy);
      const grow = easeOut((cageIn - i * .04) / .35); knots.setMatrixAt(i, m4.compose(nodes[i], q4.identity(), va.setScalar(grow)));
    }
    for (let i = 0; i < 30; i++) {
      const a = nodes[EDGES[i][0]], b = nodes[EDGES[i][1]], draw = easeInOut((cageIn - i * .022) / .5), L = vb.subVectors(b, a).length() * draw;
      if (L < 1e-4) { wires.setMatrixAt(i, zero); continue; }
      vb.normalize(); q4.setFromUnitVectors(up, vb); wires.setMatrixAt(i, m4.compose(va.copy(a).addScaledVector(vb, L / 2), q4, one.set(1, L, 1)));
    }
    one.set(1, 1, 1); wireMat.color.setRGB((.60 + .45 * invert) * .5, 0, 0);
    for (let i = 0; i < 10; i++) sparks.setMatrixAt(i, zero);
    for (let i = pulses.length - 1; i >= 0; i--) {
      const pz = pulses[i]; pz.t += dt * pz.speed * (locked ? 0 : 1);
      if (pz.t >= 1) {
        const end = EDGES[pz.e][pz.rev ? 0 : 1];
        if (pz.hops-- > 0) { const next = EDGES.map((e, k) => [e, k]).filter(([e, k]) => k !== pz.e && (e[0] === end || e[1] === end)), pick = next[Math.floor(Math.random() * next.length)]; pz.e = pick[1]; pz.rev = pick[0][1] === end; pz.t = 0; }
        else { pulses.splice(i, 1); continue; }
      }
      const [a, b] = EDGES[pz.e], tt = pz.rev ? 1 - pz.t : pz.t;
      sparks.setMatrixAt(i, m4.compose(va.lerpVectors(nodes[a], nodes[b], tt), q4.identity(), vb.setScalar(pz.size)));
    }
    wires.instanceMatrix.needsUpdate = knots.instanceMatrix.needsUpdate = sparks.instanceMatrix.needsUpdate = true;

    // halo
    for (let i = 0; i < N; i++) {
      const ang = (i + .5) / N * 2 * Math.PI - Math.PI, grow = easeOut((haloIn - ((i + 32) % N) * .012) / .4);
      m4.makeRotationZ(ang).multiply(q4m.makeTranslation(.385 * VIEW, 0, 0)).multiply(q4s.makeScale(Math.max(1e-4, len[i] * .26 * VIEW * grow), wid[i] * .54 * VIEW, 1));
      spokes.setMatrixAt(i, m4); spokes.setColorAt(i, col.setRGB(Math.min(1, (.62 + (i === slot ? flash : 0)) * .5), 0, 0));
    }
    spokes.instanceMatrix.needsUpdate = true; spokes.instanceColor.needsUpdate = true; ring.scale.setScalar(easeOut(haloIn / .5) || 1e-4);

    post.uniforms.uAlert.value = invert; post.uniforms.uInvert.value = invert; post.uniforms.uGlitch.value = still ? 0 : glitch;
    renderer.setRenderTarget(target); renderer.setClearColor(0x000000, 0); renderer.clear(); renderer.render(scene, camera);
    renderer.setRenderTarget(null); renderer.render(postScene, postCam);

    if (opts.onParts) {                                   // where each reading's part is on screen right now
      rig.updateMatrixWorld(true);
      const out = {}, put = (k, w) => { w.project(camera); out[k] = { x: .5 + w.x * .5, y: .5 - w.y * .5 }; };
      for (const k in PARTS) put(k, body.localToWorld(va.set((PARTS[k][0] - .5) * S, (.5 - PARTS[k][1]) * S, partDepth[k] * D)));
      put('halo', halo.localToWorld(va.set(Math.cos(3.6) * .44 * VIEW, Math.sin(3.6) * .44 * VIEW, 0)));
      opts.onParts(out);
    }
  }
  const q4m = new Matrix4(), q4s = new Matrix4();
  requestAnimationFrame(frame);
  return { pushKey, set, stats, canvas: cv, intro, visible: v => { if (shown !== !!v) { shown = !!v; dirty = true; } }, mirror: v => { if (mirror !== !!v) { mirror = !!v; dirty = true; } } };
}

globalThis.DuckPlate = DuckPlate;
