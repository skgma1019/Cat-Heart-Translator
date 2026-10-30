from contextlib import asynccontextmanager
from pathlib import Path
import json
import logging
import os
import tempfile

import joblib
import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from .preprocessing import extract_features

ROOT = Path(__file__).parent
META = json.loads((ROOT / 'model_metadata.json').read_text())
LABELS = {'B': '빗질', 'F': '먹이 기다림', 'I': '낯선 환경에서 혼자 있음'}
model = None
logger = logging.getLogger("uvicorn.error")

@asynccontextmanager
async def lifespan(app):
    global model
    model = joblib.load(ROOT / 'catmeows_model.joblib')
    if list(model.classes_) != META['classes'] or model.n_features_in_ != META['feature_count']:
        raise RuntimeError('모델 클래스 또는 특징 수 불일치')
    # Prepare librosa's first-call work before the service is marked healthy.
    warmup_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as warmup:
            warmup_path = warmup.name
            sf.write(warmup, np.sin(2 * np.pi * 440 * np.arange(4000) / 8000).astype('float32'), 8000)
        warmup_features = extract_features(warmup_path)
        model.predict_proba(warmup_features.reshape(1, -1))
    finally:
        if warmup_path:
            os.unlink(warmup_path)
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3000', 'http://127.0.0.1:3000'], allow_methods=['GET', 'POST'], allow_headers=['*'])

@app.get('/')
def home():
    return {'service': '냥심 번역기 모델 API', 'status': 'ok', 'health': '/health', 'docs': '/docs'}

@app.get('/health')
def health():
    return {'status': 'ok', 'features': model.n_features_in_, 'classes': list(model.classes_)}

@app.post('/analyze')
async def analyze(file: UploadFile = File(...)):
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in {'.wav', '.mp3'}:
        raise HTTPException(400, 'WAV 또는 MP3 파일만 업로드할 수 있습니다.')
    data = await file.read(10 * 1024 * 1024 + 1)
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, '파일은 0바이트 초과, 10MB 이하여야 합니다.')
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            path = tmp.name
            tmp.write(data)
        logger.info('analyze: validating audio')
        info = sf.info(path)
        if info.format != {'.wav': 'WAV', '.mp3': 'MP3'}[suffix]:
            raise HTTPException(400, '파일 확장자와 실제 오디오 형식이 일치하지 않습니다.')
        if info.duration < 0.5 or info.duration > 30:
            raise HTTPException(400, '녹음 길이는 0.5~30초여야 합니다.')
        audio, _ = sf.read(path, dtype='float32')
        if not np.isfinite(audio).all() or np.max(np.abs(audio)) < 0.0001:
            raise HTTPException(400, '무음 파일은 분석할 수 없습니다.')
        logger.info('analyze: extracting features')
        features = extract_features(path)
        logger.info('analyze: features extracted')
        if len(features) != META['feature_count'] or not np.isfinite(features).all():
            raise HTTPException(400, '오디오 특징을 추출할 수 없습니다.')
        probabilities = model.predict_proba(features.reshape(1, -1))[0]
        logger.info('analyze: prediction complete')
        index = int(np.argmax(probabilities))
        return {'result': LABELS[model.classes_[index]], 'probabilities': [{'code': code, 'label': LABELS[code], 'probability': float(probabilities[i])} for i, code in enumerate(model.classes_)]}
    except HTTPException:
        raise
    except Exception:
        logger.exception('analyze: failed')
        raise HTTPException(400, '손상되었거나 지원하지 않는 오디오 파일입니다.')
    finally:
        if path:
            os.unlink(path)
