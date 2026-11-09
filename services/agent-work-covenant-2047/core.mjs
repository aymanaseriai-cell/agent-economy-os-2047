/**
 * Agent Economy OS 2047: Proof-Carrying Work Covenant (beta)
 * Pure deterministic compile/evaluate engine; NO network, account, buyer identity,
 * financial, settlement, or execution permissions.
 *
 * A passing result means ONLY that supplied bytes meet caller-supplied criteria,
 * never that a customer accepted the work or that anyone paid.
 */
const textEncoder = new TextEncoder();
const isRecord = v => v !== null && typeof v === "object" && !Array.isArray(v);
const safeNumber = v => Number.isSafeInteger(v) && v >= 0;
const criterionId = /^[a-z][a-z0-9_-]{1,47}$/;
const artifactName = /^[a-zA-Z0-9][a-zA-Z0-9_.\/-]{0,119}$/;
const sha256hex = /^[0-9a-f]{64}$/;
const suiteName = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$/;
const TYPES = new Set(["artifact_exists","artifact_sha256","json_pointer_equals","text_contains","test_summary"]);
export const API_VERSION = "agent-economy.work-covenant.v1";

export class CovenantError extends Error {
  constructor(code) { super(code); this.name="CovenantError"; this.code=code; }
}
const reject = code => {throw new CovenantError(code);};
const check = (test, code) => {if(!test) reject(code);};
const textBytes = s => textEncoder.encode(s).length;
function str(v,limit,code,pattern=null) {
  check(typeof v==="string" && v.trim()===v && v.length>0 && textBytes(v)<=limit,code);
  if(pattern) check(pattern.test(v),code);
  return v;
}
function name(v) {
  str(v,120,"invalid_artifact_name",artifactName);
  check(!v.includes("..") && !v.startsWith("/") && !v.includes("//") && !v.includes("\\"),"invalid_artifact_name");
  return v;
}
function safeUrl(v) {
  if(v===undefined || v===null || v==="") return null;
  str(v,350,"invalid_source_url");
  let u;
  try {u=new URL(v);} catch {reject("invalid_source_url");}
  check(u.protocol==="https:" && !!u.hostname && !u.username && !u.password && !u.hash &&
    (u.port==="" || u.port==="443") && !/[\s]/.test(v),"invalid_source_url");
  // A label only. The service NEVER fetches this URL.
  return v;
}
function scalar(v) {
  return v===null || typeof v==="string" || typeof v==="boolean" ||
    (typeof v==="number" && Number.isFinite(v));
}
export function canonical(value) {
  if(Array.isArray(value)) return "["+value.map(canonical).join(",")+"]";
  if(isRecord(value)) {
    const keys=Object.keys(value).sort();
    return "{"+keys.map(k=>JSON.stringify(k)+":"+canonical(value[k])).join(",")+"}";
  }
  if(value===null || typeof value==="boolean" || typeof value==="string" ||
    (typeof value==="number" && Number.isFinite(value))) return JSON.stringify(value);
  reject("non_json_value");
}
export async function digest(value) {
  const bytes=typeof value==="string" ? textEncoder.encode(value):value;
  const hash=await crypto.subtle.digest("SHA-256",bytes);
  return Array.from(new Uint8Array(hash), x=>x.toString(16).padStart(2,"0")).join("");
}

