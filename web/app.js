/* 爆款拆解台 · 前端逻辑 */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const state = { jobId: null, timer: null, seen: 0, file: null };

async function api(path, opt) {
  const r = await fetch(path, opt);
  let d = {};
  try { d = await r.json(); } catch (e) { /* 忽略 */ }
  if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}

function logLine(line, cls) {
  const li = document.createElement("li");
  li.textContent = line;
  if (cls) li.classList.add(cls);
  $("#log").appendChild(li);
  $("#log").scrollTop = $("#log").scrollHeight;
}

function clsFor(line) {
  if (line.startsWith("✅")) return "l-done";
  if (line.includes("⚠️")) return "l-warn";
  if (/^[①②③④⑤]/.test(line)) return "l-step";
  if (line.startsWith("❌")) return "l-err";
  return "";
}

function resetLog() {
  $("#log").innerHTML = "";
  state.seen = 0;
}

function resetBtns() {
  $("#go-btn").disabled = false;
  $("#cancel-btn").hidden = true;
  $("#cancel-btn").disabled = false;
}

/* ── 初始化：读取配置状态 ─────────── */
async function initCfg() {
  try {
    const c = await api("/api/config");
    const issues = [];
    if (!c.llm_configured) issues.push("未配置 LLM Key");
    setupVisionPresets(c);
    if (!c.vision_available) {
      issues.push("未配置视觉模型");
      $("#vision").checked = false;
      $("#vision").disabled = true;
      $("#vision-note").hidden = false;
    }
    const dot = $("#cfg-dot");
    const tx = $("#cfg-text");
    if (c.cookiefile) $("#cookies-file").value = c.cookiefile;
    if (c.whisper_model) $("#whisper-model").value = c.whisper_model;
    if (c.transcribe_engine) $("#engine").value = c.transcribe_engine;
    if (issues.length) {
      dot.classList.add("amber");
      tx.textContent = issues.join(" / ");
    } else {
      dot.classList.add("ok");
      const parts = [c.llm_model || "LLM"];
      if (c.vision_available) parts.push("+" + c.vision_model);
      tx.textContent = "就绪 · " + parts.join(" ");
    }
  } catch (e) {
    $("#cfg-text").textContent = "配置读取失败：" + e.message;
  }
}

/* ── 视觉模型预设切换 ─────────────── */
function setupVisionPresets(c) {
  const field = $("#vision-model-field");
  const sel = $("#vision-model");
  const presets = c.vision_presets || [];
  if (!presets.length) {
    field.hidden = true;
    return;
  }
  sel.innerHTML = "";
  for (const p of presets) {
    const opt = document.createElement("option");
    opt.value = p.name;
    opt.textContent = p.name;
    if (p.model && p.model !== p.name) opt.textContent += ` · ${p.model}`;
    sel.appendChild(opt);
  }
  sel.value = c.vision_active || presets[0].name;
  field.hidden = false;
  sel.addEventListener("change", async () => {
    try {
      await api("/api/vision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: sel.value }),
      });
      logLine(`🔄 视觉模型已切换：${sel.value}`, "l-warn");
      initCfg();
    } catch (e) {
      logLine("❌ 切换视觉模型失败：" + e.message, "l-err");
      initCfg();
    }
  });
}

/* ── 拆解任务 ─────────────────────── */
$("#file-input").addEventListener("change", (ev) => {
  const f = ev.target.files[0] || null;
  state.file = f;
  $("#file-name").textContent = f
    ? `${f.name}（${(f.size / 1048576).toFixed(1)} MB）`
    : "未选择文件";
});

