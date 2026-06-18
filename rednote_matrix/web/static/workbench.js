const conversation = document.querySelector("#conversation");
const submitButton = document.querySelector("#submitButton");
const outputState = document.querySelector("#outputState");
const titleOutput = document.querySelector("#titleOutput");
const bodyOutput = document.querySelector("#bodyOutput");
const tagOutput = document.querySelector("#tagOutput");
const promptInput = document.querySelector('.chat-composer textarea[name="custom_prompt"]');
const agentForm = document.querySelector("#agentForm");
const importJsonButton = document.querySelector("#importJsonButton");
const jsonImportInput = document.querySelector("#jsonImportInput");
const chatComposer = document.querySelector(".chat-composer");
const submitButtonLabel = submitButton.querySelector(".btn-label-full");
const submitButtonCompactLabel = submitButton.querySelector(".btn-label-compact");
const historyToggle = document.querySelector("#historyToggle");
const historyClose = document.querySelector("#historyClose");
const historyDrawer = document.querySelector("#historyDrawer");
const historyList = document.querySelector("#historyList");
const newConversationButton = document.querySelector("#newConversationButton");
const PROMPT_INPUT_MAX_HEIGHT = 180;

let activeAgentMessage = null;
let outputParts = { titles: "", body: "", tags: "" };
let hasSubmittedOnce = false;
let isRunning = false;
let conversationId = "";
let lastSubmittedPayload = null;
let latestResult = null;

initTypewriters();
syncSubmitAvailability();
loadHistoryList();

agentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formToPayload(event.currentTarget);
  const userMessage = promptInput.value.trim();
  const changes = diffPayload(lastSubmittedPayload, payload);
  if (isRunning || (hasSubmittedOnce && !userMessage && changes.length === 0)) {
    return;
  }
  payload.message = userMessage;
  payload.conversation_id = conversationId;
  payload.changes = changes;
  resetRun();
  appendUserTurn(userMessage, payload, changes);
  activeAgentMessage = appendAgentEventMessage();
  hasSubmittedOnce = true;
  isRunning = true;
  lastSubmittedPayload = clonePayload(payload);
  delete lastSubmittedPayload.message;
  delete lastSubmittedPayload.conversation_id;
  promptInput.value = "";
  resetPromptInputHeight();
  syncSubmitAvailability();
  chatComposer.classList.add("is-compact");
  submitButton.disabled = true;
  setSubmitButtonState("running");

  try {
    await streamAgent(payload);
  } finally {
    isRunning = false;
    submitButton.disabled = false;
    setSubmitButtonState("idle");
    syncSubmitAvailability();
  }
});

importJsonButton.addEventListener("click", () => {
  jsonImportInput.click();
});

historyToggle.addEventListener("click", async () => {
  historyDrawer.classList.add("is-open");
  historyDrawer.setAttribute("aria-hidden", "false");
  await loadHistoryList();
});

historyClose.addEventListener("click", closeHistoryDrawer);

historyDrawer.addEventListener("click", (event) => {
  if (event.target === historyDrawer) {
    closeHistoryDrawer();
  }
});

newConversationButton.addEventListener("click", () => {
  startNewConversation();
  closeHistoryDrawer();
});

jsonImportInput.addEventListener("change", async () => {
  const file = jsonImportInput.files?.[0];
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    applyImportedJson(data);
    markImportLoaded(file.name);
    appendMessage("assistant", "JSON Imported", `已导入 ${file.name}，商品背景已自动解析。`);
  } catch (error) {
    appendMessage("assistant", "JSON Import Failed", `导入失败：${error.message}`);
  } finally {
    jsonImportInput.value = "";
  }
});

promptInput.addEventListener("input", () => {
  growPromptInput();
  syncSubmitAvailability();
});

agentForm.addEventListener("input", (event) => {
  if (event.target === promptInput) return;
  syncSubmitAvailability();
});

agentForm.addEventListener("change", (event) => {
  if (event.target === promptInput) return;
  syncSubmitAvailability();
});

