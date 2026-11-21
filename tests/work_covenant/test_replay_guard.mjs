import {test} from "node:test";
import assert from "node:assert/strict";
import {compileContract} from "../../services/agent-work-covenant-2047/core.mjs";
import {evaluateOnce} from "../../services/agent-work-covenant-2047/replay_guard.mjs";
const NOW=Date.parse("2026-11-19T12:00:00Z");
async function fixture() {
  const compiled=await compileContract({
    task:{title:"Deliver report",id:"unique-work-order-001"},
    criteria:[{id:"output_exists",type:"artifact_exists",artifact:"output.json"}]
  });
  const input={contract:compiled.contract,contract_id:compiled.contract_id,
    submission:{artifacts:[{name:"output.json",content:'{"ok":true}'}]}};
  const used=new Set();
  const trusted={
    expected_contract_id:compiled.contract_id,
    expected_task_id:"unique-work-order-001",audience_id:"buyer-acme-001",
    challenge_nonce:"ab".repeat(16),issued_at:"2026-11-19T11:59:00Z",
    expires_at:"2026-11-19T12:04:00Z",now_ms:NOW,
    consume_once:async key=>{if(used.has(key))return false;used.add(key);return true;}
  };
  return {input,trusted,used};
}
test("accepts one locally verified technical proof, never a settlement claim",async()=>{
  const {input,trusted}=await fixture();
  const r=await evaluateOnce(input,trusted);
  assert.equal(r.accepted,true);
  assert.match(r.replay_key,/^[a-f0-9]{64}$/);
  assert.equal(r.payment_verified,false);
  assert.equal(r.buyer_acceptance_verified,false);
});
test("identical replay fails",async()=>{
  const {input,trusted}=await fixture();
  assert.equal((await evaluateOnce(input,trusted)).accepted,true);
  assert.equal((await evaluateOnce(input,trusted)).reason,"duplicate_contract_proof");
});
test("different challenge cannot bypass one-time contract nullifier",async()=>{
  const {input,trusted}=await fixture();
  const a=await evaluateOnce(input,trusted);
  const b=await evaluateOnce(input,{...trusted,challenge_nonce:"cd".repeat(16)});
  assert.equal(b.reason,"duplicate_contract_proof");
  assert.equal(a.replay_key,b.replay_key);
});
test("changed unpinned evidence cannot bypass contract nullifier",async()=>{
  const {input,trusted}=await fixture();
  await evaluateOnce(input,trusted);
  const different=structuredClone(input);
  different.submission.artifacts[0].content='{"ok":false}';
  assert.equal((await evaluateOnce(different,trusted)).reason,"duplicate_contract_proof");
});
test("wrong pinned task or contract is rejected",async()=>{
  const {input,trusted}=await fixture();
  await assert.rejects(evaluateOnce(input,{...trusted,expected_task_id:"wrong"}),
    {code:"untrusted_contract_binding"});
  await assert.rejects(evaluateOnce(input,{...trusted,expected_contract_id:"0".repeat(64)}),
    {code:"untrusted_contract_binding"});
});
test("failed technical check does not reserve a nullifier",async()=>{
  const {input,trusted,used}=await fixture();
  input.submission.artifacts=[];
  assert.equal((await evaluateOnce(input,trusted)).reason,"local_checks_failed");
  assert.equal(used.size,0);
});
test("self-reported test counts cannot pass the stronger gate",async()=>{
  const {trusted,used}=await fixture();
  const c=await compileContract({task:{title:"Claim tests",id:"unique-work-order-001"},
    criteria:[{id:"tests",type:"test_summary",suite:"unit",min_passed:1,max_failed:0}]});
  const input={contract:c.contract,contract_id:c.contract_id,
    submission:{reported_tests:[{suite:"unit",passed:42,failed:0}]}};
  assert.equal((await evaluateOnce(input,{...trusted,expected_contract_id:c.contract_id})).reason,
    "unverified_self_reports");
  assert.equal(used.size,0);
});
test("expired or excessively long challenges fail closed",async()=>{
  const {input,trusted}=await fixture();
  await assert.rejects(evaluateOnce(input,{...trusted,now_ms:NOW+300_000}),
    {code:"stale_or_invalid_challenge"});
  await assert.rejects(evaluateOnce(input,{...trusted,expires_at:"2026-11-19T12:08:00Z"}),
    {code:"stale_or_invalid_challenge"});
});
test("no store, broken store and nonboolean response fail closed",async()=>{
  const {input,trusted}=await fixture();
  await assert.rejects(evaluateOnce(input,{...trusted,consume_once:undefined}),
    {code:"durable_store_required"});
  await assert.rejects(evaluateOnce(input,{...trusted,consume_once:async()=>{throw Error("down");}}),
    {code:"replay_store_unavailable"});
  await assert.rejects(evaluateOnce(input,{...trusted,consume_once:async()=>1}),
    {code:"invalid_store_response"});
});
test("forged challenges and future timestamps fail closed",async()=>{
  const {input,trusted}=await fixture();
  await assert.rejects(evaluateOnce(input,{...trusted,challenge_nonce:"deadbeef"}),
    {code:"invalid_trusted_challenge"});
  await assert.rejects(evaluateOnce(input,{...trusted,issued_at:"2026-11-19T12:01:00Z"}),
    {code:"stale_or_invalid_challenge"});
});
test("mutated contract breaks the evaluator digest check",async()=>{
  const {input,trusted}=await fixture();
  input.contract.criteria[0].artifact="changed.txt";
  await assert.rejects(evaluateOnce(input,trusted),/contract_id_mismatch/);
});
