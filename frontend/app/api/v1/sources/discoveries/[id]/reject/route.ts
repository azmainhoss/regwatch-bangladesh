import { NextRequest, NextResponse } from "next/server";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  return NextResponse.json({
    discovery_id: params.id,
    status: "REJECTED",
    message: "Discovered circular rejected.",
  });
}

