"""Mobile browser capture and Overlay experiment."""

MOBILE_DEMO_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Visual Product Guide PoC</title>
  <style>
    :root { color-scheme: light; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #f3f5f7; color: #101828; }
    main { max-width: 720px; margin: auto; padding: 16px; }
    h1 { font-size: 1.45rem; margin: 8px 0; }
    .notice { background: #fff4e5; border: 1px solid #f6c766; padding: 12px; border-radius: 12px; }
    label { display: block; margin-top: 14px; font-weight: 700; }
    input, textarea, button { box-sizing: border-box; width: 100%; font: inherit; }
    input, textarea { margin-top: 6px; padding: 12px; border: 1px solid #98a2b3; border-radius: 10px; }
    textarea { min-height: 84px; }
    button { margin-top: 16px; padding: 14px; border: 0; border-radius: 12px; background: #1267e5; color: white; font-weight: 800; }
    button:disabled { background: #98a2b3; }
    canvas { display: block; width: 100%; height: auto; margin-top: 16px; border-radius: 12px; background: #111; }
    #status { min-height: 48px; padding: 12px 0; white-space: pre-wrap; }
    .privacy { color: #475467; font-size: .9rem; }
  </style>
</head>
<body>
<main>
  <h1>제품 필터 위치 Overlay 실험</h1>
  <p class="notice">검수된 삼성 수리 절차가 아닙니다. 현재 사진에서 지정한 부품의 위치만 실험합니다. 전원 차단이나 분해 작업은 진행하지 마세요.</p>
  <label for="model">모델코드 또는 제품 메모</label>
  <input id="model" placeholder="예: AR07B9350HZS">
  <label for="component">찾을 부품</label>
  <input id="component" value="필터 접근 커버">
  <label for="instruction">현재 단계</label>
  <textarea id="instruction">사진에서 현재 보이는 필터 접근 커버만 찾으세요. 보이지 않거나 구분할 수 없으면 기권하세요.</textarea>
  <label for="photo">카메라 촬영 또는 사진 선택</label>
  <input id="photo" type="file" accept="image/jpeg,image/png" capture="environment">
  <button id="analyze" disabled>사진에서 위치 찾기</button>
  <div id="status" role="status"></div>
  <canvas id="overlay" hidden></canvas>
  <p class="privacy">사진은 이 요청의 GPT 분석에만 전송되며 앱 서버에 저장하지 않습니다.</p>
</main>
<script>
const photo = document.getElementById('photo');
const button = document.getElementById('analyze');
const status = document.getElementById('status');
const canvas = document.getElementById('overlay');
const context = canvas.getContext('2d');
let selectedFile;
let image;
const MAX_PIXELS = 7500000;

photo.addEventListener('change', async () => {
  const original = photo.files[0];
  button.disabled = !original;
  if (!original) return;
  const source = await createImageBitmap(original);
  const scale = Math.min(1, Math.sqrt(MAX_PIXELS / (source.width * source.height)));
  canvas.width = Math.max(1, Math.floor(source.width * scale));
  canvas.height = Math.max(1, Math.floor(source.height * scale));
  context.fillStyle = 'white';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(source, 0, 0, canvas.width, canvas.height);
  selectedFile = await new Promise((resolve, reject) => {
    canvas.toBlob(
      blob => blob ? resolve(blob) : reject(new Error('사진 변환 실패')),
      'image/jpeg',
      0.9
    );
  });
  image = await createImageBitmap(selectedFile);
  canvas.hidden = false;
  status.textContent = `촬영 크기: ${image.width} × ${image.height}`;
});

function asBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = () => resolve(reader.result.split(',', 2)[1]);
    reader.readAsDataURL(file);
  });
}

button.addEventListener('click', async () => {
  button.disabled = true;
  status.textContent = 'GPT-6.1 Terra 분석 중...';
  context.drawImage(image, 0, 0);
  try {
    const model = document.getElementById('model').value.trim();
    const component = document.getElementById('component').value.trim();
    const instruction = document.getElementById('instruction').value.trim();
    const response = await fetch('/demo/propose', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        step_id: 'mobile-grounding-experiment',
        component,
        instruction: model ? `제품 메모: ${model}. ${instruction}` : instruction,
        image_mime: selectedFile.type,
        image_base64: await asBase64(selectedFile)
      })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '요청 실패');
    if (result.status !== 'located') {
      status.textContent = `${result.status}: ${result.evidence}`;
      return;
    }
    const box = result.box;
    const point = result.point;
    context.strokeStyle = '#ffd400';
    context.lineWidth = Math.max(4, canvas.width / 150);
    context.strokeRect(box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1);
    context.fillStyle = '#ff2d2d';
    context.beginPath();
    context.arc(point.x, point.y, Math.max(8, canvas.width / 70), 0, Math.PI * 2);
    context.fill();
    status.textContent = `후보 위치: ${result.evidence}\\n사용자가 실제 부품과 일치하는지 확인해야 합니다.`;
  } catch (error) {
    status.textContent = `오류: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});
</script>
</body>
</html>
"""

DEMO_LOGIN_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Visual Product Guide 로그인</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; background: #f3f5f7; }
    main { max-width: 480px; margin: 15vh auto; padding: 20px; }
    input, button { box-sizing: border-box; width: 100%; padding: 14px; margin-top: 12px; font: inherit; }
    button { border: 0; border-radius: 10px; background: #1267e5; color: white; font-weight: 800; }
    input { border: 1px solid #98a2b3; border-radius: 10px; }
    #status { color: #b42318; min-height: 24px; }
  </style>
</head>
<body>
<main>
  <h1>모바일 데모 접속</h1>
  <p>전달받은 임시 접근 코드를 입력하세요.</p>
  <form id="login">
    <input id="code" type="password" autocomplete="one-time-code" required>
    <button type="submit">카메라 데모 열기</button>
  </form>
  <p id="status" role="alert"></p>
</main>
<script>
document.getElementById('login').addEventListener('submit', async event => {
  event.preventDefault();
  const response = await fetch('/demo/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({code: document.getElementById('code').value})
  });
  if (response.ok) {
    window.location.replace('/demo');
    return;
  }
  document.getElementById('status').textContent = '접근 코드를 확인하세요.';
});
</script>
</body>
</html>
"""
