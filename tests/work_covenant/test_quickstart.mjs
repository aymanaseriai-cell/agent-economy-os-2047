import {test} from "node:test";
import assert from "node:assert/strict";
import {runDemo} from "../../examples/proof-carrying-work/run.mjs";

test("zero-network getting-started demo passes legitimate synthetic work",async()=>{
  const result=await runDemo();
  assert.equal(result.synthetic_only,true);
  assert.equal(result.valid.status,"local_checks_passed");
  assert.equal(result.valid.passed,3);
  assert.equal(result.valid.total,3);
  assert.match(result.contract_id,/^[a-f0-9]{64}$/);
  assert.match(result.valid.proof_id,/^[a-f0-9]{64}$/);
  assert.equal(result.payment_verified,false);
  assert.equal(result.buyer_acceptance_verified,false);
});
test("same demo deterministically rejects altered submitted bytes",async()=>{
  const result=await runDemo();
  assert.equal(result.tampered.status,"local_checks_failed");
  assert.deepEqual(result.tampered.failed_check_ids,["hash_matches"]);
});
test("offline demo is deterministic and cannot be confused with a purchase",async()=>{
  const a=await runDemo(), b=await runDemo();
  assert.equal(a.contract_id,b.contract_id);
  assert.equal(a.valid.proof_id,b.valid.proof_id);
  assert.equal(a.payment_verified,false);
  assert.equal(a.buyer_acceptance_verified,false);
});
