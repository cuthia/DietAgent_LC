"use strict";

/* ==================== 工具函数 ==================== */
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
function escapeHtml(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText)
    return navigator.clipboard.writeText(text).then(()=>true).catch(()=>_fc(text));
  return Promise.resolve(_fc(text));
}
function _fc(t){ try { const ta = document.createElement("textarea"); ta.value = t; ta.style.cssText = "position:fixed;opacity:0"; document.body.appendChild(ta); ta.select(); const ok = document.execCommand("copy"); document.body.removeChild(ta); return ok; } catch(e) { return false; } }
function uid() { return "s_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2,7); }

/* ==================== Toast ==================== */
function toast(msg, type="info") {
  const colors = { info:"bg-gray-900", success:"bg-green-600", error:"bg-red-500", warn:"bg-amber-500" };
  const el = document.createElement("div");
  el.className = `toast ${colors[type]||colors.info} text-white text-[13px] px-4 py-2.5 rounded-xl shadow-lg`;
  el.textContent = msg;
  $("#toast-container").appendChild(el);
  setTimeout(() => el.remove(), 2600);
}

/* ==================== Markdown 渲染 ==================== */
marked.setOptions({ breaks: true, gfm: true, highlight:(code,lang) => {
  try { if (lang && hljs.getLanguage(lang)) return hljs.highlight(code,{language:lang}).value; return hljs.highlightAuto(code).value; } catch(e){ return code; }
}});
function renderMarkdown(md) {
  const tmp = document.createElement("div");
  tmp.innerHTML = marked.parse(md || "");
  tmp.querySelectorAll("pre").forEach(pre => {
    const codeEl = pre.querySelector("code");
    const txt = (codeEl ? codeEl.innerText : pre.innerText) || "";
    const btn = document.createElement("button");
    btn.className = "code-copy-btn"; btn.textContent = "复制"; btn.type = "button";
    btn.addEventListener("click", e => { e.preventDefault(); e.stopPropagation(); copyText(txt).then(ok => { btn.textContent = ok ? "已复制" : "复制失败"; setTimeout(()=>btn.textContent="复制",1400); }); });
    pre.appendChild(btn);
  });
  return tmp.innerHTML;
}
function renderDietPlan(plan) {
  if (!plan) return "";
  const meal = (label, icon) => {
    const m = plan[label];
    if (!m || !m.items || m.items.length === 0) return "";
    const itemsHtml = m.items.map(it =>
      `<div class="meal-item"><span class="name">${escapeHtml(it.name)}</span><span>${it.amount||""}${it.calories?` · ${it.calories}kcal`:""}</span></div>`
    ).join("");
    const lbl = label==="breakfast"?"早餐":label==="lunch"?"午餐":label==="dinner"?"晚餐":"加餐";
    return `<div style="margin-top:10px"><h4>${icon} ${lbl}</h4>${itemsHtml}</div>`;
  };
  const total = plan.total_calories ? `<div style="margin-top:10px;font-size:13px;color:#4E5969">🌡️ 全天总热量：<b style="color:#1F2329">${plan.total_calories} kcal</b></div>` : "";
  const tips = (plan.health_tips && plan.health_tips.length) ? `<div style="margin-top:10px;font-size:13px;color:#4E5969">💡 ${plan.health_tips.join(" / ")}</div>` : "";
  return `<div class="diet-card">${meal("breakfast","🌅")}${meal("lunch","☀️")}${meal("dinner","🌙")}${meal("snack","🍎")}${total}${tips}</div>`;
}

/* ==================== 状态 ==================== */
const API_BASE = "http://localhost:8000";
const K = { TOKEN:"dietagent_token", USER:"dietagent_user", SESSIONS:"dietagent_sessions", ACTIVE:"dietagent_active_session" };
const state = {
  token: localStorage.getItem(K.TOKEN) || "",
  user: JSON.parse(localStorage.getItem(K.USER) || "null"),
  sessions: JSON.parse(localStorage.getItem(K.SESSIONS) || "[]"),
  activeId: localStorage.getItem(K.ACTIVE) || null,
  view: "chat",
  generating: false,
  stopFlag: false,
};

/* ==================== API 封装 ==================== */
async function apiFetch(path, opts={}) {
  const url = API_BASE + path;
  const headers = { "Content-Type":"application/json", ...(opts.headers||{}) };
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  const resp = await fetch(url, { ...opts, headers });
  return { ok: resp.ok, status: resp.status, data: await resp.json().catch(()=>({})), raw: resp };
}
async function httpPing() { try { const r = await fetch(API_BASE + "/health"); return r.ok; } catch(e) { return false; } }

/* Auth */
async function apiLogin(username, password) {
  const r = await apiFetch("/api/user/login", { method:"POST", body: JSON.stringify({ username, password }) });
  if (r.ok && r.data.code === 200) {
    state.token = r.data.data.access_token;
    state.user = r.data.data.user_info;
    localStorage.setItem(K.TOKEN, state.token);
    localStorage.setItem(K.USER, JSON.stringify(state.user));
    return { ok: true };
  }
  return { ok:false, msg: r.data?.message || "登录失败" };
}
async function apiRegister(username, password) {
  const r = await apiFetch("/api/user/register", { method:"POST", body: JSON.stringify({ username, password }) });
  if (r.ok && r.data.code === 200) return { ok:true, data:r.data.data };
  return { ok:false, msg: r.data?.message || "注册失败" };
}

/* Profile */
async function apiGetProfile() {
  const r = await apiFetch("/api/user/profile");
  if (r.ok && r.data.code === 200) return r.data.data;
  return null;
}
async function apiUpdateProfile(data) {
  const r = await apiFetch("/api/user/profile", { method:"PUT", body: JSON.stringify(data) });
  if (r.ok && r.data.code === 200) return { ok:true, data:r.data.data };
  return { ok:false, msg: r.data?.message || "更新失败" };
}

/* Chat SSE */
async function apiStreamChat(userMessage, sessionId, onEvent, onDone) {
  const body = { user_id: state.user.id, message: userMessage, session_id: sessionId };
  try {
    const resp = await fetch(API_BASE + "/api/agent/chat/stream", {
      method:"POST", 
      headers:{
        "Content-Type":"application/json",
        ...(state.token ? { "Authorization": "Bearer " + state.token } : {})
      }, 
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalData = null;
    let stageMsg = "";
    while (true) {
      if (state.stopFlag) { try { reader.cancel(); } catch(_){} break; }
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream:true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();
      for (const part of parts) {
        const lines = part.split("\n");
        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const str = line.slice(5).trim();
          if (!str || str === "[DONE]") continue;
          try {
            const evt = JSON.parse(str);
            if (evt.done) { onDone && onDone(finalData); return; }
            if (evt.stage === "output" && evt.status === "complete" && evt.data) finalData = evt.data;
            if (evt.message) stageMsg = evt.message;
            onEvent && onEvent(evt, stageMsg, finalData);
          } catch(e) {}
        }
      }
    }
    onDone && onDone(finalData);
  } catch(e) {
    onEvent && onEvent({ stage:"error", status:"error", message:e.message }, "", null);
    onDone && onDone(null);
  }
}

/* History */
async function apiGetHistory(userId, maxMessages=50) {
  const r = await apiFetch(`/api/agent/user/${userId}/history?max_messages=${maxMessages}`);
  if (r.ok && r.data.messages) return r.data.messages;
  return [];
}
async function apiSaveDietPlan(plan) {
  const r = await apiFetch(`/api/agent/user/${state.user.id}/diet-history`, { method:"POST", body: JSON.stringify({ plan }) });
  return r.ok && r.data.success;
}
async function apiClearHistory(userId, sessionId="default") {
  const r = await apiFetch(`/api/agent/user/${userId}/history?session_id=${encodeURIComponent(sessionId)}`, { method:"DELETE" });
  return r.ok && r.data.success;
}
async function apiValidatePlan(dietPlan) {
  const r = await apiFetch("/api/agent/validate", { method:"POST", body: JSON.stringify({ user_id: state.user.id, diet_plan: dietPlan }) });
  return r.ok ? r.data : null;
}

/* Knowledge */
async function apiKnowledgeStats() {
  const r = await apiFetch("/api/knowledge/stats");
  return (r.ok && r.data.code === 200) ? r.data.data : null;
}
async function apiKnowledgeList() { const r = await apiFetch("/api/knowledge/list"); return r.ok ? r.data : null; }
async function apiKnowledgeSearch(query, top_k=5) {
  const r = await apiFetch(`/api/knowledge/search?query=${encodeURIComponent(query)}&top_k=${top_k}`);
  return (r.ok && r.data.code === 200) ? r.data.data.documents || [] : [];
}
async function apiKnowledgeUpload(file, category="营养学") {
  const fd = new FormData(); fd.append("file", file); fd.append("category", category);
  const resp = await fetch(API_BASE + "/api/knowledge/upload", { method:"POST", headers: state.token ? { Authorization:"Bearer " + state.token } : {}, body: fd });
  return resp.ok;
}
async function apiKnowledgeDelete(docId) { const r = await apiFetch(`/api/knowledge/${encodeURIComponent(docId)}`, { method:"DELETE" }); return r.ok; }
async function apiKnowledgeClear() { const r = await apiFetch("/api/knowledge/clear", { method:"DELETE" }); return r.ok; }

/* ==================== 会话管理 ==================== */
function saveSessions() { localStorage.setItem(K.SESSIONS, JSON.stringify(state.sessions)); }
function saveActive() { if (state.activeId) localStorage.setItem(K.ACTIVE, state.activeId); }
function getActiveSession() { return state.sessions.find(s => s.id === state.activeId) || state.sessions[0] || null; }

function createSession() {
  const s = { id: uid(), title: "新对话", messages: [], updatedAt: Date.now() };
  state.sessions.unshift(s); state.activeId = s.id;
  saveSessions(); saveActive();
  return s;
}
function deleteSession(id) {
  const idx = state.sessions.findIndex(s => s.id === id);
  if (idx === -1) return;
  state.sessions.splice(idx, 1);
  if (state.activeId === id) state.activeId = state.sessions[0]?.id || null;
  if (!state.activeId) createSession();
  saveSessions(); saveActive();
}
function saveMsg(sessionId, role, content, extra={}) {
  const s = state.sessions.find(s => s.id === sessionId);
  if (!s) return;
  s.messages.push({ role, content, ...extra });
  if (role === "user") {
    const t = content.replace(/\s+/g," ").trim();
    if (t.length > 0 && (s.title === "新对话" || s.title.length === 0)) s.title = t.length > 18 ? t.slice(0,18) + "…" : t;
  }
  s.updatedAt = Date.now();
  saveSessions();
}

/* ==================== 侧边栏渲染 ==================== */
function renderSidebar() {
  const logged = !!state.user;
  $("#nav-tabs").classList.toggle("hidden", !logged);
  $("#chat-section").classList.toggle("hidden", !logged);

  const hl = $("#history-list");
  if (!logged) {
    hl.innerHTML = `<div class="text-center py-6 text-[13px] text-slate-400">登录后开始对话<br>历史记录将显示在这里</div>`;
  } else {
    if (state.sessions.length === 0) createSession();
    const sorted = [...state.sessions].sort((a,b) => (b.updatedAt||0) - (a.updatedAt||0));
    hl.innerHTML = sorted.map(s => {
      const active = s.id === state.activeId;
      return `<div class="group relative">
        <button data-sid="${s.id}" class="w-full text-left h-10 rounded-lg px-3 flex items-center gap-2 transition ${active ? "bg-sidebar-700/80 text-white" : "text-slate-200 hover:bg-sidebar-700/40"}">
          <svg class="shrink-0 w-[16px] h-[16px] opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <span class="sb-text text-[13px] truncate flex-1">${escapeHtml(s.title || "新对话")}</span>
        </button>
        <button data-del="${s.id}" class="hidden group-hover:flex absolute right-1 top-1/2 -translate-y-1/2 w-6 h-6 rounded hover:bg-red-500/20 items-center justify-center text-slate-400 hover:text-red-300">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/></svg>
        </button>
      </div>`;
    }).join("");
  }

  $("#btn-login-sidebar").classList.toggle("hidden", logged);
  $("#btn-logout").classList.toggle("hidden", !logged);
  if (logged) {
    $("#user-name").textContent = state.user.username;
    $("#user-sub").textContent = "ID: " + state.user.id;
    $("#user-avatar").textContent = state.user.username.charAt(0).toUpperCase();
  } else {
    $("#user-name").textContent = "未登录";
    $("#user-sub").textContent = "请先登录";
    $("#user-avatar").textContent = "U";
  }

  $$("#history-list [data-sid]").forEach(b => b.addEventListener("click", () => {
    state.activeId = b.getAttribute("data-sid"); saveActive(); renderSidebar(); renderMessages();
  }));
  $$("#history-list [data-del]").forEach(b => b.addEventListener("click", e => {
    e.stopPropagation(); deleteSession(b.getAttribute("data-del")); renderSidebar();
  }));
}

/* ==================== 消息渲染 ==================== */
function renderOneMsg(m, idx) {
  if (m.role === "user") {
    return `<div class="msg-wrap flex justify-end" data-idx="${idx}">
      <div class="flex max-w-[78%] md:max-w-[72%] items-start gap-3 justify-end">
        <div class="rounded-2xl rounded-tr-md px-4 py-2.5 bg-userbubble text-[15px] text-gray-900 leading-[1.7] whitespace-pre-wrap break-words shadow-[0_1px_2px_rgba(0,0,0,0.03)]">${escapeHtml(m.content)}</div>
        <div class="w-9 h-9 shrink-0 rounded-full bg-gradient-to-br from-sky-500 to-indigo-600 text-white text-[13px] font-medium flex items-center justify-center select-none">U</div>
      </div></div>`;
  }
  const cursor = m.streaming ? '<span class="typing-cursor"></span>' : "";
  const planHtml = m.diet_plan ? renderDietPlan(m.diet_plan) : "";
  const mdContent = m.content ? renderMarkdown(m.content) : "";
  return `<div class="msg-wrap flex justify-start" data-idx="${idx}">
    <div class="w-full">
      <div class="flex items-start gap-3 md:gap-4">
        <div class="w-9 h-9 shrink-0 rounded-xl2 bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center text-white font-bold select-none">D</div>
        <div class="flex-1 min-w-0">
          <div class="md-body">${mdContent}${cursor}${planHtml}</div>
          <div class="msg-actions flex items-center gap-1 mt-2">
            <button class="act-copy h-8 px-2.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-700 text-[12.5px] flex items-center gap-1">
              <svg class="w-[14px] h-[14px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              复制
            </button>
            ${m.diet_plan ? `<button class="act-save-plan h-8 px-2.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-700 text-[12.5px] flex items-center gap-1">
              <svg class="w-[14px] h-[14px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
              保存方案
            </button>` : ""}
          </div>
        </div>
      </div>
    </div></div>`;
}

function renderMessages() {
  const chat = getActiveSession();
  const elW = $("#welcome"), elM = $("#messages");
  $("#chat-title").textContent = chat ? (chat.title || "新对话") : "新对话";
  if (!chat || chat.messages.length === 0) { elW.classList.remove("hidden"); elM.innerHTML = ""; return; }
  elW.classList.add("hidden");
  elM.innerHTML = chat.messages.map((m, i) => renderOneMsg(m, i)).join("");
  bindMsgActions();
  scrollToBottom(!chat.messages.some(m => m.streaming));
}

function bindMsgActions() {
  const chat = getActiveSession(); if (!chat) return;
  const idxList = $$("#messages [data-idx]").map(e => +e.getAttribute("data-idx"));
  $$(".act-copy").forEach((btn, i) => btn.addEventListener("click", () => {
    const msg = chat.messages[idxList[i]]; if (!msg) return;
    copyText(msg.content || "").then(ok => {
      const last = btn.childNodes[btn.childNodes.length - 1];
      if (last) { const orig = last.textContent; last.textContent = ok ? "已复制" : "失败"; setTimeout(()=>last.textContent=orig,1200); }
    });
  }));
  $$(".act-save-plan").forEach((btn, i) => btn.addEventListener("click", async () => {
    const msg = chat.messages[idxList[i]]; if (!msg || !msg.diet_plan) return;
    const ok = await apiSaveDietPlan(msg.diet_plan);
    toast(ok ? "方案已保存" : "保存失败", ok ? "success" : "error");
  }));
}

function scrollToBottom(smooth) {
  const el = $("#chat-scroll");
  try { el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" }); } catch(e) { el.scrollTop = el.scrollHeight; }
}

/* ==================== 发送消息 ==================== */
async function sendMessage() {
  if (state.generating) return;
  if (!state.user) { openAuthModal("login"); return; }
  const val = $("#input").value.trim(); if (!val) return;

  let chat = getActiveSession();
  if (!chat) { chat = createSession(); renderSidebar(); }

  saveMsg(chat.id, "user", val);
  renderSidebar(); renderMessages();
  $("#input").value = ""; autoResize();

  const aiMsg = { role:"assistant", content:"", streaming:true, diet_plan:null };
  chat.messages.push(aiMsg);
  const msgIdx = chat.messages.length - 1;

  state.generating = true; state.stopFlag = false;
  $("#btn-send").disabled = true; $("#btn-stop").classList.remove("hidden");

  const backendOk = await httpPing();
  if (!backendOk) {
    // 后端离线 → mock 降级
    await mockReply(val, aiMsg);
    aiMsg.streaming = false;
    renderMessages();
    state.generating = false; state.stopFlag = false;
    $("#btn-send").disabled = false; $("#btn-stop").classList.add("hidden");
    saveSessions();
    return;
  }

  try {
    let streamStarted = false; // 最终答复流式输出是否已开始
    await apiStreamChat(val, chat.id,
      (evt, stageMsg, finalData) => {
        // --- 最终答复逐字流：优先处理
        if (evt.stage === "finalize" && evt.status === "stream" && typeof evt.chunk === "string") {
          if (!streamStarted) {
            // 第一次收到答复 chunk：清空之前的阶段提示消息
            aiMsg.content = "";
            streamStarted = true;
          }
          aiMsg.content += evt.chunk;
          renderMessages();
          return;
        }
        // --- finalize start：提示"正在整理答复"，但随后会被 stream 清空
        if (evt.stage === "finalize" && evt.status === "start" && !streamStarted) {
          aiMsg.content = aiMsg.content + (aiMsg.content ? "\n\n" : "") + `> ${stageMsg || "正在整理最终答复..."}`;
          renderMessages();
          return;
        }

        // --- 阶段 start：追加提示（仅当还未进入流式答复阶段）
        if (evt.status === "start" && evt.stage && !streamStarted) {
          aiMsg.content = aiMsg.content + (aiMsg.content ? "\n\n" : "") + `> ${stageMsg || ("正在处理：" + evt.stage)}`;
        }
        if (evt.status === "complete" && evt.stage === "output" && finalData) {
          if (!streamStarted) {
            // 没进过流式（例如失败/追问）：直接用完整消息
            aiMsg.content = finalData.message || aiMsg.content;
          } else {
            // 流式已经渲染过了；如果 finalData 非空且流式内容为空才覆盖（保险）
            if (!aiMsg.content) aiMsg.content = finalData.message || "";
          }
          if (finalData.diet_plan) aiMsg.diet_plan = finalData.diet_plan;
          if (finalData.need_info && finalData.follow_up) aiMsg.content = finalData.follow_up;
        } else if (evt.status === "complete" && stageMsg && !finalData && !aiMsg.diet_plan && !streamStarted) {
          aiMsg.content = stageMsg;
        }
        if (evt.status === "error") aiMsg.content = "⚠️ 服务异常：" + (evt.message || "未知错误");
        renderMessages();
      },
      (finalData) => {
        if (finalData) {
          aiMsg.content = finalData.message || aiMsg.content;
          if (finalData.need_info && finalData.follow_up) aiMsg.content = finalData.follow_up;
          if (finalData.diet_plan) aiMsg.diet_plan = finalData.diet_plan;
        }
        aiMsg.streaming = false;
        renderMessages();
        state.generating = false; state.stopFlag = false;
        $("#btn-send").disabled = false; $("#btn-stop").classList.add("hidden");
        saveSessions();
      }
    );
  } catch(e) {
    aiMsg.content = "⚠️ 网络异常：" + e.message;
    aiMsg.streaming = false;
    renderMessages();
    state.generating = false; state.stopFlag = false;
    $("#btn-send").disabled = false; $("#btn-stop").classList.add("hidden");
    saveSessions();
  }
}

/* ==================== Mock 回复（后端离线降级） ==================== */
async function mockReply(userMsg, aiMsg) {
  const templates = [
    `收到你的消息：「${userMsg}」。\n\n这是一条离线模式的模拟回复。请启动后端服务（\`python run.py\`）后即可获得真实的 AI 膳食顾问服务。`,
    `我是 DietAgent 膳食顾问。\n\n关于「${userMsg}」，我建议你：\n\n1. **均衡饮食**：确保每餐包含蛋白质、碳水化合物和健康脂肪\n2. **多吃蔬菜水果**：每天至少 5 份不同颜色的蔬果\n3. **控制热量**：根据个人需求合理安排每日摄入\n4. **充足饮水**：每天保持 1500-2000ml 饮水量\n\n> 💡 启动后端后可获得个性化的膳食方案、营养分析和健康建议。`,
  ];
  const reply = templates[Math.floor(Math.random() * templates.length)];
  for (let i = 0; i < reply.length; i++) {
    if (state.stopFlag) break;
    aiMsg.content = reply.slice(0, i + 1);
    renderMessages();
    await new Promise(r => setTimeout(r, 15));
  }
}

/* ==================== 输入框 ==================== */
function autoResize() { const el = $("#input"); el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 200) + "px"; }
$("#input").addEventListener("input", autoResize);
$("#input").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMessage(); } });
$("#btn-send").addEventListener("click", sendMessage);
$("#btn-stop").addEventListener("click", () => { state.stopFlag = true; });
$$(".suggest-card").forEach(b => b.addEventListener("click", () => { $("#input").value = b.querySelector("div:first-child").textContent.trim(); sendMessage(); }));

