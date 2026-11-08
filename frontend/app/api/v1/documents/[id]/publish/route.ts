import { NextRequest, NextResponse } from "next/server";
import { getDocument } from "@/lib/seedDb";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const doc = getDocument(params.id);
  return NextResponse.json({
    document_id: params.id,
    publication_status: "PUBLISHED_HUMAN_REVIEWED",
    status_updated: true,
    message: "Document regulatory analysis approved and published by compliance officer.",
    document: doc,
  });
}

