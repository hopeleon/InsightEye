const transcriptEl = document.getElementById("transcript");
const jobHintEl = document.getElementById("jobHint");
const sampleSelectEl = document.getElementById("sampleSelect");
const analyzeBtn = document.getElementById("analyzeBtn");
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
let sampleLibrary = [];
let defaultSampleLoaded = false;
let lastPayload = null;
let lastReport = null;
let loadingTimer = null;
let currentTaskId = null;  // 新增：当前 LLM 任务 ID
let pollTimer = null;      // 新增：轮询定时器
const TEXT = {
  na: "暂无数据",
  sourceLlm: "LLM 主分析",
  sourceLocal: "本地规则分析",
  unknown: "未知",
  fill: "填充示例",
  loading: "加载中...",
  analyzing: "分析中...",
  run: "开始分析",
  selectSample: "请选择样例",
  sampleLoadFailed: "样例库加载失败",
  sampleTextLoadFailed: "样例文本加载失败",
  pasteTranscriptFirst: "请先粘贴完整的面试文本。",
  requestFailed: "请求失败",
  askFirst: "优先追问：",
  noFollowup: "暂无推荐追问",
  noRiskSummary: "暂无明确风险总结。",
  noRiskDetail: "暂无风险细节。",
  continueValidate: "建议继续，但需优先核验薄弱点。",
  needMoreSamples: "当前样本不足，建议继续补充面试信息。",
  weakSignals: "当前信号过弱，暂时无法形成稳定总结。",
  validateEvidence: "这些标签只能作为快速提示，仍需结合证据核验。",
  loadingMessage: "请稍候，系统正在拆解问答、提取证据并生成评估。",
};
const DISC_META = {
  D: { label: "D / 红色", className: "d", style: "结果导向、推进直接" },
  I: { label: "I / 黄色", className: "i", style: "外放表达、感染带动" },
  S: { label: "S / 绿色", className: "s", style: "稳定协作、节奏平和" },
  C: { label: "C / 蓝色", className: "c", style: "结构清晰、注重细节" },
};
const LOADING_STEPS = ["正在解析面试文本","正在提取行为与证据信号","正在生成 DISC 评估与面试建议"];
const DEFAULT_TRANSCRIPT = `面试官：讲一个你做过的技术项目。
候选人：我之前参与过一个订单系统优化项目，高峰期响应时间不太稳定。我主要参与了接口和数据流程优化，也看了日志和监控，调整了一些逻辑，还加了一部分缓存，整体性能有一定改善。
面试官：你具体是怎么定位问题的？
候选人：我主要先看日志和响应时间，再看哪些接口比较慢。有些问题比较明显，比如重复查询，优化后会有一些效果。`;
function setHtml(id, html) { const el = document.getElementById(id); if (el) el.innerHTML = html; }
function setText(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
function safeText(value, fallback = TEXT.na) { return value === null || value === undefined || value === "" ? fallback : value; }
function createList(items, renderer, empty = TEXT.na) { return !items || !items.length ? `<div class="list-item">${empty}</div>` : items.map(renderer).join(""); }
function rankDimensions(scores) { return Object.entries(scores || {}).sort((a, b) => b[1] - a[1]).map(([key, value]) => ({ key, value })); }
function getPrimaryAnalysis(report) { return report.llm_analysis && report.llm_analysis.scores ? { source: TEXT.sourceLlm, analysis: report.llm_analysis } : { source: TEXT.sourceLocal, analysis: report.disc_analysis }; }
function riskLevelClass(level) { const lowered = String(level || "low").toLowerCase(); if (lowered.includes("高") || lowered.includes("high") || lowered.includes("failed")) return "high"; if (lowered.includes("中") || lowered.includes("medium") || lowered.includes("skipped")) return "medium"; return "low"; }
function scoreByRisk(level) { const type = riskLevelClass(level); return type === "high" ? 42 : type === "medium" ? 67 : 84; }
function trimSentence(value, fallback = TEXT.na, limit = 60) {
  const content = safeText(value, fallback).replace(/\s+/g, " ").trim();
  if (content.length <= limit) return content;
  const compact = content.split(/[。；!！?？]/)[0].trim();
  return compact && compact.length >= 8 ? `${compact}。` : `${content.slice(0, limit)}...`;
}
function buildStyleSummary(analysis) {
  if (analysis.decision_summary) return trimSentence(analysis.decision_summary, TEXT.weakSignals, 42);
  const ranking = rankDimensions(analysis.scores);
  const top = ranking[0];
  const second = ranking[1];
  if (!top || !second) return TEXT.weakSignals;
  return `整体偏${DISC_META[top.key]?.style || TEXT.unknown}，次要信号为${DISC_META[second.key]?.style || TEXT.unknown}。`;
}
function buildStyleNote(analysis) { return trimSentence(analysis.overall_style_summary || TEXT.needMoreSamples, TEXT.needMoreSamples, 40); }
function buildRiskHeadline(analysis) { return trimSentence(analysis.risk_summary || TEXT.noRiskSummary, TEXT.noRiskSummary, 36); }
function buildRiskDetail(analysis) { return analysis.critical_findings?.length ? analysis.critical_findings.slice(0, 2).map((item) => item.finding).join("；") : trimSentence((analysis.meta?.notes || []).slice(0, 2).join("；") || TEXT.noRiskDetail, TEXT.noRiskDetail, 50); }
function buildNextAction(analysis) { return trimSentence(analysis.recommended_action || TEXT.continueValidate, TEXT.continueValidate, 36); }
function buildCapabilityTags(report) {
  const f = report.atomic_features || {};
  const tags = [];
  if ((f.star_structure_score || 0) >= 0.75) tags.push("结构完整"); else if ((f.star_structure_score || 0) >= 0.5) tags.push("结构中等"); else tags.push("结构偏弱");
  if ((f.logical_connector_ratio || 0) >= 0.015) tags.push("逻辑较清晰"); else tags.push("逻辑待验证");
  if ((f.story_richness_score || 0) >= 0.65) tags.push("细节丰富"); else if ((f.story_richness_score || 0) >= 0.45) tags.push("细节一般"); else tags.push("细节偏薄");
  if ((f.action_verbs_ratio || 0) >= 0.02) tags.push("动作表达较强");
  return tags;
}
function buildDiscTagline(analysis) {
  const ranking = rankDimensions(analysis.scores);
  const top = ranking[0];
  const second = ranking[1];
  if (!top) return TEXT.na;
  const firstLabel = DISC_META[top.key]?.style || TEXT.unknown;
  const secondLabel = second ? DISC_META[second.key]?.style : "";
  return secondLabel ? `人格标签：${firstLabel} / ${secondLabel}` : `人格标签：${firstLabel}`;
}
function buildStrengthItems(report, analysis) {
  const items = [];
  const tags = buildCapabilityTags(report);
  if (tags[0]) items.push(tags[0]);
  if (analysis.dimension_analysis) items.push(...Object.values(analysis.dimension_analysis).flatMap((item) => item.evidence_for || []).slice(0, 3));
  return [...new Set(items.filter(Boolean))].slice(0, 3);
}
function buildRiskItems(analysis) {
  const findings = (analysis.critical_findings || []).map((item) => item.finding);
  const gaps = analysis.evidence_gaps || [];
  return [...new Set([...findings, ...gaps].filter(Boolean))].slice(0, 3);
}
function scoreToLevel(value) { return value >= 75 ? "high" : value >= 50 ? "medium" : "low"; }
function levelLabel(level) { return level === "high" ? "高" : level === "medium" ? "中" : "低"; }
function bulletHtml(items, empty = TEXT.na) {
  if (!items || !items.length) return `<div class="bullet-item"><span class="bullet-dot"></span><span>${empty}</span></div>`;
  return items.slice(0, 3).map((item) => `<div class="bullet-item"><span class="bullet-dot"></span><span>${trimSentence(item, TEXT.na, 36)}</span></div>`).join("");
}
function buildInsightBullets(report, analysis) {
  const capabilityTags = buildCapabilityTags(report);
  const riskBullets = [...(analysis.critical_findings || []).map((item) => item.finding), ...(analysis.evidence_gaps || [])].filter(Boolean).slice(0, 3);
  const actionBullets = [analysis.recommended_action, analysis.follow_up_questions?.[0]?.question, analysis.follow_up_questions?.[1]?.question].filter(Boolean).slice(0, 3);
  const evidenceBullets = [...capabilityTags, ...(analysis.meta?.notes || [])].filter(Boolean).slice(0, 3);
  return { riskBullets, actionBullets, evidenceBullets };
}
function buildCapabilityCards(report, analysis) {
  const f = report.atomic_features || {};
  const riskClass = riskLevelClass(analysis.meta?.impression_management_risk);
  const riskScore = riskClass === "high" ? 82 : riskClass === "medium" ? 56 : 24;
  const cards = [
    { title: "表达能力", score: Math.round(((f.logical_connector_ratio || 0) / 0.03) * 100), desc: "看表达是否顺畅、重点是否能快速落位。" },
    { title: "结构能力", score: Math.round((f.star_structure_score || 0) * 100), desc: "看回答是否具备问题、动作、结果的完整骨架。" },
    { title: "证据强度", score: Math.round((f.story_richness_score || 0) * 100), desc: "看细节、量化与验证锚点是否足够。" },
    { title: "包装风险", score: riskScore, desc: "看是否存在套话、泛化和证据支撑不足。", risk: true },
  ];
  return cards.map((item) => {
    const safeScore = Math.max(8, Math.min(100, item.score || 0));
    const level = scoreToLevel(safeScore);
    const badgeLevel = item.risk ? riskLevelClass(analysis.meta?.impression_management_risk) : level;
    const badgeText = item.risk ? safeText(analysis.meta?.impression_management_risk, "中") : levelLabel(level);
    return `<div class="ability-row"><div class="ability-row-head"><strong>${item.title}</strong><span class="capability-badge ${badgeLevel}">${badgeText}</span></div><div class="ability-progress"><span style="width:${safeScore}%"></span></div><div class="ability-note">${item.desc}</div></div>`;
  }).join("");
}
function showView(name) { inputView.classList.toggle("hidden", name !== "input"); loadingView.classList.toggle("hidden", name !== "loading"); resultView.classList.toggle("hidden", name !== "result"); }
function renderLoading(stepIndex = 0) {
  loadingMessageEl.textContent = TEXT.loadingMessage;
  loadingStepsEl.innerHTML = LOADING_STEPS.map((step, index) => {
    const state = index < stepIndex ? "done" : index === stepIndex ? "active" : "";
    return `<div class="loading-step ${state}"><span class="loading-step-dot"></span><span>${step}</span></div>`;
  }).join("");
}
function startLoadingSequence() {
  let stepIndex = 0;
  renderLoading(stepIndex);
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => {
    stepIndex = (stepIndex + 1) % LOADING_STEPS.length;
    renderLoading(stepIndex);
  }, 1100);
}
function stopLoadingSequence() { clearInterval(loadingTimer); loadingTimer = null; }
function showError(message) { stopLoadingSequence(); errorBoxEl.classList.remove("hidden"); errorTextEl.textContent = message || TEXT.requestFailed; }
function hideError() { errorBoxEl.classList.add("hidden"); errorTextEl.textContent = ""; }
function renderDiscBars(analysis) {
  return rankDimensions(analysis.scores).map(({ key, value }) => `<div class="metric-bar"><div class="metric-bar-head"><span>${DISC_META[key]?.label || key}</span><strong>${value}</strong></div><div class="bar-track"><div class="bar-fill ${DISC_META[key]?.className || ""}" style="width:${Math.max(8, value)}%"></div></div></div>`).join("");
}
function renderDiscPie(analysis) {
  const scores = analysis.scores || {};
  const total = Object.values(scores).reduce((sum, value) => sum + Number(value || 0), 0) || 1;
  const ordered = ["D", "I", "S", "C"].map((key) => ({ key, value: Number(scores[key] || 0) }));
  let angle = 0;
  const stops = ordered.map(({ key, value }) => {
    const start = angle;
    angle += (value / total) * 360;
    return `${getComputedStyle(document.documentElement).getPropertyValue(`--${key.toLowerCase()}-color`).trim()} ${start.toFixed(1)}deg ${angle.toFixed(1)}deg`;
  });
  const top = rankDimensions(scores)[0];
  return `<div class="disc-pie" style="background: conic-gradient(${stops.join(", ")});"><div class="disc-pie-center"><div><strong>${top?.value || 0}</strong><span>${DISC_META[top?.key]?.label || TEXT.na}</span></div></div></div><div class="disc-pie-caption">基于当前分值分布计算的 D / I / S / C 相对占比。</div>`;
}
function renderHeroScore(analysis) {
  const riskClass = riskLevelClass(analysis.meta?.impression_management_risk);
  const score = scoreByRisk(analysis.meta?.impression_management_risk);
  const ringColor = riskClass === "high" ? "var(--risk)" : riskClass === "medium" ? "#a16bff" : "var(--success)";
  return `<div class="score-ring" style="background: conic-gradient(${ringColor} ${score * 3.6}deg, rgba(255,255,255,0.12) 0deg);"><div class="score-ring-inner"><strong>${score}</strong><span>可信度 / 可用度</span></div></div>`;
}
function renderDimensionCards(targetId, analysis) {
  setHtml(targetId, Object.entries(analysis || {}).map(([dim, item]) => `<div class="dimension-card"><h3>${dim} - ${safeText(item.score, 0)}</h3><p>${safeText(item.summary)}</p><strong>支持证据</strong><ul>${(item.evidence_for || []).slice(0, 3).map((entry) => `<li>${entry}</li>`).join("") || "<li>暂无</li>"}</ul><strong>反证线索</strong><ul>${(item.evidence_against || []).slice(0, 2).map((entry) => `<li>${entry}</li>`).join("") || "<li>暂无</li>"}</ul></div>`).join("") || `<div class="list-item">${TEXT.na}</div>`);
}
function renderWorkflow(report) {
  const workflow = report.workflow || {};
  const stageTrace = workflow.stage_trace || [];
  setText("workflowStageTop", String(stageTrace.length));
  setHtml("workflowStages", createList(stageTrace, (item, index) => `<div class="workflow-stage"><div class="workflow-stage-top"><div class="workflow-stage-name"><span class="workflow-step-index">${index + 1}</span><strong>${safeText(item.stage)}</strong></div><span class="workflow-stage-status ${riskLevelClass(item.status)}">${safeText(item.status)}</span></div><div class="workflow-stage-meta"><span>${trimSentence(item.detail, TEXT.na, 48)}</span></div></div>`, TEXT.na));
  const evidence = workflow.disc_evidence || {};
  setHtml("workflowEvidence", `<div class="workflow-tile"><strong>维度排序</strong><div>${safeText((evidence.ranking || []).join(" / "), TEXT.na)}</div></div><div class="workflow-tile"><strong>分值摘要</strong><div>${Object.entries(evidence.scores || {}).map(([k, v]) => `<span class="inline-kpi">${k}: ${v}</span>`).join("") || TEXT.na}</div></div><div class="workflow-tile"><strong>证据亮点</strong><div>${trimSentence((evidence.feature_highlights || []).join("；") || TEXT.na, TEXT.na, 60)}</div></div>`);
  const masking = workflow.masking_assessment || {};
  setHtml("workflowMasking", `<div class="workflow-tile"><strong>关键缺陷</strong><div>${trimSentence((masking.critical_findings || []).map((item) => item.finding).join("；") || TEXT.na, TEXT.na, 60)}</div></div><div class="workflow-tile"><strong>证据缺口</strong><div>${trimSentence((masking.evidence_gaps || []).join("；") || TEXT.na, TEXT.na, 60)}</div></div><div class="workflow-tile"><strong>录用风险</strong><div>${trimSentence((masking.hire_risks || []).join("；") || TEXT.na, TEXT.na, 60)}</div></div>`);
  const decision = workflow.decision_payload || {};
  setHtml("workflowDecision", `<div class="workflow-tile"><strong>决策总结</strong><p>${trimSentence(decision.decision_summary, TEXT.na, 60)}</p></div><div class="workflow-tile"><strong>风险结论</strong><p>${trimSentence(decision.risk_summary, TEXT.na, 60)}</p></div><div class="workflow-tile"><strong>推荐动作</strong><p>${trimSentence(decision.recommended_action, TEXT.na, 60)}</p></div>`);
}
function renderDecisionLayer(report, analysis, source) {
  const bullets = buildInsightBullets(report, analysis);
  setText("analysisSource", source);
  setText("analysisSourceTop", source);
  setText("candidateStyle", buildStyleSummary(analysis));
  setText("candidateStyleNote", buildStyleNote(analysis));
  setText("riskHeadline", buildRiskHeadline(analysis));
  setText("nextAction", buildNextAction(analysis));
  setText("riskLevelTop", safeText(analysis.meta?.impression_management_risk, "未判定"));
  setHtml("heroScore", renderHeroScore(analysis));
  setHtml("riskBulletList", bulletHtml(bullets.riskBullets));
  setHtml("actionBulletList", bulletHtml(bullets.actionBullets));
  setHtml("evidenceBulletList", bulletHtml(bullets.evidenceBullets));
  setHtml("topFollowups", createList((analysis.follow_up_questions || []).slice(0, 3), (item, index) => `<div class="followup-item"><span class="followup-index">${index + 1}</span><div><strong>${trimSentence(item.question, TEXT.na, 42)}</strong><p>${trimSentence(item.purpose, TEXT.na, 54)}</p></div></div>`, TEXT.noFollowup));
  setHtml("strengthList", createList(buildStrengthItems(report, analysis), (item) => `<div class="micro-item bare"><span class="micro-dot"></span><span>${trimSentence(item, TEXT.na, 34)}</span></div>`, TEXT.na));
  setHtml("riskList", createList(buildRiskItems(analysis), (item) => `<div class="micro-item bare"><span class="micro-dot negative"></span><span>${trimSentence(item, TEXT.na, 34)}</span></div>`, TEXT.na));
  const riskTags = [...buildCapabilityTags(report), ...(analysis.evidence_gaps || []).slice(0, 2)].filter(Boolean).slice(0, 5);
  setHtml("riskTags", createList(riskTags, (note) => `<div class="tag summary-tag">${trimSentence(note, TEXT.na, 18)}</div>`, TEXT.na));
  setText("riskStripHeadline", buildRiskHeadline(analysis));
  setText("riskStripDetail", buildRiskDetail(analysis));
}
function renderMetricsLayer(report, analysis) {
  setHtml("discPie", renderDiscPie(analysis));
  setHtml("discBars", renderDiscBars(analysis));
  setText("discTagline", buildDiscTagline(analysis));
  setText("discExplain", trimSentence(analysis.validated_style || analysis.overall_style_summary || TEXT.validateEvidence, TEXT.validateEvidence, 56));
  const riskClass = riskLevelClass(analysis.meta?.impression_management_risk);
  const riskLabel = safeText(analysis.meta?.impression_management_risk, "低");
  const riskScale = riskClass === "high" ? 88 : riskClass === "medium" ? 58 : 28;
  setHtml("riskMeter", `<div class="risk-strip-value"><span class="risk-badge ${riskClass}">${riskLabel}</span><div class="risk-scale-bar compact"><div class="risk-scale-fill ${riskClass}" style="width:${riskScale}%"></div></div></div>`);
  setHtml("capabilityCards", buildCapabilityCards(report, analysis));
}
function renderInterviewOverview(report) {
  setText("turnCountTop", String(report.input_overview?.turn_count || 0));
  setText("jobGuessTop", report.interview_map?.job_inference?.value || TEXT.unknown);
  setText("candidateCharTop", String(report.input_overview?.candidate_char_count || 0));
  setText("sampleQualityTop", safeText(report.llm_analysis?.meta?.sample_quality || report.disc_analysis?.meta?.sample_quality));
  setText("sampleQualityTopDetail", safeText(report.llm_analysis?.meta?.sample_quality || report.disc_analysis?.meta?.sample_quality));
  setText("parseSourceTop", safeText(report.interview_map?.parse_source));
  setHtml("overview", [`<div class="chip">岗位猜测：${report.interview_map?.job_inference?.value || TEXT.unknown}</div>`,`<div class="chip">问答轮次：${report.input_overview?.turn_count || 0}</div>`,`<div class="chip">候选人字数：${report.input_overview?.candidate_char_count || 0}</div>`,`<div class="chip">样本质量：${safeText(report.llm_analysis?.meta?.sample_quality || report.disc_analysis?.meta?.sample_quality)}</div>`,`<div class="chip">解析来源：${safeText(report.interview_map?.parse_source)}</div>`].join(""));
  setHtml("turns", createList(report.interview_map?.turns, (turn) => `<div class="turn-item"><div class="type">第 ${turn.turn_id} 轮 · ${safeText(turn.question_type)}</div><p><strong>问题：</strong>${safeText(turn.question, TEXT.na)}</p><p><strong>回答摘要：</strong>${safeText(turn.answer_summary)}</p></div>`, TEXT.na));
}
function renderDetailedLayer(report, analysis, source) {
  renderDimensionCards("dimensions", analysis.dimension_analysis || {});
  setHtml("criticalFindings", createList(analysis.critical_findings, (item) => `<div class="list-item"><div class="type">${safeText(item.severity)}</div><p><strong>${safeText(item.finding)}</strong></p><p>${(item.basis || []).join("；") || TEXT.na}</p><p>${safeText(item.impact, TEXT.na)}</p></div>`, TEXT.na));
  setHtml("evidenceGaps", createList(analysis.evidence_gaps, (item) => `<div class="list-item"><p>${safeText(item)}</p></div>`, TEXT.na));
  const features = report.atomic_features ? [{ label: "STAR 完整度", value: `${Math.round((report.atomic_features.star_structure_score || 0) * 100)}%` }, { label: "逻辑连接词比例", value: report.atomic_features.logical_connector_ratio }, { label: "动作动词比例", value: report.atomic_features.action_verbs_ratio }, { label: "故事丰富度", value: `${Math.round((report.atomic_features.story_richness_score || 0) * 100)}%` }, { label: "个人 / 团队取向", value: report.atomic_features.self_vs_team_orientation }, { label: "问题 / 人际取向", value: report.atomic_features.problem_vs_people_focus }] : [];
  setHtml("features", createList(features, (item) => `<div class="feature-item"><strong>${item.label}</strong><div>${item.value}</div></div>`, TEXT.na));
  setHtml("hypotheses", createList(analysis.behavioral_hypotheses, (item) => `<div class="list-item"><div class="type">${safeText(item.strength)}</div><p>${safeText(item.hypothesis)}</p><p>${(item.basis || []).join("；")}</p></div>`, TEXT.na));
  setHtml("followups", createList(analysis.follow_up_questions, (item) => `<div class="list-item"><div class="type">${safeText(item.target_dimension)}</div><p>${safeText(item.question)}</p><p>${safeText(item.purpose)}</p></div>`, TEXT.noFollowup));
  const llmStatus = report.llm_status?.enabled ? [`当前主视图：${source}`,`解析模型：${report.llm_status.parser_model}`,`主分析模型：${report.llm_status.analysis_model}`,report.llm_status.parser_error ? `解析错误：${report.llm_status.parser_error}` : "解析模型可用。",report.llm_status.analysis_error ? `分析错误：${report.llm_status.analysis_error}` : "分析模型可用。"].join("<br />") : TEXT.sourceLocal;
  setHtml("llmStatus", llmStatus);
  setText("llmOutput", JSON.stringify(report.llm_analysis || report.disc_analysis, null, 2));
}
function renderMBTILayer(report) {
  const mbti = report.mbti_analysis || {};
  
  if (!mbti.type) {
    console.log("⚠️ 未检测到 MBTI 分析结果");
    return;
  }
  
  console.log("📊 渲染 MBTI 分析...", mbti);
  
  // ========== 渲染整体置信度 ==========
  const confidenceBadge = document.getElementById("mbtiConfidence");
  if (confidenceBadge) {
    const conf = mbti.meta?.confidence || "low";
    confidenceBadge.textContent = conf === "high" ? "高置信" : conf === "medium" ? "中置信" : "低置信";
    confidenceBadge.className = `source-badge confidence-${conf}`;
  }
  
  // ========== 渲染 MBTI 类型 ==========
  const typeBadge = document.getElementById("mbtiTypeBadge");
  if (typeBadge) {
    typeBadge.textContent = mbti.type;
    typeBadge.className = `mbti-type-badge mbti-${mbti.type.toLowerCase().replace(/x/g, "neutral")}`;
  }
  
  const typeDesc = document.getElementById("mbtiTypeDesc");
  if (typeDesc) {
    typeDesc.textContent = mbti.type_description || "认知风格类型";
  }
  
  // ========== 渲染冲突列表 ==========
  const conflictsEl = document.getElementById("mbtiConflicts");
  if (conflictsEl) {
    const conflicts = mbti.conflicts || [];
    
    if (conflicts.length === 0) {
      conflictsEl.innerHTML = '<div class="mbti-no-conflict">✓ DISC 与 MBTI 无明显冲突</div>';
    } else {
      conflictsEl.innerHTML = conflicts.map((item) => {
        const severityClass = item.severity === "high" ? "high" : item.severity === "medium" ? "medium" : "low";
        return `
          <div class="mbti-conflict-item ${severityClass}">
            <div class="mbti-conflict-head">
              <span class="mbti-conflict-badge ${severityClass}">${item.severity === "high" ? "高" : item.severity === "medium" ? "中" : "低"}</span>
              <strong>${safeText(item.description, TEXT.na)}</strong>
            </div>
            <p class="mbti-conflict-rec">${safeText(item.recommendation, "")}</p>
          </div>
        `;
      }).join("");
    }
  }
  
  // ========== 渲染四维度 ==========
  const dimensions = mbti.dimensions || {};
  
  renderMBTIDimension("E_I", dimensions.E_I || {});
  renderMBTIDimension("N_S", dimensions.N_S || {});
  renderMBTIDimension("T_F", dimensions.T_F || {});
  renderMBTIDimension("J_P", dimensions.J_P || {});
  
  // ========== 渲染追问建议 ==========
  const followupsEl = document.getElementById("mbtiFollowups");
  if (followupsEl) {
    const questions = mbti.follow_up_questions || [];
    
    if (questions.length === 0) {
      followupsEl.innerHTML = '<div class="question-item">暂无MBTI追问建议</div>';
    } else {
      followupsEl.innerHTML = questions.map((q) => `
        <div class="question-item">
          <strong>${safeText(q.question, TEXT.na)}</strong>
          <div>${safeText(q.purpose, "")}</div>
        </div>
      `).join("");
    }
  }
  
  console.log("✅ MBTI 渲染完成");
}