/* ==================== 登录 Modal ==================== */
let authMode = "login";
function openAuthModal(mode="login") {
  authMode = mode;
  $("#auth-modal-title").textContent = mode === "login" ? "登录" : "注册";
  $("#auth-submit").textContent = mode === "login" ? "登录" : "注册";
  $$(".auth-tab").forEach(t => {
    const active = t.dataset.auth === mode;
    t.classList.toggle("tab-active", active);
    t.classList.toggle("text-gray-400", !active);
  });
  $("#auth-error").classList.add("hidden");
  $("#auth-modal").classList.remove("hidden");
}
function closeAuthModal() { $("#auth-modal").classList.add("hidden"); }
$$(".auth-tab").forEach(t => t.addEventListener("click", () => openAuthModal(t.dataset.auth)));
$("#auth-modal-close").addEventListener("click", closeAuthModal);
$("#auth-modal").addEventListener("click", e => { if (e.target.id === "auth-modal") closeAuthModal(); });
$("#btn-login-sidebar").addEventListener("click", () => openAuthModal("login"));

$("#auth-form").addEventListener("submit", async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const username = fd.get("username").trim();
  const password = fd.get("password");
  $("#auth-error").classList.add("hidden");

  if (authMode === "login") {
    const r = await apiLogin(username, password);
    if (r.ok) {
      toast("登录成功", "success");
      closeAuthModal();
      // 登录后加载后端历史，与本地会话合并（避免重复）
      try {
        const history = await apiGetHistory(state.user.id, 50);
        if (history && history.length > 0) {
          const bySession = {};
          history.forEach(m => {
            const sid = m.session_id || "default";
            if (!bySession[sid]) bySession[sid] = { id: uid(), title: sid === "default" ? "历史对话" : "会话 " + sid.slice(-4), messages: [], updatedAt: Date.now() };
            bySession[sid].messages.push({ role: m.role === "assistant" ? "assistant" : "user", content: m.content });
          });
          const existingContents = new Set(state.sessions.flatMap(s => s.messages.map(m => m.content)));
          Object.values(bySession).forEach(s => {
            const newContents = s.messages.map(m => m.content);
            const hasNew = newContents.some(c => !existingContents.has(c));
            if (hasNew) {
              // 仅当有新消息时才添加，避免重复
              state.sessions.unshift(s);
              s.messages.forEach(m => existingContents.add(m.content));
            }
          });
          state.activeId = state.sessions[0].id;
          saveSessions(); saveActive();
        }
      } catch(e) { /* 后端不可用时忽略 */ }
      if (!getActiveSession()) createSession();
      switchView("chat"); renderSidebar(); renderMessages();
    } else {
      const er = $("#auth-error"); er.textContent = r.msg; er.classList.remove("hidden");
    }
  } else {
    const r = await apiRegister(username, password);
    if (r.ok) { toast("注册成功，请登录", "success"); openAuthModal("login"); }
    else { const er = $("#auth-error"); er.textContent = r.msg; er.classList.remove("hidden"); }
  }
});

