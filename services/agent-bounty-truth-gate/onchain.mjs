/**
 * Read-only Base USDC Transfer event corroboration.
 * Observing a transfer DOES NOT prove the wallet is a true escrow
 * contract or that the transfer belongs to any specific GitHub issue.
 */
const TOKEN="0x833589fcD6eDb6e08f4c7c32d4f71b54bdA02913".toLowerCase();
const TOPIC="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
export const BASE_PROVIDERS=["https://mainnet.base.org","https://base-rpc.publicnode.com","https://base.drpc.org"];
const toHex=v=>BigInt(v).toString(16);
export class ChainError extends Error {}
async function rpc(url,method,params,fetcher,timeoutMs){
 const reqBody=JSON.stringify({jsonrpc:"2.0",id:1,method,params});
 const res=await fetcher(url,{method:"POST",headers:{"Content-Type":"application/json","Accept":"application/json"},
  body:reqBody,redirect:"error",signal:AbortSignal.timeout(timeoutMs)});
 if(!res.ok)throw new ChainError("provider_http_"+res.status);
 if(Number(res.headers.get("content-length")||0)>750000)throw new ChainError("provider_response_oversized");
 const text=await res.text();
 if(text.length>750000)throw new ChainError("provider_response_oversized");
 const obj=JSON.parse(text);
 if(!obj||obj.error||!Object.hasOwn(obj,"result"))throw new ChainError("provider_rpc_error");
 return obj.result;
}
function inspectTransfer(receipt,escrowWallet,minimumMicro,head){
 if(!receipt||typeof receipt!=="object"||receipt.status!=="0x1")return null;
 if(!/^0x[0-9a-f]{64}$/i.test(receipt.blockHash||"")||
    !/^0x[0-9a-f]+$/i.test(receipt.blockNumber||"") ||
    !Array.isArray(receipt.logs)||receipt.logs.length>512 ||
    !/^0x[0-9a-f]+$/i.test(head||""))return null;
 const confirmations=BigInt(head)-BigInt(receipt.blockNumber)+1n;
 if(confirmations<12n)return null;
 let total=0n;const matches=[];
 for(const log of receipt.logs){
  if(!log||String(log.address).toLowerCase()!==TOKEN||
    String(log.topics?.[0]).toLowerCase()!==TOPIC||
    !Array.isArray(log.topics)||log.topics.length!==3||
    String(log.topics[2]).toLowerCase()!=="0x"+escrowWallet.toLowerCase().slice(2).padStart(64,"0"))continue;
  if(!/^0x[0-9a-f]{64}$/i.test(log.data||""))continue;
  const amount=BigInt(log.data);
  if(amount===0n)continue;
  total+=amount;
  matches.push({log_index:String(log.logIndex||"0x0").toLowerCase(),amount_micro:amount.toString()});
 }
 if(total<BigInt(minimumMicro))return null;
 const fingerprint=JSON.stringify({
  status:receipt.status,hash:String(receipt.blockHash).toLowerCase(),
  height:BigInt(receipt.blockNumber).toString(),to:escrowWallet.toLowerCase(),
  amounts:matches.sort((a,b)=>a.log_index.localeCompare(b.log_index)),
  total:total.toString()
 });
 return {fingerprint,total_micro:total.toString(),confirmation_depth:confirmations.toString(),
  block_hash:String(receipt.blockHash).toLowerCase(),
  block_number:BigInt(receipt.blockNumber).toString(),
  matched_transfer_events:matches.length};
}
export async function checkUsdcTransfer(params, options={}){
 const providers=options.providers||BASE_PROVIDERS,fetcher=options.fetcher||fetch,timeoutMs=options.timeoutMs||7000;
 if(!Array.isArray(providers)||providers.length<2||providers.length>4)throw new ChainError("invalid_provider_configuration");
 const responses=await Promise.all(providers.map(async provider=>{
  try{
   const [chain,receipt,head]=await Promise.all([
    rpc(provider,"eth_chainId",[],fetcher,timeoutMs),
    rpc(provider,"eth_getTransactionReceipt",[params.tx],fetcher,timeoutMs),
    rpc(provider,"eth_blockNumber",[],fetcher,timeoutMs)
   ]);
   if(chain!=="0x2105"||receipt?.transactionHash?.toLowerCase()!==params.tx.toLowerCase())return null;
   return inspectTransfer(receipt,params.wallet,params.minimum_micro,head);
  }catch{return null;}
 }));
 const valid=responses.filter(Boolean);
 const groups=new Map();
 for(const item of valid){const a=groups.get(item.fingerprint)||[];a.push(item);groups.set(item.fingerprint,a);}
 const winner=[...groups.values()].sort((a,b)=>b.length-a.length)[0]||[];
 const transfer_observed=winner.length>=2;
 return {
  transfer_observed,
  rpc_consensus_met:transfer_observed,
  quorum_required:2,
  providers_checked:providers.length,
  providers_with_matching_transfer:transfer_observed?winner.length:0,
  amount_received_micro_usdc:transfer_observed?winner[0].total_micro:null,
  block_hash:transfer_observed?winner[0].block_hash:null,
  confirmation_depth_at_least_12:transfer_observed,
  independently_verified_escrow_contract:false,
  enforced_bounty_payout_verified:false,
  issue_to_payment_link_verified:false,
  caveat:"USDC transfer to an address is not proof that an escrow contract exists or enforces an issue payout."
 };
}
