const transcriptEl = document.getElementById("transcript");
const jobHintEl = document.getElementById("jobHint");
const sampleSelectEl = document.getElementById("sampleSelect");
const analyzeBtn = document.getElementById("analyzeBtn");
const sampleBtn = document.getElementById("sampleBtn");
const resultsEl = document.getElementById("results");
const statusEl = document.getElementById("status");

let sampleLibrary = [];
let defaultSampleLoaded = false;
<<<<<<< Updated upstream

const TEXT = {
  na: "\u6682\u65e0\u6570\u636e",
  sourceLlm: "LLM \u4e3b\u5206\u6790",
  sourceLocal: "\u672c\u5730\u89c4\u5219\u5206\u6790",
  unknown: "\u672a\u77e5",
  noDetail: "\u6682\u65e0\u8bf4\u660e",
  defaultStatus: "\u5f53\u524d\u663e\u793a\u9ed8\u8ba4\u9884\u89c8\u6216\u672c\u5730\u89c4\u5219\u5206\u6790\u7ed3\u679c",
  fill: "\u586b\u5145",
  loading: "\u52a0\u8f7d\u4e2d...",
  analyzing: "\u5206\u6790\u4e2d...",
  run: "\u5f00\u59cb\u5206\u6790",
  selectSample: "\u8bf7\u9009\u62e9\u6837\u4f8b",
  sampleLoadFailed: "\u6837\u4f8b\u5e93\u52a0\u8f7d\u5931\u8d25",
  sampleTextLoadFailed: "\u6837\u4f8b\u6587\u672c\u52a0\u8f7d\u5931\u8d25",
  pasteTranscriptFirst: "\u8bf7\u5148\u7c98\u8d34\u5b8c\u6574\u7684\u9762\u8bd5\u6587\u672c\u3002",
  requestFailed: "\u8bf7\u6c42\u5931\u8d25",
  askFirst: "\u4f18\u5148\u8ffd\u95ee\uff1a",
  noFollowup: "\u6682\u65e0\u63a8\u8350\u8ffd\u95ee",
  noRiskSummary: "\u6682\u65e0\u660e\u786e\u98ce\u9669\u603b\u7ed3\u3002",
  noRiskDetail: "\u6682\u65e0\u98ce\u9669\u7ec6\u8282\u3002",
  continueValidate: "\u5efa\u8bae\u7ee7\u7eed\uff0c\u4f46\u9700\u4f18\u5148\u6838\u9a8c\u8584\u5f31\u70b9\u3002",
  needMoreSamples: "\u5f53\u524d\u6837\u672c\u4e0d\u8db3\uff0c\u5efa\u8bae\u7ee7\u7eed\u8865\u5145\u9762\u8bd5\u4fe1\u606f\u3002",
  weakSignals: "\u5f53\u524d\u4fe1\u53f7\u8fc7\u5f31\uff0c\u6682\u65f6\u65e0\u6cd5\u5f62\u6210\u7a33\u5b9a\u603b\u7ed3\u3002",
  validateEvidence: "\u8fd9\u4e9b\u6807\u7b7e\u53ea\u80fd\u4f5c\u4e3a\u5feb\u901f\u63d0\u793a\uff0c\u4ecd\u9700\u7ed3\u5408\u8bc1\u636e\u6838\u9a8c\u3002",
=======
let lastPayload = null;
let lastReport = null;
let loadingTimer = null;

function getCurrentMode() {
  if (modeRadios) {
    for (const r of modeRadios) {
      if (r.checked) return r.value;
    }
  }
  return "quick";
}

function getAnalysisEndpoint() {
  return getCurrentMode() === "full" ? "/api/analyze/full" : "/api/analyze";
}

function getLoadingSteps() {
  return getCurrentMode() === "full" ? LOADING_STEPS_FULL : LOADING_STEPS_QUICK;
}

function updateAnalyzeBtnText() {
  if (!analyzeBtn) return;
  analyzeBtn.textContent = getCurrentMode() === "full" ? TEXT.runFull : TEXT.run;
}

function updateModeHint() {
  const hint = document.getElementById("modeHint");
  if (!hint) return;
  hint.textContent = getCurrentMode() === "full" ? TEXT.loadingMessageFull : TEXT.loadingMessage;
}

function applyModeCardStyle() {
  const quickCard = document.getElementById("modeQuickCard");
  const fullCard = document.getElementById("modeFullCard");
  if (!quickCard || !fullCard) return;
  const isFull = getCurrentMode() === "full";
  quickCard.classList.toggle("active", !isFull);
  fullCard.classList.toggle("active", isFull);
}

function initModeSelector() {
  modeRadios = Array.from(document.querySelectorAll('input[name="modeGroup"]'));
  for (const r of modeRadios) {
    r.addEventListener("change", () => {
      updateAnalyzeBtnText();
      updateModeHint();
      applyModeCardStyle();
    });
  }
  applyModeCardStyle();
}


const TEXT = {
  na: "暂无数据",
  sourceLlm: "LLM 主分析",
  sourceLocal: "本地规则分析",
  unknown: "未知",
  fill: "填充示例",
  loading: "加载中...",
  analyzing: "分析中...",
  analyzingFull: "深度分析中...",
  run: "开始分析",
  runFull: "深度分析",
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
  loadingMessageFull: "请稍候，系统正在并行分析 DISC · BigFive · 九型 · MBTI · 跨模型映射。",
>>>>>>> Stashed changes
};

const DISC_META = {
  D: { label: "D / \u7ea2\u8272", className: "d", style: "\u7ed3\u679c\u5bfc\u5411\u3001\u63a8\u8fdb\u76f4\u63a5" },
  I: { label: "I / \u9ec4\u8272", className: "i", style: "\u5916\u653e\u8868\u8fbe\u3001\u611f\u67d3\u5e26\u52a8" },
  S: { label: "S / \u7eff\u8272", className: "s", style: "\u7a33\u5b9a\u534f\u4f5c\u3001\u8282\u594f\u5e73\u548c" },
  C: { label: "C / \u84dd\u8272", className: "c", style: "\u7ed3\u6784\u6e05\u6670\u3001\u6ce8\u91cd\u7ec6\u8282" },
};

<<<<<<< Updated upstream
const MBTI_DIM_LABELS = {
  E_I: "\u80fd\u91cf\u6765\u6e90",
  N_S: "\u4fe1\u606f\u83b7\u53d6",
  T_F: "\u51b3\u7b56\u65b9\u5f0f",
  J_P: "\u751f\u6d3b\u65b9\u5f0f",
};

/** WHR \u540c\u6b3e\uff1a\u7ef4\u5ea6\u4fa7\u6807\u7b7e\u4e0e\u8272\u5f69\uff08renderMBTIDimensions / \u5361\u7247\u6761\u4f9d\u8d56\u6b64\u5e38\u91cf\uff09 */
const MBTI_META = {
  E: { label: "\u5916\u5411 E", color: "#e57373" },
  I: { label: "\u5185\u5411 I", color: "#64b5f6" },
  N: { label: "\u76f4\u89c9 N", color: "#ba68c8" },
  S: { label: "\u5b9e\u611f S", color: "#ffb74d" },
  T: { label: "\u601d\u8003 T", color: "#4fc3f7" },
  F: { label: "\u60c5\u611f F", color: "#f06292" },
  J: { label: "\u5224\u65ad J", color: "#7986cb" },
  P: { label: "\u77e5\u89c9 P", color: "#81c784" },
  X: { label: "\u672a\u5b9a X", color: "#9e9e9e" },
};

// ========== MBTI \u515a\u5e95\u6d4b\u677f\uff1a\u6240\u6709\u5185\u5bb9\u653e\u5165 personality-row \u7684 mbtiCards \u5bb9\u5668\uff0c\u6c47\u96c6\u7c7b\u578b\u3001\u56db\u7ef4\u5ea6\u3001\u8ffd\u95ee\u548c\u51b2\u7a81 ==========

function mbtiConfLevel(conf) {
  const c = String(conf || "").toLowerCase();
  if (c.includes("clear") || c.includes("high")) return "high";
  if (c.includes("moderate") || c.includes("medium")) return "medium";
  if (c.includes("slight") || c.includes("neutral") || c.includes("low")) return "low";
  return "low";
}

/**
 * MBTI \u515a\u5e95\u6d4b\u677f\uff1a\u6240\u6709\u5185\u5bb9\u653e\u5165 personality-row \u7684 #mbtiCards
 * \u5305\u542b\uff1a\u7c7b\u578b\u5361\u3001\u56db\u7ef4\u5ea6\u3001\u8ffd\u95ee\u5efa\u8bae\u3001\u51b2\u7a81\u63d0\u793a
 */
function renderMbtiLayer(report) {
  const mbti = report.mbti_analysis || report.workflow?.mbti_analysis || report.workflow?.mbti_result;
  if (!mbti || !mbti.dimensions) {
    setHtml("mbtiCards", `<div class="mbti-na">${TEXT.na}</div>`);
    return;
  }

  const meta    = mbti.meta || {};
  const type    = safeText(mbti.type, TEXT.unknown);
  const typeDesc = safeText(mbti.type_description, TEXT.noDetail);
  const conf    = safeText(meta.confidence, "medium");
  const confCls = mbtiConfLevel(conf);
  const sampleQ = safeText(meta.sample_quality, "");
  const words   = meta.word_count ?? TEXT.na;
  const turns   = meta.turn_count ?? TEXT.na;

  // \u7c7b\u578b\u5361\uff08\u590d\u76f6\u80cc\u666f\uff0c\u5b57\u7b26\u7279\u8272\uff09
  const typeBadgeColor = confCls === "high" ? "#2f8667" : confCls === "medium" ? "#764ba2" : "#9e9e9e";
  const typeBadge = `
    <div class="mbti-hero">
      <div class="mbti-type-badge" style="background:${typeBadgeColor}">${type}</div>
      <div class="mbti-hero-meta">
        <p class="mbti-type-desc">${typeDesc}</p>
        <div class="mbti-meta-row">
          <span class="mbti-meta-chip">\u6837\u672c\uff1a${sampleQ || TEXT.na}</span>
          <span class="mbti-meta-chip">\u7f6e\u4fe1\u5ea6\uff1a<span class="risk-badge ${confCls}">${conf}</span></span>
          <span class="mbti-meta-chip">\u5b57\u6570\uff1a${words}</span>
          <span class="mbti-meta-chip">\u56de\u5408\uff1a${turns}</span>
        </div>
      </div>
    </div>`;

  // \u56db\u7ef4\u5ea6\uff082\u00d72 \u5361\u7247\u680f\uff09
  const dimOrder = ["E_I", "N_S", "T_F", "J_P"];
  const dimCards = `<div class="mbti-dim-grid">${dimOrder.map((dim) => {
    const obj      = mbti.dimensions[dim] || {};
    const pref     = safeText(obj.preference, "X");
    const strength = Number(obj.strength);
    const conf2    = safeText(obj.confidence, "medium");
    const pct      = Number.isFinite(strength) ? Math.max(6, Math.round(strength)) : 0;
    const color    = MBTI_META[pref]?.color || "#9e9e9e";
    return `
      <div class="mbti-dim-card" style="border-top:3px solid ${color}">
        <div class="mbti-dim-head">
          <span class="mbti-dim-label">${MBTI_DIM_LABELS[dim] || dim}</span>
          <span class="mbti-pref-tag" style="background:${color}">${pref}</span>
        </div>
        <div class="mbti-bar-track">
          <div class="mbti-bar-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        <div class="mbti-dim-footer">
          <span class="mbti-strength">${pct}%</span>
          <span class="risk-badge ${mbtiConfLevel(conf2)}">${conf2}</span>
        </div>
      </div>`;
  }).join("")}</div>`;

  // \u8ffd\u95ee\u5efa\u8bae
  const followups = (mbti.follow_up_questions || []).slice(0, 3);
  const followupHtml = followups.length
    ? `
      <div class="mbti-section">
        <div class="mbti-section-title">\u8ffd\u95ee\u5efa\u8bae</div>
        ${followups.map((q) => `
          <div class="mbti-question">
            <div class="mbti-q-meta"><span class="mbti-dim-tag">${safeText(q.dimension, "")}</span></div>
            <p class="mbti-q-text"><strong>${safeText(q.question)}</strong></p>
            <p class="mbti-q-purpose">${safeText(q.purpose)}</p>
          </div>`).join("")}
      </div>`
    : "";

  // \u51b2\u7a81\u63d0\u793a
  const conflicts = (mbti.conflicts || []).slice(0, 2);
  const conflictHtml = conflicts.length
    ? `
      <div class="mbti-section">
        <div class="mbti-section-title">\u4ea4\u53c9\u9a8c\u8bc1</div>
        ${conflicts.map((c) => {
          const sev = safeText(c.severity, "low");
          const col = sev === "high" ? "var(--danger)" : sev === "medium" ? "var(--warn)" : "var(--ok)";
          return `
            <div class="mbti-conflict-item" style="border-left:3px solid ${col}">
              <div class="mbti-conflict-head">
                <strong>${safeText(c.type)}</strong>
                <span class="risk-badge ${sev}">${sev}</span>
              </div>
              <p class="mbti-conflict-desc">${safeText(c.description)}</p>
              ${c.recommendation ? `<p class="mbti-conflict-rec">\u5efa\u8bae\uff1a${safeText(c.recommendation)}</p>` : ""}
            </div>`;
        }).join("")}
      </div>`
    : "";

  setHtml("mbtiCards", typeBadge + dimCards + followupHtml + conflictHtml);
}

const DEFAULT_TRANSCRIPT = `\u9762\u8bd5\u5b98\uff1a\u8bb2\u4e00\u4e2a\u4f60\u505a\u8fc7\u7684\u6280\u672f\u9879\u76ee\u3002
\u5019\u9009\u4eba\uff1a\u6211\u4e4b\u524d\u53c2\u4e0e\u8fc7\u4e00\u4e2a\u8ba2\u5355\u7cfb\u7edf\u4f18\u5316\u9879\u76ee\uff0c\u9ad8\u5cf0\u671f\u54cd\u5e94\u65f6\u95f4\u4e0d\u592a\u7a33\u5b9a\u3002\u6211\u4e3b\u8981\u53c2\u4e0e\u4e86\u63a5\u53e3\u548c\u6570\u636e\u6d41\u7a0b\u4f18\u5316\uff0c\u4e5f\u770b\u4e86\u65e5\u5fd7\u548c\u76d1\u63a7\uff0c\u8c03\u6574\u4e86\u4e00\u4e9b\u903b\u8f91\uff0c\u8fd8\u52a0\u4e86\u4e00\u90e8\u5206\u7f13\u5b58\uff0c\u6574\u4f53\u6027\u80fd\u6709\u4e00\u5b9a\u6539\u5584\u3002
\u9762\u8bd5\u5b98\uff1a\u4f60\u5177\u4f53\u662f\u600e\u4e48\u5b9a\u4f4d\u95ee\u9898\u7684\uff1f
\u5019\u9009\u4eba\uff1a\u6211\u4e3b\u8981\u5148\u770b\u65e5\u5fd7\u548c\u54cd\u5e94\u65f6\u95f4\uff0c\u518d\u770b\u54ea\u4e9b\u63a5\u53e3\u6bd4\u8f83\u6162\u3002\u6709\u4e9b\u95ee\u9898\u6bd4\u8f83\u660e\u663e\uff0c\u6bd4\u5982\u91cd\u590d\u67e5\u8be2\uff0c\u4f18\u5316\u540e\u4f1a\u6709\u4e00\u4e9b\u6548\u679c\u3002`;

const DEFAULT_REPORT = {
  input_overview: { segment_count: 6, turn_count: 2, candidate_char_count: 118 },
  interview_map: {
    job_inference: { value: "\u540e\u7aef\u7814\u53d1", confidence: 0.71, evidence: ["\u8ba2\u5355\u7cfb\u7edf", "\u63a5\u53e3", "\u7f13\u5b58"] },
    parse_source: "\u9ed8\u8ba4\u9884\u89c8",
    segments: [],
    turns: [
      { turn_id: 1, question: "\u8bb2\u4e00\u4e2a\u4f60\u505a\u8fc7\u7684\u6280\u672f\u9879\u76ee\u3002", question_type: "\u9879\u76ee\u7ecf\u5386", answer_summary: "\u5019\u9009\u4eba\u63cf\u8ff0\u4e86\u8ba2\u5355\u7cfb\u7edf\u4f18\u5316\u9879\u76ee\uff0c\u4f46\u5173\u952e\u52a8\u4f5c\u4e0e\u6280\u672f\u673a\u5236\u5c55\u5f00\u4e0d\u8db3\u3002" },
      { turn_id: 2, question: "\u4f60\u5177\u4f53\u662f\u600e\u4e48\u5b9a\u4f4d\u95ee\u9898\u7684\uff1f", question_type: "\u95ee\u9898\u5b9a\u4f4d", answer_summary: "\u5019\u9009\u4eba\u63d0\u5230\u65e5\u5fd7\u3001\u76d1\u63a7\u548c\u54cd\u5e94\u65f6\u95f4\uff0c\u4f46\u7f3a\u5c11\u660e\u786e\u6307\u6807\u4e0e\u8bca\u65ad\u94fe\u8def\u3002" },
    ],
  },
  atomic_features: {
    text_length: 118,
    star_structure_score: 0.46,
    logical_connector_ratio: 0.011,
    action_verbs_ratio: 0.013,
    story_richness_score: 0.38,
    self_vs_team_orientation: "\u504f\u4e2a\u4eba\u8868\u8fbe",
    problem_vs_people_focus: "\u504f\u95ee\u9898\u5bfc\u5411",
  },
  disc_analysis: {
    meta: {
      sample_quality: "\u4e2d\u7b49",
      confidence: "\u4e2d\u7b49",
      impression_management_risk: "\u4e2d\u7b49",
      notes: ["\u56de\u7b54\u5177\u5907\u57fa\u7840\u7ed3\u6784\uff0c\u4f46\u673a\u5236\u7ec6\u8282\u8f83\u8584\u3002", "\u6280\u672f\u672f\u8bed\u5b58\u5728\uff0c\u4f46\u6df1\u5ea6\u5c1a\u672a\u88ab\u8bc1\u660e\u3002"],
    },
    scores: { D: 34, I: 22, S: 49, C: 66 },
    ranking: ["C", "S", "D", "I"],
    decision_summary: "\u8868\u5c42\u98ce\u683c\u504f C/S\uff0c\u4f46\u66f4\u5f3a\u7684\u4fe1\u53f7\u662f\u6280\u672f\u56de\u7b54\u4fe1\u606f\u5bc6\u5ea6\u504f\u4f4e\u3002",
    risk_summary: "\u5b58\u5728\u4e2d\u9ad8\u5f3a\u5ea6\u8bc4\u4f30\u98ce\u9669\uff0c\u4e0d\u80fd\u53ea\u56e0\u4e3a\u8868\u8fbe\u987a\u7545\u5c31\u7ed9\u51fa\u8f83\u9ad8\u8bc4\u4ef7\u3002",
    recommended_action: "\u5efa\u8bae\u7ee7\u7eed\u9762\u8bd5\uff0c\u4f46\u4f18\u5148\u6838\u9a8c\u5b9a\u4f4d\u903b\u8f91\u3001\u53d6\u820d\u8fc7\u7a0b\u548c\u4e2a\u4eba\u51b3\u7b56\u70b9\u3002",
    overall_style_summary: "\u6837\u672c\u542c\u8d77\u6765\u6709\u4e00\u5b9a\u7ed3\u6784\u611f\uff0c\u4f46\u8fd8\u4e0d\u8db3\u4ee5\u8bc1\u660e\u662f\u771f\u6b63\u9ad8\u4e25\u8c28\u3002\u56de\u7b54\u6574\u4f53\u6709\u5e8f\uff0c\u4e0d\u8fc7\u8fb9\u754c\u3001\u673a\u5236\u548c\u9a8c\u8bc1\u6b65\u9aa4\u4ecd\u7136\u504f\u8584\u3002",
    critical_findings: [
      { finding: "\u56de\u7b54\u504f\u957f\uff0c\u4f46\u4fe1\u606f\u5bc6\u5ea6\u4e0d\u8db3\u3002", severity: "\u9ad8", basis: ["\u63d0\u5230\u4e86\u65e5\u5fd7\u3001\u76d1\u63a7\u548c\u7f13\u5b58", "\u6ca1\u6709\u5c55\u5f00\u8bca\u65ad\u94fe\u8def\u548c\u5177\u4f53\u673a\u5236"], impact: "\u5bb9\u6613\u628a\u53c2\u4e0e\u5f0f\u63cf\u8ff0\u8bef\u5224\u6210\u8f83\u5f3a\u7684\u95ee\u9898\u89e3\u51b3\u80fd\u529b\u3002" },
      { finding: "\u7ed3\u679c\u8bc1\u636e\u504f\u5f31\uff0c\u7f3a\u5c11\u91cf\u5316\u5bf9\u6bd4\u3002", severity: "\u4e2d", basis: ["\u53ea\u8bf4\u6027\u80fd\u6709\u6539\u5584", "\u6ca1\u6709\u5177\u4f53\u6307\u6807\u6216\u533a\u95f4"], impact: "\u96be\u4ee5\u5224\u65ad\u771f\u5b9e\u6280\u672f\u4ef7\u503c\u3002" },
    ],
    hire_risks: ["\u6280\u672f\u6df1\u5ea6\u98ce\u9669", "\u4e3b\u5bfc\u6027\u9700\u8981\u9a8c\u8bc1"],
    evidence_gaps: ["\u7f3a\u5c11\u5177\u4f53\u8bca\u65ad\u6307\u6807", "\u7f3a\u5c11\u7f13\u5b58\u5c42\u7ea7\u6216\u67b6\u6784\u7ec6\u8282", "\u7f3a\u5c11\u91cf\u5316\u7ed3\u679c"],
    dimension_analysis: {
      D: { score: 34, summary: "\u6709\u4e00\u5b9a\u95ee\u9898\u5bfc\u5411\uff0c\u4f46\u51b3\u7b56\u538b\u5f3a\u504f\u5f31\u3002", evidence_for: ["\u63d0\u5230\u4f18\u5316\u52a8\u4f5c"], evidence_against: ["\u6ca1\u6709\u660e\u786e\u62cd\u677f\u8282\u70b9"] },
      I: { score: 22, summary: "\u4e92\u52a8\u4e0e\u5f71\u54cd\u4ed6\u4eba\u7684\u4fe1\u53f7\u8f83\u5f31\u3002", evidence_for: ["\u8868\u8fbe\u8f83\u6d41\u7545"], evidence_against: ["\u6ca1\u6709\u8bf4\u670d\u6216\u5f71\u54cd\u8fc7\u7a0b"] },
      S: { score: 49, summary: "\u8bed\u6c14\u8f83\u7a33\uff0c\u4f46\u5f3a S \u8bc1\u636e\u4ecd\u7136\u4e0d\u8db3\u3002", evidence_for: ["\u63aa\u8f9e\u5e73\u548c"], evidence_against: ["\u7f3a\u5c11\u957f\u671f\u652f\u6301\u6216\u8010\u5fc3\u7c7b\u8bc1\u636e"] },
      C: { score: 66, summary: "\u8868\u5c42\u7ed3\u6784\u611f\u6bd4\u8f83\u660e\u663e\uff0c\u4f46\u9ad8 C \u6df1\u5ea6\u5c1a\u672a\u8bc1\u5b9e\u3002", evidence_for: ["\u63d0\u5230\u65e5\u5fd7\u548c\u76d1\u63a7", "\u56de\u7b54\u987a\u5e8f\u8f83\u6e05\u695a"], evidence_against: ["\u673a\u5236\u3001\u8fb9\u754c\u548c\u9a8c\u8bc1\u7ec6\u8282\u4e0d\u8db3"] },
    },
    behavioral_hypotheses: [
      { hypothesis: "\u5019\u9009\u4eba\u5448\u73b0\u51fa\u8868\u5c42\u7ed3\u6784\u5316\u8868\u8fbe\u98ce\u683c\u3002", strength: "\u4e2d", basis: ["\u56de\u7b54\u6709\u660e\u663e\u987a\u5e8f", "\u91cd\u70b9\u56f4\u7ed5\u8bca\u65ad\u6d41\u7a0b\u5c55\u5f00"] },
      { hypothesis: "\u8fd9\u4e2a\u6837\u672c\u66f4\u50cf\u8c28\u614e\u53c2\u4e0e\uff0c\u800c\u4e0d\u662f\u5f3a\u4e3b\u5bfc\u3002", strength: "\u4e2d", basis: ["\u6ca1\u6709\u660e\u786e\u4e2a\u4eba\u62cd\u677f\u884c\u4e3a", "\u7f3a\u5c11\u5173\u952e\u51b3\u7b56\u5c55\u5f00"] },
    ],
    follow_up_questions: [
      { target_dimension: "C", question: "\u4f60\u7b2c\u4e00\u6b65\u770b\u7684\u662f\u54ea\u4e2a\u5177\u4f53\u6307\u6807\uff0c\u4e3a\u4ec0\u4e48\u5148\u770b\u5b83\uff1f", purpose: "\u9a8c\u8bc1\u662f\u5426\u5177\u5907\u7ed3\u6784\u5316\u8bca\u65ad\u80fd\u529b\u3002" },
      { target_dimension: "C", question: "\u7f13\u5b58\u5177\u4f53\u52a0\u5728\u54ea\u4e00\u5c42\uff0c\u4e3a\u4ec0\u4e48\u9009\u8fd9\u91cc\uff1f", purpose: "\u9a8c\u8bc1\u6280\u672f\u6df1\u5ea6\u548c\u8fb9\u754c\u610f\u8bc6\u3002" },
      { target_dimension: "D", question: "\u8fd9\u4e2a\u4f18\u5316\u91cc\u6709\u6ca1\u6709\u4f60\u4eb2\u81ea\u62cd\u677f\u7684\u53d6\u820d\uff1f", purpose: "\u786e\u8ba4\u662f\u4e2a\u4eba\u51b3\u7b56\u8fd8\u662f\u4ec5\u4ec5\u53c2\u4e0e\u6267\u884c\u3002" },
    ],
    feature_highlights: ["\u6709\u4e00\u5b9a\u7ed3\u6784\u611f", "\u4e3b\u8981\u98ce\u9669\u662f\u4fe1\u606f\u5bc6\u5ea6\u548c\u7ed3\u679c\u8bc1\u660e\u4e0d\u8db3"],
  },
  star_analysis: {
    dimension_scores: {
      S: { score: 62, band: "medium", interpretation: "\u60c5\u5883\u6709\u4e00\u5b9a\u80cc\u666f\uff0c\u4f46\u7f3a\u5c11\u5177\u4f53\u7ea6\u675f\u6761\u4ef6\u548c\u56f4\u5883\u8bf4\u660e\u3002" },
      T: { score: 35, band: "low", interpretation: "\u89d2\u8272\u5b9a\u4f4d\u6a21\u7cca\uff0c\u201c\u6211\u201d\u548c\u201c\u6211\u4eec\u201d\u6df7\u6dc6\uff0c\u4efb\u52a1\u8303\u56f4\u4e0d\u6e05\u3002" },
      A: { score: 28, band: "low", interpretation: "\u884c\u52a8\u591f\u63cf\u8ff0\u6d89\u5c3d\uff0c\u4f46\u7f3a\u5c11\u5177\u4f53\u6b65\u9aa4\u548c\u5de5\u5177\u65b9\u6cd5\u8bf4\u660e\u3002" },
      R: { score: 40, band: "medium", interpretation: "\u6709\u7ed3\u679c\u8c08\u53d6\uff0c\u4f46\u6ca1\u6709\u91cf\u5316\u6307\u6807\u548c\u5bf9\u6bd4\uff0c\u4ec5\u4f5c\u4e3a\u53c2\u8003\u3002" },
    },
    overall_score: 39.05,
    defects: [
      { defect_id: "action_vague", severity: "medium", label: "\u884c\u52a8\u7a7a\u6d1e", reason: "\u884c\u52a8\u591f\u63cf\u8ff0\u4f46\u7a76\u6784\u67b6\u4e0d\u6e05\uff0c\u7f3a\u5c11\u5177\u4f53\u6b65\u9aa4\u548c\u5de5\u5177\u3002" },
      { defect_id: "situation_missing", severity: "low", label: "\u60c5\u5883\u7f3a\u5931", reason: "\u6709\u65f6\u95f4\u6807\u8bb0\u4f46\u65e0\u7ea6\u675f\u6761\u4ef6\u548c\u56f4\u5883\u8bf4\u660e\u3002" },
    ],
    authenticity_summary: { overall: 39.05, confidence: "medium", confidence_notes: ["\u7f3a\u9677\u4e0e\u5f3a\u4fe1\u53f7\u5e76\u5b58\uff0c\u6837\u672c\u91cf\u4e0d\u8db3\u4ee5\u5f62\u6210\u5f3a\u7ed3\u8bba"], risk_signals: [] },
    star_disc_auxiliary_signals: ["STAR-\u9ad8\u5206\u4f46\u60c5\u5883\u504f\u5f31\uff0c\u5efa\u8bae\u5728DISC\u5206\u6790\u4e2d\u8c28\u614e\u89c2\u5bdf\u3002"],
    followup_questions: [],
    defect_interactions: [],
    meta: { sample_words: 118, turn_count: 2, star_structure_score: 0.46 },
  },
  bigfive_analysis: {
    scores: { openness: 0.72, conscientiousness: 0.65, extraversion: 0.38, agreeableness: 0.55, neuroticism: 0.42 },
    ranking: ["openness", "conscientiousness", "agreeableness", "neuroticism", "extraversion"],
    behavioral_hypotheses: [
      { hypothesis: "\u5019\u9009\u4eba\u5f00\u653e\u6027\u9ad8\uff0c\u611f\u5199\u80fd\u529b\u5f3a\uff0c\u559c\u6b22\u63a5\u89e6\u65b0\u4e8b\u7269\u3002", strength: "\u4e2d", basis: ["\u63d0\u5230\u65b0\u6280\u672f\uff0c\u63a5\u89e6\u4e86\u7f13\u5b58\u3001\u76d1\u63a7\u7b49\u65b0\u65b9\u6cd5"] },
      { hypothesis: "\u8d28\u7f1d\u6027\u5c3d\u8f83\u9ad8\uff0c\u6709\u7ec6\u81ea\u548c\u8ba1\u5212\u6027\uff0c\u4f46\u7ec6\u8282\u6267\u884c\u529b\u5c1a\u5f85\u9a8c\u8bc1\u3002", strength: "\u4e2d", basis: ["\u63d0\u5230\u4e86\u8ba1\u5212\u6027\u63aa\u65bd\uff0c\u4f46\u672a\u8bc1\u660e\u6267\u884c\u7ed3\u679c"] },
    ],
  },
  enneagram_analysis: {
    top_types: [
      { type: "5", score: 71, description: "\u89c2\u5bdf\u8005\u2014\u2014\u559c\u6b22\u63a2\u7d22\u3001\u6570\u636e\u5206\u6790\uff0c\u5f80\u5f80\u6709\u6df1\u5ea6\u7684\u4e13\u4e1a\u80fd\u529b\u3002" },
      { type: "1", score: 58, description: "\u6539\u5584\u8005\u2014\u2014\u9ad8\u6807\u51c6\u3001\u8c28\u614e\u6027\uff0c\u6ce8\u91cd\u89c4\u5219\u548c\u7ec6\u8282\u6267\u884c\u3002" },
      { type: "3", score: 44, description: "\u8bbe\u8ba1\u8005\u2014\u2014\u8fdb\u53d6\u5fc3\uff0c\u6ce8\u91cd\u6210\u5c31\u3002" },
    ],
    cross_model_notes: ["\u4e09\u578b\u516c\u5f00\u80fd\u529b\u4e0eDICS\u7c7b\u578b\u8868\u73b0\u57fa\u672c\u4e00\u81f4\uff0c\u5efa\u8bae\u5173\u6ce8\u5173\u6ce8\u6280\u672f\u6df1\u5ea6\u548c\u7ed3\u679c\u5f52\u56fe\u80fd\u529b\u3002"],
  },
  mbti_analysis: {
    meta: { sample_quality: "medium", confidence: "medium", word_count: 118, turn_count: 2 },
    type: "ISTJ",
    type_description: "\u9ed8\u8ba4\u9884\u89c8\uff1a\u6837\u672c\u504f\u6280\u672f\u7ec6\u8282\u4e0e\u903b\u8f91\u5b9a\u4f4d\uff0c\u7c7b\u578b\u4ec5\u4f9b\u5c55\u793a\u3002\u70b9\u51fb\u300c\u5f00\u59cb\u5206\u6790\u300d\u540e\u66ff\u6362\u4e3a\u5b9e\u65f6\u89c4\u5219\u7ed3\u679c\u3002",
    dimensions: {
      E_I: { preference: "I", strength: 58, confidence: "medium", scores: { E: 32, I: 48 }, evidence: { E: ["\u793a\u4f8b\uff1a\u793e\u4ea4\u8bcd\u6c47\u5360\u6bd4\u504f\u4f4e"], I: ["\u504f\u4e2a\u4eba\u884c\u52a8\u4e0e\u6280\u672f\u7ec6\u8282\u63cf\u8ff0"] } },
      N_S: { preference: "S", strength: 54, confidence: "medium", scores: { N: 36, S: 44 }, evidence: { N: [], S: ["\u5173\u6ce8\u65e5\u5fd7\u3001\u76d1\u63a7\u4e0e\u63a5\u53e3\u54cd\u5e94\u7b49\u5177\u4f53\u7ec6\u8282"] } },
      T_F: { preference: "T", strength: 62, confidence: "medium", scores: { T: 51, F: 31 }, evidence: { T: ["\u504f\u95ee\u9898\u4e0e\u673a\u5236\u5b9a\u4f4d"], F: [] } },
      J_P: { preference: "J", strength: 50, confidence: "low", scores: { J: 42, P: 36 }, evidence: { J: ["\u56de\u7b54\u6709\u660e\u663e\u6b65\u9aa4\u611f"], P: [] } },
    },
    conflicts: [],
    follow_up_questions: [
      { dimension: "J_P", question: "\u9047\u5230\u65b0\u9700\u6c42\u65f6\uff0c\u4f60\u66f4\u5e38\u5148\u9501\u5b9a\u65b9\u6848\u8fd8\u662f\u5148\u4fdd\u7559\u7075\u6d3b\u6027\uff1f", purpose: "\u9a8c\u8bc1 J/P \u5728\u5de5\u4f5c\u8282\u594f\u4e0a\u7684\u8868\u8fbe\u3002" },
    ],
    evidence_summary: {},
  },
  graph_boost: { enabled: false, skipped_stages: [], speedup_ratio: 0 },
  llm_analysis: null,
  llm_status: { enabled: false, parser_model: "gpt-5-mini", analysis_model: "gpt-5.4", parser_error: null, analysis_error: null, parser_output_available: false },
  workflow: {
    version: "v0.2-preview",
    mode: "disc",
    stage_trace: [
      { stage: "parse_stage", status: "completed", detail: "\u5df2\u62c6\u5206\u4e3a 2 \u8f6e\u95ee\u7b54" },
      { stage: "feature_stage", status: "completed", detail: "\u5df2\u63d0\u53d6\u539f\u5b50\u7279\u5f81" },
      { stage: "star_stage", status: "completed", detail: "\u5df2\u5b8c\u6210 STAR \u7ed3\u6784\u5206\u6790" },
      { stage: "disc_evidence_stage", status: "completed", detail: "\u5df2\u6784\u5efa D/I/S/C \u8bc1\u636e\u5305" },
      { stage: "masking_stage", status: "completed", detail: "\u8bc6\u522b\u5230 2 \u4e2a\u5173\u952e\u7f3a\u9677" },
      { stage: "decision_stage", status: "completed", detail: "\u5df2\u751f\u6210\u51b3\u7b56\u8f7d\u8377" },
      { stage: "llm_stage", status: "skipped", detail: "\u5f53\u524d\u5c55\u793a\u9ed8\u8ba4\u9884\u89c8\u6570\u636e" },
    ],
    disc_evidence: { scores: { D: 34, I: 22, S: 49, C: 66 }, ranking: ["C", "S", "D", "I"], feature_highlights: ["\u8868\u5c42\u7ed3\u6784\u660e\u663e", "\u95ee\u9898\u5bfc\u5411\u5f3a\u4e8e\u4eba\u9645\u5bfc\u5411"] },
    masking_assessment: {
      meta: { impression_management_risk: "\u4e2d\u7b49", confidence: "\u4e2d\u7b49" },
      critical_findings: [
        { finding: "\u56de\u7b54\u504f\u957f\uff0c\u4f46\u4fe1\u606f\u5bc6\u5ea6\u4e0d\u8db3\u3002", severity: "\u9ad8" },
        { finding: "\u7ed3\u679c\u8bc1\u636e\u504f\u5f31\uff0c\u7f3a\u5c11\u91cf\u5316\u5bf9\u6bd4\u3002", severity: "\u4e2d" },
      ],
      evidence_gaps: ["\u7f3a\u5c11\u8bca\u65ad\u6307\u6807", "\u7f3a\u5c11\u91cf\u5316\u7ed3\u679c"],
      hire_risks: ["\u6280\u672f\u6df1\u5ea6\u98ce\u9669", "\u4e3b\u5bfc\u6027\u9700\u8981\u9a8c\u8bc1"],
    },
    decision_payload: {
      decision_summary: "\u8868\u5c42\u98ce\u683c\u504f C/S\uff0c\u4f46\u66f4\u5f3a\u7684\u4fe1\u53f7\u662f\u6280\u672f\u56de\u7b54\u4fe1\u606f\u5bc6\u5ea6\u504f\u4f4e\u3002",
      risk_summary: "\u5b58\u5728\u4e2d\u9ad8\u5f3a\u5ea6\u8bc4\u4f30\u98ce\u9669\uff0c\u4e0d\u80fd\u53ea\u56e0\u4e3a\u8868\u8fbe\u987a\u7545\u5c31\u7ed9\u51fa\u8f83\u9ad8\u8bc4\u4ef7\u3002",
      recommended_action: "\u5efa\u8bae\u7ee7\u7eed\u9762\u8bd5\uff0c\u4f46\u4f18\u5148\u6838\u9a8c\u5b9a\u4f4d\u903b\u8f91\u3001\u53d6\u820d\u8fc7\u7a0b\u548c\u4e2a\u4eba\u51b3\u7b56\u70b9\u3002",
      overall_style_summary: "\u6837\u672c\u6709\u7ed3\u6784\u611f\uff0c\u4f46\u5c1a\u4e0d\u8db3\u4ee5\u652f\u6301\u9ad8\u4e25\u8c28\u5224\u65ad\u3002",
    },
  },
};

function createList(items, renderer, empty = TEXT.na) {
  if (!items || !items.length) return `<div class="list-item">${empty}</div>`;
  return items.map(renderer).join("");
}
function setHtml(id, html) { const el = document.getElementById(id); if (el) el.innerHTML = html; }
function setText(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
function safeText(value, fallback = TEXT.na) { return value === null || value === undefined || value === "" ? fallback : value; }
function rankDimensions(scores) { return Object.entries(scores || {}).sort((a, b) => b[1] - a[1]).map(([key, value]) => ({ key, value })); }
function getPrimaryAnalysis(report) { return report.llm_analysis && report.llm_analysis.scores ? { source: TEXT.sourceLlm, analysis: report.llm_analysis } : { source: TEXT.sourceLocal, analysis: report.disc_analysis }; }
function riskLevelClass(level) { const lowered = String(level || "low").toLowerCase(); if (lowered.includes("\u9ad8") || lowered.includes("high") || lowered.includes("failed")) return "high"; if (lowered.includes("\u4e2d") || lowered.includes("medium") || lowered.includes("skipped")) return "medium"; return "low"; }
function buildStyleSummary(analysis) { if (analysis.decision_summary) return analysis.decision_summary; const ranking = rankDimensions(analysis.scores); const top = ranking[0]; const second = ranking[1]; const topLabel = DISC_META[top?.key]?.style || "\u98ce\u683c\u4e0d\u660e\u786e"; const secondLabel = DISC_META[second?.key]?.style || ""; if (!top || !second) return TEXT.weakSignals; return `\u6574\u4f53\u66f4\u504f${topLabel}\uff0c\u6b21\u8981\u4fe1\u53f7\u4e3a${secondLabel}\u3002`; }
function buildStyleNote(analysis) { if (analysis.overall_style_summary) return analysis.overall_style_summary; return TEXT.needMoreSamples; }
function buildRiskHeadline(analysis) { if (analysis.risk_summary) return analysis.risk_summary; return TEXT.noRiskSummary; }
function buildRiskDetail(analysis) { if (analysis.critical_findings?.length) return analysis.critical_findings.slice(0, 2).map((item) => item.finding).join("\uff1b"); return (analysis.meta?.notes || []).slice(0, 2).join("\uff1b") || TEXT.noRiskDetail; }
function buildNextAction(analysis) { return analysis.recommended_action || TEXT.continueValidate; }
function buildNextActionDetail(analysis) { const topQuestion = analysis.follow_up_questions?.[0]?.question; return topQuestion ? `${TEXT.askFirst}${topQuestion}` : "\u7ee7\u7eed\u8981\u6c42\u5019\u9009\u4eba\u8bf4\u660e\u52a8\u4f5c\u3001\u51b3\u7b56\u548c\u7ed3\u679c\u8bc1\u636e\u3002"; }
function buildCapabilityTags(report) { const features = report.atomic_features || {}; const tags = []; if ((features.star_structure_score || 0) >= 0.75) tags.push("\u7ed3\u6784\u5b8c\u6574"); else if ((features.star_structure_score || 0) >= 0.5) tags.push("\u7ed3\u6784\u4e2d\u7b49"); else tags.push("\u7ed3\u6784\u504f\u5f31"); if ((features.logical_connector_ratio || 0) >= 0.015) tags.push("\u903b\u8f91\u8f83\u6e05\u6670"); else tags.push("\u903b\u8f91\u5f85\u9a8c\u8bc1"); if ((features.story_richness_score || 0) >= 0.65) tags.push("\u7ec6\u8282\u4e30\u5bcc"); else if ((features.story_richness_score || 0) >= 0.45) tags.push("\u7ec6\u8282\u4e00\u822c"); else tags.push("\u7ec6\u8282\u504f\u8584"); if ((features.action_verbs_ratio || 0) >= 0.02) tags.push("\u52a8\u4f5c\u8868\u8fbe\u8f83\u5f3a"); return tags; }
=======
const LOADING_STEPS_QUICK = [
  "正在解析面试文本",
  "正在提取行为与证据信号",
  "正在生成 DISC 评估与面试建议",
];

const LOADING_STEPS_FULL = [
  "正在解析面试文本",
  "正在提取行为与证据信号",
  "正在运行 DISC 分析",
  "正在并行 BigFive · 九型 · MBTI 规则分析",
  "正在跨模型人格映射",
  "正在生成最终结论",
];

const DEFAULT_TRANSCRIPT = `面试官：讲一个你做过的技术项目。
候选人：我之前参与过一个订单系统优化项目，高峰期响应时间不太稳定。我主要参与了接口和数据流程优化，也看了日志和监控，调整了一些逻辑，还加了一部分缓存，整体性能有一定改善。
面试官：你具体是怎么定位问题的？
候选人：我主要先看日志和响应时间，再看哪些接口比较慢。有些问题比较明显，比如重复查询，优化后会有一些效果。`;

// ─── 通用工具 ───────────────────────────────────────────────────────────────
function setHtml(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}
function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}
function safeText(value, fallback = TEXT.na) {
  return value === null || value === undefined || value === "" ? fallback : value;
}
function createList(items, renderer, empty = TEXT.na) {
  return !items || !items.length ? `<div class="list-item">${empty}</div>` : items.map(renderer).join("");
}
function rankDimensions(scores) {
  return Object.entries(scores || {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ key: k, value: v }));
}
function getPrimaryAnalysis(report) {
  return report.llm_analysis && report.llm_analysis.scores
    ? { source: TEXT.sourceLlm, analysis: report.llm_analysis }
    : { source: TEXT.sourceLocal, analysis: report.disc_analysis };
}
function riskLevelClass(level) {
  const s = String(level || "low").toLowerCase();
  if (s.includes("高") || s.includes("high") || s.includes("failed")) return "high";
  if (s.includes("中") || s.includes("medium") || s.includes("skipped")) return "medium";
  return "low";
}
function scoreByRisk(level) {
  const t = riskLevelClass(level);
  return t === "high" ? 42 : t === "medium" ? 67 : 84;
}
function scoreToLevel(value) {
  return value >= 75 ? "high" : value >= 50 ? "medium" : "low";
}
function levelLabel(level) {
  return level === "high" ? "高" : level === "medium" ? "中" : "低";
}
function trimSentence(value, fallback = TEXT.na, limit = 60) {
  const content = safeText(value, fallback).replace(/\s+/g, " ").trim();
  if (content.length <= limit) return content;
  const compact = content.split(/[。；!！?？]/)[0].trim();
  return compact && compact.length >= 8 ? `${compact}。` : `${content.slice(0, limit)}...`;
}

