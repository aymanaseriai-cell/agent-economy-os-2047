import test from "node:test";
import assert from "node:assert/strict";
import { routeRequest } from "./worker.mjs";

const env = {
  PRIMARY_API_BASE: "https://primary.example/functions/v1/agent-work-covenant-2047",
  SECONDARY_API_BASE: "https://secondary.example/functions/v1/agent-work-covenant-2047",
  UPSTREAM_TIMEOUT_MS: "2000"
};

test("primary success preserves route and query", async () => {
  const calls = [];
  const response = await routeRequest(
    new Request("https://router.example/openapi.json?v=1"),
    env,
    async (url) => {
      calls.push(url);
      return new Response('{"openapi":"3.1.0"}', { status: 200 });
    }
  );
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-agent-economy-upstream"), "primary");
  assert.deepEqual(calls, [
    "https://primary.example/functions/v1/agent-work-covenant-2047/openapi.json?v=1"
  ]);
});

test("502 causes one read-only failover", async () => {
  const calls = [];
  const response = await routeRequest(
    new Request("https://router.example/demo"), env,
    async (url) => {
      calls.push(url);
      return new Response("ok", { status: calls.length === 1 ? 502 : 200 });
    }
  );
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-agent-economy-upstream"), "secondary");
  assert.equal(calls.length, 2);
  assert.ok(calls[1].startsWith("https://secondary.example/"));
});

test("connection error also fails over", async () => {
  const response = await routeRequest(new Request("https://router.example/demo"), env,
    async (url) => {
      if (url.startsWith("https://primary.")) throw new Error("offline");
      return new Response("backup", { status: 200 });
    });
  assert.equal(await response.text(), "backup");
});

test("404 does not fail over", async () => {
  let calls = 0;
  const response = await routeRequest(new Request("https://router.example/missing"), env,
    async () => { calls++; return new Response("not found", { status: 404 }); });
  assert.equal(response.status, 404);
  assert.equal(calls, 1);
});

test("429 does not bypass upstream quota enforcement", async () => {
  let calls = 0;
  const response = await routeRequest(new Request("https://router.example/demo"), env,
    async () => { calls++; return new Response("quota", { status: 429 }); });
  assert.equal(response.status, 429);
  assert.equal(calls, 1);
});

test("POST is never proxied or retried", async () => {
  let calls = 0;
  const response = await routeRequest(
    new Request("https://router.example/evaluate", { method: "POST", body: "{}" }),
    env, async () => { calls++; return new Response("bad"); }
  );
  assert.equal(response.status, 405);
  assert.equal(calls, 0);
});

test("missing primary fails closed", async () => {
  const response = await routeRequest(
    new Request("https://router.example/demo"), {},
    async () => { throw new Error("must not fetch"); }
  );
  assert.equal(response.status, 503);
});

test("no backup and unreachable primary returns 503", async () => {
  const response = await routeRequest(new Request("https://router.example/demo"),
    { PRIMARY_API_BASE: env.PRIMARY_API_BASE },
    async () => { throw new Error("offline"); }
  );
  assert.equal(response.status, 503);
});
