import {
  button,
  clear,
  closeDialog,
  element,
  formatDateTime,
  openDialog,
  setBusy,
  showToast,
} from "./ui.js";

const byId = (id) => document.getElementById(id);
const roleLabels = {
  owner: "Владелец",
  admin: "Администратор",
  member: "Участник",
};
const boardRoleLabels = {
  admin: "Администратор",
  editor: "Редактор",
  viewer: "Наблюдатель",
};

function setError(id, error) {
  const node = byId(id);
  node.textContent = error?.message || "Неизвестная ошибка";
  node.hidden = false;
}

function clearError(id) {
  const node = byId(id);
  node.textContent = "";
  node.hidden = true;
}

async function copyText(value) {
  await navigator.clipboard.writeText(value);
  showToast("Ссылка скопирована", "success");
}

export class TeamController {
  constructor({ api, state, openBoard, openCard, showLogin, openPasswordDialog }) {
    this.api = api;
    this.state = state;
    this.openBoard = openBoard;
    this.openCard = openCard;
    this.showLogin = showLogin;
    this.openPasswordDialog = openPasswordDialog;
    this.inviteToken = null;
    this.resetToken = null;
    this.notificationTimer = null;
  }

  bind() {
    byId("forgot-password-button").addEventListener("click", () => {
      byId("forgot-password-form").reset();
      byId("forgot-password-message").hidden = true;
      clearError("forgot-password-error");
      openDialog(byId("forgot-password-dialog"));
    });
    byId("forgot-password-form").addEventListener("submit", (event) =>
      this.submitForgotPassword(event),
    );
    byId("invite-accept-form").addEventListener("submit", (event) =>
      this.acceptInvitation(event),
    );
    byId("reset-password-form").addEventListener("submit", (event) =>
      this.confirmReset(event),
    );
    byId("profile-button").addEventListener("click", () => this.openProfile());
    byId("profile-form").addEventListener("submit", (event) => this.saveProfile(event));
    byId("profile-change-password").addEventListener("click", () => {
      closeDialog(byId("profile-dialog"));
      this.openPasswordDialog();
    });
    byId("participants-button").addEventListener("click", () => this.openParticipants());
    byId("refresh-participants").addEventListener("click", () => this.loadParticipants());
    byId("admin-invite-form").addEventListener("submit", (event) =>
      this.createInvitation(event),
    );
    byId("copy-invite-url").addEventListener("click", () =>
      copyText(byId("invite-result-url").value),
    );
    byId("board-members-button").addEventListener("click", () => this.openBoardMembers());
    byId("notifications-button").addEventListener("click", () => this.openNotifications());
    byId("close-notifications").addEventListener("click", () => this.closeNotifications());
    byId("notifications-backdrop").addEventListener("click", () => this.closeNotifications());
    byId("mark-all-notifications").addEventListener("click", () => this.markAllRead());
  }

  async initializePublicFlow() {
    const url = new URL(window.location.href);
    const inviteToken = url.searchParams.get("invite");
    const resetToken = url.searchParams.get("reset-password");
    if (inviteToken) {
      this.inviteToken = inviteToken;
      try {
        const preview = await this.api.request(
          `/auth/invitations/${encodeURIComponent(inviteToken)}`,
          { auth: false },
        );
        byId("invite-preview").textContent = `${preview.display_name}, приглашение отправлено на ${preview.email}. Ссылка действует до ${formatDateTime(preview.expires_at)}.`;
        byId("invite-display-name").value = preview.display_name;
        byId("invite-username").value = this.suggestUsername(preview.email);
        clearError("invite-error");
        openDialog(byId("invite-dialog"));
      } catch (error) {
        showToast(error.message, "error", 10_000);
      }
    } else if (resetToken) {
      this.resetToken = resetToken;
      byId("reset-password-form").reset();
      clearError("reset-password-error");
      openDialog(byId("reset-password-dialog"));
    }
  }

