const transcriptEl = document.getElementById("transcript");
const jobHintEl = document.getElementById("jobHint");
const sampleSelectEl = document.getElementById("sampleSelect");
const audioFileEl = document.getElementById("audioFile");
const audioLanguageEl = document.getElementById("audioLanguage");
const captureMicEl = document.getElementById("captureMic");
const captureSystemEl = document.getElementById("captureSystem");
const analyzeBtn = document.getElementById("analyzeBtn");
const realtimeBtn = document.getElementById("realtimeBtn");
const audioRealtimeBtn = document.getElementById("audioRealtimeBtn");
const liveWsBtn = document.getElementById("liveWsBtn");
const toggleMicRouteBtn = document.getElementById("toggleMicRouteBtn");
const toggleSystemRouteBtn = document.getElementById("toggleSystemRouteBtn");
const sampleBtn = document.getElementById("sampleBtn");
const statusEl = document.getElementById("status");
const inputView = document.getElementById("inputView");
const loadingView = document.getElementById("loadingView");
const resultView = document.getElementById("resultView");
const loadingStepsEl = document.getElementById("loadingSteps");
const loadingMessageEl = document.getElementById("loadingMessage");
const errorBoxEl = document.getElementById("errorBox");
const errorTextEl = document.getElementById("errorText");
const retryBtn = document.getElementById("retryBtn");
const backBtn = document.getElementById("backBtn");
const editAgainBtn = document.getElementById("editAgainBtn");
const realtimePauseBtn = document.getElementById("realtimePauseBtn");
const realtimeEndBtn = document.getElementById("realtimeEndBtn");
const viewFullReportBtn = document.getElementById("viewFullReportBtn");
const quickCard = document.getElementById("modeQuickCard");
const fullCard = document.getElementById("modeFullCard");
const modeQuickEl = document.getElementById("modeQuick");
const modeFullEl = document.getElementById("modeFull");

const TEXT = {
  na: "\u6682\u65e0",
  selectSample: "\u8bf7\u9009\u62e9\u6837\u4f8b",
  fill: "\u586b\u5145\u793a\u4f8b",
  loading: "\u52a0\u8f7d\u4e2d...",
  run: "\u5f00\u59cb\u5206\u6790",
  requestFailed: "\u8bf7\u6c42\u5931\u8d25",
  noFollowup: "\u6682\u65e0\u8ffd\u95ee\u5efa\u8bae",
  weakSignals: "\u5f53\u524d\u6837\u672c\u4fe1\u53f7\u4ecd\u7136\u504f\u5f31\u3002",
};

const DISC_META = {
  D: { label: "D / \u652f\u914d", className: "d", style: "\u76f4\u63a5\u63a8\u52a8\u578b" },
  I: { label: "I / \u5f71\u54cd", className: "i", style: "\u8868\u8fbe\u611f\u67d3\u578b" },
  S: { label: "S / \u7a33\u5b9a", className: "s", style: "\u7a33\u5b9a\u8010\u5fc3\u578b" },
  C: { label: "C / \u8c28\u614e", className: "c", style: "\u4e25\u8c28\u5ba1\u614e\u578b" },
};

const DEFAULT_TRANSCRIPT = `Interviewer: Walk me through a project you led.
Candidate: I worked on an order system optimization project. Traffic spikes caused unstable latency, so I reviewed logs, compared response times, reduced duplicate queries, and added a cache layer. Overall performance improved after the change.
Interviewer: How did you locate the root cause?
Candidate: I started from logs and slow endpoints, then checked repeated reads and timing patterns before deciding where to optimize.`;

const LOADING_STEPS_QUICK = [
  "\u89e3\u6790\u9762\u8bd5\u6587\u672c",
  "\u63d0\u53d6\u5173\u952e\u8bc1\u636e",
  "\u751f\u6210 DISC / MBTI \u7ed3\u679c",
];

const LOADING_STEPS_FULL = [
  "\u89e3\u6790\u9762\u8bd5\u6587\u672c",
  "\u8fd0\u884c DISC / MBTI / STAR \u5206\u6790",
  "\u8fd0\u884c\u4e94\u5927\u4eba\u683c / \u4e5d\u578b\u4eba\u683c / \u7efc\u5408\u6620\u5c04",
];

let sampleLibrary = [];
let lastPayload = null;
let currentTaskId = null;
let pollTimer = null;
let loadingTimer = null;
let realtimeSessionId = null;
let realtimeSegments = [];
let realtimeSegmentIndex = 0;
let realtimeTimer = null;
let realtimeRunning = false;
let realtimeDemoMode = false;
let liveStreamingMode = false;
let micSocket = null;
let micStream = null;
let systemStream = null;
let micAudioContext = null;
let audioSourceNodes = [];
let audioAnalyserNodes = {};
let micProcessorNode = null;
let micSilentGain = null;
let levelMeterTimer = null;
let liveMediaRecorders = [];
let liveChunkDurationMs = 5000;
let liveSourceEnabled = { mic: true, system: true };
const LIVE_MIN_CHUNK_BYTES = { mic: 4000, system: 16000 };
let liveChunkCursorMs = { mic: 0, system: 0 };
let liveUploadInflight = { mic: Promise.resolve(), system: Promise.resolve() };
let realtimePartialBySpeaker = {};
let lastRenderedSegmentCount = 0;
let pendingFinalRealtimeReport = null;
let latestRealtimeSession = null;

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value, fallback = TEXT.na) {
  const el = byId(id);
  if (el) el.textContent = value === undefined || value === null || value === "" ? fallback : String(value);
}

function setHtml(id, html) {
  const el = byId(id);
  if (el) el.innerHTML = html;
}

function setRouteButtonState(name) {
  const btn = name === "mic" ? toggleMicRouteBtn : toggleSystemRouteBtn;
  if (!btn) return;
  const enabled = Boolean(liveSourceEnabled[name]);
  btn.classList.toggle("active", enabled);
  btn.classList.toggle("inactive", !enabled);
  btn.textContent = name === "mic"
    ? (enabled ? "\u9ea6\u514b\u98ce\u5df2\u5f00\u542f" : "\u9ea6\u514b\u98ce\u5df2\u5173\u95ed")
    : (enabled ? "\u7cfb\u7edf\u97f3\u9891\u5df2\u5f00\u542f" : "\u7cfb\u7edf\u97f3\u9891\u5df2\u5173\u95ed");
}

function refreshRouteButtons() {
  setRouteButtonState("mic");
  setRouteButtonState("system");
}

function toggleLiveRoute(name) {
  liveSourceEnabled[name] = !liveSourceEnabled[name];
  refreshRouteButtons();
  const hint = byId("audioDebugHint");
  if (hint) {
    hint.textContent = name === "mic"
      ? (liveSourceEnabled[name] ? "\u5df2\u6062\u590d\u63a5\u6536\u9ea6\u514b\u98ce\u5206\u7247\u3002" : "\u5df2\u6682\u505c\u63a5\u6536\u9ea6\u514b\u98ce\u5206\u7247\u3002")
      : (liveSourceEnabled[name] ? "\u5df2\u6062\u590d\u63a5\u6536\u7cfb\u7edf\u97f3\u9891\u5206\u7247\u3002" : "\u5df2\u6682\u505c\u63a5\u6536\u7cfb\u7edf\u97f3\u9891\u5206\u7247\u3002");
  }
}

function safeText(value, fallback = TEXT.na) {
  return value === undefined || value === null || value === "" ? fallback : String(value);
}

function createList(items, renderItem, empty = TEXT.na) {
  if (!items || !items.length) return `<div class="list-item"><p>${empty}</p></div>`;
  return items.map(renderItem).join("");
}

function trimText(value, limit = 120, fallback = TEXT.na) {
  const raw = safeText(value, fallback).replace(/\s+/g, " ").trim();
  return raw.length <= limit ? raw : `${raw.slice(0, limit)}...`;
}

function rankDimensions(scores) {
  return Object.entries(scores || {}).sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0));
}

function getCurrentMode() {
  return modeFullEl && modeFullEl.checked ? "full" : "quick";
}

function applyModeCards() {
  const full = getCurrentMode() === "full";
  if (quickCard) quickCard.classList.toggle("active", !full);
  if (fullCard) fullCard.classList.toggle("active", full);
  if (analyzeBtn) analyzeBtn.textContent = full ? "\u5f00\u59cb\u5b8c\u6574\u4eba\u683c\u5206\u6790" : "\u5f00\u59cb\u5feb\u901f\u5206\u6790";
}

function showView(name) {
  inputView.classList.toggle("hidden", name !== "input");
  loadingView.classList.toggle("hidden", name !== "loading");
  resultView.classList.toggle("hidden", name !== "result");
}

function setFullReportVisible(visible) {
  byId("fullReportSections")?.classList.toggle("hidden", !visible);
}

function setRealtimeWorkspaceMode(active) {
  byId("realtimeStage")?.classList.toggle("hidden", !active);
  if (active) setFullReportVisible(false);
}

function scrollRealtimeTranscriptToLatest() {
  const transcriptList = byId("realtimeLiveTranscript");
  if (!transcriptList) return;
  transcriptList.scrollTop = transcriptList.scrollHeight;
}

function renderLoading(stepIndex = 0) {
  const steps = getCurrentMode() === "full" ? LOADING_STEPS_FULL : LOADING_STEPS_QUICK;
  loadingStepsEl.innerHTML = steps
    .map((step, index) => {
      const state = index < stepIndex ? "done" : index === stepIndex ? "active" : "";
      return `<div class="loading-step ${state}"><span class="loading-step-dot"></span><span>${step}</span></div>`;
    })
    .join("");
  loadingMessageEl.textContent = getCurrentMode() === "full"
    ? "\u6b63\u5728\u6267\u884c\u5b8c\u6574\u4eba\u683c\u5206\u6790\uff0c\u8bf7\u7a0d\u5019..."
    : "\u6b63\u5728\u6267\u884c\u5feb\u901f DISC / MBTI \u5206\u6790\uff0c\u8bf7\u7a0d\u5019...";
}

