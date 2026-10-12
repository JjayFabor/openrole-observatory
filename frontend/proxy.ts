import { NextResponse, type NextRequest } from "next/server";
import { checkDashboardAccess } from "./lib/dashboard/access";

export function proxy(request: NextRequest): NextResponse {
  const access = checkDashboardAccess(request.headers.get("authorization"));
  if (access === "allowed") {
    const response = NextResponse.next();
    response.headers.set("Cache-Control", "private, no-store");
    return response;
  }
  return new NextResponse(
    access === "unconfigured"
      ? "Dashboard access is not configured."
      : "Dashboard authentication required.",
    {
      status: access === "unconfigured" ? 503 : 401,
      headers: {
        "Cache-Control": "private, no-store",
        ...(access === "unauthorized"
          ? {
              "WWW-Authenticate": 'Basic realm="OpenRole dashboard", charset="UTF-8"',
            }
          : {}),
      },
    },
  );
}

// The only Server Action is administrative, including when posted to a public URL.
export const config = {
  matcher: [
    "/dashboard/:path*",
    { source: "/:path*", has: [{ type: "header", key: "next-action" }] },
  ],
};