  clearAuthQuery() {
    const url = new URL(window.location.href);
    url.searchParams.delete("invite");
    url.searchParams.delete("reset-password");
    window.history.replaceState({}, "", url);
  }

  suggestUsername(email) {
    const value = String(email || "").split("@")[0].toLowerCase().replace(/[^a-z0-9._-]+/g, "-");
    return value.length >= 3 ? value.slice(0, 80) : "user";
  }

  async acceptInvitation(event) {
    event.preventDefault();
    if (event.submitter?.value === "cancel") return;
    clearError("invite-error");
    const password = byId("invite-password").value;
    if (password !== byId("invite-password-repeat").value) {
      setError("invite-error", new Error("Пароли не совпадают"));
      return;
    }
    setBusy(event.currentTarget, true, "Создание…");
    try {
      const result = await this.api.request("/auth/invitations/accept", {
        method: "POST",
        auth: false,
        body: {
          token: this.inviteToken,
          username: byId("invite-username").value.trim(),
          display_name: byId("invite-display-name").value.trim(),
          password,
        },
      });
      closeDialog(byId("invite-dialog"));
      this.clearAuthQuery();
      this.showLogin(result.message, false);
    } catch (error) {
      setError("invite-error", error);
    } finally {
      setBusy(event.currentTarget, false);
    }
  }

  async submitForgotPassword(event) {
    event.preventDefault();
    if (event.submitter?.value === "cancel") return;
    clearError("forgot-password-error");
    setBusy(event.currentTarget, true, "Отправка…");
    try {
      const result = await this.api.request("/auth/password-reset/request", {
        method: "POST",
        auth: false,
        body: { email: byId("forgot-password-email").value.trim() },
      });
      byId("forgot-password-message").textContent = result.message;
      byId("forgot-password-message").hidden = false;
    } catch (error) {
      setError("forgot-password-error", error);
    } finally {
      setBusy(event.currentTarget, false);
    }
  }

  async confirmReset(event) {
    event.preventDefault();
    if (event.submitter?.value === "cancel") return;
    clearError("reset-password-error");
    const password = byId("reset-password-new").value;
    if (password !== byId("reset-password-repeat").value) {
      setError("reset-password-error", new Error("Пароли не совпадают"));
      return;
    }
    setBusy(event.currentTarget, true, "Сохранение…");
    try {
      const result = await this.api.request("/auth/password-reset/confirm", {
        method: "POST",
        auth: false,
        body: { token: this.resetToken, new_password: password },
      });
      closeDialog(byId("reset-password-dialog"));
      this.clearAuthQuery();
      this.showLogin(result.message);
    } catch (error) {
      setError("reset-password-error", error);
    } finally {
      setBusy(event.currentTarget, false);
    }
  }

  async afterLogin() {
    const user = this.state.user;
    byId("profile-button").textContent = user.display_name;
    byId("participants-button").hidden = !["owner", "admin"].includes(user.role);
    this.updateBoardAccessButtons();
    await this.refreshNotificationCount();
    window.clearInterval(this.notificationTimer);
    this.notificationTimer = window.setInterval(() => {
      if (!document.hidden && this.state.user) this.refreshNotificationCount().catch(() => {});
    }, 20_000);
  }

  loggedOut() {
    window.clearInterval(this.notificationTimer);
    this.notificationTimer = null;
    this.closeNotifications();
  }

  updateBoardAccessButtons() {
    const role = this.state.snapshot?.board?.current_user_role;
    byId("board-members-button").hidden = !role;
  }

  openProfile() {
    const user = this.state.user;
    byId("profile-display-name").value = user.display_name;
    byId("profile-email").textContent = user.email || "Не указан";
    byId("profile-username").textContent = user.username;
    byId("profile-role").textContent = roleLabels[user.role] || user.role;
    const settings = user.notification_settings || {};
    byId("profile-notify-assignment").checked = settings.assignment !== false;
    byId("profile-notify-mention").checked = settings.mention !== false;
    byId("profile-notify-due").checked = settings.due_date === true;
    clearError("profile-error");
    openDialog(byId("profile-dialog"));
  }

