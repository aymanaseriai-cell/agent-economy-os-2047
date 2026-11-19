/**
 * One-time technical proof reuse gate. Original MIT-licensed code.
 * NOT identity, work provenance, buyer acceptance, payment or settlement.
 * Requires an independently trusted server context and atomic durable store.
 */
import {evaluateContract, canonical, digest} from "./core.mjs";

const HEX64=/^[0-9a-f]{64}$/;
const NONCE=/^[0-9a-f]{32,64}$/;
const AUDIENCE=/^[a-zA-Z0-9_.:-]{3,120}$/;
export const REPLAY_GUARD_VERSION="agent-economy.one-time-proof.v1";
export class ReplayGuardError extends Error {
  constructor(code) {super(code);this.name="ReplayGuardError";this.code=code;}
}
function check(test,code) {if(!test) throw new ReplayGuardError(code);}
const isRecord=x=>x!==null && typeof x==="object" && !Array.isArray(x);
function instant(value) {
  check(typeof value==="string" &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value),"invalid_challenge_time");
  const ms=Date.parse(value);
  check(Number.isFinite(ms) &&
    new Date(ms).toISOString().replace(".000Z","Z")===value.replace(".000Z","Z"),
    "invalid_challenge_time");
  return ms;
}
/**
 * Inputs are untrusted, but trusted options MUST come from authenticated server
 * configuration. consume_once(key, metadata) MUST be an atomic insert-if-absent
 * on a shared durable unique key. Never pass this option from a client.
 */
export async function evaluateOnce(input,trusted) {
  check(isRecord(input)&&isRecord(trusted),"invalid_input");
  const {expected_contract_id,expected_task_id,audience_id,challenge_nonce,
    issued_at,expires_at,consume_once}=trusted;
  const now=trusted.now_ms===undefined?Date.now():trusted.now_ms;
  check(Number.isSafeInteger(now)&&now>=0,"invalid_clock");
  check(typeof expected_contract_id==="string"&&HEX64.test(expected_contract_id),
    "invalid_expected_contract_id");
  check(typeof expected_task_id==="string"&&expected_task_id.length>0&&
    expected_task_id.length<=100,"invalid_expected_task_id");
  check(typeof audience_id==="string"&&AUDIENCE.test(audience_id),"invalid_audience");
  check(typeof challenge_nonce==="string"&&NONCE.test(challenge_nonce),
    "invalid_trusted_challenge");
  check(typeof consume_once==="function","durable_store_required");
  const issued=instant(issued_at),expires=instant(expires_at);
  check(expires>issued && expires-issued<=300_000 &&
    issued<=now+30_000 && expires>now,"stale_or_invalid_challenge");
  check(isRecord(input.contract)&&isRecord(input.contract.task)&&
    input.contract.task.id===expected_task_id &&
    input.contract_id===expected_contract_id,"untrusted_contract_binding");

  // Re-evaluate the bytes: untrusted client-supplied pass flags are ignored.
  const result=await evaluateContract(input);
  check(result.contract_id===expected_contract_id,"untrusted_contract_binding");
  if(result.status!=="local_checks_passed")
    return {schema:REPLAY_GUARD_VERSION,accepted:false,reason:"local_checks_failed"};
  if(result.has_unverified_self_reports)
    return {schema:REPLAY_GUARD_VERSION,accepted:false,reason:"unverified_self_reports"};

  // Replays with changed nonce/proof content still collide on the SAME contract.
  const replay_key=await digest(canonical({
    domain:REPLAY_GUARD_VERSION,contract_id:expected_contract_id
  }));
  const binding_id=await digest(canonical({
    domain:REPLAY_GUARD_VERSION,contract_id:expected_contract_id,
    task_id:expected_task_id,audience_id,challenge_nonce,issued_at,expires_at,
    proof_id:result.proof_id
  }));
  let consumed;
  try {
    consumed=await consume_once(replay_key,{
      contract_id:expected_contract_id,proof_id:result.proof_id,
      binding_id,task_id:expected_task_id,audience_id,expires_at
    });
  } catch {
    throw new ReplayGuardError("replay_store_unavailable");
  }
  check(consumed===true||consumed===false,"invalid_store_response");
  if(!consumed)
    return {schema:REPLAY_GUARD_VERSION,accepted:false,
      reason:"duplicate_contract_proof",replay_key};
  return {schema:REPLAY_GUARD_VERSION,accepted:true,
    status:"one_time_local_technical_check",contract_id:expected_contract_id,
    proof_id:result.proof_id,binding_id,replay_key,expires_at,
    evidence_scope:"caller_supplied_bytes_only",
    buyer_acceptance_verified:false,signer_identity_verified:false,
    execution_provenance_verified:false,payment_verified:false,
    settlement_verified:false};
}