function startLoadingSequence() {
  let stepIndex = 0;
  renderLoading(stepIndex);
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => {
    const steps = getCurrentMode() === "full" ? LOADING_STEPS_FULL : LOADING_STEPS_QUICK;
    stepIndex = (stepIndex + 1) % steps.length;
    renderLoading(stepIndex);
  }, 1200);
}

function stopLoadingSequence() {
  clearInterval(loadingTimer);
  loadingTimer = null;
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function hideError() {
  errorBoxEl.classList.add("hidden");
  errorTextEl.textContent = "";
}

function showError(message) {
  stopLoadingSequence();
  errorBoxEl.classList.remove("hidden");
  errorTextEl.textContent = message || TEXT.requestFailed;
}

function getPrimaryAnalysis(report) {
  if (report.llm_analysis && report.llm_analysis.scores) {
    return { source: "\u6a21\u578b\u5206\u6790", analysis: report.llm_analysis };
  }
  return { source: "\u672c\u5730\u89c4\u5219", analysis: report.disc_analysis || {} };
}

function renderDiscPie(analysis) {
  const scores = analysis.scores || {};
  const ordered = ["D", "I", "S", "C"].map((key) => ({ key, value: Number(scores[key] || 0) }));
  const total = ordered.reduce((sum, item) => sum + item.value, 0) || 1;
  let angle = 0;
  const stops = ordered.map(({ key, value }) => {
    const start = angle;
    angle += (value / total) * 360;
    return `${getComputedStyle(document.documentElement).getPropertyValue(`--${key.toLowerCase()}-color`).trim()} ${start.toFixed(1)}deg ${angle.toFixed(1)}deg`;
  });
  const top = rankDimensions(scores)[0];
  return `<div class="disc-pie" style="background: conic-gradient(${stops.join(", ")});"><div class="disc-pie-center"><div><strong>${top ? top[1] : 0}</strong><span>${top ? DISC_META[top[0]].label : TEXT.na}</span></div></div></div><div class="disc-pie-caption">D / I / S / C \u56db\u4e2a\u7ef4\u5ea6\u7684\u76f8\u5bf9\u5206\u5e03\u3002</div>`;
}

function renderDiscBars(analysis) {
  return rankDimensions(analysis.scores || {})
    .map(([key, value]) => {
      const pct = Math.max(8, Math.min(100, Number(value || 0)));
      return `<div class="metric-bar"><div class="metric-bar-head"><span>${DISC_META[key]?.label || key}</span><strong>${value}</strong></div><div class="bar-track"><div class="bar-fill ${DISC_META[key]?.className || ""}" style="width:${pct}%"></div></div></div>`;
    })
    .join("");
}
function renderHeroScore(analysis) {
  const risk = String(analysis.meta?.impression_management_risk || "low").toLowerCase();
  const score = risk.includes("high") ? 42 : risk.includes("medium") ? 68 : 86;
  const color = score < 50 ? "var(--risk)" : score < 75 ? "var(--amber)" : "var(--success)";
  return `<div class="score-ring" style="background: conic-gradient(${color} ${score * 3.6}deg, rgba(255,255,255,0.12) 0deg);"><div class="score-ring-inner"><strong>${score}</strong><span>\u7efc\u5408\u7f6e\u4fe1\u5ea6</span></div></div>`;
}

function renderDecisionLayer(report, analysis, source) {
  const topRank = rankDimensions(analysis.scores || {});
  const topStyle = topRank[0] ? DISC_META[topRank[0][0]]?.style : TEXT.weakSignals;
  setText("analysisSource", source);
  setText("analysisSourceTop", source);
  setText("candidateStyle", trimText(analysis.decision_summary || `\u5019\u9009\u4eba\u7684\u4e3b\u8981\u98ce\u683c\u504f\u5411${topStyle}\u3002`, 90));
  setText("candidateStyleNote", trimText(analysis.overall_style_summary || analysis.risk_summary || TEXT.weakSignals, 120));
  setText("riskHeadline", trimText(analysis.risk_summary || "\u5f53\u524d\u5c1a\u672a\u8bc6\u522b\u51fa\u660e\u786e\u9ad8\u98ce\u9669\u4fe1\u53f7\u3002", 80));
  setText("nextAction", trimText(analysis.recommended_action || "\u5efa\u8bae\u7ee7\u7eed\u901a\u8fc7\u8ffd\u95ee\u9a8c\u8bc1\u5173\u952e\u5224\u65ad\u3002", 80));
  setText("riskLevelTop", safeText(analysis.meta?.impression_management_risk, "\u672a\u77e5"));
  setHtml("heroScore", renderHeroScore(analysis));
  setHtml("riskBulletList", createList((analysis.critical_findings || []).slice(0, 3), (item) => `<div class="bullet-item"><span class="bullet-dot"></span><span>${trimText(item.finding, 80)}</span></div>`, "\u6682\u65e0\u98ce\u9669\u63d0\u793a"));
  setHtml("actionBulletList", createList((analysis.follow_up_questions || []).slice(0, 3), (item) => `<div class="bullet-item"><span class="bullet-dot"></span><span>${safeText(item.question)}</span></div>`, "\u6682\u65e0\u5efa\u8bae\u52a8\u4f5c"));
  setHtml("evidenceBulletList", createList((analysis.meta?.notes || []).slice(0, 3), (item) => `<div class="bullet-item"><span class="bullet-dot"></span><span>${trimText(item, 80)}</span></div>`, "\u6682\u65e0\u5224\u65ad\u4f9d\u636e"));
  setHtml("topFollowups", createList((analysis.follow_up_questions || []).slice(0, 3), (item, index) => `<div class="followup-item"><span class="followup-index">${index + 1}</span><div><strong>${safeText(item.question)}</strong><p>${safeText(item.purpose)}</p></div></div>`, TEXT.noFollowup));
  setHtml("strengthList", createList(topRank.slice(0, 2), ([key, value]) => `<div class="micro-item bare"><span class="micro-dot"></span><span>${DISC_META[key]?.label || key}: ${value}</span></div>`, "\u6682\u65e0\u660e\u663e\u4f18\u52bf"));
  setHtml("riskList", createList((analysis.evidence_gaps || []).slice(0, 3), (item) => `<div class="micro-item bare"><span class="micro-dot negative"></span><span>${trimText(item, 70)}</span></div>`, "\u6682\u65e0\u660e\u663e\u98ce\u9669\u7f3a\u53e3"));
  setHtml("riskTags", createList((analysis.evidence_gaps || []).slice(0, 4), (item) => `<div class="tag summary-tag">${trimText(item, 22)}</div>`, "\u6682\u65e0\u6807\u7b7e"));
  setText("riskStripHeadline", trimText(analysis.risk_summary || "\u6682\u65e0\u98ce\u9669\u6458\u8981", 80));
  setText("riskStripDetail", trimText((analysis.critical_findings || []).map((item) => item.finding).join("\uff1b") || "\u6682\u65e0\u8be6\u7ec6\u8bf4\u660e", 120));
}

function renderMetricsLayer(report, analysis) {
  setHtml("discPie", renderDiscPie(analysis));
  setHtml("discBars", renderDiscBars(analysis));
  const top = rankDimensions(analysis.scores || {})[0];
  setText("discTagline", top ? `\u4e3b\u5bfc\u98ce\u683c\uff1a${DISC_META[top[0]].style}` : TEXT.na);
  setText("discExplain", trimText(analysis.overall_style_summary || analysis.decision_summary || TEXT.weakSignals, 120));
  setHtml(
    "capabilityCards",
    [
      ["STAR \u7ed3\u6784\u5b8c\u6574\u5ea6", Math.round(Number(report.atomic_features?.star_structure_score || 0) * 100)],
      ["\u903b\u8f91\u8fde\u63a5\u5bc6\u5ea6", Math.round(Number(report.atomic_features?.logical_connector_ratio || 0) * 5000)],
      ["\u6545\u4e8b\u7ec6\u8282\u4e30\u5bcc\u5ea6", Math.round(Number(report.atomic_features?.story_richness_score || 0) * 100)],
      ["\u884c\u52a8\u8868\u8fbe\u5bc6\u5ea6", Math.round(Number(report.atomic_features?.action_verbs_ratio || 0) * 5000)],
    ]
      .map(([label, score]) => {
        const safeScore = Math.max(5, Math.min(100, Number(score || 0)));
        const level = safeScore >= 75 ? "high" : safeScore >= 50 ? "medium" : "low";
        return `<div class="ability-row"><div class="ability-row-head"><strong>${label}</strong><span class="capability-badge ${level}">${safeScore}</span></div><div class="ability-progress"><span style="width:${safeScore}%"></span></div></div>`;
      })
      .join("")
  );
  const risk = String(analysis.meta?.impression_management_risk || "low").toLowerCase();
  const riskLevel = risk.includes("high") ? "high" : risk.includes("medium") ? "medium" : "low";
  const riskScore = riskLevel === "high" ? 88 : riskLevel === "medium" ? 58 : 28;
  setHtml("riskMeter", `<div class="risk-strip-value"><span class="risk-badge ${riskLevel}">${safeText(analysis.meta?.impression_management_risk, "low")}</span><div class="risk-scale-bar compact"><div class="risk-scale-fill ${riskLevel}" style="width:${riskScore}%"></div></div></div>`);
}

function renderInterviewOverview(report) {
  setText("turnCountTop", report.input_overview?.turn_count || 0, "0");
  setText("jobGuessTop", report.interview_map?.job_inference?.value || "\u672a\u77e5");
  setText("sampleQualityTop", report.disc_analysis?.meta?.sample_quality || report.llm_analysis?.meta?.sample_quality || "\u672a\u77e5");
  setText("sampleQualityTopDetail", report.disc_analysis?.meta?.sample_quality || report.llm_analysis?.meta?.sample_quality || "\u672a\u77e5");
  setText("candidateCharTop", report.input_overview?.candidate_char_count || 0, "0");
  setText("parseSourceTop", report.interview_map?.parse_source || "\u672a\u77e5");
  setHtml("overview", [
    `\u5c97\u4f4d\u731c\u6d4b\uff1a${safeText(report.interview_map?.job_inference?.value, "\u672a\u77e5")}`,
    `\u95ee\u7b54\u8f6e\u6b21\uff1a${report.input_overview?.turn_count || 0}`,
    `\u5019\u9009\u4eba\u6587\u672c\u91cf\uff1a${report.input_overview?.candidate_char_count || 0}`,
    `\u89e3\u6790\u6765\u6e90\uff1a${safeText(report.interview_map?.parse_source, "\u672a\u77e5")}`,
  ].map((item) => `<div class="chip">${item}</div>`).join(""));
  setHtml("turns", createList(report.interview_map?.turns || [], (item) => `<div class="turn-item"><div class="type">\u7b2c ${item.turn_id || "-"} \u8f6e</div><p><strong>${trimText(item.question || "\u6682\u65e0\u95ee\u9898", 70)}</strong></p><p>${trimText(item.answer_summary || item.answer || "\u6682\u65e0\u56de\u7b54", 160)}</p></div>`, "\u6682\u65e0\u8f6e\u6b21\u6570\u636e"));
}

function renderWorkflow(report) {
  const workflow = report.workflow || {};
  const stageTrace = workflow.stage_trace || [];
  setText("workflowStageTop", stageTrace.length, "0");
  setHtml("workflowStages", createList(stageTrace, (item, index) => `<div class="workflow-stage"><div class="workflow-stage-top"><div class="workflow-stage-name"><span class="workflow-step-index">${index + 1}</span><strong>${safeText(item.stage)}</strong></div><span class="workflow-stage-status ${safeText(item.status, "low").toLowerCase()}">${safeText(item.status)}</span></div><div class="workflow-stage-meta"><span>${trimText(item.detail, 90)}</span></div></div>`, "\u6682\u65e0\u5de5\u4f5c\u6d41\u8bb0\u5f55"));
  setHtml("workflowEvidence", `<div class="workflow-tile"><strong>\u7ef4\u5ea6\u6392\u5e8f</strong><p>${safeText((workflow.disc_evidence?.ranking || []).join(" / "), "\u6682\u65e0\u6392\u5e8f")}</p></div>`);
  setHtml("workflowMasking", `<div class="workflow-tile"><strong>\u5173\u952e\u53d1\u73b0</strong><p>${trimText((workflow.masking_assessment?.critical_findings || []).map((item) => item.finding).join("\uff1b"), 140, "\u6682\u65e0\u5173\u952e\u53d1\u73b0")}</p></div>`);
  setHtml("workflowDecision", `<div class="workflow-tile"><strong>\u51b3\u7b56\u6458\u8981</strong><p>${trimText(workflow.decision_payload?.decision_summary, 140, "\u6682\u65e0\u51b3\u7b56\u6458\u8981")}</p></div>`);
}
function renderDetailedLayer(report, analysis, source) {
  setHtml("dimensions", createList(Object.entries(analysis.dimension_analysis || {}), ([key, item]) => `<div class="dimension-card"><div class="type">${key}</div><p><strong>${safeText(item.band, "")}</strong> \u00b7 \u5206\u6570 ${safeText(item.score, 0)}</p><p>${trimText(item.summary, 100)}</p></div>`, "\u6682\u65e0\u7ef4\u5ea6\u8be6\u60c5"));
  setHtml("criticalFindings", createList(analysis.critical_findings || [], (item) => `<div class="list-item"><div class="type">${safeText(item.severity, "unknown")}</div><p><strong>${trimText(item.finding, 100)}</strong></p><p>${trimText(item.impact, 120, "\u6682\u65e0\u5f71\u54cd\u8bf4\u660e")}</p></div>`, "\u6682\u65e0\u5173\u952e\u53d1\u73b0"));
  setHtml("evidenceGaps", createList(analysis.evidence_gaps || [], (item) => `<div class="list-item"><p>${trimText(item, 100)}</p></div>`, "\u6682\u65e0\u8bc1\u636e\u7f3a\u53e3"));
  setHtml("hypotheses", createList(analysis.behavioral_hypotheses || [], (item) => `<div class="list-item"><div class="type">${safeText(item.strength, "unknown")}</div><p>${trimText(item.hypothesis, 100)}</p></div>`, "\u6682\u65e0\u884c\u4e3a\u5047\u8bbe"));
  const features = report.atomic_features || {};
  const featureRows = Object.entries(features)
    .slice(0, 16)
    .map(([key, value]) => `<div class="feature-item"><strong>${key}</strong><div>${typeof value === "number" ? (value.toFixed ? value.toFixed(4) : value) : safeText(value)}</div></div>`)
    .join("");
  setHtml("features", featureRows || `<div class="feature-item"><strong>\u6682\u65e0\u7279\u5f81\u6570\u636e</strong></div>`);
  setHtml("followups", createList(analysis.follow_up_questions || [], (item) => `<div class="list-item"><div class="type">${safeText(item.target_dimension || item.dimension, "-")}</div><p>${safeText(item.question)}</p><p>${safeText(item.purpose)}</p></div>`, TEXT.noFollowup));
  setHtml("llmStatus", [
    `\u5206\u6790\u6765\u6e90\uff1a${source}`,
    `\u89e3\u6790\u6a21\u578b\uff1a${safeText(report.llm_status?.parser_model)}`,
    `\u5206\u6790\u6a21\u578b\uff1a${safeText(report.llm_status?.analysis_model)}`,
    `\u4eba\u683c\u6a21\u578b\uff1a${safeText(report.llm_status?.personality_model, "\u672a\u4f7f\u7528")}`,
    report.llm_status?.analysis_error ? `\u5206\u6790\u5f02\u5e38\uff1a${report.llm_status.analysis_error}` : "\u5206\u6790\u5f02\u5e38\uff1a\u65e0",
  ].join("<br />"));
  setText("llmOutput", JSON.stringify(report, null, 2));
}

function renderMBTIDimension(prefix, dimData, leftKey, rightKey) {
  setText(`mbti${prefix}`, dimData.preference || "-");
  const scores = dimData.scores || {};
  const leftScore = Math.round(Number(scores[leftKey] || 50));
  const rightScore = Math.round(Number(scores[rightKey] || 50));
  setHtml(`mbti${prefix}Bar`, `<div class="mbti-pref-labels"><span>${leftKey} ${leftScore}%</span><span>${rightKey} ${rightScore}%</span></div><div class="mbti-pref-bar"><div class="mbti-pref-fill left" style="width:${leftScore}%"></div><div class="mbti-pref-fill right" style="width:${rightScore}%"></div><div class="mbti-pref-center"></div></div>`);
  setText(`mbti${prefix}Summary`, `\u504f\u597d\uff1a${safeText(dimData.preference, "\u4e0d\u660e\u786e")} \u00b7 \u7f6e\u4fe1\u5ea6\uff1a${safeText(dimData.confidence, "\u4f4e")}`);
  setHtml(`mbti${prefix}Evidence`, `<div class="mbti-evidence-section"><strong>${leftKey}</strong><ul>${(dimData.evidence?.[leftKey] || []).map((item) => `<li>${trimText(item, 80)}</li>`).join("") || "<li>\u6682\u65e0\u660e\u663e\u8bc1\u636e</li>"}</ul></div><div class="mbti-evidence-section"><strong>${rightKey}</strong><ul>${(dimData.evidence?.[rightKey] || []).map((item) => `<li>${trimText(item, 80)}</li>`).join("") || "<li>\u6682\u65e0\u660e\u663e\u8bc1\u636e</li>"}</ul></div>`);
}

function renderMBTILayer(report) {
  const mbti = report.mbti_analysis || {};
  setText("mbtiConfidence", safeText(mbti.meta?.confidence, "\u672a\u77e5"));
  setText("mbtiTypeBadge", safeText(mbti.type, "XXXX"));
  setText("mbtiTypeDesc", trimText(mbti.type_description || "\u6682\u672a\u751f\u6210 MBTI \u7ed3\u679c", 120));
  setHtml("mbtiConflicts", createList(mbti.conflicts || [], (item) => `<div class="mbti-conflict-item ${safeText(item.severity, "low")}"><div class="mbti-conflict-head"><span class="mbti-conflict-badge ${safeText(item.severity, "low")}">${safeText(item.severity, "-")}</span><strong>${trimText(item.type || item.risk_type || "MBTI \u51b2\u7a81", 60)}</strong></div><p class="mbti-conflict-rec">${trimText(item.description || item.message || item.recommendation || "", 140)}</p></div>`, "\u6682\u65e0\u660e\u663e MBTI \u51b2\u7a81"));
  renderMBTIDimension("EI", mbti.dimensions?.E_I || {}, "E", "I");
  renderMBTIDimension("NS", mbti.dimensions?.N_S || {}, "N", "S");
  renderMBTIDimension("TF", mbti.dimensions?.T_F || {}, "T", "F");
  renderMBTIDimension("JP", mbti.dimensions?.J_P || {}, "J", "P");
  setHtml("mbtiFollowups", createList(mbti.follow_up_questions || [], (item) => `<div class="question-item"><strong>${safeText(item.question)}</strong><div>${safeText(item.purpose)}</div></div>`, TEXT.noFollowup));
}

function collectConflictItems(report) {
  const items = [];
  const pushItems = (source, values) => {
    (values || []).forEach((item) => {
      if (!item || typeof item !== "object") return;
      items.push({
        source,
        severity: item.severity || "medium",
        type: item.type || item.risk_type || source,
        description: item.description || item.message || item.reason || "",
        recommendation: item.recommendation || item.mitigation || "",
      });
    });
  };
  pushItems("MBTI", report.mbti_analysis?.conflicts);
  pushItems("\u4e5d\u578b\u4eba\u683c", report.enneagram_analysis?.risk_flags);
  return items;
}

function renderConflictSection(report, show) {
  const el = byId("conflictSection");
  if (!el) return;
  el.classList.toggle("hidden", !show);
  if (!show) return;
  const items = collectConflictItems(report);
  if (!items.length) {
    el.innerHTML = `<div class="personality-row-item"><strong>\u6682\u672a\u53d1\u73b0\u8de8\u6a21\u578b\u51b2\u7a81\u4fe1\u53f7\u3002</strong><p>\u5f53\u524d\u5b8c\u6574\u4eba\u683c\u6a21\u5f0f\u6ca1\u6709\u8bc6\u522b\u5230\u989d\u5916\u7684\u77db\u76fe\u9884\u8b66\u3002</p></div>`;
    return;
  }
  el.innerHTML = `<div class="panel-head panel-head-space personality-section-head"><div><p class="section-kicker">\u51b2\u7a81\u63d0\u793a</p><h3>\u8de8\u6a21\u578b\u98ce\u9669\u63d0\u9192</h3></div><span class="source-badge">${items.length} \u6761</span></div>` + items.map((item) => `<div class="conflict-item ${item.severity}"><div class="conflict-item-head"><strong>${item.source}\uff1a${trimText(item.type, 50)}</strong><span class="risk-badge ${item.severity}">${item.severity}</span></div><p>${trimText(item.description, 160, "\u6682\u65e0\u8bf4\u660e")}</p>${item.recommendation ? `<p>${trimText(item.recommendation, 140)}</p>` : ""}</div>`).join("");
}
function renderBigFive(report) {
  const data = report.bigfive_analysis || {};
  const container = byId("bigfiveCards");
  if (!container) return;
  const scores = data.scores || {};
  const rows = ["O", "C", "E", "A", "N"].map((key) => {
    const score = Number(scores[key] || 0);
    return `<div class="bf-row"><div class="bf-row-head"><strong>${key}</strong><span>${score}</span></div><div class="bf-bar-wrap"><span class="bf-bar-fill" style="width:${Math.max(4, score)}%"></span></div><p>${trimText(data.trait_interpretations?.[key], 100, "\u6682\u65e0\u89e3\u91ca")}</p></div>`;
  });
  container.innerHTML = rows.join("") || `<div class="panel-empty-note">\u6682\u65e0\u4e94\u5927\u4eba\u683c\u7ed3\u679c</div>`;
}

function renderEnneagram(report) {
  const data = report.enneagram_analysis || {};
  const container = byId("enneagramCards");
  if (!container) return;
  const topTwo = data.top_two_types || [];
  container.innerHTML = topTwo.length
    ? topTwo.map((item) => `<div class="personality-row-item"><strong>${safeText(item.type_number, "-")} \u578b \u00b7 ${safeText(item.label, "\u672a\u77e5")}</strong><p>\u5f97\u5206\uff1a${safeText(item.raw_score, "-")} \u00b7 \u7f6e\u4fe1\u5ea6\uff1a${safeText(item.confidence_level, "-")}</p><p>${trimText((item.key_evidence || []).join("\uff1b"), 140, "\u6682\u65e0\u8bc1\u636e")}</p></div>`).join("")
    : `<div class="panel-empty-note">\u6682\u65e0\u4e5d\u578b\u4eba\u683c\u7ed3\u679c</div>`;
}

function renderStar(report) {
  const data = report.star_analysis || {};
  const container = byId("starCards");
  if (!container) return;
  const dimensions = data.dimension_scores || {};
  const keys = ["S", "T", "A", "R"];
  container.innerHTML = keys.map((key) => {
    const item = dimensions[key] || {};
    const score = Number(item.score || 0);
    return `<div class="star-dim-card"><div class="star-dim-head"><strong>${key}</strong><span class="risk-badge ${safeText(item.band, "low")}">${safeText(item.band, "-")}</span></div><div class="star-bar-wrap"><span class="star-bar-fill" style="width:${Math.max(4, score)}%"></span></div><p>${trimText(item.interpretation, 100, "\u6682\u65e0\u89e3\u91ca")}</p></div>`;
  }).join("");
}

function renderMapping(report) {
  const data = report.personality_mapping || {};
  const profile = data.integrated_personality_profile || {};
  const container = byId("mappingCards");
  if (!container) return;
  if (!Object.keys(profile).length) {
    container.innerHTML = `<div class="panel-empty-note">\u6682\u65e0\u7efc\u5408\u753b\u50cf\u7ed3\u679c</div>`;
    return;
  }
  container.innerHTML = [
    `<div class="mapping-row"><strong>${safeText(profile.primary_style_label, "\u6682\u65e0\u4e3b\u6807\u7b7e")}</strong><p>${trimText(profile.primary_style_description, 160, "\u6682\u65e0\u8bf4\u660e")}</p></div>`,
    `<div class="mapping-row"><strong>DISC</strong><p>${safeText(profile.disc_integration?.dominant_style, "-")} / ${safeText(profile.disc_integration?.secondary_style, "-")}</p></div>`,
    `<div class="mapping-row"><strong>\u4e94\u5927\u4eba\u683c</strong><p>${safeText(profile.bigfive_integration?.dominant_trait, "-")} \u00b7 \u7f6e\u4fe1\u5ea6 ${safeText(profile.bigfive_integration?.confidence, "-")}</p></div>`,
    `<div class="mapping-row"><strong>\u4e5d\u578b\u4eba\u683c</strong><p>${safeText(profile.enneagram_integration?.dominant_type, "-")} \u00b7 \u4fa7\u7ffc ${safeText(profile.enneagram_integration?.wing, "-")}</p></div>`,
  ].join("");
}

function renderPersonalitySection(report, show) {
  const section = byId("personalitySection");
  if (!section) return;
  section.classList.toggle("hidden", !show);
  if (!show) return;
  renderBigFive(report);
  renderEnneagram(report);
  renderStar(report);
  renderMapping(report);
}

function renderReport(report, sourceHint = null) {
  setRealtimeWorkspaceMode(false);
  setFullReportVisible(true);
  const primary = getPrimaryAnalysis(report);
  const showFull = getCurrentMode() === "full" || Boolean(report.bigfive_analysis && Object.keys(report.bigfive_analysis).length);
  const source = sourceHint || primary.source;
  renderInterviewOverview(report);
  renderDecisionLayer(report, primary.analysis, source);
  renderMetricsLayer(report, primary.analysis);
  renderWorkflow(report);
  renderDetailedLayer(report, primary.analysis, source);
  renderMBTILayer(report);
  renderConflictSection(report, showFull);
  renderPersonalitySection(report, showFull);
  statusEl.textContent = source;
}

function setAudioLevel(name, value) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  const barId = name === "mic" ? "micLevelBar" : name === "system" ? "systemLevelBar" : "mixedLevelBar";
  const textId = name === "mic" ? "micLevelText" : name === "system" ? "systemLevelText" : "mixedLevelText";
  const bar = byId(barId);
  const text = byId(textId);
  if (bar) {
    bar.style.width = `${pct}%`;
    bar.closest(".audio-meter-card")?.classList.toggle("active", pct >= 8);
  }
  if (text) text.textContent = `${pct}%`;
}

