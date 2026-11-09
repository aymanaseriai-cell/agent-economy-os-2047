import {DatabaseSync} from 'node:sqlite';
import type {Issue,Provider} from './core.ts';
import {fingerprint} from './core.ts';

export type Job={id:number,origin:Provider,issue:Issue,attempts:number};
export class Store {
  db:DatabaseSync;
  constructor(path:string){
    this.db=new DatabaseSync(path);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=10000;
      CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,provider TEXT NOT NULL,received_at TEXT DEFAULT CURRENT_TIMESTAMP);
      CREATE TABLE IF NOT EXISTS links(github_id TEXT NOT NULL UNIQUE,linear_id TEXT NOT NULL UNIQUE, github_hash TEXT,linear_hash TEXT,github_updated INTEGER DEFAULT 0,linear_updated INTEGER DEFAULT 0, PRIMARY KEY(github_id,linear_id));
      CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT,origin TEXT NOT NULL,issue_id TEXT NOT NULL,payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',attempts INTEGER DEFAULT 0,next_attempt INTEGER DEFAULT 0,last_error TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(origin,issue_id,payload));
      CREATE INDEX IF NOT EXISTS outbox_status ON outbox(status,next_attempt,id);`);
  }
  close(){this.db.close();}
  received(provider:Provider,id:string){
    const info=this.db.prepare('INSERT OR IGNORE INTO receipts(id,provider) VALUES (?,?)').run(`${provider}:${id}`,provider);
    return info.changes>0;
  }
  accept(provider:Provider,delivery:string,issue:Issue){
    // Receipt + outbox become durable together. Never acknowledge a webhook after only saving its ID.
    this.db.exec('BEGIN IMMEDIATE');
    try {
      if(!this.received(provider,delivery)){this.db.exec('COMMIT');return false;}
      this.queue(issue);
      this.db.exec('COMMIT');return true;
    } catch(e){this.db.exec('ROLLBACK');throw e;}
  }
  queue(issue:Issue){
    this.db.prepare('INSERT OR IGNORE INTO outbox(origin,issue_id,payload) VALUES (?,?,?)').run(issue.source,issue.id,JSON.stringify(issue));
  }
  getLink(source:Provider,id:string):{github_id:string,linear_id:string,github_hash:string|null,linear_hash:string|null,github_updated:number,linear_updated:number}|undefined {
    return this.db.prepare(`SELECT * FROM links WHERE ${source==='github'?'github_id':'linear_id'}=?`).get(id) as any;
  }
  link(gh:string,ln:string){
    this.db.prepare('INSERT OR IGNORE INTO links(github_id,linear_id) VALUES (?,?)').run(gh,ln);
  }
  mark(source:Provider,id:string,issue:Issue){
    const column=source==='github'?'github':'linear';
    this.db.prepare(`UPDATE links SET ${column}_hash=?,${column}_updated=? WHERE ${column}_id=?`).run(fingerprint(issue),Date.parse(issue.updatedAt)||0,id);
  }
  next():Job|undefined{
    const row=this.db.prepare("SELECT * FROM outbox WHERE status='queued' AND next_attempt <= ? ORDER BY id LIMIT 1").get(Date.now()) as any;
    if(!row)return;
    this.db.prepare("UPDATE outbox SET status='working' WHERE id=?").run(row.id);
    return {id:row.id,origin:row.origin,issue:JSON.parse(row.payload),attempts:row.attempts};
  }
  preview(id:number){this.db.prepare("UPDATE outbox SET status='previewed' WHERE id=?").run(id);}
  resumePreviews(){this.db.prepare("UPDATE outbox SET status='queued' WHERE status='previewed'").run();}
  success(id:number){this.db.prepare('UPDATE outbox SET status=\'done\', last_error=NULL WHERE id=?').run(id);}
  retry(id:number,attempts:number,error:string){
    const pause=Math.min(60000*2**Math.min(attempts,9),3600000);
    this.db.prepare("UPDATE outbox SET status=?,attempts=?,next_attempt=?,last_error=? WHERE id=?").run(attempts>=8?'dead':'queued',attempts,Date.now()+pause,error.slice(0,500),id);
  }
  recover(){this.db.prepare("UPDATE outbox SET status='queued' WHERE status='working'").run();}
  stats(){return this.db.prepare("SELECT status,COUNT(*) n FROM outbox GROUP BY status").all();}
}
