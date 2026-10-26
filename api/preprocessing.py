import numpy as np
import librosa
SR = 8000

def extract_features(path):
    y, sr = librosa.load(path, sr=SR)
    y_trim, _ = librosa.effects.trim(y, top_db=30)   # 앞뒤 무음 제거
    if len(y_trim) >= sr * 0.3:                      # 너무 짧아지면 원본 사용
        y = y_trim
    if len(y) < sr * 0.5:                            # 0.5초보다 짧으면 뒤를 0으로 채움
        y = np.pad(y, (0, int(sr * 0.5) - len(y)))
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    delta = librosa.feature.delta(mfcc, mode="nearest")
    cent = librosa.feature.spectral_centroid(y=y, sr=sr)   # 밝기
    zcr = librosa.feature.zero_crossing_rate(y)
    rms = librosa.feature.rms(y=y)                          # 크기
    f0 = librosa.yin(y, fmin=200, fmax=1500, sr=sr)          # 음높이
    feats = [mfcc.mean(1), mfcc.std(1), delta.mean(1), delta.std(1),
             [cent.mean(), cent.std(), zcr.mean(), rms.mean(), rms.std(),
              np.median(f0), f0.std(), len(y) / sr]]
    return np.concatenate([np.ravel(f) for f in feats])
