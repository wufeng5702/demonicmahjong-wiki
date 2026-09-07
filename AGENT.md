# AGENT.md — DemonicMahjong 资源图鉴项目

## 项目概述

**游戏**：我在地府打麻将 (Demonic Mahjong)，开发商 Boxed Lightning Games
**引擎**：Unity 2022.3.14f1 + **IL2CPP**
**平台**：Windows x64 (Steam)

---

## 快速开始

```bash
# 1. 安装 uv（如未安装）
pip install uv

# 2. 安装依赖
uv sync

# 3. 配置环境
cp .env.example .env   # 编辑 GAME_DIR 等路径

# 4. 完整构建
uv run python build_web.py

# 5. 预览
打开 web_src/index.html（可直接预览）
或打开 output/site/index.html（部署版本）
```

---

## 项目结构

```
wiki\
├── build_web.py                 # 主构建脚本 ⭐
├── deploy.py                    # 部署脚本（压缩图片、转 AVIF）
├── calibrate.py                 # rawparse 校准器
├── extract_enums.py             # 从 dump.cs 提取枚举 → assets/enums.json
├── generate_lingyong_cards.py   # 灵佣卡片图生成（独立工具）
│
├── lib/                         # 可复用模块
│   ├── rawparse.py              # MonoBehaviour 字节解析器
│   ├── catalog.py               # Addressables catalog 解析
│   └── render_pl_icons.py       # 牌灵 3D 头像渲染
│
├── assets/                      # 静态资源
│   ├── enums.json               # 枚举定义（58KB，可提交 git）
│   └── lingyong_card/           # 卡片背景素材
│
├── web_src/                     # 前端源码
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── data.json                # 构建生成的纯 JSON 数据
│
├── output/site/                 # 构建产物（不入 git）
│
├── .env                         # 本地配置（不入 git）
├── .env.example                 # 配置模板
└── dump_output/                 # IL2CppDumper 输出（不入 git）
```

---

## 环境配置

`.env` 文件（参考 `.env.example`）：
```bash
# 游戏安装目录（包含 "xxx_Data" 文件夹）
GAME_DIR=你的游戏目录

# IL2CppDumper 输出的 dump.cs 路径（可选，用于枚举解析，详见 IL2CppDumper 章节）
DUMP_CS=你的dump.cs路径

# 中文字体路径（灵佣卡片生成用，可选）
FONT_PATHS=你的字体路径
```

依赖：
- Python 3.14
- uv（`pip install uv`，然后 `uv sync` 安装依赖）
- Node.js（可选，用于校验 JS 语法）

---

## 核心脚本

### build_web.py — 一键构建图鉴

```bash
uv run python build_web.py             # 完整构建（3-5分钟）
uv run python build_web.py --web-only  # 仅同步前端（改 app.js/style.css 后快速刷新）
```

构建流程：
1. 加载枚举（`assets/enums.json`，回退到 `dump.cs`）
2. 提取主 bundle 数据（灵佣/祭品/遗物/番种/成就/事件等）
3. 提取 sharedassets（角色/本体数据）并合并
4. I2 Localization 文本回填
5. 提取图标（灵佣/祭品/遗物/角色/事件/Buff/成就）
6. 写入 `web_src/data.json`，复制到 `output/site/`

当前数据规模：
- 灵佣 591（玩家 264 / BOSS 155 / 角色技能 172）
- 祭品 181（栏内展示 79）
- 遗物 197（本体 131 + DLC 23 + 神秘 24）
- 角色 42、番种 136、牌灵 18、宝牌 16、成就 177、事件 45

### calibrate.py — rawparse 校准

```bash
uv run python calibrate.py            # 自动查找 bundle，输出 probe_out.txt
uv run python calibrate.py --bundle <path>  # 指定 bundle
```

使用时机（无需每次构建都跑，仅在以下情况手动调用）：
1. 游戏版本更新后 —— 字段布局可能偏移
2. 修改了 rawparse.py 的字段定义后 —— 验证改动是否正确
3. build_web.py 出现解析错误时 —— 定位偏移位置

结果解读：
- `bad=0`：字段布局没变，无需操作
- `bad>0`：对照输出里的 diffs，更新 `rawparse.py` 的 SPECS

### deploy.py — 部署

```bash
uv run python deploy.py   # 压缩图片、转 AVIF，输出到 output/site_deploy/
```

### extract_enums.py — 提取枚举定义

```bash
uv run python extract_enums.py              # 从 dump.cs 提取 → assets/enums.json
uv run python extract_enums.py path/to/dump.cs  # 指定 dump.cs 路径
```

生成的 `assets/enums.json`（~58KB）包含 Tag、Rarity、CharacterID 等枚举定义，可提交 git。build_web.py 优先读此文件，不再依赖 40MB 的 dump.cs。

---

## IL2CppDumper

IL2CppDumper 用于从 IL2CPP 编译后的二进制中提取类结构信息。

### 用途

- 生成 `dump.cs`：包含所有类、字段、枚举的定义
- 本项目用它提取枚举值（Tag、Rarity、CharacterID 等）
- rawparse.py 的字段规格（SPECS）也源自 dump.cs 的字段声明顺序

### 工具获取

