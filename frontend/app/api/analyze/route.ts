export const runtime = 'nodejs';

export async function POST(request: Request) {
  try {
    const body = await request.formData();
    const response = await fetch(`${process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000'}/analyze`, {
      method: 'POST',
      body,
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { 'content-type': 'application/json' },
    });
  } catch {
    return Response.json({ detail: '분석 서버에 연결할 수 없습니다.' }, { status: 502 });
  }
}
