/* Invoices list: click the status pill to toggle Paid / Unpaid without
   opening the invoice row. */
(function () {
  "use strict";
  document.querySelectorAll(".status-toggle").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.stopPropagation();             // don't trigger the row's open-invoice click
      var number = btn.getAttribute("data-number");
      btn.disabled = true;
      fetch("/invoices/" + number + "/toggle-status", { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (!res.ok) throw new Error();
          btn.textContent = res.status;
          btn.classList.toggle("tag-paid", res.status === "Paid");
          btn.classList.toggle("tag-unpaid", res.status === "Unpaid");
        })
        .catch(function () { btn.textContent = "?"; })
        .finally(function () { btn.disabled = false; });
    });
  });
})();
