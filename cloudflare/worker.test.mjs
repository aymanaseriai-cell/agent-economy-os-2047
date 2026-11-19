import test from "node:test";
import assert from "node:assert/strict";
import {workerFetch} from "./worker.mjs";

const base="https://failover.example";
const compileInput={task:{title:"Deliver JSON report"},criteria:[{id:"report_exists",type:"artifact_exists",artifact:"report.json"}]};
const post=(path,payload)=>new Request(base+path,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload)});

test("primary GET succeeds and preserves status",async()=>{
  let count=0;
  const r=await workerFetch(new Request(base+"/health"),{},async req=>{count++;assert.ok(req.url.startsWith("https://jzallxzbbdtelcpabfgr.supabase.co/"));return new Response(JSON.stringify({ok:true}),{status:200,headers:{"content-type":"application/json"}});});
  assert.equal(count,1);assert.equal(r.status,200);
  assert.equal(r.headers.get("x-agent-economy-upstream"),"supabase-primary");
});
test("health/read fallback after 503",async()=>{
  const r=await workerFetch(new Request(base+"/health"),{},async()=>new Response("fail",{status:503}));
  assert.equal(r.status,200);
  assert.equal(r.headers.get("x-agent-economy-upstream"),"cloudflare-local-v4");
  assert.equal((await r.json()).service,"agent-work-covenant-2047");
});
test("network errors fallback to local computation for POST",async()=>{
  const r=await workerFetch(post("/v1/compile",compileInput),{},async()=>{throw Error("unreachable")});
  assert.equal(r.status,200);
  const obj=await r.json();
  assert.equal(obj.status,"compiled");
  assert.match(obj.contract_id,/^[0-9a-f]{64}$/);
});
test("evaluate can run when primary unavailable",async()=>{
  const fail=async()=>{throw Error("network");};
  const compile=await (await workerFetch(post("/v1/compile",compileInput),{},fail)).json();
  const r=await workerFetch(post("/v1/evaluate",{contract:compile.contract,contract_id:compile.contract_id,submission:{artifacts:[{name:"report.json",content:"ok"}]}}),{},fail);
  const obj=await r.json();
  assert.equal(obj.status,"local_checks_passed");
  assert.equal(obj.payment_verified,false);
});
test("429 and 500 do not fail over",async()=>{
  for(const code of [401,403,429,500]) {
    let calls=0;
    const r=await workerFetch(new Request(base+"/health"),{},async()=>{calls++;return new Response("blocked",{status:code})});
    assert.equal(r.status,code);
    assert.equal(calls,1);
  }
});
test("unknown stateful endpoint is never proxied",async()=>{
  let calls=0;
  const r=await workerFetch(post("/x402/settle",{amount:1}),{},async()=>{calls++;return new Response("bad")});
  assert.equal(r.status,404); assert.equal(calls,0);
});
test("POST to GET-only route fails closed",async()=>{
  let calls=0;
  const r=await workerFetch(post("/health",{}),{},async()=>{calls++;return new Response("bad")});
  assert.equal(r.status,405);assert.equal(calls,0);
});
test("over-large POST is rejected before upstream",async()=>{
  let calls=0;
  const r=await workerFetch(new Request(base+"/v1/compile",{method:"POST",headers:{"content-type":"application/json"},body:"x".repeat(17000)}),{},async()=>{calls++;return new Response("bad")});
  assert.equal(r.status,413);assert.equal(calls,0);
});
test("credentials are not forwarded to public stateless upstream",async()=>{
  const r=await workerFetch(new Request(base+"/health",{headers:{authorization:"Bearer hidden",cookie:"session=hidden"}}),{},async req=>{
    assert.equal(req.headers.has("authorization"),false);
    assert.equal(req.headers.has("cookie"),false);
    return new Response("ok");
  });
  assert.equal(r.status,200);
});
test("HEAD request returns no body",async()=>{
  const r=await workerFetch(new Request(base+"/health",{method:"HEAD"}),{},async()=>new Response("not empty"));
  assert.equal(r.status,200);
  assert.equal(await r.text(),"");
});
test("OPTIONS handled locally without external calls",async()=>{
  let count=0;
  const r=await workerFetch(new Request(base+"/v1/compile",{method:"OPTIONS"}),{},async()=>{count++;throw Error()});
  assert.equal(r.status,204);assert.equal(count,0);
});
