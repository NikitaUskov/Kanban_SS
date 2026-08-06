import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
const appSource = await readFile(
  new URL("../assets/js/app.js", import.meta.url),
  "utf8",
);
const drawerSource = await readFile(
  new URL("../assets/js/card-detail.js", import.meta.url),
  "utf8",
);
const teamSource = await readFile(
  new URL("../assets/js/team.js", import.meta.url),
  "utf8",
);
const styles = await readFile(
  new URL("../assets/css/styles.css", import.meta.url),
  "utf8",
);

test("board filters are optional and controlled by an accessible toggle", () => {
  assert.match(html, /id="toggle-filters"/);
  assert.match(html, /aria-controls="filters-panel"/);
  assert.match(html, /id="filters-panel"[^>]*hidden/);
  assert.match(appSource, /setFiltersPanelOpen/);
});

test("board list cards do not render column and card counters", () => {
  assert.doesNotMatch(appSource, /board\.column_count/);
  assert.doesNotMatch(appSource, /board\.active_card_count/);
});

test("existing card opens a responsive collaboration drawer", () => {
  assert.match(html, /id="card-drawer"/);
  assert.match(html, /id="comments-list"/);
  assert.match(html, /id="checklist-items"/);
  assert.match(drawerSource, /class CardDrawerController/);
  assert.match(styles, /\.card-drawer/);
  assert.match(styles, /width: 100vw/);
});

test("columns can be collapsed without changing shared board data", () => {
  assert.match(appSource, /kanban\.collapsedColumns/);
  assert.match(appSource, /toggleColumnCollapsed/);
  assert.match(styles, /\.kanban-column--collapsed/);
});


test("version 1.3 provides invitations, participants and notifications", () => {
  assert.match(html, /id="participants-dialog"/);
  assert.match(html, /id="invite-dialog"/);
  assert.match(html, /id="notifications-drawer"/);
  assert.match(teamSource, /class TeamController/);
  assert.match(teamSource, /\/admin\/invitations/);
  assert.match(styles, /\.notifications-drawer/);
});

test("card drawer provides one-level subtasks", () => {
  assert.match(html, /id="subtask-form"/);
  assert.match(html, /id="subtasks-list"/);
  assert.match(drawerSource, /addSubtask/);
  assert.match(drawerSource, /parent_card_id/);
  assert.match(styles, /\.subtask-item/);
});

test("board actions react to access roles", () => {
  assert.match(appSource, /canEditBoardContent/);
  assert.match(appSource, /canAdministerBoard/);
  assert.match(teamSource, /current_user_role/);
});
