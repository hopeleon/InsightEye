const transcriptEl = document.getElementById("transcript");
const jobHintEl = document.getElementById("jobHint");
const sampleSelectEl = document.getElementById("sampleSelect");
const analyzeBtn = document.getElementById("analyzeBtn");
const sampleBtn = document.getElementById("sampleBtn");
const resultsEl = document.getElementById("results");
const statusEl = document.getElementById("status");

let sampleLibrary = [];

const DISC_META = {
  D: { label: "D / 红色", className: "d", style: "结果导向、推进感强" },
  I: { label: "I / 黄色", className: "i", style: "表达外放、感染力强" },
  S: { label: "S / 绿色", className: "s", style: "稳定协作、节奏平稳" },
  C: { label: "C / 蓝色", className: "c", style: "结构清晰、谨慎严谨" },
};

function createList(items, renderer, empty = "暂无") {
  if (!items || !items.length) return `<div class='list-item'>${empty}</div>`;
  return items.map(renderer).join("");
}

function setHtml(id, html) {
  document.getElementById(id).innerHTML = html;
}

function safeText(value, fallback = "暂无") {
  if (value === null || value === undefined || value === "") return fallback;
  return value;
}

function normalizeScores(scores) {
  const normalized = {
    D: Number(scores?.D || 0),
    I: Number(scores?.I || 0),
    S: Number(scores?.S || 0),
    C: Number(scores?.C || 0),
  };
  const total = normalized.D + normalized.I + normalized.S + normalized.C || 1;
  return { scores: normalized, total };
}

function rankDimensions(scores) {
  return Object.entries(scores || {})
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => ({ key, value }));
}

function getPrimaryAnalysis(report) {
  if (report.llm_analysis && report.llm_analysis.scores) {
    return {
      source: "LLM 主分析",
      analysis: report.llm_analysis,
    };
  }
  return {
    source: "本地规则分析",
    analysis: report.disc_analysis,
  };
}

function riskLevelClass(level) {
  const lowered = String(level || "low").toLowerCase();
  if (lowered.includes("high") || lowered.includes("高")) return "high";
  if (lowered.includes("medium") || lowered.includes("中")) return "medium";
  return "low";
}

function buildStyleSummary(analysis) {
  const ranking = rankDimensions(analysis.scores);
  const top = ranking[0];
  const second = ranking[1];
  const topLabel = DISC_META[top?.key]?.style || "风格未明";
  const secondLabel = DISC_META[second?.key]?.style || "";
  if (!top || !second) return "风格信号不足，需要更多样本。";
  return `整体偏 ${topLabel}，同时带有 ${secondLabel} 的表达特征。`;
}

function buildRiskHeadline(analysis) {
  const risk = safeText(analysis.meta?.impression_management_risk, "low");
  const level = riskLevelClass(risk);
  if (level === "high") return "存在较高包装或真实性风险";
  if (level === "medium") return "存在一定包装倾向，建议验证细节";
  return "风险可控，当前样本未见明显真实性问题";
}

function buildRiskDetail(analysis) {
  return (analysis.meta?.notes || []).slice(0, 2).join("；") || "当前未出现强冲突信号，但仍建议通过追问验证关键细节。";
}

function buildNextAction(analysis) {
  const risk = riskLevelClass(analysis.meta?.impression_management_risk);
  const confidence = String(analysis.meta?.confidence || "").toLowerCase();
  if (risk === "high") return "建议继续面试，但重点核验真实性与执行细节";
  if (confidence.includes("low") || confidence.includes("低")) return "建议补充样本，再判断是否继续深挖";
  return "建议继续深入面试，重点验证最强风格背后的实际能力";
}

function buildNextActionDetail(analysis) {
  const topQuestion = analysis.follow_up_questions?.[0]?.question;
  return topQuestion ? `优先追问：${topQuestion}` : "优先要求对方展开关键动作、决策依据与结果证据。";
}

function buildCapabilityTags(report, analysis) {
  const features = report.atomic_features || {};
  const tags = [];
  if ((features.star_structure_score || 0) >= 0.75) tags.push("结构完整");
  else if ((features.star_structure_score || 0) >= 0.5) tags.push("结构中等");
  else tags.push("结构偏弱");

  if ((features.logical_connector_ratio || 0) >= 0.015) tags.push("逻辑清晰");
  else tags.push("逻辑需验证");

  if ((features.story_richness_score || 0) >= 0.65) tags.push("细节较充足");
  else if ((features.story_richness_score || 0) >= 0.45) tags.push("细节一般");
  else tags.push("细节不足");

  if ((features.action_verbs_ratio || 0) >= 0.02) tags.push("行动表达较强");
  return tags;
}

