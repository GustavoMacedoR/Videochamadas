const { chromium } = require('playwright');

const ROOM_URL = process.env.ROOM_URL;
const API_BASE = process.env.API_BASE;
const ROOM_NAME = process.env.ROOM_NAME || 'testroom';
const UPLOAD_ID = process.env.UPLOAD_ID;
const FILE_NAME = process.env.FILE_NAME || `recording-${Date.now()}.webm`;
const PARTICIPANTS = process.env.PARTICIPANTS_JSON || '[]';
const RECORDER_NAME = process.env.RECORDER_NAME || 'Gravador';
const RECORDER_ROLE = process.env.RECORDER_ROLE || 'gravador';

if (!ROOM_URL || !API_BASE || !UPLOAD_ID) {
  console.error('Missing required env vars: ROOM_URL, API_BASE, UPLOAD_ID');
  process.exit(1);
}

console.log('[recorder] Starting with:', { ROOM_URL, API_BASE, ROOM_NAME, UPLOAD_ID, FILE_NAME });

let stopping = false;
let shutdownRequested = false;
let startupComplete = false;
let browser;
let context;
let page;

async function cleanupResources() {
  if (context) {
    try {
      await context.close();
    } catch (_) {}
    context = null;
  }

  if (browser) {
    try {
      await browser.close();
    } catch (_) {}
    browser = null;
  }
}

function ensureStartupNotInterrupted() {
  if (shutdownRequested) {
    throw new Error('Gravação interrompida antes de iniciar a captura.');
  }
}

async function finalizeAndExit() {
  if (stopping) return;
  if (!startupComplete) {
    shutdownRequested = true;
    return;
  }

  stopping = true;

  try {
    const result = await page.evaluate(async () => {
      // Stop canvas draw & audio-check intervals
      if (window.__serverGridInterval) clearInterval(window.__serverGridInterval);
      if (window.__serverAudioCheckInterval) clearInterval(window.__serverAudioCheckInterval);

      const finalizeUpload = async () => {
        await new Promise(resolve => setTimeout(resolve, 1200));
        await Promise.all(window.__serverUploadPromises || []);
        return await window.__serverPostChunk(null, true);
      };

      if (window.__serverRecorder && window.__serverRecorder.state !== 'inactive') {
        window.__serverRecorder.stop();
        return await finalizeUpload();
      }

      if ((window.__serverUploadPromises || []).length > 0) {
        return await finalizeUpload();
      }

      throw new Error('Gravação interrompida antes de iniciar a captura.');
    });
    await postComplete(result || {});
  } catch (err) {
    console.error('[recorder] page.evaluate failed:', err && err.message ? err.message : err);
    // Browser closed before we could finalize via page — send is_last=1 directly from Node
    const fallbackResult = await finalizeUploadFromNode();
    await postComplete(fallbackResult);
  }

  await cleanupResources();
  process.exit(0);
}

function requestShutdown() {
  shutdownRequested = true;
  if (startupComplete) {
    void finalizeAndExit();
  }
}

process.on('SIGTERM', requestShutdown);
process.on('SIGINT', requestShutdown);

async function finalizeUploadFromNode() {
  console.log('[recorder] Fallback: finalizing upload directly from Node.js');
  try {
    const params = new URLSearchParams();
    params.append('upload_id', UPLOAD_ID);
    params.append('filename', FILE_NAME);
    params.append('room_name', ROOM_NAME);
    params.append('is_last', '1');
    params.append('participants', PARTICIPANTS);
    const res = await fetch(`${API_BASE}/recordings/chunk/`, {
      method: 'POST',
      body: params,
    });
    const json = await res.json().catch(() => ({}));
    console.log('[recorder] Fallback finalize response:', res.status, JSON.stringify(json));
    if (!res.ok) {
      return { error: json.error || `HTTP ${res.status}` };
    }
    return json;
  } catch (err) {
    console.error('[recorder] Fallback finalize FAILED:', err && err.message ? err.message : err);
    return { error: err && err.message ? err.message : 'Falha ao finalizar upload via fallback.' };
  }
}

