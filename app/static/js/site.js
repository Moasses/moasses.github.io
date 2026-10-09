/* Small progressive enhancements. The site works fully without JavaScript. */
(function () {
  "use strict";

  /* close the burger menu after choosing a link */
  var menu = document.querySelector(".menu-wrap");
  if (menu) {
    menu.addEventListener("click", function (e) {
      if (e.target.tagName === "A") menu.removeAttribute("open");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") menu.removeAttribute("open");
    });
  }
    /* email links: the address is only assembled when someone clicks,
     so it never appears as a complete address in the page source */
  Array.prototype.forEach.call(document.querySelectorAll("a.mail[data-u][data-d]"), function (a) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      window.location.href = "mailto:" + a.getAttribute("data-u") + "@" + a.getAttribute("data-d");
    });
  });
  
  /* publication type filters */
  var bar = document.querySelector(".filters");
  if (bar) {
    bar.classList.remove("hidden");
    bar.addEventListener("click", function (e) {
      var k = e.target.getAttribute("data-k");
      if (!k) return;
      Array.prototype.forEach.call(bar.querySelectorAll("button"), function (b) {
        b.classList.toggle("on", b === e.target);
        b.setAttribute("aria-pressed", b === e.target ? "true" : "false");
      });
      Array.prototype.forEach.call(document.querySelectorAll(".pub"), function (p) {
        p.classList.toggle("hidden", k !== "all" && p.getAttribute("data-type") !== k);
      });
      Array.prototype.forEach.call(document.querySelectorAll(".pub-group"), function (g) {
        g.classList.toggle("hidden", !g.querySelector(".pub:not(.hidden)"));
      });
    });
  }
})();
