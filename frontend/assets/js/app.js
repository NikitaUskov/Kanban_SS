import { ApiClient, ApiError } from "./api.js";
import {
  EXPECTED_API_VERSION,
  FRONTEND_VERSION,
  RuntimeConfigStore,
} from "./config.js";
import {
  PRIORITIES,
  filterCards,
  hasActiveFilters,
  isOverdue,
  pollingDelay,
  resetFilters,
  shouldDeferRevision,
  state,
} from "./state.js";
import {
  button,
  clear,
  closeDialog,
  element,
  formatDateTime,
  openDialog,
  setBusy,
  setConnectionState,
  setHidden,
  showToast,
  toDateTimeLocal,
} from "./ui.js";

const byId = (id) => document.getElementById(id);
const configStore = new RuntimeConfigStore();
let healthInfo = null;
let pollTimer = null;
let recoveryTimer = null;
let dragContext = null;
let dropInProgress = false;

const api = new ApiClient(configStore, {
  onConnected: () => {
    state.connection = "connected";
    setConnectionState("connected", "Подключено");
  },
  onUnavailable: () => {
    state.connection = "offline";
    setConnectionState("offline", "Сервер недоступен. Выполняется переподключение");
    startRecoveryLoop();
  },
  onUnauthorized: () => showLogin("Сессия завершена. Войдите повторно"),
});

function mutationId() {
  return crypto.randomUUID();
}