// ========== LLM 异步分析核心函数 ==========

async function performAnalysis(payload) {
  showView("loading");
  startLoadingSequence();
  hideError();
  
  // 停止之前的轮询
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  
  try {
    console.log("📤 发送分析请求...", payload);
    
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.error || TEXT.requestFailed);
    }
    
    const data = await res.json();
    console.log("📥 收到响应:", data);
    
    // ========== 1. 立即展示本地规则结果 ==========
    stopLoadingSequence();
    lastReport = data.local_result;
    renderReport(data.local_result, "local");
    showView("result");
    
    // ========== 2. 如果触发了 LLM，开始轮询 ==========
    if (data.llm_status.triggered) {
      currentTaskId = data.llm_status.task_id;
      showLLMLoadingBanner(data.llm_status.reason);
      startPollingLLM(currentTaskId);
    }
    
  } catch (err) {
    console.error("❌ 分析失败:", err);
    showError(err.message || TEXT.requestFailed);
  }
}


function showLLMLoadingBanner(reason) {
  // 移除旧的横幅
  document.getElementById("llmBanner")?.remove();
  
  const banner = document.createElement("div");
  banner.id = "llmBanner";
  banner.className = "llm-loading-banner";
  banner.innerHTML = `
    <div class="llm-banner-content">
      <div class="llm-spinner"></div>
      <div class="llm-banner-text">
        <strong>正在调用 LLM 深度分析...</strong>
        <p class="llm-reason">${reason}</p>
        <p class="llm-progress" id="llmProgress">准备中...</p>
      </div>
    </div>
    <button id="cancelLLM" class="llm-cancel-btn" title="取消深度分析">✕</button>
  `;
  
  resultView.prepend(banner);
  
  // 绑定取消按钮
  document.getElementById("cancelLLM")?.addEventListener("click", () => {
    if (confirm("确定取消 LLM 深度分析吗？将仅保留本地规则结果。")) {
      stopPollingLLM();
      banner.remove();
    }
  });
}


