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
