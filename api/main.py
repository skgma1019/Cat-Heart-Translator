from contextlib import asynccontextmanager
from pathlib import Path
import json
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

@asynccontextmanager
async def lifespan(app):
    global model
    model = joblib.load(ROOT / 'catmeows_model.joblib')
    if list(model.classes_) != META['classes'] or model.n_features_in_ != META['feature_count']:
        raise RuntimeError('모델 클래스 또는 특징 수 불일치')
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
    if not file.filename or not file.filename.lower().endswith('.wav'):
        raise HTTPException(400, 'WAV 파일만 업로드할 수 있습니다.')
    data = await file.read(10 * 1024 * 1024 + 1)
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, '파일은 0바이트 초과, 10MB 이하여야 합니다.')
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            path = tmp.name
            tmp.write(data)
        info = sf.info(path)
        if info.duration < 0.5 or info.duration > 30:
            raise HTTPException(400, '녹음 길이는 0.5~30초여야 합니다.')
        audio, _ = sf.read(path, dtype='float32')
        if not np.isfinite(audio).all() or np.max(np.abs(audio)) < 0.0001:
            raise HTTPException(400, '무음 파일은 분석할 수 없습니다.')
        features = extract_features(path)
        if len(features) != META['feature_count'] or not np.isfinite(features).all():
            raise HTTPException(400, '오디오 특징을 추출할 수 없습니다.')
        probabilities = model.predict_proba(features.reshape(1, -1))[0]
        index = int(np.argmax(probabilities))
        return {'result': LABELS[model.classes_[index]], 'probabilities': [{'code': code, 'label': LABELS[code], 'probability': float(probabilities[i])} for i, code in enumerate(model.classes_)]}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, '손상되었거나 지원하지 않는 WAV 파일입니다.')
    finally:
        if path:
            os.unlink(path)