function normalizeCriterion(raw) {
  check(isRecord(raw),"invalid_criterion");
  const id=str(raw.id,48,"invalid_criterion_id",criterionId);
  const type=str(raw.type,40,"invalid_criterion_type");
  check(TYPES.has(type),"unsupported_criterion_type");
  const base={id,type};
  if(type==="test_summary") {
    base.suite=str(raw.suite,80,"invalid_suite",suiteName);
    check(safeNumber(raw.min_passed) && raw.min_passed>=1 && raw.min_passed<=100000,"invalid_min_passed");
    check(safeNumber(raw.max_failed) && raw.max_failed<=100000,"invalid_max_failed");
    base.min_passed=raw.min_passed;
    base.max_failed=raw.max_failed;
    return base;
  }
  base.artifact=name(raw.artifact);
  if(type==="artifact_sha256") {
    base.expected_sha256=str(raw.expected_sha256,64,"invalid_expected_hash",sha256hex);
  }
  if(type==="json_pointer_equals") {
    const ptr=str(raw.pointer,128,"invalid_json_pointer");
    check(ptr.startsWith("/") && !ptr.endsWith("/") && !ptr.includes("//") &&
      !ptr.includes("__proto__"),"invalid_json_pointer");
    check(scalar(raw.expected),"invalid_expected_value");
    if(typeof raw.expected==="string") check(textBytes(raw.expected)<=256,"expected_value_too_long");
    base.pointer=ptr;
    base.expected=raw.expected;
  }
  if(type==="text_contains") base.needle=str(raw.needle,100,"invalid_needle");
  return base;
}
export function normalizeContract(input) {
  check(isRecord(input) && isRecord(input.task),"invalid_contract");
  const task={title:str(input.task.title,180,"invalid_task_title")};
  if(input.task.id!==undefined) task.id=str(input.task.id,100,"invalid_task_id",/^[a-zA-Z0-9_:.\/-]{1,100}$/);
  const url=safeUrl(input.task.source_url);
  if(url) task.source_url=url;
  check(Array.isArray(input.criteria) && input.criteria.length>0 && input.criteria.length<=12,"invalid_criteria_count");
  const criteria=input.criteria.map(normalizeCriterion);
  check(new Set(criteria.map(x=>x.id)).size===criteria.length,"duplicate_criterion_id");
  return {
    schema: API_VERSION,
    scope: "caller_supplied_work_requirements_only",
    task, criteria
  };
}
export async function compileContract(input) {
  const contract=normalizeContract(input);
  const contract_id=await digest(canonical(contract));
  return {
    schema: API_VERSION, status:"compiled",contract_id,contract,
    limitations:[
      "Not a buyer-signed contract: criteria are caller-supplied and unauthenticated.",
      "No escrow, economic settlement, independent acceptance, or legal guarantee.",
      "Keep this contract_id in an independently trusted system before accepting work."
    ]
  };
}
function parseEvidence(input) {
  check(isRecord(input),"invalid_submission");
  const rawArtifacts=input.artifacts ?? [];
  const rawTests=input.reported_tests ?? [];
  check(Array.isArray(rawArtifacts) && rawArtifacts.length<=10,"invalid_artifacts");
  check(Array.isArray(rawTests) && rawTests.length<=10,"invalid_reported_tests");
  const artifacts = new Map();
  for(const a of rawArtifacts) {
    check(isRecord(a),"invalid_artifact");
    const n=name(a.name);
    check(typeof a.content==="string" && textBytes(a.content)<=9000,"invalid_artifact_content");
    check(!artifacts.has(n),"duplicate_artifact_name");
    artifacts.set(n,a.content);
  }
  const tests=new Map();
  for(const t of rawTests) {
    check(isRecord(t),"invalid_test_report");
    const suite=str(t.suite,80,"invalid_suite",suiteName);
    check(safeNumber(t.passed)&&safeNumber(t.failed)&&t.passed<=1000000&&t.failed<=1000000,"invalid_test_counts");
    check(!tests.has(suite),"duplicate_test_suite");
    tests.set(suite,{suite,passed:t.passed,failed:t.failed});
  }
  return {artifacts,tests};
}
function pointerGet(value,pointer) {
  const parts=pointer.split("/").slice(1).map(s=>s.replace(/~1/g,"/").replace(/~0/g,"~"));
  let current=value;
  for(const p of parts) {
    if(isRecord(current) && Object.prototype.hasOwnProperty.call(current,p)) current=current[p];
    else if(Array.isArray(current) && /^(0|[1-9][0-9]*)$/.test(p) && Number(p)<current.length)
      current=current[Number(p)];
    else return {exists:false,value:null};
  }
  return {exists:true,value:current};
}
function sameScalar(a,b) {return scalar(a)&&scalar(b)&&Object.is(a,b);}
export async function evaluateContract(input) {
  check(isRecord(input) && isRecord(input.contract),"invalid_evaluation");
  const contract=normalizeContract(input.contract);
  const contract_id=await digest(canonical(contract));
  check(typeof input.contract_id==="string" && input.contract_id===contract_id,"contract_id_mismatch");
  const {artifacts,tests}=parseEvidence(input.submission);
  const hashes = {};
  for(const [key,content] of artifacts) hashes[key]={sha256:await digest(content),bytes:textBytes(content)};
  const checks = [];
  for(const criterion of contract.criteria) {
    let pass=false;
    let evidence_basis="supplied_bytes";
    const data=artifacts.get(criterion.artifact);
    switch(criterion.type) {
      case "artifact_exists":
        pass=typeof data==="string" && data.length>0;
        break;
      case "artifact_sha256":
        pass=typeof data==="string" && hashes[criterion.artifact].sha256===criterion.expected_sha256;
        break;
      case "text_contains":
        pass=typeof data==="string" && data.includes(criterion.needle);
        break;
      case "json_pointer_equals": {
        if(typeof data==="string") {
          try {
            const parsed=JSON.parse(data);
            const found=pointerGet(parsed,criterion.pointer);
            pass=found.exists && sameScalar(found.value,criterion.expected);
          } catch {pass=false;}
        }
        break;
      }
      case "test_summary": {
        evidence_basis="unverified_self_report";
        const t=tests.get(criterion.suite);
        pass=!!t && t.passed>=criterion.min_passed && t.failed<=criterion.max_failed;
        break;
      }
    }
    checks.push({id:criterion.id,type:criterion.type,pass,evidence_basis});
  }
  const all=checks.every(x=>x.pass);
  const support={contract_id,artifact_hashes:hashes,reported_tests:Array.from(tests.values()),checks};
  const proof_id=await digest(canonical(support));
  return {
    schema:API_VERSION,
    status:all ? "local_checks_passed" : "local_checks_failed",
    contract_id,proof_id,results:checks,
    artifact_hashes:hashes,reported_tests:Array.from(tests.values()),
    passed:checks.filter(x=>x.pass).length,total:checks.length,
    evidence_covers_supplied_bytes_only:true,
    has_unverified_self_reports:checks.some(x=>x.evidence_basis==="unverified_self_report"),
    buyer_acceptance_verified:false,
    payment_verified:false,
    onchain_settlement_verified:false,
    limitations:[
      "The caller controls submitted artifacts and reports; this is not independent buyer acceptance.",
      "proof_id is a deterministic checksum, not a digital signature or on-chain proof.",
      "For economic proof independently confirm buyer approval, delivery and settled payment."
    ]
  };
}

