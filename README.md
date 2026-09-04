# 我在地府打麻将 · 资源图鉴

从游戏资源中提取数据，生成可浏览的网页图鉴。

## 快速开始

```bash
# 1. 安装依赖
pip install unitypy

# 2. 配置环境
cp .env.example .env
# 编辑 .env，设置 GAME_DIR 指向游戏安装目录

# 3. 构建
python build_web.py

# 4. 预览
# 打开 web_src/index.html（开发版）
# 或打开 output/site/index.html（部署版）
```

## 项目结构

```
├── build_web.py              # 主构建脚本
├── deploy.py                 # 部署（压缩图片、转 AVIF）
├── calibrate.py              # rawparse 校准器
├── extract_enums.py          # 提取枚举定义
├── lib/                      # 可复用模块
│   ├── rawparse.py           # MonoBehaviour 字节解析器
│   ├── catalog.py            # Addressables catalog 解析
│   └── render_pl_icons.py    # 牌灵 3D 头像渲染
├── assets/                   # 静态资源
│   └── enums.json            # 枚举定义（可提交 git）
├── web_src/                  # 前端源码
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── data.json             # 构建生成的数据
└── output/site/              # 构建产物
```

## 常用命令

```bash
python build_web.py             # 完整构建（3-5分钟）
python build_web.py --web-only  # 仅同步前端（改代码后快速刷新）
python deploy.py                # 部署（压缩图片、转 AVIF）
python calibrate.py             # 校准 rawparse（游戏更新后）
python extract_enums.py         # 提取枚举到 assets/enums.json
```

## 数据规模

| 分类 | 数量 | 说明 |
|------|------|------|
| 灵佣 | 591 | 玩家 264 / BOSS 155 / 角色技能 172 |
| 祭品 | 181 | 栏内展示 79 |
| 遗物 | 197 | 本体 131 + DLC 23 + 神秘 24 |
| 角色 | 42 | 全部带技能 |
| 番种 | 136 | |
| 成就 | 177 | |
| 事件 | 45 | |
| 牌灵 | 18 | |
| 宝牌 | 16 | |

## 网页功能

- 全局搜索（支持多关键词）
- 分类 Tab 切换（角色/灵佣/BOSS/祭品/遗物/牌灵/番种/事件/成就）
- 稀有度过滤（普通/稀有/史诗/传说）
- Tag 标签分组过滤（牌型/花色/动物/仙妖/机制/数值）
- 卡片展开详情（技能/描述/关联番种）
- 番种悬浮卡片（显示番数和规则说明）
- 响应式布局（适配手机）

## 环境要求

- Python 3.14+
- UnityPy（`pip install unitypy`）
- 游戏安装目录（Steam）
- Node.js（可选，用于校验 JS 语法）

## 相关文档

- [AGENT.md](AGENT.md) — 详细技术文档、架构说明、开发规范

## 许可

仅供个人学习研究使用。
