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
    if (!next.name.toLowerCase().endsWith('.wav') || next.size === 0 || next.size > 10 * 1024 * 1024) {
      setFile(null); setError('0바이트 초과, 10MB 이하의 WAV 파일을 선택해 주세요.'); return;
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
        if (current >= 28) { if (next.state === 'recording') next.stop(); return 29; }
        return current + 1;
      }), 1000);
    } catch {
      stream.current?.getTracks().forEach(track => track.stop());
      setError('마이크 사용을 허용해 주세요. 마이크 녹음은 HTTPS 또는 localhost에서 사용할 수 있습니다.');
    }
  }
  function stopRecording() { if (recorder.current?.state === 'recording') recorder.current.stop(); }
  async function analyze() {
    if (!file) return; setLoading(true); setError('');
    const body = new FormData(); body.append('file', file);
    try {
      const response = await fetch('/api/analyze', { method: 'POST', body }); const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '분석에 실패했습니다.'); setResult(data);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '서버 오류가 발생했습니다.'); }
    finally { setLoading(false); }
  }
  return <main className="mx-auto max-w-3xl px-5 py-12 sm:py-20">
    <header className="mb-10"><p className="mb-3 font-bold tracking-widest text-[#a4664f]">CAT SOUND LAB</p><h1 className="text-5xl font-bold sm:text-6xl">냥심 번역기</h1><p className="mt-5 text-xl text-[#6f6258]">고양이 울음 상황 분석</p><p className="mt-3 leading-7 text-[#6f6258]">녹음된 울음을 빗질, 먹이 기다림, 낯선 환경에서 혼자 있음의 세 상황과 비교합니다.</p></header>
    <section className="rounded-3xl border border-[#eadbc9] bg-white p-6 shadow-sm sm:p-9">
      <h2 className="mb-4 text-2xl font-bold">울음 입력</h2>
      <label className="block cursor-pointer rounded-2xl border-2 border-dashed border-[#cfaa8d] bg-[#fffaf4] p-8 text-center"><span className="block text-lg font-semibold">{file ? file.name : 'WAV 파일 선택'}</span><span className="mt-2 block text-sm text-[#76675c]">최대 10MB · 길이 0.5~30초 · 무음 파일 제외</span><input className="sr-only" type="file" accept=".wav,audio/wav" disabled={recording || loading} onChange={event => choose(event.target.files?.[0])} /></label>
      <p className="my-5 text-center text-sm text-[#76675c]">또는</p>
      <button type="button" disabled={loading} onClick={recording ? stopRecording : startRecording} className="w-full rounded-xl border border-[#b58a72] px-6 py-4 font-bold text-[#6c4435] disabled:opacity-50">{recording ? `■ 녹음 끝내기 · ${seconds}초` : '● 마이크로 녹음하기'}</button>
      {recording && <p role="status" className="mt-3 text-center text-sm text-[#9f654e]">녹음 중입니다. 최대 29초에 자동 종료됩니다.</p>}
      {url && <audio className="mt-6 w-full" src={url} controls aria-label="선택한 오디오 미리 듣기" />}
      <button type="button" disabled={!file || loading || recording} onClick={analyze} className="mt-6 w-full rounded-xl bg-[#9f654e] px-6 py-4 font-bold text-white disabled:opacity-50">{loading ? '분석 중…' : '분석하기'}</button>
      {error && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-4 text-red-700">{error}</p>}
    </section>
    {result && <section className="mt-8 rounded-3xl border border-[#eadbc9] bg-white p-6 shadow-sm sm:p-9"><h2 className="text-2xl font-bold">{result.result} 상황의 울음과 가장 유사합니다</h2><p className="mt-2 text-sm text-[#76675c]">제공된 모델의 특징 88개로 세 녹음 상황을 비교한 결과입니다.</p><div className="mt-7 space-y-5">{result.probabilities.map(item => <div key={item.code}><div className="mb-2 flex justify-between"><span>{item.label}</span><strong>{Math.round(item.probability * 100)}%</strong></div><div className="h-3 rounded-full bg-[#f0e7dc]"><div className="h-3 rounded-full bg-[#a66d54]" style={{ width: `${item.probability * 100}%` }} /></div></div>)}</div><p className="mt-7 text-sm leading-6 text-[#76675c]">세 상황 중 비교한 참고 결과이며 실제 상황과 다를 수 있습니다. 백분율은 모델 추정 확률입니다.</p><button type="button" onClick={() => { setFile(null); setResult(null); setError(''); }} className="mt-6 rounded-xl border border-[#b58a72] px-5 py-3 font-semibold">다시 분석하기</button></section>}
  </main>;
}
