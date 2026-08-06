export const PRIORITIES = {
  low: "Низкий",
  normal: "Обычный",
  high: "Высокий",
  critical: "Критический",
};

export const state = {
  user: null,
  users: [],
  boardMembers: [],
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
    assigneeId: "",
    mine: false,
    withComments: false,
    withChecklist: false,
    completed: "",
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
  if (!card.due_date || card.archived_at || card.completed_at) return false;
  const column = columns.find((item) => item.id === card.column_id);
  if (column?.is_done) return false;
  return new Date(card.due_date).getTime() < now.getTime();
}

export function filterCards(
  cards,
  filters,
  columns,
  now = new Date(),
  currentUserId = null,
) {
  const query = filters.query.trim().toLocaleLowerCase("ru");
  return cards.filter((card) => {
    if (card.archived_at) return false;
    if (query) {
      const haystack = `${card.title}\n${card.description || ""}`.toLocaleLowerCase("ru");
      if (!haystack.includes(query)) return false;
    }
    if (filters.priority && card.priority !== filters.priority) return false;
    if (filters.columnId && card.column_id !== filters.columnId) return false;
    if (filters.assigneeId === "__none__" && card.assignee_user_id) return false;
    if (
      filters.assigneeId &&
      filters.assigneeId !== "__none__" &&
      card.assignee_user_id !== filters.assigneeId
    ) return false;
    if (filters.mine && card.assignee_user_id !== currentUserId) return false;
    if (filters.withComments && Number(card.comment_count || 0) < 1) return false;
    if (filters.withChecklist && Number(card.checklist_total || 0) < 1) return false;
    if (filters.completed === "yes" && !card.completed_at) return false;
    if (filters.completed === "no" && card.completed_at) return false;
    if (filters.due === "with" && !card.due_date) return false;
    if (filters.due === "without" && card.due_date) return false;
    if (filters.due === "overdue" && !isOverdue(card, columns, now)) return false;
    if (filters.due === "today") {
      if (!card.due_date) return false;
      const due = new Date(card.due_date);
      if (due.toDateString() !== now.toDateString()) return false;
    }
    return true;
  });
}

export function resetFilters() {
  Object.assign(state.filters, {
    query: "",
    priority: "",
    columnId: "",
    due: "",
    assigneeId: "",
    mine: false,
    withComments: false,
    withChecklist: false,
    completed: "",
  });
}
