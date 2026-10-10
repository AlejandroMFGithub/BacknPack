/* BacknPack: comportamiento de la interfaz (menús, listas y buscadores). */
(function () {
  "use strict";

  /** Minúsculas y sin tildes, igual que app/text.py. */
  function norm(text) {
    return (text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function submitForm(form) {
    if (form.requestSubmit) form.requestSubmit(); else form.submit();
  }

  // --- Menú hamburguesa y desplegables «⋯» --------------------------------------------

  function setNav(open) {
    var toggle = document.querySelector(".menu-toggle");
    document.body.classList.toggle("nav-open", open);
    if (toggle) {
      toggle.setAttribute("aria-expanded", open);
      toggle.setAttribute("aria-label", open ? "Cerrar menú" : "Abrir menú");
    }
  }

  document.addEventListener("click", function (e) {
    if (e.target.closest(".menu-toggle")) {
      setNav(!document.body.classList.contains("nav-open"));
      return;
    }
    document.querySelectorAll("details.menu[open]").forEach(function (menu) {
      if (!menu.contains(e.target)) menu.removeAttribute("open");
    });
  });

  // Solo un desplegable abierto a la vez
  document.addEventListener("toggle", function (e) {
    if (!e.target.matches || !e.target.matches("details.menu") || !e.target.open) return;
    document.querySelectorAll("details.menu[open]").forEach(function (menu) {
      if (menu !== e.target) menu.removeAttribute("open");
    });
  }, true);

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    setNav(false);
    document.querySelectorAll("details.menu[open]").forEach(function (m) { m.removeAttribute("open"); });
  });

  // --- Listas: los desplegables de filtro/orden se aplican al cambiarlos ----------------

  document.addEventListener("change", function (e) {
    if (e.target.matches("select[data-autosubmit]")) submitForm(e.target.form);
  });

  // URLs limpias: los campos vacíos de una búsqueda no se envían (?q=&category= …)
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form.method !== "get" || e.defaultPrevented) return;
    Array.prototype.forEach.call(form.elements, function (field) {
      if (field.name && field.value === "") field.disabled = true;
    });
  });
  // Al volver con «Atrás», el formulario debe estar usable de nuevo
  window.addEventListener("pageshow", function () {
    document.querySelectorAll("form[method=get] [disabled]").forEach(function (f) { f.disabled = false; });
  });

  // --- Filtro rápido de filas en la página (sin recargar) ------------------------------
  // <input data-quick-filter="#lista">  filtra los elementos [data-filter-text] de #lista

  document.addEventListener("input", function (e) {
    var input = e.target;
    if (!input.matches("[data-quick-filter]")) return;
    var scope = document.querySelector(input.getAttribute("data-quick-filter"));
    if (!scope) return;
    var needle = norm(input.value);
    scope.querySelectorAll("[data-filter-text]").forEach(function (row) {
      row.hidden = !!needle && norm(row.getAttribute("data-filter-text")).indexOf(needle) === -1;
    });
  });

  // --- Buscador desplegable -------------------------------------------------------------
  // Pide resultados al servidor mientras se escribe (de 20 en 20) y guarda el id elegido
  // en el campo oculto. Ver la macro picker() en views/_macros.html.

  var pickerCount = 0;

  function Picker(root) {
    var self = this;
    this.root = root;
    this.source = root.getAttribute("data-source");
    this.params = JSON.parse(root.getAttribute("data-params") || "{}");
    this.hidden = root.querySelector("input[type=hidden]");
    this.input = root.querySelector(".picker-input");
    this.form = root.closest("form");
    this.items = [];
    this.page = 1;
    this.hasMore = false;
    this.active = -1;
    this.request = 0;
    this.timer = null;
    this.filterSelects = [];
    var id = "picker-" + (++pickerCount);

    var control = el("div", "picker-control");
    root.insertBefore(control, this.input);
    control.appendChild(this.input);

    var filters = JSON.parse(root.getAttribute("data-filters") || "[]");
    if (filters.length) {
      var toggle = el("button", "picker-filter-btn btn-small btn-ghost", "Filtros");
      toggle.type = "button";
      toggle.setAttribute("aria-expanded", "false");
      control.appendChild(toggle);
      var box = el("div", "picker-filters");
      box.hidden = true;
      filters.forEach(function (f) {
        var label = el("label", "", f.label + " ");
        var select = el("select");
        select.setAttribute("data-key", f.name);  // sin name: no se envía con el formulario
        select.appendChild(new Option("Cualquiera", ""));
        f.options.forEach(function (opt) {
          var pair = Array.isArray(opt) ? opt : [opt, opt];
          select.appendChild(new Option(pair[1], pair[0]));
        });
        select.addEventListener("change", function () {
          var count = self.filterSelects.filter(function (s) { return s.value; }).length;
          toggle.textContent = count ? "Filtros (" + count + ")" : "Filtros";
          self.search(true);
          self.input.focus();
        });
        self.filterSelects.push(select);
        label.appendChild(select);
        box.appendChild(label);
      });
      toggle.addEventListener("click", function () {
        box.hidden = !box.hidden;
        toggle.setAttribute("aria-expanded", String(!box.hidden));
      });
      root.appendChild(box);
    }

    this.list = el("ul", "picker-list");
    this.list.id = id + "-list";
    this.list.setAttribute("role", "listbox");
    this.list.hidden = true;
    root.appendChild(this.list);
    this.error = el("div", "picker-error");
    this.error.hidden = true;
    root.appendChild(this.error);

    this.input.setAttribute("role", "combobox");
    this.input.setAttribute("aria-autocomplete", "list");
    this.input.setAttribute("aria-controls", this.list.id);
    this.input.setAttribute("aria-expanded", "false");
    if (this.hidden.value) root.classList.add("has-value");

    this.input.addEventListener("input", function () {
      self.clearValue();
      clearTimeout(self.timer);
      self.timer = setTimeout(function () { self.search(true); }, 220);
    });
    this.input.addEventListener("focus", function () {
      if (!self.hidden.value) self.search(true);
    });
    this.input.addEventListener("keydown", function (e) { self.onKey(e); });
    // mousedown en vez de click: elige antes de que el campo pierda el foco
    this.list.addEventListener("mousedown", function (e) {
      var li = e.target.closest("li");
      if (!li) return;
      e.preventDefault();
      if (li.classList.contains("picker-more")) { self.more(); return; }
      var index = Number(li.getAttribute("data-index"));
      if (!isNaN(index)) self.choose(self.items[index]);
    });
    document.addEventListener("click", function (e) {
      if (!root.contains(e.target)) self.close();
    });
    if (this.form && root.hasAttribute("data-required")) {
      this.form.addEventListener("submit", function (e) {
        if (self.hidden.value) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        self.showError("Elige una opción de la lista.");
        self.input.focus();
      });
    }
  }

  Picker.prototype.url = function () {
    var query = new URLSearchParams();
    query.set("q", this.input.value.trim());
    query.set("page", this.page);
    Object.keys(this.params).forEach(function (k) { query.set(k, this.params[k]); }, this);
    this.filterSelects.forEach(function (s) { if (s.value) query.set(s.getAttribute("data-key"), s.value); });
    return this.source + "?" + query.toString();
  };

  Picker.prototype.search = function (reset) {
    var self = this;
    if (reset) { this.page = 1; this.items = []; this.active = -1; }
    var ticket = ++this.request;  // descarta respuestas que lleguen tarde
    this.root.classList.add("loading");
    fetch(this.url(), { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) {
        if (ticket !== self.request) return;
        self.items = self.items.concat(data.results);
        self.hasMore = data.has_more;
        self.total = data.total;
        self.render();
      })
      .catch(function () {
        if (ticket === self.request) self.showError("No se pudo buscar. ¿Sigue abierta la sesión?");
      })
      .then(function () { if (ticket === self.request) self.root.classList.remove("loading"); });
  };

  Picker.prototype.more = function () {
    this.page += 1;
    this.search(false);
  };

  Picker.prototype.render = function () {
    var self = this;
    this.list.textContent = "";
    if (!this.items.length) {
      this.list.appendChild(el("li", "picker-empty", "Sin resultados"));
    }
    this.items.forEach(function (item, i) {
      var li = el("li", "picker-option" + (i === self.active ? " active" : ""));
      li.id = self.list.id + "-" + i;
      li.setAttribute("role", "option");
      li.setAttribute("data-index", i);
      li.appendChild(el("span", "picker-label", item.label));
      if (item.sub) li.appendChild(el("span", "picker-sub", item.sub));
      self.list.appendChild(li);
    });
    if (this.hasMore) {
      var more = el("li", "picker-more", "Cargar más… (" + this.items.length + " de " + this.total + ")");
      this.list.appendChild(more);
    }
    this.open();
  };

  Picker.prototype.open = function () {
    this.list.hidden = false;
    this.input.setAttribute("aria-expanded", "true");
    this.error.hidden = true;
  };

  Picker.prototype.close = function () {
    this.list.hidden = true;
    this.input.setAttribute("aria-expanded", "false");
    this.input.removeAttribute("aria-activedescendant");
  };

  Picker.prototype.highlight = function (index) {
    if (!this.items.length) return;
    this.active = (index + this.items.length) % this.items.length;
    var current = this.list.querySelector(".active");
    if (current) current.classList.remove("active");
    var li = this.list.querySelector('[data-index="' + this.active + '"]');
    if (li) {
      li.classList.add("active");
      li.scrollIntoView({ block: "nearest" });
      this.input.setAttribute("aria-activedescendant", li.id);
    }
  };

  Picker.prototype.onKey = function (e) {
    var openList = !this.list.hidden;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!openList) this.search(true); else this.highlight(this.active + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (openList) this.highlight(this.active - 1);
    } else if (e.key === "Enter") {
      if (openList && this.active >= 0) {
        e.preventDefault();
        this.choose(this.items[this.active]);
      } else if (!this.hidden.value) {
        e.preventDefault();  // Enter mientras se busca no envía el formulario
        if (this.items.length === 1) this.choose(this.items[0]);
      }
    } else if (e.key === "Escape" && openList) {
      e.stopPropagation();
      this.close();
    }
  };

  Picker.prototype.choose = function (item) {
    if (!item) return;
    this.hidden.value = item.id;
    this.input.value = item.label;
    this.root.classList.add("has-value");
    this.root.classList.remove("invalid");
    this.error.hidden = true;
    this.close();
    this.hidden.dispatchEvent(new Event("change", { bubbles: true }));
    if (this.root.hasAttribute("data-submit") && this.form) submitForm(this.form);
  };

  Picker.prototype.clearValue = function () {
    if (!this.hidden.value) return;
    this.hidden.value = "";
    this.root.classList.remove("has-value");
  };

  Picker.prototype.showError = function (message) {
    this.close();
    this.error.textContent = message;
    this.error.hidden = false;
    this.root.classList.add("invalid");
  };

  document.querySelectorAll(".picker").forEach(function (root) { new Picker(root); });
})();
