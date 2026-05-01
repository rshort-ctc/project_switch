import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const WEB_ALLOWED_PREFIXES = ["/chat", "/repos"];
const PUBLIC_ASSET = /\.[^/]+$/;

export function proxy(request: NextRequest) {
  if (process.env.SWITCH_DASHBOARD_SURFACE !== "web") {
    return NextResponse.next();
  }

  const { pathname } = request.nextUrl;
  if (pathname.startsWith("/_next") || PUBLIC_ASSET.test(pathname)) {
    return NextResponse.next();
  }

  if (pathname === "/") {
    return redirectToChat(request);
  }

  if (WEB_ALLOWED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))) {
    return NextResponse.next();
  }

  return redirectToChat(request);
}

function redirectToChat(request: NextRequest) {
  const url = request.nextUrl.clone();
  url.pathname = "/chat";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
