import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

// Only the annotation tool requires sign-in — everything else is public.
const isProtectedRoute = createRouteMatcher(["/annotate(.*)"]);

// Clerk middleware throws "Missing publishableKey" when the key is absent, which
// 500s every route. The site is mostly public, so when Clerk is not configured
// we fall back to a pass-through that simply blocks the auth-gated routes.
const CLERK_ENABLED = /^pk_(test|live)_\w{20,}$/.test(
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "",
);

const clerk = clerkMiddleware(async (auth, req) => {
  if (isProtectedRoute(req)) {
    await auth.protect();
  }
});

export default CLERK_ENABLED
  ? clerk
  : (req: Parameters<typeof clerk>[0]) => {
      if (isProtectedRoute(req)) {
        const signIn = new URL("/sign-in", req.url);
        return NextResponse.redirect(signIn);
      }
      return NextResponse.next();
    };

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico)).*)",
    "/(api|trpc)(.*)",
  ],
};
