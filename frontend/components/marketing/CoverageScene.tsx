"use client";

import { useEffect, useRef, useState } from "react";
import type { CoveragePhase } from "./CoverageObservatory";
import styles from "./CoverageObservatory.module.css";

type SceneRuntime = { setPhase: (phase: CoveragePhase, animate: boolean) => void; setRotation: (rotation: number) => void; dispose: () => void };
export type SceneStatus = "loading" | "ready" | "fallback";
const phaseIndex: Record<CoveragePhase, number> = { uncertainty: 0, questions: 1, clarity: 2 };

function SceneBlueprint({ phase }: { phase: CoveragePhase }) {
  return <svg viewBox="0 0 620 460" className={styles.blueprint} aria-hidden="true"><defs><linearGradient id="coverage-glass" x2="0" y2="1"><stop stopColor="#86c8ed" stopOpacity=".35" /><stop offset="1" stopColor="#86c8ed" stopOpacity=".04" /></linearGradient></defs><ellipse cx="310" cy="340" rx="225" ry="75" fill="#143c78" stroke="#d9bf8c" strokeOpacity=".45" /><path d="M110 300Q110 95 310 95Q510 95 510 300" fill="url(#coverage-glass)" stroke="#9dd5f4" strokeWidth="2" strokeDasharray={phase === "clarity" ? "150 30" : "35 25"} /><path d="m237 250 73-58 73 58v93H237Z" fill="#f8e8c6" /><path d="m225 250 85-69 85 69" fill="none" stroke="#213e63" strokeWidth="15" /><rect x="290" y="284" width="39" height="59" rx="3" fill="#274c7a" /><rect x="248" y="271" width="24" height="30" rx="3" fill="#f1c879" /><rect x="348" y="271" width="24" height="30" rx="3" fill="#f1c879" /><g fill="#fff2d8" stroke="#d8ba7e">{[155, 290, 425].map((x, i) => <g key={x} transform={`translate(${x} ${phase === "questions" ? 110 + i * 25 : 330}) rotate(${phase === "uncertainty" ? (i - 1) * 14 : 0})`}><rect width="84" height="65" rx="5" /><path d="M12 18h55M12 30h42M12 42h48" stroke="#173e7440" /></g>)}</g><circle cx="480" cy="222" r="11" fill="#e4b46d" /><path d="M480 218v6m0 4v1" stroke="#17365e" strokeWidth="2" /></svg>;
}

