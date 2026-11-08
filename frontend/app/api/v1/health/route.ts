import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    app_name: "RegWatch Bangladesh",
    version: "1.0.0",
    environment: "production",
    timestamp: Date.now() / 1000,
  });
}
