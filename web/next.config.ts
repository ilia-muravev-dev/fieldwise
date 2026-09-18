import type { NextConfig } from "next";

// /api/* is proxied to the FastAPI service by src/app/api/[...path]/route.ts at request time
// (API_URL), so the built image needs no baked-in address.
const nextConfig: NextConfig = {
  output: "standalone",
  reactCompiler: true,
};

export default nextConfig;
