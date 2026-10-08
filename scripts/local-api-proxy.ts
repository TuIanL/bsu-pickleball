import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin, ProxyOptions } from "vite";

const PREFIX = "/__analysis_api";
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
const LOOPBACK_ADDRESSES = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);

/** Local demo boundary: reject LAN peers, DNS rebinding, and cross-origin browsers. */
export function isAllowedLocalRequest(request: Pick<IncomingMessage, "headers" | "socket">): boolean {
  if (!LOOPBACK_ADDRESSES.has(request.socket.remoteAddress ?? "")) return false;
  try {
    const authority = request.headers.host;
    if (!authority) return false;
    const target = new URL(`http://${authority}`);
    if (!LOOPBACK_HOSTS.has(target.hostname) || target.host !== authority) return false;
    const origin = request.headers.origin;
    if (origin && origin !== target.origin) return false;
    const site = request.headers["sec-fetch-site"];
    return !site || site === "same-origin" || site === "none";
  } catch {
    return false;
  }
}

export function localApiProxy(env: Record<string, string>): {
  plugin: Plugin;
  routes: Record<string, ProxyOptions>;
} {
  const target = env.PICKLEBALL_API_PROXY_TARGET || "http://127.0.0.1:8000";
  const parsed = new URL(target);
  if (parsed.protocol !== "http:" || !LOOPBACK_HOSTS.has(parsed.hostname)
      || parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash) {
    throw new Error("PICKLEBALL_API_PROXY_TARGET must be a loopback HTTP origin.");
  }
  const token = env.PICKLEBALL_API_TOKEN?.trim();
  const bypass = /^(1|true|yes|on)$/i.test(env.PICKLEBALL_AUTH_DISABLED ?? "");
  const guard = (request: IncomingMessage, response: ServerResponse, next: () => void) => {
    if (!request.url?.startsWith(PREFIX)) return next();
    if (!isAllowedLocalRequest(request)) {
      response.writeHead(403, { "Content-Type": "text/plain", "Cache-Control": "no-store" });
      response.end("Local same-origin access required.");
      return;
    }
    if (!/^\/__analysis_api\/(api(?:\/|\?|$)|calibration(?:\/|\?|$)|health(?:\?|$))/.test(request.url)) {
      response.writeHead(404);
      response.end();
      return;
    }
    if (!token && !bypass) {
      response.writeHead(503, { "Content-Type": "text/plain", "Cache-Control": "no-store" });
      response.end("Configure PICKLEBALL_API_TOKEN for the local API proxy.");
      return;
    }
    next();
  };
  const requireLoopback = (host: string | boolean | undefined) => {
    if (host !== "127.0.0.1" && host !== "localhost" && host !== "::1") {
      throw new Error("The local API proxy requires a loopback listener; LAN/public hosting needs separate authentication.");
    }
  };
  return {
    plugin: {
      name: "pickleball-local-api-boundary",
      configureServer(server) {
        requireLoopback(server.config.server.host);
        server.middlewares.use(guard);
      },
      configurePreviewServer(server) {
        requireLoopback(server.config.preview.host);
        server.middlewares.use(guard);
      },
    },
    routes: {
      [PREFIX]: {
        target,
        changeOrigin: true,
        rewrite: (path) => path.slice(PREFIX.length),
        // Credentials are supplied only by the local server, never by a VITE_* variable.
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      },
    },
  };
}
