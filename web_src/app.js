/* 我在地府打麻将 · 图鉴  (由 build_web.py 数据驱动) */
"use strict";

/* ========== 站点配置 ========== */
const SITE_CONFIG = {
  repoUrl: "__REPO_URL__", // 仓库地址，构建时从 .env 替换
};

const TABS = [
  { key: "characters", label: "角色" },
  { key: "lingyong", label: "灵佣" },
  { key: "bosslingyong", label: "BOSS" },
  { key: "offerings", label: "祭品" },
  { key: "relics", label: "遗物" },
  { key: "pabao", label: "牌灵/宝牌" },
  { key: "fanzhong", label: "番种" },
  { key: "events", label: "神秘事件" },
  { key: "achievements", label: "成就" },
];

/* 虚拟分类: 从 lingyong 按 ID 区间拆分
   - 玩家可获得的灵佣: id < 10000
   - BOSS 专属灵佣: 10000 <= id < 20000
   - BOSS 主动技能: 30000 <= id < 40000 (tag=BOSS主动)
   - 20000+: 玩家操作角色的技能, 归入角色详情, 不在灵佣栏展示 */
const RAR_ORDER = { 普通: 0, 稀有: 1, 史诗: 2, 传说: 3 };

(async function loadData() {
  try {
    const resp = await fetch("data.json");
    if (!resp.ok) throw new Error(resp.status);
    window.DATA = await resp.json();
  } catch (e) {
    document.getElementById("result-info").innerHTML =
      '<span style="color:#e88">未加载数据 (data.json) —— 先运行 <b>python build_web.py</b> 生成数据。</span>';
    return;
  }
  initApp();
})();

function initApp() {
  // 设置仓库链接
  const repoLink = document.getElementById("repo-link");
  if (repoLink && SITE_CONFIG.repoUrl) {
    repoLink.href = SITE_CONFIG.repoUrl;
  }
  init();
}

function getEntries(cat) {
  const d = window.DATA.data;
  if (cat === "bosslingyong")
    return (d.lingyong || [])
      .filter(
        (e) =>
          (e.id >= 10000 && e.id < 20000) ||
          (e.id >= 30000 &&
            e.id < 40000 &&
            (e.tags || []).includes("BOSS主动")),
      )
      .sort(byRarity);
  if (cat === "lingyong")
    return (d.lingyong || []).filter((e) => e.id < 10000).sort(byRarity);
  if (cat === "offerings")
    return (d.offerings || []).filter((e) => e.id > 0 && e.id < 20000); // #28: 角色技能祭品(20000+)不展示
  if (cat === "pabao") {
    const p = (d.pailing || []).map((e) => ({ ...e, _src: "牌灵" }));
    const b = (d.baopai || []).map((e) => ({ ...e, _src: "宝牌" }));
    const y = (d.yejingbuff || []).map((e) => ({ ...e, _src: "业镜Buff" }));
    return [...p, ...b, ...y];
  }
  return d[cat] || [];
}

function byRarity(a, b) {
  const ra = RAR_ORDER[a.rar] ?? 9,
    rb = RAR_ORDER[b.rar] ?? 9;
  return ra - rb || a.id - b.id || (a.level || 0) - (b.level || 0);
}

/* ---------- 过滤 chips (需求 #10/#11/#13) ---------- */
const FAN_RANGES = [
  [1, 8],
  [9, 16],
  [17, 32],
  [33, 64],
  [65, 88],
  [89, Infinity],
];

