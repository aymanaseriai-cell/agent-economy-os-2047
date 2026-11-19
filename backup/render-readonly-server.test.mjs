import test from "node:test";
import assert from "node:assert/strict";
import { once } from "node:events";
import { createReadonlyServer } from "./render-readonly-server.mjs";
import { handler } from "../services/agent-work-covenant-2047/index.mjs";

async function withServer(fn) {
  const server = createReadonlyServer();
  server.listen(0,"127.0.0.1");
  await once(server, "listening");
  try {
    await fn("http://127.0.0.1:" + server.address().port);
  } finally {
    await new Promise((resolve, reject) => server.close(e => e ? reject(e) : resolve()));
  }
}
test("healthy GET responses use the exact core handler", async () => withServer(async base => {
  for(const path of ["/health","/demo","/openapi.json","/skill.md","/.well-known/agent.json"]) {
    const response = await fetch(base + path);
    const expected = await handler(new Request("https://example.invalid/functions/v1/agent-work-covenant-2047" + path));
    assert.equal(response.status, 200, path);
    assert.equal(await response.text(), await expected.text(), path);
    assert.equal(response.headers.get("x-agent-economy-backup"), "readonly");
  }
}));
test("HEAD is accepted without response body", async () => withServer(async base => {
  const r = await fetch(base + "/health", { method:"HEAD" });
  assert.equal(r.status, 200);
  assert.equal(await r.text(), "");
}));
test("write methods are rejected, including compile and evaluate", async () => withServer(async base => {
  for(const path of ["/v1/compile","/v1/evaluate","/"]) {
    const r=await fetch(base+path,{method:"POST",headers:{"content-type":"application/json"},body:"{}"});
    assert.equal(r.status,405);
  }
}));
test("unexpected GET paths are rejected", async () => withServer(async base => {
  const r=await fetch(base+"/v1/evaluate");
  assert.equal(r.status,404);
}));
