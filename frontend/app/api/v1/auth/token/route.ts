import { NextRequest, NextResponse } from "next/server";
import { authenticate } from "@/lib/seedDb";

export async function POST(request: NextRequest) {
  let username = "";
  let password = "";

  const contentType = request.headers.get("content-type") || "";
  if (contentType.includes("application/x-www-form-urlencoded")) {
    const formData = await request.formData();
    username = formData.get("username")?.toString() || "";
    password = formData.get("password")?.toString() || "";
  } else {
    try {
      const json = await request.json();
      username = json.username || "";
      password = json.password || "";
    } catch {
      // ignore
    }
  }

  const result = authenticate(username, password);
  return NextResponse.json(result);
}

