const test = require("node:test");
const assert = require("node:assert/strict");
const {webcrypto} = require("node:crypto");
const {evaluate} = require("../docs/starter-demo.js");
for (const [scenario, verdict, reason, pin, status] of [
  ["intact", "PASS", "LOCAL_CHECKS_MATCH", true, true],
  ["artifact", "REJECT", "OUTPUT_STATUS_MISMATCH", true, false],
  ["policy", "REJECT", "POLICY_PIN_MISMATCH", false, null],
  ["both", "REJECT", "POLICY_PIN_MISMATCH", false, null]
]) {
  test(scenario, async () => {
    const r = await evaluate(scenario, webcrypto);
    assert.equal(r.verdict, verdict);
    assert.equal(r.reason, reason);
    assert.equal(r.policy_pin_matched, pin);
    assert.equal(r.output_status_matched, status);
    for (const k of ["buyer_authority_verified", "agent_execution_verified", "payment_verified"]) assert.equal(r[k], false);
    assert.equal(r.synthetic, true);
  });
}
test("unknown scenario and missing crypto fail closed", async () => {
  await assert.rejects(evaluate("__proto__", webcrypto), /Unknown/);
  await assert.rejects(evaluate("intact", null), /unavailable/);
});
