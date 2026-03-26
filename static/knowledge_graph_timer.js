/**
 * ============================================================
 * knowledge_graph_timer.js
 * 计时器 + 图谱加速状态指示器（前端部分）
 * 职责：
 *   1. 分析开始时启动计时器
 *   2. 分析结束时显示总耗时（秒）并变色
 *   3. 读取后端返回的 graph_boost 字段并显示图谱加速状态
 * 完全独立，不修改任何原有 JS 逻辑
 * ============================================================
 */

(function () {
  "use strict";

  /* ---- SVG 图标（内联，不依赖外部资源） ---- */
  var SPINNER_SVG = [
    '<svg id="timer-icon" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">',
    '<circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 2" opacity="0.5"/>',
    '<path d="M8 3.5A4.5 4.5 0 0 1 12.5 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
    '</svg>',
  ].join("");

  var CHECK_SVG = [
    '<svg id="timer-icon" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">',
    '<circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/>',
    '<path d="M5 8l2.2 2.2L11 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
    '</svg>',
  ].join("");

  var GRAPH_SVG = [
    '<svg width="10" height="10" viewBox="0 0 10 10" fill="none" xmlns="http://www.w3.org/2000/svg">',
    '<circle cx="2" cy="2" r="1.5" fill="currentColor"/>',
    '<circle cx="8" cy="2" r="1.5" fill="currentColor"/>',
    '<circle cx="5" cy="8" r="1.5" fill="currentColor"/>',
    '<line x1="3.3" y1="2.9" x2="4" y2="7.1" stroke="currentColor" stroke-width="1"/>',
    '<line x1="6.7" y1="2.9" x2="6" y2="7.1" stroke="currentColor" stroke-width="1"/>',
    '<line x1="3.5" y1="2" x2="6.5" y2="2" stroke="currentColor" stroke-width="1"/>',
    '</svg>',
  ].join("");

  /* ---- 计时器状态 ---- */
  var _timerStart = null;    // Date.now() of analysis start
  var _timerInterval = null; // setInterval handle
  var _analyzeBtn = null;    // 原"开始分析"按钮（由外层提供）

  /* ---- 公共 API（供外层 analyzeBtn.addEventListener 调用前挂载） ---- */
  function startTimer() {
    _timerStart = Date.now();
    var widget = getOrCreateWidget();
    widget.className = "running";
    updateDisplay(widget, 0, true);
    // 每 100ms 刷新显示
    if (_timerInterval) clearInterval(_timerInterval);
    _timerInterval = setInterval(function () {
      if (_timerStart) {
        var elapsed = Date.now() - _timerStart;
        var w = document.getElementById("timer-widget");
        if (w) updateDisplay(w, elapsed, true);
      }
    }, 100);
  }

  function stopTimer() {
    if (_timerInterval) {
      clearInterval(_timerInterval);
      _timerInterval = null;
    }
    if (!_timerStart) return;
    var elapsed = Date.now() - _timerStart;
    _timerStart = null;
    var widget = document.getElementById("timer-widget");
    if (!widget) return;
    widget.className = elapsed > 60000 ? "slow" : "done";
    updateDisplay(widget, elapsed, false);
  }

  /**
   * 刷新图谱加速状态指示器
   * @param {object} boostData  — 后端返回的 graph_boost 字段
   *   { enabled: bool, skipped_stages: string[], speedup_ratio: float }
   */
  function updateGraphStatus(boostData) {
    var el = document.getElementById("graph-status");
    if (!el) return;
    var label = document.getElementById("graph-status-label");
    if (!boostData || !boostData.enabled) {
      el.className = "normal";
      if (boostData && boostData.suppressed_by_client) {
        el.title = "本次请求已关闭知识图谱加速";
        if (label) label.textContent = "本次已关闭";
      } else {
        el.title = "知识图谱加速由服务端控制。勾选框只决定是否请求启用；若服务端未加载该模块，会显示此状态。";
        if (label) label.textContent = "服务端未加载";
      }
      return;
    }
    el.className = "boosted";
    var ratio = boostData.speedup_ratio || 0;
    var stages = (boostData.skipped_stages || []).join(", ");
    var tip = "知识图谱已参与（启发式加速约 " + Math.round(ratio * 100) + "%）"
      + (stages ? "\n索引命中项：" + stages : "");
    el.title = tip;
    if (label) label.textContent = "已参与";
  }

  /* ---- 私有辅助 ---- */

  function getOrCreateWidget() {
    var w = document.getElementById("timer-widget");
    if (!w) {
      var btn = document.getElementById("analyzeBtn");
      if (!btn) return document.createElement("div");
      w = document.createElement("div");
      w.id = "timer-widget";
      btn.parentNode.insertBefore(w, btn.nextSibling);
    }
    /* index.html 里可能预留了空节点：必须补齐内部结构，否则计时数字永远不会出现 */
    if (!document.getElementById("timer-ms")) {
      w.innerHTML = '<span id="timer-icon-wrap"></span><span id="timer-ms">0.0s</span>';
    }
    return w;
  }

  function updateDisplay(widget, elapsedMs, isRunning) {
    var iconWrap = document.getElementById("timer-icon-wrap");
    var msEl = document.getElementById("timer-ms");
    if (!widget || !msEl) return;
    var seconds = elapsedMs / 1000;
    msEl.textContent = seconds < 10
      ? seconds.toFixed(1) + "s"
      : Math.round(seconds) + "s";
    if (iconWrap) {
      iconWrap.innerHTML = isRunning ? SPINNER_SVG : CHECK_SVG;
    }
  }

  /* ---- 自动挂载：拦截原生 analyzeBtn 事件 ---- */
  function bootstrap() {
    var btn = document.getElementById("analyzeBtn");
    if (!btn) return;
    // 监听原生点击事件，在其之前先启动计时器
    btn.addEventListener("click", function () {
      startTimer();
    }, true); // true = capture，在原生逻辑之前执行

    // 也监听原生 fetch 成功/失败，统一停表
    var _origFetch = window.fetch;
    window.fetch = function (input, init) {
      var args = arguments;
      // 仅拦截 /api/analyze* 请求
      var url = typeof input === "string" ? input : input.url || "";
      var isAnalyze = /\/api\/analyze/.test(url);
      if (isAnalyze) {
        startTimer();
      }
      return _origFetch.apply(this, args).then(
        function (res) {
          if (isAnalyze) {
            res.clone().json().then(function (data) {
              stopTimer();
              updateGraphStatus(data.graph_boost);
            }).catch(function () {
              stopTimer();
            });
          }
          return res;
        },
        function (err) {
          if (isAnalyze) stopTimer();
          return Promise.reject(err);
        }
      );
    };
  }

  /* ---- 入口：DOMContentLoaded 后初始化 ---- */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
  } else {
    bootstrap();
  }

  /* ---- 暴露最小化公共 API（可选） ---- */
  window.__kgTimer = {
    start: startTimer,
    stop: stopTimer,
    setGraphStatus: updateGraphStatus,
  };
})();
