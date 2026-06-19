const conversation = document.querySelector("#conversation");
const submitButton = document.querySelector("#submitButton");
const outputState = document.querySelector("#outputState");
const titleOutput = document.querySelector("#titleOutput");
const bodyOutput = document.querySelector("#bodyOutput");
const tagOutput = document.querySelector("#tagOutput");
const promptInput = document.querySelector('.chat-composer textarea[name="custom_prompt"]');
const agentForm = document.querySelector("#agentForm");
const chatComposer = document.querySelector(".chat-composer");
const crawlLimitInput = document.querySelector("#crawlLimitInput");
const crawlerNoteList = document.querySelector("#crawlerNoteList");
const skipCrawlerButton = document.querySelector("#skipCrawlerButton");
const xhsAuthState = document.querySelector("#xhsAuthState");
const chromeState = document.querySelector("#chromeState");
const crawlerCountState = document.querySelector("#crawlerCountState");
const crawlerInsightList = document.querySelector("#crawlerInsightList");
const submitButtonLabel = submitButton.querySelector(".btn-label-full");
const submitButtonCompactLabel = submitButton.querySelector(".btn-label-compact");
const historyToggle = document.querySelector("#historyToggle");
const historyClose = document.querySelector("#historyClose");
const historyDrawer = document.querySelector("#historyDrawer");
const historyList = document.querySelector("#historyList");
const newConversationButton = document.querySelector("#newConversationButton");
const contextPanel = document.querySelector(".panel-context");
const chatPanel = document.querySelector(".panel-chat");
const outputPanel = document.querySelector(".panel-right");
const loginGate = document.querySelector("#loginGate");
const loginCountdown = document.querySelector("#loginCountdown");
const loginGateStatus = document.querySelector("#loginGateStatus");
const composerResizeHandle = document.querySelector("#composerResizeHandle");
const composerInputShell = document.querySelector(".composer-input-shell");
const PROMPT_INPUT_MIN_HEIGHT = 44;
const PROMPT_INPUT_MAX_HEIGHT = 180;
const LOGIN_GATE_SECONDS = 120;
const LOGIN_WORKER_TIMEOUT_SECONDS = 900;

let activeAgentMessage = null;
let outputParts = { titles: "", body: "", tags: "" };
let hasSubmittedOnce = false;
let isRunning = false;
let conversationId = "";
let lastSubmittedPayload = null;
let latestResult = null;
let activeStreamController = null;
let currentRunPayload = null;
let crawlerBypassRequested = false;
let crawlerNotes = [];
let crawlerRenderVersion = 0;
let activeNodeRows = new Map();
let isLoginPending = false;
let latestWorkbenchStatus = null;
let loginCountdownTimer = null;
let userPromptHeight = PROMPT_INPUT_MIN_HEIGHT;

initTypewriters();
initHistoryHint();
syncSubmitAvailability();
loadHistoryList();

agentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formToPayload(event.currentTarget);
  const userMessage = promptInput.value.trim();
  const changes = diffPayload(lastSubmittedPayload, payload);
  if (isRunning || isLoginPending) {
    return;
  }
  if (!hasRunnableRequest(payload)) {
    syncSubmitAvailability();
    return;
  }
  if (hasSubmittedOnce && !userMessage && changes.length === 0) {
    return;
  }
  payload.message = userMessage;
  payload.conversation_id = conversationId;
  payload.changes = changes;
  if (payload.enable_realtime_research) {
    const loginReady = await ensureXhsLoginBeforeRun();
    if (!loginReady) {
      syncSubmitAvailability();
      return;
    }
  }
  await runSubmittedPayload(payload, userMessage, changes);
});

