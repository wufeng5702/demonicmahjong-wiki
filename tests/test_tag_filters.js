const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../web_src/app.js"), "utf8");

function renderTags(expanded = false, selected = [], tab = "lingyong", records = null) {
  const box = { innerHTML: "" };
  const entries = records || [
    { id: 1, tags: ["蛋", "童话", "刻子"] },
    { id: 2, tags: ["童话", "新标签"] },
  ];
  const context = vm.createContext({
    window: { DATA: { data: { [tab]: entries } } },
    document: { getElementById: () => box },
    localStorage: { getItem: () => null },
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(source, context);
  vm.runInContext(
    `state.tab = ${JSON.stringify(tab)};
     state.tagExpanded["其他"] = ${expanded};
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

const miscRelicTags = ["地图节点", "莲花", "特殊事件", "毒", "蛋"];
const relics = [{ id: 1, tags: [...miscRelicTags, "新标签", "武器"] }];

test("遗物杂项合并到唯一的其他分组", () => {
  const { html } = renderTags(false, [], "relics", relics);
  assert.doesNotMatch(html, /data-tg="杂项"/);
  assert.equal((html.match(/data-tg="其他"/g) || []).length, 1);
});

test("其他分组包含原杂项与新增标签且不重复", () => {
  const { html } = renderTags(true, [], "relics", relics);
  for (const tag of [...miscRelicTags, "新标签"]) {
    assert.equal((html.match(new RegExp(`data-tchip="${tag}"`, "g")) || []).length, 1);
  }
});

test("合并后的遗物标签仍可用于筛选", () => {
  const { html, context } = renderTags(true, ["莲花"], "relics", relics);
  assert.match(html, /其他 \(1\)/);
  assert.equal(vm.runInContext(`matches({tags: ["莲花"]}, "relics", "")`, context), true);
  assert.equal(vm.runInContext(`matches({tags: ["武器"]}, "relics", "")`, context), false);
});

test("诅咒遗物按主分类筛选而不是普通底层稀有度", () => {
  const entries = [{ id: 197, rar: "诅咒", rar2: "普通", tags: ["诅咒"] }];
  const { context } = renderTags(false, [], "relics", entries);
  assert.equal(vm.runInContext(`chipModel("relics").test(getEntries("relics")[0], "诅咒")`, context), true);
  assert.equal(vm.runInContext(`chipModel("relics").test(getEntries("relics")[0], "普通")`, context), false);
});
