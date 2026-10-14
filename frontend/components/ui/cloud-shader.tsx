"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export type CloudShaderProps = {
  className?: string;
  children?: ReactNode;
  speed?: number;
  count?: number;
  cloudColor?: string;
  skyTopColor?: string;
  skyBottomColor?: string;
  /** Composite clouds over existing artwork instead of drawing an opaque sky. */
  transparent?: boolean;
  paused?: boolean;
};

const VERT = `
attribute vec2 a_pos;
varying vec2 v_uv;
void main() { v_uv = a_pos * 0.5 + 0.5; gl_Position = vec4(a_pos, 0.0, 1.0); }
`;

// Adapted from the Aceternity Cloud Shader supplied by the user.
// https://ui.aceternity.com/components/cloud-shader
// Billow noise + directional density sampling provide apparent volume.
const FRAG = `
precision highp float;
varying vec2 v_uv;
uniform vec2 u_res;
uniform float u_time, u_count, u_overlay;
uniform vec3 u_cloud, u_skyTop, u_skyBottom;
const mat2 R = mat2(0.80, 0.60, -0.60, 0.80);
float hash(vec2 p) { return fract(sin(dot(p, vec2(41.31, 289.17))) * 26737.367); }
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1., 0.)), f.x),
    mix(hash(i + vec2(0., 1.)), hash(i + vec2(1., 1.)), f.x), f.y);
}
float fbm(vec2 p) {
  float sum = 0., amp = .5;
  for (int i = 0; i < 4; i++) { sum += amp * vnoise(p); p = R * p * 2.03 + 19.19; amp *= .5; }
  return sum;
}
float billow(vec2 p) {
  float sum = 0., amp = .5;
  for (int i = 0; i < 5; i++) {
    sum += amp * (1. - abs(2. * vnoise(p) - 1.)); p = R * p * 2.11 + 13.37; amp *= .5;
  }
  return sum;
}
float cloudDensity(vec2 p, vec2 c, vec2 r, float seed, float t) {
  vec2 q = p - c;
  float ry = q.y > 0. ? r.y : r.y * .42;
  float env = 1. - length(vec2(q.x / r.x, q.y / ry));
  if (env < -.35) return 0.;
  vec2 dp = q * (2.4 / r.x) + seed;
  dp += .6 * vec2(fbm(dp * 1.4 + t * .04), fbm(dp * 1.4 + 7.7 - t * .03));
  return env + (billow(dp * 1.6) - .62) * .62;
}
vec4 shadeCloud(vec4 color, vec3 sky, vec2 p, vec2 c, vec2 r, float seed, float t, float dist) {
  float d = cloudDensity(p, c, r, seed, t);
  if (d < .02) return color;
  float dUp = cloudDensity(p + vec2(0., r.y * .55), c, r, seed, t);
  float occl = clamp((dUp - d) * 1.1 + d * .55, 0., 1.);
  vec3 cloudCol = mix(u_cloud * 1.04, mix(u_cloud * .60, sky, .38), occl * .85);
  float alpha = smoothstep(.02, .38, d);
  float rim = smoothstep(.02, .14, d) * (1. - smoothstep(.14, .40, d));
  cloudCol += rim * .10;
  cloudCol = mix(cloudCol, sky, dist * .35);
  alpha *= mix(1., .8, dist);
  // Accumulate premultiplied color, then unpremultiply once for the canvas.
  return vec4(cloudCol * alpha + color.rgb * (1. - alpha), alpha + color.a * (1. - alpha));
}
vec4 cloudPass(vec4 color, vec3 sky, vec2 p, float aspect, float t,
              float spd, float phase, float y, vec2 r, float seed, float dist) {
  float cx = mix(-r.x - .25, aspect + r.x + .25, fract(t * spd + phase));
  float cy = y + sin(t * .05 + phase * 6.2831) * .012;
  return shadeCloud(color, sky, p, vec2(cx, cy), r, seed, t, dist);
}
void main() {
  float aspect = u_res.x / u_res.y, t = u_time;
  vec2 p = vec2(v_uv.x * aspect, v_uv.y);
  vec3 sky = mix(u_skyBottom, u_skyTop, v_uv.y);
  vec4 color = vec4(0.);
  if (u_overlay < .5) {
    vec3 background = mix(sky, u_skyBottom * 1.06, (1. - smoothstep(0., .35, v_uv.y)) * .5);
    float sunDist = length(p - vec2(aspect * .78, .92));
    background += vec3(1., .95, .82) * exp(-sunDist * sunDist * 5.) * .28;
    float band = smoothstep(.55, .8, v_uv.y) * (1. - smoothstep(.9, 1., v_uv.y));
    float wisp = smoothstep(.52, .78, fbm(vec2(p.x * 1.6 - t * .006, p.y * 12.))) * band;
    color = vec4(mix(background, u_cloud * .98, wisp * .35), 1.);
  }
  if (u_count > 5.5) color = cloudPass(color, sky, p, aspect, t, .006, .10, .84, vec2(.20, .10), 43.7, 1.);
  if (u_count > 4.5 && u_overlay < .5) color = cloudPass(color, sky, p, aspect, t, .008, .62, .73, vec2(.24, .12), 71.3, .85);
  if (u_count > 3.5) color = cloudPass(color, sky, p, aspect, t, .011, .28, mix(.60, .46, u_overlay), vec2(.34, .14), 17.3, .55);
  if (u_count > 2.5) color = cloudPass(color, sky, p, aspect, t, .013, .80, mix(.47, .40, u_overlay), vec2(.30, .13), 29.9, .45);
  if (u_count > 1.5) color = cloudPass(color, sky, p, aspect, t, .016, mix(.05, .20, u_overlay), mix(.35, .30, u_overlay), vec2(.46, .18), 91.1, .15);
  color = cloudPass(color, sky, p, aspect, t, .020, mix(.48, .75, u_overlay), mix(.20, .23, u_overlay), vec2(.56, .21), 57.2, 0.);
  if (u_count > 4.5 && u_overlay > .5) {
    // A shallow ribbon crosses the upper steps just beneath the figure's feet.
    color = cloudPass(color, sky, p, aspect, t, .014, .50, .405, vec2(.40, .085), 71.3, .30);
  }
  float alpha = color.a;
  if (u_overlay > .5) {
    // Protect the station and figure, but allow mist to cross the steps below.
    float station = smoothstep(.455, .495, v_uv.y) * (1. - smoothstep(.65, .72, v_uv.y)) * smoothstep(.20, .28, v_uv.x);
    float figure = 1. - smoothstep(.65, 1.25, length((v_uv - vec2(.498, .512)) / vec2(.016, .032)));
    float lowerSteps = (1. - smoothstep(.025, .065, abs(v_uv.x - .50))) * (1. - smoothstep(.24, .34, v_uv.y));
    alpha *= (1. - station * .98) * (1. - figure) * (1. - lowerSteps * .55);
    alpha *= (1. - smoothstep(.58, .72, v_uv.y)) * .68;
  }
  gl_FragColor = vec4(color.rgb / max(color.a, .0001), alpha);
}
`;