// ─── 视图切换 ───────────────────────────────────────────────────────────────
function showView(name) {
  inputView.classList.toggle("hidden", name !== "input");
  loadingView.classList.toggle("hidden", name !== "loading");
  resultView.classList.toggle("hidden", name !== "result");
  hideError();
}
function renderLoading(stepIndex = 0, steps) {
  loadingStepsEl.innerHTML = steps.map((step, i) => {
    const state = i < stepIndex ? "done" : i === stepIndex ? "active" : "";
    return `<div class="loading-step ${state}"><span class="loading-step-dot"></span><span>${step}</span></div>`;
  }).join("");
}
function startLoadingSequence(steps) {
  let idx = 0;
  renderLoading(idx, steps);
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => {
    idx = (idx + 1) % steps.length;
    renderLoading(idx, steps);
  }, 1100);
}
function stopLoadingSequence() { clearInterval(loadingTimer); loadingTimer = null; }
function showError(message) {
  stopLoadingSequence();
  showView("loading");
  errorBoxEl.classList.remove("hidden");
  errorTextEl.textContent = message || TEXT.requestFailed;
}
function hideError() {
  errorBoxEl.classList.add("hidden");
  errorTextEl.textContent = "";
}

// ─── DISC 核心渲染 ────────────────────────────────────────────────────────
function buildStyleSummary(analysis) {
  if (analysis.decision_summary) return trimSentence(analysis.decision_summary, TEXT.weakSignals, 42);
  const ranking = rankDimensions(analysis.scores);
  const top = ranking[0], second = ranking[1];
  if (!top || !second) return TEXT.weakSignals;
  return `整体偏${DISC_META[top.key]?.style || TEXT.unknown}，次要信号为${DISC_META[second.key]?.style || TEXT.unknown}。`;
}
function buildStyleNote(analysis) { return trimSentence(analysis.overall_style_summary || TEXT.needMoreSamples, TEXT.needMoreSamples, 40); }
function buildRiskHeadline(analysis) { return trimSentence(analysis.risk_summary || TEXT.noRiskSummary, TEXT.noRiskSummary, 36); }
function buildRiskDetail(analysis) {
  return analysis.critical_findings?.length
    ? analysis.critical_findings.slice(0, 2).map((i) => i.finding).join("；")
    : trimSentence((analysis.meta?.notes || []).slice(0, 2).join("；") || TEXT.noRiskDetail, TEXT.noRiskDetail, 50);
}
function buildNextAction(analysis) { return trimSentence(analysis.recommended_action || TEXT.continueValidate, TEXT.continueValidate, 36); }
function buildCapabilityTags(report) {
  const f = report.atomic_features || {};
  const tags = [];
  const ss = f.star_structure_score || 0;
  tags.push(ss >= 0.75 ? "结构完整" : ss >= 0.5 ? "结构中等" : "结构偏弱");
  tags.push((f.logical_connector_ratio || 0) >= 0.015 ? "逻辑较清晰" : "逻辑待验证");
  const sr = f.story_richness_score || 0;
  tags.push(sr >= 0.65 ? "细节丰富" : sr >= 0.45 ? "细节一般" : "细节偏薄");
  if ((f.action_verbs_ratio || 0) >= 0.02) tags.push("动作表达较强");
  return tags;
}
function buildDiscTagline(analysis) {
  const ranking = rankDimensions(analysis.scores);
  const top = ranking[0], second = ranking[1];
  if (!top) return TEXT.na;
  const lbl = DISC_META[top.key]?.style || TEXT.unknown;
  return second ? `人格标签：${lbl} / ${DISC_META[second.key]?.style || TEXT.unknown}` : `人格标签：${lbl}`;
}
function buildStrengthItems(report, analysis) {
  const items = [...buildCapabilityTags(report)];
  if (analysis.dimension_analysis) items.push(...Object.values(analysis.dimension_analysis).flatMap((i) => i.evidence_for || []).slice(0, 3));
  return [...new Set(items.filter(Boolean))].slice(0, 3);
}
function buildRiskItems(analysis) {
  const findings = (analysis.critical_findings || []).map((i) => i.finding);
  const gaps = analysis.evidence_gaps || [];
  return [...new Set([...findings, ...gaps].filter(Boolean))].slice(0, 3);
}
function bulletHtml(items, empty = TEXT.na) {
  if (!items || !items.length) return `<div class="bullet-item"><span class="bullet-dot"></span><span>${empty}</span></div>`;
  return items.slice(0, 3).map((item) => `<div class="bullet-item"><span class="bullet-dot"></span><span>${trimSentence(item, TEXT.na, 36)}</span></div>`).join("");
}
function buildInsightBullets(report, analysis) {
  const capabilityTags = buildCapabilityTags(report);
  const riskBullets = [...(analysis.critical_findings || []).map((i) => i.finding), ...(analysis.evidence_gaps || [])].filter(Boolean).slice(0, 3);
  const actionBullets = [analysis.recommended_action, analysis.follow_up_questions?.[0]?.question, analysis.follow_up_questions?.[1]?.question].filter(Boolean).slice(0, 3);
  const evidenceBullets = [...capabilityTags, ...(analysis.meta?.notes || [])].filter(Boolean).slice(0, 3);
  return { riskBullets, actionBullets, evidenceBullets };
}
function buildCapabilityCards(report, analysis) {
  const f = report.atomic_features || {};
  const rc = riskLevelClass(analysis.meta?.impression_management_risk);
  const riskScore = rc === "high" ? 82 : rc === "medium" ? 56 : 24;
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
>>>>>>> Stashed changes
function renderDiscBars(analysis) {
  return rankDimensions(analysis.scores).map(({ key, value }) => `<div class="metric-bar"><div class="metric-bar-head"><span>${DISC_META[key]?.label || key}</span><strong>${value}</strong></div><div class="bar-track"><div class="bar-fill ${DISC_META[key]?.className || ""}" style="width:${Math.max(8, value)}%"></div></div></div>`).join("");
}

const BIGFIVE_LABELS = {
  openness: { label: "\u5f00\u653e", desc: "\u654f\u611f\u3001\u597d\u5947\u5fc3" },
  conscientiousness: { label: "\u5c3d\u8d23", desc: "\u8c28\u614e\u3001\u81ea\u5f8b" },
  extraversion: { label: "\u5916\u5411", desc: "\u6d3b\u6cfc\u3001\u4e92\u52a8" },
  agreeableness: { label: "\u5b9c\u4eba", desc: "\u4fe1\u4efb\u3001\u5408\u4f5c" },
  neuroticism: { label: "\u795e\u7ecf\u8d28", desc: "\u60c5\u7eea\u3001\u62c5\u5fe7" },
};

/** \u672c\u5730 bigfive_engine \u7528 scores{O,C,E,A,N}\uff1bLLM \u8fd4\u56de bigfive_scores\u3002\u7edf\u4e00\u4e3a UI \u957f\u952e\u540d + 0\u20131\u3002 */
function normalizeBigFiveForUi(bf) {
  if (!bf) return bf;
  const s = bf.scores ?? bf.bigfive_scores;
  if (!s) return bf;
  const letterMap = { O: "openness", C: "conscientiousness", E: "extraversion", A: "agreeableness", N: "neuroticism" };
  if (s.O !== undefined || s.C !== undefined || s.E !== undefined || s.A !== undefined || s.N !== undefined) {
    const next = { ...bf, scores: {} };
    for (const [letter, name] of Object.entries(letterMap)) {
      const v = Number(s[letter]);
      if (Number.isFinite(v)) next.scores[name] = v > 1 ? v / 100 : v;
    }
    return next;
  }
  const longKeys = Object.values(letterMap);
  if (longKeys.some((k) => s[k] !== undefined && Number(s[k]) > 1)) {
    const next = { ...bf, scores: { ...s } };
    for (const k of longKeys) {
      const v = Number(next.scores[k]);
      if (Number.isFinite(v) && v > 1) next.scores[k] = v / 100;
    }
    return next;
  }
  return { ...bf, scores: s };
}

function pickBigFiveForSecondary(report) {
  const local = report.bigfive_analysis;
  const llm = report.llm_bigfive_analysis;
  if (llm && llm.bigfive_scores && typeof llm.bigfive_scores === "object") {
    return normalizeBigFiveForUi({
      ...local,
      scores: llm.bigfive_scores,
      behavioral_hypotheses: local?.behavioral_hypotheses,
    });
  }
  return normalizeBigFiveForUi(local);
}

/** \u672c\u5730/LMM \u4e5d\u578b\u7528 top_two_types\uff1b\u65e7\u6f14\u793a\u6570\u636e\u7528 top_types\uff08type / score\uff09\u3002 */
function normalizeEnneagramForUi(en) {
  if (!en) return en;
  if (en.top_types && en.top_types.length) return en;
  const two = en.top_two_types;
  if (two && two.length) {
    return {
      ...en,
      top_types: two.map((t) => ({
        type: String(t.type_number ?? t.type ?? ""),
        score: t.raw_score ?? t.score,
        description: (Array.isArray(t.key_evidence) ? t.key_evidence.join("\uff1b") : "") || t.label || "",
      })),
    };
  }
  const p = en.primary_type;
  if (p && p.type_number != null && p.type_number !== "") {
    const types = [
      {
        type: String(p.type_number),
        score: p.raw_score,
        description: p.interpretation || p.label || "",
      },
    ];
    const s = en.secondary_type;
    if (s && s.type_number != null && s.type_number !== "" && String(s.type_number) !== String(p.type_number)) {
      types.push({
        type: String(s.type_number),
        score: s.raw_score,
        description: s.interpretation || s.label || "",
      });
    }
    return { ...en, top_types: types };
  }
  return en;
}

function pickEnneagramForSecondary(report) {
  const local = report.enneagram_analysis;
  const llm = report.llm_enneagram_analysis;
  if (llm && typeof llm === "object" && (llm.top_two_types?.length || llm.primary_type)) {
    return normalizeEnneagramForUi({
      ...local,
      ...llm,
      cross_model_notes: local?.cross_model_notes ?? llm.cross_model_notes,
    });
  }
  return normalizeEnneagramForUi(local);
}

/** \u5408\u5e76 API / \u7f13\u5b58\u5f02\u5e38\u7684 dimension_scores\uff1b\u7f3a\u5931\u65f6\u7528 atomic_features \u7684 star_*_score \u5c55\u793a\u3002 */
function normalizeStarForSecondary(report) {
  const star = report.star_analysis || report.workflow?.star_analysis || report.workflow?.star_result;
  const rawDs =
    star && typeof star === "object" && star.dimension_scores && typeof star.dimension_scores === "object"
      ? star.dimension_scores
      : {};
  const letters = ["S", "T", "A", "R"];
  const featKeys = { S: "star_s_score", T: "star_t_score", A: "star_a_score", R: "star_r_score" };
  const normalizedDs = {};
  for (const dim of letters) {
    const cell = rawDs[dim] ?? rawDs[dim.toLowerCase()];
    if (cell && typeof cell === "object") {
      const sc = Number(cell.score);
      if (Number.isFinite(sc)) {
        normalizedDs[dim] = {
          score: sc,
          band: cell.band || (sc >= 75 ? "high" : sc >= 50 ? "medium" : "low"),
          interpretation: String(cell.interpretation || ""),
        };
      }
    }
    const direct = Number(rawDs[dim] ?? rawDs[dim.toLowerCase()]);
    if (!normalizedDs[dim] && Number.isFinite(direct)) {
      normalizedDs[dim] = {
        score: direct,
        band: direct >= 75 ? "high" : direct >= 50 ? "medium" : "low",
        interpretation: "",
      };
    }
  }
  const f = report.atomic_features || {};
  for (const dim of letters) {
    if (normalizedDs[dim]) continue;
    const raw = Number(f[featKeys[dim]]);
    if (!Number.isFinite(raw)) continue;
    const pct = raw <= 1 ? Math.round(raw * 100) : Math.round(raw);
    const band = pct >= 75 ? "high" : pct >= 50 ? "medium" : "low";
    normalizedDs[dim] = {
      score: pct,
      band,
      interpretation: "\u6839\u636e\u539f\u5b50\u7279\u5f81\u5c55\u793a",
    };
  }
  const legacyScores = star && typeof star === "object" && star.scores && typeof star.scores === "object" ? star.scores : {};
  for (const dim of letters) {
    if (normalizedDs[dim]) continue;
    const raw = Number(legacyScores[dim]);
    if (!Number.isFinite(raw)) continue;
    normalizedDs[dim] = {
      score: raw,
      band: raw >= 75 ? "high" : raw >= 50 ? "medium" : "low",
      interpretation: "\u6839\u636e\u517c\u5bb9\u5b57\u6bb5\u5c55\u793a",
    };
  }
  if (Object.keys(normalizedDs).length === 0) return null;
  const base = star && typeof star === "object" ? star : {};
  return {
    ...base,
    dimension_scores: normalizedDs,
    defects: Array.isArray(base.defects) ? base.defects : [],
    authenticity_summary: base.authenticity_summary || {
      confidence: "medium",
      overall: Number.isFinite(Number(f.star_structure_score)) ? Math.round(Number(f.star_structure_score) * 100) : undefined,
    },
  };
}

const ENNEAGRAM_LABELS = {
  "1": { label: "1\u53f7", name: "\u6539\u5584\u8005", desc: "\u539f\u5219\u3001\u8d23\u4efb\u5fc3" },
  "2": { label: "2\u53f7", name: "\u52a9\u4eba\u8005", desc: "\u70ed\u60c5\u3001\u8983\u8c31" },
  "3": { label: "3\u53f7", name: "\u8bbe\u8ba1\u8005", desc: "\u8fdb\u53d6\u3001\u6210\u5c31\u5fc3" },
  "4": { label: "4\u53f7", name: "\u7406\u60f3\u8005", desc: "\u60c5\u611f\u3001\u72ec\u7279" },
  "5": { label: "5\u53f7", name: "\u63a2\u7d22\u8005", desc: "\u89c2\u5bdf\u3001\u77e5\u8bc6" },
  "6": { label: "6\u53f7", name: "\u5b88\u671b\u8005", desc: "\u5ba1\u614e\u3001\u5b89\u5168" },
  "7": { label: "7\u53f7", name: "\u73a9\u56fe\u8005", desc: "\u4e50\u89c2\u3001\u5192\u9669" },
  "8": { label: "8\u53f7", name: "\u4fdd\u62a4\u8005", desc: "\u81ea\u4fe8\u3001\u6297\u4e89" },
  "9": { label: "9\u53f7", name: "\u548c\u89e3\u8005", desc: "\u4fdd\u548c\u3001\u987a\u4ece" },
};

function renderPersonalitySecondary(report) {
  // ── Big Five ────────────────────────────────────────────────────────────────
  const bf = pickBigFiveForSecondary(report);
  if (bf && bf.scores) {
    const items = Object.entries(BIGFIVE_LABELS).map(([key, meta]) => {
      const score = Number(bf.scores[key] || 0);
      const pct = Math.round(score * 100);
      const band = pct >= 70 ? "\u9ad8" : pct >= 40 ? "\u4e2d" : "\u4f4e";
      return `<div class="personality-dim">
        <span>${meta.label} <small style="opacity:.5">${meta.desc}</small></span>
        <strong>${pct}</strong>
        <div class="personality-dim-bar" style="width:${pct}%"></div>
        <span class="risk-badge ${riskLevelClass(band)}">${band}</span>
      </div>`;
    }).join("");
    const hypotheses = (bf.behavioral_hypotheses || []).slice(0, 2).map(h =>
      `<div class="personality-star-item" style="border-left:3px solid #4fc3f7;padding:5px 8px;margin-top:4px;border-radius:4px">
        <strong>${h.hypothesis || ""}</strong>
        <div style="opacity:.7;font-size:.78rem">${(h.basis || []).slice(0,2).join("\uff1b")}</div>
      </div>`
    ).join("");
    setHtml("bigfiveCards", items + hypotheses || `<div class="list-item">${TEXT.na}</div>`);
  } else {
    setHtml("bigfiveCards", `<div class="list-item">${TEXT.na}</div>`);
  }

  // ── Enneagram ──────────────────────────────────────────────────────────────
  const en = pickEnneagramForSecondary(report);
  if (en && en.top_types) {
    const top = en.top_types[0];
    const topMeta = ENNEAGRAM_LABELS[top?.type] || {};
    const topHtml = top ? `<div class="personality-star-item high" style="padding:8px;border-radius:5px;margin-bottom:6px">
      <strong>${topMeta.label || top.type} ${topMeta.name || ""}</strong>
      <div style="font-size:.78rem;opacity:.7">${topMeta.desc || ""}</div>
      <div style="font-size:.8rem;margin-top:3px">\u7b49\u7ea7\uff1a<strong>${top.score || ""}</strong></div>
    </div>` : "";
    const others = (en.top_types || []).slice(1, 3).map(t => {
      const m = ENNEAGRAM_LABELS[t?.type] || {};
      return `<div class="personality-star-item" style="border-left:3px solid #4fc3f7;padding:4px 8px;border-radius:4px;margin-top:3px">
        <span>${m.label || t?.type} ${m.name || ""} <strong>${t.score || ""}</strong></span>
      </div>`;
    }).join("");
    const mapping = en.cross_model_notes?.length
      ? `<div style="font-size:.78rem;opacity:.6;margin-top:6px">${en.cross_model_notes[0]}</div>`
      : "";
    setHtml("enneagramCards", topHtml + others + mapping || `<div class="list-item">${TEXT.na}</div>`);
  } else {
    setHtml("enneagramCards", `<div class="list-item">${TEXT.na}</div>`);
  }

  // ── STAR ───────────────────────────────────────────────────────────────────
  const star = normalizeStarForSecondary(report);
  if (star && star.dimension_scores && Object.keys(star.dimension_scores).length) {
    const dims = [["S", "\u60c5\u5883"], ["T", "\u4efb\u52a1"], ["A", "\u884c\u52a8"], ["R", "\u7ed3\u679c"]].map(([dim, name]) => {
      const s = star.dimension_scores[dim];
      if (!s) return "";
      const pct = s.score || 0;
      const band = s.band === "high" ? "\u9ad8" : s.band === "medium" ? "\u4e2d" : "\u4f4e";
      return `<div class="personality-star-item ${s.band === "high" ? "high" : s.band === "medium" ? "medium" : "low"}">
        <strong>${dim} ${name}</strong> \u5f97\u5206\uff1a${pct}
        <div class="personality-dim-bar" style="width:${pct}%;margin-top:3px"></div>
        <div style="font-size:.78rem;opacity:.7;margin-top:2px">${safeText(s.interpretation, "").slice(0, 36)}</div>
      </div>`;
    }).join("");

    const defects = (star.defects || []).slice(0, 3).map(d => {
      const cls = d.severity === "high" ? "high" : d.severity === "medium" ? "medium" : "low";
      return `<div class="personality-star-item ${cls}" style="padding:4px 8px;border-radius:4px;margin-top:4px;font-size:.78rem">
        <strong>${safeText(d.label, d.defect_id)}</strong> ${safeText(d.reason, "").slice(0, 40)}
      </div>`;
    }).join("");

    const meta = star.authenticity_summary || {};
    const confidenceTag = `<div style="margin-top:6px">
      <span class="risk-badge ${riskLevelClass(meta.confidence === "high" ? "\u9ad8" : meta.confidence === "medium" ? "\u4e2d" : "\u4f4e")}">
        \u771f\u5b9e\u6027\u7f6e\u4fe1\u5ea6\uff1a${safeText(meta.confidence)}
      </span>
    </div>`;

    const body = (dims || TEXT.na) + defects + confidenceTag;
    setHtml("starCards", body.trim() ? body : `<div class="list-item">${TEXT.na}</div>`);
  } else {
    const fallback = report.atomic_features || {};
    const fromAtomic = ["S", "T", "A", "R"].map((dim) => {
      const raw = Number(fallback[`star_${dim.toLowerCase()}_score`]);
      if (!Number.isFinite(raw)) return "";
      const pct = raw <= 1 ? Math.round(raw * 100) : Math.round(raw);
      return `<div class="personality-star-item low"><strong>${dim}</strong> ${pct}</div>`;
    }).join("");
    setHtml("starCards", fromAtomic || `<div class="list-item">${TEXT.na}</div>`);
  }
}

function renderDiscPie(analysis) {
  const scores = analysis.scores || {};
  const total = Object.values(scores).reduce((s, v) => s + Number(v || 0), 0) || 1;
  let angle = 0;
  const stops = ["D", "I", "S", "C"].map((k) => {
    const v = Number(scores[k] || 0);
    const start = angle;
    angle += (v / total) * 360;
    return `${getComputedStyle(document.documentElement).getPropertyValue(`--${k.toLowerCase()}-color`).trim()} ${start.toFixed(1)}deg ${angle.toFixed(1)}deg`;
  });
  const top = rankDimensions(scores)[0];
<<<<<<< Updated upstream
  const topLabel = DISC_META[top?.key]?.label || TEXT.na;
  const topValue = top?.value || 0;
  return `<div class="disc-pie" style="background: conic-gradient(${stops.join(", ")});"><div class="disc-pie-center"><div><strong>${topValue}</strong><span>${topLabel}</span></div></div></div><div class="disc-pie-caption">\u57fa\u4e8e\u5f53\u524d\u5206\u503c\u5206\u5e03\u8ba1\u7b97\u7684 D / I / S / C \u76f8\u5bf9\u5360\u6bd4\u3002</div>`;
=======
  return `<div class="disc-pie" style="background: conic-gradient(${stops.join(", ")});"><div class="disc-pie-center"><div><strong>${top?.value || 0}</strong><span>${DISC_META[top?.key]?.label || TEXT.na}</span></div></div></div><div class="disc-pie-caption">基于当前分值分布计算的 D / I / S / C 相对占比。</div>`;
}
function renderHeroScore(analysis) {
  const rc = riskLevelClass(analysis.meta?.impression_management_risk);
  const score = scoreByRisk(analysis.meta?.impression_management_risk);
  const color = rc === "high" ? "var(--risk)" : rc === "medium" ? "#a16bff" : "var(--success)";
  return `<div class="score-ring" style="background: conic-gradient(${color} ${score * 3.6}deg, rgba(255,255,255,0.12) 0deg);"><div class="score-ring-inner"><strong>${score}</strong><span>可信度 / 可用度</span></div></div>`;
}
function renderDimensionCards(targetId, analysis) {
  setHtml(targetId, Object.entries(analysis || {}).map(([dim, item]) => `<div class="dimension-card"><h3>${dim} - ${safeText(item.score, 0)}</h3><p>${safeText(item.summary)}</p><strong>支持证据</strong><ul>${(item.evidence_for || []).slice(0, 3).map((e) => `<li>${e}</li>`).join("") || "<li>暂无</li>"}</ul><strong>反证线索</strong><ul>${(item.evidence_against || []).slice(0, 2).map((e) => `<li>${e}</li>`).join("") || "<li>暂无</li>"}</ul></div>`).join("") || `<div class="list-item">${TEXT.na}</div>`);
>>>>>>> Stashed changes
}
function renderDimensionCards(targetId, analysis) { setHtml(targetId, Object.entries(analysis || {}).map(([dim, item]) => `<div class="dimension-card"><h3>${dim} - ${safeText(item.score, 0)}</h3><p>${safeText(item.summary)}</p><strong>\u652f\u6301\u8bc1\u636e</strong><ul>${(item.evidence_for || []).slice(0, 3).map((entry) => `<li>${entry}</li>`).join("") || "<li>\u6682\u65e0</li>"}</ul><strong>\u53cd\u8bc1\u7ebf\u7d22</strong><ul>${(item.evidence_against || []).slice(0, 2).map((entry) => `<li>${entry}</li>`).join("") || "<li>\u6682\u65e0</li>"}</ul></div>`).join("") || "<div class='list-item'>\u6682\u65e0\u7ef4\u5ea6\u5206\u6790</div>"); }
function renderWorkflow(report) {
  const workflow = report.workflow || {};
  const stageTrace = workflow.stage_trace || [];
  setText("workflowStageTop", String(stageTrace.length));
<<<<<<< Updated upstream
  setHtml("workflowStages", createList(stageTrace, (item) => `<div class="workflow-stage"><div class="workflow-stage-meta"><strong>${safeText(item.stage)}</strong><span>${safeText(item.detail, TEXT.noDetail)}</span></div><span class="workflow-stage-status ${riskLevelClass(item.status)}">${safeText(item.status)}</span></div>`, "\u6682\u65e0\u9636\u6bb5\u8f68\u8ff9"));
=======
  setHtml("workflowStages", createList(stageTrace, (item, i) => `<div class="workflow-stage"><div class="workflow-stage-top"><div class="workflow-stage-name"><span class="workflow-step-index">${i + 1}</span><strong>${safeText(item.stage)}</strong></div><span class="workflow-stage-status ${riskLevelClass(item.status)}">${safeText(item.status)}</span></div><div class="workflow-stage-meta"><span>${trimSentence(item.detail, TEXT.na, 48)}</span></div></div>`, TEXT.na));
>>>>>>> Stashed changes
  const evidence = workflow.disc_evidence || {};
  setHtml("workflowEvidence", `<div class="workflow-tile"><strong>\u7ef4\u5ea6\u6392\u5e8f</strong><div>${safeText((evidence.ranking || []).join(" / "), TEXT.na)}</div></div><div class="workflow-tile"><strong>\u5206\u503c\u6458\u8981</strong><div>${Object.entries(evidence.scores || {}).map(([k, v]) => `${k}: ${v}`).join(" | ") || TEXT.na}</div></div><div class="workflow-tile"><strong>\u8bc1\u636e\u4eae\u70b9</strong><div>${(evidence.feature_highlights || []).join("\uff1b") || TEXT.na}</div></div>`);
  const masking = workflow.masking_assessment || {};
<<<<<<< Updated upstream
  setHtml("workflowMasking", `<div class="workflow-tile"><strong>\u5173\u952e\u7f3a\u9677</strong><div>${(masking.critical_findings || []).map((item) => item.finding).join("\uff1b") || TEXT.na}</div></div><div class="workflow-tile"><strong>\u8bc1\u636e\u7f3a\u53e3</strong><div>${(masking.evidence_gaps || []).join("\uff1b") || TEXT.na}</div></div><div class="workflow-tile"><strong>\u5f55\u7528\u98ce\u9669</strong><div>${(masking.hire_risks || []).join("\uff1b") || TEXT.na}</div></div>`);
  const decision = workflow.decision_payload || {};
  setHtml("workflowDecision", `<div class="workflow-tile"><strong>\u51b3\u7b56\u603b\u7ed3</strong><p>${safeText(decision.decision_summary)}</p></div><div class="workflow-tile"><strong>\u98ce\u9669\u7ed3\u8bba</strong><p>${safeText(decision.risk_summary)}</p></div><div class="workflow-tile"><strong>\u63a8\u8350\u52a8\u4f5c</strong><p>${safeText(decision.recommended_action)}</p></div>`);
}
function renderDecisionLayer(report, analysis, source) { setText("analysisSource", source); setText("analysisSourceTop", source); setText("candidateStyle", buildStyleSummary(analysis)); setText("candidateStyleNote", buildStyleNote(analysis)); setText("riskHeadline", buildRiskHeadline(analysis)); setText("riskDetail", buildRiskDetail(analysis)); setText("nextAction", buildNextAction(analysis)); setText("nextActionDetail", buildNextActionDetail(analysis)); setText("riskLevelTop", safeText(analysis.meta?.impression_management_risk, "\u672a\u5224\u5b9a")); setHtml("topFollowups", createList((analysis.follow_up_questions || []).slice(0, 3), (item) => `<div class="question-item"><strong>${safeText(item.question)}</strong><div>${safeText(item.purpose)}</div></div>`, TEXT.noFollowup)); }
function renderMetricsLayer(report, analysis) { setHtml("discPie", renderDiscPie(analysis)); setHtml("discBars", renderDiscBars(analysis)); const riskClass = riskLevelClass(analysis.meta?.impression_management_risk); setHtml("riskMeter", `<div class="risk-head"><strong>${buildRiskHeadline(analysis)}</strong><span class="risk-badge ${riskClass}">${safeText(analysis.meta?.impression_management_risk, "\u4f4e")}</span></div><p class="card-note">${buildRiskDetail(analysis)}</p>`); setHtml("riskTags", createList([...(analysis.hire_risks || []), ...(analysis.evidence_gaps || []), ...((analysis.meta?.notes || []).slice(0, 2))].slice(0, 4), (note) => `<div class="tag">${note}</div>`, "\u6682\u65e0\u98ce\u9669\u6807\u7b7e")); const capabilityTags = buildCapabilityTags(report); setHtml("capabilityTags", capabilityTags.map((tag) => `<div class="tag">${tag}</div>`).join("")); setHtml("capabilitySummary", `${capabilityTags.join(" / ")}\u3002${TEXT.validateEvidence}`); }
function renderInterviewOverview(report) { setText("turnCountTop", String(report.input_overview?.turn_count || 0)); setHtml("overview", [`<div class="chip">\u5c97\u4f4d\u731c\u6d4b\uff1a${report.interview_map?.job_inference?.value || TEXT.unknown}</div>`,`<div class="chip">\u95ee\u7b54\u8f6e\u6b21\uff1a${report.input_overview?.turn_count || 0}</div>`,`<div class="chip">\u5019\u9009\u4eba\u5b57\u6570\uff1a${report.input_overview?.candidate_char_count || 0}</div>`,`<div class="chip">\u6837\u672c\u8d28\u91cf\uff1a${safeText(report.llm_analysis?.meta?.sample_quality || report.disc_analysis?.meta?.sample_quality)}</div>`,`<div class="chip">\u89e3\u6790\u6765\u6e90\uff1a${safeText(report.interview_map?.parse_source)}</div>`].join("")); setHtml("turns", createList(report.interview_map?.turns, (turn) => `<div class="turn-item"><div class="type">\u7b2c ${turn.turn_id} \u8f6e \u00b7 ${safeText(turn.question_type)}</div><p><strong>\u95ee\u9898\uff1a</strong>${safeText(turn.question, TEXT.na)}</p><p><strong>\u56de\u7b54\u6458\u8981\uff1a</strong>${safeText(turn.answer_summary)}</p></div>`, "\u6682\u65e0\u95ee\u7b54\u6620\u5c04")); }
function renderDetailedLayer(report, analysis, source) { renderDimensionCards("dimensions", analysis.dimension_analysis || {}); setHtml("criticalFindings", createList(analysis.critical_findings, (item) => `<div class="list-item"><div class="type">${safeText(item.severity)}</div><p><strong>${safeText(item.finding)}</strong></p><p>${(item.basis || []).join("\uff1b") || "\u6682\u65e0\u4f9d\u636e"}</p><p>${safeText(item.impact, "\u6682\u65e0\u5f71\u54cd\u8bf4\u660e")}</p></div>`, "\u6682\u65e0\u5173\u952e\u7f3a\u9677")); setHtml("evidenceGaps", createList(analysis.evidence_gaps, (item) => `<div class="list-item"><p>${safeText(item)}</p></div>`, "\u6682\u65e0\u8bc1\u636e\u7f3a\u53e3")); setHtml("features", createList(report.atomic_features ? [{ label: "STAR \u5b8c\u6574\u5ea6", value: `${Math.round((report.atomic_features.star_structure_score || 0) * 100)}%` },{ label: "\u903b\u8f91\u8fde\u63a5\u8bcd\u6bd4\u4f8b", value: report.atomic_features.logical_connector_ratio },{ label: "\u52a8\u4f5c\u52a8\u8bcd\u6bd4\u4f8b", value: report.atomic_features.action_verbs_ratio },{ label: "\u6545\u4e8b\u4e30\u5bcc\u5ea6", value: `${Math.round((report.atomic_features.story_richness_score || 0) * 100)}%` },{ label: "\u4e2a\u4eba / \u56e2\u961f\u53d6\u5411", value: report.atomic_features.self_vs_team_orientation },{ label: "\u95ee\u9898 / \u4eba\u9645\u53d6\u5411", value: report.atomic_features.problem_vs_people_focus }] : [], (item) => `<div class="feature-item"><strong>${item.label}</strong><div>${item.value}</div></div>`, "\u6682\u65e0\u539f\u5b50\u7279\u5f81")); setHtml("hypotheses", createList(analysis.behavioral_hypotheses, (item) => `<div class="list-item"><div class="type">${safeText(item.strength)}</div><p>${safeText(item.hypothesis)}</p><p>${(item.basis || []).join("\uff1b")}</p></div>`, "\u6682\u65e0\u884c\u4e3a\u5047\u8bbe")); setHtml("followups", createList(analysis.follow_up_questions, (item) => `<div class="list-item"><div class="type">${safeText(item.target_dimension)}</div><p>${safeText(item.question)}</p><p>${safeText(item.purpose)}</p></div>`, "\u6682\u65e0\u8ffd\u95ee\u5efa\u8bae")); const llmStatus = report.llm_status?.enabled ? [`\u5f53\u524d\u4e3b\u89c6\u56fe\uff1a${source}`,`\u89e3\u6790\u6a21\u578b\uff1a${report.llm_status.parser_model}`,`\u4e3b\u5206\u6790\u6a21\u578b\uff1a${report.llm_status.analysis_model}`,report.llm_status.parser_error ? `\u89e3\u6790\u9519\u8bef\uff1a${report.llm_status.parser_error}` : "\u89e3\u6790\u6a21\u578b\u53ef\u7528\u3002",report.llm_status.analysis_error ? `\u5206\u6790\u9519\u8bef\uff1a${report.llm_status.analysis_error}` : "\u5206\u6790\u6a21\u578b\u53ef\u7528\u3002"].join("<br />") : TEXT.defaultStatus; setHtml("llmStatus", llmStatus); setText("llmOutput", JSON.stringify(report.llm_analysis || report.disc_analysis, null, 2)); }
function renderReport(report) { const primary = getPrimaryAnalysis(report); resultsEl.classList.remove("hidden"); statusEl.textContent = report.llm_status?.enabled ? `\u89e3\u6790\u6a21\u578b\uff1a${report.llm_status.parser_model} / \u4e3b\u5206\u6790\u6a21\u578b\uff1a${report.llm_status.analysis_model}` : TEXT.defaultStatus; renderDecisionLayer(report, primary.analysis, primary.source); renderMetricsLayer(report, primary.analysis); renderPersonalitySecondary(report); renderMbtiLayer(report); renderWorkflow(report); renderInterviewOverview(report); renderDetailedLayer(report, primary.analysis, primary.source); }
async function loadSampleLibrary() { try { const response = await fetch("/samples/index.json"); if (!response.ok) throw new Error(TEXT.sampleLoadFailed); sampleLibrary = await response.json(); sampleSelectEl.innerHTML = [`<option value="">${TEXT.selectSample}</option>`].concat(sampleLibrary.map((item) => `<option value="${item.id}">${item.title}</option>`)).join(""); if (!defaultSampleLoaded && sampleLibrary.length) { sampleSelectEl.value = sampleLibrary[0].id; await fillSelectedSample(); defaultSampleLoaded = true; } } catch { sampleSelectEl.innerHTML = `<option value="">${TEXT.sampleLoadFailed}</option>`; } }
async function fillSelectedSample() { const selectedId = sampleSelectEl.value; if (!selectedId) { transcriptEl.value = DEFAULT_TRANSCRIPT; jobHintEl.value = "\u540e\u7aef\u7814\u53d1"; return; } const item = sampleLibrary.find((entry) => entry.id === selectedId); if (!item) return; sampleBtn.disabled = true; sampleBtn.textContent = TEXT.loading; try { const response = await fetch(`/samples/${item.filename}`); if (!response.ok) throw new Error(TEXT.sampleTextLoadFailed); transcriptEl.value = await response.text(); jobHintEl.value = item.job_hint || ""; } catch { transcriptEl.value = DEFAULT_TRANSCRIPT; jobHintEl.value = item.job_hint || "\u540e\u7aef\u7814\u53d1"; } finally { sampleBtn.disabled = false; sampleBtn.textContent = TEXT.fill; } }
sampleBtn.addEventListener("click", fillSelectedSample);
// /api/analyze/full：含大五/九型/STAR 本地规则；/api/analyze 仅 DISC，次要映射字段为 null
analyzeBtn.addEventListener("click", async () => { const interview_transcript = transcriptEl.value.trim(); if (!interview_transcript) { window.alert(TEXT.pasteTranscriptFirst); return; } const kgEl = document.getElementById("useKnowledgeGraph"); const use_knowledge_graph = !kgEl || kgEl.checked; analyzeBtn.disabled = true; analyzeBtn.textContent = TEXT.analyzing; try { const response = await fetch("/api/analyze/full", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ interview_transcript, job_hint_optional: jobHintEl.value.trim(), use_knowledge_graph }) }); const data = await response.json(); if (!response.ok) throw new Error(data.error || TEXT.requestFailed); renderReport(data); } catch (error) { window.alert(error.message); } finally { analyzeBtn.disabled = false; analyzeBtn.textContent = TEXT.run; } });
renderReport(DEFAULT_REPORT);
transcriptEl.value = DEFAULT_TRANSCRIPT;
jobHintEl.value = "\u540e\u7aef\u7814\u53d1";
=======
  setHtml("workflowMasking", `<div class="workflow-tile"><strong>关键缺陷</strong><div>${trimSentence((masking.critical_findings || []).map((i) => i.finding).join("；") || TEXT.na, TEXT.na, 60)}</div></div><div class="workflow-tile"><strong>证据缺口</strong><div>${trimSentence((masking.evidence_gaps || []).join("；") || TEXT.na, TEXT.na, 60)}</div></div><div class="workflow-tile"><strong>录用风险</strong><div>${trimSentence((masking.hire_risks || []).join("；") || TEXT.na, TEXT.na, 60)}</div></div>`);
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
  setHtml("topFollowups", createList((analysis.follow_up_questions || []).slice(0, 3), (item, i) => `<div class="followup-item"><span class="followup-index">${i + 1}</span><div><strong>${trimSentence(item.question, TEXT.na, 42)}</strong><p>${trimSentence(item.purpose, TEXT.na, 54)}</p></div></div>`, TEXT.noFollowup));
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
  const rc = riskLevelClass(analysis.meta?.impression_management_risk);
  setHtml("riskMeter", `<div class="risk-strip-value"><span class="risk-badge ${rc}">${safeText(analysis.meta?.impression_management_risk, "低")}</span><div class="risk-scale-bar compact"><div class="risk-scale-fill ${rc}" style="width:${rc === "high" ? 88 : rc === "medium" ? 58 : 28}%"></div></div></div>`);
  setHtml("capabilityCards", buildCapabilityCards(report, analysis));
}
function renderInterviewOverview(report) {
  setText("turnCountTop", String(report.input_overview?.turn_count || 0));
  setText("jobGuessTop", report.interview_map?.job_inference?.value || TEXT.unknown);
  setText("candidateCharTop", String(report.input_overview?.candidate_char_count || 0));
  setText("sampleQualityTop", safeText(report.llm_analysis?.meta?.sample_quality || report.disc_analysis?.meta?.sample_quality));
  setText("sampleQualityTopDetail", safeText(report.llm_analysis?.meta?.sample_quality || report.disc_analysis?.meta?.sample_quality));
  setText("parseSourceTop", safeText(report.interview_map?.parse_source));
  const chips = [
    `岗位猜测：${report.interview_map?.job_inference?.value || TEXT.unknown}`,
    `问答轮次：${report.input_overview?.turn_count || 0}`,
    `候选人字数：${report.input_overview?.candidate_char_count || 0}`,
    `样本质量：${safeText(report.llm_analysis?.meta?.sample_quality || report.disc_analysis?.meta?.sample_quality)}`,
    `解析来源：${safeText(report.interview_map?.parse_source)}`,
  ];
  setHtml("overview", chips.map((c) => `<div class="chip">${c}</div>`).join(""));
  setHtml("turns", createList(report.interview_map?.turns, (turn) => `<div class="turn-item"><div class="type">第 ${turn.turn_id} 轮 · ${safeText(turn.question_type)}</div><p><strong>问题：</strong>${safeText(turn.question, TEXT.na)}</p><p><strong>回答摘要：</strong>${safeText(turn.answer_summary)}</p></div>`, TEXT.na));
}
function renderDetailedLayer(report, analysis, source) {
  renderDimensionCards("dimensions", analysis.dimension_analysis || {});
  setHtml("criticalFindings", createList(analysis.critical_findings, (item) => `<div class="list-item"><div class="type">${safeText(item.severity)}</div><p><strong>${safeText(item.finding)}</strong></p><p>${(item.basis || []).join("；") || TEXT.na}</p><p>${safeText(item.impact, TEXT.na)}</p></div>`, TEXT.na));
  setHtml("evidenceGaps", createList(analysis.evidence_gaps, (item) => `<div class="list-item"><p>${safeText(item)}</p></div>`, TEXT.na));
  const features = report.atomic_features ? [
    { label: "STAR 完整度", value: `${Math.round((report.atomic_features.star_structure_score || 0) * 100)}%` },
    { label: "逻辑连接词比例", value: report.atomic_features.logical_connector_ratio },
    { label: "动作动词比例", value: report.atomic_features.action_verbs_ratio },
    { label: "故事丰富度", value: `${Math.round((report.atomic_features.story_richness_score || 0) * 100)}%` },
    { label: "个人 / 团队取向", value: report.atomic_features.self_vs_team_orientation },
    { label: "问题 / 人际取向", value: report.atomic_features.problem_vs_people_focus },
  ] : [];
  setHtml("features", createList(features, (item) => `<div class="feature-item"><strong>${item.label}</strong><div>${item.value}</div></div>`, TEXT.na));
  setHtml("hypotheses", createList(analysis.behavioral_hypotheses, (item) => `<div class="list-item"><div class="type">${safeText(item.strength)}</div><p>${safeText(item.hypothesis)}</p><p>${(item.basis || []).join("；")}</p></div>`, TEXT.na));
  setHtml("followups", createList(analysis.follow_up_questions, (item) => `<div class="list-item"><div class="type">${safeText(item.target_dimension)}</div><p>${safeText(item.question)}</p><p>${safeText(item.purpose)}</p></div>`, TEXT.noFollowup));
  const pm = report.llm_status?.personality_model;
  const statusParts = [`当前主视图：${source}`, `解析模型：${safeText(report.llm_status?.parser_model)}`, `主分析模型：${safeText(report.llm_status?.analysis_model)}`];
  if (pm) statusParts.splice(2, 0, `人格分析模型：${pm}`);
  if (report.llm_status?.parser_error) statusParts.push(`解析错误：${report.llm_status.parser_error}`);
  else statusParts.push("解析模型可用。");
  if (report.llm_status?.analysis_error) statusParts.push(`分析错误：${report.llm_status.analysis_error}`);
  else statusParts.push("分析模型可用。");
  setHtml("llmStatus", report.llm_status?.enabled ? statusParts.join("<br />") : TEXT.sourceLocal);
  setText("llmOutput", JSON.stringify(report.llm_analysis || report.disc_analysis, null, 2));
}

