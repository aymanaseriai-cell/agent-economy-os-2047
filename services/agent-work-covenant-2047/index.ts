/*
 * Agent Economy OS 2047: Work Covenant beta HTTP API
 * Stateless and read-only: no accounts, databases, external fetches,
 * credential handling, contracts signed on behalf of others, or payments.
 */
import {API_VERSION,compileContract,evaluateContract,prepareEndorsement,verifyEndorsement,CovenantError} from "./core.mjs";
const FUNCTION_NAME="agent-work-covenant-2047";
const MAX_BODY=16_384;
const HEADERS={
  "access-control-allow-origin":"*",
  "access-control-allow-methods":"GET,POST,OPTIONS",
  "access-control-allow-headers":"content-type",
  "cache-control":"no-store",
  "x-content-type-options":"nosniff",
  "content-security-policy":"default-src 'none'; frame-ancestors 'none'",
  "cross-origin-resource-policy":"cross-origin"
};
function response(value,status=200,contentType="application/json; charset=utf-8") {
  return new Response(typeof value==="string" ? value:JSON.stringify(value),{
    status,headers:{...HEADERS,"content-type":contentType}
  });
}
function error(code,status=400) {
  return response({ok:false,error:{code}},status);
}
function internalPath(url) {
  const segments=new URL(url).pathname.split("/").filter(Boolean);
  const at=segments.indexOf(FUNCTION_NAME);
  const rest=at<0 ? segments:segments.slice(at+1);
  return "/"+rest.join("/");
}
async function parseBody(req) {
  const type=req.headers.get("content-type")||"";
  if(!/^application\/json(?:\s*;|$)/i.test(type)) throw new CovenantError("expected_application_json");
  const claimed=req.headers.get("content-length");
  if(claimed!==null && Number(claimed)>MAX_BODY) throw new CovenantError("request_too_large");
  if(!req.body) throw new CovenantError("missing_body");
  const reader=req.body.getReader();
  const chunks=[];
  let size=0;
  try {
    while(true) {
      const {value,done}=await reader.read();
      if(done) break;
      size+=value.byteLength;
      if(size>MAX_BODY) {await reader.cancel();throw new CovenantError("request_too_large");}
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const all=new Uint8Array(size);
  let start=0;
  for(const chunk of chunks) {all.set(chunk,start);start+=chunk.byteLength;}
  let body;
  try {body=JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(all));}
  catch {throw new CovenantError("invalid_json");}
  if(!body || typeof body!=="object" || Array.isArray(body)) throw new CovenantError("expected_json_object");
  return body;
}
function discovery() {
  return {
    schema:"agent-economy.work-covenant-discovery.v1",
    name:"Agent Economy OS 2047 — Proof-Carrying Work Covenant",
    maturity:"public_beta",
    service_url:"https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/"+FUNCTION_NAME,
    version:API_VERSION,
    payment_required:false,
    capabilities:[
      "compile deterministic caller-defined work checks",
      "verify hashes and JSON fields of user-supplied artifacts",
      "evaluate self-reported test counts with explicit trust limitations",
      "produce repeatable evidence checksums"
    ],
    anti_claims:[
      "not a signed contract or independent buyer approval",
      "not an attestation of execution, authorship, payment, or settlement",
      "not a formal A2A or x402 implementation"
    ],
    endpoints:{
      health:"GET /health",
      demo:"GET /demo",
      compile:"POST /v1/compile",
      evaluate:"POST /v1/evaluate",
      prepare_endorsement:"POST /v1/endorsement-message",
      verify_endorsement:"POST /v1/verify-endorsement",
      discovery:"GET /.well-known/agent.json",
      schema:"GET /openapi.json",
      skill:"GET /skill.md"
    }
  };
}
const demoContract={
  task:{title:"Generate reproducible JSON report",id:"demo_public_qa"},
  criteria:[
    {id:"report_exists",type:"artifact_exists",artifact:"report.json"},
    {id:"status_ok",type:"json_pointer_equals",artifact:"report.json",pointer:"/ok",expected:true},
    {id:"report_test",type:"test_summary",suite:"unit",min_passed:3,max_failed:0}
  ]
};
function skill() {
  return [
    "# Proof-Carrying Work Covenant (public beta)",
    "Stateless, free, technical-evidence checker. Not payment or independent acceptance.",
    "POST /v1/compile with a task title and 1-12 criteria.",
    "Types: artifact_exists, artifact_sha256, json_pointer_equals, text_contains, test_summary.",
    "Preserve the returned contract_id with a trusted third party; it is not signed.",
    "POST /v1/evaluate with contract, contract_id, and a submission containing",
    "artifacts: [{name, content}] and optional reported_tests: [{suite,passed,failed}].",
    "The result distinguishes checks against supplied bytes from unverified self-reports.",
    "Optional POST /v1/endorsement-message yields a deterministic Ed25519 message to sign elsewhere.",
    "Optional POST /v1/verify-endorsement verifies that cryptographic signature, NOT the signer's authority.",
    "Local pass does NOT imply buyer acceptance, rights transfer, receipt, or paid revenue.",
    "No client-supplied source_url is fetched. Never submit secrets or private customer data.",
    "Limits: 16 KiB JSON request body, 12 criteria, 10 artifacts, 9,000 bytes per artifact.",
    "See GET /openapi.json for protocol fields and GET /demo for a sample."
  ].join("\n");
}
function openapi() {
  return {
    openapi:"3.0.3",
    info:{title:"Agent Economy Work Covenant API",version:"1.0.0-beta",
      description:"Caller-supplied technical evidence checks only; no buyer acceptance or financial settlement."},
    servers:[{url:discovery().service_url}],
    paths:{
      "/health":{get:{summary:"Service health",responses:{"200":{description:"Available"}}}},
      "/demo":{get:{summary:"Sample compiled work contract",responses:{"200":{description:"Demo only"}}}},
      "/v1/compile":{post:{summary:"Compile task criteria",requestBody:{required:true,content:{"application/json":{schema:{$ref:"#/components/schemas/CompileRequest"}}}},responses:{"200":{description:"Compiled immutable-checksum descriptor"},"400":{description:"Invalid criteria"}}}},
      "/v1/evaluate":{post:{summary:"Evaluate local evidence",requestBody:{required:true,content:{"application/json":{schema:{$ref:"#/components/schemas/EvaluateRequest"}}}},responses:{"200":{description:"Local checks report, no purchase or buyer attestation"},"400":{description:"Invalid evidence"}}}},
      "/v1/endorsement-message":{post:{summary:"Prepare deterministic Ed25519 technical-review message",responses:{"200":{description:"Unsigned message: signer must sign elsewhere"},"400":{description:"Invalid descriptor"}}}},
      "/v1/verify-endorsement":{post:{summary:"Verify Ed25519 signature only, NOT signer authority",responses:{"200":{description:"Cryptographic verification result with identity=false"},"400":{description:"Invalid signature envelope"}}}}
    },
    components:{schemas:{
      CompileRequest:{type:"object",required:["task","criteria"],properties:{
        task:{type:"object",required:["title"],properties:{id:{type:"string"},title:{type:"string"},source_url:{type:"string",format:"uri"}}},
        criteria:{type:"array",minItems:1,maxItems:12,items:{type:"object",required:["id","type"],properties:{
          id:{type:"string"},
          type:{type:"string",enum:["artifact_exists","artifact_sha256","json_pointer_equals","text_contains","test_summary"]},
          artifact:{type:"string"},expected_sha256:{type:"string"},pointer:{type:"string"},
          expected:{},needle:{type:"string"},suite:{type:"string"},min_passed:{type:"integer"},max_failed:{type:"integer"}
        }}}
      }},
      EvaluateRequest:{type:"object",required:["contract","contract_id","submission"],properties:{
        contract:{$ref:"#/components/schemas/CompileRequest"},
        contract_id:{type:"string"},
        submission:{type:"object",properties:{
          artifacts:{type:"array",items:{type:"object",required:["name","content"],properties:{name:{type:"string"},content:{type:"string"}}}},
          reported_tests:{type:"array",items:{type:"object",properties:{suite:{type:"string"},passed:{type:"integer"},failed:{type:"integer"}}}}
        }}
      }}
    }}
  };
}
export async function handler(req) {
  try {
    const path=internalPath(req.url);
    if(req.method==="OPTIONS") return new Response(null,{status:204,headers:HEADERS});
    if(req.method==="GET") {
      if(path==="/" || path==="/.well-known/agent.json") return response(discovery());
      if(path==="/health") return response({ok:true,service:FUNCTION_NAME,version:API_VERSION,stateless:true,no_paid_actions:true});
      if(path==="/skill.md") return response(skill(),200,"text/markdown; charset=utf-8");
      if(path==="/openapi.json") return response(openapi());
      if(path==="/demo") return response({ok:true,...await compileContract(demoContract),
        sample_submission:{artifacts:[{name:"report.json",content:'{"ok":true}'}],
        reported_tests:[{suite:"unit",passed:3,failed:0}]}
      });
      return error("not_found",404);
    }
    if(req.method==="POST") {
      if(!["/v1/compile","/v1/evaluate","/v1/endorsement-message","/v1/verify-endorsement"].includes(path)) return error("not_found",404);
      const json=await parseBody(req);
      if(path==="/v1/compile") return response({ok:true,...await compileContract(json)});
      if(path==="/v1/evaluate") return response({ok:true,...await evaluateContract(json)});
      if(path==="/v1/endorsement-message") return response({ok:true,...await prepareEndorsement(json)});
      return response({ok:true,...await verifyEndorsement(json)});
    }
    return error("method_not_allowed",405);
  } catch(e) {
    if(e instanceof CovenantError) return error(e.code,400);
    // Never expose stack traces or echo confidential caller input.
    return error("internal_error",500);
  }
}
if(typeof Deno!=="undefined" && typeof Deno.serve==="function") Deno.serve(handler);
