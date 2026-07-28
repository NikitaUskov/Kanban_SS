export const PRIORITIES = {
  low: "Низкий",
  normal: "Обычный",
  high: "Высокий",
  critical: "Критический",
};

export const state = {
  user: null,
  boards: [],
  currentBoardId: null,
  snapshot: null,
  archivedBoards: false,
  connection: "starting",
  compatible: true,
  dragging: false,
  pendingRevisionCheck: false,
  filters: {
    query: "",
    priority: "",
    columnId: "",
    due: "",
    updatedBy: "",
  },
};

export function hasActiveFilters(filters = state.filters) {
  return Object.values(filters).some(Boolean);
}

export function pollingDelay(isDocumentHidden) {
  return isDocumentHidden ? 20_000 : 5_000;
}

export function shouldDeferRevision(isDragging) {
  return Boolean(isDragging);
}

export function isOverdue(card, columns, now = new Date()) {
  if (!card.due_date || card.archived_at) return false;
  const column = columns.find((item) => item.id === card.column_id);
  if (column?.is_done) return false;
  return new Date(card.due_date).getTime() < now.getTime();
}

export function filterCards(cards, filters, columns, now = new Date()) {
  const query = filters.query.trim().toLocaleLowerCase("ru");
  return cards.filter((card) => {
    if (card.archived_at) return false;
    if (query) {
      const haystack = `${card.title}\n${card.description || ""}`.toLocaleLowerCase("ru");
      if (!haystack.includes(query)) return false;
    }
    if (filters.priority && card.priority !== filters.priority) return false;
    if (filters.columnId && card.column_id !== filters.columnId) return false;
    if (filters.updatedBy && card.updated_by_user_id !== filters.updatedBy) return false;
    if (filters.due === "with" && !card.due_date) return false;
    if (filters.due === "without" && card.due_date) return false;
    if (filters.due === "overdue" && !isOverdue(card, columns, now)) return false;
    return true;
  });
}

export function resetFilters() {
  Object.assign(state.filters, {
    query: "",
    priority: "",
    columnId: "",
    due: "",
    updatedBy: "",
  });
}