// ─── 冲突渲染（统一）──────────────────────────────────────────────────────
function renderConflictItem(item) {
  const sc = item.severity === "high" ? "high" : item.severity === "medium" ? "medium" : "low";
  const typeIcon = item.type || "冲突";
  const iconMap = {
    "DISC-MBTI 冲突": "◈",
    "BigFive ↔ DISC 冲突": "◉",
    "Enneagram ↔ DISC 冲突": "◐",
    "Enneagram ↔ STAR 包装风险": "⚠",
    "Enneagram ↔ DISC 风险信号": "◐",
  };
  const icon = iconMap[typeIcon] || "◈";
  return `<div class="conflict-item ${sc}">
    <div class="conflict-head">
      <span class="conflict-icon">${icon}</span>
      <span class="conflict-badge ${sc}">${sc === "high" ? "高" : sc === "medium" ? "中" : "低"}</span>
      <span class="conflict-type-label">${typeIcon}</span>
    </div>
    <p class="conflict-desc">${safeText(item.description, TEXT.na)}</p>
    ${item.recommendation ? `<div class="conflict-rec"><strong>追问建议：</strong>${safeText(item.recommendation)}</div>` : ""}
  </div>`;
}

function renderAllConflicts(report) {
  const mbti = report.mbti_analysis || {};
  const conflicts = mbti.conflicts || [];

  const conflictSection = document.getElementById("conflictSection");
  if (!conflictSection) return;

  if (conflicts.length === 0) {
    conflictSection.innerHTML = `<div class="conflict-empty">
      <div class="conflict-icon-wrap"><span>✓</span></div>
      <strong>DISC、MBTI、BigFive、九型人格之间无明显冲突</strong>
      <p>各模型结论一致性较高，人格画像置信度较好。</p>
    </div>`;
    return;
  }

  const high = conflicts.filter((c) => c.severity === "high");
  const med = conflicts.filter((c) => c.severity === "medium");
  const low = conflicts.filter((c) => c.severity !== "high" && c.severity !== "medium");

  let html = `<div class="conflict-summary-row">`;
  if (high.length) html += `<span class="conflict-summary-chip high">高风险 ${high.length}</span>`;
  if (med.length)  html += `<span class="conflict-summary-chip medium">中风险 ${med.length}</span>`;
  if (low.length)  html += `<span class="conflict-summary-chip low">低风险 ${low.length}</span>`;
  html += `</div>`;

  const groups = [
    ...high.map(renderConflictItem),
    ...med.map(renderConflictItem),
    ...low.map(renderConflictItem),
  ];
  conflictSection.innerHTML = html + groups.join("");
}

