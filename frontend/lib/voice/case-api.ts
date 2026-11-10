import { api } from "../api-client";
import { ContractError, identifier } from "../api-contracts";
import { bindCaseCommand, caseBinding, captionPacket, type VoiceCaseBinding } from "./case-contracts";

export function readCaseBinding(voice: string, signal?: AbortSignal) {
  const expected = identifier(voice);
  return api(`voice/development/sessions/${expected}/case-binding`, value => {
    const selected = caseBinding(value);
    if (selected.voice_session_id !== expected) throw new ContractError();
    return selected;
  }, undefined, { signal });
}
export function bindVoiceCase(voice: string, caseId: string, key: string, signal?: AbortSignal) {
  const expected = identifier(voice), command = bindCaseCommand({ case_id: caseId, idempotency_key: key });
  return api(`voice/development/sessions/${expected}/case-binding`, value => {
    const selected = caseBinding(value);
    if (selected.voice_session_id !== expected || selected.case_id !== command.case_id) throw new ContractError();
    return selected;
  }, command, { signal });
}
export function readReviewedCaptions(binding: VoiceCaseBinding, signal?: AbortSignal) {
  return api(`voice/development/sessions/${identifier(binding.voice_session_id)}/captions`, value => captionPacket(value, binding), undefined, { signal });
}
