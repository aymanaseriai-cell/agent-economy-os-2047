import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHmac} from 'node:crypto';
import {Store} from '../src/store.ts';
import {fingerprint,signatureValid,normalizeGithub,normalizeLinear,sourceWins,stripMarker,ghMarker,linearMarker,type Issue,type Provider} from '../src/core.ts';
import {processOne,type Adapter} from '../src/server.ts';

const now='2026-11-09T14:00:00Z';
const gh=(id='demo/repo#2',title='Bug'):Issue=>({source:'github',id,title,body:'Repair data race',state:'open',updatedAt:now,url:'https://github.com/demo/repo/issues/2'});
const ln=(id='abcd-1234',title='Bug'):Issue=>({source:'linear',id,title,body:'Repair data race',state:'open',updatedAt:now,url:'https://linear.app/demo/issue/abc'});
class MockAdapter implements Adapter{
 github=new Map<string,Issue>();linear=new Map<string,Issue>();writes:string[]=[];
 async get(s:Provider,id:string){const x=this[s].get(id);if(!x)throw Error('not_found');return x;}
 async findByMarker(s:Provider,o:Issue){return undefined;}
 async create(s:Provider,o:Issue){const v=s==='github'?gh('demo/repo#88',o.title):ln('linear-88',o.title);v.body=o.body;v.state=o.state;this[s].set(v.id,v);this.writes.push('create:'+s);return v;}
 async update(s:Provider,t:Issue,o:Issue){const v={...t,title:o.title,body:o.body,state:o.state,updatedAt:o.updatedAt};this[s].set(v.id,v);this.writes.push('update:'+s);return v;}
 async list(s:Provider){return [...this[s].values()];}
}

test('signed GitHub webhooks reject wrong signature, exact payload accepts',()=>{
 const raw=Buffer.from('{"hello":"world"}');const good=createHmac('sha256','strongghsecret').update(raw).digest('hex');
 assert.equal(signatureValid('strongghsecret',raw,'sha256='+good),true);
 assert.equal(signatureValid('strongghsecret',raw,'sha256='+'0'.repeat(64)),false);
 assert.equal(signatureValid('strongghsecret',raw,null),false);
 assert.equal(signatureValid('wrong',raw,'sha256='+good),false);
});
test('Linear webhook signatures accept raw digest only',()=>{
 const raw=Buffer.from('important');const good=createHmac('sha256','separate-linear').update(raw).digest('hex');
 assert.equal(signatureValid('separate-linear',raw,good,''),true);
 assert.equal(signatureValid('separate-linear',Buffer.from('tampered'),good,''),false);
});
test('normalize metadata and strip echo prevention marker',()=>{
 const issue=normalizeGithub({number:8,title:'Repair',body:'Fix\n\n'+linearMarker('lin-33'),state:'closed',updated_at:now},'demo/repo');
 assert.equal(issue.body,'Fix');assert.equal(issue.state,'closed');assert.equal(issue.id,'demo/repo#8');
 const other=normalizeLinear({id:'lin-33',title:'Repair',description:'Fix\n\n'+ghMarker('demo/repo#8'),state:{type:'completed'},updatedAt:now});
 assert.equal(other.body,'Fix');assert.equal(other.state,'closed');
 assert.equal(fingerprint({...issue,source:'linear'}),fingerprint(issue));
});
test('event receipts and outbox are idempotent across replays',()=>{
 const db=new Store(':memory:');assert.equal(db.received('github','abc'),true);assert.equal(db.received('github','abc'),false);
 db.queue(gh());db.queue(gh());let item=db.next();assert.ok(item);assert.equal(db.next(),undefined);db.success(item.id);assert.deepEqual(db.stats().map(x=>x.status),['done']);db.close();
});
test('first GitHub issue produces one mapped Linear issue and loops do not amplify',async()=>{
 const db=new Store(':memory:');const adapter=new MockAdapter();adapter.github.set(gh().id,gh());
 db.queue(gh());assert.equal((await processOne(db,adapter)).status,'synced');assert.equal(adapter.writes.length,1);
 assert.equal(db.getLink('github',gh().id)?.linear_id,'linear-88');
 db.queue(ln('linear-88'));assert.equal((await processOne(db,adapter)).status,'deduplicated');
 assert.equal(adapter.writes.length,1);db.close();
});
test('normal GitHub edit pushes update once and ignores duplicate',async()=>{
 const db=new Store(':memory:');const a=new MockAdapter();db.queue(gh());await processOne(db,a);
 const edit=gh('demo/repo#2','Bug fixed');edit.updatedAt='2026-11-09T15:00:00Z';
 db.queue(edit);let r=await processOne(db,a);assert.equal(r.status,'synced');assert.deepEqual(a.writes,['create:linear','update:linear']);
 db.queue(edit);r=await processOne(db,a);assert.equal(r.status,'empty');db.close();
});
test('fatal API errors requeue with bounded backoff, do not discard work',async()=>{
 const db=new Store(':memory:');const a=new MockAdapter();a.create=async()=>{throw Error('503 service unavailable')};
 db.queue(gh());assert.equal((await processOne(db,a)).status,'retried_or_dead');
 assert.equal(db.next(),undefined);const count=db.db.prepare("SELECT attempts FROM outbox").get() as any;assert.equal(count.attempts,1);db.close();
});
test('dry run performs no remote changes or spend',async()=>{
 const db=new Store(':memory:');const a=new MockAdapter();db.queue(gh());
 assert.equal((await processOne(db,a,true)).status,'dry_run');assert.deepEqual(a.writes,[]);
 db.resumePreviews();assert.equal((await processOne(db,a,false)).status,'synced');db.close();
});
test('newer remote target takes precedence during an actual conflicting edit',async()=>{
 const db=new Store(':memory:');const a=new MockAdapter();db.queue(gh());await processOne(db,a);
 const remote=ln('linear-88','External more recent');remote.updatedAt='2026-11-09T18:00:00Z';a.linear.set('linear-88',remote);
 const edit=gh('demo/repo#2','Old edit');edit.updatedAt='2026-11-09T16:00:00Z';db.queue(edit);
 const r=await processOne(db,a);assert.equal(r.status,'conflict_target_wins');
 assert.equal(a.linear.get('linear-88')?.title,'External more recent');db.close();
});
test('create from Linear maps to GitHub, enforces same deduplication',async()=>{
 const db=new Store(':memory:');const a=new MockAdapter();db.queue(ln('lin-new'));
 assert.equal((await processOne(db,a)).status,'synced');
 assert.equal(db.getLink('linear','lin-new')?.github_id,'demo/repo#88');
 db.queue(gh('demo/repo#88'));assert.equal((await processOne(db,a)).status,'deduplicated');db.close();
});

test('atomic webhook acknowledgement and event replay queue exactly one issue',()=>{
 const db=new Store(':memory:');const issue=gh('demo/repo#54');
 assert.equal(db.accept('github','delivery-1',issue),true);
 assert.equal(db.accept('github','delivery-1',issue),false);
 assert.equal(db.next()?.issue.id,'demo/repo#54');assert.equal(db.next(),undefined);db.close();
});
