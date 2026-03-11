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

async function postComplete(payload) {
  try {
    await fetch(`${API_BASE}/recordings/server/complete/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        room_name: ROOM_NAME,
        recording: payload || {},
      }),
    });
  } catch (_) {}
}

(async () => {
  let browser;
  let context;
  let page;

  try {
    browser = await chromium.launch({
      headless: true,
      args: ['--no-sandbox']
    });
    context = await browser.newContext({ permissions: ['microphone', 'camera'] });
    page = await context.newPage();

    await page.goto(ROOM_URL);
    await page.fill('#roomInput', ROOM_NAME);
    await page.click('#connectBtn');
    await page.waitForTimeout(5000);

    await page.evaluate(async ({ apiBase, uploadId, fileName, participants, roomName }) => {
    window.__serverUploadPromises = [];

    window.__serverPostChunk = async (chunkBlob, isLast) => {
      const fd = new FormData();
      fd.append('upload_id', uploadId);
      fd.append('filename', fileName);
      fd.append('room_name', roomName || '');
      fd.append('is_last', isLast ? '1' : '0');
      if (isLast) fd.append('participants', participants || '[]');
      if (chunkBlob) fd.append('chunk', chunkBlob, fileName);
      const res = await fetch(`${apiBase}/recordings/chunk/`, { method: 'POST', body: fd });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`);
      return json;
    };

    const waitForVideo = async () => {
      const timeoutAt = Date.now() + 15000;
      while (Date.now() < timeoutAt) {
        const remote = document.querySelector('#remoteContainer video');
        if (remote && remote.srcObject) return remote;
        const local = document.querySelector('#localVideo');
        if (local && local.srcObject) return local;
        await new Promise(resolve => setTimeout(resolve, 300));
      }
      return null;
    };

    const videoEl = await waitForVideo();
    if (!videoEl) throw new Error('Nenhum stream de vídeo disponível para gravar na sala.');

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
    roomName: ROOM_NAME,
    });

    const finalizeAndExit = async () => {
      if (stopping) return;
      stopping = true;

      try {
        const result = await page.evaluate(async () => {
          if (window.__serverRecorder && window.__serverRecorder.state !== 'inactive') {
            window.__serverRecorder.stop();
          }
          await new Promise(resolve => setTimeout(resolve, 1200));
          await Promise.all(window.__serverUploadPromises || []);
          return await window.__serverPostChunk(null, true);
        });
        await postComplete(result || {});
      } catch (err) {
        await postComplete({ error: err && err.message ? err.message : 'Falha ao finalizar gravação no servidor.' });
      }

      if (context) await context.close();
      if (browser) await browser.close();
      process.exit(0);
    };

    process.on('SIGTERM', finalizeAndExit);
    process.on('SIGINT', finalizeAndExit);
  } catch (err) {
    await postComplete({ error: err && err.message ? err.message : 'Falha ao iniciar gravador no servidor.' });
    if (context) await context.close();
    if (browser) await browser.close();
    process.exit(1);
  }
})();
