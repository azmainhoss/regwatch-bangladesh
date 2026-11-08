import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const authHeader = request.headers.get("authorization") || "";
  const isSuper = authHeader.includes("admin");

  return NextResponse.json({
    id: "active-user-session",
    email: isSuper ? "admin@regwatch.bd" : "cco@nationalbank.bd",
    full_name: isSuper ? "System Administrator" : "Mahmudur Rahman, CCO",
    is_superuser: isSuper,
    is_active: true,
  });
}

