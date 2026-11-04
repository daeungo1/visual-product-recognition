"""Mobile browser capture and hybrid issue guidance experiment."""

MOBILE_DEMO_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Visual Product Guide</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, Pretendard, system-ui, -apple-system, sans-serif;
      --brand-primary: #0f766e;
      --brand-primary-dark: #115e59;
      --brand-soft: #ccfbf1;
      --accent: #f97316;
      --surface: #ffffff;
      --surface-muted: #f0fdfa;
      --background: #f5faf9;
      --text: #12302e;
      --text-muted: #58716f;
      --line: #c9dedb;
      --danger: #dc2626;
      --shadow: 0 16px 40px rgba(15, 118, 110, .1);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background:
        radial-gradient(circle at top right, rgba(45, 212, 191, .22), transparent 34rem),
        var(--background);
      color: var(--text);
    }
    main { max-width: 760px; margin: auto; padding: 18px 16px 48px; }
    h1, h2, p { margin-top: 0; }
    h1 { margin-bottom: 10px; font-size: clamp(1.75rem, 6vw, 2.45rem); line-height: 1.18; letter-spacing: -.04em; }
    h2 { margin-bottom: 4px; font-size: 1.2rem; }
    .hero {
      overflow: hidden;
      position: relative;
      margin-bottom: 16px;
      padding: 24px;
      border-radius: 24px;
      background: linear-gradient(135deg, #134e4a, #0f766e 60%, #14b8a6);
      color: white;
      box-shadow: var(--shadow);
    }
    .hero::after {
      content: '';
      position: absolute;
      right: -54px;
      bottom: -72px;
      width: 190px;
      height: 190px;
      border-radius: 50%;
      background: rgba(255,255,255,.1);
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 12px;
      padding: 6px 10px;
      border: 1px solid rgba(255,255,255,.3);
      border-radius: 999px;
      background: rgba(255,255,255,.12);
      font-size: .78rem;
      font-weight: 800;
      letter-spacing: .04em;
    }
    .hero p { max-width: 560px; margin-bottom: 0; color: #ccfbf1; line-height: 1.55; }
    .stepper {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin: 16px 0;
    }
    .step {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255,255,255,.72);
      color: var(--text-muted);
      font-size: .78rem;
      font-weight: 700;
    }
    .step-number {
      display: grid;
      flex: 0 0 26px;
      width: 26px;
      height: 26px;
      place-items: center;
      border-radius: 50%;
      background: #dce8e6;
      color: var(--text-muted);
    }
    .step.active { border-color: #5eead4; background: var(--brand-soft); color: var(--brand-primary-dark); }
    .step.active .step-number, .step.done .step-number { background: var(--brand-primary); color: white; }
    .step.done { color: var(--brand-primary-dark); }
    .card {
      margin-top: 14px;
      padding: 20px;
      border: 1px solid rgba(201,222,219,.9);
      border-radius: 22px;
      background: var(--surface);
      box-shadow: 0 8px 28px rgba(18, 48, 46, .06);
    }
    .card-header { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 16px; }
    .card-icon {
      display: grid;
      flex: 0 0 40px;
      width: 40px;
      height: 40px;
      place-items: center;
      border-radius: 13px;
      background: var(--brand-soft);
      font-size: 1.2rem;
    }
    .helper { margin-bottom: 0; color: var(--text-muted); font-size: .9rem; line-height: 1.45; }
    .field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    label { display: block; font-size: .9rem; font-weight: 800; }
    .optional { color: var(--text-muted); font-size: .76rem; font-weight: 600; }
    input, textarea, button, select { width: 100%; font: inherit; }
    input, textarea, select {
      margin-top: 7px;
      padding: 13px 14px;
      border: 1px solid var(--line);
      border-radius: 13px;
      background: #fbfefd;
      color: var(--text);
      outline: none;
      transition: border-color .2s, box-shadow .2s;
    }
    input:focus, textarea:focus, select:focus {
      border-color: #2dd4bf;
      box-shadow: 0 0 0 4px rgba(45, 212, 191, .16);
    }
    textarea { min-height: 104px; resize: vertical; }
    .issue-field { margin-top: 14px; }
    .upload-zone {
      display: flex;
      align-items: center;
      gap: 14px;
      min-height: 92px;
      padding: 16px;
      border: 2px dashed #5eead4;
      border-radius: 18px;
      background: var(--surface-muted);
      cursor: pointer;
    }
    .upload-zone:hover { border-color: var(--brand-primary); background: #e6fffb; }
    .upload-icon {
      display: grid;
      flex: 0 0 48px;
      width: 48px;
      height: 48px;
      place-items: center;
      border-radius: 16px;
      background: white;
      box-shadow: 0 6px 18px rgba(15, 118, 110, .12);
      font-size: 1.35rem;
    }
    .upload-zone strong { display: block; margin-bottom: 4px; color: var(--brand-primary-dark); }
    .upload-zone span { color: var(--text-muted); font-size: .84rem; font-weight: 500; }
    .upload-zone input { position: absolute; width: 1px; height: 1px; opacity: 0; }
    .action-bar { display: grid; grid-template-columns: 1fr; gap: 10px; margin-top: 16px; }
    button {
      min-height: 50px;
      padding: 13px 18px;
      border: 0;
      border-radius: 15px;
      background: var(--brand-primary);
      color: white;
      font-weight: 850;
      cursor: pointer;
      box-shadow: 0 8px 18px rgba(15, 118, 110, .2);
      transition: transform .15s, background .15s, box-shadow .15s;
    }
    button:hover:not(:disabled) { transform: translateY(-1px); background: var(--brand-primary-dark); }
    button:active:not(:disabled) { transform: translateY(0); }
    button.secondary { border: 1px solid var(--line); background: white; color: var(--brand-primary-dark); box-shadow: none; }
    button.small { width: auto; min-height: 40px; padding: 8px 11px; margin: 0; color: var(--danger); }
    button:disabled { background: #a9bfbc; cursor: not-allowed; box-shadow: none; }
    .status-panel {
      min-height: 52px;
      margin-top: 14px;
      padding: 13px 15px;
      border-radius: 14px;
      background: #e9f8f5;
      color: var(--brand-primary-dark);
      white-space: pre-wrap;
      line-height: 1.5;
    }
    .status-panel:empty { display: none; }
    .preview-card { overflow: hidden; padding: 10px; }
    canvas { display: block; width: 100%; height: auto; border-radius: 16px; background: #0b1f1d; }
    #resolution { scroll-margin-top: 12px; }
    #resolution[hidden] { display: none; }
    .mode { display: inline-block; margin-right: 6px; padding: 5px 9px; border-radius: 999px; font-weight: 800; font-size: .8rem; }
    .reviewed { background: #d1fadf; color: #05603a; }
    .zero-shot { background: #fef0c7; color: #93370d; }
    .target-chip { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: end; margin-top: 10px; padding: 10px; border-radius: 15px; background: var(--surface-muted); }
    .target-chip label { margin: 0; }
    .privacy { margin-top: 16px; color: var(--text-muted); font-size: .82rem; text-align: center; }
    @media (max-width: 560px) {
      main { padding-inline: 12px; }
      .hero, .card { padding: 17px; border-radius: 20px; }
      .field-grid { grid-template-columns: 1fr; }
      .step { justify-content: center; padding: 8px 4px; }
      .step-label { display: none; }
    }
  </style>
</head>
<body>
<main>
  <header class="hero">
    <div class="eyebrow">✦ AI VISUAL ASSISTANT</div>
    <h1>제품을 보여주면<br>필요한 위치를 찾아드려요</h1>
    <p>제품 문제를 설명하고 사진을 촬영하세요. AI가 조작할 부분을 찾아 사진 위에 표시합니다.</p>
  </header>

  <nav class="stepper" aria-label="진행 단계">
    <div class="step active" data-step="1"><span class="step-number">1</span><span class="step-label">도움 요청</span></div>
    <div class="step" data-step="2"><span class="step-number">2</span><span class="step-label">사진 촬영</span></div>
    <div class="step" data-step="3"><span class="step-number">3</span><span class="step-label">결과 확인</span></div>
  </nav>

  <section class="card">
    <div class="card-header">
      <div class="card-icon">💬</div>
      <div>
        <h2>1. 어떤 도움이 필요한가요?</h2>
        <p class="helper">제품명이나 모델을 몰라도 괜찮아요. 해결하고 싶은 내용을 먼저 적어주세요.</p>
      </div>
    </div>
    <div class="field-grid">
      <label for="productHint">제품명 <span class="optional">선택</span>
        <input id="productHint" placeholder="예: 삼성 세탁건조기">
      </label>
      <label for="modelCode">모델코드 <span class="optional">선택</span>
        <input id="modelCode" placeholder="제품 라벨에 표시된 코드">
      </label>
    </div>
    <label class="issue-field" for="userIssue">문제 또는 찾을 대상
      <textarea id="userIssue" required placeholder="예: 세제를 어디에 넣고 어떤 버튼을 눌러야 해?"></textarea>
    </label>
    <label class="issue-field" for="currentState">현재 상태 <span class="optional">선택</span>
      <input id="currentState" placeholder="예: 제품 문이 닫혀 있고 전원이 꺼져 있음">
    </label>
  </section>

  <section class="card">
    <div class="card-header">
      <div class="card-icon">📷</div>
      <div>
        <h2>2. 제품 사진을 보여주세요</h2>
        <p class="helper">찾을 부분이 포함되도록 제품 전면을 밝고 선명하게 촬영해주세요.</p>
      </div>
    </div>
    <label class="upload-zone" for="photo">
      <span class="upload-icon">📸</span>
      <span><strong>사진 선택 또는 카메라 촬영</strong>JPG 또는 PNG · 최대 8MP로 자동 최적화</span>
      <input id="photo" type="file" accept="image/jpeg,image/png" capture="environment">
    </label>
    <div class="action-bar">
      <button id="analyze" disabled>✦ AI로 도움 방법 찾기</button>
    </div>
  </section>

  <div id="status" class="status-panel" role="status"></div>
  <section class="card preview-card">
    <canvas id="overlay" hidden></canvas>
  </section>

  <section id="resolution" class="card" hidden>
    <div class="card-header">
      <div class="card-icon">✓</div>
      <div>
        <h2>3. 분석 결과 확인</h2>
        <p class="helper">AI가 찾은 대상이 맞는지 확인한 뒤 사진에서 위치를 표시하세요.</p>
      </div>
    </div>
    <div id="supportMode"></div>
    <div id="productConfirmation" hidden>
      <label for="productCandidate">제품 후보 확인
        <select id="productCandidate"></select>
      </label>
    </div>
    <h2 style="margin-top:18px">확인할 대상</h2>
    <p class="helper">이름을 수정하거나 필요 없는 항목을 삭제할 수 있습니다.</p>
    <div id="targetChips"></div>
    <div class="action-bar">
      <button id="addTarget" class="secondary" type="button">＋ 다른 대상 추가</button>
      <button id="ground" type="button">사진 위에 위치 표시하기</button>
    </div>
  </section>

  <p class="privacy">간편 테스트용 페이지입니다. 사진은 분석 요청에만 사용됩니다.</p>
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
const steps = Array.from(document.querySelectorAll('.step'));
let selectedFile;
let image;
let issueResolution;
let confirmedTargets = [];

function setStep(activeStep) {
  steps.forEach((step, index) => {
    const number = index + 1;
    step.classList.toggle('active', number === activeStep);
    step.classList.toggle('done', number < activeStep);
  });
}

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
  setStep(2);
  status.textContent = `✓ 사진 준비 완료 · ${image.width} × ${image.height}`;
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
  const originalLabel = analyze.textContent;
  analyze.textContent = 'AI가 제품과 문제를 분석하고 있어요...';
  status.textContent = '잠시만 기다려주세요. 사진과 입력 내용을 함께 확인하고 있습니다.';
  try {
    issueResolution = await resolveIssue(issue);
    confirmedTargets = issueResolution.targets.slice(0, MAX_TARGETS);
    renderSupportMode();
    renderTargetChips();
    document.getElementById('resolution').hidden = false;
    setStep(3);
    document.getElementById('resolution').scrollIntoView({
      behavior: 'smooth',
      block: 'start'
    });
    status.textContent = issueResolution.next_capture_instruction;
  } catch (error) {
    status.textContent = `오류: ${error.message}`;
  } finally {
    analyze.disabled = false;
    analyze.textContent = originalLabel;
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
  const originalLabel = ground.textContent;
  ground.textContent = '사진에서 위치를 찾고 있어요...';
  status.textContent = '대상별 위치를 여러 번 확인하고 있습니다.';
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
    setStep(3);
    canvas.scrollIntoView({behavior: 'smooth', block: 'center'});
  } catch (error) {
    status.textContent = `오류: ${error.message}`;
  } finally {
    ground.disabled = false;
    ground.textContent = originalLabel;
  }
});
</script>
</body>
</html>
"""
