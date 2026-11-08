import { NextRequest, NextResponse } from "next/server";
import { authenticate } from "@/lib/seedDb";

export async function POST(request: NextRequest) {
  let email = "";
  let password = "";
  try {
    const json = await request.json();
    email = json.email || "";
    password = json.password || "";
  } catch {
    // ignore
  }

  const result = authenticate(email, password);
  return NextResponse.json(result);
}

