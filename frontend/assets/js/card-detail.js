import {
  button,
  clear,
  element,
  formatDateTime,
  setBusy,
  showToast,
  toDateTimeLocal,
} from "./ui.js";

const byId = (id) => document.getElementById(id);

function initials(name) {
  return String(name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase("ru") || "")
    .join("");
}

export class CardDrawerController {
  constructor({ api, state, mutationId, errorText, reloadSnapshot, handleMutationError }) {
    this.api = api;
    this.state = state;
    this.mutationId = mutationId;
    this.errorText = errorText;
    this.reloadSnapshot = reloadSnapshot;
    this.handleMutationError = handleMutationError;
    this.card = null;
    this.bound = false;
  }

  bind() {
    if (this.bound) return;
    this.bound = true;
    byId("close-card-drawer").addEventListener("click", () => this.close());
    byId("card-drawer-backdrop").addEventListener("click", () => this.close());
    byId("save-card-detail").addEventListener("click", () => this.save());
    byId("archive-card-detail").addEventListener("click", () => this.archive());
    byId("comment-form").addEventListener("submit", (event) => this.addComment(event));
    byId("checklist-form").addEventListener("submit", (event) =>
      this.addChecklistItem(event),
    );
    byId("subtask-form").addEventListener("submit", (event) =>
      this.addSubtask(event),
    );
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !byId("card-drawer").hidden) this.close();
    });
  }

  canEdit() {
    return ["admin", "editor"].includes(
      this.state.snapshot?.board?.current_user_role,
    );
  }

  setEditable(editable) {
    for (const id of [
      "card-detail-title",
      "card-detail-description",
      "card-detail-assignee",
      "card-detail-priority",
      "card-detail-due",
      "card-detail-completed",
      "checklist-new-text",
      "comment-new-body",
      "subtask-new-title",
      "subtask-new-assignee",
      "subtask-new-due",
    ]) {
      const node = byId(id);
      if (node) node.disabled = !editable;
    }
    byId("save-card-detail").hidden = !editable;
    byId("archive-card-detail").hidden = !editable;
    byId("checklist-form").hidden = !editable;
    byId("comment-form").hidden = !editable;
    if (!this.card?.parent_card_id) byId("subtask-form").hidden = !editable;
  }

  populateUserSelect(select, selectedId = "") {
    select.replaceChildren(
      element("option", { text: "Не назначен", attrs: { value: "" } }),
    );
    for (const user of this.state.users) {
      select.append(
        element("option", {
          text: user.display_name,
          attrs: { value: user.id },
        }),
      );
    }
    select.value = selectedId || "";
  }

  async open(cardId) {
    this.bind();
    byId("card-drawer").hidden = false;
    byId("card-drawer-backdrop").hidden = false;
    document.body.classList.add("drawer-open");
    byId("card-detail-loading").hidden = false;
    byId("card-detail-content").hidden = true;
    byId("card-detail-error").hidden = true;
    try {
      await this.load(cardId);
    } catch (error) {
      byId("card-detail-loading").textContent = this.errorText(error);
    }
  }

  close() {
    byId("card-drawer").hidden = true;
    byId("card-drawer-backdrop").hidden = true;
    document.body.classList.remove("drawer-open");
    this.card = null;
  }

  async load(cardId = this.card?.id) {
    if (!cardId) return;
    this.card = await this.api.request(`/cards/${cardId}`);
    this.render();
  }

  render() {
    const card = this.card;
    if (!card) return;
    const column = this.state.snapshot?.columns.find((item) => item.id === card.column_id);
    byId("card-detail-loading").hidden = true;
    byId("card-detail-content").hidden = false;
    byId("card-detail-id").textContent = `Карточка ${card.id.slice(0, 8)}`;
    byId("card-detail-heading").textContent = card.title;
    byId("card-detail-title").value = card.title;
    byId("card-detail-description").value = card.description || "";
    byId("card-detail-priority").value = card.priority;
    byId("card-detail-due").value = toDateTimeLocal(card.due_date);
    byId("card-detail-column").value = column?.title || "—";
    byId("card-detail-completed").checked = Boolean(card.completed_at);
    this.populateUserSelect(byId("card-detail-assignee"), card.assignee_user_id);
    this.populateUserSelect(byId("subtask-new-assignee"));
    const mentionUsers = this.state.users.map((user) => `@${user.username}`).join(", ");
    byId("comment-mention-hint").textContent = mentionUsers || "нет доступных участников";
    byId("card-detail-meta").textContent = [
      `Автор: ${card.created_by.display_name}`,
      `изменено ${formatDateTime(card.updated_at)}`,
    ].join(" · ");
    byId("card-detail-error").hidden = true;
    this.renderSubtasks();
    this.renderChecklist();
    this.renderComments();
    this.setEditable(this.canEdit());
  }

  async refreshAfterMutation(message) {
    await this.reloadSnapshot();
    await this.load();
    if (message) showToast(message, "success");
  }

  async save() {
    const card = this.card;
    if (!card) return;
    const title = byId("card-detail-title").value.trim();
    const description = byId("card-detail-description").value.trim();
    const priority = byId("card-detail-priority").value;
    const dueInput = byId("card-detail-due").value;
    const assigneeId = byId("card-detail-assignee").value;
    const completed = byId("card-detail-completed").checked;
    const body = {
      expected_version: card.version,
      client_request_id: this.mutationId(),
    };
    if (title !== card.title) body.title = title;
    if (description !== (card.description || "")) {
      if (description) body.description = description;
      else body.clear_description = true;
    }
    if (priority !== card.priority) body.priority = priority;
    const currentDue = toDateTimeLocal(card.due_date);
    if (dueInput !== currentDue) {
      if (dueInput) body.due_date = new Date(dueInput).toISOString();
      else body.clear_due_date = true;
    }
    if (assigneeId !== (card.assignee_user_id || "")) {
      if (assigneeId) body.assignee_user_id = assigneeId;
      else body.clear_assignee = true;
    }
    if (completed !== Boolean(card.completed_at)) body.completed = completed;
    if (Object.keys(body).length === 2) {
      showToast("Изменений нет");
      return;
    }
    const saveButton = byId("save-card-detail");
    saveButton.disabled = true;
    byId("card-detail-error").hidden = true;
    try {
      await this.api.request(`/cards/${card.id}`, { method: "PATCH", body });
      await this.refreshAfterMutation("Карточка сохранена");
    } catch (error) {
      byId("card-detail-error").textContent = this.errorText(error);
      byId("card-detail-error").hidden = false;
      await this.handleMutationError(error);
      if (error?.status === 409) await this.load(card.id);
    } finally {
      saveButton.disabled = false;
    }
  }

  async archive() {
    const card = this.card;
    if (!card || !window.confirm(`Переместить карточку «${card.title}» в архив?`)) return;
    try {
      await this.api.request(`/cards/${card.id}`, {
        method: "DELETE",
        body: {
          expected_version: card.version,
          client_request_id: this.mutationId(),
        },
      });
      this.close();
      await this.reloadSnapshot();
      showToast("Карточка перемещена в архив", "success");
    } catch (error) {
      await this.handleMutationError(error);
    }
  }

  renderSubtasks() {
    const list = byId("subtasks-list");
    clear(list);
    const form = byId("subtask-form");
    if (this.card.parent_card_id) {
      byId("subtasks-progress").textContent = "";
      form.hidden = true;
      list.append(
        element("p", {
          className: "muted compact-empty",
          text: "Это подзадача. Дополнительный уровень вложенности не создаётся.",
        }),
      );
      return;
    }
    form.hidden = !this.canEdit();
    const subtasks = [...(this.card.subtasks || [])].sort((a, b) => a.position - b.position);
    const completed = subtasks.filter((item) => item.completed_at).length;
    byId("subtasks-progress").textContent = subtasks.length
      ? `${completed}/${subtasks.length}`
      : "";
    if (!subtasks.length) {
      list.append(
        element("p", { className: "muted compact-empty", text: "Подзадач пока нет." }),
      );
      return;
    }
    for (const subtask of subtasks) {
      const main = element("div", { className: "subtask-item__main" }, [
        element("span", {
          className: `subtask-status${subtask.completed_at ? " subtask-status--done" : ""}`,
          text: subtask.completed_at ? "✓" : "○",
        }),
        element("div", {}, [
          element("strong", { text: subtask.title }),
          element("span", {
            className: "muted subtask-item__meta",
            text: [
              subtask.assignee?.display_name || "Без ответственного",
              subtask.due_date ? formatDateTime(subtask.due_date) : null,
            ].filter(Boolean).join(" · "),
          }),
        ]),
      ]);
      const node = element("button", {
        className: "subtask-item",
        attrs: { type: "button" },
      }, [main, element("span", { className: "subtask-arrow", text: "›" })]);
      node.addEventListener("click", () => this.open(subtask.id));
      list.append(node);
    }
  }

  async addSubtask(event) {
    event.preventDefault();
    if (!this.card || this.card.parent_card_id || !this.canEdit()) return;
    const titleInput = byId("subtask-new-title");
    const title = titleInput.value.trim();
    if (!title) return;
    const dueInput = byId("subtask-new-due").value;
    const assigneeId = byId("subtask-new-assignee").value;
    const body = {
      column_id: this.card.column_id,
      parent_card_id: this.card.id,
      title,
      priority: this.card.priority,
      client_request_id: this.mutationId(),
    };
    if (dueInput) body.due_date = new Date(dueInput).toISOString();
    if (assigneeId) body.assignee_user_id = assigneeId;
    setBusy(event.currentTarget, true, "Добавление…");
    try {
      await this.api.request(`/boards/${this.card.board_id}/cards`, {
        method: "POST",
        body,
      });
      event.currentTarget.reset();
      this.populateUserSelect(byId("subtask-new-assignee"));
      await this.refreshAfterMutation("Подзадача добавлена");
    } catch (error) {
      await this.handleMutationError(error);
    } finally {
      setBusy(event.currentTarget, false);
    }
  }

  renderChecklist() {
    const list = byId("checklist-items");
    clear(list);
    const items = [...this.card.checklist_items].sort((a, b) => a.position - b.position);
    const completed = items.filter((item) => item.is_completed).length;
    byId("checklist-progress").textContent = items.length
      ? `${completed}/${items.length}`
      : "";
    if (!items.length) {
      list.append(
        element("p", { className: "muted compact-empty", text: "Пунктов пока нет." }),
      );
      return;
    }
    items.forEach((item, index) => {
      const checkbox = element("input", {
        attrs: { type: "checkbox", "aria-label": `Выполнение: ${item.text}` },
      });
      checkbox.checked = item.is_completed;
      checkbox.disabled = !this.canEdit();
      checkbox.addEventListener("change", async () => {
        checkbox.disabled = true;
        try {
          await this.api.request(`/checklist-items/${item.id}`, {
            method: "PATCH",
            body: {
              is_completed: checkbox.checked,
              expected_version: item.version,
              client_request_id: this.mutationId(),
            },
          });
          await this.refreshAfterMutation();
        } catch (error) {
          await this.handleMutationError(error);
          await this.load();
        }
      });
      const text = element("span", {
        className: `checklist-item__text${item.is_completed ? " is-completed" : ""}`,
        text: item.text,
      });
      const actions = element("div", { className: "checklist-item__actions" });
      if (this.canEdit()) actions.append(
        button("↑", "mini-button", () => this.moveChecklist(item, index - 1), "Выше"),
        button("↓", "mini-button", () => this.moveChecklist(item, index + 1), "Ниже"),
        button("✎", "mini-button", () => this.editChecklist(item), "Изменить"),
        button("×", "mini-button mini-button--danger", () => this.deleteChecklist(item), "Удалить"),
      );
      if (this.canEdit()) {
        actions.children[0].disabled = index === 0;
        actions.children[1].disabled = index === items.length - 1;
      }
      list.append(element("div", { className: "checklist-item" }, [checkbox, text, actions]));
    });
  }

  async addChecklistItem(event) {
    event.preventDefault();
    const input = byId("checklist-new-text");
    const text = input.value.trim();
    if (!text || !this.card) return;
    setBusy(event.currentTarget, true, "Добавление…");
    try {
      await this.api.request(`/cards/${this.card.id}/checklist-items`, {
        method: "POST",
        body: { text, client_request_id: this.mutationId() },
      });
      input.value = "";
      await this.refreshAfterMutation();
    } catch (error) {
      await this.handleMutationError(error);
    } finally {
      setBusy(event.currentTarget, false);
    }
  }

  async editChecklist(item) {
    const text = window.prompt("Текст пункта", item.text)?.trim();
    if (!text || text === item.text) return;
    try {
      await this.api.request(`/checklist-items/${item.id}`, {
        method: "PATCH",
        body: {
          text,
          expected_version: item.version,
          client_request_id: this.mutationId(),
        },
      });
      await this.refreshAfterMutation();
    } catch (error) {
      await this.handleMutationError(error);
      await this.load();
    }
  }

  async moveChecklist(item, targetIndex) {
    if (targetIndex < 0) return;
    try {
      await this.api.request(`/checklist-items/${item.id}/move`, {
        method: "POST",
        body: {
          target_index: targetIndex,
          expected_version: item.version,
          client_request_id: this.mutationId(),
        },
      });
      await this.refreshAfterMutation();
    } catch (error) {
      await this.handleMutationError(error);
      await this.load();
    }
  }

  async deleteChecklist(item) {
    if (!window.confirm(`Удалить пункт «${item.text}»?`)) return;
    try {
      await this.api.request(`/checklist-items/${item.id}`, {
        method: "DELETE",
        body: {
          expected_version: item.version,
          client_request_id: this.mutationId(),
        },
      });
      await this.refreshAfterMutation();
    } catch (error) {
      await this.handleMutationError(error);
      await this.load();
    }
  }

  renderComments() {
    const list = byId("comments-list");
    clear(list);
    const comments = [...this.card.comments].sort(
      (a, b) => new Date(a.created_at) - new Date(b.created_at),
    );
    byId("comments-count").textContent = comments.length ? String(comments.length) : "";
    if (!comments.length) {
      list.append(
        element("p", { className: "muted compact-empty", text: "Комментариев пока нет." }),
      );
      return;
    }
    for (const comment of comments) {
      const avatar = element("span", {
        className: "avatar avatar--comment",
        text: initials(comment.author.display_name),
        title: comment.author.display_name,
      });
      const header = element("div", { className: "comment__header" }, [
        element("strong", { text: comment.author.display_name }),
        element("span", {
          className: "comment__time",
          text: `${formatDateTime(comment.created_at)}${comment.edited_at ? " · изменено" : ""}`,
        }),
      ]);
      const body = element("p", { className: "comment__body", text: comment.body });
      const content = element("div", { className: "comment__content" }, [header, body]);
      if (this.canEdit() && comment.author_user_id === this.state.user.id) {
        content.append(
          element("div", { className: "comment__actions" }, [
            button("Изменить", "text-button", () => this.editComment(comment)),
            button("Удалить", "text-button text-button--danger", () =>
              this.deleteComment(comment),
            ),
          ]),
        );
      }
      list.append(element("article", { className: "comment" }, [avatar, content]));
    }
  }

  async addComment(event) {
    event.preventDefault();
    const input = byId("comment-new-body");
    const body = input.value.trim();
    if (!body || !this.card) return;
    setBusy(event.currentTarget, true, "Отправка…");
    try {
      await this.api.request(`/cards/${this.card.id}/comments`, {
        method: "POST",
        body: { body, client_request_id: this.mutationId() },
      });
      input.value = "";
      await this.refreshAfterMutation();
    } catch (error) {
      await this.handleMutationError(error);
    } finally {
      setBusy(event.currentTarget, false);
    }
  }

  async editComment(comment) {
    const body = window.prompt("Комментарий", comment.body)?.trim();
    if (!body || body === comment.body) return;
    try {
      await this.api.request(`/comments/${comment.id}`, {
        method: "PATCH",
        body: {
          body,
          expected_version: comment.version,
          client_request_id: this.mutationId(),
        },
      });
      await this.refreshAfterMutation();
    } catch (error) {
      await this.handleMutationError(error);
      await this.load();
    }
  }

  async deleteComment(comment) {
    if (!window.confirm("Удалить комментарий?")) return;
    try {
      await this.api.request(`/comments/${comment.id}`, {
        method: "DELETE",
        body: {
          expected_version: comment.version,
          client_request_id: this.mutationId(),
        },
      });
      await this.refreshAfterMutation();
    } catch (error) {
      await this.handleMutationError(error);
      await this.load();
    }
  }
}

export { initials };
