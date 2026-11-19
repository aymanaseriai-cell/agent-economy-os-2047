import {test} from "node:test";
import assert from "node:assert/strict";
import {handler} from "../../services/agent-work-covenant-2047/index.ts";
const BASE="https://example.supabase.co/functions/v1/agent-work-covenant-2047";
const get=p=>handler(new Request(BASE+p));
const post=(p,body,options={})=>handler(new Request(BASE+p,{method:"POST",headers:{"content-type":"application/json",...options.headers},body:JSON.stringify(body)}));
test("health/discovery/skill/openapi routes work",async()=>{
 for(const path of ["/","/health","/.well-known/agent.json","/skill.md","/openapi.json","/demo"]){
   const r=await get(path);assert.equal(r.status,200,path);
 }
 const o=await (await get("/openapi.json")).json();assert.equal(o.openapi,"3.0.3");
});
test("demo can be evaluated without external calls",async()=>{
 const obj=await (await get("/demo")).json();
 const r=await post("/v1/evaluate",{contract:obj.contract,contract_id:obj.contract_id,submission:obj.sample_submission});
 const result=await r.json();
 assert.equal(result.status,"local_checks_passed");
 assert.equal(result.buyer_acceptance_verified,false);
 assert.equal(result.payment_verified,false);
});
test("compile then evaluate: missing artifact fails local check",async()=>{
 const compiled=await (await post("/v1/compile",{task:{title:"Provide README"},criteria:[{id:"readme_present",type:"artifact_exists",artifact:"README.md"}]})).json();
 const result=await (await post("/v1/evaluate",{contract:compiled.contract,contract_id:compiled.contract_id,submission:{artifacts:[]}})).json();
 assert.equal(result.status,"local_checks_failed");
});
test("blocks invalid content-type and huge payload",async()=>{
 const r=await handler(new Request(BASE+"/v1/compile",{method:"POST",headers:{"content-type":"text/plain"},body:"hello"}));
 assert.equal((await r.json()).error.code,"expected_application_json");
 const huge=await handler(new Request(BASE+"/v1/compile",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({x:"a".repeat(20000)})}));
 assert.equal((await huge.json()).error.code,"request_too_large");
});
test("no redirects or unsafe method/actions",async()=>{
 assert.equal((await get("/transfer")).status,404);
 const x=await handler(new Request(BASE+"/v1/compile",{method:"PUT"}));
 assert.equal(x.status,405);
 const o=await handler(new Request(BASE+"/v1/compile",{method:"OPTIONS"}));
 assert.equal(o.status,204);
});
test("endorsement message and signature-verification endpoints maintain explicit trust boundary",async()=>{
 const c=await (await post("/v1/compile",{task:{title:"A task"},criteria:[
  {id:"file_present",type:"artifact_exists",artifact:"f.txt"}
 ]})).json();
 const envelope={contract:c.contract,contract_id:c.contract_id,decision:"technical-reviewed",issued_at:"2026-11-09T17:53:00Z"};
 const x=await post("/v1/endorsement-message",envelope);
 assert.equal(x.status,200);
 const message=await x.json();
 assert.match(message.message,/work-covenant.technical-endorsement/);
 const pair=await crypto.subtle.generateKey({name:"Ed25519"},true,["sign","verify"]);
 const signature=await crypto.subtle.sign("Ed25519",pair.privateKey,new TextEncoder().encode(message.message));
 const pub=await crypto.subtle.exportKey("raw",pair.publicKey);
 const verify=await post("/v1/verify-endorsement",{...envelope,
   public_key_b64url:Buffer.from(pub).toString("base64url"),
   signature_b64url:Buffer.from(signature).toString("base64url")
 });
 assert.equal(verify.status,200);
 const result=await verify.json();
 assert.equal(result.signature_valid,true);
 assert.equal(result.signer_identity_verified,false);
 assert.equal(result.payment_verified,false);
});


test("new delivery HTTP routes sign exact proof, reject changed bytes and avoid buyer claims",async()=>{
 const demo=await (await get("/demo")).json();
 const evaluation=await (await post("/v1/evaluate",{contract:demo.contract,
   contract_id:demo.contract_id,submission:demo.sample_submission})).json();
 const envelope={contract:demo.contract,contract_id:demo.contract_id,
   submission:demo.sample_submission,proof_id:evaluation.proof_id,
   decision:"delivery-accepted",issued_at:"2026-11-19T10:00:00Z",
   nonce:"http_challenge_00001",audience:"did:example:buyer"};
 const response=await post("/v1/delivery-endorsement-message",envelope);
 assert.equal(response.status,200);
 const prepared=await response.json();
 assert.ok(prepared.message.includes(evaluation.proof_id));
 const keyPair=await crypto.subtle.generateKey("Ed25519",true,["sign","verify"]);
 const signature=await crypto.subtle.sign("Ed25519",keyPair.privateKey,
   new TextEncoder().encode(prepared.message));
 const pub=await crypto.subtle.exportKey("raw",keyPair.publicKey);
 const signed={...envelope,public_key_b64url:Buffer.from(pub).toString("base64url"),
   signature_b64url:Buffer.from(signature).toString("base64url")};
 const good=await post("/v1/verify-delivery-endorsement",signed);
 assert.equal(good.status,200);
 const verified=await good.json();
 assert.equal(verified.signature_valid,true);
 assert.equal(verified.signer_authority_verified,false);
 assert.equal(verified.buyer_acceptance_verified,false);
 assert.equal(verified.payment_verified,false);
 const bad=await post("/v1/verify-delivery-endorsement",
   {...signed,submission:{...signed.submission,artifacts:[
     {...signed.submission.artifacts[0],content:"altered"}
   ]}});
 assert.equal(bad.status,400);
 assert.equal((await bad.json()).error.code,"proof_id_mismatch");
 const swapped=await (await post("/v1/verify-delivery-endorsement",
   {...signed,audience:"did:example:someone_else"})).json();
 assert.equal(swapped.signature_valid,false);
 const spec=await (await get("/openapi.json")).json();
 assert.ok(spec.paths["/v1/delivery-endorsement-message"]);
 assert.ok(spec.paths["/v1/verify-delivery-endorsement"]);
});
