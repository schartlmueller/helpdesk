(function () {
  "use strict";

  // --- Menü auf kleinen Bildschirmen ----------------------------------------
  var menuButton = document.querySelector(".menu-toggle");
  if (menuButton) {
    menuButton.addEventListener("click", function () {
      var open = document.body.classList.toggle("menu-open");
      menuButton.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // --- Artikelvorschläge beim Anlegen eines Tickets -------------------------
  var box = document.getElementById("kb-suggest");
  var titleInput = document.getElementById("id_title");
  if (box && titleInput) {
    var results = document.getElementById("kb-suggest-results");
    var hint = document.getElementById("kb-suggest-hint");
    var timer = null;

    var render = function (items) {
      results.textContent = "";
      if (!items.length) {
        hint.textContent = "Kein passender Artikel gefunden. Lege einfach das Ticket an.";
        return;
      }
      hint.textContent = "Diese Artikel könnten dein Problem bereits lösen:";
      items.forEach(function (item) {
        var link = document.createElement("a");
        link.className = "row-link";
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = item.title;
        results.appendChild(link);
      });
    };

    titleInput.addEventListener("input", function () {
      clearTimeout(timer);
      var query = titleInput.value.trim();
      if (query.length < 4) {
        return;
      }
      timer = setTimeout(function () {
        fetch(box.dataset.url + "?q=" + encodeURIComponent(query), {
          credentials: "same-origin",
        })
          .then(function (r) { return r.json(); })
          .then(function (data) { render(data.results || []); })
          .catch(function () {});
      }, 350);
    });
  }

  // --- Lösung aus einem Wissensartikel in das Lösungsfeld übernehmen --------
  document.querySelectorAll(".js-adopt").forEach(function (button) {
    button.addEventListener("click", function () {
      var field = document.getElementById("id_solution");
      var checkbox = document.getElementById("id_create_article");
      if (field) {
        field.value = button.dataset.solution;
        field.focus();
      }
      // Die Lösung steht schon in der Wissensbasis, also kein zweiter Artikel.
      if (checkbox) {
        checkbox.checked = false;
      }
    });
  });

  // --- Textbaustein in das Antwortfeld einfügen -----------------------------
  var canned = document.querySelector(".js-canned");
  if (canned) {
    canned.addEventListener("change", function () {
      var field = document.getElementById("id_body");
      if (field && canned.value) {
        field.value = field.value ? field.value + "\n\n" + canned.value : canned.value;
        field.focus();
      }
      canned.selectedIndex = 0;
    });
  }

  // --- Laufende Zeiterfassung anzeigen --------------------------------------
  var timerEl = document.getElementById("timer");
  if (timerEl && timerEl.dataset.running === "1") {
    var base = parseInt(timerEl.dataset.seconds, 10) || 0;
    var loadedAt = Date.now();
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    var tick = function () {
      var total = base + Math.floor((Date.now() - loadedAt) / 1000);
      timerEl.textContent =
        Math.floor(total / 3600) + ":" + pad(Math.floor((total % 3600) / 60)) +
        ":" + pad(total % 60);
    };
    tick();
    setInterval(tick, 1000);
  }

  // --- Wochenpool: alle Kandidaten auf einmal an- oder abwählen --------------
  var checkAll = document.querySelector(".js-check-all");
  if (checkAll) {
    checkAll.addEventListener("change", function () {
      var table = checkAll.closest("table");
      table.querySelectorAll('input[name="tickets"]').forEach(function (box) {
        box.checked = checkAll.checked;
      });
    });
  }

  // --- Diagramme: Fadenkreuz und Hinweisfenster ------------------------------
  document.querySelectorAll(".viz-wrap").forEach(function (wrap) {
    var svg = wrap.querySelector("svg.viz");
    var tip = wrap.querySelector(".viz-tip");
    if (!svg || !tip) { return; }
    var cross = svg.querySelector(".viz-cross");
    var width = svg.viewBox.baseVal.width;
    var show = function (hit) {
      var x = parseFloat(hit.dataset.x);
      cross.setAttribute("x1", x);
      cross.setAttribute("x2", x);
      cross.style.visibility = "visible";
      tip.textContent = hit.dataset.tip;
      tip.hidden = false;
      // Am Rand nicht aus dem Diagramm ragen
      var percent = Math.min(88, Math.max(12, (x / width) * 100));
      tip.style.left = percent + "%";
    };
    var hide = function () {
      cross.style.visibility = "hidden";
      tip.hidden = true;
    };
    svg.querySelectorAll(".viz-hit").forEach(function (hit) {
      hit.addEventListener("mouseenter", function () { show(hit); });
      hit.addEventListener("click", function () { show(hit); });  // Antippen am Handy
    });
    svg.addEventListener("mouseleave", hide);
  });

  // --- Karten verschieben: mit der Maus ziehen oder antippen ----------------
  // Ziehen funktioniert nur mit der Maus. Für Handy und Tablet hat jede Karte
  // einen Knopf: Karte damit auswählen, dann das Ziel antippen.
  var postJson = function (url, csrf, payload) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(payload),
    });
  };

  var setupMovable = function (root, cardSelector, targetSelector, hooks) {
    var active = null;   // gerade gezogene Karte
    var picked = null;   // per Knopf ausgewählte Karte

    var unpick = function () {
      if (picked) { picked.classList.remove("picked"); }
      picked = null;
      root.classList.remove("placing");
    };

    root.querySelectorAll(cardSelector).forEach(function (card) {
      card.addEventListener("dragstart", function (event) {
        unpick();
        active = card;
        card.classList.add("dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", card.dataset.id);
      });
      card.addEventListener("dragend", function () {
        card.classList.remove("dragging");
        active = null;
        root.querySelectorAll(".drop-hover").forEach(function (el) {
          el.classList.remove("drop-hover");
        });
      });
      var button = card.querySelector(".move-btn");
      if (button) {
        button.addEventListener("click", function (event) {
          event.preventDefault();
          event.stopPropagation();
          if (picked === card) { unpick(); return; }
          unpick();
          picked = card;
          card.classList.add("picked");
          root.classList.add("placing");
        });
      }
    });

    root.querySelectorAll(targetSelector).forEach(function (target) {
      target.addEventListener("dragover", function (event) {
        if (!active) { return; }
        event.preventDefault();
        target.classList.add("drop-hover");
        if (hooks.over) { hooks.over(active, target, event); }
      });
      target.addEventListener("dragleave", function () {
        target.classList.remove("drop-hover");
      });
      target.addEventListener("drop", function (event) {
        if (!active) { return; }
        event.preventDefault();
        hooks.place(active, target, true);
      });
      target.addEventListener("click", function (event) {
        if (!picked || event.target.closest(".move-btn")) { return; }
        // Im Auswahlmodus öffnet ein Antippen keine Karte, sondern legt ab.
        event.preventDefault();
        var card = picked;
        unpick();
        hooks.place(card, target, false);
      });
    });
  };

  // Kanban-Board der Projekte
  var board = document.querySelector(".board");
  if (board) {
    var cardBelow = function (column, y) {
      var cards = column.querySelectorAll(".card-task:not(.dragging)");
      for (var i = 0; i < cards.length; i++) {
        var rect = cards[i].getBoundingClientRect();
        if (y < rect.top + rect.height / 2) { return cards[i]; }
      }
      return null;
    };
    setupMovable(board, ".card-task", ".column-body", {
      over: function (card, column, event) {
        var below = cardBelow(column, event.clientY);
        if (below) { column.insertBefore(card, below); } else { column.appendChild(card); }
      },
      place: function (card, column, dragged) {
        if (!dragged) { column.appendChild(card); }
        board.querySelectorAll(".column").forEach(function (col) {
          col.querySelector(".js-count").textContent =
            col.querySelectorAll(".card-task").length;
        });
        var ids = [];
        column.querySelectorAll(".card-task").forEach(function (c) { ids.push(c.dataset.id); });
        postJson(board.dataset.url, board.dataset.csrf, {
          status: column.dataset.status,
          ids: ids,
        })
          .then(function (r) { if (!r.ok) { window.location.reload(); } })
          .catch(function () { window.location.reload(); });
      },
    });
  }

  // Wochenplanung
  var planner = document.querySelector(".planner");
  if (planner) {
    setupMovable(planner, ".plan-card", ".plan-drop", {
      place: function (card, target) {
        if (card.parentNode === target) { return; }
        target.appendChild(card);
        var reload = function () { window.location.reload(); };
        postJson(planner.dataset.url, planner.dataset.csrf, {
          kind: card.dataset.kind,
          id: card.dataset.id,
          date: target.dataset.date || null,
          user: target.dataset.user || null,
          keep_user: target.dataset.keep === "1",
          pool: target.dataset.pool || null,
          unpool: target.dataset.unpool === "1",
        }).then(reload).catch(reload);  // neu laden, damit die Summen stimmen
      },
    });
  }
})();
