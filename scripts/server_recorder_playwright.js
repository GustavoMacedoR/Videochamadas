const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Usage: NODE_URL=http://localhost:8000 ROOM_URL=http://localhost:8000/client/rooms/ROOM_NAME DURATION=15000 node scripts/server_recorder_playwright.js

(async () => {
  const ROOM_URL = process.env.ROOM_URL;
  const UPLOAD_URL = (process.env.NODE_URL || 'http://localhost:8000') + '/api/recordings/';
  const DURATION = parseInt(process.env.DURATION || '15000', 10);
  if (!ROOM_URL) {
    console.error('Please set ROOM_URL env var');
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({
    // grant permissions for microphone/camera
    permissions: ['microphone', 'camera']
  });
  const page = await context.newPage();
  await page.goto(ROOM_URL);

  // inject media recorder in page context
  await page.evaluate(() => {
    window._recordBlobs = [];
    window._recorder = null;
    window._startServerRecording = async (recordVideoSelector) => {
      // find target element (video element or a container)
      const videoEl = document.querySelector(recordVideoSelector) || document.querySelector('video');
      if (!videoEl) throw new Error('Video element not found');

      // capture stream from element (includes audio if available)
      const stream = videoEl.captureStream ? videoEl.captureStream() : videoEl.mozCaptureStream();
      if (!stream) throw new Error('Unable to capture stream from video element');

      window._recordBlobs = [];
      window._recorder = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp8,opus' });
      window._recorder.ondataavailable = e => { if (e.data && e.data.size) window._recordBlobs.push(e.data); };
      window._recorder.start(1000); // emit dataavailable every 1s

      window._stopServerRecording = () => new Promise(resolve => {
        if (!window._recorder) return resolve(window._recordBlobs);
        window._recorder.onstop = () => resolve(window._recordBlobs);
        window._recorder.stop();
      });

      return true;
    };

    window._postRecordingToServer = async (uploadUrl, filename) => {
      if (!window._recordBlobs || window._recordBlobs.length === 0) return { error: 'no blobs' };
      const blob = new Blob(window._recordBlobs, { type: 'video/webm' });
      const fd = new FormData();
      fd.append('file', blob, filename || `recording-${Date.now()}.webm`);
      // post the blob
      const res = await fetch(uploadUrl, { method: 'POST', body: fd });
      const json = await res.json();
      return json;
    };
  });

  // start recording: you can pass selector to the video element to capture
  await page.evaluate(() => window._startServerRecording('video'));
  console.log('Recording started');

  await page.waitForTimeout(DURATION);

  console.log('Stopping recording');
  const blobs = await page.evaluate(() => window._stopServerRecording());
  // post to server from page context
  const result = await page.evaluate((uploadUrl) => window._postRecordingToServer(uploadUrl, `room-${Date.now()}.webm`), UPLOAD_URL);

  console.log('Upload result:', result);

  await context.close();
  await browser.close();
})();