async function runSubmittedPayload(payload, userMessage, changes) {
  resetRun({ preserveCrawler: hasSubmittedOnce });
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
  flashPanel(chatPanel, "agent");

  try {
    await streamAgent(payload);
  } catch (error) {
    if (error.name === "AbortError" && crawlerBypassRequested) {
      crawlerBypassRequested = false;
      try {
        await streamCrawlerBypassRun();
      } catch (bypassError) {
        handleEvent({ type: "error", message: bypassError.message || String(bypassError) });
      }
    } else if (error.name !== "AbortError") {
      handleEvent({ type: "error", message: error.message || String(error) });
    }
  } finally {
    isRunning = false;
    crawlerBypassRequested = false;
    activeStreamController = null;
    currentRunPayload = null;
    submitButton.disabled = false;
    if (skipCrawlerButton) {
      skipCrawlerButton.disabled = false;
      skipCrawlerButton.textContent = "终止爬取进入生成";
    }
    setSubmitButtonState("idle");
    syncSubmitAvailability();
  }
}

historyToggle.addEventListener("click", async () => {
  historyToggle.classList.remove("history-attention");
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

if (skipCrawlerButton) {
  skipCrawlerButton.addEventListener("click", async () => {
    if (isRunning && activeStreamController && currentRunPayload?.enable_realtime_research) {
      crawlerBypassRequested = true;
      skipCrawlerButton.disabled = true;
      skipCrawlerButton.textContent = "正在进入生成";
      activeStreamController.abort();
      return;
    }
    agentForm.enable_realtime_research.checked = false;
    skipCrawlerButton.textContent = "本轮已跳过爬取";
    updateCrawlerInsights(["已关闭实时爬取，本轮将使用项目内置爆款方法论生成。"]);
    syncSubmitAvailability();
  });
}

promptInput.addEventListener("input", () => {
  growPromptInput();
  syncSubmitAvailability();
});

promptInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  if (!submitButton.disabled) {
    agentForm.requestSubmit();
  }
});

if (composerResizeHandle) {
  composerResizeHandle.addEventListener("pointerdown", startComposerResize);
}

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
  const productName = String(data.product_name || "").trim();
  data.realtime_research_keywords = data.enable_realtime_research && productName
    ? `${productName} 爆款笔记\n${productName} 真实体验\n${productName} 避坑`
    : "";
  data.realtime_research_max_notes = clampNumber(crawlLimitInput?.value, 1, 30, 20);
  data.memory_namespace = data.brand_name || productName;
  return data;
}

function clampNumber(value, min, max, fallback) {
  const number = Number.parseInt(value, 10);
  if (Number.isNaN(number)) return fallback;
  return Math.max(min, Math.min(max, number));
}

function clonePayload(payload) {
  return JSON.parse(JSON.stringify(payload));
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
  const nextHeight = clampNumber(promptInput.scrollHeight, PROMPT_INPUT_MIN_HEIGHT, PROMPT_INPUT_MAX_HEIGHT, PROMPT_INPUT_MIN_HEIGHT);
  if (nextHeight > userPromptHeight + 2) {
    setPromptInputHeight(nextHeight);
  }
}

function resetPromptInputHeight() {
  setPromptInputHeight(PROMPT_INPUT_MIN_HEIGHT);
}

function setPromptInputHeight(height) {
  userPromptHeight = clampNumber(height, PROMPT_INPUT_MIN_HEIGHT, PROMPT_INPUT_MAX_HEIGHT, PROMPT_INPUT_MIN_HEIGHT);
  promptInput.style.height = `${userPromptHeight}px`;
  if (composerInputShell) {
    composerInputShell.style.height = `${userPromptHeight}px`;
  }
}

function startComposerResize(event) {
  event.preventDefault();
  const startY = event.clientY;
  const startHeight = promptInput.getBoundingClientRect().height || userPromptHeight;
  composerResizeHandle.setPointerCapture?.(event.pointerId);
  chatComposer.classList.add("is-resizing");

  const onMove = (moveEvent) => {
    const delta = startY - moveEvent.clientY;
    setPromptInputHeight(startHeight + delta);
  };
  const onEnd = () => {
    chatComposer.classList.remove("is-resizing");
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onEnd);
    window.removeEventListener("pointercancel", onEnd);
  };

  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onEnd);
  window.addEventListener("pointercancel", onEnd);
}

