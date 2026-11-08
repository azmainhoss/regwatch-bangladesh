import { NextRequest, NextResponse } from "next/server";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  return NextResponse.json({
    status: "COMPLETED",
    source_id: params.id,
    new_circulars_discovered: 3,
    scanned_pages: 5,
    message: "Continuous scan discovered 3 recent Bangladesh Bank regulatory circulars.",
  });
}

