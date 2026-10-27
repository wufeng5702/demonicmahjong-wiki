const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../web_src/app.js"), "utf8");

function renderTags(expanded = false, selected = []) {
  const box = { innerHTML: "" };
  const entries = [
    { id: 1, tags: ["蛋", "童话", "刻子"] },
    { id: 2, tags: ["童话", "新标签"] },
  ];
  const context = vm.createContext({
    window: { DATA: { data: { lingyong: entries } } },
    document: { getElementById: () => box },
    localStorage: { getItem: () => null },
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(source, context);
  vm.runInContext(
    `state.tagExpanded["其他"] = ${expanded};
     state.tagChips = ${JSON.stringify(selected)};
     renderTagFilters();`,
    context,
  );
  return { html: box.innerHTML, context };
}

test("灵俑标签只有一个其他分组", () => {
  const { html } = renderTags();
  assert.equal((html.match(/data-tg="其他"/g) || []).length, 1);
});

test("原其他标签和新增未分组标签都可展开且不重复", () => {
  const { html } = renderTags(true);
  for (const tag of ["蛋", "童话", "新标签"]) {
    assert.equal((html.match(new RegExp(`data-tchip="${tag}"`, "g")) || []).length, 1);
  }
});

test("未分组的童话标签仍可用于筛选", () => {
  const { html, context } = renderTags(true, ["童话"]);
  assert.match(html, /其他 \(1\)/);
  assert.equal(
    vm.runInContext(`matches({tags: ["童话"]}, "lingyong", "")`, context),
    true,
  );
  assert.equal(
    vm.runInContext(`matches({tags: ["蛋"]}, "lingyong", "")`, context),
    false,
  );
});