/* 登出 */
$("#btn-logout").addEventListener("click", () => {
  state.token = ""; state.user = null;
  localStorage.removeItem(K.TOKEN); localStorage.removeItem(K.USER);
  // 保留会话列表（方便下次登录查看）
  toast("已退出登录", "info");
  renderSidebar();
});

/* ==================== 视图切换 ==================== */
function switchView(view) {
  state.view = view;
  $$(".view").forEach(v => v.classList.add("hidden"));
  $("#view-" + view).classList.remove("hidden");
  $$(".nav-tab").forEach(t => {
    const active = t.dataset.view === view;
    t.classList.toggle("bg-sidebar-700/60", active);
    t.classList.toggle("text-white", active);
    t.classList.toggle("text-slate-300", !active);
  });
  if (view === "profile") loadProfile();
  if (view === "knowledge") loadKnowledge();
}
$$(".nav-tab").forEach(t => t.addEventListener("click", () => { if (!state.user) { openAuthModal("login"); return; } switchView(t.dataset.view); }));

/* ==================== 档案 ==================== */
async function loadProfile() {
  if (!state.user) return;
  const p = await apiGetProfile();
  if (p) {
    const form = $("#profile-form");
    Object.keys(p).forEach(k => { const el = form.elements[k]; if (el) el.value = p[k] ?? ""; });
  }
}
$("#profile-form").addEventListener("submit", async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const data = {};
  fd.forEach((v,k) => { if (v !== "") data[k] = (k==="age"||k==="height"||k==="weight") ? Number(v) : v; });
  const r = await apiUpdateProfile(data);
  toast(r.ok ? "保存成功" : (r.msg || "保存失败"), r.ok ? "success" : "error");
});
$("#btn-load-profile").addEventListener("click", loadProfile);