function renderDiscBars(analysis) {
  const ranking = rankDimensions(analysis.scores);
  return ranking.map(({ key, value }) => `
    <div class="metric-bar">
      <div class="metric-bar-head">
        <span>${DISC_META[key]?.label || key}</span>
        <strong>${value}</strong>
      </div>
      <div class="bar-track">
        <div class="bar-fill ${DISC_META[key]?.className || ""}" style="width:${Math.max(8, value)}%"></div>
      </div>
    </div>
  `).join("");
}

function renderDimensionCards(targetId, analysis) {
  setHtml(
    targetId,
    Object.entries(analysis || {})
      .map(
        ([dim, item]) => `
          <div class="dimension-card">
            <h3>${dim} · ${safeText(item.score, 0)}</h3>
            <p>${safeText(item.summary)}</p>
            <strong>支持证据</strong>
            <ul>${(item.evidence_for || []).slice(0, 3).map((entry) => `<li>${entry}</li>`).join("") || "<li>暂无</li>"}</ul>
            <strong>反向证据</strong>
            <ul>${(item.evidence_against || []).slice(0, 2).map((entry) => `<li>${entry}</li>`).join("") || "<li>暂无</li>"}</ul>
          </div>
        `
      )
      .join("") || "<div class='list-item'>暂无维度分析</div>"
  );
}

async function loadSampleLibrary() {
  try {
    const response = await fetch("/samples/index.json");
    if (!response.ok) {
      throw new Error("样例库加载失败");
    }
    sampleLibrary = await response.json();
    sampleSelectEl.innerHTML = ['<option value="">请选择样例</option>']
      .concat(sampleLibrary.map((item) => `<option value="${item.id}">${item.title}</option>`))
      .join("");
  } catch (error) {
    sampleSelectEl.innerHTML = '<option value="">样例库加载失败</option>';
  }
}

async function fillSelectedSample() {
  const selectedId = sampleSelectEl.value;
  if (!selectedId) {
    window.alert("请先选择一个样例。");
    return;
  }
  const item = sampleLibrary.find((entry) => entry.id === selectedId);
  if (!item) {
    window.alert("未找到对应样例。");
    return;
  }
  sampleBtn.disabled = true;
  sampleBtn.textContent = "加载中...";
  try {
    const response = await fetch(`/samples/${item.filename}`);
    if (!response.ok) {
      throw new Error("样例文本加载失败");
    }
    transcriptEl.value = await response.text();
    jobHintEl.value = item.job_hint || "";
  } catch (error) {
    window.alert(error.message);
  } finally {
    sampleBtn.disabled = false;
    sampleBtn.textContent = "填充示例";
  }
}

function renderDecisionLayer(report, analysis, source) {
  document.getElementById("analysisSource").textContent = source;
  document.getElementById("candidateStyle").textContent = buildStyleSummary(analysis);
  document.getElementById("candidateStyleNote").textContent = safeText(analysis.overall_style_summary, "需要更多样本才能给出稳定判断。");
  document.getElementById("riskHeadline").textContent = buildRiskHeadline(analysis);
  document.getElementById("riskDetail").textContent = buildRiskDetail(analysis);
  document.getElementById("nextAction").textContent = buildNextAction(analysis);
  document.getElementById("nextActionDetail").textContent = buildNextActionDetail(analysis);

  setHtml(
    "topFollowups",
    createList((analysis.follow_up_questions || []).slice(0, 3), (item) => `
      <div class="question-item">
        <strong>${safeText(item.question)}</strong>
        <div>${safeText(item.purpose)}</div>
      </div>
    `, "暂无推荐追问")
  );
}

function renderMetricsLayer(report, analysis) {
  setHtml("discBars", renderDiscBars(analysis));

  const riskClass = riskLevelClass(analysis.meta?.impression_management_risk);
  setHtml(
    "riskMeter",
    `
      <div class="risk-head">
        <strong>${buildRiskHeadline(analysis)}</strong>
        <span class="risk-badge ${riskClass}">${safeText(analysis.meta?.impression_management_risk, "low")}</span>
      </div>
      <p class="decision-note">${buildRiskDetail(analysis)}</p>
    `
  );

  setHtml(
    "riskTags",
    createList((analysis.meta?.notes || []).slice(0, 3), (note) => `<div class="tag">${note}</div>`, "暂无风险标签")
  );

  const capabilityTags = buildCapabilityTags(report, analysis);
  setHtml("capabilityTags", capabilityTags.map((tag) => `<div class="tag">${tag}</div>`).join(""));
  setHtml(
    "capabilitySummary",
    `${capabilityTags.join(" / ")}。建议优先结合追问，确认这些标签是否有真实证据支撑。`
  );
}

