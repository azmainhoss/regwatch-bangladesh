import { NextRequest, NextResponse } from "next/server";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  return NextResponse.json({
    discovery_id: params.id,
    status: "APPROVED",
    message: "Discovered circular approved and scheduled for automated extraction.",
  });
}