/* ==================== 知识库 ==================== */
let kbLoaded = false;
async function loadKnowledge() {
  if (!state.user) return;
  const stats = await apiKnowledgeStats();
  $("#kb-stats").textContent = stats
    ? `共 ${stats.total_count||0} 份文档 · ${Object.entries(stats.category_counts||{}).map(([k,v])=>`${k}:${v}`).join(" / ")}`
    : "暂无数据";

  const list = await apiKnowledgeList();
  const container = $("#kb-doc-list");
  if (!list || !list.documents || list.documents.length === 0) {
    container.innerHTML = `<div class="text-center py-8 text-[13px] text-gray-400">暂无文档，请先上传</div>`;
  } else {
    container.innerHTML = list.documents.map(d => `
      <div class="flex items-center justify-between p-3 rounded-xl border border-gray-100 hover:border-gray-200 hover:bg-gray-50 transition">
        <div class="flex items-center gap-3 min-w-0">
          <div class="w-9 h-9 rounded-lg bg-amber-50 flex items-center justify-center text-amber-600 shrink-0">📄</div>
          <div class="min-w-0"><div class="text-[13.5px] font-medium text-gray-900 truncate">${escapeHtml(d.title || d.id || "文档")}</div><div class="text-[12px] text-gray-500">${escapeHtml(d.category || "未分类")} · ${d.chunk_count || 0} 个分块</div></div>
        </div>
        <button data-del-doc="${escapeHtml(d.id)}" class="h-7 px-2 rounded-md text-[12px] text-red-400 hover:text-red-600 hover:bg-red-50 transition shrink-0">删除</button>
      </div>
    `).join("");
    $$("#kb-doc-list [data-del-doc]").forEach(b => b.addEventListener("click", async () => {
      const id = b.getAttribute("data-del-doc");
      const ok = await apiKnowledgeDelete(id);
      toast(ok ? "已删除" : "删除失败", ok ? "success" : "error");
      if (ok) loadKnowledge();
    }));
  }
  kbLoaded = true;
}
$("#kb-upload").addEventListener("change", async e => {
  const files = Array.from(e.target.files); if (!files.length) return;
  const cat = $("#kb-category").value;
  toast(`正在上传 ${files.length} 个文件...`, "info");
  let okCount = 0;
  for (const f of files) { if (await apiKnowledgeUpload(f, cat)) okCount++; }
  toast(`上传完成：${okCount}/${files.length}`, okCount === files.length ? "success" : "warn");
  e.target.value = "";
  loadKnowledge();
});
$("#kb-search-btn").addEventListener("click", async () => {
  const q = $("#kb-search-input").value.trim(); if (!q) return;
  toast("搜索中...", "info");
  const docs = await apiKnowledgeSearch(q, 5);
  const container = $("#kb-search-results");
  if (!docs.length) {
    container.innerHTML = `<div class="text-center py-4 text-[13px] text-gray-400">未找到相关内容</div>`;
  } else {
    container.innerHTML = docs.map(d => `
      <div class="p-3 rounded-xl border border-gray-100 bg-white">
        <div class="flex items-center justify-between mb-1">
          <div class="text-[13px] font-medium text-gray-900">${escapeHtml(d.metadata?.source || "文档片段")}</div>
          <div class="text-[11px] text-gray-400">相似度 ${(d.score*100).toFixed(1)}%</div>
        </div>
        <div class="text-[12.5px] text-gray-600 line-clamp-2">${escapeHtml(d.content.slice(0,200))}${d.content.length>200?"...":""}</div>
      </div>
    `).join("");
  }
});
$("#kb-clear-btn").addEventListener("click", async () => {
  if (!confirm("确认清空知识库所有文档？")) return;
  const ok = await apiKnowledgeClear();
  toast(ok ? "已清空" : "清空失败", ok ? "success" : "error");
  if (ok) loadKnowledge();
});