官方版本不支持 metadata v39（Unity 6000.x），需使用 fork：
- [c01ns/Il2CppDumper](https://github.com/c01ns/Il2CppDumper/releases/tag/v39-support)（仅 Windows）

### 运行方式

```powershell
# 输入文件位于游戏目录
& "Il2CppDumper.exe" "GameAssembly.dll" "Demonic Mahjong_Data\il2cpp_data\Metadata\global-metadata.dat" "dump_output"
```

输入：
- `GameAssembly.dll`：IL2CPP 编译后的代码
- `global-metadata.dat`：元数据文件

输出（`dump_output/` 目录）：
- `dump.cs`：类/枚举定义（~40MB，不提交 git）
- `DummyDll/`：可反编译的 DLL
- `script.json`：元数据信息

### 注意事项

- 游戏每次更新后 metadata 版本可能变化，需检查工具兼容性
- dump.cs 仅在以下情况需要重新生成：
  1. 新增枚举类型
  2. 枚举值变化
  3. 字段布局变化（需同步更新 rawparse.py）
- 日常委托 `assets/enums.json` 即可，无需 dump.cs

---

## 数据架构

### 数据源

| 数据源 | 位置 | 说明 |
|--------|------|------|
| 主 bundle | `defaultlocalgroup_assets_all_*.bundle`（3GB） | DLC 数据，类型树完整 |
| sharedassets1 | `sharedassets1.assets` | 本体数据（类型树剥离，需 rawparse） |
| sharedassets4 | `sharedassets4.assets` | 角色/BOSS/遗物列表（类型树剥离） |
| I2 语言表 | sharedassets1 #13761 | 4692 词条，6 语言 |

### ID 区段语义

| ID 范围 | 含义 | 展示位置 |
|---------|------|----------|
| 灵佣 <10000 | 玩家可获得灵佣 | 【灵佣】栏 |
| 灵佣 10000-19999 | BOSS 专属灵佣 | 【BOSS灵佣】栏 |
| 灵佣 ≥20000 | 玩家角色技能 | 角色卡详情 |
| 祭品 1-38 | 本体祭品 | 祭品栏 |
| 祭品 10001+ | 奶茶 | 祭品栏 |
| 祭品 20000+ | 角色主动技能 | 角色卡详情 |

### Tag 系统

标签分组定义在 `web_src/app.js` 的 `TAG_GROUPS` 中：
- 牌型：刻子/顺子/对子/杠子/和牌/门前清/吃/碰
- 花色：万/筒/索/字/风/三元/数牌
- 动物：鸟/狐/龙/牛/猫/狗/猴/马/蛇/兔/龟/鹤/猪/象/鼠/鱼
- 仙妖：狐仙/风怪/地仙/仙/四凶/娃娃/小妖/鬼俑/人俑
- 机制：打出/可计分/金币/血量/牌灵/奇数/偶数/摸牌数/额外牌/魂力
- 数值：成长/宝牌/毒/牌基础分/金币强化/祭品
- 其他：蛋/衍生/独立/空巢/蜡烛/容器/付费强化/念灵/灵佣/BOSS被动/BOSS主动/BOSS灵佣

枚举值在 `build_web.py` 的 `TAG_CN`（英文→中文）和 `TAG_ID_CN`（ID→中文）中定义。

---

## 技术细节

### rawparse.py — MonoBehaviour 字节解析

适用：`.assets` 中类型树被剥离的对象。

字节布局规则：
- 头部 28B = GameObject PPtr(12) + enabled(1+pad3) + Script PPtr(12)
- 之后 m_Name(string)，然后按 dump.cs 字段声明顺序内联
- int/enum/float = 4B（读取前 align4）
- bool = 读 1B 后独立 align 到 4B
- string = len(i32) + bytes + align4
- PPtr = file_id(i32) + path_id(i64)
- List<T> = count(i32) + N×T
- LocalizedString = mTerm(str) + bool + i32 + bool + bool（尾部共 16B）

### I2 Localization

- 6 语言顺序固定：[简中, 英, 日, 繁中, ?, 韩]
- key 格式：`LingYong/Individual/{id}_{hash}/Name|Description`
- 简中优先，英文回退

### 图标提取

图标在 `build_web.py` 的 `extract_all_icons()` 中统一提取：
- 灵佣/祭品/遗物：通过 iconReference GUID 解析到具体资源
- 角色头像：从 RoleAvatar 的 headIcon PPtr 提取
- 事件/Buff/成就：从 bundle 中按名称匹配 Sprite

---

## 开发规范

- **阶段性修改及时提交**：完成一个功能/修复后立即 `git commit`，不要积攒大量修改一次性提交
- 提交信息格式：`feat/fix/chore: 简要描述`，如 `feat: 番种 tooltip 卡片`

---

## 已知限制

1. 部分角色（牛头马面/黑白无常等 NPC）没有技能数据
2. 神秘事件效果链留空（效果节点无标签无法跨事件归属）
3. 传说灵佣金色边框由 RarityEffect 动态渲染，静态合成需另做

---

## 环境注意

- PowerShell 终端 GBK：print 中文乱码不影响文件
- 3GB bundle 加载 30-60s，扫 40 万对象 2-4 分钟
- 读 .assets 的 Sprite 必须用 `UnityPy.load()`（Environment 解析 .resS），AssetsManager 不行