$("#analyze-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const url = $("#url").value.trim();
  const file = state.file;
  if (!/^https?:\/\//.test(url) && !file) {
    logLine("❌ 请粘贴 http(s) 开头的视频链接，或先选择本地视频文件", "l-err");
    return;
  }
  resetLog();
  $("#go-btn").disabled = true;
  $("#cancel-btn").hidden = false;
  try {
    const cf = $("#cookies-file").value.trim();
    if ($("#cookies-save").checked && cf) {
      api("/api/cookiefile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: cf }),
      }).catch(() => {});
    }
    let job_id;
    if (file && isImageFile(file.name)) {
      // 单图六维反推：上传图片 → 一次视觉调用 → 直接展示结果
      logLine(`🖼 单图反推：上传 ${file.name}…`, "l-warn");
      const d = await api("/api/analyze-image?name=" + encodeURIComponent(file.name), {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      });
      logLine("✅ 单图反推完成", "l-done");
      showSingleResult(d.result);
      resetBtns();
      return;
    } else if (file) {
      const params = new URLSearchParams({
        name: file.name,
        engine: $("#engine").value,
        whisper_model: $("#whisper-model").value,
        vision: $("#vision").checked ? "1" : "0",
      });
      logLine(`⬆ 上传本地文件：${file.name}（${(file.size / 1048576).toFixed(1)} MB）`, "l-warn");
      const d = await api("/api/upload?" + params.toString(), {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      });
      job_id = d.job_id;
      logLine("✅ 上传完成，开始拆解…", "l-done");
    } else {
      const body = {
        url,
        engine: $("#engine").value,
        whisper_model: $("#whisper-model").value,
        vision: $("#vision").checked,
        cookies_file: cf,
      };
      const d = await api("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      job_id = d.job_id;
    }
    state.jobId = job_id;
    poll();
  } catch (e) {
    logLine("❌ 提交失败：" + e.message, "l-err");
    resetBtns();
  }
});

$("#cancel-btn").addEventListener("click", async () => {
  if (!state.jobId) return;
  $("#cancel-btn").disabled = true;
  try {
    await api("/api/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: state.jobId }),
    });
    logLine("⏹ 已请求中止，等待当前步骤结束…", "l-warn");
  } catch (e) { /* 忽略 */ }
});

async function poll() {
  clearTimeout(state.timer);
  try {
    const s = await api("/api/status?id=" + state.jobId);
    const lines = s.progress || [];
    while (state.seen < lines.length) {
      logLine(lines[state.seen], clsFor(lines[state.seen]));
      state.seen++;
    }
    if (s.status === "running") {
      state.timer = setTimeout(poll, 1500);
      return;
    }
    if (s.status === "done") {
      showReport(s.report);
      resetBtns();
      return;
    }
    if (s.status === "error") {
      logLine("❌ " + (s.error || "未知错误"), "l-err");
      resetBtns();
      return;
    }
  } catch (e) {
    logLine("❌ 状态查询失败：" + e.message, "l-err");
    resetBtns();
  }
}

function showReport(report) {
  $("#work-empty").hidden = true;
  const el = $("#report");
  el.innerHTML = report.html;
  el.hidden = false;
  document.title = report.title + " · 拆片";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

const IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"];

function isImageFile(name) {
  const i = String(name).lastIndexOf(".");
  return i >= 0 && IMAGE_EXTS.includes(String(name).slice(i).toLowerCase());
}

function showSingleResult(r) {
  $("#work-empty").hidden = true;
  const el = $("#report");
  const qp = (r && r.quick_prompt && (r.quick_prompt.zh || r.quick_prompt.en)) || "";
  const escJson = (v) => esc(v == null ? "" : (typeof v === "string" ? v : JSON.stringify(v, null, 2)));
  const blocks = [];
  for (const [label, key] of [
    ["主体", "subject"], ["环境", "environment"], ["镜头语言", "camera"],
    ["光影", "lighting"], ["美术风格", "style"], ["氛围情绪", "mood"],
  ]) {
    const b = (r && r[key]) || {};
    const rows = Object.entries(b)
      .filter(([, v]) => v != null && v !== "")
      .map(([k, v]) => `<tr><td><b>${esc(k)}</b></td><td>${esc(v)}</td></tr>`)
      .join("");
    if (rows) blocks.push(`<h3>${label}</h3><table>${rows}</table>`);
  }
  const neg = (r && r.negative_prompt) || "";
  const params = (r && r.params) || {};
  const paramLine = Object.entries(params)
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => `${esc(k)} ${esc(v)}`)
    .join(" ｜ ");
  el.innerHTML = `
    <h2>🖼 单图六维反推结果</h2>
    ${qp ? `<p><b>📌 快速提示词（可直接粘贴）</b></p><pre>${esc(qp)}</pre>` : ""}
    ${r && r.description_zh ? `<p><b>画面深度描述</b></p><p>${esc(r.description_zh)}</p>` : ""}
    ${blocks.join("")}
    ${neg ? `<p><b>🚫 负面提示词</b>　${esc(neg)}</p>` : ""}
    ${paramLine ? `<p><b>🔧 参数建议</b>　${paramLine}</p>` : ""}
    ${r && r.recreate_notes ? `<p><b>💡 复刻建议</b>　${esc(r.recreate_notes)}</p>` : ""}
    ${r ? `<details><summary>查看原始 JSON</summary><pre>${escJson(r)}</pre></details>` : ""}`;
  el.hidden = false;
  document.title = "单图反推 · 拆片";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ── 标签切换 ─────────────────────── */
$$(".tab").forEach((t) =>
  t.addEventListener("click", () => switchTab(t.dataset.tab))
);

function switchTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("is-active", t.dataset.tab === name));
  $$(".panel").forEach((p) => (p.hidden = p.id !== "panel-" + name));
  if (name === "hooks") loadLib("hooks");
  if (name === "prompts") loadLib("prompts");
  if (name === "history") loadHistory();
}

