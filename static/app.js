// ── 상태 ──
const state = {
  sensor: { ec: null, ph: null },
  target: { ec: 2.0, ph: 6.5 },
  connected: false,
};

// 센서 정상 범위
const RANGE = {
  ec: { min: 1.2, max: 2.0 },
  ph: { min: 5.5, max: 6.5 },
};

// ── 탭 전환 ──
function switchTab(name, btn) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  btn.classList.add('active');
}

// ── 상태 뱃지 ──
function getBadge(key, val) {
  const r = RANGE[key];
  const span = r.max - r.min;
  const margin = span * 0.1;
  if (val < r.min || val > r.max) return { cls: 'danger', text: '위험' };
  if (val < r.min + margin || val > r.max - margin) return { cls: 'caution', text: '주의' };
  return { cls: 'normal', text: '정상' };
}

function setBadge(id, cls, text) {
  const el = document.getElementById(id);
  el.className = 'badge ' + cls;
  el.textContent = text;
}

// ── 차이값 ──
function diffText(current, target) {
  const d = current - target;
  if (Math.abs(d) < 0.01) return { text: '목표 도달', cls: 'ok' };
  if (d > 0) return { text: `+${d.toFixed(2)} 초과`, cls: 'high' };
  return { text: `${d.toFixed(2)} 부족`, cls: 'low' };
}

// ── UI 갱신 ──
function updateMonitor() {
  const { sensor, target } = state;
  const fmt = (v, d) => v == null ? '—' : v.toFixed(d);

  // EC
  document.getElementById('val-ec').textContent = fmt(sensor.ec, 2);
  document.getElementById('tgt-ec').textContent = `목표 ${target.ec.toFixed(1)}`;
  if (sensor.ec != null) {
    const b = getBadge('ec', sensor.ec);
    setBadge('badge-ec', b.cls, b.text);
    const d = diffText(sensor.ec, target.ec);
    document.getElementById('diff-ec-label').textContent = `EC  현재 ${sensor.ec.toFixed(2)} / 목표 ${target.ec.toFixed(1)}`;
    const dv = document.getElementById('diff-ec-value');
    dv.textContent = d.text; dv.className = 'diff-value ' + d.cls;
  }

  // pH
  document.getElementById('val-ph').textContent = fmt(sensor.ph, 1);
  document.getElementById('tgt-ph').textContent = `목표 ${target.ph.toFixed(1)}`;
  if (sensor.ph != null) {
    const b = getBadge('ph', sensor.ph);
    setBadge('badge-ph', b.cls, b.text);
    const d = diffText(sensor.ph, target.ph);
    document.getElementById('diff-ph-label').textContent = `pH  현재 ${sensor.ph.toFixed(1)} / 목표 ${target.ph.toFixed(1)}`;
    const dv = document.getElementById('diff-ph-value');
    dv.textContent = d.text; dv.className = 'diff-value ' + d.cls;
  }
}

// ── 연결 상태 표시 ──
function setConnected(ok) {
  state.connected = ok;
  const dot = document.getElementById('conn-dot');
  const txt = document.getElementById('conn-text');
  dot.className = 'conn-dot ' + (ok ? 'connected' : 'disconnected');
  txt.textContent = ok ? '연결됨' : '연결 끊김';
}

// ── WebSocket ──
let ws = null;

function connectWS() {
  if (ws) ws.close();
  ws = new WebSocket(`ws://${location.host}/ws`);

  ws.onopen = () => setConnected(true);

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.ec != null) state.sensor.ec = data.ec;
      if (data.ph != null) state.sensor.ph = data.ph;
      updateMonitor();
    } catch (_) {}
  };

  ws.onclose = () => {
    setConnected(false);
    setTimeout(connectWS, 5000);
  };

  ws.onerror = () => ws.close();
}

// ── 목표값 로드/저장 (REST API) ──
async function loadTarget() {
  try {
    const r = await fetch('/api/settings/target');
    if (!r.ok) return;
    const d = await r.json();
    if (d.ec != null) state.target.ec = d.ec;
    if (d.ph != null) state.target.ph = d.ph;
    document.getElementById('input-ec').value = state.target.ec.toFixed(1);
    document.getElementById('input-ph').value = state.target.ph.toFixed(1);
    updateMonitor();
  } catch (_) {}
}

