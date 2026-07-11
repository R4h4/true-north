// Same-origin proxy: the browser only ever talks to this Next.js route;
// the AG-UI FastAPI backend (:8000) stays private behind it (phase-3 plan:
// one cloudflared origin, CORS only ever a local-dev concern).
import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { HttpAgent } from "@ag-ui/client";
import { NextRequest } from "next/server";

const runtime = new CopilotRuntime({
  agents: {
    "true-north": new HttpAgent({
      url: process.env.AGUI_URL ?? "http://localhost:8000/",
    }),
  },
});

export const POST = async (req: NextRequest) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter: new ExperimentalEmptyAdapter(),
    endpoint: "/api/copilotkit",
  });
  return handleRequest(req);
};
