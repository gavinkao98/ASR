/*
  語音輸入 — 設定視窗邏輯
  純 vanilla JS，無框架、無建置流程。所有資料透過 window.pywebview.api.* 存取（回傳 Promise）。
  若 pywebview 不存在（例如直接用瀏覽器打開這個檔案做靜態檢視），會改用下方的假資料 API，
  介面仍要完整可用，並顯示「未連線（預覽模式）」，不可白屏、不可丟未捕捉的例外。
*/
(function () {
  'use strict';

  /* ============================================================
   * 0. 小工具
   * ============================================================ */
  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }
  function delay(ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); }

  function setSwitch(el, checked) { el.setAttribute('aria-checked', checked ? 'true' : 'false'); }

  function setSegmented(container, value) {
    qsa('.segmented-btn', container).forEach(function (btn) {
      btn.setAttribute('aria-checked', btn.dataset.value === value ? 'true' : 'false');
    });
  }

  var toastTimer = null;
  function showToast(msg) {
    var toast = qs('#toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove('show'); }, 1800);
  }

  function formatTs(ts) {
    if (ts === undefined || ts === null) return '--:--';
    var ms = ts > 1e12 ? ts : ts * 1000;
    var d = new Date(ms);
    if (isNaN(d.getTime())) return '--:--';
    var now = new Date();
    var sameDay = d.toDateString() === now.toDateString();
    var hh = String(d.getHours()).padStart(2, '0');
    var mm = String(d.getMinutes()).padStart(2, '0');
    if (sameDay) return hh + ':' + mm;
    var MM = String(d.getMonth() + 1).padStart(2, '0');
    var DD = String(d.getDate()).padStart(2, '0');
    return MM + '/' + DD + ' ' + hh + ':' + mm;
  }

  function engineLabel(name) {
    if (name === 'qwen3') return 'Qwen3-ASR';
    if (name === 'breeze') return 'Breeze-ASR';
    return name || '—';
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      try {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        return true;
      } catch (err2) {
        return false;
      }
    }
  }

  function confirmDangerAction(btn, armedText, onConfirm) {
    if (btn.dataset.armed === '1') {
      delete btn.dataset.armed;
      clearTimeout(Number(btn.dataset.armTimer));
      btn.classList.remove('armed');
      btn.textContent = btn.dataset.originalText || btn.textContent;
      onConfirm();
      return;
    }
    btn.dataset.originalText = btn.textContent;
    btn.dataset.armed = '1';
    btn.classList.add('armed');
    btn.textContent = armedText;
    var timer = setTimeout(function () {
      delete btn.dataset.armed;
      btn.classList.remove('armed');
      btn.textContent = btn.dataset.originalText;
    }, 3000);
    btn.dataset.armTimer = String(timer);
  }

  /* 簡易輪詢管理：同一個 key 重複啟動時，先清掉舊的計時器 */
  var pollers = {};
  function startPoll(key, fn, intervalMs) {
    stopPoll(key);
    fn();
    pollers[key] = setInterval(fn, intervalMs);
  }
  function stopPoll(key) {
    if (pollers[key]) { clearInterval(pollers[key]); delete pollers[key]; }
  }

  /* ============================================================
   * 1. 離線預覽用的假資料 API
   *    當 window.pywebview 不存在時頂替真正的橋接，讓介面照樣可以操作、有資料可看。
   * ============================================================ */
  var FAKE_MIC_NAMES = ['麥克風陣列 (Realtek(R) Audio)', 'USB 麥克風 (USB Audio Device)', '耳機麥克風 (Headset)'];
  var FAKE_SENTENCES = [
    '今天的會議記錄我等一下傳給你，麻煩再幫我確認一下時間。',
    '這個 API 的 response time 有點慢，可能要優化一下 cache。',
    '晚點記得幫我訂晚餐，我想吃滷肉飯。',
    '麻煩把這份 report 的第二段重寫，語氣再正式一點。',
    '欸對了，明天的 deadline 記得提醒我一下。',
    '這段程式碼的 bug 應該是在 recorder 那邊，我等一下再看。',
    '會議改到下午三點，地點一樣在 302 會議室。',
    '幫我把這句話翻成英文，然後寄給客戶。',
    '測試一下語音輸入好不好用，這樣講應該沒問題吧。',
    '記得備份一下 database，上次忘記結果出事了。',
    '好，那我們就照這個方向繼續做下去。',
    '謝謝，辛苦了，明天見。'
  ];

  function buildFakeHistory() {
    var now = Date.now();
    var spreadMinutes = [2, 15, 40, 95, 190, 400, 900, 1600, 2600, 4200, 6000, 8000];
    return spreadMinutes.map(function (mins, i) {
      return {
        ts: Math.floor((now - mins * 60000) / 1000),
        text: FAKE_SENTENCES[i % FAKE_SENTENCES.length],
        engine: i % 3 === 0 ? 'qwen3' : 'breeze'
      };
    });
  }

  var fakeDb = {
    config: {
      hotkey: 'caps lock', hold_threshold_ms: 300, engine: 'breeze', paste_mode: 'clipboard',
      use_punct_model: true, force_language: null, sounds_enabled: true, mic_device: null,
      overlay_corner: 'bottom-right', history_enabled: true, autostart: false,
      first_run_done: true, qwen3_use_gpu: true
    },
    engines: { breeze: { ready: true, active: true }, qwen3: { ready: false, active: false } },
    download: { active: false, progress: 0, label: '' },
    downloadTimer: null,
    hotwords: '# 範例熱詞（可自行刪改；預覽模式資料）\n派森=Python\n欸皮愛=API\n',
    history: buildFakeHistory()
  };

  function fakeSimulateDownload(name) {
    clearInterval(fakeDb.downloadTimer);
    fakeDb.download = { active: true, progress: 0, label: '準備下載 ' + engineLabel(name) + '（預覽模擬）' };
    fakeDb.downloadTimer = setInterval(function () {
      fakeDb.download.progress = Math.min(1, fakeDb.download.progress + 0.09 + Math.random() * 0.08);
      if (fakeDb.download.progress >= 1) {
        clearInterval(fakeDb.downloadTimer);
        fakeDb.download = { active: false, progress: 1, label: engineLabel(name) + ' 下載完成（預覽模擬）' };
        if (fakeDb.engines[name]) fakeDb.engines[name].ready = true;
      } else {
        fakeDb.download.label = '下載中…（預覽模擬資料）';
      }
    }, 450);
  }

  var fakeApi = {
    get_state: async function () {
      await delay(70);
      return {
        engine: fakeDb.config.engine,
        engine_state: 'ready',
        recording: false,
        first_run_done: fakeDb.config.first_run_done,
        version: '1.0.0-preview'
      };
    },
    get_config: async function () { await delay(50); return Object.assign({}, fakeDb.config); },
    set_config: async function (patch) { await delay(60); Object.assign(fakeDb.config, patch); return Object.assign({}, fakeDb.config); },
    list_mics: async function () { await delay(180); return FAKE_MIC_NAMES.slice(); },
    get_engines: async function () { await delay(50); return JSON.parse(JSON.stringify(fakeDb.engines)); },
    switch_engine: async function (name) {
      await delay(500);
      Object.keys(fakeDb.engines).forEach(function (k) { fakeDb.engines[k].active = (k === name); });
      fakeDb.config.engine = name;
      return { ok: true };
    },
    download_engine: async function (name) {
      if (!fakeDb.download.active) fakeSimulateDownload(name);
      return { ok: true };
    },
    get_download_progress: async function () { await delay(20); return Object.assign({}, fakeDb.download); },
    get_hotwords: async function () { await delay(40); return fakeDb.hotwords; },
    set_hotwords: async function (text) { await delay(60); fakeDb.hotwords = text; return { ok: true }; },
    get_history: async function (limit) { await delay(70); return fakeDb.history.slice(0, limit || 200); },
    clear_history: async function () { await delay(60); fakeDb.history = []; return { ok: true }; },
    set_autostart: async function (enabled) { await delay(50); fakeDb.config.autostart = enabled; return { ok: true }; },
    mic_test_start: async function () { await delay(40); return { ok: true }; },
    mic_test_stop: async function () { await delay(40); return { ok: true, level: 0.3 + Math.random() * 0.5, seconds: 3.0 }; },
    env_check: async function () { await delay(550); return { cuda: true, detail: 'CUDA 裝置數：1（預覽模式模擬資料）' }; },
    mark_first_run_done: async function () { await delay(40); fakeDb.config.first_run_done = true; return { ok: true }; }
  };

  /* ============================================================
   * 2. API 分派：有 pywebview 就走真的，否則走假資料
   * ============================================================ */
  var usingFake = false;
  var API_METHODS = [
    'get_state', 'get_config', 'set_config', 'list_mics', 'get_engines', 'switch_engine',
    'download_engine', 'get_download_progress', 'get_hotwords', 'set_hotwords',
    'get_history', 'clear_history', 'set_autostart', 'mic_test_start', 'mic_test_stop',
    'env_check', 'mark_first_run_done'
  ];
  var Api = {};
  API_METHODS.forEach(function (name) {
    Api[name] = function () {
      var args = Array.prototype.slice.call(arguments);
      if (!usingFake && window.pywebview && window.pywebview.api && typeof window.pywebview.api[name] === 'function') {
        return window.pywebview.api[name].apply(window.pywebview.api, args);
      }
      return fakeApi[name].apply(fakeApi, args);
    };
  });

  function waitForPywebview(timeoutMs) {
    return new Promise(function (resolve) {
      if (window.pywebview && window.pywebview.api) { resolve(true); return; }
      var done = false;
      window.addEventListener('pywebviewready', function () {
        if (!done) { done = true; resolve(true); }
      });
      setTimeout(function () { if (!done) { done = true; resolve(false); } }, timeoutMs);
    });
  }

  function updateConnStatus(connected) {
    var chip = qs('#conn-status');
    chip.dataset.connected = connected ? 'true' : 'false';
    qs('#conn-status-text').textContent = connected ? '已連線' : '未連線（預覽模式）';
  }

  function renderVersion(v) {
    qs('#app-version').textContent = v ? 'v' + v : '';
  }

  function defaultConfigFallback() {
    return {
      hotkey: 'caps lock', hold_threshold_ms: 300, engine: 'breeze', paste_mode: 'clipboard',
      use_punct_model: true, force_language: null, sounds_enabled: true, mic_device: null,
      overlay_corner: 'bottom-right', history_enabled: true, autostart: false,
      first_run_done: true, qwen3_use_gpu: true
    };
  }

  var appState = { config: defaultConfigFallback() };

  /* ============================================================
   * 3. 導覽 / 分頁切換
   * ============================================================ */
  function initNavigation() {
    qsa('.nav-item').forEach(function (item) {
      item.addEventListener('click', function () { showTab(item.dataset.tab); });
    });
  }

  function showTab(name) {
    qsa('.nav-item').forEach(function (item) {
      item.setAttribute('aria-selected', String(item.dataset.tab === name));
    });
    qsa('.pane').forEach(function (pane) {
      pane.hidden = pane.dataset.tab !== name;
    });
    var active = qs('.pane[data-tab="' + name + '"]');
    if (!active) return;
    active.classList.remove('pane-anim');
    void active.offsetWidth; /* 強制 reflow，讓動畫每次切換都重新播放 */
    active.classList.add('pane-anim');
  }

  /* ============================================================
   * 4. 一般設定
   * ============================================================ */
  function updatePasteModeHint(value) {
    var hint = qs('#paste-mode-hint');
    hint.textContent = value === 'type'
      ? '模擬一字一字輸入，用於少數不支援貼上的視窗'
      : '貼上前先複製到剪貼簿再模擬 Ctrl+V，速度快、相容性最好';
  }

  function applyConfigToGeneralTab(cfg) {
    setSwitch(qs('#toggle-autostart'), !!cfg.autostart);
    setSwitch(qs('#toggle-sounds'), cfg.sounds_enabled !== false);
    var pasteMode = cfg.paste_mode || 'clipboard';
    setSegmented(qs('#paste-mode'), pasteMode);
    updatePasteModeHint(pasteMode);
  }

  function initGeneralTab() {
    var autostartBtn = qs('#toggle-autostart');
    autostartBtn.addEventListener('click', async function () {
      var next = autostartBtn.getAttribute('aria-checked') !== 'true';
      setSwitch(autostartBtn, next);
      autostartBtn.disabled = true;
      try {
        await Api.set_autostart(next);
        appState.config.autostart = next;
      } catch (err) {
        setSwitch(autostartBtn, !next);
        showToast('設定失敗，請稍後再試');
      } finally {
        autostartBtn.disabled = false;
      }
    });

    var soundsBtn = qs('#toggle-sounds');
    soundsBtn.addEventListener('click', async function () {
      var next = soundsBtn.getAttribute('aria-checked') !== 'true';
      setSwitch(soundsBtn, next);
      try {
        appState.config = await Api.set_config({ sounds_enabled: next });
      } catch (err) {
        setSwitch(soundsBtn, !next);
        showToast('設定失敗，請稍後再試');
      }
    });

    var pasteGroup = qs('#paste-mode');
    qsa('.segmented-btn', pasteGroup).forEach(function (btn) {
      btn.addEventListener('click', async function () {
        var value = btn.dataset.value;
        var prev = appState.config.paste_mode;
        setSegmented(pasteGroup, value);
        updatePasteModeHint(value);
        try {
          appState.config = await Api.set_config({ paste_mode: value });
        } catch (err) {
          setSegmented(pasteGroup, prev);
          updatePasteModeHint(prev);
          showToast('設定失敗，請稍後再試');
        }
      });
    });

    qs('#mic-select').addEventListener('change', async function (e) {
      var value = e.target.value;
      try {
        appState.config = await Api.set_config({ mic_device: value === '' ? null : value });
      } catch (err) {
        showToast('設定失敗，請稍後再試');
      }
    });
  }

  async function refreshMics(cfg) {
    var select = qs('#mic-select');
    var mics = [];
    try { mics = await Api.list_mics(); } catch (err) { mics = []; }
    select.innerHTML = '';
    var def = document.createElement('option');
    def.value = ''; def.textContent = '系統預設';
    select.appendChild(def);
    mics.forEach(function (name) {
      var opt = document.createElement('option');
      opt.value = name; opt.textContent = name;
      select.appendChild(opt);
    });
    var current = cfg.mic_device || '';
    select.value = current;
    if (current && select.value !== current) {
      var missing = document.createElement('option');
      missing.value = current; missing.textContent = current + '（未偵測到）';
      select.appendChild(missing);
      select.value = current;
    }
  }

  /* ============================================================
   * 5. 熱鍵
   * ============================================================ */
  var CODE_TO_NAME = {
    CapsLock: 'caps lock', Space: 'space', Tab: 'tab', Enter: 'enter', Escape: 'esc',
    Backspace: 'backspace', ControlLeft: 'ctrl', ControlRight: 'ctrl',
    AltLeft: 'alt', AltRight: 'alt', ShiftLeft: 'shift', ShiftRight: 'shift',
    MetaLeft: 'win', MetaRight: 'win', Insert: 'insert', Delete: 'delete',
    Home: 'home', End: 'end', PageUp: 'page up', PageDown: 'page down',
    ScrollLock: 'scroll lock', Pause: 'pause', NumLock: 'num lock', Backquote: '`'
  };
  var NAME_TO_DISPLAY = {
    'caps lock': 'Caps Lock', space: 'Space', tab: 'Tab', enter: 'Enter', esc: 'Esc',
    backspace: 'Backspace', ctrl: 'Ctrl', alt: 'Alt', shift: 'Shift', win: 'Win',
    insert: 'Insert', delete: 'Delete', home: 'Home', end: 'End',
    'page up': 'Page Up', 'page down': 'Page Down', 'scroll lock': 'Scroll Lock',
    pause: 'Pause', 'num lock': 'Num Lock'
  };

  function keyEventToName(e) {
    var code = e.code || '';
    if (CODE_TO_NAME[code]) return CODE_TO_NAME[code];
    if (/^Key[A-Z]$/.test(code)) return code.slice(3).toLowerCase();
    if (/^Digit[0-9]$/.test(code)) return code.slice(5);
    if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) return code.toLowerCase();
    if (/^Numpad[0-9]$/.test(code)) return 'numpad ' + code.slice(6);
    var k = (e.key || '').toLowerCase();
    return (k && k !== 'unidentified') ? k : code.toLowerCase();
  }

  function displayKeyName(name) {
    if (!name) return '—';
    if (NAME_TO_DISPLAY[name]) return NAME_TO_DISPLAY[name];
    return name.replace(/(^|\s)\S/g, function (c) { return c.toUpperCase(); });
  }

  function updateSliderFill(slider) {
    var min = Number(slider.min), max = Number(slider.max), val = Number(slider.value);
    var pct = ((val - min) / (max - min)) * 100;
    slider.style.setProperty('--fill', pct + '%');
  }

  function applyConfigToHotkeyTab(cfg) {
    qs('#hotkey-display').textContent = displayKeyName(cfg.hotkey || 'caps lock');
    var slider = qs('#hold-threshold');
    slider.value = cfg.hold_threshold_ms || 300;
    updateSliderFill(slider);
    qs('#hold-threshold-value').textContent = slider.value + ' ms';
  }

  var listening = false;
  var listenTimeout = null;

  function startListening() {
    listening = true;
    qs('#hotkey-capture').classList.add('listening');
    qs('#hotkey-capture-hint').textContent = '請按下新按鍵…（Esc 取消）';
    window.addEventListener('keydown', onCaptureKeydown, true);
    listenTimeout = setTimeout(cancelListening, 6000);
  }

  function cancelListening() {
    listening = false;
    clearTimeout(listenTimeout);
    window.removeEventListener('keydown', onCaptureKeydown, true);
    qs('#hotkey-capture').classList.remove('listening');
    qs('#hotkey-capture-hint').textContent = '點一下重新設定';
  }

  async function onCaptureKeydown(e) {
    e.preventDefault();
    e.stopPropagation();
    if (e.key === 'Escape') { cancelListening(); return; }
    var name = keyEventToName(e);
    cancelListening();
    qs('#hotkey-display').textContent = displayKeyName(name);
    try {
      appState.config = await Api.set_config({ hotkey: name });
      showToast('熱鍵已更新為 ' + displayKeyName(name));
    } catch (err) {
      showToast('設定失敗，請稍後再試');
    }
  }

  function initHotkeyTab() {
    qs('#hotkey-capture').addEventListener('click', function () {
      if (listening) { cancelListening(); } else { startListening(); }
    });

    var slider = qs('#hold-threshold');
    slider.addEventListener('input', function () {
      updateSliderFill(slider);
      qs('#hold-threshold-value').textContent = slider.value + ' ms';
    });
    slider.addEventListener('change', async function () {
      try {
        appState.config = await Api.set_config({ hold_threshold_ms: Number(slider.value) });
      } catch (err) {
        showToast('設定失敗，請稍後再試');
      }
    });
  }

  /* ============================================================
   * 6. 模型
   * ============================================================ */
  var latestEngines = { breeze: { ready: false, active: false }, qwen3: { ready: false, active: false } };
  var downloadingEngine = null;

  function renderEngineSummary() {
    var cfg = appState.config || {};
    var name = cfg.engine || 'breeze';
    var info = latestEngines[name] || {};
    var el = qs('#engine-summary');
    if (!el) return;
    el.textContent = '目前引擎：' + engineLabel(name) + (info.ready ? '' : '（未下載）');
  }

  function renderModelsTab(engines) {
    ['breeze', 'qwen3'].forEach(function (name) {
      var info = engines[name] || { ready: false, active: false };
      var card = qs('.engine-card[data-engine="' + name + '"]');
      if (!card) return;
      var pill = qs('.pill', card);
      var downloadBtn = qs('[data-action="download"]', card);
      var switchBtn = qs('[data-action="switch"]', card);
      if (info.active) {
        pill.textContent = '使用中'; pill.dataset.state = 'active';
        downloadBtn.hidden = true;
        switchBtn.hidden = true;
      } else if (info.ready) {
        pill.textContent = '已下載'; pill.dataset.state = 'ready';
        downloadBtn.hidden = true;
        switchBtn.hidden = false;
        switchBtn.disabled = false;
        switchBtn.textContent = '切換使用';
      } else {
        pill.textContent = '未下載'; pill.dataset.state = 'none';
        downloadBtn.hidden = false;
        downloadBtn.disabled = !!downloadingEngine && downloadingEngine !== name;
        switchBtn.hidden = true;
      }
    });
  }

  function setDownloadButtonsDisabled(disabled) {
    qsa('[data-action="download"]').forEach(function (b) { b.disabled = disabled; });
  }

  function setWizardDownloadButtonMode(mode) {
    var btn = qs('#wizard-start-download');
    if (!btn) return;
    btn.dataset.mode = mode;
    btn.textContent = mode === 'next' ? '下一步' : '開始下載';
  }

  function onWizardDownloadSettled() {
    var btn = qs('#wizard-start-download');
    if (!btn) return;
    btn.disabled = false;
    setWizardDownloadButtonMode('next');
  }

  function updateDownloadUI(st) {
    var pct = Math.round((st.progress || 0) * 100);
    var failed = /失敗/.test(st.label || '');

    if (downloadingEngine) {
      var card = qs('.engine-card[data-engine="' + downloadingEngine + '"]');
      if (card) {
        var progress = qs('.progress', card);
        progress.hidden = false;
        qs('.progress-fill', progress).style.width = pct + '%';
        qs('.progress-text', progress).textContent = st.label || '下載中…';
        qs('.progress-pct', progress).textContent = pct + '%';
        progress.classList.toggle('is-active', !!st.active);
        progress.classList.toggle('is-done', !st.active && !failed);
        progress.classList.toggle('is-error', !st.active && failed);
      }
    }

    var wizardFill = qs('#wizard-dl-fill');
    if (wizardFill) {
      wizardFill.style.width = pct + '%';
      qs('#wizard-dl-label').textContent = st.label || (st.active ? '下載中…' : '尚未開始下載');
      qs('#wizard-dl-pct').textContent = pct + '%';
      var wp = qs('#wizard-progress');
      wp.classList.toggle('is-active', !!st.active);
      wp.classList.toggle('is-done', !st.active && !failed && pct > 0);
      wp.classList.toggle('is-error', !st.active && failed);
    }
  }

  async function pollDownload() {
    var st;
    try { st = await Api.get_download_progress(); } catch (err) { return; }
    updateDownloadUI(st);
    if (!st.active) {
      stopPoll('download');
      var finishedEngine = downloadingEngine;
      downloadingEngine = null;
      setDownloadButtonsDisabled(false);
      try {
        latestEngines = await Api.get_engines();
        renderModelsTab(latestEngines);
        renderEngineSummary();
      } catch (err) { /* 忽略，畫面保留舊資料即可 */ }
      var failed = /失敗/.test(st.label || '');
      if (finishedEngine) {
        showToast(failed ? (engineLabel(finishedEngine) + ' 下載失敗') : (engineLabel(finishedEngine) + ' 下載完成'));
      }
      onWizardDownloadSettled();
    }
  }

  async function onDownloadClick(name) {
    if (downloadingEngine) return;
    downloadingEngine = name;
    setDownloadButtonsDisabled(true);
    var card = qs('.engine-card[data-engine="' + name + '"]');
    var progress = qs('.progress', card);
    progress.hidden = false;
    progress.classList.add('is-active');
    progress.classList.remove('is-done', 'is-error');
    qs('.progress-text', progress).textContent = '準備下載…';
    qs('.progress-pct', progress).textContent = '0%';
    qs('.progress-fill', progress).style.width = '0%';
    try {
      await Api.download_engine(name);
      startPoll('download', pollDownload, 1000);
    } catch (err) {
      downloadingEngine = null;
      setDownloadButtonsDisabled(false);
      progress.classList.remove('is-active');
      showToast('下載無法啟動，請確認網路連線');
    }
  }

  async function onSwitchClick(name) {
    var card = qs('.engine-card[data-engine="' + name + '"]');
    var switchBtn = qs('[data-action="switch"]', card);
    switchBtn.disabled = true;
    switchBtn.textContent = '切換中…';
    try {
      var res = await Api.switch_engine(name);
      if (!res || res.ok === false) {
        showToast('切換失敗' + (res && res.error ? '：' + res.error : ''));
        switchBtn.disabled = false;
        switchBtn.textContent = '切換使用';
        return;
      }
      appState.config.engine = name;
      startPoll('switch', function () { pollEngineSwitch(name); }, 1000);
    } catch (err) {
      showToast('切換失敗，請稍後再試');
      switchBtn.disabled = false;
      switchBtn.textContent = '切換使用';
    }
  }

  async function pollEngineSwitch(name) {
    var state;
    try { state = await Api.get_state(); } catch (err) { return; }
    if (state.engine_state === 'loading') return;
    stopPoll('switch');
    try { latestEngines = await Api.get_engines(); } catch (err) { /* 忽略 */ }
    renderModelsTab(latestEngines);
    renderEngineSummary();
    showToast(state.engine_state === 'ready'
      ? ('已切換至 ' + engineLabel(name))
      : ('切換 ' + engineLabel(name) + ' 時發生錯誤，請查看記錄'));
  }

  function initModelsTab() {
    qsa('.engine-card').forEach(function (card) {
      var name = card.dataset.engine;
      qs('[data-action="download"]', card).addEventListener('click', function () { onDownloadClick(name); });
      qs('[data-action="switch"]', card).addEventListener('click', function () { onSwitchClick(name); });
    });
  }

  async function refreshEngines() {
    try {
      latestEngines = await Api.get_engines();
    } catch (err) {
      latestEngines = { breeze: { ready: false, active: false }, qwen3: { ready: false, active: false } };
    }
    renderModelsTab(latestEngines);
    renderEngineSummary();
    /* 若視窗重新整理時剛好有下載在背景進行，恢復輪詢顯示進度 */
    try {
      var st = await Api.get_download_progress();
      if (st.active) {
        downloadingEngine = downloadingEngine || 'breeze';
        setDownloadButtonsDisabled(true);
        var card = qs('.engine-card[data-engine="' + downloadingEngine + '"]');
        if (card) qs('.progress', card).hidden = false;
        startPoll('download', pollDownload, 1000);
      }
    } catch (err) { /* 忽略 */ }
  }

  /* ============================================================
   * 7. 熱詞
   * ============================================================ */
  var hotwordsLastSaved = '';

  async function refreshHotwords() {
    var text = '';
    try { text = await Api.get_hotwords(); } catch (err) { text = ''; }
    hotwordsLastSaved = text;
    qs('#hotwords-text').value = text;
    var hint = qs('#hotwords-hint');
    hint.textContent = '';
    hint.className = 'save-hint';
  }

  async function saveHotwords() {
    var btn = qs('#hotwords-save');
    var textarea = qs('#hotwords-text');
    btn.disabled = true;
    try {
      await Api.set_hotwords(textarea.value);
      hotwordsLastSaved = textarea.value;
      var hint = qs('#hotwords-hint');
      hint.textContent = '已儲存';
      hint.className = 'save-hint saved';
      showToast('熱詞已儲存');
    } catch (err) {
      showToast('儲存失敗，請稍後再試');
    } finally {
      btn.disabled = false;
    }
  }

  function initHotwordsTab() {
    var textarea = qs('#hotwords-text');
    textarea.addEventListener('input', function () {
      var hint = qs('#hotwords-hint');
      if (textarea.value !== hotwordsLastSaved) {
        hint.textContent = '有未儲存的變更';
        hint.className = 'save-hint dirty';
      } else {
        hint.textContent = '';
        hint.className = 'save-hint';
      }
    });
    textarea.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        saveHotwords();
      }
    });
    qs('#hotwords-save').addEventListener('click', saveHotwords);
  }

  /* ============================================================
   * 8. 歷史
   * ============================================================ */
  function applyHistoryToggle(cfg) {
    setSwitch(qs('#toggle-history'), cfg.history_enabled !== false);
  }

  function renderHistory(rows) {
    var list = qs('#history-list');
    var empty = qs('#history-empty');
    list.innerHTML = '';
    qs('#history-count').textContent = '共 ' + rows.length + ' 筆';
    if (!rows.length) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    rows.forEach(function (row) {
      var btn = document.createElement('button');
      btn.className = 'history-row';
      btn.type = 'button';

      var time = document.createElement('span');
      time.className = 'history-time mono';
      time.textContent = formatTs(row.ts);

      var badge = document.createElement('span');
      badge.className = 'badge ' + (row.engine === 'qwen3' ? 'badge-qwen3' : 'badge-breeze');
      badge.textContent = engineLabel(row.engine);

      var text = document.createElement('span');
      text.className = 'history-text';
      text.textContent = row.text;
      text.title = row.text;

      var flash = document.createElement('span');
      flash.className = 'history-copied-flash';
      flash.textContent = '已複製';
      flash.setAttribute('aria-hidden', 'true'); /* 視覺提示用，避免螢幕報讀器在每一列都唸出「已複製」 */

      btn.appendChild(time);
      btn.appendChild(badge);
      btn.appendChild(text);
      btn.appendChild(flash);

      btn.addEventListener('click', async function () {
        var ok = await copyText(row.text);
        if (ok) {
          btn.classList.add('just-copied');
          showToast('已複製到剪貼簿');
          setTimeout(function () { btn.classList.remove('just-copied'); }, 900);
        } else {
          showToast('複製失敗，請手動選取文字');
        }
      });

      list.appendChild(btn);
    });
  }

  async function refreshHistory(cfg) {
    applyHistoryToggle(cfg || appState.config || {});
    var rows = [];
    try { rows = await Api.get_history(200); } catch (err) { rows = []; }
    renderHistory(rows);
  }

  function initHistoryTab() {
    var toggleBtn = qs('#toggle-history');
    toggleBtn.addEventListener('click', async function () {
      var next = toggleBtn.getAttribute('aria-checked') !== 'true';
      setSwitch(toggleBtn, next);
      try {
        appState.config = await Api.set_config({ history_enabled: next });
      } catch (err) {
        setSwitch(toggleBtn, !next);
        showToast('設定失敗，請稍後再試');
      }
    });

    qs('#history-clear').addEventListener('click', function (e) {
      confirmDangerAction(e.currentTarget, '確定清空？', async function () {
        try {
          await Api.clear_history();
          await refreshHistory(appState.config);
          showToast('已清空歷史紀錄');
        } catch (err) {
          showToast('清空失敗，請稍後再試');
        }
      });
    });
  }

  /* ============================================================
   * 9. 首次啟動精靈
   * ============================================================ */
  var micTestCompleted = false;
  var wizardStep = 1;

  function buildLevelMeter(container, n) {
    container.innerHTML = '';
    for (var i = 0; i < n; i++) {
      var seg = document.createElement('span');
      seg.className = 'seg';
      container.appendChild(seg);
    }
  }

  function setLevelMeter(container, level) {
    var segs = qsa('.seg', container);
    var clamped = Math.max(0, Math.min(1, level));
    var lit = Math.round(clamped * segs.length);
    segs.forEach(function (seg, i) {
      seg.classList.remove('lit-low', 'lit-mid', 'lit-high');
      if (i < lit) {
        var zone = i / segs.length;
        seg.classList.add(zone < 0.6 ? 'lit-low' : (zone < 0.85 ? 'lit-mid' : 'lit-high'));
      }
    });
  }

  function setIconPath(pathEl, d) { pathEl.setAttribute('d', d); }

  function goToWizardStep(n) {
    wizardStep = n;
    qsa('.wizard-pane').forEach(function (p) { p.hidden = Number(p.dataset.step) !== n; });
    qsa('.wizard-step-dot').forEach(function (dot) {
      var s = Number(dot.dataset.step);
      dot.classList.toggle('done', s < n);
      dot.classList.toggle('current', s === n);
    });
    qsa('.wizard-step-line').forEach(function (line) {
      var s = Number(line.dataset.line);
      line.classList.toggle('done', s < n);
    });
    if (n === 2) onEnterWizardStep2();
    if (n === 3) onEnterWizardStep3();
  }

  async function runEnvCheck() {
    var resultBox = qs('#env-result');
    var spinner = qs('#env-spinner');
    var icon = qs('#env-icon');
    spinner.hidden = false; icon.hidden = true;
    resultBox.classList.remove('ok', 'warn');
    qs('#env-title').textContent = '正在檢查環境…';
    qs('#env-detail').textContent = '';
    qs('#env-note').hidden = true;
    qs('#wizard-next-1').disabled = true;

    var res;
    try {
      res = await Api.env_check();
    } catch (err) {
      res = { cuda: false, detail: '檢查失敗，可稍後於「模型」分頁重新確認' };
    }

    spinner.hidden = true; icon.hidden = false;
    if (res.cuda) {
      resultBox.classList.add('ok');
      setIconPath(qs('#env-icon-path'), 'M5 13l4 4L19 7');
      qs('#env-title').textContent = 'GPU 加速：可使用';
    } else {
      resultBox.classList.add('warn');
      setIconPath(qs('#env-icon-path'), 'M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z');
      qs('#env-title').textContent = '未偵測到 GPU 加速';
      var note = qs('#env-note');
      note.hidden = false;
      note.textContent = '仍可用 CPU 模式運作，只是辨識速度會比較慢。';
    }
    qs('#env-detail').textContent = res.detail || '';
    qs('#wizard-next-1').disabled = false;
  }

  async function onEnterWizardStep2() {
    var btn = qs('#wizard-start-download');
    try {
      latestEngines = await Api.get_engines();
      if (latestEngines.breeze && latestEngines.breeze.ready) {
        var wp = qs('#wizard-progress');
        qs('#wizard-dl-fill').style.width = '100%';
        qs('#wizard-dl-pct').textContent = '100%';
        qs('#wizard-dl-label').textContent = 'Breeze 模型已下載完成';
        wp.classList.add('is-done');
        wp.classList.remove('is-active', 'is-error');
        btn.disabled = false;
        setWizardDownloadButtonMode('next');
        return;
      }
    } catch (err) { /* 忽略，走一般下載流程 */ }

    try {
      var st = await Api.get_download_progress();
      if (st.active) {
        downloadingEngine = downloadingEngine || 'breeze';
        btn.disabled = true;
        startPoll('download', pollDownload, 1000);
      } else {
        btn.disabled = false;
        setWizardDownloadButtonMode('start');
      }
    } catch (err) {
      btn.disabled = false;
      setWizardDownloadButtonMode('start');
    }
  }

  function onEnterWizardStep3() {
    qs('#wizard-finish').disabled = !micTestCompleted;
  }

  async function onWizardDownloadBtnClick() {
    var btn = qs('#wizard-start-download');
    if (btn.dataset.mode === 'next') { goToWizardStep(3); return; }
    btn.disabled = true;
    downloadingEngine = 'breeze';
    var wp = qs('#wizard-progress');
    wp.classList.add('is-active');
    wp.classList.remove('is-done', 'is-error');
    qs('#wizard-dl-label').textContent = '準備下載…';
    try {
      await Api.download_engine('breeze');
      startPoll('download', pollDownload, 1000);
    } catch (err) {
      btn.disabled = false;
      showToast('下載無法啟動，請確認網路連線');
    }
  }

  async function onWizardMicBtnClick() {
    var btn = qs('#wizard-mic-btn');
    if (btn.classList.contains('recording')) return;
    btn.classList.add('recording');
    btn.disabled = true;
    qs('#wizard-mic-result').textContent = '';
    qs('#wizard-mic-result').className = 'mic-test-result';
    setLevelMeter(qs('#wizard-mic-meter'), 0);

    try {
      await Api.mic_test_start();
    } catch (err) {
      btn.classList.remove('recording');
      btn.disabled = false;
      qs('#wizard-mic-hint').textContent = '點一下開始，錄 3 秒';
      showToast('無法開始錄音，請確認麥克風權限');
      return;
    }

    var tick = 3;
    qs('#wizard-mic-hint').textContent = '錄音中… ' + tick;
    var countdown = setInterval(function () {
      tick -= 1;
      if (tick > 0) qs('#wizard-mic-hint').textContent = '錄音中… ' + tick;
    }, 1000);

    setTimeout(async function () {
      clearInterval(countdown);
      var res;
      try {
        res = await Api.mic_test_stop();
      } catch (err) {
        res = { ok: false, level: 0, seconds: 0 };
      }
      btn.classList.remove('recording');
      btn.disabled = false;
      qs('#wizard-mic-hint').textContent = '點一下重新測試';

      var level = res.level || 0;
      setLevelMeter(qs('#wizard-mic-meter'), level);
      var resultEl = qs('#wizard-mic-result');
      if (level >= 0.04) {
        resultEl.textContent = '收到聲音了！音量約 ' + Math.round(level * 100) + '%';
        resultEl.className = 'mic-test-result ok';
      } else {
        resultEl.textContent = '沒有偵測到聲音，請確認麥克風已連接並允許存取權限';
        resultEl.className = 'mic-test-result warn';
      }
      micTestCompleted = true;
      qs('#wizard-finish').disabled = false;
    }, 3000);
  }

  async function onWizardFinish() {
    var btn = qs('#wizard-finish');
    btn.disabled = true;
    try {
      await Api.mark_first_run_done();
    } catch (err) { /* 即使失敗也讓使用者進入主畫面，不要卡住精靈 */ }
    appState.config.first_run_done = true;
    showShell();
    try { await refreshEngines(); } catch (err) { /* 忽略 */ }
    try { await refreshHistory(appState.config); } catch (err) { /* 忽略 */ }
  }

  function initWizard() {
    qs('#wizard-next-1').addEventListener('click', function () { goToWizardStep(2); });
    qs('#wizard-back-2').addEventListener('click', function () { goToWizardStep(1); });
    qs('#wizard-back-3').addEventListener('click', function () { goToWizardStep(2); });
    qs('#wizard-start-download').addEventListener('click', onWizardDownloadBtnClick);
    qs('#wizard-mic-btn').addEventListener('click', onWizardMicBtnClick);
    qs('#wizard-finish').addEventListener('click', onWizardFinish);
    buildLevelMeter(qs('#wizard-mic-meter'), 20);
  }

  function showWizard() {
    qs('#shell').hidden = true;
    qs('#wizard').hidden = false;
    goToWizardStep(1);
    runEnvCheck();
  }

  function showShell() {
    qs('#wizard').hidden = true;
    qs('#shell').hidden = false;
  }

  /* ============================================================
   * 10. 開機流程
   * ============================================================ */
  async function boot() {
    try {
      var ready = await waitForPywebview(700);
      usingFake = !ready || !(window.pywebview && window.pywebview.api);
    } catch (err) {
      usingFake = true;
    }
    updateConnStatus(!usingFake);

    initNavigation();
    initGeneralTab();
    initHotkeyTab();
    initModelsTab();
    initHotwordsTab();
    initHistoryTab();
    initWizard();

    var state;
    try {
      state = await Api.get_state();
    } catch (err) {
      state = { first_run_done: true, version: '', engine: 'breeze', engine_state: 'idle', recording: false };
    }

    var cfg;
    try {
      cfg = await Api.get_config();
    } catch (err) {
      cfg = defaultConfigFallback();
    }

    appState.config = cfg;
    renderVersion(state.version);

    try { applyConfigToGeneralTab(cfg); } catch (err) { /* 不讓渲染錯誤卡住畫面 */ }
    try { applyConfigToHotkeyTab(cfg); } catch (err) { /* 同上 */ }

    try { await refreshMics(cfg); } catch (err) { /* 忽略 */ }
    try { await refreshEngines(); } catch (err) { /* 忽略 */ }
    try { await refreshHotwords(); } catch (err) { /* 忽略 */ }
    try { await refreshHistory(cfg); } catch (err) { /* 忽略 */ }

    if (state.first_run_done === false) {
      showWizard();
    } else {
      showShell();
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    boot().catch(function () {
      /* 最後防線：任何未預期的錯誤都不能讓畫面白屏 */
      updateConnStatus(false);
      showShell();
    });
  });
})();
