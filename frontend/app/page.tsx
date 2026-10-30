'use client';
import { useEffect, useRef, useState } from 'react';
import { recordingToWav } from './recording';
type Result = { result: string; probabilities: { code: string; label: string; probability: number }[] };
export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (!file) { setUrl(''); return; }
    const next = URL.createObjectURL(file); setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [file]);
  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
    if (recorder.current?.state === 'recording') recorder.current.stop();
    stream.current?.getTracks().forEach(track => track.stop());
  }, []);
  function choose(next?: File) {
    setResult(null); setError('');
    if (!next) { setFile(null); return; }
    if (!/\.(wav|mp3)$/i.test(next.name) || next.size === 0 || next.size > 10 * 1024 * 1024) {
      setFile(null); setError('0바이트 초과, 10MB 이하의 WAV 또는 MP3 파일을 선택해 주세요.'); return;
    }
    setFile(next);
  }
  async function startRecording() {
    setError(''); setResult(null); setFile(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined' || typeof AudioContext === 'undefined') {
      setError('이 브라우저는 마이크 녹음을 지원하지 않습니다. WAV 파일을 업로드해 주세요.'); return;
    }
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true }); stream.current = mic;
      const next = new MediaRecorder(mic); const chunks: BlobPart[] = [];
      next.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      next.onerror = () => setError('녹음 중 오류가 발생했습니다. 다시 시도해 주세요.');
      next.onstop = async () => {
        mic.getTracks().forEach(track => track.stop()); stream.current = null;
        if (timer.current) clearInterval(timer.current); timer.current = null; setRecording(false);
        try { choose(await recordingToWav(chunks, next.mimeType)); }
        catch { setError('녹음을 WAV로 변환할 수 없습니다. WAV 파일을 업로드하거나 다른 브라우저에서 시도해 주세요.'); }
      };
      recorder.current = next; setSeconds(0); setRecording(true); next.start();
      timer.current = setInterval(() => setSeconds(current => {
        if (current >= 58) { if (next.state === 'recording') next.stop(); return 59; }
        return current + 1;
      }), 1000);
    } catch {
      stream.current?.getTracks().forEach(track => track.stop());
      setError('마이크 사용을 허용해 주세요. 마이크 녹음은 HTTPS 또는 localhost에서 사용할 수 있습니다.');
    }
  }
  function stopRecording() { if (recorder.current?.state === 'recording') recorder.current.stop(); }
  async function analyze() {
    if (!file) return; setLoading(true); setError(''); setResult(null);
    const body = new FormData();
    try {
      let upload = file;
      if (/\.mp3$/i.test(file.name) || file.size > 4 * 1024 * 1024) {
        try { upload = await recordingToWav([file], file.type || (/\.mp3$/i.test(file.name) ? 'audio/mpeg' : 'audio/wav'), file.name.replace(/\.(mp3|wav)$/i, '.wav')); }
        catch { throw new Error('오디오 파일을 읽을 수 없습니다. 형식과 길이(최대 60초)를 확인해 주세요.'); }
      }
      if (upload.size > 10 * 1024 * 1024) throw new Error('변환된 오디오가 10MB를 초과합니다. 더 짧은 파일을 선택해 주세요.');
      body.append('file', upload);
      const response = await fetch('/api/analyze', { method: 'POST', body }); const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '분석에 실패했습니다.'); setResult(data);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'MP3 변환 또는 서버 연결 중 오류가 발생했습니다.'); }
    finally { setLoading(false); }
  }
  const top = result?.probabilities.reduce((best, item) => item.probability > best.probability ? item : best);
  const phrases: Record<string, string> = { B: '빗질하던', F: '먹이를 기다리던', I: '낯선 환경에서 혼자 있던' };
  return <main className="app-shell">
    <header className="service-header"><h1>냥심 번역기</h1><p className="subtitle">고양이 울음 상황 분석</p><p>울음을 입력하고, 학습한 세 녹음 상황과 얼마나 유사한지 확인하세요.</p></header>
    <div className="workspace-grid">
    <section className="panel" aria-labelledby="input-title">
      <h2 id="input-title">울음 입력</h2>
      <label className={`upload-zone ${recording || loading ? 'unavailable' : ''}`}>
        <span className="input-label">파일 업로드</span>
        <span className="upload-title">{file ? file.name : 'WAV 또는 MP3 파일 선택'}</span>
        <span className="help-text">최대 10MB · 길이 0.5~60초<br />빈 파일·손상된 오디오·무음 파일 제외</span>
        <input key={file ? 'selected' : 'empty'} type="file" accept=".wav,.mp3,audio/wav,audio/mpeg" disabled={recording || loading} onChange={event => choose(event.target.files?.[0])} aria-label="WAV 또는 MP3 파일 선택" />
      </label>
      <div className="recording-section"><p className="input-label">또는 마이크 녹음</p>
      <button type="button" disabled={loading} onClick={recording ? stopRecording : startRecording} className="button secondary full">{recording ? '■ 녹음 끝내기' : '마이크로 녹음하기'}</button>
      {recording && <p role="status" className="recording-status">● 녹음 중 <strong>{String(Math.floor(seconds / 60)).padStart(2, '0')}:{String(seconds % 60).padStart(2, '0')}</strong><span>59초에 자동 종료됩니다.</span></p>}</div>
      {url && <div className="audio-preview"><p className="input-label">미리 듣기</p><p className="filename">{file?.name}</p><audio src={url} controls aria-label="선택한 오디오 미리 듣기" /></div>}
      <button type="button" disabled={!file || loading || recording} onClick={analyze} className="button primary full analyze-button">{loading ? '울음 분석 중…' : '분석하기'}</button>
      {loading && <p role="status" className="analysis-status">오디오 처리 → 특징 88개 추출 → 모델 예측<br />서버 응답을 기다리고 있습니다.</p>}
      {error && <p role="alert" className="error-message">{error}</p>}
    </section>
    <section className="panel result-panel" aria-labelledby="result-title" aria-busy={loading}>
      <h2 id="result-title">분석 결과</h2>
      {result && top ? <>
        <p className="result-headline">{phrases[top.code] || top.label} 상황의 울음과 가장 유사합니다.</p>
        <p className="filename analyzed-file">분석한 파일: {file?.name}</p>
        <h3 className="chart-title">모델 추정 확률</h3>
        <div className="probability-chart">{result.probabilities.map(item => <div key={item.code} className={`probability-item ${item.code === top.code ? 'highest' : ''}`}>
          <div className="probability-label"><span>{item.label} <span className="class-code">{item.code}</span>{item.code === top.code && <span className="highest-badge">가장 유사</span>}</span><strong>{Math.round(item.probability * 100)}%</strong></div>
          <div className="probability-track" role="meter" aria-label={`${item.label} 모델 추정 확률`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(item.probability * 100)}><div style={{ width: `${item.probability * 100}%` }} /></div>
        </div>)}</div>
        <p className="result-notice">학습한 세 상황 중 비교한 참고 결과이며 실제 상황과 다를 수 있습니다.</p>
        <button type="button" disabled={loading || recording} onClick={() => { setFile(null); setResult(null); setError(''); }} className="button secondary full reset-button">다시 분석하기</button>
      </> : <div className="result-placeholder" aria-live="polite"><h3>{loading ? '울음의 특징을 분석하고 있습니다' : '이렇게 이용하세요'}</h3><ol><li>WAV·MP3 파일을 선택하거나 마이크로 녹음하세요.</li><li>미리 듣기로 오디오를 확인하고 분석하기를 누르세요.</li><li>가장 유사한 상황과 세 상황의 모델 추정 확률을 확인하세요.</li></ol><p>비교 상황: 빗질 · 먹이 기다림 · 낯선 환경에서 혼자 있음</p></div>}
    </section>
    </div>
  </main>;
}
