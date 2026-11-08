import { NextResponse } from "next/server";
import { getInstitutions } from "@/lib/seedDb";

export async function GET() {
  const data = getInstitutions();
  return NextResponse.json(data);
}
