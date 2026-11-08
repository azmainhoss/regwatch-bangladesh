import { NextRequest, NextResponse } from "next/server";

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const body = await request.json().catch(() => ({}));
  return NextResponse.json({
    id: params.id,
    is_active: body.is_active ?? true,
    message: "Source status updated successfully.",
  });
}

