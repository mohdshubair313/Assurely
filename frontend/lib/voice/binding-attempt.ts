import { ContractError, identifier, text } from "../api-contracts";
import { bindCaseCommand } from "./case-contracts";

/** Only opaque account/case/session IDs and a retry key; never report content. */
export function caseBindingAttempt(account: string, voice: string, caseId: string,
  storage: Pick<Storage, "getItem" | "setItem">, generate = () => crypto.randomUUID()) {
  const path = `assurely-voice-case:${encodeURIComponent(text(account, 128))}:${identifier(voice)}`;
  const expected = identifier(caseId), saved = storage.getItem(path);
  if (saved !== null) {
    const command = bindCaseCommand(JSON.parse(saved));
    if (command.case_id !== expected) throw new ContractError("A previous case selection needs confirmation. Recover this session's binding first.");
    return command;
  }
  const command = bindCaseCommand({ case_id: expected, idempotency_key: generate() });
  storage.setItem(path, JSON.stringify(command));
  return command;
}