function startPollingLLM(taskId) {
  console.log(`🔄 开始轮询任务: ${taskId}`);
  
  let attempts = 0;
  const maxAttempts = 60; // 最多轮询 2 分钟
  
  pollTimer = setInterval(async () => {
    attempts++;
    
    try {
      const res = await fetch(`/api/llm_status/${taskId}`);
      
      if (!res.ok) {
        throw new Error("无法获取任务状态");
      }
      
      const data = await res.json();
      console.log(`📊 任务状态 [${attempts}/${maxAttempts}]:`, data.status);
      
      // 更新进度文本
      const progressEl = document.getElementById("llmProgress");
      if (progressEl) {
        progressEl.textContent = data.progress || "分析中...";
      }
      
      if (data.status === "completed") {
        stopPollingLLM();
        onLLMCompleted(data.result);
      } else if (data.status === "failed") {
        stopPollingLLM();
        onLLMFailed(data.error);
      } else if (attempts >= maxAttempts) {
        stopPollingLLM();
        onLLMTimeout();
      }
      
    } catch (err) {
      console.error("❌ 轮询失败:", err);
      stopPollingLLM();
      onLLMFailed(err.message);
    }
  }, 2000); // 每 2 秒轮询一次
}


function stopPollingLLM() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
    console.log("⏸️ 停止轮询");
  }
}