// ─── MBTI 渲染 ─────────────────────────────────────────────────────────
function renderMBTILayer(report) {
  const mbti = report.mbti_analysis || {};
  if (!mbti.type) return;

  const conf = mbti.meta?.confidence || "low";
  const confBadge = document.getElementById("mbtiConfidence");
  if (confBadge) {
    confBadge.textContent = conf === "high" ? "高置信" : conf === "medium" ? "中置信" : "低置信";
    confBadge.className = `source-badge confidence-${conf}`;
  }

  const typeBadge = document.getElementById("mbtiTypeBadge");
  if (typeBadge) {
    typeBadge.textContent = mbti.type;
    typeBadge.className = `mbti-type-badge mbti-${mbti.type.toLowerCase().replace(/x/g, "neutral")}`;
  }

  const typeDesc = document.getElementById("mbtiTypeDesc");
  if (typeDesc) typeDesc.textContent = mbti.type_description || "认知风格类型";

  // 冲突列表现在由 renderAllConflicts 统一处理
  const conflictsEl = document.getElementById("mbtiConflicts");
  if (conflictsEl) {
    const conflicts = mbti.conflicts || [];
    if (conflicts.length === 0) {
      conflictsEl.innerHTML = '<div class="mbti-no-conflict">✓ DISC 与 MBTI 无明显冲突</div>';
    } else {
      conflictsEl.innerHTML = `<div class="conflict-mini-note">共检测到 <strong>${conflicts.length}</strong> 项跨模型冲突，详见下方「跨模型冲突」区域。</div>`;
    }
  }

  const dimensions = mbti.dimensions || {};
  renderMBTIDimension("E_I", dimensions.E_I || {});
  renderMBTIDimension("N_S", dimensions.N_S || {});
  renderMBTIDimension("T_F", dimensions.T_F || {});
  renderMBTIDimension("J_P", dimensions.J_P || {});

  const followupsEl = document.getElementById("mbtiFollowups");
  if (followupsEl) {
    const qs = mbti.follow_up_questions || [];
    followupsEl.innerHTML = qs.length === 0
      ? '<div class="question-item">暂无追问建议</div>'
      : qs.map((q) => `<div class="question-item"><strong>${safeText(q.question, TEXT.na)}</strong><div>${safeText(q.purpose, "")}</div></div>`).join("");
  }
}

