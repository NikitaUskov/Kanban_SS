import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
const appSource = await readFile(
  new URL("../assets/js/app.js", import.meta.url),
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
