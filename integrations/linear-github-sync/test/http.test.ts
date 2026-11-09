import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHmac} from 'node:crypto';
import {createServer} from 'node:http';
import {Store} from '../src/store.ts';
import {handler} from '../src/server.ts';

const cfg:any={repo:'demo/repo',team:'team-limited',ghSecret:'gh-unique-secret',linearSecret:'linear-unique-secret',port:3000};
const issue={number:7,title:'Test issue',body:'Request a fix',state:'open',updated_at:'2026-11-09T15:00:00Z',html_url:'https://github.com/demo/repo/issues/7'};
const ghEvent={action:'opened',repository:{full_name:'demo/repo'},issue};
const signature=(body:string,secret:string,prefix='sha256=')=>prefix+createHmac('sha256',secret).update(body).digest('hex');

async function api(cb:(base:string,store:Store)=>Promise<void>){
 const store=new Store(':memory:');const server=createServer((req,res)=>void handler(store,cfg)(req,res));
 await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
 const address=server.address();if(!address||typeof address==='string')throw Error('invalid address');
 try{await cb(`http://127.0.0.1:${address.port}`,store);}finally{await new Promise<void>(resolve=>server.close(()=>resolve()));store.close();}
}

test('GitHub webhook refuses unauthenticated messages and accepts signed events',async()=>api(async(base,db)=>{
 const body=JSON.stringify(ghEvent);
 const options={method:'POST',headers:{'x-github-event':'issues','x-github-delivery':'abc1','x-hub-signature-256':signature(body,cfg.ghSecret)},body};
 assert.equal((await fetch(base+'/webhooks/github',{...options,headers:{...options.headers,'x-hub-signature-256':'sha256='+'0'.repeat(64)}})).status,401);
 let res=await fetch(base+'/webhooks/github',options);assert.equal(res.status,202);assert.equal((await res.json()).queued,true);
 res=await fetch(base+'/webhooks/github',options);assert.equal(res.status,202);assert.equal((await res.json()).duplicate,true);
 assert.equal(db.next()?.issue.id,'demo/repo#7');assert.equal(db.next(),undefined);
}));

test('signed GitHub event cannot act on an unauthorized repository',async()=>api(async(base,db)=>{
 const body=JSON.stringify({...ghEvent,repository:{full_name:'competitor/secret'}});
 const res=await fetch(base+'/webhooks/github',{method:'POST',headers:{'x-github-event':'issues','x-github-delivery':'abc2','x-hub-signature-256':signature(body,cfg.ghSecret)},body});
 assert.equal(res.status,403);assert.equal(db.next(),undefined);
}));

test('Linear signed webhook is team-scoped and idempotent',async()=>api(async(base,db)=>{
 const body=JSON.stringify({type:'Issue',action:'create',webhookId:'lin-delivery-1',data:{id:'lin-id-1',title:'Create',description:'Safe text',teamId:'team-limited',state:{type:'started'},updatedAt:'2026-11-09T15:00:00Z'}});
 const options={method:'POST',headers:{'linear-signature':signature(body,cfg.linearSecret,'')},body};
 assert.equal((await fetch(base+'/webhooks/linear',{...options,headers:{'linear-signature':'f'.repeat(64)}})).status,401);
 let res=await fetch(base+'/webhooks/linear',options);assert.equal(res.status,202);assert.equal((await res.json()).queued,true);
 res=await fetch(base+'/webhooks/linear',options);assert.equal(res.status,202);assert.equal((await res.json()).duplicate,true);
 assert.equal(db.next()?.issue.id,'lin-id-1');assert.equal(db.next(),undefined);
}));

test('server health is internal no-store and disallows unexpected routes',async()=>api(async(base)=>{
 const resp=await fetch(base+'/health');const health=await resp.json();
 assert.equal(resp.status,200);assert.equal(resp.headers.get('cache-control'),'no-store');assert.equal(health.ok,true);
 assert.equal((await fetch(base+'/secret-file')).status,404);
}));