function chipModel(cat) {
  const entries = getEntries(cat);
  if (["lingyong", "bosslingyong", "relics"].includes(cat)) {
    const vals = [...new Set(entries.map((e) => e.rar || e.rar2 || ""))]
      .filter(Boolean)
      .sort((a, b) => (RAR_ORDER[a] ?? 9) - (RAR_ORDER[b] ?? 9));
    if (!vals.length) return null;
    return {
      label: "稀有度",
      values: vals,
      test: (e, v) => (e.rar || e.rar2 || "") === v,
    };
  }
  if (cat === "offerings") {
    return {
      label: "分类",
      values: ["水果", "花草", "糕点", "奶茶", "其他"],
      test: (e, v) => e.cat === v,
    };
  }
  if (cat === "fanzhong") {
    return {
      label: "番数",
      values: FAN_RANGES.map(([lo, hi]) =>
        hi === Infinity ? `${lo}+` : `${lo}-${hi}`,
      ),
      test: (e, v) => {
        const idx = FAN_RANGES.findIndex(([lo, hi]) =>
          hi === Infinity ? `${lo}+` : `${lo}-${hi}` === v,
        );
        if (idx < 0) return true;
        const [lo, hi] = FAN_RANGES[idx];
        return e.fan >= lo && e.fan <= hi;
      },
    };
  }
  if (cat === "pabao") {
    return {
      label: "分类",
      values: ["牌灵", "宝牌", "业镜Buff"],
      test: (e, v) => e._src === v,
    };
  }
  return null;
}

const HUASE_CN = { 1: "万", 2: "筒", 3: "索", 4: "风", 5: "箭" };

let state = {
  tab: localStorage.getItem("tab") || "lingyong",
  q: "",
  chip: null,
  openId: null,
  tagChips: [],
  tagExpanded: {},
};

function esc(s) {
  return String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
}

function hl(text, q) {
  const safe = esc(text);
  if (!q) return safe;
  try {
    return safe.replace(
      new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"),
      "<mark>$1</mark>",
    );
  } catch {
    return safe;
  }
}

/* ---------- 检索匹配 ---------- */
function entryHaystack(e, cat) {
  const parts = [e.name, e.cn, e.en, e.id, e.desc, e.rar, e.tags];
  if (cat === "characters") {
    for (const g of ["passives", "actives"])
      for (const s of e[g] || []) parts.push(s.name, s.desc);
  }
  if (e.fanList) parts.push(e.fanList.join(" "));
  if (cat === "fanzhong")
    parts.push(e.fan, e.series, (e.paiNames || []).join(" "));
  // 合并升级款后的祭品: 各等级的名称与描述一并纳入检索
  for (const t of e.tiers || []) parts.push(t.name, t.desc);
  // 神秘事件: 选项与效果
  for (const o of e.options || [])
    parts.push(o.text, (o.effects || []).join(" "));
  return parts.filter(Boolean).join("\n").toLowerCase();
}

function matches(e, cat, q) {
  const cm = chipModel(cat);
  if (state.chip && cm && !cm.test(e, state.chip)) return false;
  if ((cat === "lingyong" || cat === "bosslingyong") && state.tagChips.length) {
    const tags = e.tags || [];
    if (!state.tagChips.some((t) => tags.includes(t))) return false;
  }
  if (!q) return true;
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return true;
  const hay = entryHaystack(e, cat);
  return terms.some((t) => hay.includes(t));
}

/* ---------- 同 ID 多等级合并 (祭品升级款 #9 / BOSS难度变体 #18) ---------- */
function groupTiers(entries) {
  const map = new Map();
  for (const e of entries) {
    if (!map.has(e.id)) map.set(e.id, []);
    map.get(e.id).push(e);
  }
  const out = [];
  for (const arr of map.values()) {
    arr.sort((a, b) => (a.level || 0) - (b.level || 0));
    // 单级也包成 tiers, 保证正文渲染结构一致、文本对齐 (需求 #15)
    const base = { ...arr[0] };
    base.tiers = arr.map((x) => ({
      level: x.level || 0,
      name: x.name || "",
      desc: x.desc || "",
      nameKey: x.nameKey || "",
    }));
    out.push(base);
  }
  out.sort((a, b) => a.id - b.id);
  return out;
}

