import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CAMERA_CONSTRAINTS, describeCameraError, openCamera, stopStream } from '../assets/ar/camera.js';

test('the rear camera is preferred but never required, and audio is not requested', () => {
  const { video, audio } = CAMERA_CONSTRAINTS;
  assert.equal(audio, false);
  assert.deepEqual(video.facingMode, { ideal: 'environment' });
  assert.equal(JSON.stringify(CAMERA_CONSTRAINTS).includes('exact'), false, 'an exact constraint would fail on a device without a rear camera');
  assert.ok(video.width.ideal >= 640 && video.height.ideal >= 480);
});

test('openCamera forwards the constraints to getUserMedia and returns its stream', async () => {
  const stream = { id: 'fake' };
  const calls = [];
  const mediaDevices = { async getUserMedia(constraints) { calls.push(constraints); return stream; } };
  assert.equal(await openCamera(mediaDevices), stream);
  assert.deepEqual(calls, [CAMERA_CONSTRAINTS]);
});

test('openCamera passes a browser failure on unchanged', async () => {
  const failure = Object.assign(new Error('blocked'), { name: 'NotAllowedError' });
  await assert.rejects(openCamera({ getUserMedia: () => Promise.reject(failure) }), (error) => error === failure);
});

test('stopStream stops every track and tolerates a missing stream', () => {
  const stopped = [];
  const track = (name) => ({ stop: () => stopped.push(name) });
  stopStream({ getTracks: () => [track('video'), track('other')] });
  assert.deepEqual(stopped, ['video', 'other']);
  assert.doesNotThrow(() => stopStream(null));
  assert.doesNotThrow(() => stopStream(undefined));
  assert.doesNotThrow(() => stopStream({ getTracks: () => [] }));
});

test('every failure has a distinct, actionable Korean message', () => {
  const named = (name) => Object.assign(new Error('internal detail that must not be shown'), { name });
  const cases = [
    [named('NotAllowedError'), 'denied'],
    [named('SecurityError'), 'denied'],
    [named('PermissionDeniedError'), 'denied'],
    [named('NotFoundError'), 'not-found'],
    [named('DevicesNotFoundError'), 'not-found'],
    [named('OverconstrainedError'), 'not-found'],
    [named('NotReadableError'), 'busy'],
    [named('TrackStartError'), 'busy'],
    [named('AbortError'), 'busy'],
  ];
  const messages = new Map();
  for (const [error, code] of cases) {
    const described = describeCameraError(error);
    assert.equal(described.code, code, error.name);
    assert.match(described.message, /[가-힣]/);
    assert.equal(described.message.includes('internal detail'), false, 'raw error text is never shown');
    messages.set(code, described.message);
  }
  assert.equal(messages.size, 3, 'denied, not-found and busy are all covered');
  assert.equal(new Set(messages.values()).size, 3, 'each cause has its own message');
});

test('an insecure page or a missing API is reported before the error name', () => {
  const denied = Object.assign(new Error('x'), { name: 'NotAllowedError' });
  assert.equal(describeCameraError(denied, { secure: false }).code, 'insecure');
  assert.match(describeCameraError(denied, { secure: false }).message, /HTTPS/);
  assert.equal(describeCameraError(denied, { hasApi: false }).code, 'unsupported');
  assert.equal(describeCameraError(null, { secure: false, hasApi: false }).code, 'insecure');
});

test('an unknown error shows only its short name', () => {
  assert.deepEqual(describeCameraError(Object.assign(new Error('secret path C:\\x'), { name: 'WeirdError' })), {
    code: 'unknown', message: '카메라를 시작하지 못했습니다. (WeirdError)',
  });
  assert.equal(describeCameraError(undefined).code, 'unknown');
  assert.equal(describeCameraError('text').code, 'unknown');
  const long = describeCameraError(Object.assign(new Error('x'), { name: 'E'.repeat(500) }));
  assert.ok(long.message.length < 80);
  const inherited = describeCameraError(Object.assign(new Error('x'), { name: 'toString' }));
  assert.equal(inherited.code, 'unknown', 'prototype property names are not error names');
});