/* ── 钩子库 / 提示词库 ────────────── */
async function loadLib(kind) {
  const list = $("#" + kind + "-list");
  const empty = $("#" + kind + "-empty");
  const q = ($("#" + kind + "-search input").value || "").trim();
  list.innerHTML = "";
  let results = [];
  try {
    const d = await api(`/api/${kind}?q=${encodeURIComponent(q)}`);
    results = d.results || [];
  } catch (e) {
    list.innerHTML = `<p class="lib-empty">加载失败：${e.message}</p>`;
    return;
  }
  empty.hidden = results.length > 0;
  list.hidden = results.length === 0;
  if (kind === "hooks") renderHooks(results, list);
  else renderPrompts(results, list);
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function escAttr(s) {
  return esc(s).replace(/"/g, "&quot;");
}

function renderHooks(items, list) {
  for (const r of items) {
    const div = document.createElement("div");
    div.className = "lib-item";
    const reuse = (r.reusable || []).filter(Boolean).slice(0, 3);
    div.innerHTML = `
      <p class="lib-item-title">${esc(r.title || "未命名")}</p>
      <p class="lib-item-meta">${esc(r.date)} · ${esc(r.platform || "")} · ${esc(r.url || "")}</p>
      <p class="lib-item-line"><b>钩子类型</b>　<span class="tag">${esc(r.hook_type || "-")}</span></p>
      <p class="lib-item-line"><b>一句话钩子</b>　${esc(r.hook_one_liner || "-")}</p>
      ${r.hook_formula ? `<p class="lib-item-line"><b>钩子公式</b>　${esc(r.hook_formula)}</p>` : ""}
      ${reuse.map((x) => `<p class="lib-item-line"><b>可复用</b>　${esc(x)}</p>`).join("")}
      ${r.transfer_topic ? `<p class="lib-item-line"><b>可迁移</b>　${esc(r.transfer_topic)}</p>` : ""}
      <p class="lib-item-actions">
        <button class="btn btn-ghost btn-sm lib-del" data-act="del" data-kind="hooks" data-id="${escAttr(r.id || "")}">删除</button>
      </p>`;
    div.addEventListener("click", (ev) => {
      if (ev.target.closest("button")) return;
      openUrl(r.url);
    });
    list.appendChild(div);
  }
}

function renderPrompts(items, list) {
  for (const r of items) {
    const div = document.createElement("div");
    div.className = "lib-item";
    const kws = (r.style_keywords || []).slice(0, 8).map((k) => `<span class="tag">${esc(k)}</span>`).join(" ");
    div.innerHTML = `
      <p class="lib-item-title">${esc(r.title || "未命名")}</p>
      <p class="lib-item-meta">${esc(r.date)} · ${esc(r.platform || "")} · ${esc(r.url || "")}</p>
      <p class="lib-item-line"><b>类型判断</b>　${esc(r.video_type || "-")}</p>
      ${(r.quick_zh || r.quick_en) ? `<p class="lib-item-line"><b>快速提示词</b>　${esc(r.quick_zh || r.quick_en)}</p>` : ""}
      ${r.negative_prompt ? `<p class="lib-item-line"><b>负面提示词</b>　${esc(r.negative_prompt)}</p>` : ""}
      ${r.overall_zh ? `<p class="lib-item-line"><b>整体提示词(ZH)</b>　${esc(r.overall_zh)}</p>` : ""}
      ${kws ? `<p class="lib-item-line"><b>风格</b>　${kws}</p>` : ""}
      ${r.recreate_notes ? `<p class="lib-item-line"><b>复刻建议</b>　${esc(r.recreate_notes)}</p>` : ""}
      <p class="lib-item-actions">
        <button class="btn btn-ghost btn-sm" data-act="rewrite" data-url="${escAttr(r.url || "")}">
          ${r.pack ? "重新改写提示词包" : "改写为可直接用的提示词包"}
        </button>
        <button class="btn btn-ghost btn-sm lib-del" data-act="del" data-kind="prompts" data-id="${escAttr(r.id || "")}">删除</button>
      </p>
      ${r.pack ? packBlock(r.pack) : ""}`;
    div.addEventListener("click", (ev) => {
      if (ev.target.closest("button")) return;
      openUrl(r.url);
    });
    list.appendChild(div);
  }
}

function packBlock(p) {
  const rows = [
    ["Seedance 2.0/2.5（中文，直接粘贴）", p.seedance_zh],
    ["Seedance（英文）", p.seedance_en],
    ["可灵（中文，直接粘贴）", p.kling_zh],
    ["可灵（英文）", p.kling_en],
    ["即梦（中文，直接粘贴）", p.jimeng_zh],
    ["负向提示词", p.negative],
  ];
  const params = p.params
    ? `<p class="pack-params">参数建议：${esc(Object.entries(p.params).map(([k, v]) => `${k} ${v}`).join(" ｜ "))}</p>`
    : "";
  return `
    <div class="pack">
      <p class="pack-title">提示词包 · 已按生成工具改写</p>
      ${rows
        .filter(([, v]) => v)
        .map(
          ([label, v]) => `
        <div class="pack-row">
          <span class="pack-label">${esc(label)}</span>
          <pre class="pack-pre">${esc(v)}</pre>
          <button class="btn btn-ghost btn-sm" data-act="copy" data-text="${escAttr(v)}">复制</button>
        </div>`
        )
        .join("")}
      ${params}
    </div>`;
}

async function doRewrite(btn) {
  const url = btn.dataset.url;
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = "改写中…";
  try {
    await api("/api/rewrite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    logLine("✅ 提示词包已生成（消耗一次 LLM 调用）", "l-done");
    await loadLib("prompts");
  } catch (e) {
    btn.disabled = false;
    btn.textContent = old;
    logLine("❌ 改写失败：" + e.message, "l-err");
  }
}

async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  const old = btn.textContent;
  btn.textContent = "已复制 ✓";
  setTimeout(() => (btn.textContent = old), 1200);
}

async function doDelete(btn) {
  const kind = btn.dataset.kind;
  const id = btn.dataset.id;
  if (!confirm(`确定删除这条${kind === "hooks" ? "钩子" : "提示词"}记录？\n（只删库记录，历史报告与汇总表不受影响）`)) return;
  btn.disabled = true;
  try {
    const d = await api("/api/library/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, ids: [id] }),
    });
    logLine(`🗑 已删除 ${d.removed} 条${kind === "hooks" ? "钩子" : "提示词"}记录`, "l-warn");
    await loadLib(kind);
  } catch (e) {
    btn.disabled = false;
    logLine("❌ 删除失败：" + e.message, "l-err");
  }
}

document.addEventListener("click", (ev) => {
  const btn = ev.target.closest("button[data-act]");
  if (!btn) return;
  if (btn.dataset.act === "rewrite") doRewrite(btn);
  if (btn.dataset.act === "copy") copyText(btn.dataset.text, btn);
  if (btn.dataset.act === "del") doDelete(btn);
});

function openUrl(url) {
  if (url) window.open(url, "_blank", "noopener");
}

$("#hooks-search").addEventListener("submit", (ev) => { ev.preventDefault(); loadLib("hooks"); });
$("#prompts-search").addEventListener("submit", (ev) => { ev.preventDefault(); loadLib("prompts"); });

/* ── 历史报告 ─────────────────────── */
async function loadHistory() {
  const list = $("#history-list");
  const empty = $("#history-empty");
  list.innerHTML = "";
  let reports = [];
  try {
    reports = await api("/api/reports");
  } catch (e) {
    list.innerHTML = `<p class="lib-empty">加载失败：${e.message}</p>`;
    return;
  }
  empty.hidden = reports.length > 0;
  list.hidden = reports.length === 0;
  for (const r of reports) {
    const div = document.createElement("div");
    div.className = "lib-item";
    div.innerHTML = `
      <p class="lib-item-meta">${esc(r.date || "")}</p>
      <p class="lib-item-title">${esc(r.name.replace(/^\d{4}-\d{2}-\d{2}-/, "").replace(/\.md$/, ""))}</p>`;
    div.addEventListener("click", async () => {
      try {
        const d = await api("/api/report?name=" + encodeURIComponent(r.name));
        showReport(d);
        switchTab("work");
      } catch (e) {
        logLine("❌ 读取报告失败：" + e.message, "l-err");
      }
    });
    list.appendChild(div);
  }
}

initCfg();