function renderMBTIDimension(dimKey, dimData) {
  const pref = dimData.preference || "-";
  const summary = dimData.summary || "等待分析";
  const evidence = dimData.evidence || {};
  const scores = dimData.scores || {};
  const id = `mbti${dimKey.replace("_", "")}`;

  const badgeEl = document.getElementById(id);
  if (badgeEl) {
    badgeEl.textContent = pref;
    badgeEl.className = `mbti-pref-badge pref-${pref.toLowerCase()}`;
  }

  const barWrapEl = document.getElementById(`${id}Bar`);
  if (barWrapEl) {
    const [lk, rk] = dimKey.split("_");
    const ls = scores[lk] || 50;
    const rs = scores[rk] || 50;
    barWrapEl.innerHTML = `<div class="mbti-pref-labels"><span>${lk} ${ls}%</span><span>${rk} ${rs}%</span></div><div class="mbti-pref-bar"><div class="mbti-pref-fill left pref-${lk.toLowerCase()}" style="width:${ls}%"></div><div class="mbti-pref-fill right pref-${rk.toLowerCase()}" style="width:${rs}%"></div><div class="mbti-pref-center"></div></div>`;
  }

  const summaryEl = document.getElementById(`${id}Summary`);
  if (summaryEl) summaryEl.textContent = summary;

  const evEl = document.getElementById(`${id}Evidence`);
  if (evEl) {
    const [lk, rk] = dimKey.split("_");
    evEl.innerHTML = `<div class="mbti-ev-section"><strong>${lk} 型证据:</strong><ul>${(evidence[lk] || []).length ? evidence[lk].map((e) => `<li>${e}</li>`).join("") : "<li>暂无</li>"}</ul></div><div class="mbti-ev-section"><strong>${rk} 型证据:</strong><ul>${(evidence[rk] || []).length ? evidence[rk].map((e) => `<li>${e}</li>`).join("") : "<li>暂无</li>"}</ul></div>`;
  }
}

