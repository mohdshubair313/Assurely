import { identifier, text } from "./api-contracts";

type AttemptStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
function binding(account: string, session: string) {
  return `assurely-human-review:${encodeURIComponent(text(account, 128))}:${identifier(session)}`;
}
/** Persist only an opaque operation key, before dispatch; uncertain writes reuse it. */
export function reviewAttempt(account: string, session: string, storage: AttemptStorage, generate = () => crypto.randomUUID()): string {
  const path = binding(account, session), saved = storage.getItem(path);
  if (saved !== null) return identifier(saved);
  const key = identifier(generate());
  storage.setItem(path, key);
  return key;
}
export function confirmReviewAttempt(account: string, session: string, storage: AttemptStorage) {
  storage.removeItem(binding(account, session));
}
