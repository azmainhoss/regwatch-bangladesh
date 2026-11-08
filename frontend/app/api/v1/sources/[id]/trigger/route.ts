import { NextRequest, NextResponse } from "next/server";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  return NextResponse.json({
    status: "TRIGGERED",
    source_id: params.id,
    message: "Continuous monitoring pipeline triggered for Bangladesh Bank source.",
  });
}