function computeAnalyserLevel(analyser) {
  if (!analyser) return 0;
  const buffer = new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(buffer);
  let sumSquares = 0;
  for (let i = 0; i < buffer.length; i += 1) {
    sumSquares += buffer[i] * buffer[i];
  }
  return Math.min(1, Math.sqrt(sumSquares / buffer.length) * 2.5);
}

function startLevelMeter() {
  if (levelMeterTimer) cancelAnimationFrame(levelMeterTimer);
  const tick = () => {
    setAudioLevel("mic", computeAnalyserLevel(audioAnalyserNodes.mic));
    setAudioLevel("system", computeAnalyserLevel(audioAnalyserNodes.system));
    setAudioLevel("mixed", computeAnalyserLevel(audioAnalyserNodes.mixed));
    levelMeterTimer = requestAnimationFrame(tick);
  };
  tick();
}

function stopLevelMeter() {
  if (levelMeterTimer) {
    cancelAnimationFrame(levelMeterTimer);
    levelMeterTimer = null;
  }
  audioAnalyserNodes = {};
  setAudioLevel("mic", 0);
  setAudioLevel("system", 0);
  setAudioLevel("mixed", 0);
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

function downsampleBuffer(buffer, inputRate, outputRate = 24000) {
  if (inputRate === outputRate) return buffer;
  const ratio = inputRate / outputRate;
  const outputLength = Math.round(buffer.length / ratio);
  const output = new Float32Array(outputLength);
  let offsetResult = 0;
  let offsetBuffer = 0;
  while (offsetResult < output.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i += 1) {
      accum += buffer[i];
      count += 1;
    }
    output[offsetResult] = count ? accum / count : 0;
    offsetResult += 1;
    offsetBuffer = nextOffsetBuffer;
  }
  return output;
}

