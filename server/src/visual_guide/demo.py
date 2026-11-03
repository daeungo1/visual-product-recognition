"""Mobile browser capture and hybrid issue guidance experiment."""

MOBILE_DEMO_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Visual Product Guide</title>
  <style>
    :root { color-scheme: light; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #f3f5f7; color: #101828; }
    main { max-width: 720px; margin: auto; padding: 16px; }
    h1 { font-size: 1.45rem; margin: 8px 0; }
    .notice { background: #fff4e5; border: 1px solid #f6c766; padding: 12px; border-radius: 12px; }
    label { display: block; margin-top: 14px; font-weight: 700; }
    input, textarea, button, select { box-sizing: border-box; width: 100%; font: inherit; }
    input, textarea, select { margin-top: 6px; padding: 12px; border: 1px solid #98a2b3; border-radius: 10px; }
    textarea { min-height: 84px; }
    button { margin-top: 12px; padding: 14px; border: 0; border-radius: 12px; background: #1267e5; color: white; font-weight: 800; }
    button.secondary { background: #475467; }
    button.small { width: auto; padding: 8px 10px; margin: 0; }
    button:disabled { background: #98a2b3; }
    canvas { display: block; width: 100%; height: auto; margin-top: 16px; border-radius: 12px; background: #111; }
    #status { min-height: 48px; padding: 12px 0; white-space: pre-wrap; }
    #resolution { margin-top: 12px; padding: 12px; background: white; border-radius: 12px; }
    #resolution[hidden] { display: none; }
    .mode { display: inline-block; padding: 4px 8px; border-radius: 999px; font-weight: 700; font-size: .85rem; }
    .reviewed { background: #d1fadf; color: #05603a; }
    .zero-shot { background: #fef0c7; color: #93370d; }
    .target-chip { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: end; margin-top: 8px; }
    .target-chip label { margin: 0; }
    .privacy { color: #475467; font-size: .9rem; }
  </style>
</head>
<body>
<main>
  <h1>제품 문제 Visual Guide</h1>
  <p class="notice">제품과 문제를 자유롭게 입력하세요. 등록 제품은 검수 설명서 기반으로 안내하고, 미등록 제품은 보이는 대상의 위치만 실험합니다.</p>
  <label for="productHint">제품 메모 또는 제품명 (선택)</label>
  <input id="productHint" placeholder="예: 삼성 세탁건조기">
  <label for="modelCode">모델코드 (선택)</label>
  <input id="modelCode" placeholder="예: 제품 라벨에 표시된 코드">
  <label for="userIssue">문제 또는 찾을 대상</label>
  <textarea id="userIssue" required placeholder="예: 세제를 어디에 넣고 어떤 버튼을 눌러야 해?"></textarea>
  <label for="currentState">현재 상태 (선택)</label>
  <input id="currentState" placeholder="예: 제품 전면을 보고 있고 문은 닫혀 있음">
  <label for="photo">카메라 촬영 또는 사진 선택</label>
  <input id="photo" type="file" accept="image/jpeg,image/png" capture="environment">
  <button id="analyze" disabled>문제 분석</button>

  <section id="resolution" hidden>
    <div id="supportMode"></div>
    <div id="productConfirmation" hidden>
      <label for="productCandidate">제품 후보 확인</label>
      <select id="productCandidate"></select>
    </div>
    <h2>확인할 대상</h2>
    <div id="targetChips"></div>
    <button id="addTarget" class="secondary" type="button">+ 대상 추가</button>
    <button id="ground" type="button">확인한 대상을 사진에서 찾기</button>
  </section>

  <div id="status" role="status"></div>
  <canvas id="overlay" hidden></canvas>
  <p class="privacy">사진은 문제 분석과 위치 요청에 전송되며 앱 서버에 저장하지 않습니다.</p>
</main>
<script>
const MAX_PIXELS = 7500000;
const MAX_TARGETS = 3;
const ZERO_SHOT_MODE = 'zero_shot_locate_only';
const colors = ['#ffd400', '#00d5ff', '#ff5ca8'];
const photo = document.getElementById('photo');
const analyze = document.getElementById('analyze');
const ground = document.getElementById('ground');
const status = document.getElementById('status');
const canvas = document.getElementById('overlay');
const context = canvas.getContext('2d');
let selectedFile;
let image;
let issueResolution;
let confirmedTargets = [];

photo.addEventListener('change', async () => {
  const original = photo.files[0];
  analyze.disabled = !original;
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

function issueBody(issueText) {
  return {
    product_hint: document.getElementById('productHint').value.trim() || null,
    model_code: document.getElementById('modelCode').value.trim() || null,
    user_issue: issueText,
    current_state: document.getElementById('currentState').value.trim() || null,
    image_mime: selectedFile.type,
    image_base64: null
  };
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || '요청 실패');
  return result;
}

function renderSupportMode() {
  const mode = document.getElementById('supportMode');
  const reviewed = issueResolution.support_mode === 'reviewed_guide';
  mode.innerHTML = reviewed
    ? '<span class="mode reviewed">검수 가이드</span> 정확한 제품과 설명서 근거를 사용합니다.'
    : `<span class="mode zero-shot">Zero-shot 위치 실험</span> ${ZERO_SHOT_MODE}: 공식 조작 절차가 아닙니다.`;
  const confirmation = document.getElementById('productConfirmation');
  const select = document.getElementById('productCandidate');
  confirmation.hidden = !issueResolution.requires_product_confirmation;
  select.replaceChildren();
  issueResolution.product_candidates.forEach(candidate => {
    const option = document.createElement('option');
    option.value = candidate.product_id;
    option.dataset.models = JSON.stringify(candidate.exact_model_codes);
    option.textContent = `${candidate.manufacturer} ${candidate.display_name} (${candidate.confidence_band})`;
    select.appendChild(option);
  });
}

function renderTargetChips() {
  const container = document.getElementById('targetChips');
  container.replaceChildren();
  confirmedTargets.forEach((target, index) => {
    const row = document.createElement('div');
    row.className = 'target-chip';
    const label = document.createElement('label');
    label.textContent = target.source === 'registry' ? '검수 대상' : '자유 대상';
    const input = document.createElement('input');
    input.className = 'target-name';
    input.value = target.display_name;
    input.addEventListener('change', () => {
      confirmedTargets[index] = {...target, display_name: input.value.trim() || target.display_name};
    });
    label.appendChild(input);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'small secondary';
    remove.textContent = '삭제';
    remove.addEventListener('click', () => {
      confirmedTargets.splice(index, 1);
      renderTargetChips();
    });
    row.append(label, remove);
    container.appendChild(row);
  });
}

async function resolveIssue(issueText) {
  const body = issueBody(issueText);
  body.image_base64 = await asBase64(selectedFile);
  return postJson('/demo/issues/resolve', body);
}

analyze.addEventListener('click', async () => {
  const issue = document.getElementById('userIssue').value.trim();
  if (!issue) {
    status.textContent = '문제 또는 찾을 대상을 입력하세요.';
    return;
  }
  analyze.disabled = true;
  status.textContent = '제품과 문제를 분석 중...';
  try {
    issueResolution = await resolveIssue(issue);
    confirmedTargets = issueResolution.targets.slice(0, MAX_TARGETS);
    renderSupportMode();
    renderTargetChips();
    document.getElementById('resolution').hidden = false;
    status.textContent = issueResolution.next_capture_instruction;
  } catch (error) {
    status.textContent = `오류: ${error.message}`;
  } finally {
    analyze.disabled = false;
  }
});

document.getElementById('addTarget').addEventListener('click', async () => {
  if (confirmedTargets.length >= MAX_TARGETS) {
    status.textContent = '한 번에 최대 3개 대상만 찾을 수 있습니다.';
    return;
  }
  const phrase = window.prompt('추가로 찾을 대상을 입력하세요.');
  if (!phrase) return;
  status.textContent = '추가 대상을 다시 분석 중...';
  try {
    const added = await resolveIssue(phrase);
    for (const target of added.targets) {
      if (confirmedTargets.length >= MAX_TARGETS) break;
      if (!confirmedTargets.some(item => item.canonical_name === target.canonical_name)) {
        confirmedTargets.push(target);
      }
    }
    renderTargetChips();
    status.textContent = '추가 대상을 확인하세요.';
  } catch (error) {
    status.textContent = `오류: ${error.message}`;
  }
});

function confirmedProduct() {
  if (issueResolution.product_status === 'registered') {
    const candidate = issueResolution.product_candidates[0];
    return {
      productId: candidate.product_id,
      modelCode: candidate.confirmed_model_code
    };
  }
  if (issueResolution.product_status === 'candidate') {
    const option = document.getElementById('productCandidate').selectedOptions[0];
    const models = JSON.parse(option.dataset.models);
    document.getElementById('modelCode').value = models[0];
    return {productId: option.value, modelCode: models[0]};
  }
  return {productId: null, modelCode: null};
}

ground.addEventListener('click', async () => {
  if (!confirmedTargets.length) {
    status.textContent = '찾을 대상을 하나 이상 확인하세요.';
    return;
  }
  ground.disabled = true;
  context.drawImage(image, 0, 0);
  status.textContent = '확인한 대상을 찾는 중...';
  try {
    let product = confirmedProduct();
    if (issueResolution.product_status === 'candidate') {
      const renamed = new Map(
        confirmedTargets.map(target => [target.canonical_name, target.display_name])
      );
      issueResolution = await resolveIssue(
        document.getElementById('userIssue').value.trim()
      );
      confirmedTargets = issueResolution.targets
        .slice(0, MAX_TARGETS)
        .map(target => ({
          ...target,
          display_name: renamed.get(target.canonical_name) || target.display_name
        }));
      renderSupportMode();
      renderTargetChips();
      product = confirmedProduct();
    }
    const guide = issueResolution.guide_candidates[0] || null;
    const body = {
      request: {
        resolution: issueResolution,
        confirmed_product_id: product.productId,
        confirmed_model_code: product.modelCode,
        confirmed_guide_id: guide ? guide.guide_id : null,
        confirmed_step_id: guide && guide.step_ids.length ? guide.step_ids[0] : null,
        confirmed_targets: confirmedTargets
      },
      image_mime: selectedFile.type,
      image_base64: await asBase64(selectedFile)
    };
    const result = await postJson('/demo/issues/ground', body);
    const messages = [
      result.partial_success
        ? '일부 대상만 찾았습니다.'
        : '대상 분석이 완료되었습니다.'
    ];
    result.targets.forEach((item, index) => {
      const target = item.target;
      const grounding = item.grounding;
      if (grounding.status === 'located') {
        const color = colors[index % colors.length];
        const box = grounding.box;
        const point = grounding.point;
        context.strokeStyle = color;
        context.fillStyle = color;
        context.lineWidth = Math.max(4, canvas.width / 150);
        context.strokeRect(box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1);
        context.beginPath();
        context.arc(point.x, point.y, Math.max(8, canvas.width / 70), 0, Math.PI * 2);
        context.fill();
        context.font = `bold ${Math.max(16, canvas.width / 35)}px system-ui`;
        context.fillText(target.display_name, box.x1, Math.max(24, box.y1 - 8));
      }
      const authority = target.source === 'registry' ? '검수' : 'zero-shot';
      messages.push(`${target.display_name} [${authority}]: ${grounding.status}`);
      if (item.instruction && item.source_reference) {
        messages.push(`${item.instruction} (${item.source_reference})`);
      } else if (grounding.retake_instruction) {
        messages.push(grounding.retake_instruction);
      }
    });
    status.textContent = messages.join('\\n');
  } catch (error) {
    status.textContent = `오류: ${error.message}`;
  } finally {
    ground.disabled = false;
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
