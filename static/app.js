const transcriptEl = document.getElementById("transcript");
const jobHintEl = document.getElementById("jobHint");
const sampleSelectEl = document.getElementById("sampleSelect");
const analyzeBtn = document.getElementById("analyzeBtn");
const sampleBtn = document.getElementById("sampleBtn");
const resultsEl = document.getElementById("results");
const statusEl = document.getElementById("status");

let sampleLibrary = [];

const DISC_META = {
  D: { label: "D / Red", className: "d", style: "result-driven and forceful" },
  I: { label: "I / Yellow", className: "i", style: "expressive and outward-facing" },
  S: { label: "S / Green", className: "s", style: "steady and collaborative" },
  C: { label: "C / Blue", className: "c", style: "structured and detail-conscious" },
};

function createList(items, renderer, empty = "N/A") {
  if (!items || !items.length) return `<div class='list-item'>${empty}</div>`;
  return items.map(renderer).join("");
}

function setHtml(id, html) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = html;
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
}

function safeText(value, fallback = "N/A") {
  if (value === null || value === undefined || value === "") return fallback;
  return value;
}

function rankDimensions(scores) {
  return Object.entries(scores || {})
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => ({ key, value }));
}

function getPrimaryAnalysis(report) {
  if (report.llm_analysis && report.llm_analysis.scores) {
    return { source: "LLM primary analysis", analysis: report.llm_analysis };
  }
  return { source: "Local rules", analysis: report.disc_analysis };
}

function riskLevelClass(level) {
  const lowered = String(level || "low").toLowerCase();
  if (lowered.includes("high")) return "high";
  if (lowered.includes("medium")) return "medium";
  return "low";
}

function buildStyleSummary(analysis) {
  if (analysis.decision_summary) return analysis.decision_summary;
  const ranking = rankDimensions(analysis.scores);
  const top = ranking[0];
  const second = ranking[1];
  const topLabel = DISC_META[top?.key]?.style || "unclear style";
  const secondLabel = DISC_META[second?.key]?.style || "";
  const critical = analysis.critical_findings || [];
  const evidenceGaps = analysis.evidence_gaps || [];
  const highFinding = critical.find((item) => riskLevelClass(item.severity) === "high");
  const mediumFinding = critical.find((item) => riskLevelClass(item.severity) === "medium");

  if (!top || !second) return "Signals are still too weak to summarize this candidate.";
  if (highFinding) return `Surface style suggests ${topLabel}, but the stronger signal is: ${highFinding.finding}`;
  if (evidenceGaps.length) return `Style leans toward ${topLabel}, but the main blocker is: ${evidenceGaps[0]}`;
  if (mediumFinding) return `Style leans toward ${topLabel}, but ${mediumFinding.finding}`;
  return `Overall style leans ${topLabel}, with a secondary signal of ${secondLabel}.`;
}

function buildStyleNote(analysis) {
  if (analysis.overall_style_summary) return analysis.overall_style_summary;
  if (analysis.critical_findings?.length) {
    return analysis.critical_findings
      .slice(0, 2)
      .map((item) => `${item.finding}: ${safeText(item.impact)}`)
      .join(" ");
  }
  return "More samples are needed for a stable judgment.";
}

function buildRiskHeadline(analysis) {
  if (analysis.risk_summary) return analysis.risk_summary;
  const critical = analysis.critical_findings || [];
  if (critical.some((item) => riskLevelClass(item.severity) === "high")) return "High-priority weaknesses detected";
  const risk = safeText(analysis.meta?.impression_management_risk, "low");
  const level = riskLevelClass(risk);
  if (level === "high") return "High authenticity or impression-management risk";
  if (level === "medium") return "Some packaging risk; verify specifics";
  return "No major authenticity red flag yet";
}

function buildRiskDetail(analysis) {
  if (analysis.critical_findings?.length) {
    return analysis.critical_findings.slice(0, 2).map((item) => item.finding).join("; ");
  }
  return (analysis.meta?.notes || []).slice(0, 2).join("; ") || "No sharp conflict signal yet, but key details still need verification.";
}

function buildNextAction(analysis) {
  if (analysis.recommended_action) return analysis.recommended_action;
  if (analysis.critical_findings?.some((item) => riskLevelClass(item.severity) === "high")) return "Continue, but verify the biggest weakness before giving credit.";
  const risk = riskLevelClass(analysis.meta?.impression_management_risk);
  const confidence = String(analysis.meta?.confidence || "").toLowerCase();
  if (risk === "high") return "Continue, but focus on authenticity and execution detail.";
  if (confidence.includes("low")) return "Collect more samples before deciding whether to go deeper.";
  return "Continue the interview and validate the strongest style signal with evidence.";
}

