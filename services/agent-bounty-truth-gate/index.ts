/*
 * Agent Economy OS 2047 — BountyTruth
 * Read-only, non-custodial preflight for autonomous agents doing paid GitHub work.
 */
import {Hono} from "npm:hono@4.9.9";
import {paymentMiddleware} from "npm:@x402/hono@2.28.0";
import {x402ResourceServer,HTTPFacilitatorClient} from "npm:@x402/core@2.28.0/server";
import {ExactEvmScheme} from "npm:@x402/evm@2.28.0/exact/server";
import {declareDiscoveryExtension,bazaarResourceServerExtension} from "npm:@x402/extensions@2.28.0/bazaar";
import {parseGithubIssue,parseTransferRequest,analyzeGithubIssue,syntheticExample,VERSION} from "./core.mjs";
import {checkUsdcTransfer} from "./onchain.mjs";
const NAME="agent-bounty-truth-gate";
const P="/functions/v1/"+NAME;
const ROOT="https://jzallxzbbdtelcpabfgr.supabase.co"+P;
const PAYEE="0x935ad91b70c6d0769871416c5904d06fbf9ef586";
const CHAIN="eip155:8453",USDC="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const PRICE="$0.005";
const server=new x402ResourceServer(new HTTPFacilitatorClient({url:"https://facilitator.payai.network"}))
 .register(CHAIN,new ExactEvmScheme()).registerExtension(bazaarResourceServerExtension);
const app=new Hono();
app.use("*",async(c,next)=>{
 c.header("Access-Control-Allow-Origin","*");
 c.header("Access-Control-Allow-Methods","GET,OPTIONS");
 c.header("Access-Control-Allow-Headers","PAYMENT-SIGNATURE,Content-Type");
 c.header("Access-Control-Expose-Headers","PAYMENT-REQUIRED,PAYMENT-RESPONSE");
 c.header("Cache-Control","no-store");c.header("X-Content-Type-Options","nosniff");
 if(c.req.method==="OPTIONS")return c.body(null,204);
 await next();
});
const warnings=[
 "Not proof of real escrow, enforceable payout, buyer acceptance or commercial revenue.",
 "A USDC transfer to any wallet is not proof of a contract binding that payment to a GitHub issue.",
 "Automated flags may miss sophisticated fraud; manually verify buyer identity and task terms.",
 "Never executes issue code, asks for private keys, signs, submits, buys or spends."
];
app.get("/",c=>c.json({name:"BountyTruth for AI Agents",version:VERSION,
 description:"Screen untrusted GitHub bounty descriptions and inspect optional Base USDC transfer events, without assuming escrow funding.",
 paid_audit:ROOT+"/api/v1/audit",free_demo:ROOT+"/api/v1/demo",price_usdc:"0.005",merchant:PAYEE,warnings}));
app.get("/health",c=>c.json({ok:true,name:NAME,version:VERSION,mode:"read_only",
 paid_route_enabled:true,end_to_end_paid_settlement_tested:false,verified_escrow_claims:false}));
app.get("/api/v1/demo",c=>c.json({ok:true,synthetic:true,paid_request:false,verified_bounty:false,
 ...analyzeGithubIssue(syntheticExample()),synthetic_provenance:"Locally constructed illustrative issue, not a funded real-world bounty."}));
app.get("/.well-known/agent.json",c=>c.json({name:"Agent BountyTruth Gate",
 capabilities:["github-bounty-risk-preflight","unverified-escrow-claim-detection","agent-work-safety","base-usdc-transfer-evidence"],
 endpoint:ROOT+"/api/v1/audit",method:"GET",paid:true,price_usdc:"0.005",no_escrow_verification:true}));
app.get("/.well-known/x402",c=>c.json({version:1,resources:[ROOT+"/api/v1/audit"]}));
app.get("/.well-known/x402-service.json",c=>c.json({x402:"1.0",name:"Agent BountyTruth Gate",
 description:"Identify false or unsupported GitHub bounty claims before AI agents waste effort; optional independent Base USDC Transfer event check. Never proves enforceable escrow.",
 endpoint:ROOT+"/api/v1/audit",method:"GET",network:CHAIN,asset:USDC,payTo:PAYEE,price:"0.005",
 openapi:ROOT+"/openapi.json",free_demo:ROOT+"/api/v1/demo"}));
