type Events = Pick<EventTarget, "addEventListener" | "removeEventListener">;
export interface CaptionLifecycleSurface {
  documentEvents: Events; windowEvents: Events;
  visible: () => boolean; focused: () => boolean; online: () => boolean;
}
/** Host events can only hide or request fresh authorization; never restore cached text. */
export function attachCaptionLifecycle(display: { start: () => void; stop: () => void }, surface: CaptionLifecycleSurface) {
  const sync = () => {
    if (surface.visible() && surface.focused() && surface.online()) display.start();
    else display.stop();
  };
  const hide = () => display.stop();
  surface.documentEvents.addEventListener("visibilitychange", sync);
  for (const event of ["online", "offline", "focus"]) surface.windowEvents.addEventListener(event, sync);
  for (const event of ["pagehide", "blur"]) surface.windowEvents.addEventListener(event, hide);
  sync();
  return () => {
    surface.documentEvents.removeEventListener("visibilitychange", sync);
    for (const event of ["online", "offline", "focus"]) surface.windowEvents.removeEventListener(event, sync);
    for (const event of ["pagehide", "blur"]) surface.windowEvents.removeEventListener(event, hide);
    display.stop();
  };
}
