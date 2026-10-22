/* ReverseAI console: theme toggle, tabs, approval checkbox, job polling. No inline scripts. */
(function () {
  "use strict";

  var THEME_KEY = "reverseai-theme";
  var root = document.documentElement;

  function storedTheme() {
    try {
      var value = window.localStorage.getItem(THEME_KEY);
      return value === "dark" || value === "light" ? value : null;
    } catch (e) {
      return null;
    }
  }

  function saveTheme(value) {
    try {
      window.localStorage.setItem(THEME_KEY, value);
    } catch (e) {
      /* storage unavailable: the choice lasts for this page only */
    }
  }

  function currentTheme() {
    var forced = root.getAttribute("data-theme");
    if (forced) return forced;
    var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    return dark ? "dark" : "light";
  }

  // Applied before first paint (this script is loaded synchronously in <head>).
  var initial = storedTheme();
  if (initial) root.setAttribute("data-theme", initial);

  function initThemeToggle() {
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    Array.prototype.forEach.call(buttons, function (button) {
      button.addEventListener("click", function () {
        var next = currentTheme() === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        saveTheme(next);
      });
    });
  }

  function initTabs() {
    var lists = document.querySelectorAll("[data-tabs]");
    Array.prototype.forEach.call(lists, function (list) {
      var tabs = list.querySelectorAll("[data-tab]");
      Array.prototype.forEach.call(tabs, function (tab) {
        tab.addEventListener("click", function (event) {
          event.preventDefault();
          var key = tab.getAttribute("data-tab");
          Array.prototype.forEach.call(tabs, function (other) {
            var selected = other === tab;
            other.setAttribute("aria-selected", selected ? "true" : "false");
            var panel = document.getElementById("tab-" + other.getAttribute("data-tab"));
            if (panel) panel.hidden = !selected;
          });
          if (window.history && window.history.replaceState) {
            window.history.replaceState(null, "", "?tab=" + encodeURIComponent(key));
          }
        });
      });
    });
  }

  function initConfirm() {
    var forms = document.querySelectorAll("form[data-confirm]");
    Array.prototype.forEach.call(forms, function (form) {
      var box = form.querySelector('input[name="confirm"]');
      var submit = form.querySelector("[data-confirm-submit]");
      if (!box || !submit || submit.disabled) return;
      var sync = function () {
        submit.disabled = !box.checked;
      };
      box.addEventListener("change", sync);
      sync();
    });
  }

  function initJobPolling() {
    var panel = document.getElementById("job");
    if (!panel || panel.getAttribute("data-job-status") !== "running") return;
    var url = panel.getAttribute("data-job-url");
    var timer = window.setInterval(function () {
      fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (response) {
          return response.ok ? response.json() : null;
        })
        .then(function (data) {
          if (!data || !data.job) return;
          var job = data.job;
          var status = panel.querySelector('[data-job-field="status_label"]');
          if (status) status.textContent = job.status_label;
          var log = panel.querySelector('[data-job-field="log"]');
          if (log) log.textContent = job.log.join("\n");
          if (job.status !== "running") {
            window.clearInterval(timer);
            window.location.reload();
          }
        })
        .catch(function () {
          /* the server may be restarting: keep polling */
        });
    }, 1500);
  }

  document.addEventListener("DOMContentLoaded", function () {
    initThemeToggle();
    initTabs();
    initConfirm();
    initJobPolling();
  });
})();
