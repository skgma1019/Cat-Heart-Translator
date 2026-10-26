export const runtime = 'nodejs';

export async function POST(request: Request) {
  try {
    const body = await request.formData();
    const apiUrl = process.env.API_INTERNAL_URL || (process.env.VERCEL ? undefined : 'http://127.0.0.1:8000');
    if (!apiUrl) return Response.json({ detail: '분석 서버 주소가 설정되지 않았습니다.' }, { status: 503 });
    const response = await fetch(`${apiUrl}/analyze`, {
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
