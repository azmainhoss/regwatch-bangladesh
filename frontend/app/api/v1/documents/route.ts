import { NextRequest, NextResponse } from "next/server";
import { getDocuments } from "@/lib/seedDb";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const department_id = searchParams.get("department_id") || undefined;
  const institution_id = searchParams.get("institution_id") || undefined;
  const document_type = searchParams.get("document_type") || undefined;
  const search = searchParams.get("search") || undefined;
  const publication_status = searchParams.get("publication_status") || undefined;
  const corpus_type = searchParams.get("corpus_type") || undefined;
  const limit = parseInt(searchParams.get("limit") || "50", 10);
  const offset = parseInt(searchParams.get("offset") || "0", 10);

  const docs = getDocuments({
    department_id,
    institution_id,
    document_type,
    search,
    publication_status,
    corpus_type,
    limit,
    offset,
  });

  return NextResponse.json(docs);
}

