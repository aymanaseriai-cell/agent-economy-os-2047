import {test} from "node:test";
import assert from "node:assert/strict";
import {compileContract,evaluateContract,digest,API_VERSION,prepareDeliveryEndorsement,verifyDeliveryEndorsement} from "../../services/agent-work-covenant-2047/core.mjs";

const sample = async () => {
  const expected = await digest('{"ok":true,"count":3}');
  const raw={
    task:{title:"Deliver deterministic API report",id:"task_demo_1",
      source_url:"https://example.org/tasks/one"},
    criteria:[
      {id:"manifest_hash",type:"artifact_sha256",artifact:"report.json",expected_sha256:expected},
      {id:"json_ok",type:"json_pointer_equals",artifact:"report.json",pointer:"/ok",expected:true},
      {id:"report_has_value",type:"json_pointer_equals",artifact:"report.json",pointer:"/count",expected:3},
      {id:"readme",type:"text_contains",artifact:"README.md",needle:"verification"},
      {id:"test_suite",type:"test_summary",suite:"unit",min_passed:12,max_failed:0}
    ]};
  const submission={
    artifacts:[
      {name:"report.json",content:'{"ok":true,"count":3}'},
      {name:"README.md",content:"local verification with plain text"}
    ],
    reported_tests:[{suite:"unit",passed:12,failed:0}]
  };
  return {raw,submission};
};
test("compilation and evaluation pass only local technical checks",async()=>{
 const {raw,submission}=await sample();
 const c=await compileContract(raw);
 assert.equal(c.schema,API_VERSION);
 const r=await evaluateContract({...c,submission});
 assert.equal(r.status,"local_checks_passed");
 assert.equal(r.passed,5);
 assert.equal(r.buyer_acceptance_verified,false);
 assert.equal(r.payment_verified,false);
 assert.equal(r.has_unverified_self_reports,true);
 assert.equal(r.results.find(x=>x.id==="test_suite").evidence_basis,"unverified_self_report");
 assert.equal(r.results.find(x=>x.id==="manifest_hash").evidence_basis,"supplied_bytes");
 assert.match(r.proof_id,/^[a-f0-9]{64}$/);
 assert.ok(!JSON.stringify(r).includes("local verification with plain text"),"never echo provided content");
});
test("stable canonical contract and proof hashes are independent of key order",async()=>{
 const {raw,submission}=await sample();
 const changed={criteria:raw.criteria.map(c=>Object.fromEntries(Object.entries(c).reverse())),
 task:Object.fromEntries(Object.entries(raw.task).reverse())};
 const a=await compileContract(raw),b=await compileContract(changed);
 assert.equal(a.contract_id,b.contract_id);
 const p=await evaluateContract({...a,submission});
 const q=await evaluateContract({...b,submission});
 assert.equal(p.proof_id,q.proof_id);
});
test("tampering the contract invalidates a pinned contract hash",async()=>{
 const {raw,submission}=await sample();
 const c=await compileContract(raw);
 c.contract.criteria[0].expected_sha256="0".repeat(64);
 await assert.rejects(evaluateContract({...c,submission}),/contract_id_mismatch/);
});
test("wrong supplied bytes fail independently of self-report",async()=>{
 const {raw,submission}=await sample();
 const c=await compileContract(raw);
 submission.artifacts[0].content='{"ok":true,"count":4}';
 const r=await evaluateContract({...c,submission});
 assert.equal(r.status,"local_checks_failed");
 assert.equal(r.results.find(x=>x.id==="manifest_hash").pass,false);
 assert.equal(r.results.find(x=>x.id==="report_has_value").pass,false);
});
test("test counts are self-reported and cannot independently prove tests ran",async()=>{
 const {raw,submission}=await sample();
 const c=await compileContract(raw);
 submission.reported_tests[0].failed=1;
 const r=await evaluateContract({...c,submission});
 assert.equal(r.results.find(x=>x.id==="test_suite").pass,false);
});
test("duplicate and malicious artifact names are rejected",async()=>{
 const {raw,submission}=await sample();
 const c=await compileContract(raw);
 submission.artifacts.push({name:"../secrets",content:"anything"});
 await assert.rejects(evaluateContract({...c,submission}),/invalid_artifact_name/);
});
test("oversized content is rejected",async()=>{
 const {raw,submission}=await sample();
 const c=await compileContract(raw);
 submission.artifacts[0].content="a".repeat(9001);
 await assert.rejects(evaluateContract({...c,submission}),/invalid_artifact_content/);
});
test("duplicate criteria ids are rejected",async()=>{
 const {raw}=await sample();
 raw.criteria.push({...raw.criteria[0]});
 await assert.rejects(compileContract(raw),/duplicate_criterion_id/);
});
test("criteria cap and unknown type are rejected",async()=>{
 const {raw}=await sample();
 raw.criteria=Array.from({length:13},(_,i)=>({id:"check_"+i,type:"artifact_exists",artifact:"x"}));
 await assert.rejects(compileContract(raw),/invalid_criteria_count/);
 raw.criteria=[{id:"unsafe",type:"execute_python",code:"rm -rf /"}];
 await assert.rejects(compileContract(raw),/unsupported_criterion_type/);
});
test("source_url is inert and non-https is rejected",async()=>{
 const {raw}=await sample();
 raw.task.source_url="http://127.0.0.1:22/";
 await assert.rejects(compileContract(raw),/invalid_source_url/);
});
test("json pointer escaped keys and array index are evaluated",async()=>{
 const raw={task:{title:"Output JSON"},criteria:[
   {id:"key",type:"json_pointer_equals",artifact:"data.json",pointer:"/a~1b/0/x~0y",expected:"ok"}
 ]};
 const c=await compileContract(raw);
 const r=await evaluateContract({...c,submission:{artifacts:[{name:"data.json",content:'{"a/b":[{"x~y":"ok"}]}'}]}});
 assert.equal(r.status,"local_checks_passed");
});
test("reject missing contract digest; self-generated approval cannot count as payment",async()=>{
 const {raw,submission}=await sample();
 const c=await compileContract(raw);
 await assert.rejects(evaluateContract({contract:c.contract,contract_id:"0".repeat(64),submission}),/contract_id_mismatch/);
 const result=await evaluateContract({...c,submission});
 assert.equal(result.onchain_settlement_verified,false);
});

