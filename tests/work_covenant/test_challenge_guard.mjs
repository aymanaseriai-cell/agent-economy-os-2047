import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileContract,evaluateContract} from '../../services/agent-work-covenant-2047/core.mjs';
import {CHALLENGE_SCHEMA,signingMessage,verifyChallengeBoundWork} from '../../services/agent-work-covenant-2047/challenge_guard.mjs';
const b64 = a=>Buffer.from(a).toString('base64url');
async function fixture({withSelfReport=false}={}) {
  const contract = await compileContract({task:{title:'Deliver a report',id:'request-1'},criteria:[
    {id:'present',type:'artifact_exists',artifact:'report.txt'},
    ...(withSelfReport?[{id:'tests',type:'test_summary',suite:'unit',min_passed:1,max_failed:0}]:[])
  ]});
  const submission = {artifacts:[{name:'report.txt',content:'checked value'}],
    ...(withSelfReport?{reported_tests:[{suite:'unit',passed:1,failed:0}]}:{})};
  const proof = await evaluateContract({...contract,submission});
  const pair = await crypto.subtle.generateKey({name:'Ed25519'},true,['sign','verify']);
  const pk = b64(await crypto.subtle.exportKey('raw',pair.publicKey));
  const envelope = {schema:CHALLENGE_SCHEMA,audience:'buyer.example/v1',task_id:'request-1',
    contract_id:contract.contract_id,proof_id:proof.proof_id,
    nonce:'AbCdEfGhIjKlMnOpQrStUv01234567',
    issued_at:'2026-11-19T12:00:00Z',expires_at:'2026-11-19T12:05:00Z'};
  const sign = async env=>b64(await crypto.subtle.sign('Ed25519',pair.privateKey,new TextEncoder().encode(signingMessage(env))));
  const ledger = new Set();
  const reserveReplayKey = async key=>{if(ledger.has(key))return false;ledger.add(key);return true};
  const input = {contract:contract.contract,contract_id:contract.contract_id,submission,
    envelope,signature_b64url:await sign(envelope),trusted_public_key_b64url:pk,
    expected_audience:envelope.audience,expected_task_id:envelope.task_id,
    expected_nonce:envelope.nonce,reserveReplayKey,now_ms:Date.parse('2026-11-19T12:01:00Z')};
  return {input,sign,ledger};
}
test('accepts signature and independently re-evaluated bytes only once',async()=>{
  const {input}=await fixture();const receipt=await verifyChallengeBoundWork(input);
  assert.equal(receipt.status,'single_use_proof_reference_accepted');
  assert.equal(receipt.payment_verified,false);
  assert.equal(receipt.buyer_acceptance_verified,false);
  await assert.rejects(verifyChallengeBoundWork(input),/replay_detected_or_store_unavailable/);
});
test('rejects wrong audience, task or pinned challenge nonce',async()=>{
  const {input}=await fixture();
  for(const prop of ['expected_audience','expected_task_id','expected_nonce'])
    await assert.rejects(verifyChallengeBoundWork({...input,[prop]:'wrong'}),/challenge_context_mismatch/);
});
test('rejects altered bytes even when signed envelope matches old proof',async()=>{
  const {input}=await fixture();
  const tampered={...input,submission:{artifacts:[{name:'report.txt',content:'attacker changed this'}]}};
  await assert.rejects(verifyChallengeBoundWork(tampered),/challenge_proof_mismatch/);
});
test('rejects signature forgery without reserving a replay key',async()=>{
  const {input,ledger}=await fixture();
  await assert.rejects(verifyChallengeBoundWork({...input,signature_b64url:b64(new Uint8Array(64))}),/invalid_challenge_signature/);
  assert.equal(ledger.size,0);
});
test('rejects expiration and future issued timestamp',async()=>{
  const {input}=await fixture();
  await assert.rejects(verifyChallengeBoundWork({...input,now_ms:Date.parse('2026-11-19T12:06:00Z')}),/challenge_not_current/);
  await assert.rejects(verifyChallengeBoundWork({...input,now_ms:Date.parse('2026-11-19T11:59:59Z')}),/challenge_not_current/);
});
test('rejects self-reported tests as independent evidence',async()=>{
  const {input}=await fixture({withSelfReport:true});
  await assert.rejects(verifyChallengeBoundWork(input),/self_report_not_independent_evidence/);
});
test('cannot reuse same proof by re-signing it with a new nonce',async()=>{
  const {input,sign}=await fixture();await verifyChallengeBoundWork(input);
  const env={...input.envelope,nonce:'0987654321vUtSrQpOnMlKjIhGfEdC'};
  const changed={...input,envelope:env,expected_nonce:env.nonce,signature_b64url:await sign(env)};
  await assert.rejects(verifyChallengeBoundWork(changed),/replay_detected_or_store_unavailable/);
});
test('fails closed when ledger is absent or unavailable',async()=>{
  const {input}=await fixture();
  await assert.rejects(verifyChallengeBoundWork({...input,reserveReplayKey:undefined}),/atomic_replay_ledger_required/);
  await assert.rejects(verifyChallengeBoundWork({...input,reserveReplayKey:async()=>{throw Error('offline')}}),/replay_store_unavailable/);
});
test('rejects invalid 11-minute windows and extraneous signed properties',async()=>{
  const {input}=await fixture();
  assert.throws(()=>signingMessage({...input.envelope,expires_at:'2026-11-19T12:11:01Z'}),/invalid_challenge_window/);
  assert.throws(()=>signingMessage({...input.envelope,approval:true}),/invalid_envelope/);
});
test('concurrent claims are serialized by an atomic ledger',async()=>{
  const {input}=await fixture();
  const settled=await Promise.allSettled([verifyChallengeBoundWork(input),verifyChallengeBoundWork(input)]);
  assert.equal(settled.filter(x=>x.status==='fulfilled').length,1);
  assert.equal(settled.filter(x=>x.status==='rejected').length,1);
});
