import { NextRequest, NextResponse } from "next/server";
import { getDocumentProvisions } from "@/lib/seedDb";

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const provisions = getDocumentProvisions(params.id);
  return NextResponse.json(provisions);
}