function syncSubmitAvailability() {
  if (isRunning || isLoginPending) {
    submitButton.disabled = true;
    return;
  }
  const payload = formToPayload(agentForm);
  const hasPrompt = Boolean(promptInput.value.trim());
  const hasRequest = hasRunnableRequest(payload);
  if (!hasRequest) {
    submitButton.disabled = true;
    return;
  }
  if (!hasSubmittedOnce) {
    submitButton.disabled = false;
    return;
  }
  const hasChanges = diffPayload(lastSubmittedPayload, payload).length > 0;
  submitButton.disabled = !hasPrompt && !hasChanges;
}

function hasRunnableRequest(payload) {
  const promptText = String(promptInput.value || payload.custom_prompt || "").trim();
  if (promptText) return true;
  return [
    payload.product_name,
    payload.brand_name,
    payload.target_audience,
    payload.scenario,
    payload.selling_points,
    payload.forbidden_words,
    payload.price,
  ].some((value) => String(value || "").trim());
}

function summaryFromPayload(payload) {
  const lines = [
    payload.product_name ? `商品：${payload.product_name}` : "",
    payload.brand_name ? `品牌：${payload.brand_name}` : "",
    payload.target_audience ? `人群：${payload.target_audience}` : "",
    payload.scenario ? `场景：${payload.scenario}` : "",
    payload.enable_realtime_research ? "已开启 MediaCrawler Node" : "未开启 MediaCrawler Node",
  ].filter(Boolean);
  return lines.join("\n");
}