function errorText(error) {
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} (request_id: ${error.requestId})` : error.message;
  }
  return error?.message || "Неизвестная ошибка";
}

function showFormError(id, error) {
  const node = byId(id);
  node.textContent = errorText(error);
  node.hidden = false;
}

function clearFormError(id) {
  const node = byId(id);
  node.textContent = "";
  node.hidden = true;
}

async function handleMutationError(error) {
  const conflictCodes = new Set([
    "BOARD_VERSION_CONFLICT",
    "COLUMN_VERSION_CONFLICT",
    "CARD_VERSION_CONFLICT",
    "COLUMN_ORDER_CONFLICT",
  ]);
  if (error instanceof ApiError && conflictCodes.has(error.code)) {
    showToast(`${error.message}. Загружено актуальное состояние`, "error");
    if (state.currentBoardId) await loadSnapshot();
    return;
  }
  showToast(errorText(error), "error");
}

async function checkCompatibility() {
  healthInfo = await api.request("/health", { auth: false });
  const compatible = healthInfo.apiVersion === EXPECTED_API_VERSION;
  state.compatible = compatible;
  api.setCompatible(compatible);
  byId("about-frontend-version").textContent = FRONTEND_VERSION;
  byId("about-backend-version").textContent = healthInfo.appVersion;
  byId("about-api-version").textContent = healthInfo.apiVersion;
  byId("about-config-version").textContent = String(
    configStore.current?.configVersion || "—",
  );
  if (!compatible) {
    showToast(
      `Несовместимые версии API: интерфейс ожидает ${EXPECTED_API_VERSION}, сервер вернул ${healthInfo.apiVersion}`,
      "error",
      12_000,
    );
  } else if (
    configStore.current?.appVersion &&
    configStore.current.appVersion !== FRONTEND_VERSION
  ) {
    showToast("GitHub Pages публикует новую версию интерфейса. Мутации доступны по API v1");
  }
}

function startRecoveryLoop() {
  if (recoveryTimer) return;
  recoveryTimer = window.setInterval(async () => {
    try {
      await configStore.load();
      await checkCompatibility();
      if (!state.user && (api.tokens.accessToken || api.tokens.refreshToken)) {
        if (!api.tokens.accessToken) await api.refresh();
        const user = await api.request("/auth/me");
        await enterApplication(user);
      } else if (state.user) {
        if (state.currentBoardId) await loadSnapshot();
        else await loadBoards();
      }
      window.clearInterval(recoveryTimer);
      recoveryTimer = null;
    } catch {
      setConnectionState("starting", "Сервер запускается. Следующая попытка через 15 секунд");
    }
  }, 15_000);
}

async function onRuntimeConfigChanged(next) {
  state.connection = "changed";
  setConnectionState(
    "changed",
    `Туннель сменился. Подключение к конфигурации ${next.configVersion}`,
  );
  byId("about-config-version").textContent = String(next.configVersion);
  try {
    await checkCompatibility();
    if (state.user) {
      if (state.currentBoardId) await loadSnapshot();
      else await loadBoards();
    }
    showToast("Подключение переключено на новый адрес сервера", "success");
  } catch {
    startRecoveryLoop();
  }
}

function showLogin(message = "", clearTokens = true) {
  if (clearTokens) api.tokens.clear();
  state.user = null;
  state.currentBoardId = null;
  state.snapshot = null;
  stopPolling();
  setHidden("app-shell", true);
  setHidden("login-view", false);
  const error = byId("login-error");
  error.textContent = message;
  error.hidden = !message;
  byId("login-password").value = "";
  byId("login-username").focus();
}

function openPasswordDialog() {
  const form = byId("password-form");
  form.reset();
  clearFormError("password-form-error");
  openDialog(byId("password-dialog"));
}

async function submitPasswordForm(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    closeDialog(byId("password-dialog"));
    return;
  }
  const form = event.currentTarget;
  const currentPassword = byId("password-current").value;
  const newPassword = byId("password-new").value;
  const repeatedPassword = byId("password-repeat").value;
  clearFormError("password-form-error");
  if (newPassword !== repeatedPassword) {
    showFormError("password-form-error", new Error("Новые пароли не совпадают"));
    return;
  }
  setBusy(form, true, "Смена пароля…");
  try {
    await api.request("/auth/change-password", {
      method: "POST",
      body: {
        current_password: currentPassword,
        new_password: newPassword,
      },
    });
    api.tokens.clear();
    closeDialog(byId("password-dialog"));
    showLogin("Пароль изменён. Войдите с новым паролем");
  } catch (error) {
    showFormError("password-form-error", error);
  } finally {
    setBusy(form, false);
  }
}

async function enterApplication(user) {
  state.user = user;
  byId("current-user").textContent = user.display_name;
  setHidden("login-view", true);
  setHidden("app-shell", false);
  api.scheduleRefresh();
  showBoardsView();
  await loadBoards();
}

function showBoardsView() {
  stopPolling();
  state.currentBoardId = null;
  state.snapshot = null;
  setHidden("board-view", true);
  setHidden("boards-view", false);
}

async function loadBoards() {
  byId("boards-loading").hidden = false;
  try {
    const data = await api.request(`/boards?archived=${state.archivedBoards}`);
    state.boards = data.items;
    renderBoards();
  } finally {
    byId("boards-loading").hidden = true;
  }
}

function renderBoards() {
  const grid = byId("boards-grid");
  clear(grid);
  byId("boards-title").textContent = state.archivedBoards ? "Архив досок" : "Все доски";
  byId("toggle-board-archive").textContent = state.archivedBoards
    ? "Вернуться к активным"
    : "Показать архив";
  byId("create-board-button").hidden = state.archivedBoards;
  if (!state.boards.length) {
    grid.append(
      element("div", {
        className: "empty-state",
        text: state.archivedBoards
          ? "Архив досок пуст."
          : "Досок пока нет. Создайте первую доску.",
      }),
    );
    return;
  }
  for (const board of state.boards) {
    const title = element("h2", { text: board.title });
    const description = element("p", {
      className: "board-card__description",
      text: board.description || "Без описания",
    });
    const meta = element("div", { className: "board-card__meta" }, [
      element("span", { text: `${board.column_count} колонок` }),
      element("span", { text: `${board.active_card_count} карточек` }),
      element("span", { text: `Обновлено ${formatDateTime(board.updated_at)}` }),
    ]);
    const actions = element("div", { className: "board-card__actions" });
    if (state.archivedBoards) {
      actions.append(
        button("Восстановить", "button button--primary", async () => {
          if (!window.confirm(`Восстановить доску «${board.title}»?`)) return;
          try {
            await api.request(`/boards/${board.id}/restore`, {
              method: "POST",
              body: {
                expected_version: board.version,
                client_request_id: mutationId(),
              },
            });
            await loadBoards();
            showToast("Доска восстановлена", "success");
          } catch (error) {
            await handleMutationError(error);
          }
        }),
      );
    } else {
      actions.append(
        button("Открыть", "button button--primary", () => openBoard(board.id)),
        button("Настройки", "button button--secondary", () => openBoardEditor(board)),
      );
    }
    grid.append(
      element("article", { className: "board-card" }, [title, description, meta, actions]),
    );
  }
}

async function openBoard(boardId) {
  state.currentBoardId = boardId;
  resetFilters();
  syncFilterInputs();
  setHidden("boards-view", true);
  setHidden("board-view", false);
  byId("board-columns").replaceChildren(
    element("div", { className: "empty-state", text: "Загрузка доски…" }),
  );
  try {
    await loadSnapshot();
    startPolling();
  } catch (error) {
    showToast(errorText(error), "error");
    showBoardsView();
  }
}

async function loadSnapshot(includeArchived = false) {
  if (!state.currentBoardId) return null;
  const snapshot = await api.request(
    `/boards/${state.currentBoardId}/snapshot?include_archived=${includeArchived}`,
  );
  if (!includeArchived) {
    state.snapshot = snapshot;
    renderBoard();
  }
  return snapshot;
}

function syncFilterInputs() {
  byId("filter-query").value = state.filters.query;
  byId("filter-priority").value = state.filters.priority;
  byId("filter-column").value = state.filters.columnId;
  byId("filter-due").value = state.filters.due;
  byId("filter-user").value = state.filters.updatedBy;
}

function rebuildFilterOptions() {
  const snapshot = state.snapshot;
  const columnSelect = byId("filter-column");
  const currentColumn = state.filters.columnId;
  columnSelect.replaceChildren(element("option", { text: "Все", attrs: { value: "" } }));
  for (const column of snapshot.columns) {
    columnSelect.append(
      element("option", { text: column.title, attrs: { value: column.id } }),
    );
  }
  columnSelect.value = currentColumn;

  const users = new Map();
  for (const card of snapshot.cards) {
    users.set(card.updated_by.id, card.updated_by.display_name);
  }
  const userSelect = byId("filter-user");
  const currentUser = state.filters.updatedBy;
  userSelect.replaceChildren(
    element("option", { text: "Все пользователи", attrs: { value: "" } }),
  );
  for (const [id, name] of [...users.entries()].sort((a, b) =>
    a[1].localeCompare(b[1], "ru"),
  )) {
    userSelect.append(element("option", { text: name, attrs: { value: id } }));
  }
  userSelect.value = currentUser;
}

function renderBoard() {
  const snapshot = state.snapshot;
  if (!snapshot) return;
  byId("board-title").textContent = snapshot.board.title;
  byId("board-description").textContent = snapshot.board.description || "Без описания";
  rebuildFilterOptions();
  syncFilterInputs();
  renderColumns();
}

function renderColumns() {
  const snapshot = state.snapshot;
  if (!snapshot) return;
  const container = byId("board-columns");
  clear(container);
  const filtered = filterCards(
    snapshot.cards,
    state.filters,
    snapshot.columns,
    new Date(snapshot.server_time),
  );
  const filtering = hasActiveFilters();
  byId("drag-filter-note").hidden = !filtering;
  const sortedColumns = [...snapshot.columns].sort((a, b) => a.position - b.position);
  if (!sortedColumns.length) {
    container.append(
      element("div", {
        className: "empty-state",
        text: "На доске нет колонок. Добавьте первую колонку.",
      }),
    );
    return;
  }
  for (const column of sortedColumns) {
    const allCards = snapshot.cards
      .filter((card) => !card.archived_at && card.column_id === column.id)
      .sort((a, b) => a.position - b.position);
    const cards = filtered
      .filter((card) => card.column_id === column.id)
      .sort((a, b) => a.position - b.position);
    const header = element("div", {
      className: "column-header",
      attrs: { draggable: filtering ? "false" : "true" },
      dataset: { columnId: column.id },
    });
    header.append(
      element("h2", { className: "column-title", text: column.title }),
      element("span", { className: "column-count", text: allCards.length }),
    );
    if (column.wip_limit) {
      header.append(
        element("span", {
          className: `wip-badge${allCards.length >= column.wip_limit ? " wip-badge--full" : ""}`,
          text: `WIP ${allCards.length}/${column.wip_limit}`,
          title: "Ограничение количества активных карточек",
        }),
      );
    }
    header.append(
      button("•••", "column-menu", () => openColumnEditor(column), "Настройки колонки"),
    );
    if (!filtering) {
      header.addEventListener("dragstart", (event) => startColumnDrag(event, column.id));
      header.addEventListener("dragend", finishDrag);
    }

    const list = element("div", {
      className: "card-list",
      dataset: { columnId: column.id },
    });
    for (const card of cards) list.append(renderCard(card, filtering));
    list.addEventListener("dragover", (event) => {
      if (dragContext?.kind !== "card") return;
      event.preventDefault();
      list.closest(".kanban-column")?.classList.add("kanban-column--drop");
    });
    list.addEventListener("dragleave", () =>
      list.closest(".kanban-column")?.classList.remove("kanban-column--drop"),
    );
    list.addEventListener("drop", (event) => dropCard(event, column.id, list));

    const addButton = button(
      "Добавить карточку",
      "button add-card-button",
      () => openCardEditor(null, column.id),
      `Добавить карточку в колонку ${column.title}`,
    );
    const columnNode = element(
      "section",
      { className: "kanban-column", dataset: { columnId: column.id } },
      [header, list, addButton],
    );
    container.append(columnNode);
  }
}

function renderCard(card, filtering) {
  const snapshot = state.snapshot;
  const overdue = isOverdue(card, snapshot.columns, new Date(snapshot.server_time));
  const node = element("article", {
    className: "kanban-card",
    attrs: {
      draggable: filtering ? "false" : "true",
      tabindex: "0",
      role: "button",
      "aria-label": `Открыть карточку ${card.title}`,
    },
    dataset: { cardId: card.id, priority: card.priority },
  });
  node.append(element("h3", { className: "kanban-card__title", text: card.title }));
  if (card.description) {
    node.append(
      element("p", { className: "kanban-card__description", text: card.description }),
    );
  }
  const meta = element("div", { className: "kanban-card__meta" }, [
    element("span", {
      className: "priority-label",
      text: PRIORITIES[card.priority] || card.priority,
    }),
  ]);
  if (card.due_date) {
    meta.append(
      element("span", {
        className: `due-label${overdue ? " due-label--overdue" : ""}`,
        text: `${overdue ? "Просрочено: " : "Срок: "}${formatDateTime(card.due_date)}`,
      }),
    );
  }
  meta.append(element("span", { text: `Изменил: ${card.updated_by.display_name}` }));
  node.append(meta);
  node.addEventListener("click", () => {
    if (!state.dragging) openCardEditor(card);
  });
  node.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openCardEditor(card);
    }
  });
  if (!filtering) {
    node.addEventListener("dragstart", (event) => startCardDrag(event, card.id));
    node.addEventListener("dragend", finishDrag);
  }
  return node;
}

function startCardDrag(event, cardId) {
  dragContext = { kind: "card", id: cardId };
  state.dragging = true;
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", `card:${cardId}`);
}

function startColumnDrag(event, columnId) {
  if (event.target.closest(".column-menu")) {
    event.preventDefault();
    return;
  }
  dragContext = { kind: "column", id: columnId };
  state.dragging = true;
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", `column:${columnId}`);
}

function finishDrag() {
  document
    .querySelectorAll(".kanban-column--drop")
    .forEach((node) => node.classList.remove("kanban-column--drop"));
  if (dropInProgress) return;
  dragContext = null;
  state.dragging = false;
  if (state.pendingRevisionCheck) {
    state.pendingRevisionCheck = false;
    checkRevision();
  }
}

async function dropCard(event, targetColumnId, list) {
  if (dragContext?.kind !== "card" || hasActiveFilters()) return;
  event.preventDefault();
  event.stopPropagation();
  dropInProgress = true;
  const cardId = dragContext.id;
  const card = state.snapshot.cards.find((item) => item.id === cardId);
  const otherCards = [...list.querySelectorAll(".kanban-card")].filter(
    (item) => item.dataset.cardId !== cardId,
  );
  let targetIndex = otherCards.length;
  for (let index = 0; index < otherCards.length; index += 1) {
    const rect = otherCards[index].getBoundingClientRect();
    if (event.clientY < rect.top + rect.height / 2) {
      targetIndex = index;
      break;
    }
  }
  try {
    await api.request(`/cards/${cardId}/move`, {
      method: "POST",
      body: {
        target_column_id: targetColumnId,
        target_index: targetIndex,
        expected_version: card.version,
        client_request_id: mutationId(),
      },
    });
    await loadSnapshot();
  } catch (error) {
    await handleMutationError(error);
  } finally {
    dropInProgress = false;
    dragContext = null;
    state.dragging = false;
    finishDrag();
  }
}

function handleColumnDragOver(event) {
  if (dragContext?.kind === "column" && !hasActiveFilters()) event.preventDefault();
}

async function dropColumn(event) {
  if (dragContext?.kind !== "column" || hasActiveFilters()) return;
  event.preventDefault();
  dropInProgress = true;
  const draggedId = dragContext.id;
  const columnNodes = [...byId("board-columns").querySelectorAll(".kanban-column")].filter(
    (item) => item.dataset.columnId !== draggedId,
  );
  let targetIndex = columnNodes.length;
  for (let index = 0; index < columnNodes.length; index += 1) {
    const rect = columnNodes[index].getBoundingClientRect();
    if (event.clientX < rect.left + rect.width / 2) {
      targetIndex = index;
      break;
    }
  }
  const orderedIds = state.snapshot.columns
    .sort((a, b) => a.position - b.position)
    .map((item) => item.id)
    .filter((id) => id !== draggedId);
  orderedIds.splice(targetIndex, 0, draggedId);
  try {
    await api.request(`/boards/${state.currentBoardId}/columns/order`, {
      method: "PUT",
      body: {
        column_ids: orderedIds,
        expected_board_version: state.snapshot.board.version,
        client_request_id: mutationId(),
      },
    });
    await loadSnapshot();
  } catch (error) {
    await handleMutationError(error);
  } finally {
    dropInProgress = false;
    dragContext = null;
    state.dragging = false;
    finishDrag();
  }
}

function openBoardEditor(board = null) {
  const dialog = byId("board-dialog");
  byId("board-form").reset();
  clearFormError("board-form-error");
  byId("board-form-id").value = board?.id || "";
  byId("board-dialog-title").textContent = board ? "Настройки доски" : "Новая доска";
  byId("board-form-title").value = board?.title || "";
  byId("board-form-description").value = board?.description || "";
  byId("default-columns-label").hidden = Boolean(board);
  byId("board-danger-zone").hidden = !board;
  dialog.dataset.version = board?.version || "";
  openDialog(dialog);
}

async function submitBoardForm(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    closeDialog(byId("board-dialog"));
    return;
  }
  const form = event.currentTarget;
  const boardId = byId("board-form-id").value;
  clearFormError("board-form-error");
  setBusy(form, true);
  try {
    const title = byId("board-form-title").value;
    const description = byId("board-form-description").value.trim();
    if (boardId) {
      await api.request(`/boards/${boardId}`, {
        method: "PATCH",
        body: {
          title,
          ...(description ? { description } : { clear_description: true }),
          expected_version: Number(byId("board-dialog").dataset.version),
          client_request_id: mutationId(),
        },
      });
    } else {
      await api.request("/boards", {
        method: "POST",
        body: {
          title,
          description: description || null,
          create_default_columns: byId("board-form-defaults").checked,
          client_request_id: mutationId(),
        },
      });
    }
    closeDialog(byId("board-dialog"));
    if (state.currentBoardId === boardId) await loadSnapshot();
    else await loadBoards();
    showToast(boardId ? "Настройки доски сохранены" : "Доска создана", "success");
  } catch (error) {
    if (error instanceof ApiError && error.code === "NO_CHANGES") {
      closeDialog(byId("board-dialog"));
    } else {
      showFormError("board-form-error", error);
    }
  } finally {
    setBusy(form, false);
  }
}

async function archiveCurrentBoard() {
  const boardId = byId("board-form-id").value;
  const board = state.snapshot?.board || state.boards.find((item) => item.id === boardId);
  if (!board || !window.confirm(`Переместить доску «${board.title}» в архив?`)) return;
  try {
    await api.request(`/boards/${board.id}`, {
      method: "DELETE",
      body: {
        expected_version: board.version,
        client_request_id: mutationId(),
      },
    });
    closeDialog(byId("board-dialog"));
    showBoardsView();
    await loadBoards();
    showToast("Доска перемещена в архив", "success");
  } catch (error) {
    showFormError("board-form-error", error);
  }
}

function fillActiveColumnSelect(select, selectedId = "") {
  clear(select);
  for (const column of [...state.snapshot.columns].sort((a, b) => a.position - b.position)) {
    select.append(
      element("option", {
        text: column.title,
        attrs: { value: column.id, selected: column.id === selectedId },
      }),
    );
  }
  if (selectedId) select.value = selectedId;
}

function openCardEditor(card = null, columnId = "") {
  const dialog = byId("card-dialog");
  byId("card-form").reset();
  clearFormError("card-form-error");
  byId("card-form-id").value = card?.id || "";
  byId("card-dialog-title").textContent = card ? "Карточка" : "Новая карточка";
  fillActiveColumnSelect(byId("card-form-column"), card?.column_id || columnId);
  byId("card-form-column").disabled = Boolean(card);
  byId("card-form-title").value = card?.title || "";
  byId("card-form-description").value = card?.description || "";
  byId("card-form-priority").value = card?.priority || "normal";
  byId("card-form-due").value = toDateTimeLocal(card?.due_date);
  byId("card-danger-zone").hidden = !card;
  dialog.dataset.version = card?.version || "";
  openDialog(dialog);
}

async function submitCardForm(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    closeDialog(byId("card-dialog"));
    return;
  }
  const form = event.currentTarget;
  const cardId = byId("card-form-id").value;
  clearFormError("card-form-error");
  setBusy(form, true);
  try {
    const description = byId("card-form-description").value.trim();
    const dueInput = byId("card-form-due").value;
    const common = {
      title: byId("card-form-title").value,
      priority: byId("card-form-priority").value,
      ...(description ? { description } : { clear_description: true }),
      ...(dueInput
        ? { due_date: new Date(dueInput).toISOString() }
        : { clear_due_date: true }),
      client_request_id: mutationId(),
    };
    if (cardId) {
      await api.request(`/cards/${cardId}`, {
        method: "PATCH",
        body: {
          ...common,
          expected_version: Number(byId("card-dialog").dataset.version),
        },
      });
    } else {
      const { clear_description, clear_due_date, ...createFields } = common;
      await api.request(`/boards/${state.currentBoardId}/cards`, {
        method: "POST",
        body: {
          ...createFields,
          description: description || null,
          due_date: dueInput ? new Date(dueInput).toISOString() : null,
          column_id: byId("card-form-column").value,
        },
      });
    }
    closeDialog(byId("card-dialog"));
    await loadSnapshot();
    showToast(cardId ? "Карточка сохранена" : "Карточка создана", "success");
  } catch (error) {
    if (error instanceof ApiError && error.code === "NO_CHANGES") {
      closeDialog(byId("card-dialog"));
    } else {
      showFormError("card-form-error", error);
    }
  } finally {
    setBusy(form, false);
  }
}

async function archiveCurrentCard() {
  const cardId = byId("card-form-id").value;
  const card = state.snapshot.cards.find((item) => item.id === cardId);
  if (!card || !window.confirm(`Переместить карточку «${card.title}» в архив?`)) return;
  try {
    await api.request(`/cards/${card.id}`, {
      method: "DELETE",
      body: {
        expected_version: card.version,
        client_request_id: mutationId(),
      },
    });
    closeDialog(byId("card-dialog"));
    await loadSnapshot();
    showToast("Карточка перемещена в архив", "success");
  } catch (error) {
    showFormError("card-form-error", error);
  }
}

function openColumnEditor(column = null) {
  const dialog = byId("column-dialog");
  byId("column-form").reset();
  clearFormError("column-form-error");
  byId("column-form-id").value = column?.id || "";
  byId("column-dialog-title").textContent = column ? "Настройки колонки" : "Новая колонка";
  byId("column-form-title").value = column?.title || "";
  byId("column-form-wip").value = column?.wip_limit || "";
  byId("column-form-done").checked = Boolean(column?.is_done);
  byId("column-danger-zone").hidden = !column;
  dialog.dataset.version = column?.version || "";
  openDialog(dialog);
}

async function submitColumnForm(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    closeDialog(byId("column-dialog"));
    return;
  }
  const form = event.currentTarget;
  const columnId = byId("column-form-id").value;
  const wipText = byId("column-form-wip").value;
  clearFormError("column-form-error");
  setBusy(form, true);
  try {
    const common = {
      title: byId("column-form-title").value,
      is_done: byId("column-form-done").checked,
      ...(wipText ? { wip_limit: Number(wipText) } : { clear_wip_limit: true }),
      client_request_id: mutationId(),
    };
    if (columnId) {
      await api.request(`/columns/${columnId}`, {
        method: "PATCH",
        body: {
          ...common,
          expected_version: Number(byId("column-dialog").dataset.version),
        },
      });
    } else {
      const { clear_wip_limit, ...createFields } = common;
      await api.request(`/boards/${state.currentBoardId}/columns`, {
        method: "POST",
        body: createFields,
      });
    }
    closeDialog(byId("column-dialog"));
    await loadSnapshot();
    showToast(columnId ? "Колонка сохранена" : "Колонка создана", "success");
  } catch (error) {
    if (error instanceof ApiError && error.code === "NO_CHANGES") {
      closeDialog(byId("column-dialog"));
    } else {
      showFormError("column-form-error", error);
    }
  } finally {
    setBusy(form, false);
  }
}

async function beginColumnDelete() {
  const columnId = byId("column-form-id").value;
  const column = state.snapshot.columns.find((item) => item.id === columnId);
  const cards = state.snapshot.cards.filter(
    (item) => !item.archived_at && item.column_id === columnId,
  );
  if (!column) return;
  if (!cards.length) {
    if (!window.confirm(`Удалить пустую колонку «${column.title}»?`)) return;
    try {
      await deleteColumnRequest(column, null, null);
      closeDialog(byId("column-dialog"));
      await loadSnapshot();
      showToast("Колонка удалена", "success");
    } catch (error) {
      showFormError("column-form-error", error);
    }
    return;
  }
  const targets = state.snapshot.columns.filter((item) => item.id !== column.id);
  byId("column-delete-message").textContent =
    `В колонке «${column.title}» находится карточек: ${cards.length}. ` +
    "Выберите, что с ними сделать.";
  const action = byId("column-delete-action");
  action.querySelector('option[value="move"]').disabled = !targets.length;
  action.value = targets.length ? "move" : "archive";
  const targetSelect = byId("column-delete-target");
  clear(targetSelect);
  for (const target of targets) {
    targetSelect.append(
      element("option", { text: target.title, attrs: { value: target.id } }),
    );
  }
  byId("column-delete-target-label").hidden = action.value !== "move";
  byId("column-delete-dialog").dataset.columnId = column.id;
  clearFormError("column-delete-error");
  closeDialog(byId("column-dialog"));
  openDialog(byId("column-delete-dialog"));
}

function deleteColumnRequest(column, cardAction, targetColumnId) {
  return api.request(`/columns/${column.id}`, {
    method: "DELETE",
    body: {
      expected_version: column.version,
      card_action: cardAction,
      target_column_id: targetColumnId,
      client_request_id: mutationId(),
    },
  });
}

async function submitColumnDelete(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    closeDialog(byId("column-delete-dialog"));
    return;
  }
  const form = event.currentTarget;
  const columnId = byId("column-delete-dialog").dataset.columnId;
  const column = state.snapshot.columns.find((item) => item.id === columnId);
  const action = byId("column-delete-action").value;
  const target = action === "move" ? byId("column-delete-target").value : null;
  clearFormError("column-delete-error");
  setBusy(form, true, "Удаление…");
  try {
    await deleteColumnRequest(column, action, target);
    closeDialog(byId("column-delete-dialog"));
    await loadSnapshot();
    showToast("Колонка удалена", "success");
  } catch (error) {
    showFormError("column-delete-error", error);
  } finally {
    setBusy(form, false);
  }
}

async function showActivity() {
  const dialog = byId("activity-dialog");
  const list = byId("activity-list");
  list.replaceChildren(element("div", { className: "empty-state", text: "Загрузка…" }));
  openDialog(dialog);
  try {
    const data = await api.request(
      `/boards/${state.currentBoardId}/activity?limit=100`,
    );
    clear(list);
    if (!data.items.length) {
      list.append(element("div", { className: "empty-state", text: "Действий пока нет." }));
      return;
    }
    for (const item of data.items) {
      list.append(
        element("article", { className: "activity-item" }, [
          element("strong", { text: item.summary }),
          element("span", {
            className: "activity-item__meta",
            text: `${item.actor.display_name} · ${formatDateTime(item.created_at)}`,
          }),
        ]),
      );
    }
  } catch (error) {
    list.replaceChildren(
      element("div", { className: "form-error", text: errorText(error) }),
    );
  }
}

async function showCardArchive() {
  const dialog = byId("card-archive-dialog");
  const list = byId("card-archive-list");
  list.replaceChildren(element("div", { className: "empty-state", text: "Загрузка…" }));
  openDialog(dialog);
  try {
    const snapshot = await loadSnapshot(true);
    const archivedCards = snapshot.cards
      .filter((item) => item.archived_at)
      .sort((a, b) => new Date(b.archived_at) - new Date(a.archived_at));
    const activeColumns = snapshot.columns
      .filter((item) => !item.archived_at)
      .sort((a, b) => a.position - b.position);
    clear(list);
    if (!archivedCards.length) {
      list.append(element("div", { className: "empty-state", text: "Архив карточек пуст." }));
      return;
    }
    for (const card of archivedCards) {
      const info = element("div", {}, [
        element("strong", { text: card.title }),
        element("div", {
          className: "activity-item__meta",
          text: `Архивировано ${formatDateTime(card.archived_at)}`,
        }),
      ]);
      const select = element("select", {
        attrs: { "aria-label": `Колонка для восстановления ${card.title}` },
      });
      for (const column of activeColumns) {
        select.append(
          element("option", {
            text: column.title,
            attrs: {
              value: column.id,
              selected: column.id === card.column_id,
            },
          }),
        );
      }
      if (activeColumns.some((item) => item.id === card.column_id)) {
        select.value = card.column_id;
      }
      const restore = button(
        "Восстановить",
        "button button--primary",
        async () => {
          if (!select.value) return;
          restore.disabled = true;
          try {
            await api.request(`/cards/${card.id}/restore`, {
              method: "POST",
              body: {
                target_column_id: select.value,
                expected_version: card.version,
                client_request_id: mutationId(),
              },
            });
            await loadSnapshot();
            await showCardArchive();
            showToast("Карточка восстановлена", "success");
          } catch (error) {
            restore.disabled = false;
            await handleMutationError(error);
          }
        },
      );
      restore.disabled = !activeColumns.length;
      list.append(element("article", { className: "archive-item" }, [info, select, restore]));
    }
  } catch (error) {
    list.replaceChildren(
      element("div", { className: "form-error", text: errorText(error) }),
    );
  }
}

function stopPolling() {
  window.clearTimeout(pollTimer);
  pollTimer = null;
}

function startPolling() {
  stopPolling();
  schedulePolling();
}

function schedulePolling() {
  stopPolling();
  if (!state.currentBoardId) return;
  pollTimer = window.setTimeout(checkRevision, pollingDelay(document.hidden));
}

async function checkRevision() {
  if (!state.currentBoardId || !state.snapshot) return;
  if (shouldDeferRevision(state.dragging)) {
    state.pendingRevisionCheck = true;
    schedulePolling();
    return;
  }
  try {
    const current = await api.request(`/boards/${state.currentBoardId}/revision`);
    if (current.revision !== state.snapshot.board.revision) await loadSnapshot();
  } catch (error) {
    if (!(error instanceof ApiError && error.code === "NETWORK_ERROR")) {
      showToast(errorText(error), "error");
    }
  } finally {
    schedulePolling();
  }
}

function updateFilters() {
  Object.assign(state.filters, {
    query: byId("filter-query").value,
    priority: byId("filter-priority").value,
    columnId: byId("filter-column").value,
    due: byId("filter-due").value,
    updatedBy: byId("filter-user").value,
  });
  renderColumns();
}

function bindEvents() {
  configStore.subscribe(onRuntimeConfigChanged);
  byId("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    clearFormError("login-error");
    setBusy(form, true, "Вход…");
    try {
      if (!configStore.current) await configStore.load();
      await checkCompatibility();
      const pair = await api.login(
        byId("login-username").value,
        byId("login-password").value,
      );
      await enterApplication(pair.user);
    } catch (error) {
      showFormError("login-error", error);
      if (error instanceof ApiError && error.code === "NETWORK_ERROR") startRecoveryLoop();
    } finally {
      setBusy(form, false);
    }
  });
  byId("logout-button").addEventListener("click", async () => {
    try {
      await api.logout();
    } catch {
      api.tokens.clear();
    }
    showLogin();
  });
  byId("home-button").addEventListener("click", async () => {
    showBoardsView();
    await loadBoards();
  });
  byId("back-to-boards").addEventListener("click", async () => {
    showBoardsView();
    await loadBoards();
  });
  byId("toggle-board-archive").addEventListener("click", async () => {
    state.archivedBoards = !state.archivedBoards;
    await loadBoards();
  });
  byId("create-board-button").addEventListener("click", () => openBoardEditor());
  byId("edit-board-button").addEventListener("click", () =>
    openBoardEditor(state.snapshot.board),
  );
  byId("create-column-button").addEventListener("click", () => openColumnEditor());
  byId("activity-button").addEventListener("click", showActivity);
  byId("card-archive-button").addEventListener("click", showCardArchive);
  byId("about-button").addEventListener("click", () => openDialog(byId("about-dialog")));
  byId("change-password-button").addEventListener("click", openPasswordDialog);
  byId("board-form").addEventListener("submit", submitBoardForm);
  byId("card-form").addEventListener("submit", submitCardForm);
  byId("column-form").addEventListener("submit", submitColumnForm);
  byId("column-delete-form").addEventListener("submit", submitColumnDelete);
  byId("password-form").addEventListener("submit", submitPasswordForm);
  byId("archive-board-button").addEventListener("click", archiveCurrentBoard);
  byId("archive-card-button").addEventListener("click", archiveCurrentCard);
  byId("delete-column-button").addEventListener("click", beginColumnDelete);
  byId("column-delete-action").addEventListener("change", (event) => {
    byId("column-delete-target-label").hidden = event.target.value !== "move";
  });
  for (const id of [
    "filter-query",
    "filter-priority",
    "filter-column",
    "filter-due",
    "filter-user",
  ]) {
    byId(id).addEventListener(id === "filter-query" ? "input" : "change", updateFilters);
  }
  byId("clear-filters").addEventListener("click", () => {
    resetFilters();
    syncFilterInputs();
    renderColumns();
  });
  byId("board-columns").addEventListener("dragover", handleColumnDragOver);
  byId("board-columns").addEventListener("drop", dropColumn);
  document.querySelectorAll("[data-close-dialog]").forEach((node) => {
    node.addEventListener("click", () => closeDialog(node.closest("dialog")));
  });
  document.addEventListener("visibilitychange", () => {
    if (state.currentBoardId) {
      stopPolling();
      checkRevision();
    }
  });
}

async function initialize() {
  bindEvents();
  setConnectionState("starting", "Сервер запускается");
  try {
    await configStore.load();
    await checkCompatibility();
    if (!api.tokens.accessToken && api.tokens.refreshToken) await api.refresh();
    if (api.tokens.accessToken) {
      const user = await api.request("/auth/me");
      await enterApplication(user);
    } else {
      showLogin();
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      showLogin("Сессия завершена. Войдите повторно");
    } else {
      showLogin("Сервер запускается. Подключение повторится автоматически", false);
      startRecoveryLoop();
    }
  }
}

initialize();
