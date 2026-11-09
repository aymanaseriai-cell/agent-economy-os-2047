import {createServer, type IncomingMessage, type ServerResponse} from 'node:http';
import {readFileSync, existsSync, mkdirSync} from 'node:fs';
import {dirname} from 'node:path';
import {randomUUID} from 'node:crypto';
import {Store} from './store.ts';
import {hash,fingerprint,normalizeGithub,normalizeLinear,signatureValid,allowedIssue,ghMarker,linearMarker,hasMarker,stripMarker,sourceWins, type Issue, type Provider} from './core.ts';

type Config={repo:string,team:string,githubToken:string,linearToken:string,ghSecret:string,linearSecret:string,dbPath:string,port:number,dryRun:boolean,linearDone:string,linearOpen:string};
export const configFromEnv=():Config=>({
 repo:process.env.GITHUB_REPO||'',team:process.env.LINEAR_TEAM_ID||'',githubToken:process.env.GITHUB_TOKEN||'',linearToken:process.env.LINEAR_API_KEY||'',ghSecret:process.env.GITHUB_WEBHOOK_SECRET||'',linearSecret:process.env.LINEAR_WEBHOOK_SECRET||'',dbPath:process.env.SQLITE_PATH||'./state/sync.sqlite',port:Number(process.env.PORT||3000),dryRun:process.env.DRY_RUN==='true',linearDone:process.env.LINEAR_DONE_STATE_ID||'',linearOpen:process.env.LINEAR_OPEN_STATE_ID||''
});
const validRepo=(repo:string)=>/^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/.test(repo);
const strictConfig=(c:Config)=>{if(!validRepo(c.repo)||!c.team||!c.githubToken||!c.linearToken||!c.ghSecret||!c.linearSecret)throw Error('Set repo, team, tokens and both independent webhook secrets');if(!Number.isInteger(c.port)||c.port<1||c.port>65535)throw Error('invalid port');};
export type Adapter={get:(source:Provider,id:string)=>Promise<Issue>,create:(source:Provider,origin:Issue)=>Promise<Issue>,update:(source:Provider,target:Issue,origin:Issue)=>Promise<Issue>,findByMarker:(source:Provider,origin:Issue)=>Promise<Issue|undefined>,list:(source:Provider)=>Promise<Issue[]>};

