const { chromium } = require('playwright');

const ROOM_URL = process.env.ROOM_URL;
const API_BASE = process.env.API_BASE;
const ROOM_NAME = process.env.ROOM_NAME || 'testroom';
const UPLOAD_ID = process.env.UPLOAD_ID;
const FILE_NAME = process.env.FILE_NAME || `recording-${Date.now()}.webm`;
const PARTICIPANTS = process.env.PARTICIPANTS_JSON || '[]';

if (!ROOM_URL || !API_BASE || !UPLOAD_ID) {
  console.error('Missing required env vars: ROOM_URL, API_BASE, UPLOAD_ID');
  process.exit(1);
}

let stopping = false;

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream']
  });
  const context = await browser.newContext({ permissions: ['microphone', 'camera'] });
  const page = await context.newPage();

  await page.goto(ROOM_URL);
  await page.fill('#roomInput', ROOM_NAME);
  await page.click('#connectBtn');
  await page.waitForTimeout(4000);

  await page.evaluate(async ({ apiBase, uploadId, fileName, participants }) => {
    window.__serverUploadPromises = [];

    window.__serverPostChunk = async (chunkBlob, isLast) => {
      const fd = new FormData();
      fd.append('upload_id', uploadId);
      fd.append('filename', fileName);
      fd.append('is_last', isLast ? '1' : '0');
      if (isLast) fd.append('participants', participants || '[]');
      if (chunkBlob) fd.append('chunk', chunkBlob, fileName);
      const res = await fetch(`${apiBase}/recordings/chunk/`, { method: 'POST', body: fd });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`);
      return json;
    };

    const videoEl = document.querySelector('#remoteContainer video') || document.querySelector('video');
    if (!videoEl) throw new Error('Nenhum elemento de video para gravar.');

    const stream = videoEl.captureStream ? videoEl.captureStream() : (videoEl.mozCaptureStream ? videoEl.mozCaptureStream() : null);
    if (!stream) throw new Error('Falha ao capturar stream.');

    window.__serverRecorder = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp8,opus' });
    window.__serverRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size) {
        const p = window.__serverPostChunk(event.data, false);
        window.__serverUploadPromises.push(p);
      }
    };
    window.__serverRecorder.start(1000);
  }, {
    apiBase: API_BASE,
    uploadId: UPLOAD_ID,
    fileName: FILE_NAME,
    participants: PARTICIPANTS,
  });

  const finalizeAndExit = async () => {
    if (stopping) return;
    stopping = true;

    try {
      await page.evaluate(async () => {
        if (window.__serverRecorder && window.__serverRecorder.state !== 'inactive') {
          window.__serverRecorder.stop();
        }
        await new Promise(resolve => setTimeout(resolve, 1200));
        await Promise.all(window.__serverUploadPromises || []);
        await window.__serverPostChunk(null, true);
      });
    } catch (err) {
      console.error('Finalize error:', err.message || err);
    }

    await context.close();
    await browser.close();
    process.exit(0);
  };

  process.on('SIGTERM', finalizeAndExit);
  process.on('SIGINT', finalizeAndExit);
})();
