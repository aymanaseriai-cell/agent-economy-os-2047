import {createHmac, createHash, timingSafeEqual} from 'node:crypto';

export type Provider = 'github'|'linear';
export type Issue = {source:Provider,id:string,title:string,body:string,state:'open'|'closed',updatedAt:string,url:string};
export type Event = {id:string,source:Provider,issue:Issue};

// Never copy title/body fields from untrusted events to a shell or a query string.
export const hash = (value:string) => createHash('sha256').update(value).digest('hex');
export const canonical = (issue:Issue) => JSON.stringify({title:issue.title.trim(),body:issue.body.trim(),state:issue.state});
export const fingerprint = (issue:Issue) => hash(canonical(issue));
export const safeDate = (s:string) => {const ms=Date.parse(s);return Number.isFinite(ms)?ms:0;};
export const sourceWins = (a:Issue,b:Issue) => safeDate(a.updatedAt)>safeDate(b.updatedAt) || (safeDate(a.updatedAt)===safeDate(b.updatedAt) && a.source<b.source);
export const signatureValid = (secret:string,raw:Buffer,header:string|null,prefix='sha256=') => {
  if(!secret || !header)return false;
  const given=header.startsWith(prefix)?header.slice(prefix.length):header;
  if(!/^[0-9a-fA-F]{64}$/.test(given))return false;
  const expected=createHmac('sha256',secret).update(raw).digest();
  return timingSafeEqual(Buffer.from(given,'hex'),expected);
};
export const ghMarker=(linearId:string)=>`<!-- agent-economy-sync:linear:${linearId} -->`;
export const linearMarker=(ghId:string)=>`<!-- agent-economy-sync:github:${ghId} -->`;
export const hasMarker=(text:string,marker:string)=>text.includes(marker);
export const stripMarker=(body:string)=>body.replace(/\n?<!-- agent-economy-sync:(?:github|linear):[^>]* -->/g,'').trim();
export const normalizeGithub=(raw:any,repo:string):Issue=>{
  if(!raw || !Number.isSafeInteger(raw.number)||typeof raw.title!=='string')throw Error('invalid_github_issue');
  return {source:'github',id:`${repo}#${raw.number}`,title:raw.title,body:stripMarker(raw.body||''),state:raw.state==='closed'?'closed':'open',updatedAt:raw.updated_at||raw.created_at||'1970-01-01T00:00:00Z',url:raw.html_url||''};
};
export const normalizeLinear=(raw:any):Issue=>{
  if(!raw||typeof raw.id!=='string'||typeof raw.title!=='string')throw Error('invalid_linear_issue');
  return {source:'linear',id:raw.id,title:raw.title,body:stripMarker(raw.description||''),state:raw.state?.type==='completed'||raw.state?.type==='canceled'||raw.state==='closed'?'closed':'open',updatedAt:raw.updatedAt||raw.createdAt||'1970-01-01T00:00:00Z',url:raw.url||''};
};
export const allowedIssue=(issue:Issue,maxBytes=45000)=>issue.title.length<=500 && Buffer.byteLength(issue.body,'utf8')<=maxBytes && issue.id.length<400;
