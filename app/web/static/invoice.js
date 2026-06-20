/* Invoice create/edit screen: line-item grid, live totals, client picker,
   draft autosave, and Save / Save & Print / Save & Email. Vanilla JS, offline. */
(function () {
  "use strict";

  var DATA = JSON.parse(document.getElementById("invoiceData").textContent);
  var GST_RATE = parseFloat(DATA.gstRate) || 15;
  var clients = DATA.clients || [];
  var invoiceNumber = DATA.invoice ? DATA.invoice.invoice_number : null;
  var currentStatus = DATA.invoice ? DATA.invoice.status : null;
  var selectedClient = null;
  var dirty = false;

  var $ = function (id) { return document.getElementById(id); };
  var itemsBody = $("itemsBody");

  // ---- Money helpers (match the server: round each step to 2dp) ----
  function round2(n) { return Math.round((Number(n) + Number.EPSILON) * 100) / 100; }
  function fmt(n) {
    return Number(round2(n)).toLocaleString("en-NZ", { style: "currency", currency: "NZD" });
  }

  $("gstLabel").textContent = "GST Content (" + GST_RATE + "%)";

  // ---------------------------------------------------------------- line rows
  function makeRow(line) {
    line = line || {};
    var tr = document.createElement("tr");
    tr.className = "item-row";
    tr.innerHTML =
      '<td class="col-type"><select class="f-type">' +
        ["Labour", "Part", "Other"].map(function (t) {
          var sel = (line.type || "Labour") === t ? " selected" : "";
          return '<option' + sel + ">" + t + "</option>";
        }).join("") +
      "</select></td>" +
      '<td><input class="f-desc" type="text"></td>' +
      '<td class="num"><input class="f-qty num" type="text" inputmode="decimal"></td>' +
      '<td class="num"><input class="f-price num" type="text" inputmode="decimal"></td>' +
      '<td class="num f-total">$0.00</td>' +
      '<td class="col-del"><button type="button" class="row-del" title="Remove this line">&times;</button></td>';

    tr.querySelector(".f-desc").value = line.description || "";
    tr.querySelector(".f-qty").value = line.quantity != null ? trimNum(line.quantity) : "";
    tr.querySelector(".f-price").value = line.unit_price != null ? trimNum(line.unit_price) : "";

    tr.querySelectorAll("input, select").forEach(function (el) {
      el.addEventListener("input", function () { recalc(); markDirty(); });
    });
    tr.querySelector(".row-del").addEventListener("click", function () {
      tr.remove();
      ensureBlankRow();
      recalc();
      markDirty();
    });
    // Tab off the unit price on the last row -> new row (spreadsheet feel).
    tr.querySelector(".f-price").addEventListener("keydown", function (e) {
      if (e.key === "Tab" && !e.shiftKey && tr === itemsBody.lastElementChild) {
        e.preventDefault();
        var row = addRow();
        row.querySelector(".f-desc").focus();
      }
    });
    return tr;
  }

  function trimNum(v) {
    var f = Number(v);
    if (isNaN(f)) return v;
    return f === Math.trunc(f) ? String(Math.trunc(f)) : String(f);
  }

  function addRow(line) {
    var tr = makeRow(line);
    itemsBody.appendChild(tr);
    return tr;
  }

  function ensureBlankRow() {
    if (!itemsBody.querySelector(".item-row")) addRow();
  }

  // ------------------------------------------------------------------ totals
  function recalc() {
    var subtotal = 0;
    itemsBody.querySelectorAll(".item-row").forEach(function (tr) {
      var qty = parseFloat(tr.querySelector(".f-qty").value) || 0;
      var price = parseFloat(tr.querySelector(".f-price").value) || 0;
      var lt = round2(qty * price);
      tr.querySelector(".f-total").textContent = fmt(lt);
      subtotal += lt;
    });
    subtotal = round2(subtotal);
    var gst = round2(subtotal * GST_RATE / 100);
    var amount = round2(subtotal + gst);
    $("subtotal").textContent = fmt(subtotal);
    $("gst").textContent = fmt(gst);
    $("amountPayable").textContent = fmt(amount);
    updateBigInvoiceWarning(amount);
  }

  var warningDismissed = false;
  function updateBigInvoiceWarning(amount) {
    var noAddress = !selectedClient || !(selectedClient.address || "").trim();
    var show = amount > 1000 && noAddress && !warningDismissed;
    $("bigInvoiceWarning").hidden = !show;
  }
  $("dismissWarning").addEventListener("click", function () {
    warningDismissed = true;
    $("bigInvoiceWarning").hidden = true;
  });

  // ------------------------------------------------------------ client picker
  var clientSearch = $("clientSearch");
  var clientResults = $("clientResults");

  function showResults(term) {
    term = term.toLowerCase().trim();
    clientResults.innerHTML = "";
    if (!term) { clientResults.hidden = true; return; }
    var matches = clients.filter(function (c) {
      return (c.name + " " + c.code + " " + c.phone + " " + c.email).toLowerCase().indexOf(term) >= 0;
    }).slice(0, 8);
    if (!matches.length) { clientResults.hidden = true; return; }
    matches.forEach(function (c) {
      var div = document.createElement("div");
      div.className = "picker-item";
      div.textContent = c.name + (c.code ? "  (" + c.code + ")" : "");
      div.addEventListener("mousedown", function (e) { e.preventDefault(); pickClient(c); });
      clientResults.appendChild(div);
    });
    clientResults.hidden = false;
  }

  function pickClient(c) {
    selectedClient = c;
    $("clientId").value = c.id;
    clientSearch.value = c.name;
    clientResults.hidden = true;
    recalc();
    markDirty();
  }

  clientSearch.addEventListener("input", function () {
    selectedClient = null;
    $("clientId").value = "";
    showResults(clientSearch.value);
  });
  clientSearch.addEventListener("blur", function () {
    setTimeout(function () { clientResults.hidden = true; }, 150);
  });

  // --------------------------------------------------------------- save logic
  function collect() {
    var lines = [];
    itemsBody.querySelectorAll(".item-row").forEach(function (tr) {
      lines.push({
        type: tr.querySelector(".f-type").value,
        description: tr.querySelector(".f-desc").value,
        quantity: tr.querySelector(".f-qty").value,
        unit_price: tr.querySelector(".f-price").value
      });
    });
    return {
      invoice_number: invoiceNumber,
      client_id: $("clientId").value || null,
      client_name: clientSearch.value,
      invoice_date: $("invoiceDate").value,
      reference: $("reference").value,
      details: $("details").value,
      lines: lines
    };
  }

  function setStatus(msg, kind) {
    var el = $("saveStatus");
    el.textContent = msg || "";
    el.className = "save-status" + (kind ? " " + kind : "");
  }

  function save() {
    var payload = collect();
    if (!payload.client_id && !payload.client_name.trim()) {
      setStatus("Please choose a client first.", "err");
      clientSearch.focus();
      return Promise.reject();
    }
    setStatus("Saving…");
    return fetch("/invoices/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) throw new Error("save failed");
      var isNew = !invoiceNumber;
      invoiceNumber = res.invoice_number;
      if (isNew && !currentStatus) currentStatus = "Unpaid";
      $("formTitle").textContent = "Invoice " + invoiceNumber;
      history.replaceState(null, "", "/invoices/" + invoiceNumber);
      clearDraft();
      dirty = false;
      setStatus("Saved invoice " + invoiceNumber + ".", "ok");
      refreshButtons();
      return res;
    }).catch(function (e) {
      setStatus("Sorry, that could not be saved. Please try again.", "err");
      throw e;
    });
  }

  function openPdf() { window.open("/invoices/" + invoiceNumber + "/pdf", "_blank"); }

  // req 5: a saved, unchanged invoice shows a green tick and Save opens the PDF.
  $("btnSave").addEventListener("click", function () {
    if (invoiceNumber && !dirty) { openPdf(); return; }
    save();
  });

  // req 4: status / cash-sale button.
  function setStatusButton(label, cls) {
    var b = $("btnStatus");
    b.textContent = label;
    b.className = "btn btn-big btn-cash" + (cls ? " " + cls : "");
  }
  function refreshButtons() {
    $("saveTick").hidden = !(invoiceNumber && !dirty);
    $("btnDelete").hidden = !invoiceNumber;   // can only delete a saved invoice
    if (!invoiceNumber) {
      setStatusButton("Cash Sale — Save, Pay & Print", "");      // grey, not saved yet
    } else if (currentStatus === "Paid") {
      setStatusButton("Paid ✓", "btn-status-paid");          // green
    } else {
      setStatusButton("Mark as Paid", "btn-status-unpaid");       // red
    }
  }

  function toggleStatus() {
    return fetch("/invoices/" + invoiceNumber + "/toggle-status", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (res) { currentStatus = res.status; refreshButtons(); return res; });
  }

  $("btnStatus").addEventListener("click", function () {
    if (!invoiceNumber) {
      // Cash sale: save, mark paid, and open for printing in one step.
      save().then(function () { return toggleStatus(); }).then(function () { openPdf(); });
    } else {
      toggleStatus();
    }
  });

  $("btnDelete").addEventListener("click", function () {
    if (!invoiceNumber) return;
    if (!confirm("Delete invoice " + invoiceNumber + "? This permanently removes the "
                 + "invoice and its PDF file. This cannot be undone.")) return;
    fetch("/invoices/" + invoiceNumber + "/delete", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok) throw new Error();
        clearDraft();
        window.location = "/invoices/";
      })
      .catch(function () { setStatus("Sorry, that could not be deleted.", "err"); });
  });

  $("btnSavePrint").addEventListener("click", function () {
    save().then(function (res) {
      window.open("/invoices/" + res.invoice_number + "/pdf", "_blank");
    });
  });

  $("btnSaveEmail").addEventListener("click", function () {
    save().then(function (res) {
      var n = res.invoice_number;
      var to = selectedClient ? selectedClient.email : "";
      var subject = "Invoice " + n + " - " + DATA.businessName;
      var body = "Hi,\n\nPlease find attached invoice " + n + ".\n\n" +
                 "Thanks,\n" + (DATA.ownerName || DATA.businessName);
      // Download the PDF so it is ready to drag into the email.
      var a = document.createElement("a");
      a.href = "/invoices/" + n + "/pdf?download=1";
      document.body.appendChild(a); a.click(); a.remove();
      // Open a pre-filled Gmail compose window.
      var url = "https://mail.google.com/mail/?view=cm&fs=1" +
        "&to=" + encodeURIComponent(to) +
        "&su=" + encodeURIComponent(subject) +
        "&body=" + encodeURIComponent(body);
      window.open(url, "_blank");
    });
  });

  // --------------------------------------------------------- draft autosave
  var DRAFT_KEY = "invoice-draft-" + (invoiceNumber || "new");
  var draftTimer = null;
  function markDirty() {
    dirty = true;
    $("saveTick").hidden = true;  // editing clears the "saved" tick (req 5)
    clearTimeout(draftTimer);
    draftTimer = setTimeout(saveDraft, 600);
  }
  function saveDraft() {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(collect())); } catch (e) {}
  }
  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
  }
  function restoreDraft() {
    if (invoiceNumber) return false; // only restore drafts for brand-new invoices
    var raw = null;
    try { raw = localStorage.getItem(DRAFT_KEY); } catch (e) {}
    if (!raw) return false;
    try {
      var d = JSON.parse(raw);
      if (d.client_id) {
        var c = clients.filter(function (x) { return String(x.id) === String(d.client_id); })[0];
        if (c) pickClient(c);
      } else if (d.client_name) {
        clientSearch.value = d.client_name;
      }
      $("invoiceDate").value = d.invoice_date || DATA.today;
      $("reference").value = d.reference || "";
      $("details").value = d.details || "";
      itemsBody.innerHTML = "";
      (d.lines || []).forEach(function (l) {
        addRow({ type: l.type, description: l.description, quantity: l.quantity, unit_price: l.unit_price });
      });
      ensureBlankRow();
      return true;
    } catch (e) { return false; }
  }

  window.addEventListener("beforeunload", function (e) {
    if (dirty) { saveDraft(); }
  });

  ["invoiceDate", "reference", "details"].forEach(function (id) {
    $(id).addEventListener("input", markDirty);
  });

  // ------------------------------------------------------------------- start
  (DATA.lines || []).forEach(function (l) { addRow(l); });
  ensureBlankRow();
  if (DATA.invoice && DATA.invoice.client_id) {
    var c = clients.filter(function (x) { return String(x.id) === String(DATA.invoice.client_id); })[0];
    if (c) { selectedClient = c; $("clientId").value = c.id; clientSearch.value = c.name; }
    else if (DATA.invoice.client_name) { clientSearch.value = DATA.invoice.client_name; }
  }
  if (!DATA.invoice) restoreDraft();
  recalc();
  refreshButtons();
})();
