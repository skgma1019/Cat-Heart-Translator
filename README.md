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

웹앱과 모델 API는 WAV 및 MP3 파일을 지원합니다. Android APK는 기존 WAV 입력을 유지합니다. 크기 0바이트 초과~10MB, 길이 0.5~60초이며 무음·손상 파일은 거부합니다. 임시 파일은 요청 후 삭제합니다. 모델은 서버 시작 시 한 번 로드하며 제공된 88개 특징을 그대로 사용합니다. StandardScaler는 모델 Pipeline에 포함되어 있습니다.

SVM의 `predict`와 `predict_proba` 순위가 다를 수 있으므로 대표 결과는 `predict_proba`의 최고값으로 선택합니다. 표시한 백분율은 세 상황에 대한 모델 추정 확률이며 정확도가 아닙니다. 모델은 고양이 울음 여부를 판별하지 않습니다. 평가 데이터는 21마리·440개 녹음, GroupKFold(5), 정확도 약 59.5%, Macro F1 약 0.517입니다.

검증: `cd frontend && npm run typecheck && npm run build`; API 실행 후 `curl http://127.0.0.1:8000/health`.

## 배포

프론트엔드는 Vercel에서 GitHub 저장소를 가져와 Root Directory를 `frontend`로 설정합니다. 환경 변수 `API_INTERNAL_URL`에 배포된 Python API의 HTTPS 기본 주소를 입력합니다. API는 저장소 루트의 `render.yaml`을 Render Blueprint로 배포할 수 있습니다. Render 서비스의 `/health`에서 모델 로드 상태를 먼저 확인한 뒤 그 URL을 Vercel에 설정하고 재배포합니다. Vercel은 Next.js 프론트만, Render는 모델 API만 실행합니다. `API_INTERNAL_URL`을 설정하지 않은 Vercel 배포는 분석 요청에 503을 반환합니다.

## Android 앱

`mobile/`은 Expo React Native 설치형 앱입니다. 파일 선택·미리 듣기·분석 요청·결과 표시를 구현했습니다. 앱 빌드에는 공개 HTTPS 모델 API가 필요합니다. 로컬 `localhost` API는 휴대폰에서 접근할 수 없습니다.

API를 배포한 뒤 기본 API 주소는 `https://cat-heart-translator-api.onrender.com`입니다. 다른 서버를 사용할 때만 `EXPO_PUBLIC_API_URL`을 지정하여 `cd mobile && npm ci && npm run typecheck`로 확인합니다. APK는 Expo 계정에 로그인한 뒤 `eas build --platform android --profile preview`로 생성합니다. 공개 배포용 AAB는 `--profile production`을 사용합니다. 앱의 서버 주소는 빌드에 포함되므로 API 주소를 바꾸면 재빌드해야 합니다.

## 3회차 웹앱 시연

`frontend/`에서 WAV/MP3 업로드 또는 브라우저 마이크 녹음을 선택합니다. 녹음은 브라우저의 `MediaRecorder` 출력(WebM/Opus 등)을 `AudioContext.decodeAudioData()`로 읽고, 모노 16비트 PCM WAV로 변환한 뒤 오디오 API에 보냅니다. 마이크 사용은 HTTPS 또는 localhost와 브라우저 권한이 필요합니다. 녹음은 59초에 자동 종료되며, 두 파일 형식의 업로드 제한은 10MB·0.5~60초입니다. 실제 형식과 확장자가 다르면 거부합니다. MP3는 제공된 soundfile/libsndfile와 librosa 버전으로 디코딩합니다. 미리 듣기 후 **분석하기**를 누르면 서버가 제공된 `extract_features()`로 88개 특징을 추출하고, 저장된 Pipeline의 `predict_proba()`를 호출합니다. 대표 상황은 최고 추정 확률의 클래스이며 막대그래프의 세 확률과 일치합니다. **다시 분석하기**로 새 입력을 선택할 수 있습니다.

과제의 일반적인 입력 예시에 이미지 업로드가 포함되어 있지만, 이 모델은 오디오 특징 88개만 받아들이므로 이미지 업로드는 제공하지 않습니다. 감정이나 말의 번역, 고양이 울음 여부 판별 기능도 제공하지 않습니다.

시연 영상은 1~2분 동안 서비스 소개 → WAV 파일 선택 또는 마이크 녹음 → 미리 듣기 → 분석 버튼 → 실제 모델 결과와 B/F/I 확률 막대그래프 → 다시 분석하기 순서로 보여주면 됩니다. 영상은 `.mp4`로 녹화하고 용량을 고려해 파일 대신 공유 링크를 제출합니다.

