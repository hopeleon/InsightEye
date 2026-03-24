const transcriptEl = document.getElementById("transcript");
const jobHintEl = document.getElementById("jobHint");
const sampleSelectEl = document.getElementById("sampleSelect");
const analyzeBtn = document.getElementById("analyzeBtn");
const sampleBtn = document.getElementById("sampleBtn");
const resultsEl = document.getElementById("results");
const statusEl = document.getElementById("status");

let sampleLibrary = [];
let defaultSampleLoaded = false;

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
};

const DISC_META = {
  D: { label: "D / \u7ea2\u8272", className: "d", style: "\u7ed3\u679c\u5bfc\u5411\u3001\u63a8\u8fdb\u76f4\u63a5" },
  I: { label: "I / \u9ec4\u8272", className: "i", style: "\u5916\u653e\u8868\u8fbe\u3001\u611f\u67d3\u5e26\u52a8" },
  S: { label: "S / \u7eff\u8272", className: "s", style: "\u7a33\u5b9a\u534f\u4f5c\u3001\u8282\u594f\u5e73\u548c" },
  C: { label: "C / \u84dd\u8272", className: "c", style: "\u7ed3\u6784\u6e05\u6670\u3001\u6ce8\u91cd\u7ec6\u8282" },
};

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
  llm_analysis: null,
  llm_status: { enabled: false, parser_model: "gpt-5-mini", analysis_model: "gpt-5.4", parser_error: null, analysis_error: null, parser_output_available: false },
  workflow: {
    version: "v0.2-preview",
    mode: "disc",
    stage_trace: [
      { stage: "parse_stage", status: "completed", detail: "\u5df2\u62c6\u5206\u4e3a 2 \u8f6e\u95ee\u7b54" },
      { stage: "feature_stage", status: "completed", detail: "\u5df2\u63d0\u53d6\u539f\u5b50\u7279\u5f81" },
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
  const topLabel = DISC_META[top?.key]?.label || TEXT.na;
  const topValue = top?.value || 0;
  return `<div class="disc-pie" style="background: conic-gradient(${stops.join(", ")});"><div class="disc-pie-center"><div><strong>${topValue}</strong><span>${topLabel}</span></div></div></div><div class="disc-pie-caption">\u57fa\u4e8e\u5f53\u524d\u5206\u503c\u5206\u5e03\u8ba1\u7b97\u7684 D / I / S / C \u76f8\u5bf9\u5360\u6bd4\u3002</div>`;
}
function renderDimensionCards(targetId, analysis) { setHtml(targetId, Object.entries(analysis || {}).map(([dim, item]) => `<div class="dimension-card"><h3>${dim} - ${safeText(item.score, 0)}</h3><p>${safeText(item.summary)}</p><strong>\u652f\u6301\u8bc1\u636e</strong><ul>${(item.evidence_for || []).slice(0, 3).map((entry) => `<li>${entry}</li>`).join("") || "<li>\u6682\u65e0</li>"}</ul><strong>\u53cd\u8bc1\u7ebf\u7d22</strong><ul>${(item.evidence_against || []).slice(0, 2).map((entry) => `<li>${entry}</li>`).join("") || "<li>\u6682\u65e0</li>"}</ul></div>`).join("") || "<div class='list-item'>\u6682\u65e0\u7ef4\u5ea6\u5206\u6790</div>"); }
function renderWorkflow(report) {
  const workflow = report.workflow || {};
  const stageTrace = workflow.stage_trace || [];
  setText("workflowStageTop", String(stageTrace.length));
  setHtml("workflowStages", createList(stageTrace, (item) => `<div class="workflow-stage"><div class="workflow-stage-meta"><strong>${safeText(item.stage)}</strong><span>${safeText(item.detail, TEXT.noDetail)}</span></div><span class="workflow-stage-status ${riskLevelClass(item.status)}">${safeText(item.status)}</span></div>`, "\u6682\u65e0\u9636\u6bb5\u8f68\u8ff9"));
  const evidence = workflow.disc_evidence || {};
  setHtml("workflowEvidence", `<div class="workflow-tile"><strong>\u7ef4\u5ea6\u6392\u5e8f</strong><div>${safeText((evidence.ranking || []).join(" / "), TEXT.na)}</div></div><div class="workflow-tile"><strong>\u5206\u503c\u6458\u8981</strong><div>${Object.entries(evidence.scores || {}).map(([k, v]) => `${k}: ${v}`).join(" | ") || TEXT.na}</div></div><div class="workflow-tile"><strong>\u8bc1\u636e\u4eae\u70b9</strong><div>${(evidence.feature_highlights || []).join("\uff1b") || TEXT.na}</div></div>`);
  const masking = workflow.masking_assessment || {};
  setHtml("workflowMasking", `<div class="workflow-tile"><strong>\u5173\u952e\u7f3a\u9677</strong><div>${(masking.critical_findings || []).map((item) => item.finding).join("\uff1b") || TEXT.na}</div></div><div class="workflow-tile"><strong>\u8bc1\u636e\u7f3a\u53e3</strong><div>${(masking.evidence_gaps || []).join("\uff1b") || TEXT.na}</div></div><div class="workflow-tile"><strong>\u5f55\u7528\u98ce\u9669</strong><div>${(masking.hire_risks || []).join("\uff1b") || TEXT.na}</div></div>`);
  const decision = workflow.decision_payload || {};
  setHtml("workflowDecision", `<div class="workflow-tile"><strong>\u51b3\u7b56\u603b\u7ed3</strong><p>${safeText(decision.decision_summary)}</p></div><div class="workflow-tile"><strong>\u98ce\u9669\u7ed3\u8bba</strong><p>${safeText(decision.risk_summary)}</p></div><div class="workflow-tile"><strong>\u63a8\u8350\u52a8\u4f5c</strong><p>${safeText(decision.recommended_action)}</p></div>`);
}
function renderDecisionLayer(report, analysis, source) { setText("analysisSource", source); setText("analysisSourceTop", source); setText("candidateStyle", buildStyleSummary(analysis)); setText("candidateStyleNote", buildStyleNote(analysis)); setText("riskHeadline", buildRiskHeadline(analysis)); setText("riskDetail", buildRiskDetail(analysis)); setText("nextAction", buildNextAction(analysis)); setText("nextActionDetail", buildNextActionDetail(analysis)); setText("riskLevelTop", safeText(analysis.meta?.impression_management_risk, "\u672a\u5224\u5b9a")); setHtml("topFollowups", createList((analysis.follow_up_questions || []).slice(0, 3), (item) => `<div class="question-item"><strong>${safeText(item.question)}</strong><div>${safeText(item.purpose)}</div></div>`, TEXT.noFollowup)); }
function renderMetricsLayer(report, analysis) { setHtml("discPie", renderDiscPie(analysis)); setHtml("discBars", renderDiscBars(analysis)); const riskClass = riskLevelClass(analysis.meta?.impression_management_risk); setHtml("riskMeter", `<div class="risk-head"><strong>${buildRiskHeadline(analysis)}</strong><span class="risk-badge ${riskClass}">${safeText(analysis.meta?.impression_management_risk, "\u4f4e")}</span></div><p class="card-note">${buildRiskDetail(analysis)}</p>`); setHtml("riskTags", createList([...(analysis.hire_risks || []), ...(analysis.evidence_gaps || []), ...((analysis.meta?.notes || []).slice(0, 2))].slice(0, 4), (note) => `<div class="tag">${note}</div>`, "\u6682\u65e0\u98ce\u9669\u6807\u7b7e")); const capabilityTags = buildCapabilityTags(report); setHtml("capabilityTags", capabilityTags.map((tag) => `<div class="tag">${tag}</div>`).join("")); setHtml("capabilitySummary", `${capabilityTags.join(" / ")}\u3002${TEXT.validateEvidence}`); }
function renderInterviewOverview(report) { setText("turnCountTop", String(report.input_overview?.turn_count || 0)); setHtml("overview", [`<div class="chip">\u5c97\u4f4d\u731c\u6d4b\uff1a${report.interview_map?.job_inference?.value || TEXT.unknown}</div>`,`<div class="chip">\u95ee\u7b54\u8f6e\u6b21\uff1a${report.input_overview?.turn_count || 0}</div>`,`<div class="chip">\u5019\u9009\u4eba\u5b57\u6570\uff1a${report.input_overview?.candidate_char_count || 0}</div>`,`<div class="chip">\u6837\u672c\u8d28\u91cf\uff1a${safeText(report.llm_analysis?.meta?.sample_quality || report.disc_analysis?.meta?.sample_quality)}</div>`,`<div class="chip">\u89e3\u6790\u6765\u6e90\uff1a${safeText(report.interview_map?.parse_source)}</div>`].join("")); setHtml("turns", createList(report.interview_map?.turns, (turn) => `<div class="turn-item"><div class="type">\u7b2c ${turn.turn_id} \u8f6e \u00b7 ${safeText(turn.question_type)}</div><p><strong>\u95ee\u9898\uff1a</strong>${safeText(turn.question, TEXT.na)}</p><p><strong>\u56de\u7b54\u6458\u8981\uff1a</strong>${safeText(turn.answer_summary)}</p></div>`, "\u6682\u65e0\u95ee\u7b54\u6620\u5c04")); }
function renderDetailedLayer(report, analysis, source) { renderDimensionCards("dimensions", analysis.dimension_analysis || {}); setHtml("criticalFindings", createList(analysis.critical_findings, (item) => `<div class="list-item"><div class="type">${safeText(item.severity)}</div><p><strong>${safeText(item.finding)}</strong></p><p>${(item.basis || []).join("\uff1b") || "\u6682\u65e0\u4f9d\u636e"}</p><p>${safeText(item.impact, "\u6682\u65e0\u5f71\u54cd\u8bf4\u660e")}</p></div>`, "\u6682\u65e0\u5173\u952e\u7f3a\u9677")); setHtml("evidenceGaps", createList(analysis.evidence_gaps, (item) => `<div class="list-item"><p>${safeText(item)}</p></div>`, "\u6682\u65e0\u8bc1\u636e\u7f3a\u53e3")); setHtml("features", createList(report.atomic_features ? [{ label: "STAR \u5b8c\u6574\u5ea6", value: `${Math.round((report.atomic_features.star_structure_score || 0) * 100)}%` },{ label: "\u903b\u8f91\u8fde\u63a5\u8bcd\u6bd4\u4f8b", value: report.atomic_features.logical_connector_ratio },{ label: "\u52a8\u4f5c\u52a8\u8bcd\u6bd4\u4f8b", value: report.atomic_features.action_verbs_ratio },{ label: "\u6545\u4e8b\u4e30\u5bcc\u5ea6", value: `${Math.round((report.atomic_features.story_richness_score || 0) * 100)}%` },{ label: "\u4e2a\u4eba / \u56e2\u961f\u53d6\u5411", value: report.atomic_features.self_vs_team_orientation },{ label: "\u95ee\u9898 / \u4eba\u9645\u53d6\u5411", value: report.atomic_features.problem_vs_people_focus }] : [], (item) => `<div class="feature-item"><strong>${item.label}</strong><div>${item.value}</div></div>`, "\u6682\u65e0\u539f\u5b50\u7279\u5f81")); setHtml("hypotheses", createList(analysis.behavioral_hypotheses, (item) => `<div class="list-item"><div class="type">${safeText(item.strength)}</div><p>${safeText(item.hypothesis)}</p><p>${(item.basis || []).join("\uff1b")}</p></div>`, "\u6682\u65e0\u884c\u4e3a\u5047\u8bbe")); setHtml("followups", createList(analysis.follow_up_questions, (item) => `<div class="list-item"><div class="type">${safeText(item.target_dimension)}</div><p>${safeText(item.question)}</p><p>${safeText(item.purpose)}</p></div>`, "\u6682\u65e0\u8ffd\u95ee\u5efa\u8bae")); const llmStatus = report.llm_status?.enabled ? [`\u5f53\u524d\u4e3b\u89c6\u56fe\uff1a${source}`,`\u89e3\u6790\u6a21\u578b\uff1a${report.llm_status.parser_model}`,`\u4e3b\u5206\u6790\u6a21\u578b\uff1a${report.llm_status.analysis_model}`,report.llm_status.parser_error ? `\u89e3\u6790\u9519\u8bef\uff1a${report.llm_status.parser_error}` : "\u89e3\u6790\u6a21\u578b\u53ef\u7528\u3002",report.llm_status.analysis_error ? `\u5206\u6790\u9519\u8bef\uff1a${report.llm_status.analysis_error}` : "\u5206\u6790\u6a21\u578b\u53ef\u7528\u3002"].join("<br />") : TEXT.defaultStatus; setHtml("llmStatus", llmStatus); setText("llmOutput", JSON.stringify(report.llm_analysis || report.disc_analysis, null, 2)); }
function renderReport(report) { const primary = getPrimaryAnalysis(report); resultsEl.classList.remove("hidden"); statusEl.textContent = report.llm_status?.enabled ? `\u89e3\u6790\u6a21\u578b\uff1a${report.llm_status.parser_model} / \u4e3b\u5206\u6790\u6a21\u578b\uff1a${report.llm_status.analysis_model}` : TEXT.defaultStatus; renderDecisionLayer(report, primary.analysis, primary.source); renderMetricsLayer(report, primary.analysis); renderWorkflow(report); renderInterviewOverview(report); renderDetailedLayer(report, primary.analysis, primary.source); }
async function loadSampleLibrary() { try { const response = await fetch("/samples/index.json"); if (!response.ok) throw new Error(TEXT.sampleLoadFailed); sampleLibrary = await response.json(); sampleSelectEl.innerHTML = [`<option value="">${TEXT.selectSample}</option>`].concat(sampleLibrary.map((item) => `<option value="${item.id}">${item.title}</option>`)).join(""); if (!defaultSampleLoaded && sampleLibrary.length) { sampleSelectEl.value = sampleLibrary[0].id; await fillSelectedSample(); defaultSampleLoaded = true; } } catch { sampleSelectEl.innerHTML = `<option value="">${TEXT.sampleLoadFailed}</option>`; } }
async function fillSelectedSample() { const selectedId = sampleSelectEl.value; if (!selectedId) { transcriptEl.value = DEFAULT_TRANSCRIPT; jobHintEl.value = "\u540e\u7aef\u7814\u53d1"; return; } const item = sampleLibrary.find((entry) => entry.id === selectedId); if (!item) return; sampleBtn.disabled = true; sampleBtn.textContent = TEXT.loading; try { const response = await fetch(`/samples/${item.filename}`); if (!response.ok) throw new Error(TEXT.sampleTextLoadFailed); transcriptEl.value = await response.text(); jobHintEl.value = item.job_hint || ""; } catch { transcriptEl.value = DEFAULT_TRANSCRIPT; jobHintEl.value = item.job_hint || "\u540e\u7aef\u7814\u53d1"; } finally { sampleBtn.disabled = false; sampleBtn.textContent = TEXT.fill; } }
sampleBtn.addEventListener("click", fillSelectedSample);
analyzeBtn.addEventListener("click", async () => { const interview_transcript = transcriptEl.value.trim(); if (!interview_transcript) { window.alert(TEXT.pasteTranscriptFirst); return; } analyzeBtn.disabled = true; analyzeBtn.textContent = TEXT.analyzing; try { const response = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ interview_transcript, job_hint_optional: jobHintEl.value.trim() }) }); const data = await response.json(); if (!response.ok) throw new Error(data.error || TEXT.requestFailed); renderReport(data); } catch (error) { window.alert(error.message); } finally { analyzeBtn.disabled = false; analyzeBtn.textContent = TEXT.run; } });
renderReport(DEFAULT_REPORT);
transcriptEl.value = DEFAULT_TRANSCRIPT;
jobHintEl.value = "\u540e\u7aef\u7814\u53d1";
loadSampleLibrary();