  async saveProfile(event) {
    event.preventDefault();
    if (event.submitter?.value === "cancel") return;
    clearError("profile-error");
    setBusy(event.currentTarget, true);
    try {
      const user = await this.api.request("/profile", {
        method: "PATCH",
        body: {
          display_name: byId("profile-display-name").value.trim(),
          notification_settings: {
            assignment: byId("profile-notify-assignment").checked,
            mention: byId("profile-notify-mention").checked,
            due_date: byId("profile-notify-due").checked,
          },
        },
      });
      this.state.user = user;
      byId("profile-button").textContent = user.display_name;
      closeDialog(byId("profile-dialog"));
      showToast("Профиль сохранён", "success");
    } catch (error) {
      if (error.code === "NO_CHANGES") closeDialog(byId("profile-dialog"));
      else setError("profile-error", error);
    } finally {
      setBusy(event.currentTarget, false);
    }
  }

  async openParticipants() {
    byId("invite-result").hidden = true;
    openDialog(byId("participants-dialog"));
    await this.loadParticipants();
  }

  async loadParticipants() {
    const [users, invitations, boards] = await Promise.all([
      this.api.request("/admin/users"),
      this.api.request("/admin/invitations"),
      this.api.request("/boards?archived=false"),
    ]);
    this.renderParticipants(users.items);
    this.renderInvitations(invitations.items);
    this.renderInviteBoards(boards.items);
  }

  renderParticipants(users) {
    const list = byId("participants-list");
    clear(list);
    for (const user of users) {
      const role = element("select", { attrs: { "aria-label": `Роль ${user.display_name}` } });
      for (const value of ["owner", "admin", "member"]) {
        const option = element("option", { text: roleLabels[value], attrs: { value } });
        option.selected = user.role === value;
        if (value === "owner" && this.state.user.role !== "owner") option.disabled = true;
        role.append(option);
      }
      role.disabled = user.role === "owner" && this.state.user.role !== "owner";
      role.addEventListener("change", () => this.updateParticipant(user, { role: role.value }));
      const status = button(
        user.is_active ? "Отключить" : "Включить",
        user.is_active ? "button button--danger button--compact" : "button button--secondary button--compact",
        () => this.updateParticipant(user, { is_active: !user.is_active }),
      );
      status.disabled = user.id === this.state.user.id || user.role === "owner";
      const reset = button("Ссылка сброса", "button button--ghost button--compact", () => this.createResetLink(user));
      const edit = button("Изменить", "button button--ghost button--compact", () => this.editParticipant(user));
      list.append(
        element("article", { className: "admin-row" }, [
          element("div", { className: "admin-row__main" }, [
            element("strong", { text: user.display_name }),
            element("span", { className: "muted", text: `${user.email || "email не указан"} · @${user.username}` }),
            element("span", { className: `status-chip ${user.is_active ? "status-chip--active" : "status-chip--disabled"}`, text: user.is_active ? "Активен" : "Отключён" }),
          ]),
          element("div", { className: "admin-row__actions" }, [role, edit, reset, status]),
        ]),
      );
    }
  }

  async updateParticipant(user, body) {
    try {
      await this.api.request(`/admin/users/${user.id}`, { method: "PATCH", body });
      await this.loadParticipants();
      showToast("Пользователь обновлён", "success");
    } catch (error) {
      showToast(error.message, "error");
      await this.loadParticipants();
    }
  }

  async editParticipant(user) {
    const name = window.prompt("Имя участника", user.display_name);
    if (!name) return;
    const email = window.prompt("Email (оставьте пустым, чтобы удалить)", user.email || "");
    const body = { display_name: name.trim() };
    if (email?.trim()) body.email = email.trim();
    else body.clear_email = true;
    await this.updateParticipant(user, body);
  }

