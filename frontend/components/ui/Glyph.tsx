import type { CSSProperties } from "react";
const paths: Record<string, string> = {
  shield: "M12 3 4 6v5c0 5 3 8 8 10 5-2 8-5 8-10V6l-8-3Zm-4 9 3 3 5-6",
  file: "M6 3h8l4 4v14H6V3Zm8 0v5h4M9 12h6M9 16h6",
  search: "M16 16 22 22M19 10a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  chat: "M4 4h16v13H9l-5 4V4Zm4 5h8M8 12h5",
  compare: "M4 6h16M4 18h16M8 3 4 6l4 3m8 6 4 3-4 3M8 11v4m8-6v4",
  folder: "M3 7h7l2-3h9v16H3V7Z",
  lock: "M5 10h14v11H5V10Zm3 0V7a4 4 0 0 1 8 0v3m-4 4v3",
  check: "m5 12 4 4L19 6",
  clock: "M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  arrow: "M4 12h16m-6-6 6 6-6 6",
  moon: "M20 14A9 9 0 0 1 10 4a9 9 0 1 0 10 10Z",
  heart: "M12 20 3 11C-2 3 9 0 12 7c3-7 14-4 9 4l-9 9Z",
};
export default function Glyph({ name = "shield", size = 22, style }: { name?: string; size?: number; style?: CSSProperties }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}><path d={paths[name] || paths.shield} /></svg>;
}