document.querySelectorAll("[data-copy-target]").forEach((button) => {
  button.addEventListener("click", async () => {
    const target = button.dataset.copyTarget;
    const text = outputParts[target] || "";
    if (!text.trim()) return;
    await navigator.clipboard.writeText(text);
    const label = button.querySelector(".copy-label");
    const oldText = label ? label.textContent : button.textContent;
    button.classList.add("is-copied");
    if (label) {
      label.textContent = "已复制";
    } else {
      button.textContent = "已复制";
    }
    setTimeout(() => {
      button.classList.remove("is-copied");
      if (label) {
        label.textContent = oldText;
      } else {
        button.textContent = oldText;
      }
    }, 1400);
  });
});

function formToPayload(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  data.enable_realtime_research = form.enable_realtime_research.checked;
  data.realtime_research_keywords = data.enable_realtime_research
    ? `${data.product_name} 爆款笔记\n${data.product_name} 真实体验\n${data.product_name} 避坑`
    : "";
  data.realtime_research_max_notes = 6;
  data.memory_namespace = data.brand_name || data.product_name;
  return data;
}

function clonePayload(payload) {
  return JSON.parse(JSON.stringify(payload));
}

function applyImportedJson(data) {
  const values = data.agent_input && typeof data.agent_input === "object" ? data.agent_input : data;
  const fieldNames = [
    "product_name",
    "brand_name",
    "price",
    "target_audience",
    "scenario",
    "tone",
    "custom_prompt",
    "memory_namespace",
  ];
  fieldNames.forEach((name) => {
    setFormValue(name, values[name]);
  });
  setFormValue("selling_points", listToLines(values.selling_points));
  setFormValue("forbidden_words", listToLines(values.forbidden_words));
  if (values.enable_realtime_research !== undefined) {
    agentForm.enable_realtime_research.checked = Boolean(values.enable_realtime_research);
  }
  if (promptInput) {
    growPromptInput();
  }
  syncSubmitAvailability();
}

function setFormValue(name, value) {
  if (value === undefined || value === null) return;
  const field = agentForm.elements[name];
  if (!field) return;
  field.value = Array.isArray(value) ? listToLines(value) : String(value);
}

function listToLines(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean).join("\n");
  }
  return value === undefined || value === null ? "" : String(value);
}

function markImportLoaded(filename) {
  const label = importJsonButton.querySelector("span:last-child");
  const oldText = label.textContent;
  importJsonButton.classList.add("is-loaded");
  label.textContent = "已导入";
  setTimeout(() => {
    importJsonButton.classList.remove("is-loaded");
    label.textContent = oldText || "导入 JSON";
  }, 1400);
}

function setSubmitButtonState(state) {
  if (!submitButtonLabel || !submitButtonCompactLabel) return;
  if (state === "running") {
    submitButtonLabel.textContent = "运行中";
    submitButtonCompactLabel.textContent = "↑";
    submitButton.setAttribute("aria-label", "Agent 运行中");
    return;
  }
  submitButtonLabel.textContent = "运行 Agent";
  submitButtonCompactLabel.textContent = "↑";
  submitButton.setAttribute("aria-label", hasSubmittedOnce ? "再次运行 Agent" : "运行 Agent");
}

function growPromptInput() {
  if (!promptInput.value.trim()) {
    resetPromptInputHeight();
    return;
  }
  const nextHeight = Math.min(promptInput.scrollHeight, PROMPT_INPUT_MAX_HEIGHT);
  if (nextHeight > promptInput.clientHeight + 2) {
    promptInput.style.height = `${nextHeight}px`;
  }
}

function resetPromptInputHeight() {
  promptInput.style.height = "";
}

function syncSubmitAvailability() {
  if (isRunning) {
    submitButton.disabled = true;
    return;
  }
  if (!hasSubmittedOnce) {
    submitButton.disabled = false;
    return;
  }
  const payload = formToPayload(agentForm);
  const hasPrompt = Boolean(promptInput.value.trim());
  const hasChanges = diffPayload(lastSubmittedPayload, payload).length > 0;
  submitButton.disabled = !hasPrompt && !hasChanges;
}

function summaryFromPayload(payload) {
  const lines = [
    `商品：${payload.product_name}`,
    payload.brand_name ? `品牌：${payload.brand_name}` : "",
    payload.target_audience ? `人群：${payload.target_audience}` : "",
    payload.scenario ? `场景：${payload.scenario}` : "",
    payload.enable_realtime_research ? "已开启 MediaCrawler Node" : "未开启 MediaCrawler Node",
  ].filter(Boolean);
  return lines.join("\n");
}