검증 기록: Chromium의 테스트 마이크로 실제 녹음한 출력을 WAV로 변환해 웹 화면에서 분석 결과까지 확인했습니다. 제공된 `B_CAN01_EU_FN_GIA01_208.wav` 업로드는 빗질 90%, 먹이 기다림 8%, 낯선 환경에서 혼자 있음 2%로 표시됐습니다. FastAPI는 빈 파일, 손상 파일, 무음, 0.5초 미만, 60초 초과, 10MB 초과, 잘못된 확장자를 모두 HTTP 400으로 거부했습니다. `npm run typecheck`와 `npm run build`가 통과했습니다. 실제 휴대폰 브라우저의 녹음 권한과 Safari 녹음 형식은 아직 검증하지 못했습니다.

## 제출 영상

[웹앱 시연 영상 다운로드 (.mp4, 67초)](https://github.com/skgma1019/Cat-Heart-Translator/raw/refs/heads/main/demo/webapp-demo.mp4). 브라우저 테스트 마이크 녹음과 데이터셋 WAV 업로드, 미리 듣기, 서버 모델 분석, B/F/I 확률 막대그래프, 다시 분석하기를 보여줍니다. 영상의 마이크 입력은 Chromium 테스트 장치로 만든 녹음이며, 업로드한 WAV는 제공된 데이터셋 파일입니다. 영상 녹화는 자동화된 브라우저에서 진행했고 실제 사용자의 마이크나 휴대폰 브라우저 녹음은 영상에 포함되지 않습니다.

MP3 추가 검증: 데이터셋 WAV를 MP3로 인코딩해 API 분석 HTTP 200과 결과 출력을 확인했습니다. WAV를 `.mp3`로 이름만 바꾼 파일은 HTTP 400으로 거부합니다. MP3는 손실 압축이므로 같은 원본 WAV와 모델 추정 확률이 달라질 수 있습니다.

웹앱의 MP3 파일은 브라우저에서 디코딩해 모노 PCM WAV로 변환한 뒤 API에 전송합니다. 따라서 Render API가 아직 WAV 전용 구버전이어도 웹 MP3 업로드가 동작합니다. 브라우저에서 MP3를 디코딩할 수 없으면 오류를 표시합니다.

1분 입력을 위해 브라우저 녹음과 MP3는 8kHz 모노 PCM WAV로 변환합니다. WAV 원본이 4MB를 초과할 때도 같은 변환을 적용해 Vercel 요청 크기를 줄입니다. 작은 WAV는 원본으로 전송하며 서버의 기존 `extract_features()`가 8kHz로 리샘플링합니다.

1분 제한 검증: 59초(48kHz, 약 5.5MB) WAV를 브라우저에서 약 0.94MB로 변환해 업로드했고 결과 화면이 표시됐습니다. 61초 WAV는 API가 HTTP 400으로 거부했습니다. 브라우저 마이크 녹음도 8kHz WAV 변환 후 분석됐습니다. `/health`의 `max_duration_seconds`가 `60`이면 새 API 배포가 적용된 것입니다. 기존 Android APK의 녹음 길이 제한은 이 웹앱 변경과 별개입니다.

### 시연용 웹 화면 개선 및 검증 (2026-10-30)

- 콘텐츠 너비 1100px, 데스크톱 입력·결과 2열 / 767px 이하 1열. 서비스 제목 36px, 카드 제목 22px, 대표 결과 24px, 본문 16px 이상, 버튼 높이 50px 이상.
- 파일 업로드와 마이크 녹음을 구분하고 파일명·플레이어·녹음 시간·분석 대기·오류 상태를 표시한다. WAV/MP3, 최대 10MB, 0.5~60초 제한은 현행 서버 기준과 일치한다. 녹음은 기존대로 59초 자동 종료한다.
- 대표 문구와 강조 막대는 `probabilities`의 동일한 최댓값을 기준으로 선택한다. 새 입력 및 분석 시작 시 이전 결과를 지우며 분석한 파일명도 표시한다.
- `cd frontend && npm run typecheck`, `npm run build` 통과.
- Chromium/Playwright에서 1920×1080, 1366×768, 390×844의 업로드 전·성공 화면을 검사했다. 두 데스크톱 크기에서 확률 그래프 하단은 약 571px이며 입력·핵심 결과가 함께 보였다. 세 크기 모두 가로 넘침 없음.
- 실제 B_CAN01_EU_FN_GIA01_208.wav로 Next.js 프록시 → 로컬 FastAPI → 저장 모델 예측 → 결과 표시를 확인했다. 가상 마이크의 녹음·종료·WAV 변환·미리 듣기도 확인했다.
- 브라우저에서 분석 중과 모의 서버 오류, 잘못된 파일 형식, 새 입력 시 결과 초기화, 대표 문구/최고 확률 일치를 확인했다. 서버 오류 모의 응답은 검사 중에만 사용했다.
- 실제 사용자 마이크 하드웨어, Safari, 배포된 Vercel 화면은 이번 로컬 검증에 포함하지 않았다.
