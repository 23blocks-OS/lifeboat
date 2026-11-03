// Lifeboat chat UI. No libraries, no network calls except to this laptop.
const $ = (s) => document.querySelector(s);
const log = $("#log"), q = $("#q"), loadBtn = $("#loadBtn"), profileSel = $("#profile");
let history = [];          // [{role, content}]
let busy = false, status = null;

const QUICK = [
  "Severe bleeding that won't stop",
  "Signs of shock and what to do",
  "Make water safe to drink without power",
  "Wildfire smoke: protect people indoors",
  "Generator won't start",
  "Run a generator safely (carbon monoxide)",
  "Rattlesnake bite first aid",
  "Burn treatment without a hospital",
  "Treat diarrhea and dehydration (oral rehydration)",
  "Store food safely when the fridge is off",
];

function esc(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Small Markdown subset: headings, lists, bold, italic, code, paragraphs, [n] citations.
function md(text, id) {
  const lines = esc(text).split("\n");
  let html = "", list = null;
  const inline = (s) => s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<i>$2</i>")
    .replace(/\[(\d{1,2})\]/g, `<a class="cite" href="#" data-msg="${id}" data-n="$1">[$1]</a>`);
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const raw of lines) {
    const l = raw.trimEnd();
    let m;
    if ((m = l.match(/^#{1,4}\s+(.*)/))) { close(); html += `<h3>${inline(m[1])}</h3>`; }
    else if ((m = l.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1])}</li>`; }
    else if ((m = l.match(/^\s*[-*•]\s+(.*)/))) { if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; }
    else if (!l.trim()) { close(); }
    else { close(); html += `<p>${inline(l)}</p>`; }
  }
  close();
  return html;
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

function pill(text, cls) { return `<span class="pill ${cls || ""}">${esc(text)}</span>`; }

async function refresh() {
  try { status = await api("/api/status"); } catch { return; }
  const s = status;
  if (!profileSel.options.length) {
    for (const p of s.profiles) {
      const o = document.createElement("option");
      o.value = p.id; o.textContent = p.label + (p.available ? "" : " (not on disk)");
      o.disabled = !p.available; profileSel.appendChild(o);
    }
  }
  const loaded = s.profiles.find((p) => p.loaded);
  if (loaded) profileSel.value = loaded.id;
  if (s.loading) { loadBtn.textContent = "Loading…"; loadBtn.disabled = true; }
  else if (s.chat_loaded) { loadBtn.textContent = "Unload model"; loadBtn.disabled = false; loadBtn.classList.remove("primary"); }
  else { loadBtn.textContent = "Load model"; loadBtn.disabled = false; loadBtn.classList.add("primary"); }

  const b = s.battery || {};
  let pills = "";
  pills += s.chat_loaded ? pill(`Model on · ${s.chat_mem_gb ?? "?"} GB`, "ok") : pill(s.loading ? "Model loading" : "Model off", s.loading ? "warn" : "");
  if (b.percent != null) pills += pill(`${b.on_ac ? "⚡ " : ""}Battery ${b.percent}%`, b.on_ac ? "ok" : b.percent < 25 ? "bad" : b.percent < 50 ? "warn" : "");
  pills += pill(s.drive_online ? "Drive connected" : "Drive missing", s.drive_online ? "ok" : "warn");
  pills += pill(`${(s.index.passages || 0).toLocaleString()} passages`, s.index.passages ? "" : "warn");
  $("#hhBtn").textContent = s.household ? `Household (${s.household})` : "Household";
  if (s.household == null) maybeOfferIntake();
  if (s.error) pills += pill(`Error: ${s.error}`.slice(0, 80), "bad");
  $("#pills").innerHTML = pills;
}

loadBtn.onclick = async () => {
  loadBtn.disabled = true;
  if (status && status.chat_loaded) await api("/api/unload", { method: "POST" });
  else await api("/api/load", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: profileSel.value }) });
  refresh();
};

function addUser(text) {
  $("#welcome")?.remove();
  const d = document.createElement("div");
  d.className = "msg user"; d.innerHTML = `<div class="bubble">${esc(text)}</div>`;
  log.appendChild(d);
}

function addBot() {
  const id = "m" + Date.now();
  const d = document.createElement("div");
  d.className = "msg bot"; d.id = id;
  d.innerHTML = `<div class="answer cursor"></div><div class="meta"></div>`;
  log.appendChild(d);
  d.scrollIntoView({ block: "end" });
  return d;
}

function renderSources(box, passages, open) {
  if (!passages.length) return;
  const det = document.createElement("details");
  det.className = "sources"; det.open = !!open;
  det.innerHTML = `<summary>Sources (${passages.length}) — read these before acting</summary>` +
    passages.map((p, i) => `
      <div class="src" data-n="${i + 1}">
        <div class="head"><span class="n">[${i + 1}]</span><span class="t">${esc(p.title || "")}</span>
          <span class="from">${esc(p.source_title || p.source || "")}${p.section ? " · " + esc(p.section) : ""}${p.page ? " · p." + p.page : ""}</span>
          <a class="open" href="${esc(p.link)}" target="_blank" rel="noopener">Open full source ↗</a></div>
        <div class="body">${esc(p.context || "")}</div>
      </div>`).join("");
  box.appendChild(det);
}

log.addEventListener("click", (e) => {
  const a = e.target.closest("a.cite");
  if (!a) return;
  e.preventDefault();
  const msg = document.getElementById(a.dataset.msg);
  const det = msg.querySelector("details.sources");
  if (!det) return;
  det.open = true;
  const card = det.querySelector(`.src[data-n="${a.dataset.n}"]`);
  if (card) { card.scrollIntoView({ behavior: "smooth", block: "center" }); card.classList.add("flash"); setTimeout(() => card.classList.remove("flash"), 1600); }
});

function setBusy(v) { busy = v; $("#askBtn").disabled = v; $("#searchBtn").disabled = v; }

async function searchOnly(text) {
  addUser(text);
  const box = addBot();
  const ans = box.querySelector(".answer");
  try {
    const r = await api("/api/search?q=" + encodeURIComponent(text));
    ans.classList.remove("cursor");
    ans.innerHTML = `<p>Library results (no model). The best passages are first.</p>`;
    renderSources(box, r.passages, true);
    box.querySelector(".meta").textContent = `Search took ${r.timing.total}s over ${r.pool} candidates.`;
  } catch (e) { ans.classList.remove("cursor"); ans.innerHTML = `<p class="err">${esc(String(e))}</p>`; }
}

async function ask(text) {
  addUser(text);
  history.push({ role: "user", content: text });
  const box = addBot();
  const ans = box.querySelector(".answer"), meta = box.querySelector(".meta");
  let content = "", reasoning = "", thinkEl = null, passages = [];
  const r = await fetch("/api/chat", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: history, think: $("#think").checked }),
  });
  const reader = r.body.getReader(), dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i); buf = buf.slice(i + 2);
      const ev = (block.match(/^event: (.*)$/m) || [])[1];
      const data = JSON.parse((block.match(/^data: (.*)$/m) || [])[1] || "{}");
      if (ev === "sources") { passages = data.passages; }
      else if (ev === "reasoning") {
        reasoning += data.t;
        if (!thinkEl) { thinkEl = document.createElement("details"); thinkEl.className = "think"; thinkEl.innerHTML = "<summary>Model reasoning</summary><pre></pre>"; box.insertBefore(thinkEl, ans); }
        thinkEl.querySelector("pre").textContent = reasoning;
      }
      else if (ev === "content") { content += data.t; ans.innerHTML = md(content, box.id); }
      else if (ev === "error") { ans.innerHTML += `<p class="err">${esc(data.msg)}</p>`; }
      else if (ev === "done") {
        ans.classList.remove("cursor");
        if (data.warn) ans.insertAdjacentHTML("afterbegin", `<p class="dose-warn">⚠ ${esc(data.warn)}</p>`);
        renderSources(box, passages, !content);
        if (data.tok_s) meta.textContent = `${data.seconds}s total · ${data.tok_s} tokens/s · search ${data.retrieval.total}s`;
      }
    }
  }
  if (content) history.push({ role: "assistant", content });
  else history.pop();
}

$("#ask").onsubmit = async (e) => {
  e.preventDefault();
  const text = q.value.trim();
  if (!text || busy) return;
  q.value = ""; setBusy(true);
  try {
    if (!status || !status.chat_loaded) await searchOnly(text);
    else await ask(text);
  } catch (err) { log.insertAdjacentHTML("beforeend", `<p class="err">${esc(String(err))}</p>`); }
  setBusy(false); q.focus();
};
$("#searchBtn").onclick = async () => {
  const text = q.value.trim();
  if (!text || busy) return;
  q.value = ""; setBusy(true);
  try { await searchOnly(text); } finally { setBusy(false); }
};
q.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#ask").requestSubmit(); } });

$("#quick").innerHTML = QUICK.map((t) => `<button type="button">${esc(t)}</button>`).join("");
$("#quick").onclick = (e) => { if (e.target.tagName === "BUTTON") { q.value = e.target.textContent; $("#ask").requestSubmit(); } };

refresh();
setInterval(refresh, 4000);
