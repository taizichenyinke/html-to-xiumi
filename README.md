# HTML to Xiumi (秀米)

把一个本地 HTML 文件自动发布成秀米(秀米)编辑草稿,并可保留设计稿的行内样式。

从清华物理系学生会「万有预报」项目的秀米发布功能提取而来,独立成仓,附带 Claude Code skill(`.claude/skills/html-to-xiumi/`)。

## 功能

- 打开秀米图文编辑器,自动填充标题、作者、摘要,写入正文并保存。
- 支持 HTML + Markdown 对:存在同名 `.md` 时自动检测,或显式 `--markdown` 指定。
- **`--preserve-styles` 模式**:把源设计稿的 `background` / `gradient` / `border` / `border-radius` / `font` / `text-shadow` 等行内样式直接写进 Angular comp 模型,渲染、保存、导出预览全部保留。
- 本地图片经秀米自身上传转成 CDN URL 后内联,保存后不会丢失。
- 登录态通过持久化浏览器 profile 保留,可复用。

## 安装

```bash
pip install -r requirements.txt
```

依赖仅有 `selenium`。需要本机装有 Chrome、Edge 或 Safari(以及对应的 WebDriver)。

## 快速开始

```powershell
# PowerShell 需显式设置浏览器与编码
$env:WANYOU_SELENIUM_BROWSER='chrome'; $env:PYTHONIOENCODING='utf-8'

# 基础发布(粘贴路径)
python scripts/publish_xiumi_draft.py path/to/your.html --title "推送标题" --author "作者"

# 保留设计稿样式(模型构建路径)
python scripts/publish_xiumi_draft.py path/to/your.html --title "推送标题" --preserve-styles --no-base-format

# HTML + Markdown 对
python scripts/publish_xiumi_draft.py path/to/your.html --markdown path/to/your.md --title "推送标题"

# 试运行(填充编辑器但不点保存)
python scripts/publish_xiumi_draft.py path/to/your.html --title "推送标题" --dry-run

# 指定持久化 profile,保留登录态
python scripts/publish_xiumi_draft.py path/to/your.html --title "推送标题" --profile-dir output/selenium_cache/my-xiumi-profile
```

首次运行浏览器会打开秀米登录页,登录完成后回到终端按 Enter,程序自动继续。保存后浏览器保持打开便于人工检查,再按 Enter 关闭。

## 配置

复制 `.env.example` 为 `.env` 并按需填写。主要项:

| 变量 | 默认 | 说明 |
|---|---|---|
| `WANYOU_SELENIUM_BROWSER` | Windows=edge / macOS=chrome | `chrome`、`edge` 或 `safari` |
| `XIUMI_HOME_URL` | 秀米主页 | 进入图文排版的起点 |
| `XIUMI_IMAGE_MODE` | `upload` | `upload` / `inline` / `auto` / `omit` |
| `XIUMI_PROFILE_DIR` | `output/selenium_cache/xiumi-profile` | 持久化 profile 路径 |
| `XIUMI_LOGIN_WAIT_SECONDS` | 600 | 等待手动登录的秒数 |
| `XIUMI_SAVE_WAIT_SECONDS` | 30 | 保存结果等待秒数 |
| `XIUMI_IMAGE_UPLOAD_MAX_FAILURES` | 3 | 连续上传失败多少次后放弃上传 |

## `--preserve-styles` 说明

默认粘贴路径会被秀米粘贴处理器剥离行内样式(仅 `text-align:justify` 存活)。`--preserve-styles` 改为直接构建模型:

- 源 HTML 的每个顶层 `<section>` 解析为一个 block;
- section 的内联 CSS(转 camelCase)→ `txt1.style`;
- 内部段落/span 及其行内样式 → `txt1.text`;
- 嵌套 `<section>`/`<div>` 转 `<p>`,丢弃空 `<p></p>`。

注意配合 `--no-base-format`,避免默认的 14px/18px 归一化压扁自定义大字排版。

## 目录结构

```
.
├── .claude/skills/html-to-xiumi/SKILL.md   # Claude Code skill 定义
├── scripts/publish_xiumi_draft.py          # 发布脚本(核心)
├── generators/                             # 发布脚本依赖的 HTML/Markdown 生成
├── wanyou/                                 # 发布脚本依赖的浏览器与图片工具
├── examples/                               # 验证脚本(探针)
├── config.py                               # 最小配置
└── .env.example / requirements.txt / .gitignore
```

## 验证脚本(`examples/`)

- `check_title_box.py` / `check_verify.py` / `parse_verify.py` — 解析抓取到的草稿 `editingResp` JSON,检查标题框、主题色、残留内容。
- `xiumi_open_draft_full.py <draft_url>` — 打开草稿并抓取其完整 `editingResp` 写入 JSON。
- `xiumi_reopen_fresh.py <draft_url>` — 新会话重开草稿,检查渲染层图片 src 是否持久化。
- `xiumi_cdn_inline_probe.py [logo.png]` — 探针:粘贴 data URL 触发秀米上传、取回 CDN URL、内联构建文本组件并保存。

这些都是开发探针而非正式 API,用于验证发布结果;内部依赖 `scripts/publish_xiumi_draft.py` 的私有函数,改动需同步。

## 致谢

提取自 [Wanyou](https://github.com/2007qqc/Wanyou)(清华物理系「万有预报」自动化管线)。
