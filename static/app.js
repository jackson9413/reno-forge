/* reno-forge front end. Vanilla JS, no build step, no dependencies. */
(function () {
  "use strict";

  var state = { result: null, filter: "all", samples: [], profiles: [] };

  var $ = function (id) { return document.getElementById(id); };
  var money = function (v) {
    if (v === null || v === undefined) return "-";
    return "$" + Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };
  var num = function (v, digits) {
    if (v === null || v === undefined) return "-";
    return Number(v).toLocaleString(undefined, { maximumFractionDigits: digits === undefined ? 1 : digits });
  };
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function clear(node) { while (node && node.firstChild) node.removeChild(node.firstChild); }

  /* ---------------------------------------------------------------- boot */
  function boot() {
    loadProfiles();
    loadSamples();
    $("analyze").addEventListener("click", analyze);
    $("save").addEventListener("click", saveRun);
    $("filters").addEventListener("click", function (ev) {
      var btn = ev.target.closest(".chip");
      if (!btn) return;
      state.filter = btn.dataset.sev;
      Array.prototype.forEach.call($("filters").children, function (c) {
        c.classList.toggle("active", c === btn);
      });
      renderFindings();
    });
    $("results").addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-export]");
      if (!btn) return;
      exportAs(btn.dataset.export);
    });
    $("history-panel").addEventListener("click", function (ev) {
      var star = ev.target.closest(".star");
      if (!star) return;
      var id = star.getAttribute("data-id");
      var value = parseInt(star.getAttribute("data-value"), 10);
      fetch("/api/runs/" + id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ self_rating: value })
      }).then(function () { loadHistory(); });
    });
  }

  function loadProfiles() {
    fetch("/api/profiles").then(function (r) { return r.json(); }).then(function (list) {
      state.profiles = list;
      var sel = $("profile");
      clear(sel);
      list.forEach(function (p) {
        var o = el("option", null, p.label);
        o.value = p.id;
        sel.appendChild(o);
      });
    });
  }

  function loadSamples() {
    fetch("/api/samples").then(function (r) { return r.json(); }).then(function (list) {
      state.samples = list;
      var box = $("sample-buttons");
      clear(box);
      list.forEach(function (s) {
        var b = el("button", null, s.label);
        b.addEventListener("click", function () {
          $("brief").value = s.brief;
          $("status").textContent = "Loaded " + s.label + " - press Analyze.";
          analyze();
        });
        box.appendChild(b);
      });
    });
  }

  /* ------------------------------------------------------------- analyze */
  function analyze() {
    var brief = $("brief").value.trim();
    if (!brief) {
      $("status").textContent = "Paste a brief first.";
      return;
    }
    $("analyze").disabled = true;
    $("status").textContent = "Working...";
    fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ brief: brief, profile: $("profile").value })
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (data.error) { $("status").textContent = data.error; return; }
      state.result = data;
      render(data);
      $("status").textContent = "Reviewed " + data.project.name + ".";
      $("save").disabled = false;
    }).catch(function (err) {
      $("status").textContent = "Failed: " + err;
    }).finally(function () {
      $("analyze").disabled = false;
    });
  }

  function saveRun() {
    fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ brief: $("brief").value, profile: $("profile").value })
    }).then(function (r) { return r.json(); }).then(function () {
      $("status").textContent = "Saved to the review log.";
      loadHistory();
    });
  }

  function exportAs(fmt) {
    fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ brief: $("brief").value, profile: $("profile").value, format: fmt })
    }).then(function (r) { return r.blob(); }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "reno-forge-report." + fmt;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  /* -------------------------------------------------------------- render */
  function render(data) {
    $("results").hidden = false;
    var s = data.score;

    $("score-value").textContent = s.overall.toFixed(1);
    $("score-ring").style.background =
      "conic-gradient(var(--accent) " + (s.overall * 3.6) + "deg, #1d2735 " + (s.overall * 3.6) + "deg)";
    $("verdict").textContent = s.verdict_label;
    $("project-line").textContent =
      data.project.name + " - " + data.project.type + " - " +
      (data.project.area_sqft ? num(data.project.area_sqft, 0) + " sqft" : "no area given") +
      (data.project.start_date ? " - start " + data.project.start_date : "");

    var counts = $("severity-counts");
    clear(counts);
    ["high", "medium", "low"].forEach(function (sev) {
      var c = el("span", "count " + sev, sev + ": " + s.severity_counts[sev]);
      counts.appendChild(c);
    });

    var axes = $("axes");
    clear(axes);
    Object.keys(s.axes).forEach(function (key) {
      var a = s.axes[key];
      var box = el("div", "axis");
      var top = el("div", "axis-top");
      top.appendChild(el("h4", null, a.label));
      top.appendChild(el("b", null, a.score.toFixed(0)));
      box.appendChild(top);
      box.appendChild(el("p", null, a.question));
      var bar = el("div", "bar");
      var fill = el("i");
      fill.style.width = Math.max(0, Math.min(100, a.score)) + "%";
      bar.appendChild(fill);
      box.appendChild(bar);
      axes.appendChild(box);
    });

    renderCost(data.cost);
    renderScheduleSummary(data.schedule);
    renderTakeoff(data.takeoff.rows);
    renderSchedule(data.schedule.tasks);
    renderTools(data.tools);
    renderFindings();
    renderFixPlan(data.fix_plan);
    renderAssumptions(data.assumptions);
  }

  function renderCost(cost) {
    var box = $("cost-breakdown");
    clear(box);
    function row(label, value, cls) {
      var r = el("div", "kv" + (cls ? " " + cls : ""));
      r.appendChild(el("span", null, label));
      r.appendChild(el("span", cls || null, value));
      box.appendChild(r);
    }
    row("Materials", money(cost.material_total));
    row("Waste allowance", money(cost.waste_total));
    row("Labor", cost.labor_known ? money(cost.labor) : "not stated");
    row("Contingency", cost.contingency_pct !== null
      ? (cost.contingency_pct * 100).toFixed(0) + "% = " + money(cost.contingency) : "not applied");
    row("Tax", cost.tax_pct !== null
      ? (cost.tax_pct * 100).toFixed(2) + "% = " + money(cost.tax) : "not applied");
    row("Estimate", money(cost.total), "total");
    if (cost.budget !== null && cost.budget !== undefined) {
      row("Budget", money(cost.budget));
      var over = cost.variance > 0;
      row(over ? "Over budget by" : "Under budget by",
        money(Math.abs(cost.variance || 0)), over ? "over" : "under");
    }
    if (!cost.complete) {
      row("Unpriced materials", String(cost.unpriced_count));
    }
  }

  function renderScheduleSummary(sch) {
    var box = $("schedule-summary");
    clear(box);
    function row(label, value) {
      var r = el("div", "kv");
      r.appendChild(el("span", null, label));
      r.appendChild(el("span", null, value));
      box.appendChild(r);
    }
    row("Hands-on time", num(sch.total_hours) + " h");
    row("Elapsed with cure time", num(sch.working_days) + " days");
    row("Steps", String(sch.tasks.length));
    if (sch.start_date) row("Start", sch.start_date);
    if (sch.finish_date) row("Finish", sch.finish_date);
    var cures = sch.tasks.filter(function (t) { return t.cure_after > 0; });
    if (cures.length) {
      row("Steps with a cure wait", String(cures.length));
    }
  }

  function renderTakeoff(rows) {
    var body = $("takeoff").querySelector("tbody");
    clear(body);
    rows.forEach(function (r) {
      var tr = el("tr");
      var name = el("td");
      name.appendChild(document.createTextNode(r.name));
      (r.flags || []).forEach(function (f) {
        if (f === "missing_quantity" || f === "missing_price" || f === "basis_mismatch" ||
            f === "unit_mismatch" || f === "duplicate_material") {
          name.appendChild(el("span", "flags", f.replace(/_/g, " ")));
        }
      });
      tr.appendChild(name);
      tr.appendChild(el("td", "num", r.need !== null && r.need !== undefined
        ? num(r.need) + " " + (r.need_unit || "") : "-"));
      tr.appendChild(el("td", "num", r.need_with_waste !== null && r.need_with_waste !== undefined
        ? num(r.need_with_waste) : "-"));
      tr.appendChild(el("td", "num", r.packs_to_buy !== null && r.packs_to_buy !== undefined
        ? r.packs_to_buy + " " + r.pack : "-"));
      tr.appendChild(el("td", "num", r.price !== null && r.price !== undefined
        ? money(r.price) + " / " + (r.basis || "?") : "-"));
      tr.appendChild(el("td", "num", r.cost !== null && r.cost !== undefined ? money(r.cost) : "-"));
      tr.appendChild(el("td", "src", r.need_source || "-"));
      body.appendChild(tr);
    });
  }

  function renderSchedule(tasks) {
    var body = $("schedule").querySelector("tbody");
    clear(body);
    tasks.forEach(function (t) {
      var tr = el("tr");
      tr.appendChild(el("td", "num", String(t.day)));
      tr.appendChild(el("td", null, t.name));
      tr.appendChild(el("td", "num", num(t.hours) + " h"));
      tr.appendChild(el("td", "num", t.cure_after > 0 ? t.cure_after + " h" : "-"));
      tr.appendChild(el("td", "src", (t.materials || []).join(", ") || "-"));
      tr.appendChild(el("td", "src", (t.tools || []).join(", ") || "-"));
      body.appendChild(tr);
    });
  }

  function renderTools(tools) {
    var have = $("tools-have");
    clear(have);
    if (!tools.have.length) {
      have.appendChild(el("span", "pill", "no tool list in the brief"));
    }
    tools.have.forEach(function (k) {
      have.appendChild(el("span", "pill have", k.replace(/_/g, " ")));
    });
    var miss = $("tools-missing");
    clear(miss);
    if (!tools.missing.length) {
      miss.appendChild(el("span", "pill", "nothing missing - you have what the plan needs"));
    }
    tools.missing.forEach(function (m) {
      var p = el("span", "pill need", m.name);
      p.appendChild(el("span", "alt", m.alternative));
      miss.appendChild(p);
    });
  }

  function renderFindings() {
    var box = $("findings");
    clear(box);
    if (!state.result) return;
    var list = state.result.findings.filter(function (f) {
      return state.filter === "all" || f.severity === state.filter;
    });
    if (!list.length) {
      box.appendChild(el("p", "hint", "Nothing at that severity."));
      return;
    }
    list.forEach(function (f) {
      var card = el("div", "finding " + f.severity);
      var head = el("header");
      head.appendChild(el("span", "sev " + f.severity, f.severity));
      head.appendChild(el("h5", null, f.title));
      head.appendChild(el("span", "axis-tag", f.axis));
      card.appendChild(head);
      card.appendChild(el("p", null, f.why));
      card.appendChild(el("p", "fix", "Fix: " + f.fix));
      card.appendChild(el("p", "evidence", "Evidence: " + f.evidence));
      box.appendChild(card);
    });
  }

  function renderFixPlan(plan) {
    var box = $("fix-plan");
    clear(box);
    plan.forEach(function (p) {
      var li = el("li");
      li.appendChild(document.createTextNode(p.title + " - " + p.fix));
      li.appendChild(el("span", "gain", "+" + p.gain + " pts"));
      box.appendChild(li);
    });
  }

  function renderAssumptions(list) {
    var box = $("assumptions");
    clear(box);
    list.forEach(function (a) { box.appendChild(el("li", null, a)); });
  }

  /* ------------------------------------------------------------- history */
  function loadHistory() {
    fetch("/api/runs").then(function (r) { return r.json(); }).then(function (rows) {
      var panel = $("history-panel");
      if (!rows.length) { panel.hidden = true; return; }
      panel.hidden = false;
      var body = $("history").querySelector("tbody");
      clear(body);
      rows.forEach(function (row) {
        var tr = el("tr");
        tr.appendChild(el("td", null, row.created_at.replace("T", " ").replace("+00:00", "Z")));
        tr.appendChild(el("td", null, row.project_name));
        tr.appendChild(el("td", null, row.profile));
        tr.appendChild(el("td", "num", row.score !== null ? Number(row.score).toFixed(1) : "-"));
        tr.appendChild(el("td", null, (row.verdict || "").replace(/_/g, " ")));
        tr.appendChild(el("td", "num", row.estimate !== null ? money(row.estimate) : "-"));
        var stars = el("td");
        for (var i = 1; i <= 5; i++) {
          var b = el("button", "star" + (row.self_rating >= i ? " on" : ""), "*");
          b.setAttribute("data-id", row.id);
          b.setAttribute("data-value", i);
          stars.appendChild(b);
        }
        tr.appendChild(stars);
        body.appendChild(tr);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    boot();
    loadHistory();
  });
})();
