import {test} from 'node:test';
import assert from 'node:assert/strict';
import {checkUsdcTransfer} from '../../services/agent-bounty-truth-gate/onchain.mjs';
const tok="0x833589fcD6eDb6e08f4c7c32d4f71b54bdA02913";
const topic="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
const wallet="0x"+"b".repeat(40),tx="0x"+"a".repeat(64);
const opts={tx,wallet,minimum_micro:"5000000"};
function mock({amount=5000000n,confirmations=15,correct=true,wrongChain=false}={}){
 return async function(url,config){
   const {method}=JSON.parse(config.body);
   let result;
   if(method==="eth_chainId")result=wrongChain?"0x1":"0x2105";
   else if(method==="eth_blockNumber")result="0x"+(1000+confirmations-1).toString(16);
   else if(method==="eth_getTransactionReceipt")result={
     status:"0x1",transactionHash:tx,blockHash:correct?"0x"+"d".repeat(64):"0x"+"c".repeat(64),blockNumber:"0x3e8",
     logs:[{address:tok,logIndex:"0x1",topics:[topic,"0x"+"1".repeat(64),"0x"+wallet.slice(2).padStart(64,"0")],data:"0x"+amount.toString(16).padStart(64,"0")}]
   };
   return new Response(JSON.stringify({jsonrpc:"2.0",id:1,result}),{status:200,headers:{"content-type":"application/json"}});
 }
}
test("two provider quorum reports transfer but NEVER proves escrow",async()=>{
 const r=await checkUsdcTransfer(opts,{providers:["p1","p2","p3"],fetcher:mock()});
 assert.equal(r.transfer_observed,true);
 assert.equal(r.amount_received_micro_usdc,"5000000");
 assert.equal(r.enforced_bounty_payout_verified,false);
 assert.equal(r.independently_verified_escrow_contract,false);
 assert.equal(r.issue_to_payment_link_verified,false);
});
test("insufficient transfer rejects",async()=>{
 const r=await checkUsdcTransfer(opts,{providers:["p1","p2"],fetcher:mock({amount:100n})});
 assert.equal(r.transfer_observed,false);
});
test("insufficient confirmations rejects",async()=>{
 const r=await checkUsdcTransfer(opts,{providers:["p1","p2"],fetcher:mock({confirmations:3})});
 assert.equal(r.transfer_observed,false);
});
test("wrong chain rejects",async()=>{
 const r=await checkUsdcTransfer(opts,{providers:["p1","p2"],fetcher:mock({wrongChain:true})});
 assert.equal(r.transfer_observed,false);
});
test("disagreeing provider fingerprint rejects",async()=>{
 const fetcher=async (url,request)=>{
  const f=mock({correct:url==="p1"});return f(url,request);
 };
 const r=await checkUsdcTransfer(opts,{providers:["p1","p2"],fetcher});
 assert.equal(r.transfer_observed,false);
});
test("provider network failures never become false proof",async()=>{
 const f=async()=>{throw Error("offline")};
 const r=await checkUsdcTransfer(opts,{providers:["p1","p2"],fetcher:f});
 assert.equal(r.transfer_observed,false);
});
