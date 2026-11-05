"use client";
import { useEffect, useRef, useState } from "react";
export interface CaseTask { signal: AbortSignal; commit: (update: () => void) => void }
/** Scope changes/unmount cancel reads and suppress stale writes; cancellation is not server rollback. */
export function useCaseTask(scope: string) {
  const latest = useRef(scope);
  const active = useRef<{ id: symbol; scope: string; controller: AbortController } | null>(null);
  const [pending, setPending] = useState<{ id: symbol; scope: string } | null>(null);
  const [notice, setNotice] = useState<{ scope: string; text: string; failed: boolean } | null>(null);
  useEffect(() => { latest.current = scope; return () => {
    if (active.current?.scope === scope) active.current.controller.abort();
  }; }, [scope]);
  async function run(action: (task: CaseTask) => Promise<void>) {
    if (active.current?.scope === scope && !active.current.controller.signal.aborted) return;
    active.current?.controller.abort();
    const operation = { id: Symbol(), scope, controller: new AbortController() };
    active.current = operation; latest.current = scope;
    const current = () => active.current?.id === operation.id && latest.current === scope && !operation.controller.signal.aborted;
    setPending(operation); setNotice(null);
    try { await action({ signal: operation.controller.signal, commit: update => { if (current()) update(); } }); }
    catch (error) { if (current()) setNotice({ scope, failed: true, text: error instanceof Error ? error.message : "The request could not be confirmed." }); }
    finally { if (active.current?.id === operation.id) { active.current = null; setPending(null); } }
  }
  return { run, busy: pending?.scope === scope, notice: notice?.scope === scope ? notice : null,
    notify: (text: string) => setNotice({ scope, text, failed: false }) };
}
