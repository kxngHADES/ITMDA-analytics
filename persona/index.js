(function () {
  "use strict";

  var RAW = window.PERSONA_DATA || [];

  var allEntries = RAW.map(function (e) {
    return Object.assign({}, e, { key: e.persona_id + "::" + e.scenario_id });
  });

  var CATEGORY_LABEL = { P: "Patients", S: "Staff & System Actors" };

  function categoryFor(personaId) {
    return CATEGORY_LABEL[personaId.charAt(0)] || "Other";
  }

  // ---------- markdown rendering ----------

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function inline(s) {
    s = escapeHtml(s);
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/__(.+?)__/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, "$1<em>$2</em>");
    s = s.replace(/(^|[^\w])_([^_]+?)_(?=[^\w]|$)/g, "$1<em>$2</em>");
    s = s.replace(/`(.+?)`/g, "<code>$1</code>");
    return s;
  }

  function isTableSeparator(line) {
    return /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/.test(line.trim());
  }

  function renderMarkdown(text) {
    var lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
    var html = "";
    var i = 0;
    var buf = [];

    function flush() {
      if (buf.length) {
        html += "<p>" + inline(buf.join(" ")) + "</p>";
        buf = [];
      }
    }

    while (i < lines.length) {
      var raw = lines[i];
      var line = raw.trim();

      if (line === "") { flush(); i++; continue; }

      var h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        flush();
        var tag = h[1].length <= 2 ? "h3" : "h4";
        html += "<" + tag + ">" + inline(h[2]) + "</" + tag + ">";
        i++; continue;
      }

      if (/^\|.*\|$/.test(line) && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
        flush();
        var head = line.slice(1, -1).split("|").map(function (c) { return c.trim(); });
        i += 2;
        var rows = [];
        while (i < lines.length && /^\|.*\|$/.test(lines[i].trim())) {
          rows.push(lines[i].trim().slice(1, -1).split("|").map(function (c) { return c.trim(); }));
          i++;
        }
        html += "<table><thead><tr>" + head.map(function (c) { return "<th>" + inline(c) + "</th>"; }).join("") + "</tr></thead><tbody>";
        rows.forEach(function (r) {
          html += "<tr>" + r.map(function (c) { return "<td>" + inline(c) + "</td>"; }).join("") + "</tr>";
        });
        html += "</tbody></table>";
        continue;
      }

      if (/^[-*+]\s+/.test(line)) {
        flush();
        html += "<ul>";
        while (i < lines.length && /^[-*+]\s+/.test(lines[i].trim())) {
          html += "<li>" + inline(lines[i].trim().replace(/^[-*+]\s+/, "")) + "</li>";
          i++;
        }
        html += "</ul>";
        continue;
      }

      if (/^\d+[.)]\s+/.test(line)) {
        flush();
        html += "<ol>";
        while (i < lines.length && /^\d+[.)]\s+/.test(lines[i].trim())) {
          html += "<li>" + inline(lines[i].trim().replace(/^\d+[.)]\s+/, "")) + "</li>";
          i++;
        }
        html += "</ol>";
        continue;
      }

      if (/^>\s?/.test(line)) {
        flush();
        var quote = [];
        while (i < lines.length && /^>\s?/.test(lines[i].trim())) {
          quote.push(lines[i].trim().replace(/^>\s?/, ""));
          i++;
        }
        html += "<blockquote>" + inline(quote.join(" ")) + "</blockquote>";
        continue;
      }

      if (/^(-{3,}|_{3,}|\*{3,})$/.test(line)) {
        flush();
        html += "<hr />";
        i++; continue;
      }

      buf.push(line);
      i++;
    }
    flush();
    return html;
  }

  // ---------- search / highlight ----------

  function matches(entry, query) {
    if (!query) return true;
    var q = query.toLowerCase();
    return (
      (entry.persona_label || "").toLowerCase().indexOf(q) !== -1 ||
      (entry.scenario_label || "").toLowerCase().indexOf(q) !== -1 ||
      (entry.response_text || "").toLowerCase().indexOf(q) !== -1
    );
  }

  function highlight(container, query) {
    if (!query) return;
    var q = query.toLowerCase();
    var walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
    var nodes = [];
    var n;
    while ((n = walker.nextNode())) nodes.push(n);
    nodes.forEach(function (node) {
      var text = node.nodeValue;
      var lower = text.toLowerCase();
      var idx = lower.indexOf(q);
      if (idx === -1) return;
      var frag = document.createDocumentFragment();
      var cursor = 0;
      while (idx !== -1) {
        frag.appendChild(document.createTextNode(text.slice(cursor, idx)));
        var mark = document.createElement("mark");
        mark.textContent = text.slice(idx, idx + q.length);
        frag.appendChild(mark);
        cursor = idx + q.length;
        idx = lower.indexOf(q, cursor);
      }
      frag.appendChild(document.createTextNode(text.slice(cursor)));
      node.parentNode.replaceChild(frag, node);
    });
  }

  // ---------- state ----------

  var currentQuery = "";
  var currentKey = null;
  var openPersonas = {};

  // ---------- DOM refs ----------

  var tocInner = document.getElementById("tocInner");
  var toc = document.getElementById("toc");
  var tocToggle = document.getElementById("tocToggle");
  var pageEl = document.getElementById("page");
  var pageWrap = document.querySelector(".page-wrap");
  var searchInput = document.getElementById("searchInput");
  var searchCount = document.getElementById("searchCount");
  var prevBtn = document.getElementById("prevBtn");
  var nextBtn = document.getElementById("nextBtn");
  var progressFill = document.getElementById("progressFill");
  var progressLabel = document.getElementById("progressLabel");

  // ---------- persona grouping (preserve data order) ----------

  var personas = [];
  var personaIndex = {};
  allEntries.forEach(function (e) {
    if (!(e.persona_id in personaIndex)) {
      personaIndex[e.persona_id] = personas.length;
      personas.push({ id: e.persona_id, label: e.persona_label, category: categoryFor(e.persona_id), scenarios: [] });
    }
    personas[personaIndex[e.persona_id]].scenarios.push(e);
  });

  var categories = [];
  personas.forEach(function (p) {
    if (categories.indexOf(p.category) === -1) categories.push(p.category);
  });

  // ---------- TOC ----------

  function buildToc() {
    tocInner.innerHTML = "";
    var visibleCount = 0;

    categories.forEach(function (cat) {
      var catPersonas = personas.filter(function (p) { return p.category === cat; });
      var catHasMatch = false;

      var groupEl = document.createElement("div");
      groupEl.className = "toc-group";

      var labelEl = document.createElement("div");
      labelEl.className = "toc-group-label";
      labelEl.textContent = cat;
      groupEl.appendChild(labelEl);

      catPersonas.forEach(function (p) {
        var matchedScenarios = p.scenarios.filter(function (e) { return matches(e, currentQuery); });
        var personaMatches = matchedScenarios.length > 0;
        if (personaMatches) catHasMatch = true;

        var pEl = document.createElement("div");
        pEl.className = "toc-persona" + (personaMatches ? "" : " toc-hidden");
        var isOpen = currentQuery ? personaMatches : !!openPersonas[p.id];
        if (isOpen) pEl.classList.add("open");

        var btn = document.createElement("button");
        btn.className = "toc-persona-btn";
        btn.innerHTML =
          '<span class="toc-persona-name">' + escapeHtml(p.label) + "</span>" +
          '<span class="toc-persona-caret">&#9656;</span>';
        btn.addEventListener("click", function () {
          openPersonas[p.id] = !openPersonas[p.id];
          pEl.classList.toggle("open");
        });
        pEl.appendChild(btn);

        var scEl = document.createElement("div");
        scEl.className = "toc-scenarios";
        p.scenarios.forEach(function (e) {
          var visible = matches(e, currentQuery);
          if (visible) visibleCount++;
          var sBtn = document.createElement("button");
          sBtn.className = "toc-scenario-btn" + (visible ? "" : " toc-hidden") + (e.key === currentKey ? " active" : "");
          sBtn.textContent = e.scenario_label + (e.response_text ? "" : " (unavailable)");
          sBtn.dataset.key = e.key;
          sBtn.addEventListener("click", function () { selectEntry(e.key); });
          scEl.appendChild(sBtn);
        });
        pEl.appendChild(scEl);

        groupEl.appendChild(pEl);
      });

      if (catHasMatch) tocInner.appendChild(groupEl);
    });

    if (visibleCount === 0) {
      var empty = document.createElement("div");
      empty.className = "toc-empty";
      empty.textContent = "No entries match “" + currentQuery + "”.";
      tocInner.appendChild(empty);
    }

    searchCount.textContent = currentQuery ? visibleCount + " of " + allEntries.length + " match" : "";
  }

  // ---------- filtered navigation ----------

  function filteredEntries() {
    return allEntries.filter(function (e) { return matches(e, currentQuery); });
  }

  function updateNav() {
    var filtered = filteredEntries();
    var pos = filtered.findIndex(function (e) { return e.key === currentKey; });
    prevBtn.disabled = filtered.length === 0 || pos <= 0;
    nextBtn.disabled = filtered.length === 0 || pos === -1 || pos >= filtered.length - 1;

    var globalIdx = allEntries.findIndex(function (e) { return e.key === currentKey; });
    if (globalIdx !== -1) {
      progressFill.style.width = ((globalIdx + 1) / allEntries.length) * 100 + "%";
      var label = "Entry " + (globalIdx + 1) + " of " + allEntries.length;
      if (currentQuery) label += " · " + filtered.length + " matching";
      progressLabel.textContent = label;
    } else {
      progressFill.style.width = "0%";
      progressLabel.textContent = "";
    }
  }

  function goPrevNext(dir) {
    var filtered = filteredEntries();
    if (!filtered.length) return;
    var pos = filtered.findIndex(function (e) { return e.key === currentKey; });
    if (pos === -1) { selectEntry(filtered[0].key); return; }
    var next = pos + dir;
    if (next < 0 || next >= filtered.length) return;
    selectEntry(filtered[next].key);
  }

  // ---------- page rendering ----------

  function renderPage(entry) {
    if (!entry) {
      pageEl.innerHTML = '<div class="page-empty">No entries match your search.<br>Try a different word or clear the search box.</div>';
      updateNav();
      return;
    }
    var globalIdx = allEntries.findIndex(function (e) { return e.key === entry.key; });
    var date;
    try {
      date = new Date(entry.timestamp_utc).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
    } catch (err) {
      date = entry.timestamp_utc;
    }

    pageEl.innerHTML =
      '<div class="page-kicker">Chapter ' + (globalIdx + 1) + " · " + escapeHtml(entry.persona_id) + "</div>" +
      '<h2 class="page-title">' + escapeHtml(entry.scenario_label) + "</h2>" +
      '<p class="page-subtitle">as experienced by ' + escapeHtml(entry.persona_label) + "</p>" +
      '<div class="page-meta">' +
        "<span><b>Model</b> " + escapeHtml(entry.model) + "</span>" +
        "<span><b>Recorded</b> " + escapeHtml(date) + "</span>" +
      "</div>" +
      '<div class="page-body">' +
        (entry.response_text
          ? renderMarkdown(entry.response_text)
          : '<p class="page-missing">This entry has no recorded response — the model run for it ended in an error when the transcript was generated.</p>') +
      "</div>";

    if (currentQuery && entry.response_text) highlight(pageEl.querySelector(".page-body"), currentQuery);
    pageWrap.scrollTop = 0;
  }

  function selectEntry(key, opts) {
    var entry = allEntries.find(function (e) { return e.key === key; });
    if (!entry) return;
    currentKey = key;
    openPersonas[entry.persona_id] = true;
    renderPage(entry);
    buildToc();
    updateNav();
    if (!(opts && opts.skipHash)) {
      history.replaceState(null, "", "#" + encodeURIComponent(entry.persona_id) + "/" + encodeURIComponent(entry.scenario_id));
    }
    if (window.innerWidth <= 860) toc.classList.remove("open");
  }

  // ---------- search wiring ----------

  searchInput.addEventListener("input", function () {
    currentQuery = searchInput.value.trim();
    buildToc();
    updateNav();
    var filtered = filteredEntries();
    var stillVisible = filtered.some(function (e) { return e.key === currentKey; });
    if (!stillVisible) {
      if (filtered.length) {
        selectEntry(filtered[0].key);
      } else {
        pageEl.innerHTML = '<div class="page-empty">No entries match “' + escapeHtml(currentQuery) + '”.<br>Try a different word or clear the search box.</div>';
        updateNav();
      }
    } else {
      renderPage(allEntries.find(function (e) { return e.key === currentKey; }));
    }
  });

  // ---------- nav wiring ----------

  prevBtn.addEventListener("click", function () { goPrevNext(-1); });
  nextBtn.addEventListener("click", function () { goPrevNext(1); });

  document.addEventListener("keydown", function (ev) {
    var tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA") {
      if (ev.key === "Escape") { searchInput.blur(); }
      return;
    }
    if (ev.key === "ArrowLeft") goPrevNext(-1);
    else if (ev.key === "ArrowRight") goPrevNext(1);
    else if (ev.key === "/") { ev.preventDefault(); searchInput.focus(); }
  });

  // ---------- theme wiring ----------

  var themeButtons = document.querySelectorAll(".theme-btn");
  function setTheme(name) {
    document.body.setAttribute("data-theme", name);
    themeButtons.forEach(function (b) { b.classList.toggle("active", b.dataset.themeChoice === name); });
    try { localStorage.setItem("fieldnotes-theme", name); } catch (e) {}
  }
  themeButtons.forEach(function (b) {
    b.addEventListener("click", function () { setTheme(b.dataset.themeChoice); });
  });
  var savedTheme = null;
  try { savedTheme = localStorage.getItem("fieldnotes-theme"); } catch (e) {}
  setTheme(savedTheme || "paper");

  // ---------- toc toggle (mobile) ----------

  tocToggle.addEventListener("click", function () { toc.classList.toggle("open"); });

  // ---------- hash routing ----------

  function entryFromHash() {
    var h = location.hash.replace(/^#/, "");
    if (!h) return null;
    var parts = h.split("/");
    if (parts.length !== 2) return null;
    var pid = decodeURIComponent(parts[0]);
    var sid = decodeURIComponent(parts[1]);
    return allEntries.find(function (e) { return e.persona_id === pid && e.scenario_id === sid; }) || null;
  }

  window.addEventListener("hashchange", function () {
    var e = entryFromHash();
    if (e) selectEntry(e.key, { skipHash: true });
  });

  // ---------- init ----------

  var initial = entryFromHash() || allEntries[0];
  if (initial) {
    openPersonas[initial.persona_id] = true;
    currentKey = initial.key;
    buildToc();
    renderPage(initial);
    updateNav();
  } else {
    buildToc();
    renderPage(null);
  }
})();
