// @vitest-environment node
import { afterEach, describe, expect, it } from "vitest";
import { createServer as createHttpServer, request as httpRequest } from "node:http";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer, preview } from "vite";
import { localApiProxy } from "./local-api-proxy";

const cleanups: Array<() => Promise<unknown>> = [];
afterEach(async () => {
  for (const cleanup of cleanups.reverse()) await cleanup();
  cleanups.length = 0;
});

async function fixture(productionPreview = false, token = "test-server-only-secret") {
  const requests: Array<{ url?: string; authorization?: string; range?: string }> = [];
  const backend = createHttpServer((request, response) => {
    requests.push({ url: request.url, authorization: request.headers.authorization, range: request.headers.range });
    if (request.headers.authorization !== "Bearer test-server-only-secret") {
      response.writeHead(401); response.end(); return;
    }
    response.writeHead(request.headers.range ? 206 : 200, {
      "Content-Type": "video/mp4", "Accept-Ranges": "bytes", "Content-Range": "bytes 0-0/20",
    });
    response.end("x");
  });
  await new Promise<void>((resolve) => backend.listen(0, "127.0.0.1", resolve));
  cleanups.push(() => new Promise<void>((resolve, reject) => backend.close((error) => error ? reject(error) : resolve())));
  const address = backend.address();
  if (!address || typeof address === "string") throw new Error("Expected a TCP listener");
  const root = await mkdtemp(join(tmpdir(), "pickleball-proxy-"));
  cleanups.push(() => rm(root, { recursive: true, force: true }));
  await writeFile(join(root, "index.html"), "<html>local preview</html>");
  const proxy = localApiProxy({ PICKLEBALL_API_TOKEN: token, PICKLEBALL_API_PROXY_TARGET: `http://127.0.0.1:${address.port}` });
  const config = {
    configFile: false as const, root, plugins: [proxy.plugin], logLevel: "silent" as const,
    server: { host: "127.0.0.1", port: 0, proxy: proxy.routes },
    preview: { host: "127.0.0.1", port: 0, proxy: proxy.routes },
    build: { outDir: root },
  };
  const server = productionPreview ? await preview(config) : await createServer(config);
  if ("listen" in server) await server.listen();
  cleanups.push(async () => { await server.close(); });
  const frontend = server.httpServer?.address();
  if (!frontend || typeof frontend === "string") throw new Error("Expected frontend listener");
  return { origin: `http://127.0.0.1:${frontend.port}`, requests };
}

describe("local API boundary", () => {
  it.each([false, true])("preserves native video Range requests (preview=%s)", async (productionPreview) => {
    const { origin, requests } = await fixture(productionPreview);
    const response = await fetch(`${origin}/__analysis_api/api/videos/demo/stream`, { headers: { Range: "bytes=0-0" } });
    expect(response.status).toBe(206);
    expect(response.headers.get("content-range")).toBe("bytes 0-0/20");
    expect(await response.text()).toBe("x");
    expect(requests).toEqual([{ url: "/api/videos/demo/stream", authorization: "Bearer test-server-only-secret", range: "bytes=0-0" }]);
  });
  it.each([
    { Origin: "https://untrusted.example" },
    { "Sec-Fetch-Site": "cross-site" },
    { "Sec-Fetch-Site": "same-site" },
  ])("rejects foreign browser requests before forwarding: %s", async (headers) => {
    const { origin, requests } = await fixture();
    const response = await fetch(`${origin}/__analysis_api/api/analysis/jobs`, { method: "POST", headers });
    expect(response.status).toBe(403);
    expect(requests).toHaveLength(0);
  });
  it("rejects an untrusted Host header before forwarding", async () => {
    const { origin, requests } = await fixture();
    const status = await new Promise<number | undefined>((resolve, reject) => {
      const request = httpRequest(`${origin}/__analysis_api/api/analysis/jobs`, { headers: { Host: "untrusted.example" } }, (response) => {
        response.resume();
        response.on("end", () => resolve(response.statusCode));
      });
      request.on("error", reject);
      request.end();
    });
    expect(status).toBe(403);
    expect(requests).toHaveLength(0);
  });
  it("fails closed when the server has no credential", async () => {
    const { origin, requests } = await fixture(false, "");
    expect((await fetch(`${origin}/__analysis_api/api/videos/demo/stream`)).status).toBe(503);
    expect(requests).toHaveLength(0);
  });
  it("accepts same-origin mutations but rejects unknown proxy paths", async () => {
    const { origin, requests } = await fixture();
    expect((await fetch(`${origin}/__analysis_api/api/analysis/jobs`, { method: "POST", headers: { Origin: origin } })).status).toBe(200);
    expect((await fetch(`${origin}/__analysis_api/private`)).status).toBe(404);
    expect(requests).toHaveLength(1);
  });
  it("refuses a public target", () => {
    expect(() => localApiProxy({ PICKLEBALL_API_PROXY_TARGET: "https://example.com" })).toThrow(/loopback/);
  });
  it("refuses a LAN listener even when explicitly overridden", async () => {
    const proxy = localApiProxy({ PICKLEBALL_API_TOKEN: "test" });
    await expect(createServer({ configFile: false, plugins: [proxy.plugin], server: { host: "0.0.0.0" } })).rejects.toThrow(/loopback/);
  });
});
