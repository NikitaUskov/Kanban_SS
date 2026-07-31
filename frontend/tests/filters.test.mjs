import assert from "node:assert/strict";
import test from "node:test";

import {
  filterCards,
  hasActiveFilters,
  isOverdue,
  pollingDelay,
  shouldDeferRevision,
} from "../assets/js/state.js";

const columns = [
  { id: "todo", is_done: false },
  { id: "done", is_done: true },
];
const cards = [
  {
    id: "1",
    column_id: "todo",
    title: "Срочная задача",
    description: "Проверить договор",
    priority: "critical",
    due_date: "2026-01-01T00:00:00Z",
    assignee_user_id: "user-1",
    comment_count: 2,
    checklist_total: 3,
    completed_at: null,
    archived_at: null,
  },
  {
    id: "2",
    column_id: "done",
    title: "Завершено",
    description: null,
    priority: "normal",
    due_date: "2026-01-01T00:00:00Z",
    assignee_user_id: null,
    comment_count: 0,
    checklist_total: 0,
    completed_at: "2026-01-02T00:00:00Z",
    archived_at: null,
  },
];

const emptyFilters = {
  query: "",
  priority: "",
  columnId: "",
  due: "",
  assigneeId: "",
  mine: false,
  withComments: false,
  withChecklist: false,
  completed: "",
};

test("completed card is not overdue", () => {
  const now = new Date("2026-07-27T00:00:00Z");
  assert.equal(isOverdue(cards[0], columns, now), true);
  assert.equal(isOverdue(cards[1], columns, now), false);
});

test("query and priority filters are combined", () => {
  const result = filterCards(
    cards,
    { ...emptyFilters, query: "договор", priority: "critical" },
    columns,
    new Date("2026-07-27T00:00:00Z"),
  );
  assert.deepEqual(
    result.map((item) => item.id),
    ["1"],
  );
});

test("mine comments and checklist filters are combined", () => {
  const result = filterCards(
    cards,
    {
      ...emptyFilters,
      mine: true,
      withComments: true,
      withChecklist: true,
      completed: "no",
    },
    columns,
    new Date("2026-07-27T00:00:00Z"),
    "user-1",
  );
  assert.deepEqual(result.map((item) => item.id), ["1"]);
});

test("unassigned filter returns only cards without assignee", () => {
  const result = filterCards(
    cards,
    { ...emptyFilters, assigneeId: "__none__" },
    columns,
  );
  assert.deepEqual(result.map((item) => item.id), ["2"]);
});

test("any filter disables drag-and-drop", () => {
  assert.equal(hasActiveFilters({ ...emptyFilters, columnId: "todo" }), true);
});

test("polling uses 5/20 second cadence and defers during drag", () => {
  assert.equal(pollingDelay(false), 5_000);
  assert.equal(pollingDelay(true), 20_000);
  assert.equal(shouldDeferRevision(true), true);
  assert.equal(shouldDeferRevision(false), false);
});