async function streamAgent(payload) {
  currentRunPayload = clonePayload(payload);
  const controller = new AbortController();
  activeStreamController = controller;
  const response = await fetch("/ui/agent/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: controller.signal,
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
  activeStreamController = null;
}

async function streamCrawlerBypassRun() {
  if (!currentRunPayload) return;
  const nextPayload = clonePayload(currentRunPayload);
  nextPayload.enable_realtime_research = false;
  nextPayload.realtime_research_keywords = "";
  nextPayload.realtime_research_max_notes = 0;
  nextPayload.changes = [
    ...(Array.isArray(nextPayload.changes) ? nextPayload.changes : []),
    { key: "enable_realtime_research", before: "开启", after: "关闭" },
  ];
  addAgentEvent("decision", "终止爆款检索", "已停止当前检索请求，改用已有样本和内置爆款规则继续生成");
  await streamAgent(nextPayload);
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
  if (event.type === "market_note") {
    appendCrawlerNote(event.note || {}, event.index || crawlerNotes.length + 1);
    flashPanel(contextPanel, "crawler");
    return;
  }
  if (event.type === "result") {
    latestResult = event.result;
    flashPanel(outputPanel, "output");
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
  upsertAgentNodeEvent(event);
  if (event.node === "market_research_agent") {
    updateCrawlerNode(event);
  }
}

function renderDraft(result) {
  renderCrawlerFromResult(result);
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
  flashPanel(outputPanel, "output");
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

function updateCrawlerNode(event) {
  const payload = event.payload || {};
  if (event.status === "running") {
    setCrawlerStatusText(crawlerCountState, "检索中");
    updateCrawlerInsights(["MediaCrawler 正在检索高互动笔记，返回后会按互动强度排序。"]);
    return;
  }
  mergeCrawlerNotes(payload.notes || []);
  const status = payload.status || "unknown";
  const count = Array.isArray(payload.notes) ? payload.notes.length : Number(payload.metric || 0);
  setCrawlerStatusText(crawlerCountState, `${count} 条`);
  updateCrawlerInsights(buildCrawlerInsights(payload.notes || [], status, payload.message || event.message));
}

function renderCrawlerFromResult(result) {
  const context = result?.market_research_context || {};
  mergeCrawlerNotes(context.notes || []);
  if (context.status || context.message) {
    updateCrawlerInsights(buildCrawlerInsights(context.notes || [], context.status, context.message));
  }
}

function resetCrawlerPanel() {
  crawlerNotes = [];
  crawlerRenderVersion += 1;
  if (crawlerNoteList) {
    crawlerNoteList.innerHTML = '<div class="crawler-empty">等待 MediaCrawler 返回爆款样本。</div>';
  }
  setCrawlerStatusText(crawlerCountState, "0 条");
  updateCrawlerInsights(["还没有样本，先让 Agent 跑起来。"]);
  if (skipCrawlerButton) {
    skipCrawlerButton.disabled = false;
    skipCrawlerButton.textContent = "终止爬取进入生成";
  }
}

function renderCrawlerNotes(notes) {
  if (!crawlerNoteList || !Array.isArray(notes)) return;
  const renderVersion = ++crawlerRenderVersion;
  const cleanNotes = notes.filter((note) => note && (note.title || note.note_url));
  crawlerNotes = cleanNotes;
  crawlerNoteList.innerHTML = "";
  if (cleanNotes.length === 0) {
    const empty = document.createElement("div");
    empty.className = "crawler-empty";
    empty.textContent = "本轮没有拿到可展示的爆款样本。";
    crawlerNoteList.append(empty);
    setCrawlerStatusText(crawlerCountState, "0 条");
    return;
  }
  cleanNotes.forEach((note, index) => {
    window.setTimeout(() => {
      if (renderVersion !== crawlerRenderVersion) return;
      crawlerNoteList.append(createCrawlerNoteCard(note, index));
      crawlerNoteList.scrollTop = crawlerNoteList.scrollHeight;
    }, Math.min(index * 48, 620));
  });
  setCrawlerStatusText(crawlerCountState, `${cleanNotes.length} 条`);
}

function mergeCrawlerNotes(notes) {
  if (!Array.isArray(notes)) return;
  notes.forEach((note) => appendCrawlerNote(note, crawlerNotes.length + 1));
}

function appendCrawlerNote(note, index) {
  if (!crawlerNoteList || !note || (!note.title && !note.note_url)) return;
  const key = crawlerNoteKey(note);
  if (crawlerNotes.some((item) => crawlerNoteKey(item) === key)) return;
  crawlerNotes.push(note);
  const empty = crawlerNoteList.querySelector(".crawler-empty");
  if (empty) empty.remove();
  crawlerNoteList.append(createCrawlerNoteCard(note, index));
  crawlerNoteList.scrollTop = crawlerNoteList.scrollHeight;
  flashPanel(contextPanel, "crawler");
  setCrawlerStatusText(crawlerCountState, `${crawlerNotes.length} 条`);
  updateCrawlerInsights(buildCrawlerInsights(crawlerNotes, "completed", ""));
}

function crawlerNoteKey(note) {
  return String(note.note_url || note.title || "").trim();
}

function createCrawlerNoteCard(note, index) {
  const href = String(note.note_url || "").trim();
  const element = document.createElement(href ? "a" : "div");
  element.className = "crawler-note-card";
  if (href) {
    element.href = href;
    element.target = "_blank";
    element.rel = "noopener noreferrer";
    element.title = "打开原帖";
  }
  const title = document.createElement("div");
  title.className = "crawler-note-title";
  title.textContent = note.title || `未命名样本 ${index + 1}`;
  const metrics = document.createElement("div");
  metrics.className = "crawler-note-metrics";
  metrics.innerHTML = `
    <span>赞 ${escapeHtml(formatMetric(note.liked_count))}</span>
    <span>评 ${escapeHtml(formatMetric(note.comment_count))}</span>
    <span>${escapeHtml(note.source_keyword || "搜索样本")}</span>
  `;
  element.append(title, metrics);
  return element;
}

function formatMetric(value) {
  const text = String(value || "").trim();
  return text || "--";
}

function buildCrawlerInsights(notes, status, message) {
  const cleanNotes = Array.isArray(notes) ? notes : [];
  if (status && status !== "completed") {
    return [message || `检索状态：${status}`];
  }
  if (cleanNotes.length === 0) {
    return [message || "没有拿到实时样本，本轮会回退到项目内置爆款规则。"];
  }
  const top = [...cleanNotes].sort((a, b) => metricScore(b) - metricScore(a))[0];
  const keywordMap = new Map();
  cleanNotes.forEach((note) => {
    const keyword = String(note.source_keyword || "").trim();
    if (keyword) keywordMap.set(keyword, (keywordMap.get(keyword) || 0) + 1);
  });
  const hotKeyword = [...keywordMap.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
  return [
    `已拿到 ${cleanNotes.length} 条候选样本，可优先吸收标题里的情绪入口和场景入口。`,
    top?.title ? `当前最高互动样本：${top.title}` : "",
    hotKeyword ? `样本集中关键词：${hotKeyword}` : "样本会按点赞和评论强度进入趋势归纳节点。",
  ].filter(Boolean);
}

function metricScore(note) {
  return countToNumber(note?.liked_count) + countToNumber(note?.comment_count) * 1.4;
}

function countToNumber(value) {
  const text = String(value || "").trim().toLowerCase();
  if (!text) return 0;
  const number = Number.parseFloat(text.replace(/[,+]/g, ""));
  if (Number.isNaN(number)) return 0;
  if (text.includes("w") || text.includes("万")) return number * 10000;
  if (text.includes("k")) return number * 1000;
  return number;
}

function updateCrawlerInsights(items) {
  if (!crawlerInsightList) return;
  crawlerInsightList.innerHTML = "";
  const safeItems = (items || []).filter(Boolean);
  if (safeItems.length === 0) {
    const empty = document.createElement("span");
    empty.textContent = "还没有可总结的样本。";
    crawlerInsightList.append(empty);
    return;
  }
  safeItems.forEach((item) => {
    const line = document.createElement("span");
    line.textContent = item;
    crawlerInsightList.append(line);
  });
}

function setCrawlerStatusText(element, text) {
  if (element) element.textContent = text;
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
    "realtime_research_max_notes",
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
    realtime_research_max_notes: "检索条数",
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
  setEventIcon(icon, kind);
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
  return row;
}

function upsertAgentNodeEvent(event) {
  if (!activeAgentMessage) return;
  const key = event.node || event.label;
  let row = activeNodeRows.get(key);
  if (!row) {
    row = document.createElement("div");
    row.className = "event-row event-pending";
    row.dataset.node = key;
    const icon = document.createElement("span");
    icon.className = "event-icon";
    setEventIcon(icon, "pending");
    const body = document.createElement("div");
    body.className = "event-body";
    const strong = document.createElement("strong");
    strong.textContent = event.label || key;
    const small = document.createElement("small");
    small.className = "typewriter";
    body.append(strong, small);
    row.append(icon, body);
    activeAgentMessage.feed.append(row);
    activeNodeRows.set(key, row);
  }
  const isDone = event.status === "done";
  row.className = `event-row ${isDone ? "event-done" : "event-pending"}`;
  setEventIcon(row.querySelector(".event-icon"), isDone ? "done" : "pending");
  const small = row.querySelector("small");
  streamPlainTokens(small, event.message || (isDone ? "已完成" : "处理中"));
  conversation.scrollTop = conversation.scrollHeight;
}

function setEventIcon(icon, kind) {
  if (!icon) return;
  icon.innerHTML = "";
  if (kind === "pending") {
    icon.append(document.createElement("span"), document.createElement("span"), document.createElement("span"));
    return;
  }
  icon.textContent = kind === "done" ? "✓" : kind === "error" ? "!" : kind === "decision" ? "→" : "…";
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
  activeNodeRows = new Map();
}

function resetRun(options = {}) {
  titleOutput.textContent = "标题生成中...";
  bodyOutput.textContent = "正文生成中...";
  tagOutput.textContent = "标签生成中...";
  outputState.textContent = "streaming";
  outputParts = { titles: "", body: "", tags: "" };
  latestResult = null;
  if (!options.preserveCrawler) {
    resetCrawlerPanel();
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/ui/status");
    if (!response.ok) return null;
    const data = await response.json();
    latestWorkbenchStatus = data;
    updateWorkbenchStatus(data);
    return data;
  } catch {
    setCrawlerStatusText(xhsAuthState, "Unknown");
    setCrawlerStatusText(chromeState, "Unknown");
    return null;
  }
}

async function ensureXhsLoginBeforeRun() {
  const status = await refreshStatus();
  if (isXhsLoggedIn(status)) return true;

  isLoginPending = true;
  outputState.textContent = "login";
  openLoginGate();
  syncSubmitAvailability();

  try {
    const session = await requestXhsLoginSession();
    if (!session?.session_id) {
      updateLoginGateStatus(session?.message || "无法打开 Chrome 登录窗口，请检查小红书环境配置。");
      outputState.textContent = "error";
      await sleep(1600);
      closeLoginGate();
      return false;
    }
    updateLoginGateStatus("Chrome 登录窗口已启动，等待扫码登录。");
    const loginReady = await waitForXhsLogin(session.session_id);
    if (loginReady) {
      updateLoginGateStatus("已检测到登录态，开始运行 Agent。");
      await sleep(350);
      closeLoginGate();
      return true;
    }
    outputState.textContent = "error";
    await sleep(1200);
    closeLoginGate();
    return false;
  } catch (error) {
    updateLoginGateStatus(error.message || String(error));
    outputState.textContent = "error";
    await sleep(1600);
    closeLoginGate();
    return false;
  } finally {
    isLoginPending = false;
    syncSubmitAvailability();
  }
}

function isXhsLoggedIn(status) {
  const auth = status?.xhs_auth || latestWorkbenchStatus?.xhs_auth || {};
  return Boolean(auth.available || auth.verified);
}

async function requestXhsLoginSession() {
  const response = await fetch("/ui/xhs/login/qrcode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ timeout_seconds: LOGIN_WORKER_TIMEOUT_SECONDS }),
  });
  if (!response.ok) {
    throw new Error(`登录窗口启动失败：${response.status}`);
  }
  return response.json();
}

async function waitForXhsLogin(sessionId) {
  const countdownDeadline = Date.now() + LOGIN_GATE_SECONDS * 1000;
  let countdownExpired = false;
  while (true) {
    await sleep(1800);
    const status = await refreshStatus();
    if (isXhsLoggedIn(status)) return true;
    const session = await pollLoginSession(sessionId);
    if (session?.status === "logged_in") return true;
    if (session?.message) {
      updateLoginGateStatus(session.message);
    }
    if (["error", "blocked", "timeout", "missing"].includes(session?.status)) {
      updateLoginGateStatus(session.message || "登录流程中断，请刷新页面后重新运行。");
    } else if (!countdownExpired && Date.now() >= countdownDeadline) {
      countdownExpired = true;
      updateLoginGateStatus("120s 内未检测到登录，仍在持续检测登录态。");
    }
  }
}

async function pollLoginSession(sessionId) {
  if (!sessionId) return null;
  try {
    const response = await fetch(`/ui/xhs/login/${encodeURIComponent(sessionId)}`);
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

function openLoginGate() {
  startLoginCountdown();
  updateLoginGateStatus("正在打开 Chrome 登录窗口...");
  loginGate?.classList.add("is-open");
  loginGate?.setAttribute("aria-hidden", "false");
}

function closeLoginGate() {
  window.clearInterval(loginCountdownTimer);
  loginCountdownTimer = null;
  loginGate?.classList.remove("is-open");
  loginGate?.setAttribute("aria-hidden", "true");
}

function startLoginCountdown() {
  const deadline = Date.now() + LOGIN_GATE_SECONDS * 1000;
  const tick = () => {
    const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    if (loginCountdown) loginCountdown.textContent = String(left);
  };
  window.clearInterval(loginCountdownTimer);
  tick();
  loginCountdownTimer = window.setInterval(tick, 250);
}

function updateLoginGateStatus(message) {
  if (loginGateStatus) {
    loginGateStatus.textContent = message || "等待登录检测...";
  }
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function initHistoryHint() {
  if (!historyToggle) return;
  historyToggle.classList.add("history-attention");
  historyToggle.title = "点击打开历史对话";
}

function flashPanel(panel, kind) {
  if (!panel) return;
  const className = `panel-flash-${kind}`;
  panel.classList.remove(className);
  void panel.offsetWidth;
  panel.classList.add(className);
  window.setTimeout(() => panel.classList.remove(className), 1700);
}

function updateWorkbenchStatus(data) {
  const auth = data?.xhs_auth || {};
  const browser = data?.persistent_browser || {};
  if (auth.verified || auth.available) {
    setCrawlerStatusText(xhsAuthState, auth.verified ? "已验证" : "Cookie ready");
  } else if (auth.has_web_session) {
    setCrawlerStatusText(xhsAuthState, "待验证");
  } else {
    setCrawlerStatusText(xhsAuthState, "未登录");
  }
  const browserStatus = String(browser.status || "stopped");
  const browserLabels = {
    logged_in: "已连接",
    browser_ready: "运行中",
    starting: "启动中",
    qrcode_ready: "扫码中",
    stopped: "未运行",
    error: "异常",
    blocked: "受限",
    timeout: "超时",
  };
  const label = browserLabels[browserStatus] || browserStatus;
  const pid = browser.pid ? ` #${browser.pid}` : "";
  setCrawlerStatusText(chromeState, `${label}${pid}`);
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
  items.forEach((item) => historyList.append(createHistoryConversationCard(item)));
}

function createHistoryConversationCard(item) {
  const card = document.createElement("article");
  card.className = "history-conversation-card";

  const head = document.createElement("div");
  head.className = "history-conversation-head";

  const titleButton = document.createElement("button");
  titleButton.className = "history-conversation-title";
  titleButton.type = "button";
  titleButton.innerHTML = `
    <strong>${escapeHtml(item.title || "未命名对话")}</strong>
    <small>${item.turn_count || 0} 轮 · ${escapeHtml(formatTime(item.updated_at))}</small>
  `;
  titleButton.addEventListener("click", () => restoreConversation(item.id));

  const deleteButton = document.createElement("button");
  deleteButton.className = "history-delete-button";
  deleteButton.type = "button";
  deleteButton.setAttribute("aria-label", "删除历史对话");
  deleteButton.textContent = "×";
  deleteButton.addEventListener("click", async (event) => {
    event.stopPropagation();
    await deleteConversation(item.id, card);
  });

  head.append(titleButton, deleteButton);
  card.append(head);

  const turns = Array.isArray(item.turns) ? item.turns : [];
  const turnList = document.createElement("div");
  turnList.className = "history-turn-list";
  if (turns.length === 0) {
    const empty = document.createElement("div");
    empty.className = "history-turn-empty";
    empty.textContent = "暂无交互记录";
    turnList.append(empty);
  } else {
    turns.forEach((turn) => turnList.append(createHistoryTurnCard(item.id, turn)));
  }
  card.append(turnList);
  return card;
}

function createHistoryTurnCard(conversationID, turn) {
  const button = document.createElement("button");
  button.className = `history-turn-card history-turn-${turn.status || "unknown"}`;
  button.type = "button";
  button.innerHTML = `
    <span class="history-turn-index">#${turn.index || "?"}</span>
    <span class="history-turn-text">${escapeHtml(turn.message || "无新增要求")}</span>
    <span class="history-turn-reply">${escapeHtml(turn.reply_preview || "暂无回复")}</span>
  `;
  button.addEventListener("click", () => restoreConversation(conversationID, turn.id));
  return button;
}

async function deleteConversation(id, card) {
  if (!id) return;
  const response = await fetch(`/ui/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!response.ok) return;
  if (conversationId === id) {
    startNewConversation();
  }
  card?.remove();
  if (historyList && !historyList.querySelector(".history-conversation-card")) {
    historyList.innerHTML = '<div class="history-empty">暂无历史对话。</div>';
  }
}

async function restoreConversation(id, turnId = "") {
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
  const selectedTurn = turnId
    ? (record.turns || []).find((turn) => turn.id === turnId && turn.output_parts)
    : null;
  const outputTurn = selectedTurn || latestCompleted;
  if (outputTurn) {
    renderOutputParts(outputTurn.output_parts);
    latestResult = outputTurn.result || null;
    renderCrawlerFromResult(latestResult);
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
  resetCrawlerPanel();
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
  if (crawlLimitInput) {
    crawlLimitInput.value = clampNumber(input?.realtime_research_max_notes, 1, 30, 20);
  }
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