/* ==================== 侧边栏收缩 ==================== */
let collapsed = false;
function setCollapsed(c) {
  collapsed = c;
  const sb = $("#sidebar");
  const btn = $("#btn-expand");
  if (c) { sb.classList.remove("w-[260px]"); sb.classList.add("w-[64px]"); btn.classList.remove("hidden"); btn.classList.add("flex"); $$(".sb-text").forEach(n => n.classList.add("hidden")); }
  else { sb.classList.add("w-[260px]"); sb.classList.remove("w-[64px]"); btn.classList.add("hidden"); btn.classList.remove("flex"); $$(".sb-text").forEach(n => n.classList.remove("hidden")); }
}
$("#btn-collapse").addEventListener("click", () => setCollapsed(true));
$("#btn-expand").addEventListener("click", () => setCollapsed(false));
$("#btn-toggle").addEventListener("click", () => setCollapsed(!collapsed));
window.addEventListener("resize", () => { if (window.innerWidth < 768 && !collapsed) setCollapsed(true); });
if (window.innerWidth < 768) setCollapsed(true);

/* 新建对话按钮 - 点击创建新会话并切换到该对话（不跳转页面，仅重置当前对话视图） */
$("#btn-new-chat").addEventListener("click", () => {
  if (!state.user) { openAuthModal("login"); return; }
  createSession();
  renderSidebar();
  renderMessages();
  $("#input").focus();
  toast("已创建新对话", "info");
});

