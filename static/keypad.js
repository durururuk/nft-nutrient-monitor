// 숫자 키패드 — 자체 DOM 생성, openKeypad()로 호출
(function () {
  let kpTarget = null;
  let kpBuffer = '';
  let kpMin = 0, kpMax = 99;
  let onConfirm = null;

  // ── DOM 생성 ──
  const overlay = document.createElement('div');
  overlay.id = 'keypad-overlay';
  overlay.className = 'keypad-overlay';
  overlay.innerHTML = `
    <div class="keypad">
      <div class="keypad-label" id="keypad-label"></div>
      <div class="keypad-display" id="keypad-display">—</div>
      <div class="keypad-grid">
        <button class="key">7</button>
        <button class="key">8</button>
        <button class="key">9</button>
        <button class="key">4</button>
        <button class="key">5</button>
        <button class="key">6</button>
        <button class="key">1</button>
        <button class="key">2</button>
        <button class="key">3</button>
        <button class="key">.</button>
        <button class="key">0</button>
        <button class="key del">⌫</button>
        <button class="key cancel">취소</button>
        <button class="key confirm" style="grid-column: span 2">확인</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const display = overlay.querySelector('#keypad-display');
  const label   = overlay.querySelector('#keypad-label');

  // ── 내부 함수 ──
  function updateDisplay() {
    display.textContent = kpBuffer || '—';
  }

  function close() {
    overlay.classList.remove('open');
    kpTarget = null;
    kpBuffer = '';
    onConfirm = null;
  }

  function confirm() {
    const val = parseFloat(kpBuffer);
    if (isNaN(val) || val < kpMin || val > kpMax) {
      display.textContent = `범위: ${kpMin}~${kpMax}`;
      kpBuffer = '';
      return;
    }
    if (onConfirm) onConfirm(val);
    close();
  }

  // ── 이벤트: 숫자 키 ──
  overlay.querySelectorAll('.key:not(.del):not(.cancel):not(.confirm)').forEach(btn => {
    btn.addEventListener('click', () => {
      const ch = btn.textContent;
      if (ch === '.' && kpBuffer.includes('.')) return;
      if (kpBuffer === '0' && ch !== '.') kpBuffer = ch;
      else kpBuffer += ch;
      if (kpBuffer.length > 8) kpBuffer = kpBuffer.slice(0, 8);
      updateDisplay();
    });
  });

  overlay.querySelector('.del').addEventListener('click', () => {
    kpBuffer = kpBuffer.slice(0, -1);
    updateDisplay();
  });

  overlay.querySelector('.cancel').addEventListener('click', close);
  overlay.querySelector('.confirm').addEventListener('click', confirm);

  // 오버레이 배경 클릭 시 닫기
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });

  // ── 공개 API ──
  window.openKeypad = function (labelText, initialValue, min, max, callback) {
    kpMin     = min;
    kpMax     = max;
    kpBuffer  = String(initialValue ?? '');
    onConfirm = callback;
    label.textContent   = labelText;
    display.textContent = kpBuffer || '—';
    overlay.classList.add('open');
  };
})();
