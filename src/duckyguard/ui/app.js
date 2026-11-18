// DuckyGuard dashboard. Python pushes {type, data} through dg.receive(); the page answers with send(cmd, args).
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const q = new URLSearchParams(location.search);
  const native = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.dg;
  const preview = !native && q.has("preview");                 // the built-in simulator runs only when the URL asks for it
  const send = (cmd, args) => { const m = Object.assign({ cmd }, args || {}); if (native) native.postMessage(m); else if (preview) Mock.handle(m); };
  const S = { snap: null, tab: "overview", open: null, lastT: 0, inTest: false, testBusy: false, renderKey: {}, hidden: new Set(), seenInc: null };
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

  // ───────────────────────────────────────────────────────────── plate
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  function rgb(color) { const c = document.createElement("canvas").getContext("2d"); c.fillStyle = color; c.fillRect(0, 0, 1, 1); const d = c.getImageData(0, 0, 1, 1).data; return [d[0] / 255, d[1] / 255, d[2] / 255]; }

  // Each reading on the plate is tied to the part of the head that shows it. The plate reports where those parts are
  // on screen as the head turns, and the lines follow.
  const FROM = { burst: [20, 30], press: [352, 30], verdict: [20, 200], rate: [352, 200], halo: [20, 342], rhythm: [352, 342] };
  const leads = {};
  $("leads").innerHTML = Object.keys(FROM).map(k => `<line data-k="${k}"/><circle data-k="${k}" r="2.5"/>`).join("");
  for (const k in FROM) leads[k] = { line: $("leads").querySelector(`line[data-k="${k}"]`), dot: $("leads").querySelector(`circle[data-k="${k}"]`), x: -9, y: -9 };
  function onParts(parts) {
    for (const k in parts) {
      const L = leads[k]; if (!L) continue;
      const x = clamp(parts[k].x * 372, 6, 366), y = clamp(parts[k].y * 372, 6, 366);
      if (Math.abs(x - L.x) < .4 && Math.abs(y - L.y) < .4) continue;
      L.x = x; L.y = y;
      L.line.setAttribute("x1", FROM[k][0]); L.line.setAttribute("y1", FROM[k][1]); L.line.setAttribute("x2", x.toFixed(1)); L.line.setAttribute("y2", y.toFixed(1));
      L.dot.setAttribute("cx", x.toFixed(1)); L.dot.setAttribute("cy", y.toFixed(1));
    }
  }
  let plate = null;
  try { plate = DuckPlate($("plate"), { ink: rgb(css("--color-accent")), paper: rgb(css("--color-paper-2")), red: rgb(css("--color-danger")), texture: DUCK_TEXTURE, onParts }); } catch (e) { console.error(e); }
  if (!plate) document.querySelectorAll(".leads, .hud, .plate figcaption button").forEach(el => el.hidden = true);

  // The tape under the plate: one bar per key, as tall as the key was held. An injector barely lifts off the floor.
  const BARS = " ▁▂▃▄▅▆▇█"; let tape = "";
  function tapeKey(gap, hold, blocked) {
    const bar = blocked ? "×" : BARS[clamp(Math.round((hold == null ? 95 : hold) / 16), 1, 8)];
    tape = (tape + (gap > 350 ? "  " : gap > 160 ? " " : "") + bar).slice(-52);
    $("tape").innerHTML = esc(tape.slice(0, -1)).replace(/×+/g, m => "<u>" + m + "</u>") + (blocked ? "<u>×</u>" : "<b>" + esc(tape.slice(-1)) + "</b>");
  }

  // Live ASCII: the plate itself, re-read as characters about ten times a second. Not a drawing of the duck: the duck.
  const RAMP = " .·:-=+*x%#@", mirrors = [{ pre: $("ascii-plate"), cols: 74, rows: 37 }, { pre: $("ob-ascii"), cols: 46, rows: 23 }];
  const probe = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  let frameData = null;
  function readPlate() { const W = plate.canvas.width; probe.canvas.width = probe.canvas.height = W; probe.drawImage(plate.canvas, 0, 0); frameData = probe.getImageData(0, 0, W, W).data; }
  function asciiMirror(pre, cols, rows) {
    const W = plate.canvas.width, cw = W / cols, ch = W / rows, d = frameData, inverted = document.body.classList.contains("alert");
    let out = "";
    for (let y = 0; y < rows; y++) { const y0 = Math.floor(y * ch), y1 = Math.floor((y + 1) * ch);
      for (let x = 0; x < cols; x++) { const x0 = Math.floor(x * cw), x1 = Math.floor((x + 1) * cw);
        let ink = 0, red = 0, n = 0;
        for (let py = y0; py < y1; py++) for (let px = x0; px < x1; px++) { const o = (py * W + px) * 4; n++; if (d[o] > 150 && d[o + 1] < 110) red++; else if (d[o + 1] > 128) ink++; }   // green tells yellow ink from navy paper
        let v = ink / n; if (inverted) v = 1 - v - red / n; v = clamp((v - .15) * 1.42, 0, 1);
        out += red / n > .3 ? "<b>@</b>" : RAMP[Math.round(v * (RAMP.length - 1))];
      } out += "\n"; }
    pre.innerHTML = out;
  }
  setInterval(() => {
    if (!plate || document.hidden) return;
    const live = mirrors.filter(m => m.pre.isConnected && m.pre.offsetParent !== null);
    plate.mirror(live.length > 0); plate.visible(live.length > 0 || (S.tab === "overview" && $("onboard").hidden));
    if (live.length) { readPlate(); live.forEach(m => asciiMirror(m.pre, m.cols, m.rows)); }
  }, 100);

  // ───────────────────────────────────────────────────────────── helpers
  const clock = t => new Date(t * 1000).toTimeString().slice(0, 5);
  function day(t) {
    const d = new Date(t * 1000), now = new Date(), days = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
    return (days === 0 ? "Today" : days === 1 ? "Yesterday" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" })) + " " + clock(t);
  }
  const plural = (n, word) => n + " " + word + (n === 1 ? "" : "s");
  function toast(text, kind, action) {
    const t = document.createElement("div"); t.className = "toast" + (kind === "error" ? " error" : ""); t.append(text);
    if (action) { const b = document.createElement("button"); b.type = "button"; b.textContent = action.label; b.onclick = () => { action.fn(); t.remove(); }; t.append(b); }
    $("toasts").appendChild(t); setTimeout(() => t.remove(), action ? 8000 : 4200);
  }
  function once(key, value, fn) { const j = JSON.stringify(value); if (S.renderKey[key] === j) return; S.renderKey[key] = j; fn(); }
  // Rebuild a list without losing keyboard focus: the control that had it is found again by its data attribute.
  function rebuild(el, html) {
    const a = document.activeElement; let sig = null;
    if (a && el.contains(a)) { const k = Object.keys(a.dataset)[0]; sig = k ? `[data-${k.replace(/[A-Z]/g, m => "-" + m.toLowerCase())}="${CSS.escape(a.dataset[k])}"]` : a.id ? "#" + a.id : null; }
    el.innerHTML = html;
    if (sig) { const n = el.querySelector(sig); if (n) n.focus(); }
  }
  const idNote = k => String(k.vendor_note || "").replace(/\s*\((definite|likely|hobby board)\)$/, "");      // drop the confidence tag; the sentence says enough
  const reasonOf = inc => { const r = String(((inc.verdict || {}).features || {}).rule || ""); const t = r.includes(":") ? r.slice(r.indexOf(":") + 1).trim() : ""; return t ? t[0].toUpperCase() + t.slice(1) : ""; };
  const WORD = { protected: "Protected", holding: "Keyboard held", alert: "Blocking", paused: "Paused", observing: "Can't block", recording: "Recording only", no_permission: "Not protected", error: "Not protected" };
  // Turning protection down must come from a pointer, never from keys: a device that has just been plugged in can press
  // Tab and Space. A click made from the keyboard has detail 0.
  const fromKeys = e => { if (e.detail !== 0) return false; toast("Use the trackpad or mouse for this.", "error"); return true; };

  // ───────────────────────────────────────────────────────────── receive
  // A page error must never fail silently in a security tool: it goes to the app's log.
  addEventListener("error", e => send("log", { text: `${e.message} (${String(e.filename).split("/").pop()}:${e.lineno})` }));
  window.dg = { receive(m) { try { receive(m); } catch (e) { send("log", { text: `${m && m.type}: ${e && e.stack || e}` }); } } };
  function receive(m) {
    if (m.type === "snapshot") apply(m.data);
    else if (m.type === "toast") toast(m.data.text, m.data.kind);
    else if (m.type === "tab") go(m.data.tab);
    else if (m.type === "test_begin") { S.inTest = S.testBusy = true; go("overview"); const p = $("pad"); p.hidden = false; p.value = ""; p.classList.remove("blocked"); p.focus(); if (S.snap) overview(S.snap); }
    else if (m.type === "test_end") { S.testBusy = false; if (S.snap) overview(S.snap); setTimeout(() => { S.inTest = false; $("pad").hidden = true; }, 5000); }
    else if (m.type === "block_started") { if (S.inTest) $("pad").classList.add("blocked"); }
  }

  function apply(s) {
    S.snap = s;
    feedPlate(s); overview(s); chrome(s);
    if (S.tab === "timeline") timeline(s);
    if (S.tab === "devices") devices(s);
    if (S.tab === "settings") settings(s);
    onboarding(s);
  }
  function go(tab) {
    if (!$("s-" + tab)) return;
    S.tab = tab;
    document.querySelectorAll(".tabs button").forEach(t => t.dataset.tab === tab ? t.setAttribute("aria-current", "page") : t.removeAttribute("aria-current"));
    document.querySelectorAll(".screen").forEach(x => x.hidden = x.id !== "s-" + tab);
    if (tab === "timeline" && S.snap) S.seenInc = new Set((S.snap.incidents || []).map(i => i.id));
    S.renderKey = {}; if (S.snap) apply(S.snap);
  }

  function feedPlate(s) {
    const fresh = (s.recent || []).filter(e => e.t > S.lastT && e.kind !== "software" && e.kind !== "ignored" && e.gap_ms != null);
    if (fresh.length) {
      const t0 = fresh[0].t; S.lastT = fresh[fresh.length - 1].t;
      fresh.forEach(e => setTimeout(() => { if (plate) plate.pushKey(e.gap_ms, e.hold_ms == null ? 95 : e.hold_ms); tapeKey(e.gap_ms, e.hold_ms, e.block); }, Math.min(950, (e.t - t0) * 1000)));
    } else if (s.recent && s.recent.length) S.lastT = Math.max(S.lastT, s.recent[s.recent.length - 1].t);
    const f = (s.last_verdict || {}).features || {};
    if (plate) plate.set({ alert: s.status === "alert" || s.in_quarantine, hold: !!s.hold, burst: f.burst_len || 0 });
  }

  // ───────────────────────────────────────────────────────────── overview
  function overview(s) {
    const v = s.last_verdict || {}, f = v.features || {}, hold = s.hold, set = s.settings || {};
    const st = s.status === "protected" && set.monitor_only ? "recording" : s.status;       // "protected" that blocks nothing is not protected
    document.body.className = st;
    $("status").textContent = WORD[st] || "Not protected";
    const typing = s.idle_s != null && s.idle_s < 4 && v.kind !== "software";

    let text, acts = [], aside = "";
    if (hold) {
      const k = hold.keyboard || {}, name = k.product || "A keyboard";
      if (hold.blocked) { text = `${name} is blocked. Unplug it to get your keyboard back.`; acts = [["allow-once", "Changed my mind: allow once"]]; }
      else {
        text = (k.vendor_note ? "Identified as " + idNote(k) + "." : `${name} is not one of your trusted keyboards.`) + " Nothing it types gets through until you choose.";
        acts = [["keep", "Keep blocked", 1], ["allow-once", "Allow once"], ["allow-always", "Always allow"]];
        const left = Math.ceil(hold.until - s.now);
        aside = "Your own keyboard is off too until you choose. Use the trackpad or mouse. " + (set.away_mode ? "Away mode is on, so it stays held until you choose."
          : left > 0 ? `If you do nothing, this keyboard can type in <b>${left} s</b>. Fast scripted typing is still blocked.` : "The hold is ending.");
      }
    } else if (st === "alert") text = (v.explanation || "Typing no hand could produce was blocked.") + (S.inTest || s.in_test ? " This was the safe test: nothing was plugged in." : " Unplug the device. Your keyboard works again two seconds after it stops typing.");
    else if (st === "paused") { text = s.paused_until ? `Protection is off until ${clock(s.paused_until)}.` : "Protection is off until you resume it."; acts = [["resume", "Resume now", 1]]; }
    else if (st === "observing") { text = "DuckyGuard can see typing but cannot stop it until you turn on Accessibility."; acts = [["perm-accessibility", "Open System Settings", 1]]; aside = "It starts blocking as soon as the switch is on."; }
    else if (st === "recording") { text = "Record only is on: DuckyGuard notes what it would block and blocks nothing."; acts = [["record-off", "Turn blocking on", 1]]; }
    else if (st === "no_permission") { text = "DuckyGuard cannot see typing until you turn on Input Monitoring."; acts = [["perm-input_monitoring", "Open System Settings", 1]]; aside = "macOS may ask you to quit and reopen DuckyGuard after you turn it on."; }
    else if (st === "error") { text = "DuckyGuard could not start watching the keyboard."; acts = [["restart", "Try again", 1]]; }
    else { text = typing ? "Typing looks human." : "No typing right now."; acts = [["test", S.testBusy ? "Testing…" : "Run safe test"]]; }
    $("verdict").textContent = text;
    once("decide", [acts, S.testBusy], () => { rebuild($("decide"), acts.map(([id, label, primary]) => `<button class="${primary ? "primary" : "ghost"}" type="button" data-act="${id}"${id === "test" && S.testBusy ? " disabled" : ""}>${esc(label)}</button>`).join("")); $("decide").hidden = !acts.length; });
    once("aside", aside, () => { $("aside").innerHTML = aside; $("aside").hidden = !aside; });

    // readings on the plate
    $("h-burst").textContent = typing ? plural(f.burst_len || 0, "key") : "—";
    $("h-hold").textContent = typing && f.median_hold_ms != null ? Math.round(f.median_hold_ms) + " ms" : "—";
    $("h-verdict").textContent = st === "alert" ? "a machine" : hold ? "held" : st === "paused" ? "off" : typing ? "a hand" : "quiet";
    $("h-rate").textContent = typing && f.cps != null ? Number(f.cps).toFixed(1) + "/s" : "idle";
    $("h-halo").textContent = Math.min(64, (s.recent || []).length);
    $("h-cv").textContent = typing && f.cv != null ? (f.cv < .15 ? "even " : "uneven ") + Math.round(f.cv * 100) + "%" : "—";

    const incs = (s.incidents || []).filter(i => !S.hidden.has(i.id)), midnight = new Date().setHours(0, 0, 0, 0) / 1000, today = incs.filter(i => i.started_at >= midnight).length;
    $("cap-r").textContent = hold ? plural(hold.dropped, "key") + " blocked so far" : today ? today + " blocked today" : "Nothing blocked today";
    const top = incs[0], trusted = Object.keys(s.trusted || {}).length, prot = (s.shields || []).filter(x => !["dropping", "monitor_only"].includes(x.id));
    once("facts", [top && top.id, trusted, prot.map(x => x.on)], () => {
      $("facts").innerHTML =
        `<li>${top ? `Last blocked: ${esc(day(top.started_at))}, ${plural(top.blocked_count || 0, "key")}.<button type="button" data-go="timeline">View</button>` : "Nothing blocked yet."}</li>` +
        `<li>${trusted ? plural(trusted, "keyboard") + " trusted, plus the built-in one." : "Only the built-in keyboard is trusted."}<button type="button" data-go="devices">Manage</button></li>` +
        `<li>${prot.filter(x => x.on).length} of ${prot.length} protections on.<button type="button" data-go="settings">Settings</button></li>`;
    });
  }

  function chrome(s) {
    const ids = (s.incidents || []).map(i => i.id);
    if (S.seenInc === null || S.tab === "timeline") S.seenInc = new Set(ids);
    $("n-incidents").textContent = ids.filter(id => !S.seenInc.has(id)).length || "";
    $("n-devices").textContent = (s.keyboards || []).filter(k => !k.trusted && !k.built_in).length || "";
    const paused = s.status === "paused";
    $("b-pause").textContent = paused ? "Resume" : "Pause"; $("b-pause").hidden = ["no_permission", "error"].includes(s.status);
    if (paused) closePauseMenu();
    let n = null;
    if (s.error && s.status !== "error") n = ["DuckyGuard hit an error and may not be blocking.", "Restart protection", () => send("restart")];
    else if (s.secure_input) n = ["A password field has Secure Input on. macOS hides keys from DuckyGuard until it closes.", null];
    else if (s.update && s.update.newer) n = [`Version ${s.update.latest} is available.`, "Download", () => send("open_url", { url: s.update.url })];
    $("notice").hidden = !n;
    if (n) { $("notice-text").textContent = n[0]; const b = $("notice-act"); b.hidden = !n[1]; b.textContent = n[1] || ""; b.onclick = n[2] || null; }
  }

  // ───────────────────────────────────────────────────────────── timeline
  function timeline(s) {
    const list = (s.incidents || []).filter(i => !S.hidden.has(i.id));
    once("timeline", [list.map(i => i.id), S.open, Object.keys(s.trusted || {})], () => {
      $("b-clear").hidden = !list.length;
      mirrors.length = 2;
      if (!list.length) {
        $("incidents").innerHTML = `<div class="empty"><pre class="ascii"></pre><p>Nothing blocked yet. Run the safe test to watch a block happen with one harmless sentence.</p><button class="ghost" type="button" data-act="test">Run safe test</button></div>`;
        mirrors.push({ pre: $("incidents").querySelector(".ascii"), cols: 46, rows: 23 }); return;
      }
      rebuild($("incidents"), list.map(inc => {
        const v = inc.verdict || {}, f = v.features || {}, kb = inc.keyboard || {}, isHold = v.kind === "hold", openRow = S.open === inc.id;
        const title = isHold ? "Keyboard held" : inc.simulated ? "Safe test blocked" : inc.can_drop === false ? "Would have blocked (record only)" : "Scripted typing blocked";
        let d = "";
        if (openRow) {
          const press = f.median_hold_ms != null ? f.median_hold_ms : f.instant_release_median_ms;
          const kv = [["Got through", inc.keys_before_block], ["Blocked", inc.blocked_count], ["Rate", f.cps != null ? f.cps + "/s" : "—"], ["Rhythm", f.cv != null ? (f.cv < .15 ? "even" : "uneven") : "—"], ["Key press", press != null ? press + " ms" : "—"]];
          const canTrust = isHold && kb.key && !(s.trusted || {})[kb.key] && !kb.built_in, why = reasonOf(inc);
          d = `<div class="detail">
            ${inc.explanation && inc.explanation !== inc.summary ? `<p>${esc(inc.explanation)}</p>` : ""}
            <dl class="kv">${kv.map(([k, val]) => `<div><dt>${k}</dt><dd>${esc(val)}</dd></div>`).join("")}</dl>
            ${why && !isHold ? `<p class="sub">Why: ${esc(why)}.</p>` : ""}
            ${isHold ? "" : `<div class="sub">Got through to the front app</div><pre>${esc(inc.prefix_text || "(nothing)")}</pre><div class="sub">Blocked</div><pre>${esc(inc.blocked_text || "(nothing)")}</pre>`}
            ${kb.product || kb.vendor_hex ? `<p class="sub">${isHold ? "Keyboard" : "Probably from"}: ${esc(kb.product || "Unnamed keyboard")} (${esc(kb.vendor_hex)}:${esc(kb.product_hex)})${isHold ? "" : ", an untrusted keyboard connected shortly before"}${kb.vendor_note ? ". Identified as " + esc(idNote(kb)) : ""}.</p>` : ""}
            ${!isHold && !inc.simulated ? `<p class="sub">Was this you? DuckyGuard cannot tell keyboards apart, so trusting one does not exempt it. Pause for a minute and try again.</p>` : ""}
            <div class="decide">
              <button class="ghost" type="button" data-export="${esc(inc.id)}">Export report</button>
              ${canTrust ? `<button class="ghost" type="button" data-trust="${esc(kb.key)}">Trust this keyboard</button>` : ""}
              ${!isHold && !inc.simulated ? `<button class="ghost" type="button" data-pause="60">Pause for 1 minute</button>` : ""}
              <button class="ghost danger" type="button" data-del="${esc(inc.id)}">Delete</button>
            </div></div>`;
        }
        return `<div class="row incident"><button type="button" data-open="${esc(inc.id)}" aria-expanded="${openRow}">
            <h3>${esc(title)}</h3><p>${esc(inc.summary || inc.explanation || "")}</p>
            <div class="meta">${esc(day(inc.started_at))} · ${inc.blocked_count} blocked, ${inc.keys_before_block} got through${kb.product ? " · " + esc(kb.product) : ""}</div></button>${d}</div>`;
      }).join(""));
    });
  }
  // Deleting hides the rows at once and removes the files eight seconds later, unless Undo is pressed.
  function softDelete(ids, label, all) {
    ids.forEach(id => S.hidden.add(id)); S.open = null; if (S.snap) apply(S.snap);
    const timer = setTimeout(() => all ? send("clear_incidents") : ids.forEach(id => send("delete_incident", { id })), 8000);
    toast(label, "", { label: "Undo", fn: () => { clearTimeout(timer); ids.forEach(id => S.hidden.delete(id)); if (S.snap) apply(S.snap); } });
  }

  // ───────────────────────────────────────────────────────────── devices
  function devices(s) {
    const hold = s.hold, kbs = s.keyboards || [], trusted = s.trusted || {};
    once("devices", [kbs, Object.keys(trusted), hold && [hold.key, hold.blocked]], () => {
      rebuild($("keyboards"), kbs.map(k => {
        const held = hold && hold.key === k.key, state = k.built_in ? "Built in" : held ? (hold.blocked ? "Blocked" : "Held") : k.trusted ? "Trusted" : "Not trusted";
        const acts = held ? (hold.blocked ? "" : `<button class="primary" type="button" data-act="keep">Keep blocked</button>`) + `<button class="ghost" type="button" data-act="allow-once">Allow once</button>` + (hold.blocked ? "" : `<button class="ghost" type="button" data-act="allow-always">Always allow</button>`)
          : k.built_in ? "" : k.trusted ? `<button class="ghost" type="button" data-untrust="${esc(k.key)}">Stop trusting</button>` : `<button class="ghost" type="button" data-trust="${esc(k.key)}">Trust</button>`;
        return `<div class="row"><div><h3>${esc(k.product || "Unnamed keyboard")}</h3>
          ${k.vendor_note ? `<p>Identified as ${esc(idNote(k))}.</p>` : ""}
          <div class="meta">${esc(k.vendor_hex)}:${esc(k.product_hex)} · ${esc(k.transport || "?")}${k.vendor_name ? " · registered to " + esc(k.vendor_name) : ""}${k.manufacturer ? " · says " + esc(k.manufacturer) : ""} · serial ${esc(k.serial || "none")}</div></div>
          <div class="acts"><span class="chip ${k.trusted || k.built_in ? "on" : ""}">${state}</span>${acts}</div></div>`;
      }).join("") || `<p class="empty">DuckyGuard cannot list keyboards. Check Input Monitoring in Settings.</p>`);
      const gone = Object.entries(trusted).filter(([key]) => !kbs.some(k => k.key === key));
      $("trusted-head").hidden = !gone.length;
      rebuild($("trusted"), gone.map(([key, t]) => `<div class="row"><div><h3>${esc(t.product || key)}</h3><div class="meta">${esc(key)}</div></div><div class="acts"><button class="ghost" type="button" data-untrust="${esc(key)}">Stop trusting</button></div></div>`).join(""));
    });
  }

  // ───────────────────────────────────────────────────────────── settings
  const SETTINGS = {
    "set-protect": [
      ["hold_new_keyboards", "Hold new keyboards", "Block every key from the moment an untrusted keyboard appears until you choose. Your own keyboard is off too while it waits."],
      ["away_mode", "Away mode", "Holds never run out. Nothing new can type until you are back to choose."],
      ["lock_on_block", "Lock the screen on a block", "Lock the screen when scripted typing is blocked."],
    ],
    "set-app": [
      ["launch_at_login", "Open at login", "Start DuckyGuard when you log in."],
      ["keep_alive", "Restart if it stops", "With Open at login: start again after a crash or a kill, not after Quit."],
      ["quiet_mode", "Mute alerts", "Block and record with no sound and no notification."],
      ["check_updates", "Check for updates", "One request a day to GitHub. It tells you; it never downloads."],
    ],
    "set-advanced": [
      ["monitor_only", "Record only", "Note what would be blocked and block nothing. For trying DuckyGuard out."],
      ["score_software_input", "Also judge typing from apps", "Password managers and text expanders will be blocked."],
    ],
  };
  const LOWERS = { monitor_only: true, hold_new_keyboards: false };        // the value that turns protection down
  const HOLD_FOR = [[20, "20 s"], [60, "1 min"], [120, "2 min"]];
  function settings(s) {
    const set = Object.assign({}, s.settings || {}, { launch_at_login: s.launch_at_login });
    once("settings", [set, s.permissions, s.data_dir, s.update && s.update.message], () => {
      for (const [box, rows] of Object.entries(SETTINGS)) rebuild($(box), rows.map(([key, title, note]) =>
        `<div class="row"><div><h3>${title}</h3><p>${note}${key === "check_updates" && set.check_updates && s.update && s.update.message ? " " + esc(s.update.message) : ""}</p></div><div class="acts"><button class="switch" type="button" role="switch" aria-checked="${!!set[key]}" aria-label="${title}" data-set="${key}" data-val="${!set[key]}"></button></div></div>`).join("")
        + (box === "set-protect" ? `<div class="row"><div><h3>Hold length</h3><p>How long a new keyboard waits for you before it may type.</p></div><div class="acts seg">${HOLD_FOR.map(([secs, label]) => `<button type="button" data-holdfor="${secs}" aria-pressed="${Math.round(set.hold_seconds || 20) === secs}">${label}</button>`).join("")}</div></div>` : ""));
      rebuild($("set-access"), access(s));
      rebuild($("set-data"), `<div class="row"><div><h3>DuckyGuard ${esc(s.version || "")}</h3><p>Free, MIT licence. Tested on one Flipper Zero; the docs say what that covers.</p></div><div class="acts"><button class="ghost" type="button" data-url="${esc(s.project_url || "")}">Source</button></div></div>
        <div class="row"><div><h3>Your data stays on this Mac</h3><div class="meta">${esc(s.data_dir || "")}</div></div><div class="acts"><button class="ghost" type="button" data-act="folder">Show</button></div></div>
        <div class="row"><div><h3>Safe test</h3><p>Types one harmless sentence fast, into this window only.</p></div><div class="acts"><button class="ghost" type="button" data-act="test">Run</button></div></div>`);
    });
  }
  function access(s) {
    const p = s.permissions || {};
    return [["input_monitoring", "Input Monitoring", "macOS's name for letting an app see every key. DuckyGuard uses the timing, and keeps the text only for bursts it blocks."], ["accessibility", "Accessibility", "Lets DuckyGuard block keys. Without it, it can only warn."]].map(([k, t, n]) =>
      `<div class="row"><div><h3>${t}</h3><p>${n}</p></div><div class="acts">${p[k] ? `<span class="chip on">On</span>` : `<button class="ghost" type="button" data-act="perm-${k}">Open System Settings</button>`}</div></div>`).join("");
  }

  function onboarding(s) {
    const show = !(s.settings || {}).onboarded;
    $("onboard").hidden = !show;
    if (!show) return;
    const p = s.permissions || {}, mine = (s.keyboards || []).filter(k => !k.built_in && !k.trusted);
    once("onboard", p, () => rebuild($("ob-access"), access(s)));
    once("onboard-kb", mine.map(k => k.key), () => {             // keyed on the keyboards only, so ticking a box survives the next snapshot
      $("ob-keyboards").innerHTML = mine.length ? `<div class="note">Trust the keyboards connected now, so they are never held:</div>` + mine.map(k => `<label class="check"><input type="checkbox" checked value="${esc(k.key)}">${esc(k.product || "Unnamed keyboard")} <span>${esc(k.vendor_hex)}:${esc(k.product_hex)} · ${esc(k.transport || "")}</span></label>`).join("") : "";
    });
    $("b-start").disabled = !p.can_block; $("b-start-observe").hidden = !(p.can_observe && !p.can_block);
    $("ob-note").textContent = p.can_block ? "" : p.can_observe ? "Turn on Accessibility to block." : "Turn on Input Monitoring first. macOS may ask you to quit and reopen DuckyGuard.";
  }
  const finishOnboarding = () => send("finish_onboarding", { trust: [...document.querySelectorAll("#ob-keyboards input:checked")].map(i => i.value) });

  // ───────────────────────────────────────────────────────────── input
  function closePauseMenu() { $("pause-menu").hidden = true; $("b-pause").setAttribute("aria-expanded", "false"); }
  const ACT = {
    keep: h => h && send("block_keyboard", { key: h.key }),
    "allow-once": h => h && send("allow_keyboard", { key: h.key, trust: false }),
    "allow-always": (h, e) => h && !fromKeys(e) && send("allow_keyboard", { key: h.key, trust: true }),
    resume: () => send("resume"), restart: () => send("restart"), test: () => send("test"), folder: () => send("open_data_folder"),
    "record-off": () => send("set_setting", { key: "monitor_only", value: false }),
    "perm-accessibility": () => send("open_settings", { which: "accessibility" }),
    "perm-input_monitoring": () => send("open_settings", { which: "input_monitoring" }),
  };
  document.addEventListener("click", e => {
    const b = e.target.closest("button");
    if (!b || !$("pause").contains(b)) closePauseMenu();
    if (!b) return;
    const d = b.dataset;
    if (d.tab) return go(d.tab);
    if (d.go) return go(d.go);
    if (d.act && ACT[d.act]) return ACT[d.act](S.snap && S.snap.hold, e);
    if (d.pause) { if (fromKeys(e)) return; closePauseMenu(); return send("pause", d.pause === "forever" ? {} : { seconds: Number(d.pause) }); }
    if (d.set) { const value = d.val === "true"; if (LOWERS[d.set] === value && fromKeys(e)) return; return send("set_setting", { key: d.set, value }); }
    if (d.holdfor) return send("set_setting", { key: "hold_seconds", value: Number(d.holdfor) });
    if (d.trust) { if (fromKeys(e)) return; return send("trust", { key: d.trust }); }
    if (d.untrust) return send("untrust", { key: d.untrust });
    if (d.export) return send("export", { id: d.export });
    if (d.del) return softDelete([d.del], "Incident deleted.");
    if (d.perm) return send("open_settings", { which: d.perm });
    if (d.url) return send("open_url", { url: d.url });
    if (d.open) { S.open = S.open === d.open ? null : d.open; if (S.snap) timeline(S.snap); return; }
    if (b.id === "b-ascii") { const on = b.getAttribute("aria-pressed") !== "true"; b.setAttribute("aria-pressed", on); b.textContent = on ? "View as engraving" : "View as ASCII"; $("ascii-plate").hidden = !on; return; }
    if (b.id === "b-pause") { if (S.snap && S.snap.status === "paused") return send("resume"); const open = $("pause-menu").hidden; $("pause-menu").hidden = !open; b.setAttribute("aria-expanded", open); return; }
    if (b.id === "b-clear") { const ids = ((S.snap || {}).incidents || []).map(i => i.id).filter(id => !S.hidden.has(id)); return softDelete(ids, `Deleted ${plural(ids.length, "incident")}.`, true); }
    if (b.id === "b-start" || b.id === "b-start-observe") return finishOnboarding();
  });
  $("nav").addEventListener("mousedown", e => { if (e.button === 0 && !e.target.closest("button, .menu")) send("drag"); });   // the bar moves the window
  addEventListener("keydown", e => {
    if (e.metaKey && "1234".includes(e.key)) { e.preventDefault(); return go(["overview", "timeline", "devices", "settings"][e.key - 1]); }
    if (e.key === "Escape") { if (!$("pause-menu").hidden) return closePauseMenu(); if (S.open) { S.open = null; if (S.snap) timeline(S.snap); } }
  });
  addEventListener("contextmenu", e => { if (!String(getSelection())) e.preventDefault(); });     // the only useful menu here is Copy

  // ───────────────────────────────────────────────────────────── preview (index.html?preview in a browser, no app behind the page)
  const Mock = (() => {
    const now = () => Date.now() / 1000;
    const M = { settings: { onboarded: q.get("onboard") !== "1", hold_new_keyboards: true, hold_seconds: 20, away_mode: false, monitor_only: false, lock_on_block: false, keep_alive: false, quiet_mode: false, check_updates: false, score_software_input: false },
      running: true, status: "protected", pausedUntil: null, recent: [], incidents: [], hold: null, trusted: {}, blocks: 0, keys: 0, verdict: null, launch: false, perms: { input_monitoring: true, accessibility: true }, error: null };
    const mine = { key: "0000:0000:FIFO:Apple Internal Keyboard / Trackpad", product: "Apple Internal Keyboard / Trackpad", manufacturer: "Apple", vendor_hex: "0000", product_hex: "0000", vendor_name: "", vendor_note: "", serial: "", transport: "FIFO", built_in: true };
    const desk = { key: "05ac:024f:USB:Keychron K2", product: "Keychron K2", manufacturer: "Keychron", vendor_hex: "05ac", product_hex: "024f", vendor_name: "Apple, Inc.", vendor_note: "", serial: "", transport: "USB", built_in: false };
    const flip = { key: "046d:c529:USB:Flipper Zero", product: "Flipper Zero", manufacturer: "Flipper Devices Inc.", vendor_hex: "046d", product_hex: "c529", vendor_name: "Logitech, Inc.", vendor_note: "Flipper Zero (names itself in its USB strings) (definite)", serial: "", transport: "USB", built_in: false };
    let kbs = [mine, desk], burst = 0, t = now(), nextAt = 0, left = 0, lastKey = 0;
    const key = (gap, hold, kind, rule) => { burst = gap > 350 ? 1 : burst + 1; t = now(); M.keys++; M.recent.push({ t, gap_ms: gap, hold_ms: hold, kind, block: kind === "machine" }); if (M.recent.length > 64) M.recent.shift();
      const g = M.recent.slice(-12).map(e => e.gap_ms).filter(x => x < 1500), mean = g.reduce((a, b) => a + b, 0) / (g.length || 1), sd = Math.sqrt(g.reduce((a, b) => a + (b - mean) ** 2, 0) / (g.length || 1));
      M.verdict = { kind, block: kind === "machine", explanation: kind === "machine" ? "A keyboard pressed 6 keys in a row and let go of each within 1 ms. A finger holds a key 60-150 ms. DuckyGuard blocked it." : "Looks like a person typing.",
        features: { cps: +(1000 / mean).toFixed(1), cv: +(sd / mean).toFixed(3), median_hold_ms: hold, burst_len: burst, rule: rule || null } }; };
    function loop() {
      const n = performance.now();
      if (M.pausedUntil && now() > M.pausedUntil) { M.pausedUntil = null; M.running = true; M.status = "protected"; }
      if (M.running && !M.hold && M.status === "protected" && n > nextAt) { if (left <= 0) { left = 6 + Math.floor(Math.random() * 20); nextAt = n + 600 + Math.random() * 1500; } else { left--; const g = n - lastKey > 500 ? 600 : 62 * Math.exp(1.25 * Math.random() + .35 * Math.random()); key(g, 70 + 55 * Math.random(), "human"); lastKey = n; nextAt = n + Math.min(g, 400); } }
      if (M.hold && M.hold.dropped < 124) M.hold.dropped = Math.min(124, M.hold.dropped + 2);
      if (M.hold && !M.hold.blocked && !M.settings.away_mode && now() > M.hold.until) endHold("expired");
      setTimeout(loop, 50);
    }
    function incident(kind, extra) { const id = new Date().toISOString().replace(/\D/g, "").slice(0, 14) + M.incidents.length; M.incidents.unshift(Object.assign({ id, started_at: now(), simulated: false, can_drop: true, keyboard: kind === "hold" ? flip : null, prefix_text: "", blocked_text: "", analysis: null }, extra)); }
    function endHold(result) { const h = M.hold; M.hold = null; M.status = "protected"; kbs = kbs.filter(k => k !== flip); const text = `Flipper Zero was held as soon as it was plugged in. ${h.dropped} keys were blocked. None got through.`;
      incident("hold", { hold_result: result, keys_before_block: 0, blocked_count: h.dropped, summary: text, explanation: text, verdict: { kind: "hold", reasons: [], features: { rule: "Q: new keyboard held until you choose" } } }); if (result === "allowed") M.trusted[flip.key] = flip; }
    function snap() { return { version: "2.1.0", status: M.status, running: M.running, can_block: M.perms.accessibility, now: now(), paused_until: M.pausedUntil, error: M.error,
        permissions: Object.assign({ can_observe: M.perms.input_monitoring, can_block: M.perms.accessibility }, M.perms), settings: M.settings, launch_at_login: M.launch,
        idle_s: now() - t, keys_seen: M.keys, blocks: M.blocks, in_quarantine: M.status === "alert", last_verdict: M.verdict, recent: M.recent, keyboards: kbs.map(k => Object.assign({ trusted: k.built_in || !!M.trusted[k.key] }, k)), trusted: M.trusted, hold: M.hold, secure_input: false,
        incidents: M.incidents, data_dir: "~/Library/Application Support/DuckyGuard", project_url: "https://github.com/stevenhainley/DuckyGuard", update: null,
        shields: [["timing", 1], ["hold_time", 1], ["keyboard_hold", M.settings.hold_new_keyboards], ["impostor", 1], ["away_mode", M.settings.away_mode], ["lock_on_block", M.settings.lock_on_block], ["keep_alive", M.settings.keep_alive], ["monitor_only", M.settings.monitor_only]].map(([id, on]) => ({ id, label: id, on: !!on, note: "" })) }; }
    const push = (type, data) => window.dg.receive({ type, data });
    function handle(m) {
      if (m.cmd === "set_setting") { if (m.key === "launch_at_login") M.launch = m.value; else M.settings[m.key] = m.value; }
      else if (m.cmd === "pause" || m.cmd === "stop") { M.running = false; M.status = "paused"; M.pausedUntil = m.seconds ? now() + m.seconds : null; }
      else if (m.cmd === "resume" || m.cmd === "start" || m.cmd === "restart") { M.running = true; M.status = "protected"; M.pausedUntil = null; M.error = null; }
      else if (m.cmd === "finish_onboarding") { M.settings.onboarded = true; (m.trust || []).forEach(k => { const kb = kbs.find(x => x.key === k); if (kb) M.trusted[k] = kb; }); }
      else if (m.cmd === "test") { push("test_begin", {}); let i = 0; const typeOne = () => { if (i < 6) { key(i ? 12 : 600, 1.2, "human"); i++; setTimeout(typeOne, 30); } else { key(12, 1.1, "machine", "J: 5 keys under 20 ms apart, each released instantly"); M.status = "alert"; M.blocks++; push("block_started", {});
            setTimeout(() => { M.status = "protected"; incident("block", { simulated: true, keys_before_block: 4, blocked_count: 78, prefix_text: "This", blocked_text: " is a harmless DuckyGuard test sentence, typed faster than any hand could type it.", summary: "A keyboard typed 82 keys at 83 keys a second; 78 were blocked.", explanation: M.verdict.explanation, verdict: M.verdict }); push("test_end", { completed: true }); }, 2600); } }; setTimeout(typeOne, 900); }
      else if (m.cmd === "plug") { kbs = [...kbs.filter(k => k !== flip), flip]; M.hold = { key: flip.key, keyboard: flip, flags: ["vendor mismatch", "known injector identity"], since: now(), until: now() + M.settings.hold_seconds, blocked: false, dropped: 0 }; M.status = "holding"; }
      else if (m.cmd === "allow_keyboard") endHold(m.trust ? "allowed" : "allowed once"); else if (m.cmd === "block_keyboard" && M.hold) { M.hold.blocked = true; setTimeout(() => M.hold && endHold("unplugged"), 6000); }
      else if (m.cmd === "trust") M.trusted[m.key] = kbs.find(k => k.key === m.key) || flip; else if (m.cmd === "untrust") delete M.trusted[m.key];
      else if (m.cmd === "delete_incident") M.incidents = M.incidents.filter(i => i.id !== m.id); else if (m.cmd === "clear_incidents") M.incidents = [];
      else if (m.cmd === "export") push("toast", { text: "Report saved (preview only)." });
      push("snapshot", snap());
    }
    function start() {
      const state = q.get("state");
      if (state === "observing") { M.perms.accessibility = false; M.status = "observing"; }
      if (state === "noperm") { M.perms = { input_monitoring: false, accessibility: false }; M.status = "no_permission"; M.running = false; }
      if (state === "error") { M.status = "error"; M.running = false; M.error = "could not start the keyboard tap"; }
      if (state === "recording") M.settings.monitor_only = true;
      loop(); setInterval(() => push("snapshot", snap()), 1000); push("snapshot", snap());
      if (state === "hold") handle({ cmd: "plug" }); if (state === "block") handle({ cmd: "test" }); if (state === "paused") handle({ cmd: "pause", seconds: 300 });
      if (q.get("ascii")) setTimeout(() => $("b-ascii").click(), 400);
      if (q.get("seed")) { handle({ cmd: "plug" }); M.hold.dropped = 124; handle({ cmd: "allow_keyboard", trust: false }); handle({ cmd: "trust", key: desk.key }); }
      if (q.get("tab")) setTimeout(() => { go(q.get("tab")); if (q.get("open")) setTimeout(() => { const r = document.querySelector(".incident > button"); if (r) r.click(); }, 80); }, 60);
      addEventListener("keydown", e => { if (e.key === "F9") handle({ cmd: "plug" }); });
    }
    return { handle, start };
  })();

  if (native) send("ready");
  else if (preview) Mock.start();
  else { document.body.className = "error"; $("status").textContent = "Not connected"; $("verdict").textContent = "This window lost contact with DuckyGuard. Quit and reopen it from the menu bar."; }
})();
