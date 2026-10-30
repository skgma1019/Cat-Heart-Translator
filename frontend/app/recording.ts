/** Decode the browser recording, then encode mono PCM WAV for the WAV-only API. */
export async function recordingToWav(chunks: BlobPart[], mimeType: string, filename = '마이크-녹음.wav'): Promise<File> {
  const context = new AudioContext();
  try {
    const decoded = await context.decodeAudioData(await new Blob(chunks, { type: mimeType }).arrayBuffer());
    if (decoded.duration < 0.5 || decoded.duration > 30) throw new Error('녹음 길이는 0.5~30초여야 합니다.');
    const samples = new Float32Array(decoded.length);
    for (let channel = 0; channel < decoded.numberOfChannels; channel++) {
      const source = decoded.getChannelData(channel);
      for (let i = 0; i < samples.length; i++) samples[i] += source[i] / decoded.numberOfChannels;
    }
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const label = (offset: number, value: string) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)); };
    label(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true);
    label(8, 'WAVE'); label(12, 'fmt '); view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, decoded.sampleRate, true); view.setUint32(28, decoded.sampleRate * 2, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    label(36, 'data'); view.setUint32(40, samples.length * 2, true);
    for (let i = 0; i < samples.length; i++) {
      const sample = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(44 + i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    }
    return new File([buffer], filename, { type: 'audio/wav' });
  } finally { await context.close(); }
}