async function streamAgent(payload) {
  const response = await fetch("/ui/agent/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok || !response.body) {
    throw new Error(`Agent 请求失败：${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let finished = false;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      const event = JSON.parse(line.slice(6));
      if (event.type === "result" || event.type === "error") { finished = true; }
      handleEvent(event);
    }
  }
  if (!finished) {
    handleEvent({ type: "error", message: "连接已结束，但没有收到最终结果。请检查 LLM 配置或稍后重试。" });
  }
}

function handleEvent(event) {
  if (event.type === "accepted") {
    if (event.conversation_id) {
      conversationId = event.conversation_id;
    }
    addAgentEvent("decision", "任务已接收", event.message);
    return;
  }
  if (event.type === "node") {
    updateNodeEvent(event);
    return;
  }
  if (event.type === "result") {
    latestResult = event.result;
    renderDraft(event.result);
    outputState.textContent = "ready";
    finishAgentMessage();
    loadHistoryList();
    return;
  }
  if (event.type === "error") {
    addAgentEvent("error", "运行失败", event.message);
    outputState.textContent = "error";
  }
}

function updateNodeEvent(event) {
  if (event.status === "running") {
    addAgentEvent("pending", event.label, event.message || "处理中");
  } else {
    addAgentEvent("done", event.label, event.message || "已完成");
  }
}

function renderDraft(result) {
  const draft = result.draft || {};
  const titles = draft.titles || [];
  const body = draft.body || "";
  const tags = (draft.tags || []).map((tag) => (String(tag).startsWith("#") ? String(tag) : `#${tag}`));
  outputParts = {
    titles: titles.map((title, index) => `${index + 1}. ${title}`).join("\n"),
    body,
    tags: tags.join(" "),
  };
  streamHtmlTokens(titleOutput, markdownLines(titles.map((title, index) => `${index + 1}. ${title}`)));
  streamHtmlTokens(bodyOutput, escapeHtml(body).replace(/\n/g, "<br>"));
  streamHtmlTokens(tagOutput, tags.map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join(""));
}

function renderOutputParts(parts) {
  outputParts = {
    titles: String(parts?.titles || ""),
    body: String(parts?.body || ""),
    tags: String(parts?.tags || ""),
  };
  titleOutput.innerHTML = markdownLines(outputParts.titles.split("\n").filter(Boolean));
  bodyOutput.innerHTML = escapeHtml(outputParts.body).replace(/\n/g, "<br>");
  tagOutput.innerHTML = outputParts.tags
    .split(/\s+/)
    .filter(Boolean)
    .map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`)
    .join("");
  outputState.textContent = "ready";
}

function markdownLines(lines) {
  return lines.map((line) => `<p>${escapeHtml(line)}</p>`).join("");
}

function streamHtmlTokens(element, html) {
  element.innerHTML = "";
  const tokens = tokenizeHtml(html);
  let index = 0;
  let current = "";
  element.classList.add("typing-cursor");
  element.classList.remove("is-done");
  const step = () => {
    if (index >= tokens.length) {
      element.classList.add("is-done");
      element.classList.remove("typing-cursor");
      return;
    }
    const token = tokens[index++];
    current += token;
    element.innerHTML = current;
    window.setTimeout(step, tokenDelay(token, index));
  };
  step();
}

function appendMessage(role, meta, text) {
  const article = document.createElement("article");
  article.className = `msg ${role === "user" ? "msg-user" : "msg-agent"}`;
  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = role === "user" ? "YOU" : "RM";
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  const head = document.createElement("div");
  head.className = "msg-meta";
  head.textContent = meta;
  const body = document.createElement("p");
  body.textContent = text;
  bubble.append(head, body);
  article.append(avatar, bubble);
  conversation.append(article);
  conversation.scrollTop = conversation.scrollHeight;
  return article;
}

function appendUserTurn(message, payload, changes) {
  const fallback = hasSubmittedOnce ? "" : summaryFromPayload(payload);
  const article = document.createElement("article");
  article.className = "msg msg-user";
  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = "YOU";
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  const head = document.createElement("div");
  head.className = "msg-meta";
  head.textContent = hasSubmittedOnce ? "User Follow-up" : "User Request";
  const body = document.createElement("div");
  body.className = "user-turn-body";

  if (message) {
    const prompt = document.createElement("p");
    prompt.textContent = message;
    body.append(prompt);
  } else if (fallback) {
    const prompt = document.createElement("p");
    prompt.textContent = fallback;
    body.append(prompt);
  }
  if (changes.length > 0 && hasSubmittedOnce) {
    body.append(renderChangeList(changes));
  }
  bubble.append(head, body);
  article.append(avatar, bubble);
  conversation.append(article);
  conversation.scrollTop = conversation.scrollHeight;
}

function appendRestoredUserTurn(turn, isFirst) {
  const article = document.createElement("article");
  article.className = "msg msg-user";
  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = "YOU";
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  const head = document.createElement("div");
  head.className = "msg-meta";
  head.textContent = isFirst ? "User Request" : "User Follow-up";
  const body = document.createElement("div");
  body.className = "user-turn-body";
  const text = document.createElement("p");
  text.textContent = turn.message || (isFirst ? summaryFromPayload(turn.agent_input || {}) : "调整商品背景");
  body.append(text);
  if (Array.isArray(turn.changes) && turn.changes.length > 0) {
    body.append(renderChangeList(turn.changes));
  }
  bubble.append(head, body);
  article.append(avatar, bubble);
  conversation.append(article);
}

function appendRestoredAgentTurn(turn, index) {
  const article = document.createElement("article");
  article.className = "msg msg-agent";
  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = "RM";
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  const head = document.createElement("div");
  head.className = "msg-meta";
  head.innerHTML = `<strong>Agent</strong><span>${turn.status === "completed" ? "完成" : turn.status || "记录"}</span>`;
  const finalText = document.createElement("div");
  finalText.className = turn.status === "error" ? "final-hint event-error" : "final-hint";
  finalText.textContent = turn.status === "error" ? `运行失败：${turn.error || "未知错误"}` : "Agent 回复已生成，请查看右端输出结果！";
  bubble.append(head, finalText);
  if (turn.output_parts) {
    const actions = document.createElement("div");
    actions.className = "turn-result-actions";
    const button = document.createElement("button");
    button.className = "restore-result-button";
    button.type = "button";
    button.textContent = `恢复第 ${index + 1} 轮结果`;
    button.addEventListener("click", () => {
      renderOutputParts(turn.output_parts);
      latestResult = turn.result || null;
    });
    actions.append(button);
    bubble.append(actions);
  }
  article.append(avatar, bubble);
  conversation.append(article);
}

function renderChangeList(changes) {
  const list = document.createElement("div");
  list.className = "change-list";
  changes.forEach((change) => {
    const row = document.createElement("div");
    row.className = "change-row";
    const label = document.createElement("strong");
    label.textContent = fieldLabel(change.key);
    const oldValue = document.createElement("span");
    oldValue.className = "change-old";
    oldValue.textContent = change.before || "空";
    const arrow = document.createElement("span");
    arrow.className = "change-arrow";
    arrow.textContent = "→";
    const newValue = document.createElement("span");
    newValue.className = "change-new";
    newValue.textContent = change.after || "空";
    row.append(label, oldValue, arrow, newValue);
    list.append(row);
  });
  return list;
}

function diffPayload(previous, current) {
  if (!previous) return [];
  const keys = [
    "product_name",
    "brand_name",
    "price",
    "target_audience",
    "scenario",
    "tone",
    "selling_points",
    "forbidden_words",
    "enable_realtime_research",
  ];
  return keys
    .map((key) => ({
      key,
      before: normalizeComparable(previous[key]),
      after: normalizeComparable(current[key]),
    }))
    .filter((item) => item.before !== item.after);
}

function normalizeComparable(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean).join("\n");
  }
  if (typeof value === "boolean") {
    return value ? "开启" : "关闭";
  }
  return String(value ?? "").trim();
}

function fieldLabel(key) {
  const labels = {
    product_name: "商品",
    brand_name: "品牌",
    price: "价格",
    target_audience: "人群",
    scenario: "场景",
    tone: "语气",
    selling_points: "卖点",
    forbidden_words: "禁用词",
    enable_realtime_research: "MediaCrawler",
  };
  return labels[key] || key;
}

function appendAgentEventMessage() {
  const article = document.createElement("article");
  article.className = "msg msg-agent";
  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = "RM";
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  const head = document.createElement("div");
  head.className = "msg-meta";
  head.innerHTML = "<strong>Agent</strong><span>运行中</span><em>streaming</em>";
  const feed = document.createElement("div");
  feed.className = "event-feed";
  bubble.append(head, feed);
  article.append(avatar, bubble);
  conversation.append(article);
  conversation.scrollTop = conversation.scrollHeight;
  return { article, feed, head };
}

function addAgentEvent(kind, title, summary) {
  if (!activeAgentMessage) return;
  const row = document.createElement("div");
  row.className = `event-row event-${kind}`;
  const icon = document.createElement("span");
  icon.className = "event-icon";
  icon.textContent = kind === "done" ? "✓" : kind === "error" ? "!" : kind === "decision" ? "→" : "…";
  const body = document.createElement("div");
  body.className = "event-body";
  const strong = document.createElement("strong");
  strong.textContent = title;
  const small = document.createElement("small");
  small.className = "typewriter";
  body.append(strong, small);
  row.append(icon, body);
  activeAgentMessage.feed.append(row);
  streamPlainTokens(small, summary);
  conversation.scrollTop = conversation.scrollHeight;
}

function finishAgentMessage() {
  if (!activeAgentMessage) return;
  activeAgentMessage.feed.innerHTML = "";
  activeAgentMessage.head.innerHTML = "<strong>Agent</strong><span>完成</span>";
  const finalText = document.createElement("div");
  finalText.className = "final-hint";
  finalText.textContent = "Agent 回复已生成，请查看右端输出结果！";
  activeAgentMessage.feed.append(finalText);
  conversation.scrollTop = conversation.scrollHeight;
  activeAgentMessage = null;
}

function resetRun() {
  titleOutput.textContent = "标题生成中...";
  bodyOutput.textContent = "正文生成中...";
  tagOutput.textContent = "标签生成中...";
  outputState.textContent = "streaming";
  outputParts = { titles: "", body: "", tags: "" };
  latestResult = null;
}

async function refreshStatus() {
  await fetch("/ui/status");
}

async function loadHistoryList() {
  if (!historyList) return;
  const response = await fetch("/ui/conversations");
  if (!response.ok) return;
  const data = await response.json();
  const items = data.items || [];
  historyList.innerHTML = "";
  if (items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "暂无历史对话。";
    historyList.append(empty);
    return;
  }
  items.forEach((item) => {
    const button = document.createElement("button");
    button.className = "history-item";
    button.type = "button";
    button.innerHTML = `
      <strong>${escapeHtml(item.title || "未命名对话")}</strong>
      <span>${escapeHtml(item.latest_message || "无新增要求")}</span>
      <small>${item.turn_count || 0} 轮 · ${escapeHtml(formatTime(item.updated_at))}</small>
    `;
    button.addEventListener("click", () => restoreConversation(item.id));
    historyList.append(button);
  });
}

async function restoreConversation(id) {
  const response = await fetch(`/ui/conversations/${encodeURIComponent(id)}`);
  if (!response.ok) return;
  const record = await response.json();
  conversationId = record.id || "";
  lastSubmittedPayload = clonePayload(record.agent_input || {});
  hasSubmittedOnce = Boolean(record.turns?.length);
  isRunning = false;
  applyAgentInputToForm(lastSubmittedPayload);
  conversation.innerHTML = "";
  (record.turns || []).forEach((turn, index) => {
    appendRestoredUserTurn(turn, index === 0);
    appendRestoredAgentTurn(turn, index);
  });
  const latestCompleted = [...(record.turns || [])].reverse().find((turn) => turn.output_parts);
  if (latestCompleted) {
    renderOutputParts(latestCompleted.output_parts);
    latestResult = latestCompleted.result || null;
  }
  chatComposer.classList.toggle("is-compact", hasSubmittedOnce);
  setSubmitButtonState("idle");
  syncSubmitAvailability();
  closeHistoryDrawer();
  conversation.scrollTop = conversation.scrollHeight;
}

function startNewConversation() {
  conversationId = "";
  activeAgentMessage = null;
  outputParts = { titles: "", body: "", tags: "" };
  hasSubmittedOnce = false;
  isRunning = false;
  lastSubmittedPayload = null;
  latestResult = null;
  agentForm.reset();
  setFormValue("tone", "自然、可信、轻种草");
  promptInput.value = "";
  resetPromptInputHeight();
  chatComposer.classList.remove("is-compact");
  outputState.textContent = "waiting";
  titleOutput.textContent = "等待 Agent 输出。";
  bodyOutput.textContent = "等待 Agent 输出。";
  tagOutput.textContent = "等待 Agent 输出。";
  conversation.innerHTML = "";
  appendIntroMessage();
  setSubmitButtonState("idle");
  syncSubmitAvailability();
}

function appendIntroMessage() {
  const article = document.createElement("div");
  article.className = "msg msg-agent intro-msg";
  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = "RM";
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble type-bubble";
  const meta = document.createElement("div");
  meta.className = "msg-meta";
  meta.textContent = "Agent Ready";
  const text = document.createElement("p");
  text.className = "typewriter";
  bubble.append(meta, text);
  article.append(avatar, bubble);
  conversation.append(article);
  streamPlainTokens(text, "告诉我商品、品牌、人群和语气。我会实时展示节点进度，最终文案整理到右侧输出卡。");
}

function applyAgentInputToForm(input) {
  const fields = [
    "product_name",
    "brand_name",
    "price",
    "target_audience",
    "scenario",
    "tone",
    "selling_points",
    "forbidden_words",
  ];
  fields.forEach((name) => setFormValue(name, input?.[name] ?? ""));
  agentForm.enable_realtime_research.checked = Boolean(input?.enable_realtime_research);
  promptInput.value = "";
  resetPromptInputHeight();
  syncSubmitAvailability();
}

function closeHistoryDrawer() {
  historyDrawer.classList.remove("is-open");
  historyDrawer.setAttribute("aria-hidden", "true");
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function initTypewriters() {
  document.querySelectorAll("[data-type-text]").forEach((element) => {
    streamPlainTokens(element, element.dataset.typeText || "");
  });
}

function streamPlainTokens(element, text) {
  element.textContent = "";
  element.classList.remove("is-done");
  const tokens = tokenizePlainText(text);
  let index = 0;
  let current = "";
  const step = () => {
    if (index >= tokens.length) {
      element.classList.add("is-done");
      return;
    }
    const token = tokens[index++];
    current += token;
    element.textContent = current;
    window.setTimeout(step, tokenDelay(token, index));
  };
  step();
}

function tokenizeHtml(html) {
  const tokens = [];
  const parts = String(html).match(/<[^>]+>|[^<]+/g) || [];
  parts.forEach((part) => {
    if (part.startsWith("<")) {
      tokens.push(part);
    } else {
      tokens.push(...tokenizePlainText(part));
    }
  });
  return tokens;
}

function tokenizePlainText(text) {
  const tokens = [];
  let buffer = "";
  for (const char of String(text || "")) {
    if (/[\s\n]/.test(char)) {
      if (buffer) {
        tokens.push(buffer);
        buffer = "";
      }
      tokens.push(char);
      continue;
    }
    if (/[，。！？；：,.!?;:、]/.test(char)) {
      if (buffer) {
        tokens.push(buffer);
        buffer = "";
      }
      tokens.push(char);
      continue;
    }
    buffer += char;
    if (/[A-Za-z0-9]/.test(char)) {
      if (buffer.length >= 8) {
        tokens.push(buffer);
        buffer = "";
      }
    } else if (buffer.length >= nextCjkTokenSize(tokens.length)) {
      tokens.push(buffer);
      buffer = "";
    }
  }
  if (buffer) tokens.push(buffer);
  return mergeTinyTokens(tokens);
}

function nextCjkTokenSize(seed) {
  return [2, 3, 4, 2, 5, 3][seed % 6];
}

function mergeTinyTokens(tokens) {
  const merged = [];
  tokens.forEach((token) => {
    const previous = merged[merged.length - 1];
    if (
      previous &&
      token.length === 1 &&
      !/[\s\n，。！？；：,.!?;:、]/.test(token) &&
      !/[\s\n，。！？；：,.!?;:、]/.test(previous) &&
      previous.length < 5
    ) {
      merged[merged.length - 1] = previous + token;
    } else {
      merged.push(token);
    }
  });
  return merged;
}

function tokenDelay(token, index) {
  if (/^\s+$/.test(token) || /^<[^>]+>$/.test(token)) return 0;
  if (/[。！？.!?]/.test(token)) return 180 + (index % 3) * 35;
  if (/[，；：,;:、]/.test(token)) return 95 + (index % 2) * 25;
  return 34 + (token.length % 4) * 18 + (index % 3) * 9;
}

refreshStatus();
