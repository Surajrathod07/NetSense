"use strict";
const el = (id) => document.getElementById(id);
const text = (id, value) => {
  el(id).textContent = value;
};
const make = (tag, value) => {
  const n = document.createElement(tag);
  if (value !== undefined) n.textContent = value;
  return n;
};
const ms = (n) => (n == null ? "—" : n.toFixed(2));
const clock = (n) => new Date(n * 1000).toLocaleTimeString();
let offset = 0,
  generation = 0;
async function api(path, payload) {
  const options =
    payload === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        };
  const r = await fetch("/api/" + path, {
    ...options,
    signal: AbortSignal.timeout(8000),
  });
  const b = await r.json();
  if (!r.ok) throw Error(b.error || "Request failed");
  return b.data;
}
function pairs(id, obj) {
  el(id).replaceChildren(
    ...Object.entries(obj).flatMap(([key, v]) => [
      make("dt", key),
      make("dd", v ?? "—"),
    ]),
  );
}
function stream(rows) {
  el("rows").replaceChildren(
    ...rows.slice(0, 30).map((m) => {
      const tr = make("tr"),
        link = make("button", m.text),
        badge = make("span", m.label);
      link.className = "msg";
      link.onclick = () => {
        pairs("fields", m);
        el("details").showModal();
      };
      badge.className = "pill " + m.label.toLowerCase();
      for (const value of [
        clock(m.received),
        m.id.slice(0, 8),
        link,
        m.domain,
        badge,
        m.sender,
        ms(m.wait_ms),
        ms(m.latency_ms),
        m.status,
      ]) {
        const td = make("td");
        td.append(value);
        tr.append(td);
      }
      return tr;
    }),
  );
  el("empty").hidden = rows.length > 0;
  text("empty", "No messages match this view.");
  text(
    "page",
    rows.length
      ? offset + 1 + "–" + (offset + Math.min(30, rows.length))
      : "0 messages",
  );
  el("prev").disabled = offset === 0;
  el("next").disabled = rows.length <= 30;
}
function analytics(m) {
  const c = m.classes.CRITICAL,
    n = m.classes.NORMAL,
    total = c.n + n.n;
  text("total", total);
  text("high", c.n);
  text("normal", n.n);
  text("mean", ms(m.avg_network) + (m.avg_network == null ? "" : " ms"));
  const share = total ? (100 * c.n) / total : 0;
  el("share").style.width = share + "%";
  el("share").parentElement.style.opacity = total ? 1 : 0.25;
  text(
    "ratio",
    total
      ? share.toFixed(0) +
          "% critical · " +
          (100 - share).toFixed(0) +
          "% normal"
      : "No deliveries recorded",
  );
  el("bars").replaceChildren(
    ...m.minutes.map((v, i) => {
      const bar = make("i");
      bar.style.height = (90 * v) / Math.max(1, ...m.minutes) + "px";
      bar.title = 14 - i + " min ago · " + v + " messages";
      return bar;
    }),
  );
  el("bars").setAttribute(
    "aria-label",
    "Counts oldest to newest: " + m.minutes.join(", "),
  );
  const table = make("table");
  for (const [i, row] of [
    ["Measurement", "Critical", "Normal"],
    ...Object.entries({
      "Mean network": "avg_network",
      "95th percentile": "p95_network",
      "Mean queue wait": "avg_wait",
      "Longest queue wait": "max_wait",
      "Mean queue + network": "avg_total",
    }).map(([k, v]) => [k, ms(c[v]), ms(n[v])]),
  ].entries()) {
    const tr = make("tr");
    row.forEach((v) => tr.append(make(i ? "td" : "th", v)));
    table.append(tr);
  }
  el("performance").replaceChildren(table);
}
async function refresh() {
  const seq = ++generation;
  const args = new URLSearchParams(new FormData(el("filters")));
  if (args.get("since"))
    args.set("since", new Date(args.get("since")).getTime() / 1000);
  args.set("limit", 31);
  args.set("offset", offset);
  try {
    const [rows, m, s, events, model] = await Promise.all([
      api("messages?" + args),
      api("metrics"),
      api("system/status"),
      api("activity"),
      api("model/status"),
    ]);
    if (seq !== generation) return;
    stream(rows);
    analytics(m);
    text("node", s.config.node);
    text("connection", "● Online");
    el("connection").className = "";
    text("pace", "Demo spacing " + s.config.demo_delay_ms + " ms");
    pairs("system", {
      Classifier: model.selected + " · threshold " + model.threshold,
      "Test recall / precision":
        (100 * model.test.recall).toFixed(1) +
        "% / " +
        (100 * model.test.precision).toFixed(1) +
        "% (synthetic)",
      Receiver: s.config.listen_host + ":" + s.config.tcp_port,
      Destination: s.config.peer_host + ":" + s.config.peer_port,
      "Worker / database":
        (s.sender ? "running" : "stopped") + " / " + s.database,
      "One-way timing": s.config.clocks_synced
        ? "Remote clocks confirmed by operator"
        : "Loopback only · remote timing hidden",
      "Frames sent": m.transmitted_frames,
      Scheduler: s.config.mode,
      "Waiting · critical / normal":
        s.queues.CRITICAL.waiting + " / " + s.queues.NORMAL.waiting,
      "Queued this session · C / N":
        s.queues.CRITICAL.queued + " / " + s.queues.NORMAL.queued,
      "Outbound acknowledged / failed":
        (m.outbound.acknowledged || 0) + " / " + (m.outbound.failed || 0),
    });
    el("events").replaceChildren(
      ...events.map((e) => {
        const div = make("div");
        div.className = "event";
        [clock(e.at), e.event, e.detail].forEach((v) =>
          div.append(make("span", v)),
        );
        return div;
      }),
    );
  } catch (e) {
    if (seq === generation) {
      text("connection", "Offline · retrying");
      el("connection").className = "offline";
    }
  }
}
el("filters").onsubmit = (e) => e.preventDefault();
let debounce;
el("filters").oninput = () => {
  offset = 0;
  clearTimeout(debounce);
  debounce = setTimeout(refresh, 180);
};
el("prev").onclick = () => {
  offset = Math.max(0, offset - 30);
  refresh();
};
el("next").onclick = () => {
  offset += 30;
  refresh();
};
el("close").onclick = () => el("details").close();
document.querySelectorAll("[data-sample]").forEach(
  (b) =>
    (b.onclick = () => {
      el("compose").elements.text.value = b.dataset.sample;
    }),
);
async function submit(load) {
  const button = load ? el("load") : el("compose").querySelector(".primary");
  button.disabled = true;
  try {
    const r = await api(
      load ? "test/load" : "messages/send",
      load ? { count: 12 } : Object.fromEntries(new FormData(el("compose"))),
    );
    text(
      "feedback",
      load
        ? "Accepted " + r.length + " messages."
        : "Queued " + r.label + " · " + r.id.slice(0, 8),
    );
    await refresh();
  } catch (e) {
    text("feedback", e.message);
  } finally {
    button.disabled = false;
  }
}
el("compose").onsubmit = (e) => {
  e.preventDefault();
  submit(false);
};
el("load").onclick = () => submit(true);
setInterval(() => text("clock", new Date().toLocaleTimeString()), 1000);
(async function poll() {
  await refresh();
  setTimeout(poll, 2000);
})();