function buildNextActionDetail(analysis) {
  const topQuestion = analysis.follow_up_questions?.[0]?.question;
  return topQuestion ? `Ask first: ${topQuestion}` : "Ask for concrete actions, decision logic, and outcome evidence.";
}

function buildCapabilityTags(report) {
  const features = report.atomic_features || {};
  const tags = [];
  if ((features.star_structure_score || 0) >= 0.75) tags.push("Strong structure");
  else if ((features.star_structure_score || 0) >= 0.5) tags.push("Moderate structure");
  else tags.push("Weak structure");

  if ((features.logical_connector_ratio || 0) >= 0.015) tags.push("Clear logic");
  else tags.push("Logic needs verification");

  if ((features.story_richness_score || 0) >= 0.65) tags.push("Rich detail");
  else if ((features.story_richness_score || 0) >= 0.45) tags.push("Average detail");
  else tags.push("Thin detail");

  if ((features.action_verbs_ratio || 0) >= 0.02) tags.push("Action-oriented language");
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
            <h3>${dim} - ${safeText(item.score, 0)}</h3>
            <p>${safeText(item.summary)}</p>
            <strong>Evidence for</strong>
            <ul>${(item.evidence_for || []).slice(0, 3).map((entry) => `<li>${entry}</li>`).join("") || "<li>N/A</li>"}</ul>
            <strong>Evidence against</strong>
            <ul>${(item.evidence_against || []).slice(0, 2).map((entry) => `<li>${entry}</li>`).join("") || "<li>N/A</li>"}</ul>
          </div>
        `
      )
      .join("") || "<div class='list-item'>No dimension analysis</div>"
  );
}

async function loadSampleLibrary() {
  try {
    const response = await fetch("/samples/index.json");
    if (!response.ok) throw new Error("Failed to load samples");
    sampleLibrary = await response.json();
    sampleSelectEl.innerHTML = ['<option value="">Select a sample</option>']
      .concat(sampleLibrary.map((item) => `<option value="${item.id}">${item.title}</option>`))
      .join("");
  } catch (error) {
    sampleSelectEl.innerHTML = '<option value="">Failed to load sample library</option>';
  }
}

async function fillSelectedSample() {
  const selectedId = sampleSelectEl.value;
  if (!selectedId) {
    window.alert("Please choose a sample first.");
    return;
  }
  const item = sampleLibrary.find((entry) => entry.id === selectedId);
  if (!item) {
    window.alert("Sample not found.");
    return;
  }
  sampleBtn.disabled = true;
  sampleBtn.textContent = "Loading...";
  try {
    const response = await fetch(`/samples/${item.filename}`);
    if (!response.ok) throw new Error("Failed to load sample text.");
    transcriptEl.value = await response.text();
    jobHintEl.value = item.job_hint || "";
  } catch (error) {
    window.alert(error.message);
  } finally {
    sampleBtn.disabled = false;
    sampleBtn.textContent = "Fill Sample";
  }
}

function renderDecisionLayer(report, analysis, source) {
  setText("analysisSource", source);
  setText("candidateStyle", buildStyleSummary(analysis));
  setText("candidateStyleNote", buildStyleNote(analysis));
  setText("riskHeadline", buildRiskHeadline(analysis));
  setText("riskDetail", buildRiskDetail(analysis));
  setText("nextAction", buildNextAction(analysis));
  setText("nextActionDetail", buildNextActionDetail(analysis));

  setHtml(
    "topFollowups",
    createList((analysis.follow_up_questions || []).slice(0, 3), (item) => `
      <div class="question-item">
        <strong>${safeText(item.question)}</strong>
        <div>${safeText(item.purpose)}</div>
      </div>
    `, "No suggested follow-up yet")
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
    createList(
      [
        ...(analysis.hire_risks || []),
        ...(analysis.evidence_gaps || []),
        ...((analysis.meta?.notes || []).slice(0, 2)),
      ].slice(0, 4),
      (note) => `<div class="tag">${note}</div>`,
      "No risk tags"
    )
  );

  const capabilityTags = buildCapabilityTags(report);
  setHtml("capabilityTags", capabilityTags.map((tag) => `<div class="tag">${tag}</div>`).join(""));
  setHtml(
    "capabilitySummary",
    `${capabilityTags.join(" / ")}. Verify whether these labels are supported by real evidence.`
  );
}

function renderInterviewOverview(report) {
  setHtml(
    "overview",
    [
      `<div class="chip">Job guess: ${report.interview_map.job_inference.value}</div>`,
      `<div class="chip">Turns: ${report.input_overview.turn_count}</div>`,
      `<div class="chip">Candidate chars: ${report.input_overview.candidate_char_count}</div>`,
      `<div class="chip">Sample quality: ${safeText(report.llm_analysis?.meta?.sample_quality || report.disc_analysis?.meta?.sample_quality)}</div>`,
      `<div class="chip">Parse source: ${report.interview_map.parse_source}</div>`,
    ].join("")
  );

  setHtml(
    "turns",
    createList(report.interview_map.turns, (turn) => `
      <div class="turn-item">
        <div class="type">Turn ${turn.turn_id} - ${turn.question_type}</div>
        <p><strong>Question:</strong> ${turn.question || "Not explicitly marked"}</p>
        <p><strong>Answer summary:</strong> ${turn.answer_summary}</p>
      </div>
    `)
  );
}

function renderDetailedLayer(report, analysis, source) {
  renderDimensionCards("dimensions", analysis.dimension_analysis || {});

  setHtml(
    "criticalFindings",
    createList(analysis.critical_findings, (item) => `
      <div class="list-item">
        <div class="type">${safeText(item.severity)}</div>
        <p><strong>${safeText(item.finding)}</strong></p>
        <p>${(item.basis || []).join("; ") || "No basis provided"}</p>
        <p>${safeText(item.impact, "No impact note")}</p>
      </div>
    `, "No critical finding")
  );

  setHtml(
    "evidenceGaps",
    createList(analysis.evidence_gaps, (item) => `
      <div class="list-item">
        <p>${safeText(item)}</p>
      </div>
    `, "No major evidence gap")
  );

  setHtml(
    "features",
    createList((report.atomic_features ? [
      { label: "STAR completeness", value: `${Math.round((report.atomic_features.star_structure_score || 0) * 100)}%` },
      { label: "Logical connector ratio", value: report.atomic_features.logical_connector_ratio },
      { label: "Action verb ratio", value: report.atomic_features.action_verbs_ratio },
      { label: "Story richness", value: `${Math.round((report.atomic_features.story_richness_score || 0) * 100)}%` },
      { label: "Self vs team", value: report.atomic_features.self_vs_team_orientation },
      { label: "Problem vs people", value: report.atomic_features.problem_vs_people_focus },
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
        <p>${(item.basis || []).join("; ")}</p>
      </div>
    `, "No behavioral hypothesis")
  );

  setHtml(
    "followups",
    createList(analysis.follow_up_questions, (item) => `
      <div class="list-item">
        <div class="type">${safeText(item.target_dimension)}</div>
        <p>${safeText(item.question)}</p>
        <p>${safeText(item.purpose)}</p>
      </div>
    `, "No follow-up question")
  );

  const llmStatus = report.llm_status.enabled
    ? [
        `Primary view: ${source}`,
        `Parser model: ${report.llm_status.parser_model}`,
        `Analysis model: ${report.llm_status.analysis_model}`,
        report.llm_status.parser_error ? `Parser error: ${report.llm_status.parser_error}` : "Parser call available.",
        report.llm_status.analysis_error ? `Analysis error: ${report.llm_status.analysis_error}` : "Analysis call available.",
      ].join("<br />")
    : "OPENAI_API_KEY is not configured, so the primary view uses local rules.";

  setHtml("llmStatus", llmStatus);
  const outputEl = document.getElementById("llmOutput");
  if (outputEl) {
    outputEl.textContent = report.llm_analysis
      ? JSON.stringify(report.llm_analysis, null, 2)
      : JSON.stringify(report.disc_analysis, null, 2);
  }
}

function renderReport(report) {
  const primary = getPrimaryAnalysis(report);
  resultsEl.classList.remove("hidden");
  statusEl.textContent = report.llm_status.enabled
    ? `Parser: ${report.llm_status.parser_model} / Analysis: ${report.llm_status.analysis_model}`
    : "Local rule analysis mode";

  renderDecisionLayer(report, primary.analysis, primary.source);
  renderMetricsLayer(report, primary.analysis);
  renderInterviewOverview(report);
  renderDetailedLayer(report, primary.analysis, primary.source);
}

sampleBtn.addEventListener("click", fillSelectedSample);

analyzeBtn.addEventListener("click", async () => {
  const interview_transcript = transcriptEl.value.trim();
  if (!interview_transcript) {
    window.alert("Please paste the interview transcript first.");
    return;
  }
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "Analyzing...";
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
    if (!response.ok) throw new Error(data.error || "Request failed.");
    renderReport(data);
  } catch (error) {
    window.alert(error.message);
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "Start Analysis";
  }
});

loadSampleLibrary();