test("valid Ed25519 signature verifies a specific technical statement but not buyer identity",async()=>{
 const {compileContract,prepareEndorsement,verifyEndorsement}=await import("../../services/agent-work-covenant-2047/core.mjs");
 const compiled=await compileContract({task:{title:"Technical-review artifact"},criteria:[
   {id:"proof",type:"artifact_exists",artifact:"proof.json"}
 ]});
 const unsigned={contract:compiled.contract,contract_id:compiled.contract_id,
   decision:"technical-reviewed",issued_at:"2026-11-09T17:53:00Z"};
 const prepared=await prepareEndorsement(unsigned);
 const pair=await crypto.subtle.generateKey({name:"Ed25519"},true,["sign","verify"]);
 const sig=await crypto.subtle.sign("Ed25519",pair.privateKey,new TextEncoder().encode(prepared.message));
 const pub=await crypto.subtle.exportKey("raw",pair.publicKey);
 const encode=x=>Buffer.from(x).toString("base64url");
 const request={...unsigned,public_key_b64url:encode(pub),signature_b64url:encode(sig)};
 const valid=await verifyEndorsement(request);
 assert.equal(valid.signature_valid,true);
 assert.equal(valid.buyer_acceptance_verified,false);
 assert.equal(valid.signer_identity_verified,false);
 assert.equal(valid.signer_authority_verified,false);
 assert.equal(valid.payment_verified,false);
 assert.match(valid.public_key_fingerprint,/^[a-f0-9]{64}$/);
 const tampered=await verifyEndorsement({...request,decision:"technical-approved"});
 assert.equal(tampered.signature_valid,false);
});
test("Ed25519 endorsement rejects invalid key length or modified contract id",async()=>{
 const {compileContract,verifyEndorsement}=await import("../../services/agent-work-covenant-2047/core.mjs");
 const c=await compileContract({task:{title:"Review document"},criteria:[
  {id:"present",type:"artifact_exists",artifact:"file.txt"}
 ]});
 const base={contract:c.contract,contract_id:c.contract_id,
  decision:"technical-reviewed",issued_at:"2026-11-09T17:53:00Z",
  public_key_b64url:"AAA",signature_b64url:"AAA"};
 await assert.rejects(verifyEndorsement(base),/invalid_key_or_signature_length/);
 await assert.rejects(verifyEndorsement({...base,contract_id:"0".repeat(64)}),/contract_id_mismatch/);
});


