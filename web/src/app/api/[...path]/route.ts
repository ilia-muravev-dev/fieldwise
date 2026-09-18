import type { NextRequest } from "next/server";

// A runtime proxy to the FastAPI service: the browser only ever talks to this app, and the target
// is read from the environment when the request arrives (so the same image runs anywhere).
const API_URL = () => (process.env.API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "host",
  "content-length",
]);

async function proxy(
  request: NextRequest,
  { params }: RouteContext<"/api/[...path]">,
): Promise<Response> {
  const { path } = await params;
  const target = new URL(`${API_URL()}/${path.join("/")}`);
  target.search = request.nextUrl.search;
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });
  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: hasBody ? request.body : undefined,
    // @ts-expect-error — required by Node's fetch for streaming request bodies
    duplex: hasBody ? "half" : undefined,
    redirect: "manual",
    cache: "no-store",
  });
  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export const dynamic = "force-dynamic";
export { proxy as DELETE, proxy as GET, proxy as PATCH, proxy as POST, proxy as PUT };
