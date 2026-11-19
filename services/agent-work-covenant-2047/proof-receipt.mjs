/**
 * Proof-bound technical receipt v1. No network, payments, key custody, or storage.
 * Signatures bind an independently pinned task+contract+proof to an audience,
 * short lifetime, and random challenge. Replay protection REQUIRES a durable,
 * atomic put-if-absent callback supplied by the verifier; fail closed otherwise.
 * Copyright 2026 Agent Economy OS 2047 contributors. MIT.
 */
export const RECEIPT_DOMAIN = "agent-economy.proof-bound-receipt.v1";
const enc = new TextEncoder();
const hex64 = /^[0-9a-f]{64}$/;
const taskPattern = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$/;
const utcPattern = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/;
const isRecord = v => v !== null && typeof v === "object" && !Array.isArray(v);
export class ProofReceiptError extends Error {
  constructor(code) {super(code); this.code=code; this.name="ProofReceiptError";}
}
const requireThat = (ok,code) => {if(!ok) throw new ProofReceiptError(code);};
function b64urlBytes(value,lower,upper) {
  requireThat(typeof value === "string" && /^[A-Za-z0-9_-]+$/.test(value) &&
    value.length <= 120 && value.length % 4 !== 1,"invalid_base64url");
  let decoded;
  try { decoded=atob(value.replace(/-/g,"+").replace(/_/g,"/")+"=".repeat((4-value.length%4)%4)); }
  catch {throw new ProofReceiptError("invalid_base64url");}
  const bytes=Uint8Array.from(decoded,c=>c.charCodeAt(0));
  requireThat(bytes.length>=lower && bytes.length<=upper,"invalid_binary_length");
  // Prevent alternative encodings from identifying the same nonce or signature.
  const canonical=btoa(decoded).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/g,"");
  requireThat(canonical===value,"noncanonical_base64url");
  return bytes;
}
function utc(value) {
  requireThat(typeof value==="string" && utcPattern.test(value),"invalid_timestamp");
  const ms=Date.parse(value);
  requireThat(Number.isFinite(ms) && new Date(ms).toISOString().replace(".000Z","Z")===value,"invalid_timestamp");
  return ms;
}
function audience(input) {
  requireThat(typeof input==="string" && input.length<=240 && input.trim()===input,"invalid_audience");
  let u;
  try {u=new URL(input);} catch {throw new ProofReceiptError("invalid_audience");}
  requireThat(u.protocol==="https:" && !!u.hostname && !u.username && !u.password &&
    !u.search && !u.hash && (u.pathname==="/" || u.pathname==="") && !u.port &&
    input===u.origin,"invalid_audience");
  return input;
}
function normalize(receipt) {
  requireThat(isRecord(receipt),"invalid_receipt");
  const keys=["domain","contract_id","proof_id","task_id","audience","nonce","issued_at","expires_at"];
  requireThat(Object.keys(receipt).length===keys.length && keys.every(k=>Object.hasOwn(receipt,k)),"invalid_receipt_fields");
  requireThat(receipt.domain===RECEIPT_DOMAIN,"invalid_receipt_domain");
  requireThat(typeof receipt.contract_id==="string" && hex64.test(receipt.contract_id),"invalid_contract_id");
  requireThat(typeof receipt.proof_id==="string" && hex64.test(receipt.proof_id),"invalid_proof_id");
  requireThat(typeof receipt.task_id==="string" && taskPattern.test(receipt.task_id),"invalid_task_id");
  audience(receipt.audience);
  b64urlBytes(receipt.nonce,16,32);
  const issued=utc(receipt.issued_at),expires=utc(receipt.expires_at);
  requireThat(expires>issued && expires-issued<=15*60*1000,"invalid_receipt_lifetime");
  return Object.fromEntries(keys.map(k=>[k,receipt[k]]));
}
async function digest(data) {
  const hash=await crypto.subtle.digest("SHA-256",typeof data==="string"?enc.encode(data):data);
  return Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,"0")).join("");
}
// Fixed canonical field order is part of protocol v1 and MUST remain stable.
function canonical(receipt) {return JSON.stringify(normalize(receipt));}
export async function prepareProofReceipt(input) {
  const receipt=normalize({domain:RECEIPT_DOMAIN,...input});
  const message=canonical(receipt);
  return {
    domain:RECEIPT_DOMAIN,receipt,message,receipt_id:await digest(message),
    signature_algorithm:"Ed25519",
    warning:"Technical statement about a pinned proof checksum only; does not prove work execution, signer identity, buyer acceptance or payment."
  };
}
/**
 * Expected values MUST come from a trusted source independent of the receipt.
 * claimNonce({key,expires_at,receipt_id}) MUST be a durable atomic insert-if-absent
 * shared across verification workers; return true only on successful first insert.
 * Never use a process-local Set in production.
 */
