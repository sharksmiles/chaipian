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
    ${qp ? `<p><b>📌 快速提示词（可直接粘贴）</b></p><div class="code-block"><button type="button" class="copy-btn" data-act="copy" data-text="${escAttr(qp)}">复制</button><pre>${esc(qp)}</pre></div>` : ""}
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

function urlLink(url) {
  const u = url || "";
  if (!u) return "";
  if (/^https?:\/\//.test(u)) {
    return `<a class="lib-url" href="${escAttr(u)}" target="_blank" rel="noopener">${esc(u)}</a>`;
  }
  return esc(u); // 本地文件名等非链接：纯文本展示
}

function renderHooks(items, list) {
  for (const r of items) {
    const div = document.createElement("div");
    div.className = "lib-item";
    const reuse = (r.reusable || []).filter(Boolean).slice(0, 3);
    div.innerHTML = `
      <p class="lib-item-title">${esc(r.title || "未命名")}</p>
      <p class="lib-item-meta">${esc(r.date)} · ${esc(r.platform || "")} · ${urlLink(r.url)}</p>
      <p class="lib-item-line"><b>钩子类型</b>　<span class="tag">${esc(r.hook_type || "-")}</span></p>
      <p class="lib-item-line"><b>一句话钩子</b>　${esc(r.hook_one_liner || "-")}</p>
      ${r.hook_formula ? `<p class="lib-item-line"><b>钩子公式</b>　${esc(r.hook_formula)}</p>` : ""}
      ${reuse.map((x) => `<p class="lib-item-line"><b>可复用</b>　${esc(x)}</p>`).join("")}
      ${r.transfer_topic ? `<p class="lib-item-line"><b>可迁移</b>　${esc(r.transfer_topic)}</p>` : ""}
      <p class="lib-item-actions">
        <button class="btn btn-ghost btn-sm lib-del" data-act="del" data-kind="hooks" data-id="${escAttr(r.id || "")}">删除</button>
      </p>`;
    list.appendChild(div);
  }
}

function copyBtn(text, label) {
  if (!text) return "";
  return `<button class="btn btn-ghost btn-sm" data-act="copy" data-text="${escAttr(text)}">${esc(label || "复制")}</button>`;
}

/* 一行提示词：label + 文本（限行省略，hover 显示全文）+ 复制（中英按钮合一） */
function copyRow(label, zh, en, clamp) {
  if (!zh && !en) return "";
  const text = zh || en;
  const preCls = "pack-pre" + (clamp ? ` clamp${clamp}` : "");
  const btns = zh && en ? `${copyBtn(zh, "复制中")}${copyBtn(en, "复制EN")}` : copyBtn(text, "复制");
  return `
    <div class="pack-row lib-row">
      <span class="pack-label">${esc(label)}</span>
      <pre class="${preCls}" title="${escAttr(text)}">${esc(text)}</pre>
      <span class="btn-group">${btns}</span>
    </div>`;
}

function sceneRow(s) {
  const text = (s && s.prompt_zh) || "";
  if (!text) return "";
  const meta = [s.camera && `运镜 ${s.camera}`, s.style && `风格 ${s.style}`].filter(Boolean).join(" · ");
  return `
    <div class="scene-row">
      <span class="scene-head"><b>【${esc(s.time || "?")}】</b>${meta ? `<span class="scene-meta">${esc(meta)}</span>` : ""}</span>
      <pre class="pack-pre clamp2" title="${escAttr(text)}">${esc(text)}</pre>
      ${copyBtn(text)}
    </div>`;
}

function renderPrompts(items, list) {
  for (const r of items) {
    const div = document.createElement("div");
    div.className = "lib-item";
    const kws = (r.style_keywords || []).slice(0, 8).map((k) => `<span class="tag">${esc(k)}</span>`).join(" ");
    const scenes = Array.isArray(r.scene_prompts) ? r.scene_prompts : [];
    const scenesBlock = scenes.length
      ? scenes.map(sceneRow).join("")
      : `<p class="lib-item-line lib-dim">该记录未保存分镜提示词（旧版本生成），重新拆解一次即可与报告第 12 节完全一致</p>`;
    // 有改写包时：包内 negative 是按原始增强过的版本，卡片不再重复展示
    const packNeg = r.pack && (r.pack.negative || "").trim();
    const details = `
      <details class="lib-details"${r.pack ? "" : " open"}>
        <summary>完整反推内容（整体提示词 · 图生视频模板 · 分镜 ${scenes.length} 镜 · 复刻建议）</summary>
        <div class="lib-details-body">
          ${copyRow("整体提示词", r.overall_zh, r.overall_en, 2)}
          ${copyRow("图生视频模板", r.image_to_video_prompt, "", 2)}
          ${scenesBlock}
          ${r.recreate_notes ? `<p class="lib-item-line"><b>复刻建议</b>　${esc(r.recreate_notes)}</p>` : ""}
        </div>
      </details>`;
    div.innerHTML = `
      <p class="lib-item-title">${esc(r.title || "未命名")}</p>
      <p class="lib-item-meta">${esc(r.date)} · ${esc(r.platform || "")} · ${urlLink(r.url)}</p>
      <p class="lib-item-line"><b>类型</b>　${esc(r.video_type || "-")}${kws ? `　<b>风格</b>　${kws}` : ""}</p>
      ${copyRow("快速提示词", r.quick_zh, r.quick_en, 1)}
      ${!packNeg ? copyRow("负面提示词", r.negative_prompt, "", 1) : ""}
      ${details}
      <p class="lib-item-actions">
        <button class="btn btn-ghost btn-sm" data-act="rewrite" data-url="${escAttr(r.url || "")}">
          ${r.pack ? "重新改写提示词包" : "改写为可直接用的提示词包"}
        </button>
        <button class="btn btn-ghost btn-sm lib-del" data-act="del" data-kind="prompts" data-id="${escAttr(r.id || "")}">删除</button>
      </p>
      ${r.pack ? packBlock(r.pack) : ""}`;
    list.appendChild(div);
  }
}

