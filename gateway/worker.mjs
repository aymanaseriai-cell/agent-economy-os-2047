// Read-only failover gateway for public Work Covenant routes.
// Both configured upstreams must implement identical, reviewed API semantics.
const RETRYABLE = new Set([502, 503, 504]);

function normalizeBase(raw) {
  if (!raw || typeof raw !== "string") return null;
  const url = new URL(raw);
  if (url.protocol !== "https:" || url.username || url.password ||
      url.search || url.hash) throw new Error("Invalid upstream base");
  url.pathname = url.pathname.replace(/\/+$/, "") + "/";
  return url;
}

function makeTarget(base, requestUrl) {
  const incoming = new URL(requestUrl);
  const path = incoming.pathname.replace(/^\/+/, "");
  const target = new URL(path, base);
  if (!target.pathname.startsWith(base.pathname)) {
    throw new Error("Path escapes configured upstream");
  }
  target.search = incoming.search;
  return target;
}

async function fetchWithTimeout(target, request, fetcher, ms) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    const accept = request.headers.get("accept");
    const headers = new Headers();
    if (accept) headers.set("accept", accept);
    return await fetcher(target.toString(), {
      method: request.method,
      headers,
      signal: controller.signal,
      redirect: "manual",
      cache: "no-store"
    });
  } finally {
    clearTimeout(timer);
  }
}

export async function routeRequest(request, env, fetcher = globalThis.fetch) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Read-only gateway: method not allowed", {
      status: 405, headers: { allow: "GET, HEAD", "cache-control": "no-store" }
    });
  }

  let primary, secondary;
  try {
    primary = normalizeBase(env.PRIMARY_API_BASE);
    secondary = normalizeBase(env.SECONDARY_API_BASE);
    if (!primary) throw new Error("Missing primary");
  } catch {
    return new Response("Gateway not configured", { status: 503 });
  }

  const upstreams = [{ base: primary, label: "primary" }];
  if (secondary && secondary.href !== primary.href) {
    upstreams.push({ base: secondary, label: "secondary" });
  }
  const timeout = Math.max(250, Math.min(5000, Number(env.UPSTREAM_TIMEOUT_MS) || 2500));

  for (const upstream of upstreams) {
    try {
      const target = makeTarget(upstream.base, request.url);
      const response = await fetchWithTimeout(target, request, fetcher, timeout);
      // Never bypass authentication, rate-limits, or application-level errors.
      if (RETRYABLE.has(response.status)) continue;
      const headers = new Headers(response.headers);
      headers.set("cache-control", "no-store");
      headers.set("x-agent-economy-upstream", upstream.label);
      return new Response(request.method === "HEAD" ? null : response.body, {
        status: response.status, statusText: response.statusText, headers
      });
    } catch {
      // An unreachable upstream may be retried via the next configured host.
    }
  }
  return new Response("No healthy upstream available", {
    status: 503, headers: { "cache-control": "no-store" }
  });
}

export default {
  async fetch(request, env) {
    return routeRequest(request, env);
  }
};
