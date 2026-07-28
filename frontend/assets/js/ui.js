const toastRegion = () => document.getElementById("toast-region");

export function element(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = String(options.text);
  if (options.title) node.title = options.title;
  if (options.dataset) Object.assign(node.dataset, options.dataset);
  if (options.attrs) {
    for (const [name, value] of Object.entries(options.attrs)) {
      if (value !== false && value !== null && value !== undefined) {
        node.setAttribute(name, value === true ? "" : String(value));
      }
    }
  }
  const list = Array.isArray(children) ? children : [children];
  node.append(...list.filter(Boolean));
  return node;
}

export function button(text, className, onClick, ariaLabel = text) {
  const node = element("button", {
    className,
    text,
    attrs: { type: "button", "aria-label": ariaLabel },
  });
  node.addEventListener("click", onClick);
  return node;
}

export function clear(node) {
  node.replaceChildren();
}

export function setHidden(nodeOrId, hidden) {
  const node =
    typeof nodeOrId === "string" ? document.getElementById(nodeOrId) : nodeOrId;
  node.hidden = hidden;
}

export function showToast(message, type = "info", timeout = 5000) {
  const toast = element("div", {
    className: `toast toast--${type}`,
    text: message,
    attrs: { role: type === "error" ? "alert" : "status" },
  });
  toastRegion().append(toast);
  window.setTimeout(() => toast.remove(), timeout);
}

export function setConnectionState(kind, message) {
  const banner = document.getElementById("connection-banner");
  const pill = document.getElementById("connection-pill");
  banner.dataset.state = kind;
  banner.textContent = message;
  banner.hidden = kind === "connected";
  pill.dataset.state = kind;
  pill.textContent =
    kind === "connected"
      ? "Подключено"
      : kind === "changed"
        ? "Туннель сменился"
        : kind === "starting"
          ? "Сервер запускается"
          : "Нет соединения";
}

export function openDialog(dialog) {
  if (!dialog.open) dialog.showModal();
  const first = dialog.querySelector(
    "input:not([type=hidden]), textarea, select, button",
  );
  window.setTimeout(() => first?.focus(), 0);
}

export function closeDialog(dialog) {
  if (dialog.open) dialog.close();
}

export function formatDateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function toDateTimeLocal(value) {
  if (!value) return "";
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function setBusy(form, busy, text = "Сохранение…") {
  const submit = form.querySelector('[type="submit"]');
  if (!submit) return;
  if (busy) {
    submit.dataset.originalText = submit.textContent;
    submit.textContent = text;
    submit.disabled = true;
  } else {
    submit.textContent = submit.dataset.originalText || "Сохранить";
    submit.disabled = false;
  }
}

