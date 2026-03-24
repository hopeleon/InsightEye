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
  const star = report.star_analysis;
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
    setHtml("starCards", `<div class="list-item">${TEXT.na}</div>`);
  }
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
function renderReport(report) { const primary = getPrimaryAnalysis(report); resultsEl.classList.remove("hidden"); statusEl.textContent = report.llm_status?.enabled ? `\u89e3\u6790\u6a21\u578b\uff1a${report.llm_status.parser_model} / \u4e3b\u5206\u6790\u6a21\u578b\uff1a${report.llm_status.analysis_model}` : TEXT.defaultStatus; renderDecisionLayer(report, primary.analysis, primary.source); renderMetricsLayer(report, primary.analysis); renderPersonalitySecondary(report); renderWorkflow(report); renderInterviewOverview(report); renderDetailedLayer(report, primary.analysis, primary.source); }
async function loadSampleLibrary() { try { const response = await fetch("/samples/index.json"); if (!response.ok) throw new Error(TEXT.sampleLoadFailed); sampleLibrary = await response.json(); sampleSelectEl.innerHTML = [`<option value="">${TEXT.selectSample}</option>`].concat(sampleLibrary.map((item) => `<option value="${item.id}">${item.title}</option>`)).join(""); if (!defaultSampleLoaded && sampleLibrary.length) { sampleSelectEl.value = sampleLibrary[0].id; await fillSelectedSample(); defaultSampleLoaded = true; } } catch { sampleSelectEl.innerHTML = `<option value="">${TEXT.sampleLoadFailed}</option>`; } }
async function fillSelectedSample() { const selectedId = sampleSelectEl.value; if (!selectedId) { transcriptEl.value = DEFAULT_TRANSCRIPT; jobHintEl.value = "\u540e\u7aef\u7814\u53d1"; return; } const item = sampleLibrary.find((entry) => entry.id === selectedId); if (!item) return; sampleBtn.disabled = true; sampleBtn.textContent = TEXT.loading; try { const response = await fetch(`/samples/${item.filename}`); if (!response.ok) throw new Error(TEXT.sampleTextLoadFailed); transcriptEl.value = await response.text(); jobHintEl.value = item.job_hint || ""; } catch { transcriptEl.value = DEFAULT_TRANSCRIPT; jobHintEl.value = item.job_hint || "\u540e\u7aef\u7814\u53d1"; } finally { sampleBtn.disabled = false; sampleBtn.textContent = TEXT.fill; } }
sampleBtn.addEventListener("click", fillSelectedSample);
// /api/analyze/full：含大五/九型/STAR 本地规则；/api/analyze 仅 DISC，次要映射字段为 null
analyzeBtn.addEventListener("click", async () => { const interview_transcript = transcriptEl.value.trim(); if (!interview_transcript) { window.alert(TEXT.pasteTranscriptFirst); return; } analyzeBtn.disabled = true; analyzeBtn.textContent = TEXT.analyzing; try { const response = await fetch("/api/analyze/full", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ interview_transcript, job_hint_optional: jobHintEl.value.trim() }) }); const data = await response.json(); if (!response.ok) throw new Error(data.error || TEXT.requestFailed); renderReport(data); } catch (error) { window.alert(error.message); } finally { analyzeBtn.disabled = false; analyzeBtn.textContent = TEXT.run; } });
renderReport(DEFAULT_REPORT);
transcriptEl.value = DEFAULT_TRANSCRIPT;
jobHintEl.value = "\u540e\u7aef\u7814\u53d1";
loadSampleLibrary();