function floatTo16BitPCM(floatBuffer) {
  const pcm = new Int16Array(floatBuffer.length);
  for (let i = 0; i < floatBuffer.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, floatBuffer[i]));
    pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return new Uint8Array(pcm.buffer);
}

async function flushLiveAudioCapture() {
  if (micSocket && micSocket.readyState === WebSocket.OPEN) {
    if (micStream && liveSourceEnabled.mic) sendSocketMessage({ type: "commit", source: "mic" });
    if (systemStream && liveSourceEnabled.system) sendSocketMessage({ type: "commit", source: "system" });
    await new Promise((resolve) => window.setTimeout(resolve, 450));
  }

  const recorders = [...liveMediaRecorders];
  if (!recorders.length) return;

  recorders.forEach((item) => {
    try {
      if (item.recorder.state === "recording") {
        item.recorder.requestData();
      }
    } catch (error) {
      console.warn(error);
    }
  });

  await Promise.allSettled(Object.values(liveUploadInflight));
  await new Promise((resolve) => window.setTimeout(resolve, 400));
}

function stopLiveAudioCapture() {
  if (liveMediaRecorders.length) {
    liveMediaRecorders.forEach((item) => {
      try {
        if (item.recorder.state !== "inactive") {
          item.recorder.stop();
        }
      } catch (error) {
        console.warn(error);
      }
    });
    liveMediaRecorders = [];
  }
  if (micProcessorNode) {
    micProcessorNode.disconnect();
    micProcessorNode.onaudioprocess = null;
    micProcessorNode = null;
  }
  stopLevelMeter();
  if (audioSourceNodes.length) {
    audioSourceNodes.forEach((node) => {
      try {
        node.disconnect();
      } catch (error) {
        console.warn(error);
      }
    });
    audioSourceNodes = [];
  }
  if (micSilentGain) {
    micSilentGain.disconnect();
    micSilentGain = null;
  }
  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
    micStream = null;
  }
  if (systemStream) {
    systemStream.getTracks().forEach((track) => track.stop());
    systemStream = null;
  }
  if (micAudioContext) {
    micAudioContext.close();
    micAudioContext = null;
  }
  liveStreamingMode = false;
  if (micSocket) {
    try {
      if (micSocket.readyState === WebSocket.OPEN) {
        micSocket.send(JSON.stringify({ type: "close" }));
      }
      micSocket.close();
    } catch (error) {
      console.warn(error);
    }
    micSocket = null;
  }
  liveChunkCursorMs = { mic: 0, system: 0 };
  liveUploadInflight = { mic: Promise.resolve(), system: Promise.resolve() };
}

