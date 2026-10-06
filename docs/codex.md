# Codex 接入

此 fork 在 hanselhan23/html-to-xiumi 的原有 Claude Code 工作流之外，提供 Codex 仓库 skill、个人 skill 安装器和可供其他 harness 调用的 Python CLI。模型写入仍由原 `scripts/publish_xiumi_draft.py` 完成，不需要模型自身具备秀米接口。

## 安装

需要 Python 3.11+、Edge 或 Chrome。在线命令依赖 Selenium；prepare 仅使用标准库。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scripts/install_codex_skill.py
```

macOS/Linux 对应解释器为 `.venv/bin/python`；浏览器参数使用本机已安装的 `--browser chrome` 或 `--browser edge`。在线实测环境目前只有 Windows Edge，其他平台需自行验证。

Codex 在仓库内发现 `.agents/skills/xiumi/SKILL.md`。个人安装默认写入 `$CODEX_HOME/skills/xiumi`（未设置时为 `~/.codex/skills/xiumi`），可用 `--destination <技能目录>` 指定位置。已有技能时安装器拒绝覆盖，明确更新时添加 `--replace`；保留 browser/driver/profile 等设置，更新源码与解释器路径。请保留完整 checkout 和虚拟环境；移动后重新安装或修改个人 settings.json。

个人 skill 的 settings.json 由安装器生成，包含 upstream 和 python 的本机绝对路径，未打包浏览器 profile。可自行增加 browser、driver、profile 设置，命令行参数优先。用 settings.json 中的 Python 调用技能目录的 scripts/run.py；任何 cwd 均可运行。新建 Codex 会话检查技能是否发现：`$xiumi 将这份 HTML 导入秀米并验证保存结果`。

## 命令

以下在仓库根目录运行；供 agent 调用时，脚本、HTML、profile 和 report 使用绝对路径。省略 --driver 时 Selenium Manager 会查找对应驱动，必要时下载；离线或匹配失败时显式提供官方匹配的驱动路径。

```powershell
# 1. 离线解析与素材检查，不启动浏览器
python scripts/codex_xiumi.py prepare examples/codex-sample.html --report output/codex/prepare.json

# 2. 仅访问空白页，检查浏览器/驱动
python scripts/codex_xiumi.py doctor --browser edge --profile output/codex/doctor-profile --headless --report output/codex/doctor.json

# 3. 新建草稿、内部模型写入、保存、新标签重开核验
python scripts/codex_xiumi.py publish examples/codex-sample.html --title "Codex 测试稿" --browser edge --profile output/codex/profile --report output/codex/publish.json

# 4. 只读复查已经保存的草稿（替换为报告中的实际 URL）
python scripts/codex_xiumi.py verify examples/codex-sample.html --title "Codex 测试稿" --draft-url "实际秀米草稿URL" --browser edge --profile output/codex/profile --report output/codex/verify.json
```

首次登录由用户在专用浏览器窗口完成，程序自动检测，不调用终端 input()。无头未登录会返回 needs_login；请去掉 --headless 完成可见登录。命令结束关闭该浏览器，保留专用 profile；不要使用日常浏览器 profile，也不要并发运行同一 profile。

默认复用本 checkout 的解析与模型函数；`--upstream <完整源码目录>` 可显式选择另一个已审查版本。每次 report 使用不同文件名。生成的 JSON、截图、事件日志、WebDriver 日志保存在报告旁；包含正文/本机路径，留在 output 下，不公开提交。

## 输入与核验

- 指定 HTML 是唯一正文来源，不自动读取同名 Markdown。需要成对的顶层 section；section 的行内 CSS 进入 txt1.style，内部 HTML 进入 txt1.text。嵌套 section/div 按上游规则展平。
- 不解析 style 样式表或外部 CSS；含脚本、事件属性、可执行 URL 等输入会拒绝。prepare 检查分块是否丢失文字/图片，不能把任意网页直接当作受支持输入。
- CSS 背景必须先取得 HTTPS 地址，不含 `&`、`;` 等上游解析歧义字符；本地 img 在 publish 中交给上游上传成 CDN URL。上传后 verify 需使用含实际 HTTPS URL 的 HTML。本轮线上实测没有覆盖正文 img 上传分支。
- publish 只接受新建编辑器，避免覆盖已有稿；模型写入失败不会自动退回普通粘贴。保存前、保存重开后都核对组件数、文字、行内/章节样式、图片与渲染状态。
- 保存时秀米可能把背景 HTTPS 地址改为协议相对地址。核验只等价化这两种协议表示，仍检查路径与查询参数。CSS 背景实际加载、视觉效果及微信手机预览需人工检查。

| status | 含义 |
| --- | --- |
| prepared | 离线检查通过，尚未入稿 |
| browser_ready | 浏览器空白页诊断通过，尚未入稿 |
| verified | 报告范围内保存重开检查通过 |
| verified_with_edit_normalization | 改字测试保存重开成功，但 CSS 被编辑器规范化 |
| verification_failed / error | 本轮没有通过；查看 stage/error/checks |

`--edit-probe` 只用于明确授权的专用测试稿，会追加 `【Codex可编辑复核】` 并再次保存重开。正式文案普通核验不要使用它。秀米可能在编辑后把字号改为百分比或调整段落间距，报告会记录 edit_style_changes，不把改字成功称为完整样式无损。

失败已有 draft_url 时先 verify 复查，避免再次 publish 生成重复稿。未保存内容恢复提示会让普通核验停止，先由用户处理；不能把本地恢复内容当作服务器保存结果。沙箱导致浏览器 tab crashed 时通过宿主正常权限机制执行，不能用关闭安全机制的启动参数解决。

## 验证与后续 harness

```powershell
python -m unittest discover -s tests -v
```

离线测试不需要 Selenium 或已登录的浏览器。CLI 与模型品牌无关，OpenCode/ZCode 等 harness 可以调用相同命令并读取 JSON 状态；但技能目录发现、进程轮询、权限升级与登录交接各有差异，目前没有对应平台实测，不标为已支持。后续先接入 prepare/doctor，再用独立测试稿完成 publish/verify 的保存重开验收。

原 Claude Code skill 与 `scripts/publish_xiumi_draft.py` 保留原有行为；该文档的自动登录检测、报告与严格核验仅适用于 Codex 新入口。此项目使用秀米内部模型而非官方稳定 API，站点或上游私有函数变更后需要重新审查与实测。