async function httpJson(url:string,token:string,opts:RequestInit={}):Promise<any>{
 const r=await fetch(url,{...opts,headers:{'Accept':'application/json','Content-Type':'application/json',...opts.headers,Authorization:token},signal:AbortSignal.timeout(12500)});
 const response=await r.text();let data:any;try{data=JSON.parse(response)}catch{throw Error(`non_json_api_${r.status}`)}
 if(!r.ok)throw Error(`remote_http_${r.status}:${JSON.stringify(data).slice(0,230)}`);return data;
}
export class RealAdapter implements Adapter{
 c:Config;constructor(c:Config){this.c=c;}
 gh(path:string,opts:RequestInit={}){return httpJson(`https://api.github.com/repos/${this.c.repo}${path}`,`Bearer ${this.c.githubToken}`,{...opts,headers:{'X-GitHub-Api-Version':'2022-11-28',...opts.headers}});}
 async linear(query:string,variables:any={}){const r=await httpJson('https://api.linear.app/graphql',this.c.linearToken,{method:'POST',body:JSON.stringify({query,variables})});if(r.errors?.length)throw Error('linear_graphql_error:'+JSON.stringify(r.errors).slice(0,240));return r.data;}
 async get(source:Provider,id:string):Promise<Issue>{
  if(source==='github'){
   const n=Number(id.split('#').at(-1));if(!Number.isSafeInteger(n))throw Error('invalid_gh_issue_id');
   return normalizeGithub(await this.gh(`/issues/${n}`),this.c.repo);
  }
  const d=await this.linear(`query($id:String!){issue(id:$id){id title description updatedAt url state{type}}}`,{id});if(!d.issue)throw Error('linear_issue_not_found');return normalizeLinear(d.issue);
 }
 async create(source:Provider,origin:Issue):Promise<Issue>{
  if(source==='github'){
   const d=await this.gh('/issues',{method:'POST',body:JSON.stringify({title:origin.title,body:origin.body+'\n\n'+linearMarker(origin.id)})});return normalizeGithub(d,this.c.repo);
  }
  const d=await this.linear(`mutation($input:IssueCreateInput!){issueCreate(input:$input){success issue{id title description updatedAt url state{type}}}}`,{input:{teamId:this.c.team,title:origin.title,description:origin.body+'\n\n'+ghMarker(origin.id)}});
  if(!d.issueCreate?.success||!d.issueCreate.issue)throw Error('linear_create_failed');return normalizeLinear(d.issueCreate.issue);
 }
 async update(source:Provider,target:Issue,origin:Issue):Promise<Issue>{
  if(source==='github'){
   const n=Number(target.id.split('#').at(-1));const d=await this.gh(`/issues/${n}`,{method:'PATCH',body:JSON.stringify({title:origin.title,body:origin.body+'\n\n'+linearMarker(origin.id),state:origin.state})});return normalizeGithub(d,this.c.repo);
  }
  const stateId=origin.state==='closed'?this.c.linearDone:this.c.linearOpen;
  if(origin.state!==target.state&&!stateId)throw Error('linear_state_mapping_required');
  const input:any={title:origin.title,description:origin.body+'\n\n'+ghMarker(origin.id)};
  if(stateId&&origin.state!==target.state)input.stateId=stateId;
  const d=await this.linear(`mutation($id:String!,$input:IssueUpdateInput!){issueUpdate(id:$id,input:$input){success issue{id title description updatedAt url state{type}}}}`,{id:target.id,input});
  if(!d.issueUpdate?.success||!d.issueUpdate.issue)throw Error('linear_update_failed');return normalizeLinear(d.issueUpdate.issue);
 }
 async list(source:Provider):Promise<Issue[]>{
  if(source==='github'){
   const out:Issue[]=[];
   for(let page=1;page<=10;page++){
    const batch=await this.gh(`/issues?state=all&per_page=100&page=${page}`);
    if(!Array.isArray(batch))throw Error('bad_gh_list');out.push(...batch.filter((v:any)=>!v.pull_request).map((v:any)=>normalizeGithub(v,this.c.repo)));
    if(batch.length<100)break;
   }
   return out;
  }
  const out:Issue[]=[];let cursor:string|null=null;
  for(let n=0;n<10;n++){
   const q=await this.linear(`query($after:String,$team:String!){issues(first:100,after:$after,filter:{team:{id:{eq:$team}}}){nodes{id title description updatedAt url state{type}} pageInfo{hasNextPage endCursor}}}`,{after:cursor,team:this.c.team});
   const pages=q.issues;if(!pages?.nodes)throw Error('linear_list_invalid');out.push(...pages.nodes.map(normalizeLinear));
   if(!pages.pageInfo?.hasNextPage)break;cursor=pages.pageInfo.endCursor;
  }
  return out;
 }
 async findByMarker(source:Provider,origin:Issue):Promise<Issue|undefined>{
  const marker=source==='github'?linearMarker(origin.id):ghMarker(origin.id);
  // list() removes sync markers in normalized body; request the raw target records in a dedicated recovery read.
  if(source==='github'){
   for(let page=1;page<=10;page++){
    const batch=await this.gh(`/issues?state=all&per_page=100&page=${page}`);
    const found=batch.find((v:any)=>!v.pull_request&&hasMarker(v.body||'',marker));
    if(found)return normalizeGithub(found,this.c.repo);
    if(batch.length<100)break;
   }
  }else{
   let cursor:string|null=null;
   for(let i=0;i<10;i++){
    const r=await this.linear(`query($after:String,$team:String!){issues(first:100,after:$after,filter:{team:{id:{eq:$team}}}){nodes{id title description updatedAt url state{type}} pageInfo{hasNextPage endCursor}}}`,{after:cursor,team:this.c.team});
    const found=r.issues.nodes.find((v:any)=>hasMarker(v.description||'',marker));if(found)return normalizeLinear(found);
    if(!r.issues.pageInfo.hasNextPage)break;cursor=r.issues.pageInfo.endCursor;
   }
  }
  return;
 }
}

