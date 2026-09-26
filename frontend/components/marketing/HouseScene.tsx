"use client";

import Image from "next/image";
import { useRef, useState, type PointerEvent } from "react";

/** A 3D-style illustration with small, reversible pointer parallax. */
export default function HouseScene() {
  const scene = useRef<HTMLDivElement>(null);
  const [paused, setPaused] = useState(false);

  function reset() {
    for (const key of ["--scene-x", "--scene-y", "--scene-rx", "--scene-ry"]) {
      scene.current?.style.removeProperty(key);
    }
  }

  function move(event: PointerEvent<HTMLDivElement>) {
    if (paused || event.pointerType !== "mouse" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width - 0.5;
    const y = (event.clientY - bounds.top) / bounds.height - 0.5;
    scene.current?.style.setProperty("--scene-x", `${x * 14}px`);
    scene.current?.style.setProperty("--scene-y", `${y * 10}px`);
    scene.current?.style.setProperty("--scene-rx", `${-y * 7}deg`);
    scene.current?.style.setProperty("--scene-ry", `${x * 9}deg`);
  }

  return <div className={`house-scene${paused ? " motion-paused" : ""}`} ref={scene} onPointerMove={move} onPointerLeave={reset}>
    <div className="house-halo" aria-hidden="true" />
    <div className="house-parallax"><div className="house-float">
      <Image src="/images/house-clouds-3d.png" alt="A warmly lit stone cottage with blue slate roofs, nestled among soft three-dimensional clouds." width={1448} height={1086} priority sizes="(max-width: 720px) 100vw, 55vw" draggable={false} className="house-illustration" />
    </div></div>
    <button className="scene-motion" onClick={() => { reset(); setPaused(!paused); }} aria-pressed={paused} aria-label={paused ? "Resume house animation" : "Pause house animation"} title={paused ? "Resume motion" : "Pause motion"}>
      {paused ? <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7 4 9 6-9 6Z" /></svg> : <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 4v12M13 4v12" /></svg>}
    </button>
  </div>;
}