test("proof-bound delivery signature verifies and cannot cross audience, decision or nonce",async()=>{
 const {raw,submission}=await sample();
 const c=await compileContract(raw);
 const ev=await evaluateContract({...c,submission});
 const keyPair=await crypto.subtle.generateKey("Ed25519",true,["sign","verify"]);
 const pub=Buffer.from(await crypto.subtle.exportKey("raw",keyPair.publicKey)).toString("base64url");
 const args={...c,submission,proof_id:ev.proof_id,decision:"delivery-accepted",
   issued_at:"2026-11-19T10:00:00Z",nonce:"buyer_challenge_00001",audience:"did:example:buyer"};
 const prepared=await prepareDeliveryEndorsement(args);
 const sig=Buffer.from(await crypto.subtle.sign("Ed25519",keyPair.privateKey,
   new TextEncoder().encode(prepared.message))).toString("base64url");
 const proof={public_key_b64url:pub,signature_b64url:sig};
 const valid=await verifyDeliveryEndorsement({...args,...proof});
 assert.equal(valid.signature_valid,true);
 assert.equal(valid.buyer_acceptance_verified,false);
 assert.equal(valid.payment_verified,false);
 assert.equal(valid.nonce_replay_prevented,false);
 for(const override of [
   {audience:"did:example:other"},{nonce:"buyer_challenge_00002"},
   {decision:"delivery-reviewed"}]) {
   const changed=await verifyDeliveryEndorsement({...args,...override,...proof});
   assert.equal(changed.signature_valid,false);
 }
});
test("delivery signature cannot be moved to another artifact under the same contract",async()=>{
 const {raw,submission}=await sample();
 const c=await compileContract(raw);
 const ev=await evaluateContract({...c,submission});
 const args={...c,submission,proof_id:ev.proof_id,decision:"delivery-reviewed",
   issued_at:"2026-11-19T10:00:00Z",nonce:"buyer_challenge_00003",audience:"buyer_001"};
 await prepareDeliveryEndorsement(args);
 const altered=structuredClone(submission);
 altered.artifacts[1].content+=" changed";
 await assert.rejects(prepareDeliveryEndorsement({...args,submission:altered}),/proof_id_mismatch/);
});
test("failed work cannot be marked technically accepted by delivery endorsement",async()=>{
 const {raw,submission}=await sample();
 const c=await compileContract(raw);
 submission.artifacts[0].content='{"ok":false}';
 const ev=await evaluateContract({...c,submission});
 const args={...c,submission,proof_id:ev.proof_id,decision:"delivery-accepted",
   issued_at:"2026-11-19T10:00:00Z",nonce:"buyer_challenge_00004",audience:"buyer_001"};
 await assert.rejects(prepareDeliveryEndorsement(args),/cannot_accept_failed_checks/);
 const reject=await prepareDeliveryEndorsement({...args,decision:"delivery-rejected"});
 assert.equal(reject.technical_checks_status,"local_checks_failed");
});
test("delivery endorsement rejects forged proof ids and malformed metadata",async()=>{
 const {raw,submission}=await sample();
 const c=await compileContract(raw);
 const ev=await evaluateContract({...c,submission});
 const args={...c,submission,proof_id:ev.proof_id,decision:"delivery-reviewed",
   issued_at:"2026-11-19T10:00:00Z",nonce:"buyer_challenge_00005",audience:"buyer_001"};
 await assert.rejects(prepareDeliveryEndorsement({...args,proof_id:"0".repeat(64)}),/proof_id_mismatch/);
 await assert.rejects(prepareDeliveryEndorsement({...args,nonce:"short"}),/invalid_delivery_nonce/);
 await assert.rejects(prepareDeliveryEndorsement({...args,issued_at:"not-a-date"}),/invalid_issued_at/);
});