/**
 * Optional Ed25519 technical endorsement: verifies an externally signed statement
 * about this exact deterministic contract. This NEVER proves the key belongs
 * to the buyer. A buyer's public key must be pinned out of band.
 */
export const ENDORSEMENT_DOMAIN="agent-economy.work-covenant.technical-endorsement.v1";
function b64urlBytes(v,expectedLength) {
  str(v,180,"invalid_base64url",/^[A-Za-z0-9_-]+$/);
  check(v.length%4!==1,"invalid_base64url");
  let bin;
  try {bin=atob(v.replace(/-/g,"+").replace(/_/g,"/")+"=".repeat((4-v.length%4)%4));}
  catch {reject("invalid_base64url");}
  check(bin.length===expectedLength,"invalid_key_or_signature_length");
  return Uint8Array.from(bin,c=>c.charCodeAt(0));
}
export async function prepareEndorsement(input) {
  check(isRecord(input) && isRecord(input.contract),"invalid_endorsement_request");
  const contract=normalizeContract(input.contract);
  const expectedId=await digest(canonical(contract));
  check(input.contract_id===expectedId,"contract_id_mismatch");
  const decision=str(input.decision,40,"invalid_decision");
  check(["technical-reviewed","technical-approved","technical-rejected"].includes(decision),"invalid_decision");
  const issued_at=str(input.issued_at,30,"invalid_issued_at",
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
  check(!Number.isNaN(Date.parse(issued_at)) && new Date(issued_at).toISOString().replace(".000Z","Z")===issued_at,
    "invalid_issued_at");
  const payload={domain:ENDORSEMENT_DOMAIN,contract_id:expectedId,decision,issued_at};
  const message=canonical(payload);
  return {
    schema:ENDORSEMENT_DOMAIN,
    status:"message_prepared",
    message, message_sha256:await digest(message),
    signature_algorithm:"Ed25519",
    key_lookup:"out_of_band_required",
    warning:"Technical cryptographic statement only. Not buyer identity, authority, legal agreement, delivery or payment."
  };
}
export async function verifyEndorsement(input) {
  const prepared=await prepareEndorsement(input);
  const publicBytes=b64urlBytes(input.public_key_b64url,32);
  const signatureBytes=b64urlBytes(input.signature_b64url,64);
  let signature_valid=false;
  try {
    const key=await crypto.subtle.importKey("raw",publicBytes,{name:"Ed25519"},false,["verify"]);
    signature_valid=await crypto.subtle.verify({name:"Ed25519"},key,signatureBytes,textEncoder.encode(prepared.message));
  }catch {signature_valid=false;}
  const public_key_fingerprint=await digest(publicBytes);
  return {
    schema:ENDORSEMENT_DOMAIN,
    status:signature_valid?"cryptographic_signature_valid":"signature_invalid",
    signature_valid,
    contract_id:input.contract_id,
    message_sha256:prepared.message_sha256,
    public_key_fingerprint,
    signer_identity_verified:false,
    signer_authority_verified:false,
    buyer_acceptance_verified:false,
    legal_agreement_verified:false,
    payment_verified:false,
    warning:"Match the public key to a real authorized counterparty independently. Signature validity alone proves no commercial status."
  };
}
