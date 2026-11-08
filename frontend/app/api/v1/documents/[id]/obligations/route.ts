import { NextRequest, NextResponse } from "next/server";
import { getDocumentObligations } from "@/lib/seedDb";

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const obligations = getDocumentObligations(params.id);
  return NextResponse.json(obligations);
}