/* ==================== 连接状态 ==================== */
async function checkConn() {
  const ok = await httpPing();
  const badge = $("#conn-status");
  if (ok) {
    badge.classList.remove("hidden"); badge.classList.add("inline-flex");
    badge.querySelector("#conn-dot").className = "w-1.5 h-1.5 rounded-full bg-green-500";
    badge.querySelector("#conn-text").textContent = "后端已连接";
    badge.className = "inline-flex items-center gap-1.5 text-[12px] px-2.5 py-1 rounded-full bg-green-50 text-green-700 border border-green-200";
  } else {
    badge.classList.remove("hidden"); badge.classList.add("inline-flex");
    badge.querySelector("#conn-dot").className = "w-1.5 h-1.5 rounded-full bg-amber-500";
    badge.querySelector("#conn-text").textContent = "后端未连接（mock 模式）";
    badge.className = "inline-flex items-center gap-1.5 text-[12px] px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200";
  }
}

/* ==================== 启动 ==================== */
(function boot() {
  // 恢复登录态
  if (state.user) {
    // 验证 token 是否仍然有效
    apiGetProfile().then(p => {
      if (!p) {
        state.token = ""; state.user = null;
        localStorage.removeItem(K.TOKEN); localStorage.removeItem(K.USER);
        toast("登录已过期，请重新登录", "warn");
      }
      renderSidebar(); renderMessages();
    });
  }
  // 确保至少有一个会话
  if (!state.sessions.length) createSession();
  if (!state.activeId) state.activeId = state.sessions[0].id;

  renderSidebar(); renderMessages();
  $("#input").focus();
  checkConn();
  setInterval(checkConn, 30000);
})();
