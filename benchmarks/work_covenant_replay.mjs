/**
 * Reproducible local security-control comparison, NOT a distributed-store
 * benchmark or a throughput/SLA claim. Synthetic artifacts only.
 * Node 24, no external packages or network.
 */
import {performance} from "node:perf_hooks";
import {compileContract,evaluateContract} from "../services/agent-work-covenant-2047/core.mjs";
import {evaluateOnce} from "../services/agent-work-covenant-2047/replay_guard.mjs";

const attempts=50;
const contract=await compileContract({
  task:{id:"bench-one-time-task-001",title:"Return test JSON"},
  criteria:[{id:"output",type:"artifact_exists",artifact:"result.json"}]
});
const envelope={contract:contract.contract,contract_id:contract.contract_id,
  submission:{artifacts:[{name:"result.json",content:'{"ok":true}'}]}};
const now=Date.parse("2026-11-19T12:00:00Z");
const used=new Set();
const trusted={
  expected_contract_id:contract.contract_id,
  expected_task_id:"bench-one-time-task-001",
  audience_id:"benchmark-buyer",
  challenge_nonce:"cd".repeat(16),
  issued_at:"2026-11-19T11:59:00Z",
  expires_at:"2026-11-19T12:04:00Z",
  now_ms:now,
  consume_once:async key=>{
    if(used.has(key)) return false;
    used.add(key);
    return true;
  }
};
let baselineAccepted=0,guardAccepted=0,guardDuplicate=0;
const startBaseline=performance.now();
for(let i=0;i<attempts;i++) {
  const r=await evaluateContract(envelope);
  if(r.status==="local_checks_passed") baselineAccepted++;
}
const baselineMs=performance.now()-startBaseline;
const startGuard=performance.now();
for(let i=0;i<attempts;i++) {
  const r=await evaluateOnce(envelope,trusted);
  if(r.accepted) guardAccepted++;
  else if(r.reason==="duplicate_contract_proof") guardDuplicate++;
}
const guardMs=performance.now()-startGuard;
const record={
  schema:"agent-economy.replay-control-benchmark.v1",
  sample:"synthetic",attempts,
  baseline_stateless_checks_accepted:baselineAccepted,
  guard_first_acceptances:guardAccepted,
  guard_replay_rejections:guardDuplicate,
  baseline_loop_ms:+baselineMs.toFixed(3),
  guard_loop_ms:+guardMs.toFixed(3),
  store:"test-only in-memory Set; no durability, network, locks or concurrency",
  warning:"Not a real-world performance or security rate and not proof of buyer acceptance"
};
console.log(JSON.stringify(record));
if(baselineAccepted!==attempts || guardAccepted!==1 ||
   guardDuplicate!==attempts-1) process.exitCode=1;
