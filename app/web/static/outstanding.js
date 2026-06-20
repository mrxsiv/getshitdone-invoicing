/* Outstanding screen: an undoable "Paid" tick. Sorting and paging are handled
   server-side (column headers are links); rows click through to the invoice. */
(function () {
  "use strict";

  var table = document.getElementById("outstandingTable");
  if (!table) return;
  var tbody = table.querySelector("tbody");

  var toast = document.getElementById("toast");
  var toastMsg = document.getElementById("toastMsg");
  var toastUndo = document.getElementById("toastUndo");
  var toastTimer = null;

  function showToast(number, row, nextRow) {
    toastMsg.textContent = "Marked Inv " + number + " as paid.";
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.hidden = true; }, 8000);

    toastUndo.onclick = function () {
      fetch("/outstanding/" + number + "/unpaid", { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function () {
          if (nextRow && nextRow.parentNode === tbody) tbody.insertBefore(row, nextRow);
          else tbody.appendChild(row);
          row.querySelector(".paid-tick").checked = false;
          toast.hidden = true;
        });
    };
  }

  tbody.addEventListener("change", function (e) {
    if (!e.target.classList.contains("paid-tick") || !e.target.checked) return;
    var row = e.target.closest("tr");
    var number = row.getAttribute("data-number");
    var nextRow = row.nextElementSibling;
    fetch("/outstanding/" + number + "/paid", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function () {
        row.remove();
        showToast(number, row, nextRow);
      });
  });

  // Safety: clear any tick the browser restores on Back / bfcache.
  window.addEventListener("pageshow", function () {
    tbody.querySelectorAll(".paid-tick").forEach(function (cb) { cb.checked = false; });
  });
})();
