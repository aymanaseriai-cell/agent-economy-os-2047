/**
 * Agent Economy OS 2047 - challenge-bound, single-use proof reference verification.
 * MIT; original implementation. No network, payment, storage, or secret-key operations.
 *
 * A caller must independently pin the signer's public key and implement an
 * ATOMIC durable reserveReplayKey operation (unique-key insert).
 */
import {evaluateContract, canonical, digest} from './core.mjs';

export const CHALLENGE_SCHEMA = 'agent-economy.challenge-bound-evidence.v1';
export const SIGNING_DOMAIN = 'AgentEconomy2047:challenge-bound-evidence:v1\n';
const text = new TextEncoder();
const hex64 = /^[a-f0-9]{64}$/;
const token = /^[A-Za-z0-9_-]{22,128}$/;
const context = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$/;
const timestamp = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;

export class ChallengeGuardError extends Error {
  constructor(code) { super(code); this.name = 'ChallengeGuardError'; this.code = code; }
}
const fail = code => {throw new ChallengeGuardError(code);};
const insist = (yes, code) => {if (!yes) fail(code);};
const exactKeys = (obj, keys) => !!obj && typeof obj === 'object' && !Array.isArray(obj) &&
  Object.keys(obj).length === keys.length && keys.every(k => Object.hasOwn(obj,k));

function fromBase64url(value, bytes, code) {
  insist(typeof value === 'string' && /^[A-Za-z0-9_-]+$/.test(value) && value.length % 4 !== 1, code);
  let data;
  try {
    const bin = atob(value.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-value.length%4)%4));
    data = Uint8Array.from(bin,c=>c.charCodeAt(0));
  } catch {fail(code);}
  insist(data.length === bytes, code);
  return data;
}
function parseUTC(value) {
  insist(typeof value === 'string' && timestamp.test(value), 'invalid_challenge_time');
  const ms = Date.parse(value);
  insist(Number.isFinite(ms) && new Date(ms).toISOString().replace('.000Z','Z') === value, 'invalid_challenge_time');
  return ms;
}
export function normalizeEnvelope(raw) {
  const keys = ['schema','audience','task_id','contract_id','proof_id','nonce','issued_at','expires_at'];
  insist(exactKeys(raw,keys), 'invalid_envelope');
  insist(raw.schema === CHALLENGE_SCHEMA, 'invalid_challenge_schema');
  insist(typeof raw.audience === 'string' && typeof raw.task_id === 'string' &&
    context.test(raw.audience) && context.test(raw.task_id), 'invalid_challenge_context');
  insist(hex64.test(raw.contract_id) && hex64.test(raw.proof_id), 'invalid_proof_reference');
  insist(typeof raw.nonce === 'string' && token.test(raw.nonce), 'invalid_challenge_nonce');
  const start = parseUTC(raw.issued_at), end = parseUTC(raw.expires_at);
  insist(end > start && end-start <= 600000, 'invalid_challenge_window');
  return {schema:raw.schema,audience:raw.audience,task_id:raw.task_id,
    contract_id:raw.contract_id,proof_id:raw.proof_id,nonce:raw.nonce,
    issued_at:raw.issued_at,expires_at:raw.expires_at};
}
export function signingMessage(raw) {
  return SIGNING_DOMAIN + canonical(normalizeEnvelope(raw));
}
/**
 * Re-evaluates submitted bytes and verifies signed, externally pinned context.
 * reserveReplayKey(key, expiresAt) MUST resolve true only on the FIRST claim.
 */
export async function verifyChallengeBoundWork({
  contract,contract_id,submission,envelope,signature_b64url,
  trusted_public_key_b64url,expected_audience,expected_task_id,expected_nonce,
  reserveReplayKey,now_ms=Date.now()
}) {
  insist(typeof reserveReplayKey === 'function', 'atomic_replay_ledger_required');
  insist(typeof expected_audience === 'string' && typeof expected_task_id === 'string' &&
    typeof expected_nonce === 'string', 'trusted_challenge_context_required');
  insist(Number.isSafeInteger(now_ms) && now_ms >= 0, 'invalid_trusted_clock');
  const data = normalizeEnvelope(envelope);
  insist(data.audience === expected_audience && data.task_id === expected_task_id &&
    data.nonce === expected_nonce, 'challenge_context_mismatch');
  const start = parseUTC(data.issued_at), end = parseUTC(data.expires_at);
  insist(start <= now_ms && now_ms < end, 'challenge_not_current');
  insist(data.contract_id === contract_id, 'challenge_contract_mismatch');
  const evaluated = await evaluateContract({contract,contract_id,submission});
  insist(evaluated.status === 'local_checks_passed', 'local_evidence_checks_failed');
  insist(evaluated.has_unverified_self_reports === false, 'self_report_not_independent_evidence');
  insist(evaluated.proof_id === data.proof_id, 'challenge_proof_mismatch');

  const key = fromBase64url(trusted_public_key_b64url,32,'invalid_pinned_public_key');
  const signature = fromBase64url(signature_b64url,64,'invalid_challenge_signature');
  let valid = false;
  try {
    const publicKey = await crypto.subtle.importKey('raw',key,{name:'Ed25519'},false,['verify']);
    valid = await crypto.subtle.verify('Ed25519',publicKey,signature,text.encode(signingMessage(data)));
  } catch {fail('signature_verification_unavailable');}
  insist(valid, 'invalid_challenge_signature');

  // Exclude nonce so re-signing the same proof cannot bypass the replay ledger.
  const replay_key = await digest(canonical({schema:CHALLENGE_SCHEMA,
    audience:data.audience,task_id:data.task_id,contract_id:data.contract_id,proof_id:data.proof_id}));
  let reserved = false;
  try {reserved = await reserveReplayKey(replay_key,data.expires_at) === true;}
  catch {fail('replay_store_unavailable');}
  insist(reserved, 'replay_detected_or_store_unavailable');
  return {
    schema: CHALLENGE_SCHEMA,status:'single_use_proof_reference_accepted',
    proof_id:data.proof_id,contract_id:data.contract_id,replay_key,
    signature_valid:true,technical_checks_passed:true,
    signer_identity_verified:false,buyer_acceptance_verified:false,
    execution_independently_verified:false,payment_verified:false,
    onchain_settlement_verified:false,
    limitations:['The verifier must independently pin the signer key, nonce, and context.',
      'Replay guarantees require a shared durable atomic uniqueness ledger.',
      'A signature and local byte checks do not prove buyer acceptance, execution, or payment.']
  };
}
