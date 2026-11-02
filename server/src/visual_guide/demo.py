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
    fieldset { margin-top: 14px; padding: 12px; border: 1px solid #98a2b3; border-radius: 10px; }
    fieldset label { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
    input[type="checkbox"] { width: auto; margin: 0; }
    button { margin-top: 16px; padding: 14px; border: 0; border-radius: 12px; background: #1267e5; color: white; font-weight: 800; }
    button:disabled { background: #98a2b3; }
    canvas { display: block; width: 100%; height: auto; margin-top: 16px; border-radius: 12px; background: #111; }
    #status { min-height: 48px; padding: 12px 0; white-space: pre-wrap; }
    .privacy { color: #475467; font-size: .9rem; }
  </style>
</head>
<body>
<main>
  <h1>WD80H25BHS 세제함·조작부 Overlay</h1>
  <p class="notice">Bespoke AI 콤보 25/18kg 다크스틸 전용 실험입니다. 설명서의 제품 구성 근거로 위치를 찾지만 사용자가 실제 부품과 일치하는지 확인해야 합니다.</p>
  <p><strong>현재 단계:</strong> 제품 전면 하단의 세제함 전면 덮개와 전면 상단 가운데의 조작부를 확인합니다.</p>
  <fieldset>
    <legend>찾을 부품</legend>
    <label><input type="checkbox" name="target" value="detergent_dispenser" checked> 세제함 전면 덮개</label>
    <label><input type="checkbox" name="target" value="control_panel" checked> 조작부</label>
  </fieldset>
  <label for="photo">카메라 촬영 또는 사진 선택</label>
  <input id="photo" type="file" accept="image/jpeg,image/png" capture="environment">
  <button id="analyze" disabled>검수 가이드로 위치 찾기</button>
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
const TARGET_COLORS = {
  detergent_dispenser: '#ffd400',
  control_panel: '#00d5ff'
};

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
    const targetIds = Array.from(
      document.querySelectorAll('input[name="target"]:checked')
    ).map(input => input.value);
    if (!targetIds.length) throw new Error('찾을 부품을 하나 이상 선택하세요.');
    const response = await fetch('/demo/ground', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        model_code: 'WD80H25BHS',
        guide_id: 'detergent-and-controls',
        step_id: 'locate-detergent-and-controls',
        target_ids: targetIds,
        image_mime: selectedFile.type,
        image_base64: await asBase64(selectedFile)
      })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '요청 실패');
    const messages = [];
    result.targets.forEach(target => {
      if (target.status === 'located') {
        const color = TARGET_COLORS[target.target_id] || '#ffd400';
        const box = target.box;
        const point = target.point;
        context.strokeStyle = color;
        context.fillStyle = color;
        context.lineWidth = Math.max(4, canvas.width / 150);
        context.strokeRect(box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1);
        context.beginPath();
        context.arc(point.x, point.y, Math.max(8, canvas.width / 70), 0, Math.PI * 2);
        context.fill();
        context.font = `bold ${Math.max(16, canvas.width / 35)}px system-ui`;
        context.fillText(target.component, box.x1, Math.max(24, box.y1 - 8));
        messages.push(`${target.component}: 위치 후보 확인 (${target.attempts}차 시도)`);
        return;
      }
      messages.push(
        `${target.component}: ${target.status}\\n${target.retake_instruction}`
      );
    });
    const summary = result.partial_success
      ? '일부 부품만 찾았습니다. 아래 재촬영 안내를 확인하세요.'
      : '대상별 분석 결과';
    status.textContent = `${summary}\\n${messages.join('\\n')}`;
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