// ─── BigFive 面板 ────────────────────────────────────────────────────────
const BF_LABELS = {
  O: { label: "开放性 O",  desc: "好奇、探索、创造力" },
  C: { label: "尽责性 C",  desc: "自律、计划、可靠性" },
  E: { label: "外向性 E",  desc: "活力、社交、主动" },
  A: { label: "宜人性 A",  desc: "信任、合作、同理心" },
  N: { label: "神经质 N",  desc: "情绪波动、忧虑（N高=不稳定）" },
};

function _normBf(raw) {
  try {
    const v = Number(raw);
    if (!Number.isFinite(v)) return 0.0;
    return v > 1.0 ? v : v * 100;   // 兼容 0~1 也兼容 0~100
  } catch { return 0.0; }
}

function renderBigFivePanel(report) {
  const bf = report.bigfive_analysis;
  const llmBf = report.llm_bigfive_analysis;
  let scores = {};

  if (llmBf && llmBf.scores) {
    scores = llmBf.scores;
  } else if (bf && bf.scores) {
    scores = bf.scores;
  }

  const container = document.getElementById("bigfiveCards");
  if (!container) return;

  const hasData = Object.keys(scores).length > 0;
  if (!hasData) {
    container.innerHTML = `<div class="panel-empty-note">暂无 BigFive 分析数据（请使用「深度分析」模式）</div>`;
    return;
  }

  container.innerHTML = Object.entries(BF_LABELS).map(([key, meta]) => {
    const raw = scores[key] ?? scores[key.toLowerCase()];
    const pct = Math.round(_normBf(raw));
    const band = pct >= 65 ? "high" : pct >= 40 ? "medium" : "low";
    const bandLabel = band === "high" ? "高" : band === "medium" ? "中" : "低";
    const isN = key === "N";
    const barStyle = isN
      ? (pct > 60 ? "background:var(--amber)" : "background:linear-gradient(90deg,var(--success),var(--amber))")
      : "background:linear-gradient(90deg,var(--primary),var(--secondary))";
    return `<div class="bf-row">
      <div class="bf-label"><strong>${meta.label}</strong><small>${meta.desc}</small></div>
      <div class="bf-bar-wrap"><div class="bf-bar-fill ${isN ? "inverted" : ""}" style="width:${pct}%;${barStyle}"></div></div>
      <div class="bf-score"><strong>${pct}</strong><span class="risk-badge ${riskLevelClass(bandLabel)}">${bandLabel}</span></div>
    </div>`;
  }).join("");
}

