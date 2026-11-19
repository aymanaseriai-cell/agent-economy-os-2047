import {test} from "node:test";
import assert from "node:assert/strict";
import {compileContract, evaluateContract} from "../../services/agent-work-covenant-2047/core.mjs";

test("signed zero cannot change an evaluation under an identical JSON contract_id", async () => {
  const make = expected => ({
    task: {title: "Verify numeric zero"},
    criteria: [{id:"zero_check",type:"json_pointer_equals",artifact:"evidence.json",
      pointer:"/value",expected}]
  });
  const contracts = [await compileContract(make(0)), await compileContract(make(-0))];
  assert.equal(contracts[0].contract_id, contracts[1].contract_id);
  for (const content of ['{"value":0}', '{"value":-0}']) {
    for (const contract of contracts) {
      const result = await evaluateContract({...contract,
        submission:{artifacts:[{name:"evidence.json",content}]}});
      assert.equal(result.status,"local_checks_passed");
      assert.equal(result.passed,1);
    }
  }
  for (const contract of contracts) {
    const result = await evaluateContract({...contract,
      submission:{artifacts:[{name:"evidence.json",content:'{"value":1}'}]}});
    assert.equal(result.status,"local_checks_failed");
  }
});