async function getRequestedAudioStreams() {
  const wantMic = Boolean(captureMicEl?.checked);
  const wantSystem = Boolean(captureSystemEl?.checked);

  if (!wantMic && !wantSystem) {
    throw new Error("Please select at least one audio source.");
  }

  let nextMicStream = null;
  let nextSystemStream = null;

  if (wantMic) {
    nextMicStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  }

  if (wantSystem) {
    try {
      const displayStream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: true,
      });
      const audioTracks = displayStream.getAudioTracks();
      const videoTracks = displayStream.getVideoTracks();
      videoTracks.forEach((track) => track.stop());
      if (!audioTracks.length) {
        throw new Error("No system audio track was shared. Re-run and enable audio sharing.");
      }
      nextSystemStream = new MediaStream(audioTracks);
    } catch (error) {
      if (nextMicStream) {
        nextMicStream.getTracks().forEach((track) => track.stop());
      }
      throw error;
    }
  }

  return { nextMicStream, nextSystemStream };
}

function connectStreamToProcessor(stream, name) {
  if (!stream || !micAudioContext) return;
  const sourceNode = micAudioContext.createMediaStreamSource(stream);
  const analyser = micAudioContext.createAnalyser();
  analyser.fftSize = 2048;
  sourceNode.connect(analyser);
  if (micProcessorNode) sourceNode.connect(micProcessorNode);

  const processor = micAudioContext.createScriptProcessor(2048, 1, 1);
  processor.onaudioprocess = (event) => {
    if (!liveStreamingMode || !realtimeRunning || !liveSourceEnabled[name]) return;
    if (!micSocket || micSocket.readyState !== WebSocket.OPEN) return;
    const input = event.inputBuffer.getChannelData(0);
    const downsampled = downsampleBuffer(input, micAudioContext.sampleRate, 16000);
    if (!downsampled.length) return;
    const pcmBytes = floatTo16BitPCM(downsampled);
    sendSocketMessage({
      type: "audio_chunk",
      source: name,
      audio: bytesToBase64(pcmBytes),
    });
  };
  sourceNode.connect(processor);
  if (micSilentGain) processor.connect(micSilentGain);

  audioAnalyserNodes[name] = analyser;
  audioSourceNodes.push(sourceNode, analyser, processor);
}

function speakerDisplayLabel(speakerId, roleMap = {}) {
  const role = roleMap[speakerId];
  if (role === "interviewer") return "\u9762\u8bd5\u5b98\uff08\u63a8\u65ad\uff09";
  if (role === "candidate") return "\u5019\u9009\u4eba\uff08\u63a8\u65ad\uff09";
  if (speakerId === "speaker_a") return "\u8bf4\u8bdd\u4ebaA";
  if (speakerId === "speaker_b") return "\u8bf4\u8bdd\u4ebaB";
  return speakerId || TEXT.na;
}

function looksLikeQuestion(text) {
  const raw = safeText(text, "").trim();
  if (!raw) return false;
  if (/[\uFF1F?]$/.test(raw)) return true;
  return /(\u8bf7\u95ee|\u80fd\u4e0d\u80fd|\u80fd\u5426|\u53ef\u4e0d\u53ef\u4ee5|\u65b9\u4fbf\u8bb2\u8bb2|\u8bb2\u8bb2|\u4ecb\u7ecd\u4e00\u4e0b|\u8bf4\u4e00\u4e0b|\u4e3a\u4ec0\u4e48|\u600e\u4e48|\u5982\u4f55|\u6709\u6ca1\u6709|\u662f\u5426|\u54ea\u4e00\u4e2a|\u4ec0\u4e48\u662f|\u4f60\u80fd)/.test(raw);
}

function looksLikeAnswer(text) {
  const raw = safeText(text, "").trim();
  if (!raw) return false;
  const answerTokens = /(\u6211|\u6211\u4eec|\u5f53\u65f6|\u540e\u6765|\u6700\u540e|\u8d1f\u8d23|\u505a\u4e86|\u9879\u76ee|\u5ba2\u6237|\u63a8\u8fdb|\u5904\u7406|\u89e3\u51b3|\u590d\u76d8|\u7ed3\u679c|\u63d0\u5347|\u843d\u5730|\u6c9f\u901a|\u56e2\u961f)/;
  return raw.length >= 18 || answerTokens.test(raw);
}

function inferSingleSourceSegmentRoles(segments) {
  const inferred = {};
  let lastRole = "interviewer";
  for (const item of segments || []) {
    const text = safeText(item.text, "").trim();
    if (!text) continue;
    let role = null;
    if (looksLikeQuestion(text)) {
      role = "interviewer";
    } else if (looksLikeAnswer(text)) {
      role = "candidate";
    } else {
      role = lastRole === "interviewer" ? "candidate" : "interviewer";
    }
    inferred[item.id] = role;
    lastRole = role;
  }
  return inferred;
}

function buildRealtimeTranscriptRows(session, roleMap = {}) {
  const stableSegments = session.segments || [];
  const singleSpeakerMode = !Object.keys(roleMap || {}).length && new Set(stableSegments.map((item) => item.speaker_id)).size <= 1;
  const inferredRoles = singleSpeakerMode ? inferSingleSourceSegmentRoles(stableSegments) : {};
  return stableSegments.map((item) => {
    const label = singleSpeakerMode
      ? (inferredRoles[item.id] === "interviewer" ? "\u9762\u8bd5\u5b98\uff08\u6587\u672c\u63a8\u65ad\uff09" : "\u5019\u9009\u4eba\uff08\u6587\u672c\u63a8\u65ad\uff09")
      : speakerDisplayLabel(item.speaker_id, roleMap);
    return `<div class="live-transcript-item"><strong>${label}</strong><p>${safeText(item.text)}</p></div>`;
  });
}

function handleLiveSocketMessage(message) {
  if (!message || typeof message !== "object") return;
  const hint = byId("audioDebugHint");
  const sourceLabel = message.source === "mic" ? "麦克风" : message.source === "system" ? "系统音频" : "实时链路";

  if (message.type === "session.ready") {
    setText("audioSourceState", "已连接阿里实时 ASR");
    if (hint) hint.textContent = "实时音频链路已连通。";
    return;
  }

  if (message.type === "source.ready") {
    if (hint) hint.textContent = `${sourceLabel} 输入正常。`;
    return;
  }

  if (message.type === "transcript.delta") {
    const speakerId = message.speaker_id || (message.source === "mic" ? "speaker_a" : "speaker_b");
    realtimePartialBySpeaker[speakerId] = `${realtimePartialBySpeaker[speakerId] || ""}${message.delta || ""}`.trim();
    setText("audioSourceState", `${sourceLabel} \u6b63\u5728\u8bc6\u522b`);
    if (hint) hint.textContent = `${sourceLabel} \u6b63\u5728\u8bc6\u522b\u3002`;
    return;
  }

  if (message.type === "session.update" && message.session) {
    latestRealtimeSession = message.session;
    const segments = message.session.segments || [];
    if (segments.length > lastRenderedSegmentCount) {
      const lastSegment = segments[segments.length - 1] || {};
      if (lastSegment.speaker_id) {
        delete realtimePartialBySpeaker[lastSegment.speaker_id];
      }
      lastRenderedSegmentCount = segments.length;
    }
    renderRealtimeResponse(message.session);
    setText("audioSourceState", "阿里实时 ASR 转写中");
    return;
  }

  if (message.type === "speech.started") {
    setText("audioSourceState", `${sourceLabel} 检测到语音`);
    return;
  }

  if (message.type === "speech.stopped") {
    setText("audioSourceState", `${sourceLabel} 等待后续语音`);
    return;
  }

  if (message.type === "error") {
    const detail = [safeText(message.message, "实时链路错误"), safeText(message.hint, "")].filter(Boolean).join(" ");
    showError(detail);
    if (hint) hint.textContent = detail;
    setText("audioSourceState", "连接异常");
  }
}

