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

  /** Texto con las palabras buscadas marcadas (<mark>), ignorando tildes y mayúsculas. */
  function highlight(text, query) {
    var span = el("span", "picker-label");
    var words = norm(query).split(/\s+/).filter(Boolean);
    // Normaliza letra a letra para que las posiciones coincidan con el texto original
    var folded = Array.prototype.map.call(text, function (ch) { return norm(ch) || ch; });
    if (!words.length || folded.some(function (c) { return c.length !== 1; })) {
      span.textContent = text;
      return span;
    }
    var haystack = folded.join("");
    var marked = text.split("").map(function () { return false; });
    words.forEach(function (word) {
      for (var i = haystack.indexOf(word); i !== -1; i = haystack.indexOf(word, i + word.length)) {
        for (var k = i; k < i + word.length; k++) marked[k] = true;
      }
    });
    for (var start = 0; start < text.length;) {
      var end = start;
      while (end < text.length && marked[end] === marked[start]) end++;
      var chunk = text.slice(start, end);
      span.appendChild(marked[start] ? el("mark", "", chunk) : document.createTextNode(chunk));
      start = end;
    }
    return span;
  }

  /** Icono de personaje (igual que la macro avatar() de las plantillas). */
  function avatarIcon(info) {
    var span = el("span", "avatar avatar-sm");
    span.style.setProperty("--avatar-bg", info.color);
    span.setAttribute("aria-hidden", "true");
    if (info.url) {
      var img = el("img");
      img.src = info.url;
      img.alt = "";
      img.loading = "lazy";
      span.appendChild(img);
    } else {
      span.textContent = info.initial;
    }
    return span;
  }

  var FUNNEL_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linejoin="round" aria-hidden="true"><path d="M4 5h16l-6 7.5V19l-4-2v-4.5z"/></svg>';

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
    document.querySelectorAll("details.menu[open], details.popover[open]").forEach(function (menu) {
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
    document.querySelectorAll("details.menu[open], details.popover[open]").forEach(function (m) { m.removeAttribute("open"); });
  });

  // --- Pantallas de acceso ----------------------------------------------------------------

  // Mostrar / ocultar la contraseña
  document.addEventListener("click", function (e) {
    var button = e.target.closest(".toggle-password");
    if (!button) return;
    var input = button.parentElement.querySelector("input");
    var show = input.type === "password";
    input.type = show ? "text" : "password";
    button.textContent = show ? "Ocultar" : "Mostrar";
    button.setAttribute("aria-pressed", String(show));
    button.setAttribute("aria-label", show ? "Ocultar contraseña" : "Mostrar contraseña");
    input.focus();
  });

  // Aviso de Bloq Mayús al escribir la contraseña
  ["keydown", "keyup"].forEach(function (type) {
    document.addEventListener(type, function (e) {
      if (!e.target.matches || !e.target.matches(".password-field input") || !e.getModifierState) return;
      var warning = e.target.closest("form").querySelector(".caps-warning");
      if (warning) warning.hidden = !e.getModifierState("CapsLock");
    });
  });

  // Al entrar, el d20 rueda
  document.addEventListener("submit", function (e) {
    if (!e.target.matches(".auth-form") || e.defaultPrevented) return;
    var die = document.querySelector(".auth-d20");
    if (die) die.classList.add("rolling");
  });

  // --- Avisos de intercambios --------------------------------------------------------------
  // Campana con contador, aviso emergente para propuestas nuevas y consulta cada 30 s
  // (solo con la pestaña visible) para enterarse sin recargar la página.

  var notifyUrl = document.querySelector("meta[name=notify-url]");
  var seenUrl = document.querySelector("meta[name=notify-seen-url]");
  var toastRoot = document.querySelector(".toast-root");
  var shownTrades = {};  // propuestas que ya han tenido su aviso en esta página

  function csrfHeaders() {
    return { "X-CSRF-Token": document.querySelector("meta[name=csrf-token]").content };
  }

  function markSeen() {
    if (seenUrl) fetch(seenUrl.content, { method: "POST", headers: csrfHeaders(), credentials: "same-origin" });
  }

  function showToast(toast) {
    requestAnimationFrame(function () { toast.classList.add("show"); });
    toast.querySelector(".toast-close").addEventListener("click", function () {
      toast.classList.remove("show");
      setTimeout(function () { toast.remove(); }, 250);
      markSeen();
    });
  }

  function buildToast(unseen) {
    var toast = el("div", "toast");
    toast.setAttribute("role", "status");
    var text = el("div", "toast-text");
    text.appendChild(document.createTextNode("🔔 "));
    text.appendChild(el("b", "", unseen[0].from));
    text.appendChild(document.createTextNode(" te propone un intercambio"));
    if (unseen.length > 1) text.appendChild(el("span", "toast-more", " (y " + (unseen.length - 1) + " más)"));
    var link = el("a", "btn btn-small", "Ver");
    link.href = (document.querySelector(".bell-footer") || {}).href || "/trades/";
    var close = el("button", "toast-close", "✕");
    close.type = "button";
    close.setAttribute("aria-label", "Cerrar aviso");
    toast.appendChild(text);
    toast.appendChild(link);
    toast.appendChild(close);
    return toast;
  }

  function setCount(node, count) {
    if (!node) return;
    node.textContent = count;
    node.hidden = !count;
  }

  if (toastRoot) {
    var initial = toastRoot.querySelector(".toast");
    if (initial) {
      initial.getAttribute("data-trade-ids").split(",").forEach(function (id) { shownTrades[id] = true; });
      showToast(initial);
    }
  }

  function poll() {
    if (!notifyUrl || document.visibilityState !== "visible") return;
    fetch(notifyUrl.content, { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        var bell = document.querySelector(".bell");
        var badge = bell ? data.incoming : data.dm_pending;
        setCount(document.querySelector(".bell-count"), data.incoming);
        setCount(document.querySelector("[data-trade-badge]"), badge);
        // Refresca el panel salvo si está abierto (no cambiarlo mientras se usa)
        if (bell && data.panel && !bell.open) bell.querySelector(".bell-panel").innerHTML = data.panel;
        var fresh = (data.unseen || []).filter(function (t) { return !shownTrades[t.id]; });
        if (fresh.length && toastRoot && !location.pathname.startsWith("/trades/")) {
          (data.unseen || []).forEach(function (t) { shownTrades[t.id] = true; });
          var old = toastRoot.querySelector(".toast");
          if (old) old.remove();
          var toast = buildToast(data.unseen);
          toastRoot.appendChild(toast);
          showToast(toast);
        }
      })
      .catch(function () { /* sin conexión: se reintenta en la próxima consulta */ });
  }

  if (notifyUrl) {
    setInterval(poll, 30000);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") poll();
    });
  }

  // --- Copiar al portapapeles: <button data-copy="texto"> -------------------------------

  document.addEventListener("click", function (e) {
    var button = e.target.closest("[data-copy]");
    if (!button) return;
    var text = button.getAttribute("data-copy");
    var label = button.textContent;
    function done(ok) {
      button.textContent = ok ? "¡Copiado!" : text;  // si no se puede copiar, al menos se ve entero
      setTimeout(function () { button.textContent = label; }, 1600);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
    } else {
      done(false);
    }
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
      var toggle = el("button", "picker-filter-btn");
      toggle.type = "button";
      toggle.innerHTML = FUNNEL_ICON + "<span>Filtros</span>";
      toggle.setAttribute("aria-expanded", "false");
      var badge = el("span", "picker-filter-count");
      badge.hidden = true;
      toggle.appendChild(badge);
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
        if (f.value) select.value = f.value;  // filtro preseleccionado (p. ej. la clase del personaje)
        select.addEventListener("change", function () {
          var count = self.filterSelects.filter(function (s) { return s.value; }).length;
          badge.textContent = count;
          badge.hidden = !count;
          toggle.classList.toggle("is-active", count > 0);
          toggle.setAttribute("aria-label", count ? "Filtros (" + count + " activos)" : "Filtros");
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
      var preset = this.filterSelects.filter(function (s) { return s.value; }).length;
      if (preset) {
        badge.textContent = preset;
        badge.hidden = false;
        toggle.classList.add("is-active");
      }
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
      var text = li;
      if (item.avatar) {
        li.classList.add("with-avatar");
        li.appendChild(avatarIcon(item.avatar));
        text = el("span", "picker-text");
        li.appendChild(text);
      }
      text.appendChild(highlight(item.label, self.input.value));
      if (item.sub) text.appendChild(el("span", "picker-sub", item.sub));
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

  // --- Imagen de personaje: arrastrar y soltar, vista previa y reducción previa -----------
  // El servidor vuelve a procesar la imagen (256 px, WebP); aquí solo se reduce para que
  // la subida sea rápida en el móvil aunque la foto original pese varios MB.

  var MAX_UPLOAD = 8 * 1024 * 1024;
  var PRE_RESIZE = 512;
  var IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];

  function kb(bytes) { return Math.max(1, Math.round(bytes / 1024)) + " KB"; }

  function setFile(input, file) {
    try {
      var dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      return true;
    } catch (err) {
      return false;  // navegador antiguo: se envía el archivo original
    }
  }

  /** Reduce la imagen a PRE_RESIZE px como máximo (devuelve una promesa con un File o null). */
  function shrink(file) {
    return new Promise(function (resolve) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        URL.revokeObjectURL(url);
        var scale = Math.min(1, PRE_RESIZE / Math.max(img.naturalWidth, img.naturalHeight));
        if (scale === 1 && file.size < 300 * 1024) { resolve(null); return; }
        var canvas = document.createElement("canvas");
        canvas.width = Math.round(img.naturalWidth * scale);
        canvas.height = Math.round(img.naturalHeight * scale);
        canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
        canvas.toBlob(function (blob) {
          resolve(blob && blob.size < file.size ? new File([blob], "imagen.webp", { type: blob.type }) : null);
        }, "image/webp", 0.9);
      };
      img.onerror = function () { URL.revokeObjectURL(url); resolve(null); };
      img.src = url;
    });
  }

  function Dropzone(zone) {
    var input = zone.querySelector("input[type=file]");
    var preview = zone.querySelector(".dropzone-preview");
    var text = zone.querySelector(".dropzone-text");
    var original = text.innerHTML;
    var editor = zone.closest(".avatar-editor");

    function reset(message) {
      input.value = "";
      preview.hidden = true;
      zone.classList.remove("has-file");
      text.innerHTML = original;
      if (message) {
        var warning = el("span", "picker-error", message);
        text.appendChild(document.createElement("br"));
        text.appendChild(warning);
      }
    }

    function handle(file) {
      if (!file) return;
      if (IMAGE_TYPES.indexOf(file.type) === -1) { reset("Formato no admitido. Usa JPG, PNG, WebP o GIF."); return; }
      if (file.size > MAX_UPLOAD) { reset("La imagen supera 8 MB."); return; }
      if (input.files[0] !== file) setFile(input, file);
      preview.src = URL.createObjectURL(file);
      preview.hidden = false;
      zone.classList.add("has-file");
      text.textContent = file.name + " · " + kb(file.size);
      shrink(file).then(function (smaller) {
        if (smaller && setFile(input, smaller)) {
          text.textContent = file.name + " · se subirá reducida (" + kb(smaller.size) + ")";
        }
      });
    }

    input.addEventListener("change", function () { handle(input.files[0]); });
    ["dragenter", "dragover"].forEach(function (type) {
      zone.addEventListener(type, function (e) { e.preventDefault(); zone.classList.add("dragover"); });
    });
    ["dragleave", "drop"].forEach(function (type) {
      zone.addEventListener(type, function () { zone.classList.remove("dragover"); });
    });
    zone.addEventListener("drop", function (e) {
      e.preventDefault();
      handle(e.dataTransfer.files[0]);
    });

    // Soltar una imagen directamente sobre el icono abre el editor con ella cargada
    if (editor) {
      var trigger = editor.querySelector(".avatar-trigger");
      trigger.addEventListener("dragover", function (e) { e.preventDefault(); editor.open = true; });
      trigger.addEventListener("drop", function (e) {
        e.preventDefault();
        editor.open = true;
        handle(e.dataTransfer.files[0]);
      });
    }
  }

  document.querySelectorAll(".dropzone").forEach(function (zone) { new Dropzone(zone); });

  // --- Estadísticas calculadas: desglose al tocar / pulsar --------------------------------

  function closeCalcs(except) {
    document.querySelectorAll(".calc.open").forEach(function (el) {
      if (el === except) return;
      el.classList.remove("open");
      el.setAttribute("aria-expanded", "false");
    });
  }

  document.addEventListener("click", function (e) {
    var calc = e.target.closest(".calc");
    if (calc && e.target.closest(".calc-pop")) return;  // leer el desglose no lo cierra
    var control = e.target.closest("button, a, input, select, label");
    if (calc && control && calc.contains(control)) calc = null;  // los controles dentro del recuadro no lo abren
    closeCalcs(calc);
    if (calc) {
      var open = calc.classList.toggle("open");
      calc.setAttribute("aria-expanded", String(open));
    }
  });

  document.addEventListener("keydown", function (e) {
    var calc = e.target.closest && e.target.closest(".calc");
    if (e.key === "Escape") { closeCalcs(null); return; }
    if (calc && e.target === calc && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      calc.click();
    }
  });

  // --- Editor de efectos: añadir y quitar filas ------------------------------------------

  document.addEventListener("click", function (e) {
    var add = e.target.closest(".eff-add");
    if (add) {
      var editor = add.closest(".effects-editor");
      var row = editor.querySelector(".eff-template").content.firstElementChild.cloneNode(true);
      editor.querySelector(".eff-rows").appendChild(row);
      row.querySelector("select").focus();
      return;
    }
    var remove = e.target.closest(".eff-remove");
    if (remove) remove.closest(".eff-row").remove();
  });

  // --- Formulario de personaje: clase y subclase rellenan sus valores por defecto ---------

  document.querySelectorAll(".class-picker").forEach(function (box) {
    var form = box.closest("form");
    var catalog = JSON.parse(box.getAttribute("data-catalog") || "[]");
    var creating = box.getAttribute("data-creating") === "1";
    var classSel = box.querySelector(".js-class");
    var subSel = box.querySelector(".js-subclass");
    var hpMax = form.querySelector(".js-hp-max");
    var hpCur = form.querySelector(".js-hp-current");
    var hpTouched = false;
    if (hpMax) hpMax.addEventListener("input", function () { hpTouched = true; });

    function current() {
      return catalog.filter(function (c) { return String(c.id) === classSel.value; })[0] || null;
    }
    function currentSub(cls) {
      if (!cls) return null;
      return cls.subclasses.filter(function (s) { return String(s.id) === subSel.value; })[0] || null;
    }
    function setValue(selector, value) {
      var input = box.querySelector(selector);
      if (input) input.value = value == null ? "" : String(value);
    }
    function applyMagic(d) {
      setValue(".js-caster", d.caster || "none");
      setValue(".js-spell-ability", d.spell_ability);
      setValue(".js-spell-prep", d.spell_prep);
    }
    function suggestHp() {
      // Solo al crear y si no ha escrito los PG a mano: dado entero a nivel 1 y la media después
      var die = parseInt(box.querySelector(".js-hit-die").value, 10);
      if (!creating || hpTouched || !die || !hpMax) return;
      var level = Math.max(1, parseInt((form.querySelector("[name=level]") || {}).value, 10) || 1);
      var con = parseInt((form.querySelector("[name=constitution]") || {}).value, 10) || 10;
      var mod = Math.floor((con - 10) / 2);
      var hp = Math.max(1, die + mod + (level - 1) * (Math.floor(die / 2) + 1 + mod));
      hpMax.value = hp;
      if (hpCur) hpCur.value = hp;
    }
    function refreshVisibility() {
      var cls = current();
      box.querySelector(".js-class-name").hidden = classSel.value !== "custom";
      Array.prototype.forEach.call(subSel.options, function (opt) {
        var owner = opt.getAttribute("data-class");
        if (owner) opt.hidden = opt.disabled = !cls || owner !== String(cls.id);
      });
      if (subSel.selectedOptions[0] && subSel.selectedOptions[0].disabled) subSel.value = "";
      box.querySelector(".js-subclass-name").hidden = subSel.value !== "custom";
      box.querySelector(".js-subclass-hint").textContent =
        cls && cls.subclasses.length ? "La consigue a nivel " + cls.subclass_level + "." : "";
      box.querySelector(".js-class-profs").textContent = cls && cls.proficiencies ? "Competencias de clase: " + cls.proficiencies : "";
    }

    classSel.addEventListener("change", function () {
      subSel.value = "";
      refreshVisibility();
      var cls = current();
      if (!cls) return;
      var d = cls.defaults;
      setValue(".js-hit-die", d.hit_die);
      applyMagic(d);
      form.querySelectorAll("input[name^=save_]").forEach(function (cb) {
        cb.checked = d.saves.indexOf(cb.name.slice(5)) !== -1;
      });
      suggestHp();
    });
    subSel.addEventListener("change", function () {
      refreshVisibility();
      var cls = current(), sub = currentSub(cls);
      if (cls) applyMagic(sub ? sub.defaults : cls.defaults);
    });
    box.querySelector(".js-hit-die").addEventListener("change", suggestHp);
    ["level", "constitution"].forEach(function (name) {
      var input = form.querySelector("[name=" + name + "]");
      if (input) input.addEventListener("input", suggestHp);
    });
    refreshVisibility();
  });

  // --- PG: botones − / + sin recargar la página ---------------------------------------------

  document.querySelectorAll("form.hp-panel").forEach(function (form) {
    var amount = form.querySelector("input[name=amount]");
    form.querySelectorAll(".hp-preset").forEach(function (b) {
      b.addEventListener("click", function () { amount.value = b.getAttribute("data-amount"); });
    });
    function paint(state) {
      var max = state.hp_max || 0;
      var pct = max ? Math.max(0, Math.min(100, state.hp_current / max * 100)) : 0;
      var tempPct = max ? Math.min(state.hp_temp / max * 100, 100 - pct) : 0;
      form.querySelector(".js-hp-current").textContent = state.hp_current;
      form.querySelector(".js-hp-temp").textContent = state.hp_temp;
      var bar = form.querySelector(".js-hp-bar");
      bar.style.width = pct.toFixed(1) + "%";
      bar.style.setProperty("--hp", pct > 50 ? "#2f6b3a" : pct > 25 ? "#b7791f" : "#a12a22");
      form.querySelector(".js-temp-bar").style.width = tempPct.toFixed(1) + "%";
      form.querySelector(".hp-block.temp").classList.toggle("has-temp", state.hp_temp > 0);
    }
    form.addEventListener("submit", function (e) {
      var button = e.submitter;
      if (!button || button.name !== "op" || !window.fetch) return;  // sin JS moderno: envío normal
      e.preventDefault();
      var data = new FormData(form);
      data.set("op", button.value);
      button.disabled = true;
      fetch(form.action, {
        method: "POST", body: data, credentials: "same-origin",
        headers: Object.assign({ "Accept": "application/json" }, csrfHeaders()),
      }).then(function (r) {
        return r.json().then(function (body) { if (!r.ok) throw new Error(body.error || "Error"); return body; });
      }).then(paint).catch(function () {
        form.submit();  // si algo falla, como siempre (recarga con el aviso del servidor)
      }).finally(function () { button.disabled = false; });
    });
  });

  // --- Secciones plegables: recuerdan si las cierras y se abren si un enlace apunta a ellas -----

  function openFromHash() {
    var target = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
    var fold = target && target.closest("details.fold");
    if (fold) fold.open = true;
  }
  document.querySelectorAll("details.fold[data-fold]").forEach(function (fold) {
    var key = "fold:" + fold.getAttribute("data-fold");
    try {
      if (localStorage.getItem(key) === "closed") fold.open = false;
    } catch (e) { /* sin almacenamiento: todo abierto */ }
    fold.addEventListener("toggle", function () {
      try {
        if (fold.open) localStorage.removeItem(key); else localStorage.setItem(key, "closed");
      } catch (e) { /* nada */ }
    });
  });
  openFromHash();
  window.addEventListener("hashchange", openFromHash);
  requestAnimationFrame(function () { document.documentElement.classList.add("fold-ready"); });
  document.addEventListener("click", function (e) {
    var button = e.target.closest("[data-fold-all]");
    if (!button) return;
    var open = button.getAttribute("data-fold-all") === "open";
    document.querySelectorAll("details.fold").forEach(function (fold) { fold.open = open; });
  });

  // --- Catálogo: el bloque «Arma» solo se ve si el objeto es un arma ---------------------------

  document.addEventListener("change", function (e) {
    if (!e.target.matches(".js-weapon-toggle")) return;
    e.target.closest(".weapon-editor").querySelector(".weapon-fields").hidden = !e.target.checked;
  });

  // --- Inventario: pestañas por tipo de objeto (recuerda la última) -------------------------------

  document.querySelectorAll(".inv-tabs").forEach(function (bar) {
    var list = bar.parentElement.querySelector(".inv-list");
    function show(key) {
      var tab = bar.querySelector('[data-tab="' + key + '"]') || bar.querySelector('[data-tab="all"]');
      key = tab.getAttribute("data-tab");
      bar.querySelectorAll(".inv-tab").forEach(function (b) { b.setAttribute("aria-selected", String(b === tab)); });
      list.querySelectorAll(".inv-item").forEach(function (item) {
        item.hidden = key !== "all" && item.getAttribute("data-group") !== key;
      });
      try { localStorage.setItem("invtab", key); } catch (e) { /* nada */ }
    }
    bar.addEventListener("click", function (e) {
      var tab = e.target.closest(".inv-tab");
      if (tab) show(tab.getAttribute("data-tab"));
    });
    var saved = "all";
    try { saved = localStorage.getItem("invtab") || "all"; } catch (e) { /* nada */ }
    show(saved);
  });
})();