async function postComplete(payload) {
  console.log('[recorder] postComplete:', JSON.stringify(payload));
  try {
    const res = await fetch(`${API_BASE}/recordings/server/complete/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        room_name: ROOM_NAME,
        recording: payload || {},
      }),
    });
    const text = await res.text().catch(() => '');
    console.log('[recorder] postComplete response:', res.status, text);
  } catch (err) {
    console.error('[recorder] postComplete FAILED:', err && err.message ? err.message : err);
  }
}

(async () => {
  try {
    browser = await chromium.launch({
      headless: true,
      args: ['--no-sandbox']
    });
    ensureStartupNotInterrupted();
    context = await browser.newContext({ permissions: ['microphone', 'camera'] });
    ensureStartupNotInterrupted();
    page = await context.newPage();
    ensureStartupNotInterrupted();

    // Forward browser console to Node stdout for debugging
    page.on('console', msg => console.log('[page]', msg.type(), msg.text()));
    page.on('pageerror', err => console.error('[page error]', err.message));
    page.on('requestfailed', req => console.error('[page req failed]', req.url(), req.failure()?.errorText));

    // Build URL with recorder name and role as query params
    const recorderUrl = new URL(ROOM_URL);
    recorderUrl.searchParams.set('room', ROOM_NAME);
    recorderUrl.searchParams.set('name', RECORDER_NAME);
    recorderUrl.searchParams.set('role', RECORDER_ROLE);
    console.log('[recorder] Navigating to', recorderUrl.href);
    await page.goto(recorderUrl.href);
    ensureStartupNotInterrupted();
    console.log('[recorder] Page loaded, filling room input:', ROOM_NAME);
    await page.fill('#chatNameInput', RECORDER_NAME);
    await page.fill('#roomInput', ROOM_NAME);
    ensureStartupNotInterrupted();
    await page.click('#connectBtn');
    console.log('[recorder] Clicked connect, waiting 5s for room setup...');
    await page.waitForTimeout(5000);
    ensureStartupNotInterrupted();

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

    // -- Canvas grid compositing: record ALL participants --
    const CANVAS_W = 1280;
    const CANVAS_H = 720;
    const canvas = document.createElement('canvas');
    canvas.width = CANVAS_W;
    canvas.height = CANVAS_H;
    const ctx = canvas.getContext('2d');

    function getAllVideos() {
      const vids = [];
      const local = document.querySelector('#localVideo');
      if (local && local.srcObject) vids.push(local);
      document.querySelectorAll('#remoteContainer video').forEach(v => {
        if (v.srcObject) vids.push(v);
      });
      return vids;
    }

    // Wait until at least one video stream is available
    const waitForAnyVideo = async () => {
      const timeoutAt = Date.now() + 15000;
      while (Date.now() < timeoutAt) {
        if (getAllVideos().length > 0) return true;
        await new Promise(resolve => setTimeout(resolve, 300));
      }
      return false;
    };

    const hasVideo = await waitForAnyVideo();
    if (!hasVideo) throw new Error('Nenhum stream de vídeo disponível para gravar na sala.');

    // Draw grid layout onto canvas at ~30fps
    function drawFrame() {
      const videos = getAllVideos();
      const n = videos.length || 1;
      const cols = Math.ceil(Math.sqrt(n));
      const rows = Math.ceil(n / cols);
      const cellW = CANVAS_W / cols;
      const cellH = CANVAS_H / rows;

      ctx.fillStyle = '#1a1a1a';
      ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

      videos.forEach((v, i) => {
        const col = i % cols;
        const row = Math.floor(i / cols);
        const x = col * cellW;
        const y = row * cellH;
        try {
          ctx.drawImage(v, x, y, cellW, cellH);
        } catch (_) {}
      });
    }

    window.__serverGridInterval = setInterval(drawFrame, 33); // ~30fps
    drawFrame();

    // Capture canvas stream with audio mixed from all videos
    const audioCtx = new AudioContext();
    const destination = audioCtx.createMediaStreamDestination();
    let audioAttached = 0;

    function attachAudioSources() {
      const videos = getAllVideos();
      videos.forEach(v => {
        if (v.__audioAttached) return;
        try {
          const src = audioCtx.createMediaElementSource(v);
          src.connect(destination);
          src.connect(audioCtx.destination); // keep audible in browser too
          v.__audioAttached = true;
          audioAttached++;
        } catch (_) {} // already attached or no audio track
      });
    }

    attachAudioSources();
    // Periodically check for new participants joining
    window.__serverAudioCheckInterval = setInterval(attachAudioSources, 2000);

    const canvasStream = canvas.captureStream(30);
    // Add mixed audio track to the canvas stream
    destination.stream.getAudioTracks().forEach(t => canvasStream.addTrack(t));

    window.__serverRecorder = new MediaRecorder(canvasStream, { mimeType: 'video/webm;codecs=vp8,opus' });
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
    startupComplete = true;
    if (shutdownRequested) {
      await finalizeAndExit();
    }
  } catch (err) {
    await postComplete({ error: err && err.message ? err.message : 'Falha ao iniciar gravador no servidor.' });
    await cleanupResources();
    process.exit(1);
  }
})();