function onLLMCompleted(llmResult) {
  console.log("✨ LLM 分析完成:", llmResult);
  
  // 移除加载横幅，显示成功提示
  const banner = document.getElementById("llmBanner");
  if (banner) {
    banner.className = "llm-banner-success";
    banner.innerHTML = `
      <div class="llm-banner-content">
        <div class="llm-check">✓</div>
        <div class="llm-banner-text">
          <strong>LLM 深度分析已完成</strong>
          <p>结果已更新，变化部分已高亮显示</p>
        </div>
      </div>
    `;
    
    // 3 秒后淡出移除
    setTimeout(() => {
      banner.style.opacity = "0";
      setTimeout(() => banner.remove(), 300);
    }, 3000);
  }
  
  // 平滑更新结果
  lastReport = llmResult;
  updateResultWithAnimation(llmResult);
}


function onLLMFailed(error) {
  console.error("❌ LLM 分析失败:", error);
  
  const banner = document.getElementById("llmBanner");
  if (banner) {
    banner.className = "llm-banner-error";
    banner.innerHTML = `
      <div class="llm-banner-content">
        <div class="llm-error-icon">!</div>
        <div class="llm-banner-text">
          <strong>LLM 分析失败</strong>
          <p>${error || "未知错误"}</p>
          <p class="llm-fallback">已保留本地规则分析结果</p>
        </div>
      </div>
      <button onclick="this.parentElement.remove()" class="llm-cancel-btn">✕</button>
    `;
  }
}


