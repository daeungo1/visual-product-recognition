/**
 * Camera access of the AR demo. The only browser dependency is the `mediaDevices` object that is passed in.
 * Frames are never stored or sent anywhere; this module only opens and closes the stream.
 */

export const CAMERA_CONSTRAINTS = Object.freeze({
  video: Object.freeze({
    facingMode: Object.freeze({ ideal: 'environment' }),
    width: Object.freeze({ ideal: 1280 }),
    height: Object.freeze({ ideal: 720 }),
  }),
  audio: false,
});

/** Must be called from a user gesture. Resolves with a MediaStream or rejects with the browser error. */
export function openCamera(mediaDevices) {
  return mediaDevices.getUserMedia(CAMERA_CONSTRAINTS);
}

export function stopStream(stream) {
  if (!stream) return;
  for (const track of stream.getTracks()) track.stop();
}

const MESSAGES = Object.freeze({
  insecure: '카메라는 HTTPS 주소에서만 사용할 수 있습니다. 주소가 https:// 로 시작하는지 확인하세요.',
  unsupported: '이 브라우저는 카메라 접근을 지원하지 않습니다. 최신 Chrome(Android) 또는 Safari(iOS)에서 열어 주세요.',
  denied: '카메라 권한이 거부되었습니다. 주소창의 사이트 설정에서 카메라를 허용한 뒤 다시 시도하세요.',
  'not-found': '사용할 수 있는 카메라를 찾지 못했습니다.',
  busy: '카메라를 시작하지 못했습니다. 다른 앱이 카메라를 쓰고 있지 않은지 확인하세요.',
});

const BY_NAME = Object.freeze({
  NotAllowedError: 'denied',
  SecurityError: 'denied',
  PermissionDeniedError: 'denied',
  NotFoundError: 'not-found',
  DevicesNotFoundError: 'not-found',
  OverconstrainedError: 'not-found',
  ConstraintNotSatisfiedError: 'not-found',
  NotReadableError: 'busy',
  TrackStartError: 'busy',
  AbortError: 'busy',
});

/** User-facing reason (Korean) for a failed camera start. The raw error message is never shown or logged. */
export function describeCameraError(error, { secure = true, hasApi = true } = {}) {
  let code = 'unknown';
  if (!secure) code = 'insecure';
  else if (!hasApi) code = 'unsupported';
  else if (error && typeof error.name === 'string' && Object.prototype.hasOwnProperty.call(BY_NAME, error.name)) code = BY_NAME[error.name];
  if (code === 'unknown') {
    const name = error && typeof error.name === 'string' ? error.name.slice(0, 40) : 'UnknownError';
    return { code, message: `카메라를 시작하지 못했습니다. (${name})` };
  }
  return { code, message: MESSAGES[code] };
}