/** Locally authored procedural models. The renderer exists only when this scene is near view. */
export default function CoverageScene({ phase, rotation, instant, onRotationChange, onStatusChange }: { phase: CoveragePhase; rotation: number; instant: boolean; onRotationChange: (angle: number) => void; onStatusChange: (status: SceneStatus) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const runtime = useRef<SceneRuntime | null>(null);
  const latest = useRef({ phase, rotation, instant, onRotationChange });
  const [status, setStatus] = useState<SceneStatus>("loading");

  useEffect(() => { onStatusChange(status); }, [onStatusChange, status]);
  useEffect(() => { latest.current.onRotationChange = onRotationChange; }, [onRotationChange]);

  useEffect(() => {
    latest.current.phase = phase;
    latest.current.instant = instant;
    runtime.current?.setPhase(phase, !instant);
  }, [phase, instant]);

  useEffect(() => {
    latest.current.rotation = rotation;
    runtime.current?.setRotation(rotation);
  }, [rotation]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let cancelled = false;
    let started = false;
    let visible = false;
    let visibilityUpdate: (() => void) | undefined;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const observer = new IntersectionObserver((entries) => {
      visible = entries[0].isIntersecting;
      visibilityUpdate?.();
      if (!visible || started) return;
      started = true;
      void initialize();
    }, { rootMargin: "120px", threshold: 0.01 });
    observer.observe(element);

    async function initialize() {
      let renderer: import("three").WebGLRenderer | undefined;
      let release: (() => void) | undefined;
      try {
        const THREE = await import("three");
        const { RoundedBoxGeometry } = await import("three/addons/geometries/RoundedBoxGeometry.js");
        const { RoomEnvironment } = await import("three/addons/environments/RoomEnvironment.js");
        const { createCoverageHouse } = await import("./createCoverageHouse");
        if (cancelled) return;
        const canvas = document.createElement("canvas");
        const context = canvas.getContext("webgl2", { alpha: true, antialias: true, preserveDrawingBuffer: true });
        if (!context) { setStatus("fallback"); return; }
        renderer = new THREE.WebGLRenderer({ canvas, context, alpha: true, antialias: true, preserveDrawingBuffer: true, powerPreference: "low-power" });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = .95;
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFShadowMap;
        canvas.setAttribute("aria-hidden", "true");
        canvas.dataset.coverageCanvas = "true";
        canvas.style.touchAction = "pan-y";
        element!.appendChild(canvas);
        const scene = new THREE.Scene();
        const studio = new RoomEnvironment();
        const pmrem = new THREE.PMREMGenerator(renderer);
        const environment = pmrem.fromScene(studio, .04);
        scene.environment = environment.texture; scene.environmentIntensity = .65;
        studio.dispose(); pmrem.dispose();
        const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 60);
        const world = new THREE.Group();
        scene.add(world);
        scene.add(new THREE.HemisphereLight(0xc5e6ff, 0x334268, 1.5));
        const sunlight = new THREE.DirectionalLight(0xffe7b8, 3.2);
        sunlight.position.set(-3, 7, 5);
        sunlight.castShadow = true;
        sunlight.shadow.mapSize.set(1024, 1024);
        sunlight.shadow.camera.left = -5; sunlight.shadow.camera.right = 5;
        sunlight.shadow.camera.bottom = -5; sunlight.shadow.camera.top = 5;
        sunlight.shadow.normalBias = 0.015; sunlight.shadow.bias = -0.0002;
        scene.add(sunlight);
        const rim = new THREE.DirectionalLight(0x9cbcdf, 1.3);
        rim.position.set(5, 4, -5); scene.add(rim);
        const cream = new THREE.MeshStandardMaterial({ color: 0xffedca, roughness: 0.65 });
        const navy = new THREE.MeshStandardMaterial({ color: 0x264869, roughness: 0.35, metalness: 0.25 });
        const gold = new THREE.MeshStandardMaterial({ color: 0xeac785, roughness: 0.3, metalness: 0.55 });
        const windowLight = new THREE.MeshStandardMaterial({ color: 0xffd991, emissive: 0xffc471, emissiveIntensity: 0.3 });
        function box(w: number, h: number, d: number, material: import("three").Material, x: number, y: number, z: number, parent: import("three").Object3D = world) {
          const mesh = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 2, Math.min(0.045, w / 4, h / 4, d / 4)), material);
          mesh.position.set(x, y, z); mesh.castShadow = true; mesh.receiveShadow = true; parent.add(mesh); return mesh;
        }
        const plinth = new THREE.Mesh(new THREE.CylinderGeometry(2.7, 2.55, 0.3, 72), navy);
        plinth.position.y = 0; plinth.receiveShadow = true; world.add(plinth);
        const ground = new THREE.MeshStandardMaterial({ color: 0x899185, roughness: .95 });
        const lawn = new THREE.Mesh(new THREE.CylinderGeometry(2.5, 2.5, 0.09, 72), ground);
        lawn.position.y = 0.2; lawn.receiveShadow = true; world.add(lawn);
        const orbit = new THREE.Mesh(new THREE.TorusGeometry(2.72, 0.012, 6, 100), gold);
        orbit.rotation.x = Math.PI / 2; orbit.position.y = 0.12; world.add(orbit);
        world.add(createCoverageHouse());
        box(0.5, 0.52, 0.36, navy, -1.6, 0.55, 0.25);
        box(0.32, 0.08, 0.02, cream, -1.6, 0.58, 0.44);
        box(0.08, 0.32, 0.02, cream, -1.6, 0.58, 0.45);
        const bagHandle = new THREE.Mesh(new THREE.TorusGeometry(0.14, 0.03, 8, 20, Math.PI), gold);
        bagHandle.position.set(-1.6, 0.83, 0.25); world.add(bagHandle);
        const clock = new THREE.Group();
        const clockFace = new THREE.Mesh(new THREE.CircleGeometry(0.26, 32), cream);
        const clockRim = new THREE.Mesh(new THREE.TorusGeometry(0.27, 0.025, 8, 32), gold);
        clock.add(clockFace, clockRim);
        box(0.12, 0.025, 0.018, navy, 0.05, 0, 0.02, clock);
        box(0.025, 0.13, 0.018, navy, 0, 0.055, 0.025, clock);
        clock.position.set(1.6, 0.95, -1.15); clock.rotation.y = 0.3; world.add(clock);
        const gapMarker = new THREE.Group();
        const markerFace = new THREE.Mesh(new THREE.CircleGeometry(0.19, 32), gold);
        const markerRim = new THREE.Mesh(new THREE.TorusGeometry(0.195, 0.016, 8, 32), windowLight);
        gapMarker.add(markerFace, markerRim);
        box(0.025, 0.13, 0.02, navy, 0, 0.035, 0.025, gapMarker);
        box(0.028, 0.028, 0.02, navy, 0, -0.085, 0.025, gapMarker);
        gapMarker.position.set(-1.85, 1.1, 1.45); gapMarker.rotation.y = 0.3; world.add(gapMarker);
        const panels: import("three").Group[] = [];
        for (let i = 0; i < 6; i++) {
          const panel = new THREE.Group();
          const angle = i * Math.PI / 3;
          const surface = new THREE.Mesh(new THREE.SphereGeometry(2.16, 28, 18, angle + 0.045, Math.PI / 3 - 0.09, 0.05, Math.PI / 2 - 0.05), new THREE.MeshPhysicalMaterial({ color: i === 0 ? 0xf0b963 : 0x8dd5f7, transparent: true, opacity: 0.12, roughness: 0.12, metalness: 0.15, clearcoat: 1, envMapIntensity: 1.4, side: THREE.DoubleSide, depthWrite: false }));
          panel.add(surface);
          const edgeMaterial = new THREE.LineBasicMaterial({ color: i === 0 ? 0xffd085 : 0xafe2ff, transparent: true, opacity: i === 0 ? 0.95 : 0.75 });
          for (const phi of [angle + 0.045, angle + Math.PI / 3 - 0.045]) {
            const points = Array.from({ length: 26 }, (_, j) => { const theta = 0.05 + (Math.PI / 2 - 0.05) * j / 25; return new THREE.Vector3(-2.16 * Math.cos(phi) * Math.sin(theta), 2.16 * Math.cos(theta), 2.16 * Math.sin(phi) * Math.sin(theta)); });
            panel.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), edgeMaterial));
          }
          const arc = Array.from({ length: 28 }, (_, j) => { const phi = angle + 0.045 + (Math.PI / 3 - 0.09) * j / 27; return new THREE.Vector3(-2.16 * Math.cos(phi), 0, 2.16 * Math.sin(phi)); });
          panel.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(arc), edgeMaterial));
          panel.userData.angle = angle + Math.PI / 6;
          world.add(panel); panels.push(panel);
        }
        function paper(title: string, index: number) {
          const group = new THREE.Group();
          box(0.85, 1.06, 0.055, cream, 0, 0, 0, group);
          const label = document.createElement("canvas"); label.width = 384; label.height = 480;
          const drawing = label.getContext("2d")!;
          drawing.fillStyle = "#fff2d9"; drawing.fillRect(0, 0, 384, 480);
          drawing.fillStyle = "#214675"; drawing.font = "600 23px sans-serif"; drawing.fillText("QUESTION FILE", 30, 48);
          drawing.fillStyle = "#a67d3e"; drawing.font = "600 19px sans-serif"; drawing.fillText(title, 30, 108);
          for (let line = 0; line < 5; line++) { drawing.fillStyle = line === index ? "#e7c78c" : "#d3d6d2"; drawing.fillRect(30, 160 + line * 32, line % 2 ? 240 : 300, 9); }
          drawing.fillStyle = "#526a82"; drawing.font = "17px sans-serif"; drawing.fillText("SOURCE PENDING", 30, 421);
          const texture = new THREE.CanvasTexture(label); texture.colorSpace = THREE.SRGBColorSpace;
          const ink = new THREE.Mesh(new THREE.PlaneGeometry(0.83, 1.04), new THREE.MeshBasicMaterial({ map: texture, toneMapped: false }));
          ink.position.z = 0.03; group.add(ink); world.add(group); return group;
        }
        const papers = ["ROOM LIMITS", "WAITING PERIODS", "COST SHARING"].map(paper);
        const beacons = new THREE.Group();
        for (const x of [-1.8, 1.8]) {
          const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 8), gold); beacon.position.set(x, 0.42, -1.2); beacons.add(beacon);
        }
        world.add(beacons);
        const moving = [...panels, ...papers];
        let settled = true;
        let transitionStart = 0;
        let startPositions = moving.map(object => object.position.clone());
        let startRotations = moving.map(object => object.rotation.clone());
        let targets = moving.map(object => object.position.clone());
        let targetRotations = moving.map(object => object.rotation.clone());
        const render = (resizeFrame = false) => { if (!cancelled && (visible || resizeFrame) && document.visibilityState !== "hidden") renderer!.render(scene, camera); };
        function easeStep(t: number) {
          const curve = (u: number, p1: number, p2: number) => 3 * (1 - u) ** 2 * u * p1 + 3 * (1 - u) * u ** 2 * p2 + u ** 3;
          let lo = 0, hi = 1;
          for (let i = 0; i < 10; i++) { const mid = (lo + hi) / 2; if (curve(mid, 0.22, 0.36) < t) lo = mid; else hi = mid; }
          return t >= 1 ? 1 : curve((lo + hi) / 2, 1, 1);
        }
        function stopLoop() { renderer!.setAnimationLoop(null); }
        function frame() {
          if (!visible || document.visibilityState === "hidden") { stopLoop(); return; }
          const t = preference.matches ? 1 : Math.min((performance.now() - transitionStart) / 900, 1);
          const amount = easeStep(t);
          moving.forEach((object, i) => {
            object.position.lerpVectors(startPositions[i], targets[i], amount);
            object.rotation.set(THREE.MathUtils.lerp(startRotations[i].x, targetRotations[i].x, amount), THREE.MathUtils.lerp(startRotations[i].y, targetRotations[i].y, amount), THREE.MathUtils.lerp(startRotations[i].z, targetRotations[i].z, amount));
          });
          render();
          if (t === 1) { settled = true; element!.dataset.motionState = "still"; stopLoop(); }
        }
        function setPhase(next: CoveragePhase, animate: boolean) {
          const mode = phaseIndex[next];
          startPositions = moving.map(object => object.position.clone()); startRotations = moving.map(object => object.rotation.clone());
          targets = panels.map((panel, i) => {
            const angle = panel.userData.angle as number;
            const distance = mode === 0 ? 0.28 + i % 3 * 0.12 : mode === 1 ? 0.72 : i === 0 ? 0.8 : 0;
            return new THREE.Vector3(-Math.cos(angle) * distance, 0.33 + (mode === 1 ? 0.16 : mode === 0 ? i % 2 * 0.16 : 0), Math.sin(angle) * distance);
          });
          targetRotations = panels.map((_, i) => new THREE.Euler(0, 0, mode === 0 ? (i % 2 ? -0.06 : 0.06) : 0));
          papers.forEach((_, i) => {
            targets.push(new THREE.Vector3((i - 1) * (mode === 0 ? 2.15 : 1.7), mode === 0 ? 1.5 + i % 2 * 0.5 : mode === 1 ? 1.2 : 0.82, mode === 0 ? -0.3 : mode === 1 ? 2.2 : 2.45));
            targetRotations.push(new THREE.Euler(mode === 2 ? -0.18 : 0, mode === 0 ? -0.35 : 0.3, mode === 0 ? (i - 1) * 0.3 : 0));
          });
          element!.dataset.scenePhase = next;
          if (!animate || preference.matches || !visible) {
            moving.forEach((object, i) => { object.position.copy(targets[i]); object.rotation.copy(targetRotations[i]); });
            settled = true; element!.dataset.motionState = "still"; stopLoop(); render(); return;
          }
          settled = false; transitionStart = performance.now(); element!.dataset.motionState = "transition"; renderer!.setAnimationLoop(frame);
        }
        function setRotation(angle: number) { world.rotation.y = angle; element!.dataset.sceneRotation = String(angle); render(); }
        const resize = () => {
          const width = element!.clientWidth, height = element!.clientHeight;
          if (!width || !height) return;
          renderer!.setSize(width, height, false); camera.aspect = width / height;
          const scale = Math.max(1, 1.22 / camera.aspect);
          camera.position.set(5.1 * scale, 4 * scale, 7.1 * scale); camera.lookAt(0, 0.95, 0); camera.updateProjectionMatrix(); render(true);
        };
        const resizeObserver = new ResizeObserver(resize); resizeObserver.observe(element!);
        visibilityUpdate = () => { if (!visible || document.visibilityState === "hidden") stopLoop(); else if (!settled) renderer!.setAnimationLoop(frame); else render(); };
        document.addEventListener("visibilitychange", visibilityUpdate);
        const motionChange = () => { if (preference.matches) setPhase(latest.current.phase, false); };
        preference.addEventListener("change", motionChange);
        const contextLost = (event: Event) => { event.preventDefault(); stopLoop(); setStatus("fallback"); };
        canvas.addEventListener("webglcontextlost", contextLost);
        let dragging = false, previousX = 0;
        const pointerDown = (event: PointerEvent) => { if (event.pointerType !== "mouse" || event.button !== 0 || preference.matches) return; dragging = true; previousX = event.clientX; canvas.setPointerCapture(event.pointerId); };
        const pointerMove = (event: PointerEvent) => { if (!dragging || preference.matches) return; setRotation(THREE.MathUtils.clamp(world.rotation.y + (event.clientX - previousX) * 0.007, -0.85, 0.85)); previousX = event.clientX; };
        const pointerUp = () => { if (dragging) latest.current.onRotationChange(world.rotation.y); dragging = false; };
        canvas.addEventListener("pointerdown", pointerDown); canvas.addEventListener("pointermove", pointerMove); canvas.addEventListener("pointerup", pointerUp); canvas.addEventListener("pointercancel", pointerUp);
        release = () => {
          stopLoop(); resizeObserver.disconnect(); preference.removeEventListener("change", motionChange);
          document.removeEventListener("visibilitychange", visibilityUpdate!);
          canvas.removeEventListener("webglcontextlost", contextLost); canvas.removeEventListener("pointerdown", pointerDown); canvas.removeEventListener("pointermove", pointerMove); canvas.removeEventListener("pointerup", pointerUp); canvas.removeEventListener("pointercancel", pointerUp);
          const geometries = new Set<import("three").BufferGeometry>(), materials = new Set<import("three").Material>(), textures = new Set<import("three").Texture>();
          scene.traverse((object) => { if (object instanceof THREE.Mesh || object instanceof THREE.Line) { geometries.add(object.geometry); for (const material of Array.isArray(object.material) ? object.material : [object.material]) { materials.add(material); for (const value of Object.values(material)) if (value instanceof THREE.Texture) textures.add(value); } } });
          environment.dispose(); textures.forEach(texture => texture.dispose()); geometries.forEach(geometry => geometry.dispose()); materials.forEach(material => material.dispose());
          renderer!.dispose(); renderer!.forceContextLoss(); canvas.remove();
        };
        runtime.current = { setPhase, setRotation, dispose: release };
        setRotation(latest.current.rotation); setPhase(latest.current.phase, false); resize();
        setStatus("ready");
      } catch {
        release?.();
        if (!release) { renderer?.dispose(); renderer?.forceContextLoss(); renderer?.domElement.remove(); }
        if (!cancelled) setStatus("fallback");
      }
    }
    return () => { cancelled = true; observer.disconnect(); runtime.current?.dispose(); runtime.current = null; };
  }, []);

  return <div ref={host} className={styles.scene} data-scene-status={status}>
    {status !== "ready" && <SceneBlueprint phase={phase} />}
    <span className={styles.sceneStatus}>{status === "ready" ? "INTERACTIVE 3D STUDY" : status === "fallback" ? "ILLUSTRATED STUDY · 3D UNAVAILABLE" : "ILLUSTRATED STUDY · 3D LOADS IN VIEW"}</span>
  </div>;
}
