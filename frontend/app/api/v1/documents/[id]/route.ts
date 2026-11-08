import { NextRequest, NextResponse } from "next/server";
import { getDocument } from "@/lib/seedDb";

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const doc = getDocument(params.id);
  if (!doc) {
    return NextResponse.json({ detail: "Document not found" }, { status: 404 });
  }
  return NextResponse.json(doc);
}
