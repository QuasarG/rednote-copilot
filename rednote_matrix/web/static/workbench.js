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

let activeAgentMessage = null;
let outputParts = { titles: "", body: "", tags: "" };

initTypewriters();

agentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formToPayload(event.currentTarget);
  resetRun();
  appendMessage("user", "User Request", summaryFromPayload(payload));
  activeAgentMessage = appendAgentEventMessage();
  submitButton.disabled = true;
  submitButton.querySelector("span").textContent = "运行中";

  try {
    await streamAgent(payload);
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector("span").textContent = "运行 Agent";
  }
});

importJsonButton.addEventListener("click", () => {
  jsonImportInput.click();
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
  promptInput.style.height = "auto";
  promptInput.style.height = `${Math.min(promptInput.scrollHeight, 120)}px`;
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
    promptInput.dispatchEvent(new Event("input"));
  }
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
    addAgentEvent("decision", "任务已接收", event.message);
    return;
  }
  if (event.type === "node") {
    updateNodeEvent(event);
    return;
  }
  if (event.type === "result") {
    renderDraft(event.result);
    outputState.textContent = "ready";
    finishAgentMessage();
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
}

async function refreshStatus() {
  await fetch("/ui/status");
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
