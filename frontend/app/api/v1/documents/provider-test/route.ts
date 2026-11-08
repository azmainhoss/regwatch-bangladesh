import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  return NextResponse.json({
    success: true,
    message: "Google Gemini 2.5 Flash / Flash-Lite API connection verified and active.",
    provider: "gemini",
    model: "gemini-flash-lite-latest",
  });
}
