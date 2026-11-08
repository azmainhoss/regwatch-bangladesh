import { NextRequest, NextResponse } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  // Relationships are embedded directly in structured_payload
  return NextResponse.json([]);
}