async function saveSettings() {
  const ec = parseFloat(document.getElementById('input-ec').value);
  const ph = parseFloat(document.getElementById('input-ph').value);
  const fb = document.getElementById('save-feedback');
  if (isNaN(ec) || isNaN(ph)) { fb.textContent = '값을 확인해 주세요.'; return; }

  try {
    const r = await fetch('/api/settings/target', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ec, ph }),
    });
    if (r.ok) {
      state.target.ec = ec; state.target.ph = ph;
      updateMonitor();
      fb.style.color = 'var(--green)';
      fb.textContent = '저장되었습니다.';
    } else {
      fb.style.color = 'var(--red)';
      fb.textContent = '저장 실패.';
    }
  } catch (_) {
    state.target.ec = ec; state.target.ph = ph;
    updateMonitor();
    fb.style.color = 'var(--green)';
    fb.textContent = '저장되었습니다. (로컬)';
  }
  setTimeout(() => { fb.textContent = ''; }, 3000);
}

// ── 도징 (순차 폐루프 2단계: ①pH/B → 재측정 → ②EC/A) ──
let dosing = false;
let dosePhase = 'ph';   // 'ph' → 다음 클릭은 1단계, 'ec' → 다음 클릭은 2단계
let lastBml  = 0;       // 1단계에서 권장/투입한 B액(mL) — 2단계 상호작용 보정용

function resetDose(msg, color) {
  const btn = document.getElementById('dose-btn');
  const fb  = document.getElementById('dose-feedback');
  dosePhase = 'ph';
  lastBml   = 0;
  btn.textContent = '① pH 도징 (B액)';
  btn.disabled    = false;
  dosing          = false;
  if (msg !== undefined) { fb.style.color = color || ''; fb.textContent = msg; }
}

async function doDose() {
  if (dosing) return;
  dosing = true;
  const btn = document.getElementById('dose-btn');
  const fb  = document.getElementById('dose-feedback');
  const phase = dosePhase;
  btn.disabled = true;
  btn.textContent = '처리 중...';
  fb.textContent  = '';
  fb.style.color  = '';

  const url  = phase === 'ph' ? '/api/control/dose/ph' : '/api/control/dose/ec';
  const body = phase === 'ph'
    ? { ph: state.sensor.ph, target_ph: state.target.ph }
    : { ec: state.sensor.ec, target_ec: state.target.ec, b_ml_dosed: lastBml };

  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await r.json();
    fb.style.color = d.status === 'SKIP' ? 'var(--yellow)' : 'var(--green)';
    fb.textContent = d.message + (d.calibration_pending ? ' [계수 미보정]' : '');

    if (phase === 'ph') {
      // 1단계 완료 → 2단계(EC/A) 대기. B 투입·교반·재측정 후 다시 눌러야 함.
      lastBml   = d.b_ml || 0;
      dosePhase = 'ec';
      btn.textContent = '② 재측정 후 EC 도징 (A액)';
      btn.disabled    = false;
      dosing          = false;
    } else {
      // 2단계 완료 → 사이클 종료. 버튼은 즉시 1단계로 복귀, 피드백만 잠시 유지.
      dosePhase = 'ph';
      lastBml   = 0;
      btn.textContent = '① pH 도징 (B액)';
      btn.disabled    = false;
      dosing          = false;
      const shown = fb.textContent;
      setTimeout(() => {
        if (fb.textContent === shown) { fb.textContent = ''; fb.style.color = ''; }
      }, 5000);
    }
  } catch (_) {
    resetDose('백엔드 연결 안 됨', 'var(--yellow)');
  }
}

// ── 더미 데이터 (백엔드 없을 때) ──
function injectDummy() {
  state.sensor.ec = 1.85 + (Math.random() - 0.5) * 0.1;
  state.sensor.ph = 6.2  + (Math.random() - 0.5) * 0.2;
  updateMonitor();
}

// ── 초기화 ──
(function init() {
  updateMonitor();
  connectWS();
  loadTarget();

  setTimeout(function tryDummy() {
    if (!state.connected) {
      injectDummy();
      setConnected(false);
    }
    setTimeout(tryDummy, 5000);
  }, 2000);
})();