function openLiveSocket(wsUrl) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const socket = new WebSocket(wsUrl);
    socket.onopen = () => {
      settled = true;
      micSocket = socket;
      resolve(socket);
    };
    socket.onmessage = (event) => {
      try {
        handleLiveSocketMessage(JSON.parse(event.data));
      } catch (error) {
        console.warn(error);
      }
    };
    socket.onerror = () => {
      if (!settled) {
        settled = true;
        reject(new Error("Local realtime websocket connection failed."));
      }
    };
    socket.onclose = () => {
      if (micSocket === socket) micSocket = null;
      if (!liveStreamingMode) return;
      setText("audioSourceState", "\u8fde\u63a5\u5df2\u65ad\u5f00");
      const hint = byId("audioDebugHint");
      if (hint) hint.textContent = "\u672c\u5730\u5b9e\u65f6\u94fe\u8def\u5df2\u65ad\u5f00\uff0c\u8bf7\u68c0\u67e5 DASHSCOPE_API_KEY \u548c\u963f\u91cc realtime \u914d\u7f6e\u3002";
    };
  });
}

function sendSocketMessage(payload) {
  if (!micSocket || micSocket.readyState !== WebSocket.OPEN) return;
  micSocket.send(JSON.stringify(payload));
}

function pickRecorderMimeType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  for (const mimeType of candidates) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(mimeType)) {
      return mimeType;
    }
  }
  return "";
}

async function uploadLiveAudioChunk(blob, sourceName) {
  if (!realtimeSessionId || !blob || !blob.size) return;
  if (!liveSourceEnabled[sourceName]) return;

  const minBytes = LIVE_MIN_CHUNK_BYTES[sourceName] || 0;
  if (blob.size < minBytes) {
    const hint = byId("audioDebugHint");
    if (hint) {
      hint.textContent = `${sourceName === "mic" ? "\u9ea6\u514b\u98ce" : "\u7cfb\u7edf\u97f3\u9891"} \u5206\u7247\u8fc7\u5c0f\uff0c\u5df2\u8df3\u8fc7\u4e0a\u4f20\u3002`;
    }
    return;
  }

  const speakerId = sourceName === "mic" ? "speaker_a" : "speaker_b";
  const startMs = liveChunkCursorMs[sourceName] || 0;
  const endMs = startMs + liveChunkDurationMs;
  liveChunkCursorMs[sourceName] = endMs;

  const formData = new FormData();
  const filename = `${sourceName}_${Date.now()}.${(blob.type || "audio/webm").includes("mp4") ? "m4a" : "webm"}`;
  formData.append("audio", blob, filename);
  formData.append("language", (audioLanguageEl?.value || "zh").trim() || "zh");
  formData.append("speaker_id", speakerId);
  formData.append("start_ms", String(startMs));
  formData.append("end_ms", String(endMs));

  const response = await fetch(`/api/realtime/session/${realtimeSessionId}/transcribe_chunk`, {
    method: "POST",
    body: formData,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || TEXT.requestFailed);
  }

  if (data.session) {
    renderRealtimeResponse(data.session);
  }
  const hint = byId("audioDebugHint");
  if (hint) {
    hint.textContent = data.transcribed
      ? `\u5df2\u8f6c\u5199 ${sourceName === "mic" ? "\u9ea6\u514b\u98ce" : "\u7cfb\u7edf\u97f3\u9891"} \u5206\u7247: ${safeText(data.text, "")}`
      : `${sourceName === "mic" ? "\u9ea6\u514b\u98ce" : "\u7cfb\u7edf\u97f3\u9891"} \u5206\u7247\u4e0a\u4f20\u6210\u529f\uff0c\u4f46\u672a\u8bc6\u522b\u5230\u6587\u672c\u3002`;
  }
  setText("audioSourceState", data.transcribed ? "HTTP \u5206\u7247\u8f6c\u5199\u4e2d" : "\u7b49\u5f85\u53ef\u8bc6\u522b\u8bed\u97f3");
}

function startSourceRecorder(stream, sourceName) {
  if (!stream) return;
  const mimeType = pickRecorderMimeType();
  const options = mimeType ? { mimeType } : undefined;
  const recorder = options ? new MediaRecorder(stream, options) : new MediaRecorder(stream);

  recorder.ondataavailable = (event) => {
    if (!event.data || !event.data.size) return;
    const task = liveUploadInflight[sourceName].then(() => uploadLiveAudioChunk(event.data, sourceName));
    liveUploadInflight[sourceName] = task.catch((error) => {
      showError(error.message || TEXT.requestFailed);
      const hint = byId("audioDebugHint");
      if (hint) hint.textContent = error.message || TEXT.requestFailed;
      setText("audioSourceState", "HTTP \u5206\u7247\u4e0a\u4f20\u5931\u8d25");
    });
  };
  recorder.onerror = (event) => {
    const message = event?.error?.message || "MediaRecorder failed";
    showError(message);
    setText("audioSourceState", "\u5f55\u97f3\u5206\u7247\u5931\u8d25");
  };
  recorder.start(liveChunkDurationMs);
  liveMediaRecorders.push({ name: sourceName, recorder });
}