// ─── 九型人格面板 ────────────────────────────────────────────────────────
const ENNG_META = {
  "1": { label: "1号", name: "改革者", desc: "原则性、完美导向", color: "var(--amber)" },
  "2": { label: "2号", name: "助人者", desc: "热情、慷慨、渴望被需要", color: "var(--success)" },
  "3": { label: "3号", name: "成就者", desc: "目标导向、追求成功", color: "var(--risk)" },
  "4": { label: "4号", name: "自我型", desc: "情感深度、渴望独特", color: "var(--secondary)" },
  "5": { label: "5号", name: "探索者", desc: "洞察、知识导向、独立", color: "var(--cyan)" },
  "6": { label: "6号", name: "忠诚者", desc: "审慎、寻求安全、忠诚", color: "var(--amber)" },
  "7": { label: "7号", name: "享乐者", desc: "乐观、活跃、追求多元", color: "var(--i-color)" },
  "8": { label: "8号", name: "保护者", desc: "自信、掌控、保护他人", color: "var(--risk)" },
  "9": { label: "9号", name: "和平者", desc: "平和、接纳、避免冲突", color: "var(--s-color)" },
};

function _resolveEnng(result) {
  if (!result) return null;
  if (result.top_two_types && result.top_two_types.length) return result.top_two_types;
  if (result.top_types && result.top_types.length) return result.top_types;
  // 兜底：直接用 primary_type
  const t = result.primary_type;
  if (t) {
    return [{
      type_number: String(t.type_number ?? t.type ?? ""),
      score: Number(t.raw_score ?? t.score ?? 50),
      label: String(t.label ?? ""),
    }];
  }
  return null;
}