function renderInterviewOverview(report) {
  setHtml(
    "overview",
    [
      `<div class="chip">岗位推测：${report.interview_map.job_inference.value}</div>`,
      `<div class="chip">轮次：${report.input_overview.turn_count}</div>`,
      `<div class="chip">候选人字数：${report.input_overview.candidate_char_count}</div>`,
      `<div class="chip">样本质量：${safeText(report.llm_analysis?.meta?.sample_quality || report.disc_analysis?.meta?.sample_quality)}</div>`,
      `<div class="chip">解析来源：${report.interview_map.parse_source}</div>`,
    ].join("")
  );

  setHtml(
    "turns",
    createList(report.interview_map.turns, (turn) => `
      <div class="turn-item">
        <div class="type">Turn ${turn.turn_id} · ${turn.question_type}</div>
        <p><strong>问题：</strong>${turn.question || "未显式标记"}</p>
        <p><strong>回答摘要：</strong>${turn.answer_summary}</p>
      </div>
    `)
  );
}

function renderDetailedLayer(report, analysis, source) {
  renderDimensionCards("dimensions", analysis.dimension_analysis || {});

  setHtml(
    "features",
    createList((report.atomic_features ? [
      { label: "STAR 完整度", value: `${Math.round((report.atomic_features.star_structure_score || 0) * 100)}%` },
      { label: "逻辑连接词密度", value: report.atomic_features.logical_connector_ratio },
      { label: "行动词密度", value: report.atomic_features.action_verbs_ratio },
      { label: "细节丰富度", value: `${Math.round((report.atomic_features.story_richness_score || 0) * 100)}%` },
      { label: "团队导向", value: report.atomic_features.self_vs_team_orientation },
      { label: "问题/人际焦点", value: report.atomic_features.problem_vs_people_focus },
    ] : []), (item) => `
      <div class="feature-item">
        <strong>${item.label}</strong>
        <div>${item.value}</div>
      </div>
    `)
  );

  setHtml(
    "hypotheses",
    createList(analysis.behavioral_hypotheses, (item) => `
      <div class="list-item">
        <div class="type">${item.strength}</div>
        <p>${safeText(item.hypothesis)}</p>
        <p>${(item.basis || []).join("；")}</p>
      </div>
    `, "暂无行为假设")
  );

  setHtml(
    "followups",
    createList(analysis.follow_up_questions, (item) => `
      <div class="list-item">
        <div class="type">${safeText(item.target_dimension)}</div>
        <p>${safeText(item.question)}</p>
        <p>${safeText(item.purpose)}</p>
      </div>
    `, "暂无追问建议")
  );

  const llmStatus = report.llm_status.enabled
    ? [
        `当前主视图来源：${source}`,
        `解析模型：${report.llm_status.parser_model}`,
        `主分析模型：${report.llm_status.analysis_model}`,
        report.llm_status.parser_error ? `解析失败：${report.llm_status.parser_error}` : "解析模型调用正常或可用。",
        report.llm_status.analysis_error ? `主分析失败：${report.llm_status.analysis_error}` : "主分析模型调用正常或可用。",
      ].join("<br />")
    : "当前未配置 OPENAI_API_KEY，主视图使用本地规则分析。";
  setHtml("llmStatus", llmStatus);
  document.getElementById("llmOutput").textContent = report.llm_analysis
    ? JSON.stringify(report.llm_analysis, null, 2)
    : JSON.stringify(report.disc_analysis, null, 2);
}

function renderReport(report) {
  const primary = getPrimaryAnalysis(report);
  resultsEl.classList.remove("hidden");
  statusEl.textContent = report.llm_status.enabled
    ? `解析：${report.llm_status.parser_model} / 主分析：${report.llm_status.analysis_model}`
    : "本地规则分析模式";

  renderDecisionLayer(report, primary.analysis, primary.source);
  renderMetricsLayer(report, primary.analysis);
  renderInterviewOverview(report);
  renderDetailedLayer(report, primary.analysis, primary.source);
}

sampleBtn.addEventListener("click", fillSelectedSample);

analyzeBtn.addEventListener("click", async () => {
  const interview_transcript = transcriptEl.value.trim();
  if (!interview_transcript) {
    window.alert("请输入整段面试文本。");
    return;
  }
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "分析中...";
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        interview_transcript,
        job_hint_optional: jobHintEl.value.trim(),
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "请求失败");
    }
    renderReport(data);
  } catch (error) {
    window.alert(error.message);
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "开始分析";
  }
});

loadSampleLibrary();
