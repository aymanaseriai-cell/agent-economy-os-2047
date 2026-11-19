/**
 * Offline proof-carrying work demonstration.
 * Uses synthetic data only; no network, wallet, payment, keys or credentials.
 */
import {pathToFileURL} from "node:url";
import {compileContract, evaluateContract, digest} from "../../services/agent-work-covenant-2047/core.mjs";

export async function runDemo() {
  const artifactName="report.json";
  const artifact='{"status":"ready","count":3}';
  const expectedHash=await digest(artifact);
  const compiled=await compileContract({
    task:{id:"offline_demo",title:"Produce a small machine-readable report"},
    criteria:[
      {id:"report_present",type:"artifact_exists",artifact:artifactName},
      {id:"hash_matches",type:"artifact_sha256",artifact:artifactName,expected_sha256:expectedHash},
      {id:"status_ready",type:"json_pointer_equals",artifact:artifactName,pointer:"/status",expected:"ready"}
    ]
  });
  const envelope=(content)=>({
    contract:compiled.contract,
    contract_id:compiled.contract_id,
    submission:{artifacts:[{name:artifactName,content}]}
  });
  const valid=await evaluateContract(envelope(artifact));
  const changed=await evaluateContract(envelope('{"status":"ready","count":4}'));
  if(valid.status!=="local_checks_passed" || changed.status!=="local_checks_failed") {
    throw new Error("offline_demo_regression");
  }
  if(valid.payment_verified!==false || valid.buyer_acceptance_verified!==false ||
     changed.payment_verified!==false || changed.buyer_acceptance_verified!==false) {
    throw new Error("trust_boundary_regression");
  }
  return {
    demo:"agent-economy.offline-work-covenant.v1",
    synthetic_only:true,
    contract_id:compiled.contract_id,
    valid:{status:valid.status,passed:valid.passed,total:valid.total,proof_id:valid.proof_id},
    tampered:{status:changed.status,failed_check_ids:changed.results.filter(c=>!c.pass).map(c=>c.id)},
    buyer_acceptance_verified:false,
    payment_verified:false,
    limitation:"Only supplied artifact bytes and caller-defined checks are verified; no independent execution, buyer approval or payment is proven."
  };
}
if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
  runDemo().then(result=>console.log(JSON.stringify(result,null,2))).catch(error=>{
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode=1;
  });
}