function onLLMTimeout() {
  console.warn("⏱️ LLM 分析超时");
  
  const banner = document.getElementById("llmBanner");
  if (banner) {
    banner.className = "llm-banner-error";
    banner.innerHTML = `
      <div class="llm-banner-content">
        <div class="llm-error-icon">⏱</div>
        <div class="llm-banner-text">
          <strong>LLM 分析超时</strong>
          <p>深度分析耗时过长，已自动取消</p>
          <p class="llm-fallback">当前显示本地规则分析结果</p>
        </div>
      </div>
      <button onclick="this.parentElement.remove()" class="llm-cancel-btn">✕</button>
    `;
  }
}


function updateResultWithAnimation(newResult) {
  // 添加更新动画类
  resultView.classList.add("result-updating");
  
  setTimeout(() => {
    // 重新渲染结果
    renderReport(newResult, "llm");
    
    // 移除动画类
    setTimeout(() => {
      resultView.classList.remove("result-updating");
    }, 300);
  }, 200);
}

function renderMBTIDimension(dimKey, dimData) {
  const preference = dimData.preference || "-";
  const strength = dimData.strength || 50;
  const summary = dimData.summary || "等待分析";
  const evidence = dimData.evidence || {};
  const scores = dimData.scores || {};
  
  // 更新偏好标签
  const badgeEl = document.getElementById(`mbti${dimKey.replace("_", "")}`);
  if (badgeEl) {
    badgeEl.textContent = preference;
    badgeEl.className = `mbti-pref-badge pref-${preference.toLowerCase()}`;
  }
  
  // 更新进度条
  const barWrapEl = document.getElementById(`mbti${dimKey.replace("_", "")}Bar`);
  if (barWrapEl) {
    const [leftKey, rightKey] = dimKey.split("_");
    const leftScore = scores[leftKey] || 50;
    const rightScore = scores[rightKey] || 50;
    
    barWrapEl.innerHTML = `
      <div class="mbti-pref-labels">
        <span>${leftKey} ${leftScore}%</span>
        <span>${rightKey} ${rightScore}%</span>
      </div>
      <div class="mbti-pref-bar">
        <div class="mbti-pref-fill left pref-${leftKey.toLowerCase()}" style="width: ${leftScore}%"></div>
        <div class="mbti-pref-fill right pref-${rightKey.toLowerCase()}" style="width: ${rightScore}%"></div>
        <div class="mbti-pref-center"></div>
      </div>
    `;
  }
  
  // 更新总结
  const summaryEl = document.getElementById(`mbti${dimKey.replace("_", "")}Summary`);
  if (summaryEl) {
    summaryEl.textContent = summary;
  }
  
  // 更新证据
  const evidenceEl = document.getElementById(`mbti${dimKey.replace("_", "")}Evidence`);
  if (evidenceEl) {
    const [leftKey, rightKey] = dimKey.split("_");
    const leftEvidence = evidence[leftKey] || [];
    const rightEvidence = evidence[rightKey] || [];
    
    evidenceEl.innerHTML = `
      <div class="mbti-evidence-section">
        <strong>${leftKey} 型证据:</strong>
        <ul>
          ${leftEvidence.length > 0 ? leftEvidence.map((e) => `<li>${e}</li>`).join("") : "<li>暂无</li>"}
        </ul>
      </div>
      <div class="mbti-evidence-section">
        <strong>${rightKey} 型证据:</strong>
        <ul>
          ${rightEvidence.length > 0 ? rightEvidence.map((e) => `<li>${e}</li>`).join("") : "<li>暂无</li>"}
        </ul>
      </div>
    `;
  }
}
function renderReport(report, source = "local") {
  console.log(`渲染报告 [来源: ${source}]`, report);
  
  const { source: analysisSource, analysis } = getPrimaryAnalysis(report);
  
  // ========== 新增：显示分析来源标识 ==========
  const sourceBadge = document.getElementById("analysisSource");
  if (sourceBadge) {
    if (source === "local") {
      sourceBadge.textContent = "⚡ 快速分析（本地规则）";
      sourceBadge.className = "source-badge source-local";
    } else {
      sourceBadge.textContent = "✨ 深度分析（LLM）";
      sourceBadge.className = "source-badge source-llm";
    }
  }
  
  // ========== 原有渲染逻辑保持不变 ==========
  renderInterviewOverview(report);
  renderDecisionLayer(report, analysis, analysisSource);
  renderMetricsLayer(report, analysis);
  renderWorkflow(report);
  renderDetailedLayer(report, analysis, analysisSource);
  renderMBTILayer(report);
}
async function loadSampleLibrary() {
  try {
    const response = await fetch("/samples/index.json");
    if (!response.ok) throw new Error(TEXT.sampleLoadFailed);
    sampleLibrary = await response.json();
    sampleSelectEl.innerHTML = [`<option value="">${TEXT.selectSample}</option>`].concat(sampleLibrary.map((item) => `<option value="${item.id}">${item.title}</option>`)).join("");
    if (!defaultSampleLoaded && sampleLibrary.length) {
      sampleSelectEl.value = sampleLibrary[0].id;
      await fillSelectedSample();
      defaultSampleLoaded = true;
    }
  } catch {
    sampleSelectEl.innerHTML = `<option value="">${TEXT.sampleLoadFailed}</option>`;
  }
}
async function fillSelectedSample() {
  const selectedId = sampleSelectEl.value;
  if (!selectedId) { transcriptEl.value = DEFAULT_TRANSCRIPT; jobHintEl.value = "后端研发"; return; }
  const item = sampleLibrary.find((entry) => entry.id === selectedId);
  if (!item) return;
  sampleBtn.disabled = true;
  sampleBtn.textContent = TEXT.loading;
  try {
    const response = await fetch(`/samples/${item.filename}`);
    if (!response.ok) throw new Error(TEXT.sampleTextLoadFailed);
    transcriptEl.value = await response.text();
    jobHintEl.value = item.job_hint || "";
  } catch {
    transcriptEl.value = DEFAULT_TRANSCRIPT;
    jobHintEl.value = item.job_hint || "后端研发";
  } finally {
    sampleBtn.disabled = false;
    sampleBtn.textContent = TEXT.fill;
  }
}
async function runAnalysis() {
  const interview_transcript = transcriptEl.value.trim();
  if (!interview_transcript) { window.alert(TEXT.pasteTranscriptFirst); return; }
  lastPayload = { interview_transcript, job_hint_optional: jobHintEl.value.trim() };
  hideError();
  showView("loading");
  startLoadingSequence();
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = TEXT.analyzing;
  try {
    const response = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lastPayload) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || TEXT.requestFailed);
    stopLoadingSequence();
    renderReport(data);
    showView("result");
  } catch (error) {
    showError(error.message);
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = TEXT.run;
  }
}
sampleBtn.addEventListener("click", fillSelectedSample);
analyzeBtn.addEventListener("click", async () => {
  const transcript = transcriptEl.value.trim();
  const jobHint = jobHintEl.value.trim();
  
  if (!transcript) {
    alert(TEXT.pasteTranscriptFirst);
    return;
  }
  
  lastPayload = { 
    interview_transcript: transcript, 
    job_hint_optional: jobHint,
    force_llm: false,  // 不强制调用 LLM
  };
  
  await performAnalysis(lastPayload);  // 改用新函数
});
retryBtn.addEventListener("click", () => { if (lastPayload) runAnalysis(); });
backBtn.addEventListener("click", () => { hideError(); stopLoadingSequence(); showView("input"); });
editAgainBtn.addEventListener("click", () => { showView("input"); if (lastReport) statusEl.textContent = TEXT.sourceLocal; });
transcriptEl.value = DEFAULT_TRANSCRIPT;
jobHintEl.value = "后端研发";
renderLoading(0);
loadingMessageEl.textContent = TEXT.loadingMessage;
showView("input");
loadSampleLibrary();
