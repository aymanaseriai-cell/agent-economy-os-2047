"use strict";
const POLICY = '{"required_status":"ready_for_review"}';
const REPLACEMENT = '{"required_status":"tampered_status"}';
const PIN = "62ba60814a3c2dff622abcbefe252a5e5368f085c0c58c9ed3d3a30ecac6efef";
const SCENARIOS = Object.freeze({
  intact: [POLICY, "ready_for_review"],
  artifact: [POLICY, "tampered_status"],
  policy: [REPLACEMENT, "ready_for_review"],
  both: [REPLACEMENT, "tampered_status"]
});
async function digest(text, cryptoProvider) {
  const bytes = new TextEncoder().encode(text);
  const hash = await cryptoProvider.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash), n => n.toString(16).padStart(2, "0")).join("");
}
async function evaluate(scenario, cryptoProvider) {
  if (!Object.prototype.hasOwnProperty.call(SCENARIOS, scenario)) throw new Error("Unknown synthetic scenario");
  if (!cryptoProvider || !cryptoProvider.subtle) throw new Error("Web Crypto unavailable; use HTTPS or localhost");
  const [policy, output] = SCENARIOS[scenario];
  const actual = await digest(policy, cryptoProvider);
  const pinMatched = actual === PIN;
  const statusMatched = pinMatched ? JSON.parse(policy).required_status === output : null;
  return {
    synthetic: true,
    verdict: pinMatched && statusMatched === true ? "PASS" : "REJECT",
    reason: !pinMatched ? "POLICY_PIN_MISMATCH" : !statusMatched ? "OUTPUT_STATUS_MISMATCH" : "LOCAL_CHECKS_MATCH",
    policy_pin_matched: pinMatched,
    output_status_matched: statusMatched,
    policy_sha256: actual,
    expected_policy_sha256: PIN,
    output_status: output,
    buyer_authority_verified: false,
    agent_execution_verified: false,
    payment_verified: false
  };
}
if (typeof module !== "undefined" && module.exports) module.exports = {evaluate};
if (typeof document !== "undefined") {
  const run = document.getElementById("run");
  const scenario = document.getElementById("scenario");
  const result = document.getElementById("result");
  run.addEventListener("click", async () => {
    run.disabled = true;
    scenario.disabled = true;
    result.textContent = "Running local check...";
    try {
      result.textContent = JSON.stringify(await evaluate(scenario.value, globalThis.crypto), null, 2);
    } catch (error) {
      result.textContent = "No verdict: " + error.message;
    } finally {
      run.disabled = false;
      scenario.disabled = false;
    }
  });
}
