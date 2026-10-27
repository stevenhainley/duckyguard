/* DuckyGuard dashboard. Talks to Python through window.webkit.messageHandlers.dg. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const S = { snap: null, tab: "overview", onbPage: 0, lastRecentLen: 0, inTest: false };

  function send(cmd, extra) {
    const msg = Object.assign({ cmd }, extra || {});
    try { window.webkit.messageHandlers.dg.postMessage(msg); }
    catch (e) { console.log("no bridge", msg); }
  }
  window.dg = {
    receive(m) {
      if (m.type === "snapshot") render(m.data);
      else if (m.type === "toast") toast(m.data.text, m.data.kind);
      else if (m.type === "error") toast(m.data.message, "error");
      else if (m.type === "test_begin") testBegin();
      else if (m.type === "test_end") testEnd();
      else if (m.type === "block_started") blockStarted();
      else if (m.type === "block_finished") blockFinished(m.data.incident);
    }
  };

  // ---------------------------------------------------------------- helpers
  function toast(text, kind) {
    const t = document.createElement("div");
    t.className = "toast " + (kind || "");
    t.textContent = text;
    $("toasts").appendChild(t);
    setTimeout(() => t.remove(), 3200);
  }
  const fmtTime = (ts) => ts ? new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
  const fmtDay = (ts) => new Date(ts * 1000).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const num = (n) => (n || 0).toLocaleString();

  function showTab(name) {
    S.tab = name;
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("hidden", v.id !== "view-" + name));
    $("top").classList.remove("hidden");
  }

  function showOnboarding(page) {
    S.onbPage = page;
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("hidden", v.id !== "view-onboarding"));
    document.querySelectorAll(".onb-page").forEach((p) => p.classList.toggle("hidden", +p.dataset.page !== page));
    document.querySelectorAll("#onbSteps i").forEach((i, k) => i.classList.toggle("on", k <= page));
  }

  // ---------------------------------------------------------------- render
  function render(snap) {
    S.snap = snap;
    const st = snap.status;
    const perms = snap.permissions || {};
    const settings = snap.settings || {};

    // First run: onboarding until finished
    if (!settings.onboarded) {
      if (!document.getElementById("view-onboarding").classList.contains("hidden") || S.tab === "overview") showOnboarding(S.onbPage);
      renderPerms(perms);
      $("tabs").classList.add("hidden");
      $("pill").classList.add("hidden");
      return;
    }
    $("tabs").classList.remove("hidden");
    $("pill").classList.remove("hidden");
    if (!$("view-onboarding").classList.contains("hidden")) showTab(S.tab);

    // Pill
    const pill = $("pill");
    pill.className = "pill " + st;
    $("pillText").textContent = { protected: "Protected", observing: "Observing only", paused: "Paused", alert: "Blocking",
      no_permission: "Needs permission", error: "Error" }[st] || st;

    // Hero
    const hero = document.querySelector(".hero");
    hero.classList.toggle("alert", st === "alert");
    const titles = { protected: "Protected", observing: "Observing only", paused: "Paused", alert: "Blocking a burst",
      no_permission: "Needs permission", error: "Something went wrong" };
    $("heroTitle").textContent = titles[st] || st;
    const kbs = snap.keyboards || [];
    const ext = kbs.filter((k) => !k.built_in).length;
    const subs = {
      protected: `Watching ${kbs.length} keyboard${kbs.length === 1 ? "" : "s"}${ext ? ` (${ext} external)` : ""}. Machine-timed bursts are dropped.`,
      observing: "DuckyGuard can see keystrokes but cannot drop them. Grant Accessibility to block.",
      paused: "Nothing is being watched.",
      alert: "A keyboard is typing like a machine. Its keys are being dropped.",
      no_permission: "Grant Input Monitoring (and Accessibility) in System Settings.",
      error: snap.error || "",
    };
    $("heroSub").textContent = subs[st] || "";
    $("btnToggle").textContent = snap.running ? "Pause" : "Turn on";
    $("btnTest").disabled = !snap.running || snap.in_test;
    $("stKeys").textContent = num(snap.keys_seen);
    $("stBlocks").textContent = num(snap.blocks);
    $("stKb").textContent = kbs.length;

    // Notices
    const pn = $("permNotice");
    if (!perms.input_monitoring || !perms.accessibility) {
      pn.className = "notice warn";
      pn.innerHTML = `<div class="grow"><b>${!perms.input_monitoring ? "Input Monitoring" : "Accessibility"} is off.</b> ` +
        (!perms.input_monitoring ? "DuckyGuard cannot see keystrokes." : "DuckyGuard can warn but cannot drop keys.") +
        `</div><button class="btn" data-settings="${!perms.input_monitoring ? "input_monitoring" : "accessibility"}">Open System Settings</button>`;
    } else pn.className = "notice hidden";
    const en = $("errNotice");
    if (snap.error) { en.className = "notice bad"; en.innerHTML = `<div class="grow"><b>Problem:</b> ${esc(snap.error)}</div>`; }
    else en.className = "notice hidden";
    const un = $("updNotice");
    if (snap.update && snap.update.newer) {
      un.className = "notice";
      un.innerHTML = `<div class="grow"><b>Update:</b> ${esc(snap.update.message)}</div><button class="btn" data-url="${esc(snap.update.url)}">See release</button>`;
    } else un.className = "notice hidden";

    renderRhythm(snap.recent || []);
    renderVerdict(snap.last_verdict);

    // Last incident
    const incs = snap.incidents || [];
    $("incCount").textContent = incs.length ? String(incs.length) : "";
    const last = incs[0];
    $("lastCard").classList.toggle("hidden", !last);
    if (last) {
      $("lastWhen").textContent = fmtDay(last.started_at) + " " + fmtTime(last.started_at) + (last.simulated ? " (safe test)" : "");
      $("lastExplain").textContent = last.explanation;
      $("btnLastExport").onclick = () => send("export", { id: last.id });
    }

    renderTimeline(incs);
    renderDevices(snap);
    renderSettings(snap, settings, perms);
  }

  function renderPerms(perms) {
    $("permIM").classList.toggle("ok", !!perms.input_monitoring);
    $("permAX").classList.toggle("ok", !!perms.accessibility);
    $("onbNext1").textContent = perms.input_monitoring ? "Continue" : "Continue anyway";
  }

  function renderRhythm(recent) {
    const el = $("rhythm");
    const items = recent.slice(-80);
    if (items.length === S.lastRecentLen && items.length && el.childElementCount) {
      // same count: only redraw if the last timestamp changed
      if (el.dataset.t === String(items[items.length - 1].t)) return;
    }
    S.lastRecentLen = items.length;
    el.dataset.t = items.length ? String(items[items.length - 1].t) : "";
    el.innerHTML = "";
    let prev = null;
    for (const r of items) {
      const gap = prev == null ? 0.3 : Math.max(0, r.t - prev);
      prev = r.t;
      const h = Math.max(2, Math.min(64, Math.round(64 * Math.min(gap, 0.5) / 0.5)));
      const i = document.createElement("i");
      i.style.height = h + "px";
      if (r.block) i.className = "m"; else if (r.kind === "software") i.className = "s";
      i.title = `${Math.round(gap * 1000)} ms`;
      el.appendChild(i);
    }
    $("rhythmSub").textContent = items.length ? "gap between recent keys, in milliseconds (taller = slower)" : "type anywhere to see your rhythm";
  }

  function renderVerdict(v) {
    const el = $("verdict");
    if (!v) { el.textContent = ""; el.className = "verdict"; return; }
    const f = v.features || {};
    if (v.kind === "buffering") { el.className = "verdict"; el.textContent = v.explanation; return; }
    if (v.kind === "software") { el.className = "verdict"; el.textContent = v.explanation; return; }
    if (v.block) { el.className = "verdict block"; el.textContent = v.explanation; return; }
    el.className = "verdict";
    el.textContent = f.cps != null ? `${f.cps} keys/s, gaps vary ${Math.round((f.cv || 0) * 100)}%. ${v.explanation}` : v.explanation;
  }

  function renderTimeline(incs) {
    const el = $("timeline");
    if (!incs.length) { el.innerHTML = `<div class="empty">Nothing blocked yet. Run the safe test from Overview to see what an incident looks like.</div>`; return; }
    const open = new Set([...el.querySelectorAll(".inc.open")].map((n) => n.dataset.id));
    let html = "", day = "";
    for (const inc of incs) {
      const d = fmtDay(inc.started_at);
      if (d !== day) { day = d; html += `<div class="day">${esc(d)}</div>`; }
      const f = (inc.verdict || {}).features || {};
      const kb = inc.keyboard;
      html += `<div class="inc ${open.has(inc.id) ? "open" : ""}" data-id="${esc(inc.id)}">
        <div class="inc-row" data-toggle="1">
          <div class="inc-time">${fmtTime(inc.started_at)}</div>
          <div class="inc-sum">${esc(inc.summary || inc.explanation)}<small>${kb ? esc(kb.product) + " (attributed by time)" : "source keyboard unknown"}</small></div>
          ${inc.simulated ? `<span class="inc-tag sim">safe test</span>` : ""}
          ${inc.can_drop === false ? `<span class="inc-tag">warned only</span>` : `<span class="inc-tag">${inc.blocked_count} keys dropped</span>`}
        </div>
        <div class="inc-body">
          <p>${esc(inc.explanation)}</p>
          <ul>${((inc.verdict || {}).reasons || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
          <div class="kv">
            <div><b>${f.cps ?? "-"}</b><span>keys per second</span></div>
            <div><b>${f.median_iki_ms ?? "-"} ms</b><span>median gap</span></div>
            <div><b>${f.cv != null ? Math.round(f.cv * 100) + "%" : "-"}</b><span>gap variation</span></div>
            <div><b>${f.median_hold_ms != null ? f.median_hold_ms + " ms" : "n/a"}</b><span>key hold</span></div>
            <div><b>${inc.keys_before_block}</b><span>keys reached the app</span></div>
            <div><b>${inc.blocked_count}</b><span>keys dropped</span></div>
          </div>
          <small class="muted">Reached the app:</small><pre>${esc(inc.prefix_text || "")}</pre>
          <small class="muted">Dropped:</small><pre>${esc(inc.blocked_text || "")}</pre>
          <div class="row">
            <button class="btn" data-export="${esc(inc.id)}">Export report</button>
            ${kb && kb.key ? `<button class="btn" data-trust="${esc(kb.key)}">Trust this keyboard</button>` : ""}
            <button class="btn danger" data-del="${esc(inc.id)}">Delete</button>
          </div>
        </div></div>`;
    }
    el.innerHTML = html;
  }

  function renderDevices(snap) {
    const kbs = snap.keyboards || [];
    const trusted = snap.trusted || {};
    $("devSub").textContent = `${kbs.length} connected, checked every second (${snap.keyboard_poll_ms || 0} ms)`;
    $("devices").innerHTML = kbs.length ? kbs.map((k) => {
      const isTr = k.trusted || k.built_in;
      return `<div class="dev ${isTr ? "" : "untrusted"}">
        <div class="dev-ico">${esc(k.transport === "USB" ? "USB" : k.transport === "Bluetooth" ? "BT" : k.built_in ? "MAC" : esc(k.transport).slice(0, 4))}</div>
        <div class="dev-body"><b>${esc(k.product)}</b><small>${esc(k.manufacturer || "unknown maker")}, vendor ${k.vendor_hex} product ${k.product_hex}${k.serial ? ", serial " + esc(k.serial) : ""}</small>
        ${k.vendor_note ? `<span class="note">${esc(k.vendor_note)}</span>` : ""}</div>
        ${k.built_in ? `<span class="inc-tag">built in</span>` :
          isTr ? `<button class="btn" data-untrust="${esc(k.key)}">Untrust</button>` :
                 `<button class="btn primary" data-trust="${esc(k.key)}">Trust this keyboard</button>`}
      </div>`;
    }).join("") : `<div class="empty">No keyboards found. Is Input Monitoring granted?</div>`;
    const connected = new Set(kbs.map((k) => k.key));
    const rest = Object.entries(trusted).filter(([k]) => !connected.has(k));
    $("trustedList").innerHTML = rest.length ? rest.map(([k, v]) => `<div class="dev">
      <div class="dev-ico">${esc((v.transport || "?").slice(0, 4))}</div>
      <div class="dev-body"><b>${esc(v.product || k)}</b><small>trusted ${v.trusted_at ? fmtDay(v.trusted_at) : ""}</small></div>
      <button class="btn" data-untrust="${esc(k)}">Untrust</button></div>`).join("") : `<p class="muted">None.</p>`;
  }

  function renderSettings(snap, settings, perms) {
    document.querySelectorAll("[data-setting]").forEach((el) => {
      const k = el.dataset.setting;
      if (document.activeElement === el) return;
      if (el.type === "checkbox") el.checked = k === "launch_at_login" ? !!snap.launch_at_login : k === "protection_enabled" ? !!snap.running : !!settings[k];
      else if (el.type === "range") el.value = settings[k];
    });
    $("qLabel").textContent = `${settings.quarantine_seconds} s`;
    $("setIM").textContent = perms.input_monitoring ? "Granted." : "Not granted. DuckyGuard cannot see keystrokes.";
    $("setAX").textContent = perms.accessibility ? "Granted." : "Not granted. DuckyGuard can warn but not block.";
    $("dataDir").textContent = snap.data_dir;
    $("aboutVersion").textContent = snap.version;
    const cb = snap.callback_us || {};
    $("aboutLatency").textContent = cb.median != null ? `median ${cb.median.toFixed(0)} µs, p99 ${cb.p99.toFixed(0)} µs over ${cb.samples} keys` : "not measured yet";
    $("aboutPoll").textContent = snap.keyboard_poll_ms;
    $("updText").textContent = snap.update ? snap.update.message : "";
    $("btnSupport").classList.toggle("hidden", !snap.support_url);
  }

  // ---------------------------------------------------------------- test flow
  function testBegin() {
    S.inTest = true;
    showTab("overview");
    const pad = $("testPad");
    pad.value = "";
    pad.classList.remove("blocked");
    pad.focus();
    $("testSub").textContent = "Typing a harmless sentence at 12 ms per key...";
  }
  function blockStarted() {
    const pad = $("testPad");
    if (S.inTest) pad.classList.add("blocked");
  }
  function blockFinished(inc) {
    if (S.inTest || (inc && inc.simulated)) {
      $("testSub").textContent = `Done. ${inc.keys_before_block} keys landed before the decision, ${inc.blocked_count} were dropped.`;
    }
  }
  function testEnd() { S.inTest = false; }

  // ---------------------------------------------------------------- events
  document.addEventListener("click", (e) => {
    const b = e.target.closest("button, a, [data-toggle]");
    if (!b) return;
    if (b.dataset.tab) return showTab(b.dataset.tab);
    if (b.dataset.goto) return showTab(b.dataset.goto);
    if (b.dataset.onb != null) { showOnboarding(+b.dataset.onb); return; }
    if (b.id === "onbFinish") { send("finish_onboarding"); showTab("overview"); setTimeout(() => send("test"), 600); return; }
    if (b.dataset.settings) return send("open_settings", { which: b.dataset.settings });
    if (b.dataset.url) return send("open_url", { url: b.dataset.url });
    if (b.dataset.export) return send("export", { id: b.dataset.export });
    if (b.dataset.del) return send("delete_incident", { id: b.dataset.del });
    if (b.dataset.trust) { send("trust", { key: b.dataset.trust }); toast("Keyboard trusted"); return; }
    if (b.dataset.untrust) return send("untrust", { key: b.dataset.untrust });
    if (b.dataset.toggle) { b.closest(".inc").classList.toggle("open"); return; }
    if (b.id === "btnToggle") return send(S.snap && S.snap.running ? "stop" : "start");
    if (b.id === "btnTest") return send("test");
    if (b.id === "btnClear") { if (confirm("Delete every incident? This cannot be undone.")) send("clear_incidents"); return; }
    if (b.id === "btnDataDir") return send("open_data_folder");
    if (b.id === "btnCheckNow") { e.preventDefault(); $("updText").textContent = "Checking..."; return send("check_updates"); }
    if (b.id === "btnProject") return send("open_url", { url: S.snap.project_url });
    if (b.id === "btnSupport") return send("open_url", { url: S.snap.support_url });
  });
  document.addEventListener("change", (e) => {
    const el = e.target;
    if (!el.dataset.setting) return;
    send("set_setting", { key: el.dataset.setting, value: el.type === "checkbox" ? el.checked : parseFloat(el.value) });
  });
  $("qRange").addEventListener("input", (e) => { $("qLabel").textContent = `${e.target.value} s`; });

  send("ready");
})();
