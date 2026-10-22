// TaskBoard Pro front-end: renders the task list and talks to the JSON API.
(function () {
  "use strict";

  var form = document.getElementById("task-form");
  var list = document.getElementById("task-list");
  var errorBox = document.getElementById("form-error");
  var statsBox = document.getElementById("stats");

  var MESSAGES = {
    title_required: "Please enter a title.",
    title_too_long: "That title is too long (200 characters max).",
    invalid_priority: "Unknown priority.",
    duplicate: "You already have an open task with that title.",
    not_found: "That task no longer exists.",
  };

  function showError(code) {
    errorBox.textContent = code ? MESSAGES[code] || "Error: " + code : "";
  }

  function request(method, url, body) {
    var options = { method: method, headers: {} };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    return fetch(url, options).then(function (res) {
      if (res.status === 204) {
        return { ok: true, status: 204, data: null };
      }
      return res.json().then(function (data) {
        return { ok: res.ok, status: res.status, data: data };
      });
    });
  }

  function renderTask(task) {
    var item = document.createElement("li");
    item.dataset.id = task.id;
    if (task.done) {
      item.className = "done";
    }

    var box = document.createElement("input");
    box.type = "checkbox";
    box.checked = task.done;
    box.addEventListener("change", function () {
      toggleDone(task.id, box.checked);
    });

    var title = document.createElement("span");
    title.className = "title";
    title.textContent = task.title;

    var badge = document.createElement("small");
    badge.className = "priority-" + task.priority;
    badge.textContent = task.priority;

    var remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Delete";
    remove.addEventListener("click", function () {
      removeTask(task.id);
    });

    item.append(box, title, badge, remove);
    return item;
  }

  function renderStats(stats) {
    statsBox.textContent =
      stats.total + " total, " + stats.open + " open, " + stats.done + " done";
  }

  function refresh() {
    return Promise.all([request("GET", "/api/tasks"), request("GET", "/api/stats")]).then(
      function (results) {
        list.replaceChildren.apply(list, results[0].data.map(renderTask));
        renderStats(results[1].data);
      }
    );
  }

  function toggleDone(id, done) {
    request("PATCH", "/api/tasks/" + id, { done: done }).then(function (res) {
      showError(res.ok ? null : res.data.error);
      refresh();
    });
  }

  function removeTask(id) {
    request("DELETE", "/api/tasks/" + id).then(function (res) {
      showError(res.ok ? null : res.data.error);
      refresh();
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var payload = {
      title: form.elements.title.value,
      priority: form.elements.priority.value,
    };
    request("POST", "/api/tasks", payload).then(function (res) {
      if (!res.ok) {
        showError(res.data.error);
        return;
      }
      showError(null);
      form.reset();
      refresh();
    });
  });

  refresh();
})();