export async function processOne(store:Store,adapter:Adapter,dryRun=false):Promise<{status:string,detail?:string}> {
 const job=store.next();if(!job)return {status:'empty'};
 try{
  const origin=job.issue;
  if(!allowedIssue(origin))throw Error('bounded_issue_fields_invalid');
  const other:Provider=origin.source==='github'?'linear':'github';
  let link=store.getLink(origin.source,origin.id);
  if(link&&link[`${origin.source}_hash`]===fingerprint(origin)){store.success(job.id);return {status:'deduplicated'};}
  let target:Issue|undefined;
  if(link){target=await adapter.get(other,other==='github'?link.github_id:link.linear_id);}
  else target=await adapter.findByMarker(other,origin);
  if(dryRun){store.preview(job.id);return {status:'dry_run',detail:target?'would_update':'would_create'};}
  if(!target){target=await adapter.create(other,origin);}
  const ghId=origin.source==='github'?origin.id:target.id;
  const lnId=origin.source==='linear'?origin.id:target.id;
  store.link(ghId,lnId);
  link=store.getLink(origin.source,origin.id);
  // Durable side-effects can have been committed remotely even if the caller crashed.
  if(fingerprint(target)!==fingerprint(origin)){
   if(link && (other==='github'?link.github_hash:link.linear_hash)!==null && sourceWins(target,origin)){
     // Target changed more recently; do not silently erase its work.
     store.queue(target);store.success(job.id);return {status:'conflict_target_wins'};
   }
   target=await adapter.update(other,target,origin);
  }
  store.mark(origin.source,origin.id,origin);store.mark(other,target.id,target);
  store.success(job.id);return {status:'synced',detail:`${ghId} <-> ${lnId}`};
 }catch(e){store.retry(job.id,job.attempts+1,String(e));return {status:'retried_or_dead',detail:String(e).slice(0,230)};}
}
const readBody=async(req:IncomingMessage,limit=400000):Promise<Buffer>=>{
 const chunks:Buffer[]=[];let len=0;for await(const raw of req){len+=raw.length;if(len>limit)throw Error('body_too_large');chunks.push(raw);}return Buffer.concat(chunks);
};
const respond=(res:ServerResponse,code:number,obj:any)=>{res.writeHead(code,{'content-type':'application/json','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(JSON.stringify(obj));};
export function handler(store:Store,c:Config): (req:IncomingMessage,res:ServerResponse)=>Promise<void>{
 return async(req,res)=>{
  try{
   const p=new URL(req.url||'/',`http://localhost:${c.port}`).pathname;
   if(req.method==='GET'&&p==='/health')return respond(res,200,{ok:true,service:'agent-economy-linear-github-sync',queue:store.stats(),dryRun:c.dryRun});
   if(req.method!=='POST'||!['/webhooks/github','/webhooks/linear'].includes(p))return respond(res,404,{error:'not_found'});
   const raw=await readBody(req);
   if(p==='/webhooks/github'){
    if(!signatureValid(c.ghSecret,raw,req.headers['x-hub-signature-256'] as string|null))return respond(res,401,{error:'bad_github_signature'});
    const delivery=req.headers['x-github-delivery'];if(typeof delivery!=='string'||!delivery||delivery.length>150)return respond(res,400,{error:'invalid_delivery'});
    const event=req.headers['x-github-event'];const data=JSON.parse(raw.toString());
    if(event!=='issues'||!['opened','edited','closed','reopened'].includes(data.action))return respond(res,202,{ignored:'event_not_syncable'});
    if(data.repository?.full_name!==c.repo)return respond(res,403,{error:'repo_not_allowlisted'});
    const issue=normalizeGithub(data.issue,c.repo);
    if(!store.accept('github',delivery,issue))return respond(res,202,{duplicate:true});return respond(res,202,{queued:true,id:issue.id});
   }
   if(!signatureValid(c.linearSecret,raw,req.headers['linear-signature'] as string|null,''))return respond(res,401,{error:'bad_linear_signature'});
   const data=JSON.parse(raw.toString());
   if(data.type!=='Issue'||!['create','update'].includes(data.action))return respond(res,202,{ignored:'event_not_syncable'});
   if(data.data?.teamId!==c.team)return respond(res,403,{error:'team_not_allowlisted'});
   const issue=normalizeLinear(data.data);
   const delivery=data.webhookId||req.headers['linear-delivery']||hash(raw.toString());
   if(typeof delivery!=='string'||delivery.length>150)return respond(res,400,{error:'invalid_delivery'});
   if(!store.accept('linear',delivery,issue))return respond(res,202,{duplicate:true});return respond(res,202,{queued:true,id:issue.id});
  }catch(e){return respond(res,String(e).includes('body_too_large')?413:400,{error:String(e).slice(0,140)});}
 };
}
export async function worker(store:Store,adapter:Adapter,dryRun=false,count=50){const report:any[]=[];for(let i=0;i<count;i++){const r=await processOne(store,adapter,dryRun);if(r.status==='empty')break;report.push(r);}return report;}
export async function reconcile(store:Store,adapter:Adapter){const seen=[];for(const source of ['github','linear'] as Provider[]){const issues=await adapter.list(source);for(const issue of issues){if(!allowedIssue(issue))continue;store.queue(issue);}seen.push({source,count:issues.length});}return seen;}

if(process.argv[1]&&import.meta.url===new URL(`file://${process.argv[1]}`).href){
 const c=configFromEnv();strictConfig(c);mkdirSync(dirname(c.dbPath),{recursive:true});const store=new Store(c.dbPath);store.recover();if(!c.dryRun)store.resumePreviews();const adapter=new RealAdapter(c);
 const mode=process.argv[2]||'server';
 if(mode==='reconcile'){const report=await reconcile(store,adapter);console.log(JSON.stringify({reconcile:report,work:await worker(store,adapter,c.dryRun)}));store.close();}
 else if(mode==='once'){console.log(JSON.stringify(await worker(store,adapter,c.dryRun)));store.close();}
 else{
  const s=createServer((req,res)=>{void handler(store,c)(req,res)});s.listen(c.port,()=>console.log(JSON.stringify({ready:true,port:c.port,dryRun:c.dryRun})));
  const interval=setInterval(()=>{void worker(store,adapter,c.dryRun).catch(e=>console.error('worker',String(e)))},30000);
  // Periodic reconciliation closes the gap when either webhook provider was offline.
  let reconciling=false;
  const cron=setInterval(async()=>{if(reconciling)return;reconciling=true;try{await reconcile(store,adapter);await worker(store,adapter,c.dryRun);}catch(e){console.error('reconcile',String(e));}finally{reconciling=false;}},300000);
  process.on('SIGTERM',()=>{clearInterval(interval);clearInterval(cron);s.close(()=>{store.close();process.exit(0)})});
 }
}
