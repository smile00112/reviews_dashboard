import { NextResponse, type NextRequest } from "next/server";

// Fast cookie-presence gate. Authoritative validation happens server-side via
// GET /api/auth/me in the dashboard shell; this just avoids flashing protected
// pages for clearly-unauthenticated visitors. Starlette's SessionMiddleware
// stores the signed session in the "session" cookie.
const SESSION_COOKIE = "session";

export function middleware(req: NextRequest) {
  const hasSession = req.cookies.has(SESSION_COOKIE);
  if (!hasSession) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Guard everything except the login page, the API proxy, and static assets.
  matcher: ["/((?!login|api|_next/static|_next/image|favicon.ico).*)"],
};
