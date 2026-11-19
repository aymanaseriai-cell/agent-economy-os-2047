import {test} from 'node:test';
import assert from 'node:assert/strict';
import {prepareProofReceipt,verifyProofReceipt,RECEIPT_DOMAIN} from '../../services/agent-work-covenant-2047/proof-receipt.mjs';
const encode=b=>Buffer.from(b).toString('base64url');
const hash=async b=>Buffer.from(await crypto.subtle.digest('SHA-256',b)).toString('hex');
const contract='a'.repeat(64),proof='b'.repeat(64),task='job-42',audience='https://buyer.example';
async function fixture(){
  const pair=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
  const raw=await crypto.subtle.exportKey('raw',pair.publicKey);
  const fingerprint=await hash(raw);
  const prepared=await prepareProofReceipt({contract_id:contract,proof_id:proof,task_id:task,audience,
    nonce:encode(crypto.getRandomValues(new Uint8Array(16))),issued_at:'2026-11-19T12:00:00Z',expires_at:'2026-11-19T12:10:00Z'});
  const signature=encode(await crypto.subtle.sign('Ed25519',pair.privateKey,new TextEncoder().encode(prepared.message)));
  const input={receipt:prepared.receipt,public_key_b64url:encode(raw),signature_b64url:signature};
  const consumed=new Set();
  const opts={expected_contract_id:contract,expected_proof_id:proof,expected_task_id:task,
    expected_audience:audience,trusted_key_fingerprints:[fingerprint],
    now:new Date('2026-11-19T12:05:00Z'),claimNonce:async ({key})=>{if(consumed.has(key))return false;consumed.add(key);return true;}};
  return {prepared,input,opts,consumed};
}
test('accepts signed pinned technical statement once only, with explicit negative claims',async()=>{
 const {input,opts,prepared}=await fixture();
 assert.equal(prepared.domain,RECEIPT_DOMAIN);
 const first=await verifyProofReceipt(input,opts);
 assert.equal(first.status,'verified_technical_receipt');
 assert.equal(first.verified,true);
 assert.equal(first.signer_identity_verified,false);
 assert.equal(first.execution_provenance_verified,false);
 assert.equal(first.buyer_acceptance_verified,false);
 assert.equal(first.payment_verified,false);
 const second=await verifyProofReceipt(input,opts);
 assert.equal(second.status,'replay_detected');assert.equal(second.verified,false);
});
test('rejects tampering and different independently pinned task, audience or proof',async()=>{
 const {input,opts}=await fixture();
 assert.equal((await verifyProofReceipt({...input,receipt:{...input.receipt,proof_id:'c'.repeat(64)}},opts)).status,'signature_invalid');
 assert.equal((await verifyProofReceipt(input,{...opts,expected_task_id:'job-43'})).status,'binding_mismatch');
 assert.equal((await verifyProofReceipt(input,{...opts,expected_audience:'https://other.example'})).status,'binding_mismatch');
 assert.equal((await verifyProofReceipt(input,{...opts,expected_proof_id:'c'.repeat(64)})).status,'binding_mismatch');
});
test('fails closed for expired or future receipt',async()=>{
 const {input,opts}=await fixture();
 assert.equal((await verifyProofReceipt(input,{...opts,now:new Date('2026-11-19T12:11:00Z')})).status,'expired_or_not_yet_valid');
 assert.equal((await verifyProofReceipt(input,{...opts,now:new Date('2026-11-19T11:59:00Z')})).status,'expired_or_not_yet_valid');
});
test('fails closed when signer is not pinned or claim store unavailable/errored',async()=>{
 const {input,opts}=await fixture();
 assert.equal((await verifyProofReceipt(input,{...opts,trusted_key_fingerprints:[]})).status,'untrusted_signing_key');
 assert.equal((await verifyProofReceipt(input,{...opts,claimNonce:undefined})).status,'replay_check_unavailable');
 assert.equal((await verifyProofReceipt(input,{...opts,claimNonce:async()=>{throw Error('connection down');}})).status,'replay_check_error');
});
test('does not call claimNonce before validating signature/bindings',async()=>{
 const {input,opts}=await fixture();let calls=0;
 const result=await verifyProofReceipt({...input,signature_b64url:encode(new Uint8Array(64))},
 {...opts,claimNonce:async()=>{calls++;return true;}});
 assert.equal(result.status,'signature_invalid');assert.equal(calls,0);
});
test('rejects duplicate fields, malformed nonce, invalid clock and overlong lifetime',async()=>{
 const {input,opts}=await fixture();
 await assert.rejects(prepareProofReceipt({...input.receipt,extra:'inject'}),/invalid_receipt_fields/);
 await assert.rejects(prepareProofReceipt({...input.receipt,nonce:'x'}),/invalid_base64url|invalid_binary_length/);
 await assert.rejects(prepareProofReceipt({...input.receipt,expires_at:'2026-11-19T12:16:00Z'}),/invalid_receipt_lifetime/);
 await assert.rejects(verifyProofReceipt(input,{...opts,now:new Date('invalid')}),/invalid_clock/);
 await assert.rejects(verifyProofReceipt(input,{...opts,expected_contract_id:undefined}),/missing_trusted_binding/);
});
test('concurrent verification must produce exactly one claim with atomic store',async()=>{
 const {input,opts}=await fixture();
 const [a,b]=await Promise.all([verifyProofReceipt(input,opts),verifyProofReceipt(input,opts)]);
 assert.deepEqual([a.status,b.status].sort(),['replay_detected','verified_technical_receipt']);
});
test('integration: receipt binds to actual evaluated Work Covenant proof_id',async()=>{
  const {compileContract,evaluateContract}=await import('../../services/agent-work-covenant-2047/core.mjs');
  const c=await compileContract({task:{title:'Inspect delivered bytes',id:task},criteria:[
    {id:'output_exists',type:'artifact_exists',artifact:'out.txt'}]});
  const evaluated=await evaluateContract({...c,submission:{artifacts:[{name:'out.txt',content:'hello'}]}});
  assert.equal(evaluated.status,'local_checks_passed');
  const prepared=await prepareProofReceipt({contract_id:c.contract_id,proof_id:evaluated.proof_id,
    task_id:task,audience,nonce:encode(crypto.getRandomValues(new Uint8Array(16))),
    issued_at:'2026-11-19T12:00:00Z',expires_at:'2026-11-19T12:10:00Z'});
  assert.equal(prepared.receipt.contract_id,c.contract_id);
  assert.equal(prepared.receipt.proof_id,evaluated.proof_id);
  assert.equal(evaluated.buyer_acceptance_verified,false);
  assert.equal(evaluated.payment_verified,false);
});