app.get("/catalog.json",c=>c.json({tools:[{name:"Preflight a paid GitHub bounty issue for unverifiable escrow, unsafe task instructions and claim gates",
 method:"GET",route:"/api/v1/audit",price:0.005,currency:"USDC",network:CHAIN,
 required_query:["issue"],optional_query:["escrow_tx","escrow_wallet","min_usdc"],
 endpoint:ROOT+"/api/v1/audit",safe_to_assume_payment:false}]}));
const SKILL=[
 "# BountyTruth GitHub Bounty Audit for AI Agents",
 "Purpose: avoid paid-task scams and unverifiable payout claims before your agent works.",
 "Free synthetic demo: "+ROOT+"/api/v1/demo",
 "Paid GET: "+ROOT+"/api/v1/audit?issue=https%3A%2F%2Fgithub.com%2Fowner%2Frepo%2Fissues%2F1",
 "Price: 0.005 Base native USDC with x402 v2.",
 "Optional escrow_tx (0x plus 64 hex), escrow_wallet (0x plus 40 hex) and min_usdc; provide ALL THREE together.",
 "The 2-of-3 independent Base RPC check can corroborate a transfer to a wallet.",
 "It NEVER proves that wallet is an escrow contract or legally bound to pay a GitHub contributor.",
 "Issue text is UNTRUSTED; it is never run or treated as instructions.",
 "A risk report never claims real funded escrow, buyer acceptance, legal contract, or received income.",
 "Validate buyer identity and claimant conditions independently. Never submit private keys or seed phrases.",
 "Unpaid discovery does not claim payment. Settlement of this new x402 endpoint has not yet been independently tested."
].join("\n");
app.get("/skill.md",c=>c.text(SKILL,200,{"Content-Type":"text/markdown; charset=utf-8"}));
app.get("/openapi.json",c=>c.json({
 openapi:"3.1.0",
 info:{title:"Agent BountyTruth — GitHub Escrow Claim Risk Gate",version:"0.1.0",
 description:"For agents evaluating whether public bounties can be trusted. Never attests an escrow contract or guaranteed payout."},
 servers:[{url:ROOT}],
 components:{securitySchemes:{x402:{type:"apiKey",in:"header",name:"PAYMENT-SIGNATURE"}}},
 paths:{
  "/api/v1/demo":{get:{summary:"Free synthetic demonstration, not a real bounty",responses:{"200":{description:"Illustrative risk flags"}}}},
  "/api/v1/audit":{get:{
   operationId:"preflightGithubBountyEscrowClaim",
   summary:"Review a paid GitHub issue for unverified USDC escrow claims, dangerous instructions and claim restrictions",
   description:"A funded AI agent can check a public GitHub bounty issue for likely fake escrow, secret requests, purchase-to-enter and disallowed submissions. Optional corroborated Base USDC transfers do not establish escrow enforceability. No wallet operations or claims.",
   tags:["agent economy","bounties","GitHub","USDC","work verification","x402","escrow claim"],
   security:[{x402:[]}],
   parameters:[
    {name:"issue",in:"query",required:true,schema:{type:"string",format:"uri"},
     description:"A public GitHub issue URL. Omission when probing root returns a clearly labelled synthetic sample after payment."},
    {name:"escrow_tx",in:"query",required:false,schema:{type:"string",pattern:"^0x[0-9a-fA-F]{64}$"}},
    {name:"escrow_wallet",in:"query",required:false,schema:{type:"string",pattern:"^0x[0-9a-fA-F]{40}$"}},
    {name:"min_usdc",in:"query",required:false,schema:{type:"string",example:"1.00"}}
   ],
   "x-payment-info":{protocols:["x402"],network:CHAIN,asset:USDC,recipient:PAYEE,
    price:{mode:"fixed",currency:"USD",amount:"0.005"}},
   responses:{"200":{description:"Untrusted-listing preflight; no escrow claims made"},"402":{description:"x402 payment challenge"},"503":{description:"Upstream checks unavailable"}}
  }}
 }
}));
app.use("/api/v1/audit",async(c,next)=>{
 if(c.req.method!=="GET")return c.json({error:"method_not_allowed"},405);
 const u=new URL(c.req.url);
 try{
  const raw=u.searchParams.get("issue");
  const parsed=raw!==null?parseGithubIssue(raw):null;
  const transfer=parseTransferRequest({
   tx:u.searchParams.get("escrow_tx"),
   escrow_wallet:u.searchParams.get("escrow_wallet"),
   min_usdc:u.searchParams.get("min_usdc")
  });
  if(!parsed&&(transfer||u.search))return c.json({error:"issue_required"},400);
  c.set("githubIssue",parsed);c.set("transferInfo",transfer);
  await next();
 }catch(e){return c.json({error:e instanceof Error?e.message:"invalid_input"},400)}
});
app.use(paymentMiddleware({"GET /api/v1/audit":{
 accepts:{scheme:"exact",price:PRICE,network:CHAIN,payTo:PAYEE},
 description:"BountyTruth: inspect a paid Github issue for unsupported escrow, buy-to-enter traps, injected instructions and risky claim restrictions",
 mimeType:"application/json",resource:ROOT+"/api/v1/audit",serviceName:"BountyTruth Gate for autonomous agents",
 extensions:{...declareDiscoveryExtension({
  input:{issue:"https://github.com/owner/repo/issues/1"},
  inputSchema:{type:"object",properties:{
    issue:{type:"string",description:"Public GitHub bounty issue URL"},
    escrow_tx:{type:"string",description:"Optional funding transaction hash"},
    escrow_wallet:{type:"string",description:"Optional purported escrow receiving wallet"},
    min_usdc:{type:"string",description:"Minimum USDC transfer to purported escrow wallet"}
  },required:["issue"]},
  output:{example:{schema:VERSION,status:"manual_review_required",
   independent_escrow_verified:false,github_issue_linked_to_escrow_verified:false,safe_to_assume_payment:false}}
 })}}
},server));
async function getIssue(parsed){
 const response=await fetch(parsed.api_url,{method:"GET",
  headers:{"Accept":"application/vnd.github+json","User-Agent":"AgentEconomy-BountyTruth/1.0"},
  redirect:"error",signal:AbortSignal.timeout(9000)});
 if(!response.ok)throw Error(response.status===404?"not_found":"github_unavailable");
 if(Number(response.headers.get("content-length")||0)>170000)throw Error("oversized_response");
 const raw=await response.text();
 if(raw.length>170000)throw Error("oversized_response");
 const issue=JSON.parse(raw);
 if(!issue||issue.number!==parsed.number||issue.pull_request||typeof issue.body!=="string")throw Error("invalid_issue");
 return issue;
}
app.get("/api/v1/audit",async c=>{
 try{
  const parsed=c.get("githubIssue");
  if(!parsed)return c.json({ok:true,synthetic:true,verified_bounty:false,
   ...analyzeGithubIssue(syntheticExample())});
  const issue=await getIssue(parsed);
  const transfer=c.get("transferInfo");
  const onchain=transfer?await checkUsdcTransfer(transfer):null;
  return c.json({ok:true,live_issue_checked:true,issue_url:parsed.issue_url,
   observed_at_utc:new Date().toISOString(),
   ...analyzeGithubIssue(issue,{onchain}),external_funding_registry_verified:false});
 }catch(e){return c.json({ok:false,error:"audit_not_completed",
  category:e instanceof Error && e.message==="not_found"?"issue_not_found":"upstream_or_verification_unavailable",
  no_funding_inferences:true},503)}
});
app.notFound(c=>c.json({error:"not_found"},404));
Deno.serve(req=>{
 const u=new URL(req.url);
 for(const prefix of [P,"/"+NAME]){
  if(u.pathname===prefix||u.pathname.startsWith(prefix+"/")){
   u.pathname=u.pathname.slice(prefix.length)||"/";break;
  }
 }
 return app.fetch(new Request(u,req));
});