async function startLiveAudioWs() {
  resetRealtimeState();
  hideError();

  const response = await fetch("/api/realtime/session/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_hint_optional: jobHintEl.value.trim() }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || TEXT.requestFailed);

  realtimeSessionId = data.session_id;
  realtimeDemoMode = true;
  liveStreamingMode = true;
  realtimeRunning = true;
  showView("result");
  setRealtimeWorkspaceMode(true);
  setRealtimeControls(true, true);
  statusEl.textContent = "\u6b63\u5728\u8fde\u63a5\u963f\u91cc\u5b9e\u65f6 ASR";
  renderRealtimeSessionPanel({ status: data.status, segment_count: 0, segments: [], role_inference: {} });

  const streams = await getRequestedAudioStreams();
  micStream = streams.nextMicStream;
  systemStream = streams.nextSystemStream;

  const AudioCtor = window.AudioContext || window.webkitAudioContext;
  micAudioContext = new AudioCtor();
  if (micAudioContext.state === "suspended") {
    await micAudioContext.resume();
  }

  const mixedAnalyser = micAudioContext.createAnalyser();
  mixedAnalyser.fftSize = 2048;
  audioAnalyserNodes.mixed = mixedAnalyser;
  micProcessorNode = micAudioContext.createGain();
  micProcessorNode.connect(mixedAnalyser);
  micSilentGain = micAudioContext.createGain();
  micSilentGain.gain.value = 0;
  mixedAnalyser.connect(micSilentGain);
  micSilentGain.connect(micAudioContext.destination);

  const wsUrl = `${data.ws_url}&language=${encodeURIComponent((audioLanguageEl?.value || "zh").trim() || "zh")}`;
  await openLiveSocket(wsUrl);
  connectStreamToProcessor(micStream, "mic");
  connectStreamToProcessor(systemStream, "system");
  startLevelMeter();

  liveSourceEnabled = { mic: Boolean(micStream), system: Boolean(systemStream) };
  refreshRouteButtons();

  const sourceLabel = [micStream ? "\u9ea6\u514b\u98ce" : null, systemStream ? "\u7cfb\u7edf\u97f3\u9891" : null].filter(Boolean).join(" + ");
  setText("audioSourceState", sourceLabel || "\u672a\u9009\u62e9\u97f3\u6e90");
  statusEl.textContent = `\u963f\u91cc\u5b9e\u65f6 ASR \u91c7\u96c6\u4e2d: ${sourceLabel}`;
  const hint = byId("audioDebugHint");
  if (hint) hint.textContent = "\u5b9e\u65f6\u6a21\u5f0f\u5df2\u542f\u52a8\uff0c\u4ec5\u663e\u793a\u76d1\u63a7\u3001\u8f6c\u5f55\u548c\u63a8\u8350\u63d0\u95ee\u3002";
}

function stopRealtimePlayback() {
  if (realtimeTimer) {
    clearInterval(realtimeTimer);
    realtimeTimer = null;
  }
  realtimeRunning = false;
}

function setRealtimeControls(active, running = false) {
  byId("realtimeStage")?.classList.toggle("hidden", !active);
  realtimePauseBtn?.classList.toggle("hidden", !active);
  realtimeEndBtn?.classList.toggle("hidden", !active);
  if (active) {
    viewFullReportBtn?.classList.add("hidden");
  }
  if (realtimePauseBtn) {
    realtimePauseBtn.textContent = running ? "\u6682\u505c\u63a8\u9001" : "\u7ee7\u7eed\u63a8\u9001";
  }
}

function resetRealtimeState() {
  stopRealtimePlayback();
  stopLiveAudioCapture();
  realtimeSessionId = null;
  realtimeSegments = [];
  realtimeSegmentIndex = 0;
  realtimeDemoMode = false;
  liveStreamingMode = false;
  realtimePartialBySpeaker = {};
  lastRenderedSegmentCount = 0;
  pendingFinalRealtimeReport = null;
  latestRealtimeSession = null;
  setRealtimeWorkspaceMode(false);
  setRealtimeControls(false, false);
  setText("realtimeSessionStatus", "\u672a\u5f00\u59cb");
  setText("realtimeRoleConfidence", "\u5f85\u5224\u65ad");
  setText("realtimeSegmentCount", 0, "0");
  setText("audioSourceState", "\u5f85\u8fde\u63a5");
  liveSourceEnabled = { mic: true, system: true };
  refreshRouteButtons();
  setHtml("realtimeRoleMap", `<div class="bullet-item"><span class="bullet-dot"></span><span>\u6682\u65e0\u89d2\u8272\u63a8\u65ad</span></div>`);
  setText("realtimeSuggestionSummary", "\u6682\u65e0\u6eda\u52a8\u5efa\u8bae");
  setHtml("realtimeSuggestionList", `<div class="panel-empty-note">\u6682\u65e0\u63a8\u8350\u63d0\u95ee</div>`);
  setHtml("realtimeLiveTranscript", `<div class="panel-empty-note">\u7b49\u5f85\u5b9e\u65f6\u7247\u6bb5</div>`);
}

function parseRealtimeSegments(rawText) {
  const lines = rawText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const labelMap = new Map();
  let nextSpeakerIndex = 0;
  let cursor = 0;

  return lines.map((line) => {
    const match = line.match(/^([^:\uff1a]{1,20})[:\uff1a]\s*(.+)$/);
    const label = match ? match[1].trim() : `speaker_${nextSpeakerIndex}`;
    const text = (match ? match[2] : line).trim();
    if (!labelMap.has(label)) {
      labelMap.set(label, nextSpeakerIndex === 0 ? "speaker_a" : "speaker_b");
      nextSpeakerIndex += 1;
    }
    const speakerId = labelMap.get(label) || "speaker_b";
    const duration = Math.max(1200, Math.min(4800, text.length * 120));
    const segment = {
      speaker_id: speakerId,
      text,
      start_ms: cursor,
      end_ms: cursor + duration,
      final: true,
    };
    cursor += duration;
    return segment;
  }).filter((item) => item.text);
}

function renderRealtimeSessionPanel(session) {
  latestRealtimeSession = session;
  setText("realtimeSessionStatus", session.status || "\u672a\u77e5");
  setText("realtimeSegmentCount", session.segment_count || 0, "0");

  const roleState = session.role_inference || {};
  const roleMapping = roleState.mapping || {};
  const roleStateName = roleState.state || "insufficient";
  const stableSegments = session.segments || [];
  const singleSpeakerMode = !Object.keys(roleMapping).length && new Set(stableSegments.map((item) => item.speaker_id)).size <= 1 && stableSegments.length > 0;
  if (roleState.ready) {
    setText("realtimeRoleConfidence", `${Math.round(Number(roleState.confidence || 0) * 100)}%`);
  } else if (singleSpeakerMode) {
    setText("realtimeRoleConfidence", "\u6587\u672c\u63a8\u65ad\uff08\u5355\u8def\u97f3\u9891\uff09");
  } else if (roleStateName === "single_speaker") {
    setText("realtimeRoleConfidence", "\u672a\u542f\u7528\uff08\u5355\u8def\u97f3\u9891\uff09");
  } else if (roleStateName === "warming_up") {
    setText("realtimeRoleConfidence", "\u79ef\u7d2f\u4e2d");
  } else {
    setText("realtimeRoleConfidence", "\u8bc1\u636e\u4e0d\u8db3");
  }

  const roleLines = [];
  if (singleSpeakerMode) {
    roleLines.push(`<div class="bullet-item"><span class="bullet-dot"></span><span>当前为单路音频，按句子内容临时推断面试官 / 候选人。</span></div>`);
  }
  if (Object.keys(roleMapping).length) {
    Object.keys(roleMapping).forEach((speakerId) => {
      roleLines.push(`<div class="bullet-item"><span class="bullet-dot"></span><span>${speakerDisplayLabel(speakerId, roleMapping)}</span></div>`);
    });
  }
  (roleState.reasons || []).forEach((item) => {
    roleLines.push(`<div class="bullet-item"><span class="bullet-dot"></span><span>${trimText(item, 90)}</span></div>`);
  });
  setHtml("realtimeRoleMap", roleLines.join("") || `<div class="bullet-item"><span class="bullet-dot"></span><span>\u6682\u65e0\u89d2\u8272\u63a8\u65ad</span></div>`);

  const transcriptRows = buildRealtimeTranscriptRows(session, roleMapping);
  setHtml("realtimeLiveTranscript", transcriptRows.join("") || `<div class="panel-empty-note">\u7b49\u5f85\u5b9e\u65f6\u7247\u6bb5</div>`);
  scrollRealtimeTranscriptToLatest();

  const rolling = session.rolling_analysis || {};
  const followupItems = rolling.follow_up_questions || [];
  const leadItem = followupItems[0] || null;
  const backlogItems = followupItems.slice(1);
  const rollingSummaryParts = [
    trimText(rolling.recommended_action, 88, ""),
    trimText(rolling.summary, 108, ""),
    rolling.mbti_type ? `MBTI 倾向：${safeText(rolling.mbti_type)}` : "",
    trimText(rolling.risk_summary, 88, ""),
  ].filter(Boolean);
  setText("realtimePromptCount", followupItems.length, "0");
  setText("realtimePromptSource", leadItem ? safeText(leadItem.source_label || leadItem.source || "建议") : "待生成");
  setText(
    "realtimePromptState",
    leadItem
      ? trimText(leadItem.purpose || rolling.recommended_action || "已生成主问句", 36)
      : "等待候选人内容"
  );
  setHtml(
    "realtimeSuggestionSummary",
    rollingSummaryParts.length
      ? rollingSummaryParts.map((item, index) => `<div class="realtime-summary-row ${index === 0 ? "primary" : ""}">${safeText(item)}</div>`).join("")
      : `<div class="realtime-summary-row">滚动建议将随着实时转录逐步出现。</div>`
  );
  setHtml(
    "realtimeSuggestionLead",
    leadItem
      ? (() => {
          const sourceLabel = safeText(leadItem.source_label || leadItem.source || "建议");
          const priority = String(leadItem.priority || "medium").toLowerCase();
          const dimension = leadItem.dimension ? `<span class="realtime-followup-dimension">${safeText(leadItem.dimension)}</span>` : "";
          return `<div class="realtime-followup-lead ${priority}"><div class="realtime-followup-meta lead"><span class="realtime-followup-source">${sourceLabel}</span>${dimension}<span class="realtime-followup-priority ${priority}">${priority}</span></div><div class="realtime-followup-lead-question">${safeText(leadItem.question || leadItem)}</div><p>${safeText(leadItem.purpose || "基于当前回答的下一步追问建议")}</p></div>`;
        })()
      : `<div class="realtime-followup-empty">实时提问建议会随着更多候选人内容出现。</div>`
  );
  setHtml(
    "realtimeSuggestionList",
    createList(
      backlogItems,
      (item, index) => {
        const sourceLabel = safeText(item.source_label || item.source || "建议");
        const priority = String(item.priority || "medium").toLowerCase();
        const dimension = item.dimension ? `<span class="realtime-followup-dimension">${safeText(item.dimension)}</span>` : "";
        return `<div class="realtime-followup-card ${priority}"><div class="realtime-followup-meta"><span class="followup-index">${index + 2}</span><span class="realtime-followup-source">${sourceLabel}</span>${dimension}<span class="realtime-followup-priority ${priority}">${priority}</span></div><strong>${safeText(item.question || item)}</strong><p>${safeText(item.purpose || "基于当前回答的下一步追问建议")}</p></div>`;
      },
      "暂无候补提问"
    )
  );
}

function renderRealtimeResponse(session, finalSource = null) {
  realtimeDemoMode = true;
  setRealtimeWorkspaceMode(true);
  setRealtimeControls(true, realtimeRunning);
  renderRealtimeSessionPanel(session);

  if (session.final_report) {
    pendingFinalRealtimeReport = { report: session.final_report, source: finalSource || "\u5b9e\u65f6\u4f1a\u8bdd\u603b\u7ed3" };
    statusEl.textContent = "\u5b9e\u65f6\u4f1a\u8bdd\u5df2\u7ed3\u675f";
    setRealtimeControls(false, false);
    viewFullReportBtn?.classList.remove("hidden");
  } else {
    statusEl.textContent = "\u5b9e\u65f6\u4f1a\u8bdd\u4e2d";
  }
}

async function appendRealtimeSegment() {
  if (!realtimeSessionId || realtimeSegmentIndex >= realtimeSegments.length) {
    stopRealtimePlayback();
    setRealtimeControls(true, false);
    return;
  }

  const segment = realtimeSegments[realtimeSegmentIndex];
  const response = await fetch(`/api/realtime/session/${realtimeSessionId}/append`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(segment),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || TEXT.requestFailed);

  realtimeSegmentIndex += 1;
  renderRealtimeResponse(data);

  if (realtimeSegmentIndex >= realtimeSegments.length) {
    stopRealtimePlayback();
    setRealtimeControls(true, false);
  }
}

function startRealtimePlayback() {
  if (!realtimeSessionId || realtimeRunning) return;
  realtimeRunning = true;
  setRealtimeControls(true, true);
  realtimeTimer = setInterval(async () => {
    try {
      await appendRealtimeSegment();
    } catch (error) {
      stopRealtimePlayback();
      setRealtimeControls(true, false);
      showError(error.message || TEXT.requestFailed);
    }
  }, 1100);
}

async function toggleRealtimePlayback() {
  if (!realtimeSessionId) return;
  if (liveStreamingMode) {
    realtimeRunning = !realtimeRunning;
    setRealtimeControls(true, realtimeRunning);
    statusEl.textContent = realtimeRunning ? "\u963f\u91cc\u5b9e\u65f6 ASR \u91c7\u96c6\u4e2d" : "\u963f\u91cc\u5b9e\u65f6 ASR \u5df2\u6682\u505c";
    if (!realtimeRunning) {
      await flushLiveAudioCapture();
    }
    return;
  }
  if (realtimeRunning) {
    stopRealtimePlayback();
    setRealtimeControls(true, false);
    return;
  }
  if (realtimeSegmentIndex >= realtimeSegments.length) return;
  startRealtimePlayback();
}

async function endRealtimeSession() {
  if (!realtimeSessionId) return;
  stopRealtimePlayback();
  await flushLiveAudioCapture();
  const response = await fetch(`/api/realtime/session/${realtimeSessionId}/end`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || TEXT.requestFailed);
  renderRealtimeResponse(data, "\u5b9e\u65f6\u4f1a\u8bdd\u603b\u7ed3");
  realtimeSessionId = null;
  liveStreamingMode = false;
  stopLiveAudioCapture();
}

async function transcribeAudioToSegments() {
  const file = audioFileEl?.files?.[0];
  if (!file) {
    window.alert("\u8bf7\u5148\u9009\u62e9\u97f3\u9891\u6587\u4ef6\u3002");
    return null;
  }

  const formData = new FormData();
  formData.append("audio", file);
  formData.append("language", (audioLanguageEl?.value || "zh").trim() || "zh");

  const response = await fetch("/api/audio/transcribe", {
    method: "POST",
    body: formData,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || TEXT.requestFailed);
  return data;
}

async function runRealtimeAudioDemo() {
  resetRealtimeState();
  hideError();

  const transcription = await transcribeAudioToSegments();
  if (!transcription || !(transcription.segments || []).length) {
    throw new Error("\u97f3\u9891\u8f6c\u5199\u6ca1\u6709\u8fd4\u56de\u53ef\u7528\u7247\u6bb5");
  }

  transcriptEl.value = transcription.transcript_preview || transcriptEl.value;
  const response = await fetch("/api/realtime/session/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_hint_optional: jobHintEl.value.trim() }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || TEXT.requestFailed);

  realtimeSessionId = data.session_id;
  realtimeSegments = transcription.segments;
  realtimeSegmentIndex = 0;
  realtimeDemoMode = true;
  showView("result");
  statusEl.textContent = "\u771f\u5b9e\u97f3\u9891\u8f6c\u5199\u4e2d";
  setRealtimeControls(true, true);
  renderRealtimeSessionPanel({ status: data.status, segment_count: 0, segments: [], role_inference: {} });

  await appendRealtimeSegment();
  startRealtimePlayback();
}

async function runRealtimeDemo() {
  const transcript = transcriptEl.value.trim();
  if (!transcript) {
    window.alert("\u8bf7\u5148\u586b\u5165\u5e26\u89d2\u8272\u524d\u7f00\u7684\u5bf9\u8bdd\u6587\u672c\u3002\n\u4f8b\u5982\uff1a\u9762\u8bd5\u5b98\uff1a...\n\u5019\u9009\u4eba\uff1a...");
    return;
  }

  const segments = parseRealtimeSegments(transcript);
  if (segments.length < 2) {
    window.alert("\u5b9e\u65f6\u6f14\u793a\u81f3\u5c11\u9700\u8981\u4e24\u6bb5\u5bf9\u8bdd\u6587\u672c\u3002\n\u5efa\u8bae\u4f7f\u7528\u5e26\u89d2\u8272\u524d\u7f00\u7684\u591a\u884c\u5bf9\u8bdd\u3002");
    return;
  }

  resetRealtimeState();
  hideError();
  const response = await fetch("/api/realtime/session/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_hint_optional: jobHintEl.value.trim() }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || TEXT.requestFailed);

  realtimeSessionId = data.session_id;
  realtimeSegments = segments;
  realtimeSegmentIndex = 0;
  realtimeDemoMode = true;
  showView("result");
  statusEl.textContent = "\u5b9e\u65f6\u4f1a\u8bdd\u4e2d";
  setRealtimeControls(true, true);
  renderRealtimeSessionPanel({ status: data.status, segment_count: 0, segments: [], role_inference: {} });

  await appendRealtimeSegment();
  startRealtimePlayback();
}

async function loadSampleLibrary() {
  try {
    const response = await fetch("/samples/index.json");
    if (!response.ok) throw new Error(TEXT.requestFailed);
    sampleLibrary = await response.json();
    sampleSelectEl.innerHTML = [`<option value="">${TEXT.selectSample}</option>`].concat(sampleLibrary.map((item) => `<option value="${item.id}">${item.title}</option>`)).join("");
  } catch (error) {
    sampleSelectEl.innerHTML = `<option value="">\u6837\u4f8b\u52a0\u8f7d\u5931\u8d25</option>`;
  }
}

async function fillSelectedSample() {
  const selectedId = sampleSelectEl.value;
  if (!selectedId) {
    transcriptEl.value = DEFAULT_TRANSCRIPT;
    jobHintEl.value = "\u540e\u7aef\u5de5\u7a0b\u5e08";
    return;
  }
  const item = sampleLibrary.find((entry) => entry.id === selectedId);
  if (!item) return;
  sampleBtn.disabled = true;
  sampleBtn.textContent = TEXT.loading;
  try {
    const response = await fetch(`/samples/${item.filename}`);
    if (!response.ok) throw new Error(TEXT.requestFailed);
    transcriptEl.value = await response.text();
    jobHintEl.value = item.job_hint || "";
  } catch (error) {
    transcriptEl.value = DEFAULT_TRANSCRIPT;
  } finally {
    sampleBtn.disabled = false;
    sampleBtn.textContent = TEXT.fill;
  }
}

async function startQuickPolling(taskId) {
  stopPolling();
  let localShown = false;
  pollTimer = setInterval(async () => {
    try {
      const response = await fetch(`/api/llm_status/${taskId}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || TEXT.requestFailed);
      if (!localShown && data.local_result) {
        localShown = true;
        stopLoadingSequence();
        renderReport(data.local_result, "\u672c\u5730\u89c4\u5219");
        showView("result");
      }
      if (data.status === "completed") {
        stopPolling();
        stopLoadingSequence();
        renderReport(data.llm_result || data.local_result, data.llm_result ? "\u6a21\u578b\u5206\u6790" : "\u672c\u5730\u89c4\u5219");
        showView("result");
      }
      if (data.status === "failed") {
        stopPolling();
        showError(data.error || TEXT.requestFailed);
      }
    } catch (error) {
      stopPolling();
      showError(error.message || TEXT.requestFailed);
    }
  }, 700);
}

async function runQuickMode(payload) {
  const response = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || TEXT.requestFailed);
  currentTaskId = data.task_id;
  await startQuickPolling(currentTaskId);
}

async function runFullMode(payload) {
  const response = await fetch("/api/analyze/full", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || TEXT.requestFailed);
  stopLoadingSequence();
  renderReport(data, "\u5b8c\u6574\u4eba\u683c\u6a21\u5f0f");
  showView("result");
}
async function runAnalysis() {
  const transcript = transcriptEl.value.trim();
  if (!transcript) {
    window.alert("\u8bf7\u5148\u7c98\u8d34\u9762\u8bd5\u6587\u672c\u3002");
    return;
  }
  const payload = {
    interview_transcript: transcript,
    job_hint_optional: jobHintEl.value.trim(),
    force_llm: false,
  };
  lastPayload = payload;
  hideError();
  showView("loading");
  startLoadingSequence();
  analyzeBtn.disabled = true;

  try {
    if (getCurrentMode() === "full") {
      await runFullMode(payload);
    } else {
      await runQuickMode(payload);
    }
  } catch (error) {
    showError(error.message || TEXT.requestFailed);
  } finally {
    analyzeBtn.disabled = false;
    applyModeCards();
  }
}

sampleBtn.addEventListener("click", fillSelectedSample);
analyzeBtn.addEventListener("click", runAnalysis);
realtimeBtn?.addEventListener("click", async () => {
  try {
    await runRealtimeDemo();
  } catch (error) {
    showError(error.message || TEXT.requestFailed);
  }
});
audioRealtimeBtn?.addEventListener("click", async () => {
  try {
    await runRealtimeAudioDemo();
  } catch (error) {
    showError(error.message || TEXT.requestFailed);
  }
});
liveWsBtn?.addEventListener("click", async () => {
  try {
    await startLiveAudioWs();
  } catch (error) {
    showError(error.message || TEXT.requestFailed);
  }
});
toggleMicRouteBtn?.addEventListener("click", () => toggleLiveRoute("mic"));
toggleSystemRouteBtn?.addEventListener("click", () => toggleLiveRoute("system"));
retryBtn.addEventListener("click", () => {
  hideError();
  if (lastPayload) runAnalysis();
});
backBtn.addEventListener("click", () => {
  hideError();
  stopLoadingSequence();
  stopPolling();
  resetRealtimeState();
  showView("input");
});
editAgainBtn.addEventListener("click", () => {
  resetRealtimeState();
  showView("input");
});
realtimePauseBtn?.addEventListener("click", async () => {
  try {
    await toggleRealtimePlayback();
  } catch (error) {
    showError(error.message || TEXT.requestFailed);
  }
});
realtimeEndBtn?.addEventListener("click", async () => {
  try {
    await endRealtimeSession();
  } catch (error) {
    showError(error.message || TEXT.requestFailed);
  }
});
viewFullReportBtn?.addEventListener("click", () => {
  if (!pendingFinalRealtimeReport) return;
  renderReport(pendingFinalRealtimeReport.report, pendingFinalRealtimeReport.source);
  viewFullReportBtn.classList.add("hidden");
});
modeQuickEl?.addEventListener("change", applyModeCards);
modeFullEl?.addEventListener("change", applyModeCards);

transcriptEl.value = DEFAULT_TRANSCRIPT;
jobHintEl.value = "\u540e\u7aef\u5de5\u7a0b\u5e08";
renderLoading(0);
resetRealtimeState();
showView("input");
applyModeCards();
loadSampleLibrary();
