import { NextRequest, NextResponse } from "next/server";
import { getDocumentPages } from "@/lib/seedDb";

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string; versionId: string } }
) {
  const pages = getDocumentPages(params.id, params.versionId);
  return NextResponse.json(pages);
}