function parseColor(color: string): [number, number, number] {
  const value = color.trim();
  if (/^#[\da-f]{3}$/i.test(value)) return [...value.slice(1)].map(c => parseInt(c + c, 16) / 255) as [number, number, number];
  if (/^#[\da-f]{6}$/i.test(value)) return [1, 3, 5].map(i => parseInt(value.slice(i, i + 2), 16) / 255) as [number, number, number];
  const rgb = value.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i);
  return rgb ? rgb.slice(1, 4).map(c => Math.min(1, Math.max(0, Number(c) / 255))) as [number, number, number] : [.95, .95, .95];
}

export function CloudShader({ className, children, speed = 1, count = 6, cloudColor = "#fbf8f2", skyTopColor = "#3876ba", skyBottomColor = "#8cbfe8", transparent = false, paused = false }: CloudShaderProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const params = useRef({ speed, count, cloudColor, skyTopColor, skyBottomColor, transparent, paused });
  const refresh = useRef<(() => void) | null>(null);

  useEffect(() => {
    params.current = { speed, count, cloudColor, skyTopColor, skyBottomColor, transparent, paused };
    refresh.current?.();
  }, [speed, count, cloudColor, skyTopColor, skyBottomColor, transparent, paused]);

  useEffect(() => {
    const canvas = canvasRef.current, host = hostRef.current;
    if (!canvas || !host) return;
    const gl = canvas.getContext("webgl", { alpha: true, antialias: false, premultipliedAlpha: false, preserveDrawingBuffer: true, powerPreference: "low-power" });
    if (!gl) { host.dataset.cloudStatus = "fallback"; return; }
    const shaders: WebGLShader[] = [];
    const compile = (type: number, source: string) => {
      const shader = gl.createShader(type);
      if (!shader) return null;
      shaders.push(shader);
      gl.shaderSource(shader, source); gl.compileShader(shader);
      return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
    };
    const vert = compile(gl.VERTEX_SHADER, VERT), frag = compile(gl.FRAGMENT_SHADER, FRAG);
    const program = gl.createProgram(), buffer = gl.createBuffer();
    const dispose = () => { gl.deleteBuffer(buffer); gl.deleteProgram(program); shaders.forEach(s => gl.deleteShader(s)); };
    if (!vert || !frag || !program || !buffer) { dispose(); host.dataset.cloudStatus = "fallback"; return; }
    gl.attachShader(program, vert); gl.attachShader(program, frag); gl.bindAttribLocation(program, 0, "a_pos"); gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) { dispose(); host.dataset.cloudStatus = "fallback"; return; }
    gl.useProgram(program);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    const loc = Object.fromEntries(["res", "time", "count", "cloud", "skyTop", "skyBottom", "overlay"].map(key => [key, gl.getUniformLocation(program, `u_${key}`)]));
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0, visible = false, lost = false, disposed = false, elapsed = 0, last = 0, lastDraw = 0;
    let cloud = parseColor(params.current.cloudColor), skyTop = parseColor(params.current.skyTopColor), skyBottom = parseColor(params.current.skyBottomColor);
    const finite = (n: number, fallback: number) => Number.isFinite(n) ? n : fallback;
    const canPlay = () => visible && !document.hidden && !motion.matches && !params.current.paused && params.current.speed > 0 && !lost && !disposed;
    const render = () => {
      if (lost || disposed) return;
      gl.uniform2f(loc.res, canvas.width, canvas.height);
      gl.uniform1f(loc.time, elapsed);
      gl.uniform1f(loc.count, Math.min(6, Math.max(1, finite(params.current.count, 6))));
      gl.uniform1f(loc.overlay, params.current.transparent ? 1 : 0);
      gl.uniform3fv(loc.cloud, cloud); gl.uniform3fv(loc.skyTop, skyTop); gl.uniform3fv(loc.skyBottom, skyBottom);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };
    const draw = (now: number) => {
      frame = 0;
      if (!canPlay()) return;
      if (last) elapsed += Math.min((now - last) / 1000, .1) * Math.max(0, finite(params.current.speed, 1));
      last = now;
      // A slow atmosphere needs only 30 draws per second, at a capped resolution.
      if (now - lastDraw >= 1000 / 30) { render(); lastDraw = now; }
      frame = requestAnimationFrame(draw);
    };
    const sync = () => {
      cancelAnimationFrame(frame); frame = 0; last = 0;
      const playing = canPlay(); host.dataset.cloudPlaying = String(playing);
      if (visible && !document.hidden) render();
      if (playing) frame = requestAnimationFrame(draw);
    };
    const resize = () => {
      const width = canvas.clientWidth, height = canvas.clientHeight;
      const ratio = Math.min(devicePixelRatio || 1, 1.25, 1280 / Math.max(width, 1), 720 / Math.max(height, 1));
      canvas.width = Math.max(1, Math.round(width * ratio)); canvas.height = Math.max(1, Math.round(height * ratio));
      gl.viewport(0, 0, canvas.width, canvas.height);
      if (visible && !document.hidden) render();
    };
    const resizeObserver = new ResizeObserver(resize);
    const intersection = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync(); });
    const contextLost = (event: Event) => { event.preventDefault(); lost = true; sync(); host.dataset.cloudStatus = "fallback"; };
    // Keep the source artwork as the fallback; a subsequent mount can retry WebGL.
    canvas.addEventListener("webglcontextlost", contextLost);
    document.addEventListener("visibilitychange", sync); motion.addEventListener("change", sync);
    resizeObserver.observe(canvas); intersection.observe(canvas); resize();
    refresh.current = () => {
      cloud = parseColor(params.current.cloudColor); skyTop = parseColor(params.current.skyTopColor); skyBottom = parseColor(params.current.skyBottomColor); sync();
    };
    host.dataset.cloudStatus = "ready";
    return () => {
      disposed = true; cancelAnimationFrame(frame); refresh.current = null;
      resizeObserver.disconnect(); intersection.disconnect();
      canvas.removeEventListener("webglcontextlost", contextLost);
      document.removeEventListener("visibilitychange", sync); motion.removeEventListener("change", sync); dispose();
    };
  }, []);

  return <div ref={hostRef} data-cloud-shader data-cloud-status="loading" data-cloud-playing="false" className={cn("relative h-full min-h-80 w-full overflow-hidden", className)}>
    <canvas ref={canvasRef} aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full" />
    {children ? <div className="relative z-10 flex h-full w-full items-center justify-center">{children}</div> : null}
  </div>;
}
