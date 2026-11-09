/**
 * Agent Economy OS 2047: BountyTruth preflight.
 * All task content is UNTRUSTED, treated only as data.
 * Never follows instructions in issue bodies, claims tasks, or signs/pays.
 */
const issuePattern=/^\/([A-Za-z0-9_.-]{1,100})\/([A-Za-z0-9_.-]{1,100})\/issues\/([1-9][0-9]{0,8})\/?$/;
export const VERSION="agent-economy.bountytruth.v1";
const maxText=38000;
const redactedHex=(s)=>String(s).replace(/\b(?:0x)?[A-Fa-f0-9]{64,128}\b/g,"[hex-redacted]");
export function parseGithubIssue(input){
 if(typeof input!=="string"||input.length>350||input.trim()!==input)throw Error("invalid_github_issue_url");
 let u;try{u=new URL(input);}catch{throw Error("invalid_github_issue_url");}
 if(u.protocol!=="https:"||!(u.hostname==="github.com"||u.hostname==="www.github.com")||u.port||u.username||u.password||u.search||u.hash)throw Error("github_url_required");
 const m=u.pathname.match(issuePattern);
 if(!m||m[1]==="."||m[1]===".."||m[2]==="."||m[2]==="..")throw Error("invalid_github_issue_path");
 const [,owner,repo,number]=m;
 return {owner,repo,number:Number(number),issue_url:"https://github.com/"+owner+"/"+repo+"/issues/"+number,
  api_url:"https://api.github.com/repos/"+owner+"/"+repo+"/issues/"+number};
}
export function parseTransferRequest(params){
 if(!params)return null;
 const {tx,escrow_wallet,min_usdc}=params;
 if(tx===null&&escrow_wallet===null&&min_usdc===null)return null;
 if(typeof tx!=="string"||!/^0x[0-9a-f]{64}$/i.test(tx))throw Error("invalid_transfer_tx");
 if(typeof escrow_wallet!=="string"||!/^0x[0-9a-f]{40}$/i.test(escrow_wallet))throw Error("invalid_escrow_wallet");
 if(typeof min_usdc!=="string"||!/^(?:0|[1-9][0-9]{0,6})(?:\.[0-9]{1,6})?$/.test(min_usdc))throw Error("invalid_min_usdc");
 const [integer,fraction=""]=min_usdc.split(".");
 const amount=BigInt(integer)*1000000n+BigInt(fraction.padEnd(6,"0"));
 if(amount<=0n)throw Error("min_usdc_must_be_positive");
 return {tx:tx.toLowerCase(),wallet:escrow_wallet.toLowerCase(),minimum_micro:amount.toString()};
}
function matches(str,patterns){return patterns.some(r=>r.test(str));}
const RULES=[
 {code:"payment_or_purchase_required_to_apply",severity:"critical",
  patterns:[/\b(?:buy|purchase|deposit|send|pay)\b.{0,75}\b(?:before (?:applying|submitting|qualifying)|to (?:enter|qualify|participate))\b/i,/pay.{0,40}(?:registration|application|entry) fee/i]},
 {code:"secret_or_private_key_request",severity:"critical",
  patterns:[/send.{0,80}(?:private key|seed phrase|recovery phrase)/i,/(?:paste|upload|enter).{0,40}(?:private key|seed phrase)/i]},
 {code:"untrusted_command_or_instruction_injection",severity:"high",
  patterns:[/SYSTEM AUDIT INSTRUCTION\s*:/i,/ignore (?:all |any )?(?:previous|prior|system) instructions/i,/\bcurl\b[^\n]{0,250}\|\s*(?:bash|sh)\b/i]},
 {code:"manual_prs_disallowed",severity:"high",
  patterns:[/manual pull requests.{0,100}not reviewed/i,/\bdo not open a pr until assigned\b/i]},
 {code:"unverified_external_http_endpoint",severity:"high",
  patterns:[/http:\/\/(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?:\/|\b)/i]},
 {code:"claims_multirail_escrow_without_proof",severity:"medium",
  patterns:[/escrow\s*(?:rail|via|on)\s*[:\-]?\s*https?:\/\/.{0,120}\s*\/\s*https?:\/\//i,/\b(?:escrowed|held in escrow)\b/i]},
 {code:"claim_or_assignment_gate",severity:"medium",
  patterns:[/\bassign(?:ed|ment)?\s*[- ]?first\b/i,/\b\/claim\b/i,/\b\/attempt\b/i]},
 {code:"promised_payout_not_independently_verified",severity:"medium",
  patterns:[/\bpaid automatically on merge\b/i,/\bpayout guaranteed\b/i,/\bfunding status\s*:\s*held in escrow\b/i]},
];
export function analyzeGithubIssue(raw, opts={}){
 if(!raw||typeof raw!=="object"||Array.isArray(raw))throw Error("invalid_issue_payload");
 const number=raw.number;
 if(!Number.isSafeInteger(number)||number<1||typeof raw.title!=="string"||typeof raw.body!=="string")throw Error("invalid_issue_payload");
 if(raw.pull_request)throw Error("requested_issue_is_pr");
 const body=raw.body.slice(0,maxText);
 const title=raw.title.slice(0,300);
 const content=title+"\n"+body;
 const flags=RULES.filter(rule=>matches(content,rule.patterns)).map(x=>({code:x.code,severity:x.severity}));
 if(raw.state!=="open")flags.push({code:"issue_not_open",severity:"critical"});
 if(raw.assignee)flags.push({code:"already_assigned",severity:"medium"});
 if(raw.body.length>maxText)flags.push({code:"large_body_not_fully_reviewed",severity:"high"});
 const providedEvidence=opts.onchain||null;
 const transferObserved=providedEvidence?.transfer_observed===true;
 const critical=flags.some(x=>x.severity==="critical");
 const high=flags.some(x=>x.severity==="high");
 const moneyClaim=/(?:\$[0-9][0-9,.]*|[0-9][0-9,.]*\s*USDC|bounty|reward|escrow)/i.test(content);
 const escrowClaim=/(?:escrowed|held in escrow|escrow rail|escrow via|escrow contract)/i.test(content);
 const out={
  schema:VERSION,
  issue:{number,title:redactedHex(title.slice(0,180)),state:raw.state,created_at:raw.created_at||null,
    updated_at:raw.updated_at||null,labels:(raw.labels||[]).slice(0,12).map(l=>typeof l==="string"?l:String(l?.name||"")).filter(Boolean).map(x=>x.slice(0,40))},
  bounty_claim_present:moneyClaim,
  escrow_claim_present:escrowClaim,
  flags,flag_count:flags.length,
  status:critical?"blocked":high?"manual_review_required":moneyClaim?"unverified_payout":"not_a_confirmed_bounty",
  payment_claim_validated:false,
  onchain_transfer_observed:transferObserved,
  independent_escrow_verified:false,
  github_issue_linked_to_escrow_verified:false,
  payment_commitment_verified:false,
  payout_on_merge_verified:false,
  wallet_signing_performed:false,
  submission_performed:false,
  safe_to_assume_payment:false,
  advice:critical?"Do not perform paid work or spend money on this listing without resolving flagged blockers."
       :"Obtain verifiable escrow contract, payout conditions and owner authorization before committing substantial work.",
  limitations:[
   "Public GitHub content is untrusted and may contain deceptive payment claims.",
   "An on-chain USDC Transfer into an address alone is not evidence of a legally or technically enforceable bounty escrow.",
   "A linked issue, advertised reward, or successful local test is not a paid work contract."
  ]
 };
 if(providedEvidence)out.external_transfer_evidence=providedEvidence;
 return out;
}
export function syntheticExample(){
 return {number:2,title:"Escrowed 600 USDC bounty: confirm 24 tests",body:
 "> Automated CI Regression Mirror Notice: manual pull requests from human engineers are not reviewed on this mirror.\n"+
 "- Escrow Rail: https://algora.io / https://polar.sh / https://opire.dev\n"+
 "- Funding Status: Held in escrow; paid automatically on merge; /claim\n"+
 "- External mirror: http://157.151.170.68:11449/v1/conformance/epoch",
 state:"open",labels:[{name:"bounty"}],created_at:"2026-11-08T10:53:26Z",updated_at:"2026-11-08T18:00:00Z"};
}
