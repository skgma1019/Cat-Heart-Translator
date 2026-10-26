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

다른 터미널에서 `cd frontend && npm run dev`. 브라우저에서 `http://localhost:3000`을 엽니다. 프론트 서버가 API 요청을 내부적으로 전달합니다. API 주소를 바꾸려면 프론트 실행 시 `API_INTERNAL_URL`을 지정합니다. 클라우드 미리보기에서는 3000번 포트만 열면 됩니다.

WAV 파일만 지원합니다. 크기 0바이트 초과~10MB, 길이 0.5~30초이며 무음·손상 파일은 거부합니다. 임시 파일은 요청 후 삭제합니다. 모델은 서버 시작 시 한 번 로드하며 제공된 88개 특징을 그대로 사용합니다. StandardScaler는 모델 Pipeline에 포함되어 있습니다.

SVM의 `predict`와 `predict_proba` 순위가 다를 수 있으므로 대표 결과는 `predict_proba`의 최고값으로 선택합니다. 표시한 백분율은 세 상황에 대한 모델 추정 확률이며 정확도가 아닙니다. 모델은 고양이 울음 여부를 판별하지 않습니다. 평가 데이터는 21마리·440개 녹음, GroupKFold(5), 정확도 약 59.5%, Macro F1 약 0.517입니다.

검증: `cd frontend && npm run typecheck && npm run build`; API 실행 후 `curl http://127.0.0.1:8000/health`.

## 배포

프론트엔드는 Vercel에서 GitHub 저장소를 가져와 Root Directory를 `frontend`로 설정합니다. 환경 변수 `API_INTERNAL_URL`에 배포된 Python API의 HTTPS 기본 주소를 입력합니다. API는 저장소 루트의 `render.yaml`을 Render Blueprint로 배포할 수 있습니다. Render 서비스의 `/health`에서 모델 로드 상태를 먼저 확인한 뒤 그 URL을 Vercel에 설정하고 재배포합니다. Vercel은 Next.js 프론트만, Render는 모델 API만 실행합니다. `API_INTERNAL_URL`을 설정하지 않은 Vercel 배포는 분석 요청에 503을 반환합니다.

## Android 앱

`mobile/`은 Expo React Native 설치형 앱입니다. 파일 선택·미리 듣기·분석 요청·결과 표시를 구현했습니다. 앱 빌드에는 공개 HTTPS 모델 API가 필요합니다. 로컬 `localhost` API는 휴대폰에서 접근할 수 없습니다.

API를 배포한 뒤 기본 API 주소는 `https://cat-heart-translator-api.onrender.com`입니다. 다른 서버를 사용할 때만 `EXPO_PUBLIC_API_URL`을 지정하여 `cd mobile && npm ci && npm run typecheck`로 확인합니다. APK는 Expo 계정에 로그인한 뒤 `eas build --platform android --profile preview`로 생성합니다. 공개 배포용 AAB는 `--profile production`을 사용합니다. 앱의 서버 주소는 빌드에 포함되므로 API 주소를 바꾸면 재빌드해야 합니다.