export async function verifyProofReceipt({receipt,public_key_b64url,signature_b64url}, {
  expected_contract_id,expected_proof_id,expected_task_id,expected_audience,
  trusted_key_fingerprints,claimNonce,now=new Date()
}={}) {
  const normalized=normalize(receipt);
  requireThat(typeof expected_contract_id==="string" && hex64.test(expected_contract_id) &&
    typeof expected_proof_id==="string" && hex64.test(expected_proof_id) &&
    typeof expected_task_id==="string" && taskPattern.test(expected_task_id),"missing_trusted_binding");
  audience(expected_audience);
  requireThat(Array.isArray(trusted_key_fingerprints) &&
    trusted_key_fingerprints.every(v=>typeof v==="string" && hex64.test(v)),"invalid_trusted_keys");
  const publicBytes=b64urlBytes(public_key_b64url,32,32);
  const signatureBytes=b64urlBytes(signature_b64url,64,64);
  const message=canonical(normalized);
  const receipt_id=await digest(message);
  const public_key_fingerprint=await digest(publicBytes);
  const binding_matches=normalized.contract_id===expected_contract_id &&
    normalized.proof_id===expected_proof_id && normalized.task_id===expected_task_id &&
    normalized.audience===expected_audience;
  const timestamp=now instanceof Date?now.getTime():NaN;
  requireThat(Number.isFinite(timestamp),"invalid_clock");
  const time_valid=utc(normalized.issued_at)<=timestamp && timestamp<=utc(normalized.expires_at);
  let signature_valid=false;
  try {
    const key=await crypto.subtle.importKey("raw",publicBytes,{name:"Ed25519"},false,["verify"]);
    signature_valid=await crypto.subtle.verify({name:"Ed25519"},key,signatureBytes,enc.encode(message));
  } catch {signature_valid=false;}
  const pinned_key_matches=trusted_key_fingerprints.includes(public_key_fingerprint);
  const base={domain:RECEIPT_DOMAIN,receipt_id,contract_id:normalized.contract_id,
    proof_id:normalized.proof_id,public_key_fingerprint,signature_valid,
    pinned_key_matches,binding_matches,time_valid,
    replay_claim_accepted:false,verified:false,
    execution_provenance_verified:false,buyer_acceptance_verified:false,
    signer_identity_verified:false,payment_verified:false,
    note:"A validated signature is a scoped technical statement, not an independent proof of real-world work or settlement."};
  if(!signature_valid) return {...base,status:"signature_invalid"};
  if(!pinned_key_matches) return {...base,status:"untrusted_signing_key"};
  if(!binding_matches) return {...base,status:"binding_mismatch"};
  if(!time_valid) return {...base,status:"expired_or_not_yet_valid"};
  if(typeof claimNonce!=="function") return {...base,status:"replay_check_unavailable"};
  // Deliberately exclude proof_id: nonce reuse is blocked even if other fields change.
  const key=await digest(RECEIPT_DOMAIN+":"+public_key_fingerprint+":"+normalized.audience+":"+normalized.nonce);
  try {
    const claimed=await claimNonce({key,expires_at:normalized.expires_at,receipt_id});
    if(claimed!==true) return {...base,status:"replay_detected"};
  } catch {return {...base,status:"replay_check_error"};}
  return {...base,status:"verified_technical_receipt",replay_claim_accepted:true,verified:true};
}