/* ---------- 卡片渲染 ---------- */
const GLYPH = {
  characters: "鬼",
  lingyong: "佣",
  bosslingyong: "煞",
  offerings: "祭",
  relics: "遗",
  pabao: "灵",
  fanzhong: "番",
  achievements: "成",
  events: "遇",
};

function avatarHtml(e, cat) {
  if (cat === "fanzhong") return "";
  if (e.icon) {
    return `<img class="avatar" loading="lazy" src="${esc(e.icon)}"
      onerror="this.outerHTML='<div class=\\'avatar placeholder\\'>?</div>'
      alt="?">`;
  }
  const glyph = GLYPH[cat] || "?";
  let dir;
  if (cat === "bosslingyong") dir = "lingyong_BOSS";
  else if (cat === "pabao")
    dir =
      e._src === "宝牌" ? "baopai" : e._src === "业镜Buff" ? "buff" : "pailing";
  else dir = cat;
  const src = `icons/${dir}/${encodeURIComponent(e.id)}.png`;
  return `<img class="avatar" loading="lazy" src="${src}"
    onerror="this.outerHTML='<div class=\\'avatar placeholder\\'>${glyph}</div>'
    alt="${glyph}">`;
}

function cardHtml(e, cat, q) {
  const keySuffix =
    cat === "offerings" || cat === "bosslingyong" ? "" : ":" + (e.level ?? "");
  const open = state.openId === cat + ":" + e.id + keySuffix;
  const rarCls = e.rarity ? `r${Math.min(e.rarity, 4)}` : "";
  let badges = "";
  if (e.rar || e.rarity)
    badges += `<span class="badge ${rarCls}">${esc(e.rar || "稀有度" + e.rarity)}</span>`;
  if (e.rar2 && e.rar2 !== e.rar)
    badges += `<span class="badge ${rarCls}">${esc(e.rar2)}</span>`;
  if (e.star)
    badges += `<span class="badge">${"★".repeat(Math.min(e.star, 5))}</span>`;

  if (e.tiers && e.tiers.length > 1)
    badges += `<span class="badge">共 ${e.tiers.length} 级</span>`;

  if (e.fan) badges += `<span class="badge r4">番数 ${e.fan}</span>`;
  if (cat === "events") {
    for (const l of e.limits || [])
      badges += `<span class="badge warn">${esc(l)}</span>`;
  }
  if (e.src === "enum")
    badges += `<span class="badge warn">仅枚举·无数据</span>`;

  for (const t of e.tags || [])
    badges += `<span class="badge">${esc(t)}</span>`;

  const name = e.name || e.cn || "(未命名)";
  let bodyDesc;
  if (cat === "offerings" && e.tiers) {
    // 祭品(含单级)统一用 tier 行渲染, 各级文本左对齐 (需求 #15)
    bodyDesc = e.tiers
      .map(
        (t) =>
          `<div class="tier"><span class="tl">Lv.${t.level}${t.name && t.name !== e.name ? `<div class="tn">${hl(t.name, q)}</div>` : ""}</span>
        <div class="td">${hl(t.desc || "（无描述）", q)}</div></div>`,
      )
      .join("");
  } else if (e.tiers && e.tiers.length > 1) {
    bodyDesc = e.tiers
      .map(
        (t) =>
          `<div class="tier"><span class="tl">Lv.${t.level}</span>
        <div class="td">${hl(t.desc || "（无描述）", q)}</div></div>`,
      )
      .join("");
  } else {
    const desc =
      e.desc ||
      (cat === "characters" && !e.passives?.length && !e.actives?.length
        ? "（暂无技能数据）"
        : "") ||
      (e.descKey ? "（描述文本缺失）" : "");
    bodyDesc = desc
      ? `<div class="desc ${e.desc ? "" : "dim"}">${hl(desc, q)}</div>`
      : "";
    if (e.en === "ZaNian") {
      bodyDesc += `<div style="margin-top:2px;border-top:1px dashed var(--line);padding-top:6px">
<div style="color:var(--gold)">好运：倍率+50%/底分+50/获得2层【蓄力】/获得20金币。</div>
<hr style="border:none;border-top:1px dashed var(--line);margin:4px 0">
<div style="color:#8ac">中运：随机为1张手牌附上临时的念灵/随机将1张手牌变为临时的负面宝牌/随机净化1张手牌。</div>
<hr style="border:none;border-top:1px dashed var(--line);margin:4px 0">
<div style="color:#a463ba">厄运：底分-30/获得1层【尸毒】/对手的底分+50/对手的倍率+30%</div></div>
`;
    }

    if (e.en === "MaLing") {
      bodyDesc += `<div style="margin-top:2px;border-top:1px dashed var(--line);padding-top:6px">
<div style="color:#8ac">实际效果：12/34/56/78 互换，9变8。</div>
  `;
    }
  }

  let detail = "";
  if (open) {
    const kvs = [];
    kvs.push(["ID", e.id]);
    if (e.en) kvs.push(["枚举名", e.en]);
    if (e.cn && e.cn !== e.name) kvs.push(["中文名(枚举)", e.cn]);
    if (e.skin) kvs.push(["皮肤ID", e.skin]);
    if (e.stack) kvs.push(["堆叠上限", e.stack]);
    if (e.series) kvs.push(["系列", e.series]);
    if (e.paiNames && e.paiNames.length)
      kvs.push(["牌型", e.paiNames.join(" ")]);
    if (e.fanZhong) kvs.push(["关联番种ID", e.fanZhong]);
    if (e.nameKey) kvs.push(["名称Key", e.nameKey]);
    detail +=
      `<div class="kv">` +
      kvs
        .map(
          ([k, v]) =>
            `<div>${k}: <b title="${esc(v)}">${esc(String(v).slice(0, 60))}</b></div>`,
        )
        .join("") +
      `</div>`;
    if (cat === "events" && e.options?.length) {
      detail += `<div class="subh">选项与结果</div>`;
      for (const o of e.options) {
        const resultText = o.result || "";
        detail += `<div class="skillbox"><div class="hd"><span class="sn">${hl(o.text || "（无文本）", q)}</span></div>
          ${resultText ? `<div class="sd">${hl(resultText, q)}</div>` : ""}
          ${o.effects?.length ? `<div class="sd dim">${o.effects.map((x) => esc(x)).join("<br>")}</div>` : ""}</div>`;
      }
    }
    if (e.fanList && e.fanList.length) {
      const validFans = e.fanList.filter((f) => FZ.has(f));
      if (validFans.length)
        detail += `<div class="subh">关联番种</div><div class="stats fan-stats">${validFans
          .map((f) => {
            const fz = FZ.get(f);
            return `<span class="stat fan-tip" data-fz='${JSON.stringify({ id: f, cn: fz.cn, en: fz.en || "", fan: fz.fan || 0, desc: fz.desc || "" }).replace(/'/g, "&#39;")}'>${esc(fz.cn)}</span>`;
          })
          .join("")}</div>`;
    }
    if (cat === "characters") {
      for (const [g, label] of [
        ["passives", "被动技能"],
        ["actives", "主动技能"],
      ]) {
        if (!e[g]?.length) continue;
        // 按基础名分组 (去掉 lv.N 后缀)
        const groups = new Map();
        for (const s of e[g]) {
          const baseName = (s.name || "").replace(/\s*lv\.\d+$/, "");
          if (!groups.has(baseName)) groups.set(baseName, []);
          groups.get(baseName).push(s);
        }
        for (const [baseName, skills] of groups) {
          const firstId = skills[0]?.id;
          const suffix = g === "passives" ? "_passive" : "_active";
          const iconSrc = firstId
            ? `icons/characters/${firstId}${suffix}.png`
            : "";
          const iconHtml = iconSrc
            ? `<img class="subh-icon" src="${iconSrc}" onerror="this.style.display='none'" alt="">`
            : "";
          const skillType = g === "passives" ? "passive" : "active";
          detail += `<div class="subh subh-${skillType}">${iconHtml}<div class="subh-text"><div class="subh-label">${label}</div><div class="subh-name">${hl(baseName || "(未命名)", q)}</div></div></div>`;
          for (const s of skills) {
            const lvl = (s.name || "").match(/lv\.(\d+)/)?.[1] || "";
            const soul =
              g === "actives" && s.adds && s.adds.soulCost
                ? ` <span class="badge r4">魂力 ${s.adds.soulCost}</span>`
                : "";
            detail += `<div class="skillbox">
              <div class="skill-lv"><span class="tl">Lv${lvl}</span>${soul}</div>
              <div class="sd">${hl(s.desc || "（无描述）", q)}</div>
            </div>`;
          }
        }
      }
    }
  }

  const avatar = avatarHtml(e, cat);
  const showEn = e.en && cat !== "achievements";
  let topBlock;
  if (cat === "events" && e.icon) {
    topBlock = `<div class="card-top"><img class="avatar" loading="lazy" src="${esc(e.icon)}" alt="event"><div class="titles"><div class="name">${hl(name, q)}${showEn ? `<span class="en">${hl(e.en, q)}</span>` : ""}</div><div class="idline">ID ${hl(e.id, q)}${e.tiers && e.tiers.length > 1 ? ` · ${e.tiers.length}个等级` : e.level ? ` · Lv.${e.level}` : ""}</div></div></div>`;
  } else if (avatar) {
    topBlock = `<div class="card-top">${avatar}<div class="titles"><div class="name">${hl(name, q)}${showEn ? `<span class="en">${hl(e.en, q)}</span>` : ""}</div><div class="idline">ID ${hl(e.id, q)}${e.tiers && e.tiers.length > 1 ? ` · ${e.tiers.length}个等级` : e.level ? ` · Lv.${e.level}` : ""}</div></div></div>`;
  } else {
    topBlock = `<div class="titles"><div class="name">${hl(name, q)}${showEn ? `<span class="en">${hl(e.en, q)}</span>` : ""}</div><div class="idline">ID ${hl(e.id, q)}${e.tiers && e.tiers.length > 1 ? ` · ${e.tiers.length}个等级` : e.level ? ` · Lv.${e.level}` : ""}</div></div>`;
  }

  return `<article class="card ${open ? "open" : ""}" data-key="${cat}:${e.id}${keySuffix}">
    ${topBlock}
    ${badges ? `<div class="badges">${badges}</div>` : ""}
    ${bodyDesc}
    <div class="detail">${detail}</div>
  </article>`;
}

/* ---------- 主流程 ---------- */
let FZ = new Map();

async function init() {
  FZ = new Map(
    (window.DATA.data.fanzhong || []).map((f) => [
      f.id,
      {
        cn: f.cn || f.name || f.en,
        en: f.en || "",
        desc: f.desc || "",
        fan: f.fan,
      },
    ]),
  );
  document.getElementById("build-meta").textContent = window.DATA.meta
    ? `数据版本 ${window.DATA.meta.build}`
    : "";
  renderTabs();
  renderFilters();
  render();
  bindEvents();
  bindMiniTopbar();
}

function renderTabs() {
  const nav = document.getElementById("tabs");
  nav.innerHTML = TABS.map((t) => {
    const n = getEntries(t.key).length;
    return `<button class="tab ${state.tab === t.key ? "active" : ""}" data-tab="${t.key}">
      ${t.label}<span class="n">${n}</span></button>`;
  }).join("");
}

function renderFilters() {
  const box = document.getElementById("filters");
  const cm = chipModel(state.tab);
  if (!cm) {
    box.innerHTML = "";
    renderTagFilters();
    return;
  }
  const entries = getEntries(state.tab);
  box.innerHTML = [
    `<span style="color:var(--dim);font-size:12px">${cm.label}:</span>`,
  ]
    .concat(
      cm.values.map((v) => {
        const n = entries.filter((e) => cm.test(e, v)).length;
        return `<button class="chip ${state.chip === v ? "on" : ""}" data-chip="${esc(v)}">${esc(v)}<span class="cnt">${n}</span></button>`;
      }),
    )
    .join("");
  renderTagFilters();
}

function renderTagFilters() {
  const box = document.getElementById("tag-filters");
  if (state.tab !== "lingyong" && state.tab !== "bosslingyong") {
    box.innerHTML = "";
    return;
  }
  const entries = getEntries(state.tab);
  const tagCount = {};
  for (const e of entries) {
    for (const t of e.tags || []) tagCount[t] = (tagCount[t] || 0) + 1;
  }
  const allTags = Object.keys(tagCount);
  if (!allTags.length) {
    box.innerHTML = "";
    return;
  }

  const TAG_GROUPS =
    state.tab === "bosslingyong"
      ? { 分类: ["BOSS主动", "BOSS被动"] }
      : {
          牌型: ["刻子", "顺子", "对子", "杠子", "和牌", "门前清", "吃", "碰"],
          花色: ["万", "筒", "索", "字", "风", "三元", "数牌"],
          动物: [
            "鸟",
            "狐",
            "龙",
            "牛",
            "猫",
            "狗",
            "猴",
            "马",
            "蛇",
            "兔",
            "龟",
            "鹤",
            "猪",
            "象",
            "鼠",
            "鱼",
          ],
          仙妖: [
            "狐仙",
            "风怪",
            "地仙",
            "仙",
            "四凶",
            "娃娃",
            "小妖",
            "鬼俑",
            "人俑",
          ],
          机制: [
            "打出",
            "可计分",
            "金币",
            "血量",
            "牌灵",
            "奇数",
            "偶数",
            "摸牌数",
            "额外牌",
            "魂力",
          ],
          数值: ["成长", "宝牌", "毒", "牌基础分", "金币强化", "祭品"],
          其他: [
            "蛋",
            "衍生",
            "独立",
            "空巢",
            "蜡烛",
            "容器",
            "付费强化",
            "念灵",
            "灵佣",
            "BOSS被动",
            "BOSS主动",
            "BOSS灵佣",
          ],
        };
  const inGroup = new Set();
  const groups = [];
  for (const [label, members] of Object.entries(TAG_GROUPS)) {
    const items = members.filter((t) => allTags.includes(t));
    if (!items.length) continue;
    items.forEach((t) => inGroup.add(t));
    groups.push({ label, items });
  }
  const rest = allTags
    .filter((t) => !inGroup.has(t))
    .sort((a, b) => (tagCount[b] || 0) - (tagCount[a] || 0));
  if (rest.length) groups.push({ label: "其他", items: rest });

  let html = "";
  if (state.tab === "bosslingyong") {
    html = `<span style="color:var(--dim);font-size:12px">技能:</span>`;
    for (const t of ["BOSS被动", "BOSS主动"]) {
      if (!tagCount[t]) continue;
      const on = state.tagChips.includes(t);
      const label = t === "BOSS被动" ? "被动" : "主动";
      html += `<button class="chip ${on ? "on" : ""}" data-tchip="${esc(t)}">${esc(label)}<span class="cnt">${tagCount[t]}</span></button>`;
    }
  } else {
    html = `<span style="color:var(--dim);font-size:12px">标签:</span>`;
    for (const g of groups) {
      const expanded = state.tagExpanded[g.label] ?? false;
      const selected = g.items.filter((t) => state.tagChips.includes(t));
      const summary = selected.length ? ` (${selected.length})` : "";
      const tooltip = g.items.join(" · ");
      html += `<span class="tag-group">`;
      html += `<button class="tg-btn${expanded ? " open" : ""}" data-tg="${esc(g.label)}" data-tip="${esc(tooltip)}">${esc(g.label)}${summary}</button>`;
      if (expanded) {
        html += `<span class="tg-items">`;
        for (const t of g.items) {
          const on = state.tagChips.includes(t);
          html += `<button class="chip ${on ? "on" : ""}" data-tchip="${esc(t)}">${esc(t)}<span class="cnt">${tagCount[t]}</span></button>`;
        }
        html += `</span>`;
      }
      html += `</span>`;
    }
  }
  box.innerHTML = html;
}

function render() {
  let entries = getEntries(state.tab);
  if (state.tab === "offerings" || state.tab === "bosslingyong")
    entries = groupTiers(entries);
  const shown = entries.filter((e) => matches(e, state.tab, state.q));
  const info = document.getElementById("result-info");
  let text =
    `${shown.length} / ${entries.length} 条` +
    (state.q ? ` · 关键词 "${state.q}"` : "");
  // 如果是角色或神秘事件，追加点击提示
  if (state.tab === "characters" || state.tab === "events") {
    text +=
      ' <span style="color:var(--gold);font-weight:600;">↕ 点击卡片可查看详情</span>';
  }
  info.innerHTML = text;
  const wrap = document.getElementById("cards");
  wrap.classList.toggle("events-list", state.tab === "events"); // #42
  if (state.tab === "pabao" && !state.chip) {
    const groups = {};
    for (const e of shown) {
      const src = e._src || "其他";
      (groups[src] = groups[src] || []).push(e);
    }
    const order = ["牌灵", "宝牌", "业镜Buff"];
    let html = "";
    for (const src of order) {
      const items = groups[src];
      if (!items || !items.length) continue;
      html += `<div class="section-divider">${src}</div>`;
      html += items.map((e) => cardHtml(e, state.tab, state.q)).join("");
    }
    wrap.innerHTML = html || `<div class="empty">没有匹配的条目</div>`;
  } else {
    wrap.innerHTML = shown.length
      ? shown.map((e) => cardHtml(e, state.tab, state.q)).join("")
      : `<div class="empty">没有匹配的条目</div>`;
  }
}

function bindEvents() {
  document.getElementById("tabs").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-tab]");
    if (!b) return;
    state.tab = b.dataset.tab;
    state.openId = null;
    state.chip = null;
    state.tagChips = [];
    if (state.tab === "pabao") state.chip = null; // 默认显示全部
    localStorage.setItem("tab", state.tab);
    renderTabs();
    renderFilters();
    render();
    window.scrollTo({ top: 0 });
  });
  document.getElementById("filters").addEventListener("click", (ev) => {
    const c = ev.target.closest("[data-chip]");
    if (!c) return;
    state.chip = state.chip === c.dataset.chip ? null : c.dataset.chip;
    renderFilters();
    render();
  });
  document.getElementById("tag-filters").addEventListener("click", (ev) => {
    const tg = ev.target.closest("[data-tg]");
    if (tg) {
      const g = tg.dataset.tg;
      state.tagExpanded[g] = !(
        state.tagExpanded[g] ??
        (g === "机制" || g === "数值")
      );
      renderTagFilters();
      return;
    }
    const c = ev.target.closest("[data-tchip]");
    if (!c) return;
    const v = c.dataset.tchip;
    const idx = state.tagChips.indexOf(v);
    if (idx >= 0) state.tagChips.splice(idx, 1);
    else state.tagChips.push(v);
    renderTagFilters();
    render();
  });
  const input = document.getElementById("search");
  let deb;
  input.addEventListener("input", () => {
    clearTimeout(deb);
    deb = setTimeout(() => {
      state.q = input.value.trim();
      state.openId = null;
      render();
    }, 120);
  });
  document.getElementById("clear-btn").addEventListener("click", () => {
    input.value = "";
    state.q = "";
    render();
    input.focus();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "/" && document.activeElement !== input) {
      ev.preventDefault();
      input.focus();
    }
    if (ev.key === "Escape") {
      input.value = "";
      state.q = "";
      render();
      input.blur();
    }
  });
  document.getElementById("cards").addEventListener("click", (ev) => {
    const card = ev.target.closest(".card");
    if (!card) return;
    // 只有神秘事件页面允许点击展开详情
    if (state.tab !== "events" && state.tab !== "characters") return;
    state.openId = state.openId === card.dataset.key ? null : card.dataset.key;
    render();
    const el = document.querySelector(
      `.card[data-key="${CSS.escape(state.openId || "")}"]`,
    );
    if (el) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });
}

function bindMiniTopbar() {
  const toggle = document.getElementById("topbar-toggle");
  const input = document.getElementById("search");

  let collapsed = false;
  let manualOverride = false;

  function setCollapsed(v) {
    collapsed = v;
    document.body.classList.toggle("nav-collapsed", v);
  }

  toggle.addEventListener("click", () => {
    manualOverride = true;
    setCollapsed(!collapsed);
    setTimeout(() => {
      manualOverride = false;
    }, 600);
  });

  window.addEventListener(
    "scroll",
    () => {
      if (window.innerWidth > 768 || manualOverride) return;
      const y = window.scrollY;
      if (y > 120 && !collapsed) setCollapsed(true);
      else if (y < 40 && collapsed) setCollapsed(false);
    },
    { passive: true },
  );

  input.addEventListener("focus", () => {
    if (window.innerWidth > 768) return;
    if (collapsed) setCollapsed(false);
  });

  /* 番种 tooltip 卡片 (仅桌面端) */
  let isTouchDevice = "ontouchstart" in window;
  document.addEventListener(
    "touchstart",
    () => {
      isTouchDevice = true;
    },
    { once: true },
  );
  if (!isTouchDevice) {
    let fzTip = null;
    function showFzTip(el) {
      hideFzTip();
      const raw = el.dataset.fz;
      if (!raw) return;
      const d = JSON.parse(raw);
      fzTip = document.createElement("div");
      fzTip.className = "fz-tip-card";
      fzTip.innerHTML = `
        <div class="fz-tip-header">
          <span class="fz-tip-name">${esc(d.cn)}</span>
          <span class="fz-tip-en">${esc(d.en)}</span>
        </div>
        <div class="fz-tip-id">ID ${d.id}</div>
        ${d.fan ? `<div class="fz-tip-fan">番数 ${d.fan}</div>` : ""}
        ${d.desc ? `<div class="fz-tip-desc">${esc(d.desc)}</div>` : ""}
      `;
      document.body.appendChild(fzTip);
      const r = el.getBoundingClientRect();
      fzTip.style.left = r.left + r.width / 2 + "px";
      fzTip.style.top = r.top - 8 + "px";
    }
    function hideFzTip() {
      if (fzTip) {
        fzTip.remove();
        fzTip = null;
      }
    }
    document.getElementById("cards").addEventListener("mouseover", (ev) => {
      if (isTouchDevice) return;
      const el = ev.target.closest(".fan-tip");
      if (el) showFzTip(el);
    });
    document.getElementById("cards").addEventListener("mouseout", (ev) => {
      if (isTouchDevice) return;
      const el = ev.target.closest(".fan-tip");
      if (el && !el.contains(ev.relatedTarget)) hideFzTip();
    });
    document.getElementById("cards").addEventListener("mousedown", () => {
      hideFzTip();
    });
    document.getElementById("cards").addEventListener(
      "click",
      (ev) => {
        if (ev.target.closest(".fan-tip")) {
          ev.stopPropagation();
        }
      },
      true,
    );
  }
}
