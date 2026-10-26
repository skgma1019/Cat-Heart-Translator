# 냥심 번역기

고양이 울음 상황 분석 웹앱. `frontend/`는 Next.js App Router, TypeScript, Tailwind CSS 화면이고 `api/`는 FastAPI와 제공된 모델·전처리 파일입니다.

## 실행

Python 3.12와 Node.js 20 이상 필요. 저장소 루트에서:

```bash
python3 -m venv .venv
.venv/bin/pip install -r api/requirements.txt fastapi uvicorn python-multipart
(cd frontend && npm ci)
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

다른 터미널에서 `cd frontend && npm run dev`. 브라우저에서 `http://localhost:3000`을 엽니다. API 주소를 바꾸려면 프론트 실행 시 `NEXT_PUBLIC_API_URL`을 지정합니다.

WAV 파일만 지원합니다. 크기 0바이트 초과~10MB, 길이 0.5~30초이며 무음·손상 파일은 거부합니다. 임시 파일은 요청 후 삭제합니다. 모델은 서버 시작 시 한 번 로드하며 제공된 88개 특징을 그대로 사용합니다. StandardScaler는 모델 Pipeline에 포함되어 있습니다.

SVM의 `predict`와 `predict_proba` 순위가 다를 수 있으므로 대표 결과는 `predict_proba`의 최고값으로 선택합니다. 표시한 백분율은 세 상황에 대한 모델 추정 확률이며 정확도가 아닙니다. 모델은 고양이 울음 여부를 판별하지 않습니다. 평가 데이터는 21마리·440개 녹음, GroupKFold(5), 정확도 약 59.5%, Macro F1 약 0.517입니다.

검증: `cd frontend && npm run typecheck && npm run build`; API 실행 후 `curl http://127.0.0.1:8000/health`.