function timelineLine(segments) {
  const rs = segments
    .map((s) => {
      const m = /(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)/.exec(String(s.time || ""));
      return m ? [parseFloat(m[1]), parseFloat(m[2])] : null;
    })
    .filter(Boolean)
    .sort((a, b) => a[0] - b[0]);
  if (!rs.length) return "";
  const start = rs[0][0];
  const end = rs[rs.length - 1][1];
  let gaps = 0;
  for (let i = 1; i < rs.length; i++) if (Math.abs(rs[i][0] - rs[i - 1][1]) > 1) gaps++;
  const ok = gaps === 0;
  return `<p class="pack-timeline${ok ? "" : " warn"}">⏱ 时间轴 ${start}-${end}s · ${rs.length} 段 · ${ok ? "连续覆盖，无缝隙" : "存在缝隙/重叠，建议重新改写"}</p>`;
}

function packBlock(p) {
  // 按模型分组展示分段提示词（复刻用）：Seedance 2.0/2.5 最前，不展示整条简略版
  const segments = (Array.isArray(p.segments) ? p.segments : [])
    .filter((s) => s && (s.kling_zh || s.jimeng_zh || s.seedance_zh));
  const models = [
    ["Seedance 2.0/2.5", "seedance_zh"],
    ["可灵", "kling_zh"],
    ["即梦", "jimeng_zh"],
  ];
  const blocks = models
    .map(([name, key]) => {
      const items = segments
        .map((s) => ({ s, text: (s[key] || "").trim() }))
        .filter((x) => x.text);
      if (!items.length) return "";
      return `
        <p class="pack-title">${esc(name)}</p>
        ${items
          .map(
            ({ s, text }) => `
          <div class="scene-row">
            <span class="scene-head"><b>【${esc(s.time || "?")}】</b>${s.summary ? `<span class="scene-meta">${esc(s.summary)}</span>` : ""}</span>
            <pre class="pack-pre clamp3" title="${escAttr(text)}">${esc(text)}</pre>
            ${copyBtn(text)}
          </div>`
          )
          .join("")}`;
    })
    .filter(Boolean)
    .join("");
  if (!blocks) {
    // 旧格式包（无分段数据）：不渲染旧内容，提示重新改写
    return `
      <div class="pack">
        <p class="pack-title">提示词包</p>
        <p class="lib-item-line lib-dim">该包是旧版本生成（无分段数据），点击上方「重新改写提示词包」升级为按模型的分段版</p>
      </div>`;
  }
  const params = p.params
    ? `<p class="pack-params">参数建议：${esc(Object.entries(p.params).map(([k, v]) => `${k} ${v}`).join(" ｜ "))}</p>`
    : "";
  const warnings = Array.isArray(p.warnings) && p.warnings.length
    ? `<p class="pack-timeline warn">⚠ 时间轴校验未通过：${esc(p.warnings.join("；"))}</p>`
    : "";
  const continuity = `
    <p class="pack-notes"><b>复刻衔接建议：</b>各段提示词已统一主体/场景/光线/风格并带"延续上一段"衔接句。实际生成时请用<b>图生视频链条</b>保证连贯：第 1 段用参考图或文生视频生成，取它的<b>最后一帧</b>作为第 2 段的首帧图（可灵/即梦均支持首帧图生视频），依次接续；或用可灵<b>首尾帧</b>控制（首帧=上一段末帧）。全程用同一模型，不要中途换工具。</p>`;
  return `
    <div class="pack">
      <p class="pack-title">提示词包 · 按模型分段（可直接粘贴）</p>
      ${timelineLine(segments)}
      ${warnings}
      ${blocks}
      ${p.negative ? `
        <div class="pack-row">
          <span class="pack-label">负向提示词</span>
          <pre class="pack-pre clamp1" title="${escAttr(p.negative)}">${esc(p.negative)}</pre>
          ${copyBtn(p.negative, "复制")}
        </div>` : ""}
      ${params}
      ${continuity}
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
    div.className = "lib-item is-openable"; // 历史报告卡片整卡可点，保留 pointer 光标
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