  async createResetLink(user) {
    try {
      const result = await this.api.request(`/admin/users/${user.id}/password-reset-link`, { method: "POST" });
      await copyText(result.reset_url);
      showToast(`Ссылка действует до ${formatDateTime(result.expires_at)}`, "success", 8_000);
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  renderInviteBoards(boards) {
    const list = byId("admin-invite-boards");
    clear(list);
    if (!boards.length) {
      list.append(element("p", { className: "muted", text: "Активных досок нет" }));
      return;
    }
    for (const board of boards) {
      const checkbox = element("input", { attrs: { type: "checkbox", value: board.id } });
      const role = element("select", { attrs: { "aria-label": `Роль на доске ${board.title}` } });
      for (const value of ["editor", "viewer", "admin"]) {
        role.append(element("option", { text: boardRoleLabels[value], attrs: { value } }));
      }
      list.append(element("div", { className: "board-access-row", dataset: { boardId: board.id } }, [
        element("label", { className: "checkbox-line" }, [checkbox, element("span", { text: board.title })]),
        role,
      ]));
    }
  }

  async createInvitation(event) {
    event.preventDefault();
    clearError("admin-invite-error");
    const boardAccess = [...byId("admin-invite-boards").querySelectorAll(".board-access-row")]
      .filter((row) => row.querySelector('input[type="checkbox"]').checked)
      .map((row) => ({ board_id: row.dataset.boardId, role: row.querySelector("select").value }));
    setBusy(event.currentTarget, true, "Создание…");
    try {
      const result = await this.api.request("/admin/invitations", {
        method: "POST",
        body: {
          email: byId("admin-invite-email").value.trim(),
          display_name: byId("admin-invite-name").value.trim(),
          system_role: byId("admin-invite-role").value,
          board_access: boardAccess,
          send_email: byId("admin-invite-send-email").checked,
        },
      });
      byId("invite-result-url").value = result.invite_url;
      byId("invite-result").hidden = false;
      event.currentTarget.reset();
      await this.loadParticipants();
      showToast(result.email_status === "sent" ? "Приглашение отправлено" : "Приглашение создано; используйте ссылку", "success");
    } catch (error) {
      setError("admin-invite-error", error);
    } finally {
      setBusy(event.currentTarget, false);
    }
  }

  renderInvitations(items) {
    const list = byId("invitations-list");
    clear(list);
    if (!items.length) {
      list.append(element("p", { className: "muted", text: "Приглашений пока нет" }));
      return;
    }
    for (const item of items) {
      const status = item.accepted_at
        ? "Принято"
        : item.revoked_at
          ? "Отозвано"
          : new Date(item.expires_at) < new Date()
            ? "Истекло"
            : item.email_status === "sent"
              ? "Отправлено"
              : item.email_status === "failed"
                ? "Ошибка email"
                : "Создано";
      const actions = element("div", { className: "admin-row__actions" });
      if (!item.accepted_at && !item.revoked_at) {
        actions.append(
          button("Новая ссылка", "button button--ghost button--compact", async () => {
            const result = await this.api.request(`/admin/invitations/${item.id}/resend`, { method: "POST" });
            await copyText(result.invite_url);
            await this.loadParticipants();
          }),
          button("Отозвать", "button button--danger button--compact", async () => {
            await this.api.request(`/admin/invitations/${item.id}`, { method: "DELETE" });
            await this.loadParticipants();
          }),
        );
      }
      list.append(element("article", { className: "admin-row" }, [
        element("div", { className: "admin-row__main" }, [
          element("strong", { text: item.display_name }),
          element("span", { className: "muted", text: item.email }),
          element("span", { className: "status-chip", text: `${status} · до ${formatDateTime(item.expires_at)}` }),
        ]),
        actions,
      ]));
    }
  }

  async openBoardMembers() {
    if (!this.state.currentBoardId) return;
    openDialog(byId("board-members-dialog"));
    const [members, users] = await Promise.all([
      this.api.request(`/boards/${this.state.currentBoardId}/members`),
      this.api.request("/users?active_only=true"),
    ]);
    this.renderBoardMembers(members.items, users.items);
  }

  renderBoardMembers(members, users) {
    const list = byId("board-members-list");
    clear(list);
    const byUser = new Map(members.map((item) => [item.user_id, item]));
    const canManage = this.state.snapshot?.board?.current_user_role === "admin";
    for (const user of users) {
      const current = byUser.get(user.id);
      const select = element("select", { attrs: { "aria-label": `Доступ ${user.display_name}` } });
      select.append(element("option", { text: "Нет доступа", attrs: { value: "" } }));
      for (const value of ["viewer", "editor", "admin"]) {
        select.append(element("option", { text: boardRoleLabels[value], attrs: { value } }));
      }
      select.value = current?.role || "";
      select.disabled = !canManage;
      select.addEventListener("change", async () => {
        try {
          if (select.value) {
            await this.api.request(`/boards/${this.state.currentBoardId}/members/${user.id}`, {
              method: "PUT",
              body: { role: select.value },
            });
          } else {
            await this.api.request(`/boards/${this.state.currentBoardId}/members/${user.id}`, { method: "DELETE" });
          }
          showToast("Доступ обновлён", "success");
          await this.openBoardMembers();
        } catch (error) {
          showToast(error.message, "error");
          await this.openBoardMembers();
        }
      });
      list.append(element("article", { className: "admin-row" }, [
        element("div", { className: "admin-row__main" }, [
          element("strong", { text: user.display_name }),
          element("span", { className: "muted", text: `${user.email || "email не указан"} · @${user.username}` }),
        ]),
        select,
      ]));
    }
  }

  async refreshNotificationCount() {
    if (!this.state.user) return;
    const result = await this.api.request("/notifications/unread-count");
    const badge = byId("notification-badge");
    badge.textContent = String(result.unread_count);
    badge.hidden = result.unread_count < 1;
  }

  async openNotifications() {
    byId("notifications-drawer").hidden = false;
    byId("notifications-backdrop").hidden = false;
    document.body.classList.add("drawer-open");
    const result = await this.api.request("/notifications?limit=100");
    this.renderNotifications(result.items);
    const badge = byId("notification-badge");
    badge.textContent = String(result.unread_count);
    badge.hidden = result.unread_count < 1;
  }

  closeNotifications() {
    byId("notifications-drawer").hidden = true;
    byId("notifications-backdrop").hidden = true;
    if (byId("card-drawer")?.hidden) document.body.classList.remove("drawer-open");
  }

  renderNotifications(items) {
    const list = byId("notifications-list");
    clear(list);
    if (!items.length) {
      list.append(element("div", { className: "empty-state", text: "Новых событий нет" }));
      return;
    }
    for (const item of items) {
      const node = element("article", { className: `notification-item${item.read_at ? "" : " notification-item--unread"}` }, [
        element("strong", { text: item.title }),
        element("p", { text: item.message }),
        element("span", { className: "muted", text: formatDateTime(item.created_at) }),
      ]);
      node.addEventListener("click", async () => {
        if (!item.read_at) await this.api.request(`/notifications/${item.id}/read`, { method: "POST" });
        this.closeNotifications();
        if (item.board_id) await this.openBoard(item.board_id);
        if (item.card_id) await this.openCard(item.card_id);
        await this.refreshNotificationCount();
      });
      list.append(node);
    }
  }

  async markAllRead() {
    await this.api.request("/notifications/read-all", { method: "POST" });
    await this.openNotifications();
    await this.refreshNotificationCount();
  }
}
