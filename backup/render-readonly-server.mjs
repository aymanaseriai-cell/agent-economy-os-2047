// Independent, public, GET/HEAD-only Work Covenant backup server for Render.
// Reuses the repository's deterministic handler; DOES NOT proxy paid/mutating APIs.
import { createServer } from "node:http";
import { handler } from "../services/agent-work-covenant-2047/index.mjs";

const allowedPaths = new Set([
  "/", "/health", "/demo", "/openapi.json", "/skill.md", "/.well-known/agent.json"
]);
const errorJSON = JSON.stringify({ ok: false, error: { code: "not_found" } });

export function createReadonlyServer() {
  return createServer(async (request, response) => {
    const method = request.method || "GET";
    if (method !== "GET" && method !== "HEAD") {
      request.resume();
      response.writeHead(405, {
        allow: "GET, HEAD",
        "cache-control": "no-store",
        "content-type": "application/json"
      });
      response.end(JSON.stringify({ ok:false, error:{code:"method_not_allowed"} }));
      return;
    }
    try {
      // A fixed, operator-defined target is passed to the stateless handler.
      // Client-supplied Host values never affect the destination.
      const incoming = new URL(request.url || "/", "https://backup.invalid");
      if (!allowedPaths.has(incoming.pathname)) {
        response.writeHead(404, {
          "cache-control": "no-store", "content-type": "application/json"
        });
        response.end(method === "HEAD" ? undefined : errorJSON);
        return;
      }
      const url = new URL(
        "/functions/v1/agent-work-covenant-2047" +
          incoming.pathname + incoming.search,
        "https://backup.invalid"
      );
      const result = await handler(new Request(url, { method: "GET" }));
      const headers = Object.fromEntries(result.headers.entries());
      headers["cache-control"] = "no-store";
      headers["x-agent-economy-backup"] = "readonly";
      response.writeHead(result.status, headers);
      if (method === "HEAD") {
        response.end();
      } else {
        response.end(Buffer.from(await result.arrayBuffer()));
      }
    } catch {
      if (!response.headersSent) {
        response.writeHead(503, { "cache-control": "no-store" });
      }
      response.end();
    }
  });
}
if (process.argv[1] && import.meta.url === new URL("file://" + process.argv[1]).href) {
  const port = Number(process.env.PORT || 10000);
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535) {
    throw new Error("Invalid PORT");
  }
  createReadonlyServer().listen(port, "0.0.0.0");
}