function renderEnneagramPanel(report) {
  const local = report.enneagram_analysis;
  const llm = report.llm_enneagram_analysis;
  const combined = { ...(local || {}), ...(llm || {}) };
  const types = _resolveEnng(combined);

  const container = document.getElementById("enneagramCards");
  if (!container) return;

  if (!types || types.length === 0) {
    container.innerHTML = `<div class="panel-empty-note">暂无九型人格数据（请使用「深度分析」模式）</div>`;
    return;
  }

  const primary = types[0];
  const pMeta = ENNG_META[String(primary?.type_number || primary?.type || "")] || ENNG_META["1"];
  const pScore = primary?.score || primary?.raw_score || 50;
  const pPct = Math.round(Number(pScore));
  const pBand = pPct >= 65 ? "high" : pPct >= 45 ? "medium" : "low";

  const others = types.slice(1, 3).map((t) => {
    const m = ENNG_META[String(t?.type_number || t?.type || "")] || { label: String(t?.type_number || t?.type || "?"), name: "", desc: "" };
    const s = Math.round(Number(t?.score || t?.raw_score || 50));
    return `<div class="enng-other-row">
      <span class="enng-type-chip" style="background:${m.color}22;color:${m.color}">${m.label} ${m.name}</span>
      <span class="risk-badge ${riskLevelClass(s >= 60 ? "高" : s >= 45 ? "中" : "低")}">${s}分</span>
    </div>`;
  }).join("");

  container.innerHTML = `
    <div class="enng-primary-row">
      <div class="enng-primary-badge" style="background:${pMeta.color}18;color:${pMeta.color}">
        <div class="enng-primary-type">${pMeta.label}</div>
        <div class="enng-primary-name">${pMeta.name}</div>
      </div>
      <div class="enng-primary-info">
        <div class="enng-primary-desc">${pMeta.desc}</div>
        <div class="bf-bar-wrap short"><div class="bf-bar-fill" style="width:${pPct}%;background:${pMeta.color}"></div></div>
        <div class="enng-primary-score"><span class="risk-badge ${riskLevelClass(pBand)}">${pBand === "high" ? "高" : pBand === "medium" ? "中" : "低"}</span><span>${pPct} 分</span></div>
      </div>
    </div>
    ${others ? `<div class="enng-others-wrap">${others}</div>` : ""}
    ${llm?.cross_model_notes?.length ? `<div class="enng-cross-note">${safeText(llm.cross_model_notes[0], "")}</div>` : ""}
  `;
}

// ─── STAR 结构面板 ────────────────────────────────────────────────────────
function renderSTARPanel(report) {
  const star = report.star_analysis;
  const f = report.atomic_features || {};
  const DIM_META = [
    { key: "S", name: "情境 S", color: "var(--d-color)", feat: "star_s_score" },
    { key: "T", name: "任务 T", color: "var(--i-color)", feat: "star_t_score" },
    { key: "A", name: "行动 A", color: "var(--s-color)", feat: "star_a_score" },
    { key: "R", name: "结果 R", color: "var(--c-color)", feat: "star_r_score" },
  ];

  const container = document.getElementById("starCards");
  if (!container) return;

  // 优先用 star_analysis.dimension_scores，否则用原子特征降级
  const rawDs = (star && typeof star === "object" && star.dimension_scores) ? star.dimension_scores : {};
  const getDim = (key) => {
    const cell = rawDs[key] || rawDs[key.toLowerCase()];
    if (cell && typeof cell === "object") {
      const sc = Number(cell.score);
      if (Number.isFinite(sc)) {
        return { pct: Math.round(sc <= 1 ? sc * 100 : sc), band: cell.band || (sc >= 0.75 ? "high" : sc >= 0.5 ? "medium" : "low"), note: safeText(cell.interpretation, "") };
      }
    }
    return null;
  };

  const rows = DIM_META.map(({ key, name, color, feat }) => {
    const d = getDim(key);
    if (d) {
      const bandLabel = d.band === "high" ? "高" : d.band === "medium" ? "中" : "低";
      return `<div class="star-dim-card ${d.band}">
        <div class="star-dim-head">
          <strong style="color:${color}">${name}</strong>
          <span class="risk-badge ${riskLevelClass(bandLabel)}">${bandLabel}</span>
        </div>
        <div class="bf-bar-wrap"><div class="bf-bar-fill" style="width:${d.pct}%;background:${color}"></div></div>
        <div class="star-dim-meta"><span>${d.pct} 分</span><span>${d.note}</span></div>
      </div>`;
    }
    // 降级到原子特征
    const rawFeat = Number(f[feat]) || 0;
    const pct = Math.round(rawFeat <= 1 ? rawFeat * 100 : rawFeat);
    const band = pct >= 75 ? "high" : pct >= 50 ? "medium" : "low";
    const bandLabel = band === "high" ? "高" : band === "medium" ? "中" : "低";
    return `<div class="star-dim-card ${band}">
      <div class="star-dim-head"><strong style="color:${color}">${name}</strong><span class="risk-badge ${riskLevelClass(bandLabel)}">${bandLabel}</span></div>
      <div class="bf-bar-wrap"><div class="bf-bar-fill" style="width:${pct}%;background:${color}"></div></div>
      <div class="star-dim-meta"><span>${pct} 分</span><span>原子特征降级展示</span></div>
    </div>`;
  }).join("");

  const defects = (star?.defects || []).slice(0, 3);
  const defectHtml = defects.length ? `<div class="star-defects-wrap">${defects.map((d) => {
    const sc = d.severity === "high" ? "high" : d.severity === "medium" ? "medium" : "low";
    return `<div class="star-defect-chip ${sc}"><span class="risk-badge ${sc}">${d.severity || "?"}</span>${safeText(d.label || d.defect_id, "")}</div>`;
  }).join("")}</div>` : "";

  container.innerHTML = rows + defectHtml || `<div class="panel-empty-note">暂无 STAR 结构数据</div>`;
}

// ─── 跨模型映射面板 ────────────────────────────────────────────────────────
function renderMappingPanel(report) {
  const container = document.getElementById("mappingCards");
  if (!container) return;

  const mapping = report.personality_mapping;
  if (!mapping || typeof mapping !== "object") {
    container.innerHTML = `<div class="panel-empty-note">暂无跨模型人格映射数据（请使用「深度分析」模式）</div>`;
    return;
  }

  const profile = mapping.integrated_personality_profile || mapping;
  const primary = safeText(profile.primary_style_label, "");
  const primaryDesc = safeText(profile.primary_style_description, "");

  // 九型综合
  const enngInt = profile.enneagram_integration || {};
  const bfInt = profile.bigfive_integration || {};
  const discInt = profile.disc_integration || {};
  const enngLabel = safeText(enngInt.dominant_type, "");
  const bfLabel = safeText(bfInt.dominant_trait, "");
  const discLabel = safeText(discInt.dominant_style, "");

  // 置信度调整
  const adj = (mapping.confidence_adjustments || []).slice(0, 4);
  const adjHtml = adj.length ? adj.map((a) => {
    const dirIcon = a.direction === "up" ? "↑" : a.direction === "down" ? "↓" : "→";
    return `<div class="adj-item ${a.direction}">
      <span class="adj-icon">${dirIcon}</span>
      <div><strong>${safeText(a.target, "")}</strong> <span>${a.amount || ""}</span>
      <p>${safeText(a.reason, "")}</p></div>
    </div>`;
  }).join("") : "";

  container.innerHTML = `
    ${primary ? `<div class="mapping-primary"><strong>综合画像</strong><p>${primary}</p><p class="mapping-primary-desc">${primaryDesc}</p></div>` : ""}
    <div class="mapping-tags-row">
      ${discLabel ? `<div class="mapping-tag disc-tag">DISC <strong>${discLabel}</strong></div>` : ""}
      ${bfLabel ? `<div class="mapping-tag bf-tag">BigFive <strong>${bfLabel}</strong></div>` : ""}
      ${enngLabel ? `<div class="mapping-tag enng-tag">九型 <strong>${enngLabel}</strong></div>` : ""}
    </div>
    ${adjHtml ? `<div class="mapping-adj-section"><strong>置信度调整</strong>${adjHtml}</div>` : ""}
  ` || `<div class="panel-empty-note">暂无跨模型映射数据</div>`;
}

// ─── 深度人格总面板 ───────────────────────────────────────────────────
function renderPersonalitySection(report) {
  renderBigFivePanel(report);
  renderEnneagramPanel(report);
  renderSTARPanel(report);
  renderMappingPanel(report);
}

// ─── 主渲染入口 ─────────────────────────────────────────────────────────────
function renderReport(report) {
  const primary = getPrimaryAnalysis(report);
  const isFull = getCurrentMode() === "full";

  // DISC 核心
  renderDecisionLayer(report, primary.analysis, primary.source);
  renderMetricsLayer(report, primary.analysis);
  renderWorkflow(report);
  renderInterviewOverview(report);
  renderDetailedLayer(report, primary.analysis, primary.source);

  // MBTI（仅完整模式）
  const mbtiSection = document.getElementById("mbtiDashboardSection");
  if (mbtiSection) mbtiSection.classList.toggle("hidden", !isFull);
  if (isFull) renderMBTILayer(report);

  // 统一冲突面板（包含 MBTI + BigFive + Enneagram 冲突，仅完整模式）
  const conflictSection = document.getElementById("conflictSection");
  if (conflictSection) conflictSection.classList.toggle("hidden", !isFull);
  if (isFull) renderAllConflicts(report);

  // 深度人格面板（仅在完整分析模式展示）
  const personalitySection = document.getElementById("personalitySection");
  if (personalitySection) {
    personalitySection.style.display = isFull ? "" : "none";
    if (isFull) renderPersonalitySection(report);
  }

  statusEl.textContent = report.llm_status?.enabled
    ? `解析模型：${safeText(report.llm_status.parser_model)} / 主分析模型：${safeText(report.llm_status.analysis_model)}${report.llm_status.personality_model ? ` / 人格模型：${safeText(report.llm_status.personality_model)}` : ""}`
    : primary.source;
  lastReport = report;
}

// ─── API 调用 ──────────────────────────────────────────────────────────────
async function loadSampleLibrary() {
  try {
    const resp = await fetch("/samples/index.json");
    if (!resp.ok) throw new Error(TEXT.sampleLoadFailed);
    sampleLibrary = await resp.json();
    sampleSelectEl.innerHTML = [`<option value="">${TEXT.selectSample}</option>`].concat(
      sampleLibrary.map((item) => `<option value="${item.id}">${item.title}</option>`)
    ).join("");
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
  const id = sampleSelectEl.value;
  if (!id) { transcriptEl.value = DEFAULT_TRANSCRIPT; jobHintEl.value = "后端研发"; return; }
  const item = sampleLibrary.find((e) => e.id === id);
  if (!item) return;
  sampleBtn.disabled = true;
  sampleBtn.textContent = TEXT.loading;
  try {
    const resp = await fetch(`/samples/${item.filename}`);
    if (!resp.ok) throw new Error(TEXT.sampleTextLoadFailed);
    transcriptEl.value = await resp.text();
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
  const txt = transcriptEl.value.trim();
  if (!txt) { window.alert(TEXT.pasteTranscriptFirst); return; }
  lastPayload = { interview_transcript: txt, job_hint_optional: jobHintEl.value.trim() };
  hideError();
  showView("loading");
  const steps = getLoadingSteps();
  startLoadingSequence(steps);
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = getCurrentMode() === "full" ? TEXT.analyzingFull : TEXT.analyzing;
  try {
    const resp = await fetch(getAnalysisEndpoint(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(lastPayload),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || TEXT.requestFailed);
    stopLoadingSequence();
    renderReport(data);
    showView("result");
  } catch (err) {
    showError(err.message);
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = getCurrentMode() === "full" ? TEXT.runFull : TEXT.run;
  }
}

sampleBtn.addEventListener("click", fillSelectedSample);
analyzeBtn.addEventListener("click", runAnalysis);
retryBtn.addEventListener("click", () => { hideError(); if (lastPayload) runAnalysis(); });
backBtn.addEventListener("click", () => { hideError(); stopLoadingSequence(); showView("input"); });
editAgainBtn.addEventListener("click", () => { showView("input"); if (lastReport) statusEl.textContent = TEXT.sourceLocal; });

transcriptEl.value = DEFAULT_TRANSCRIPT;
jobHintEl.value = "后端研发";
renderLoading(0, LOADING_STEPS_QUICK);
showView("input");
initModeSelector();
updateAnalyzeBtnText();
>>>>>>> Stashed changes
loadSampleLibrary();
