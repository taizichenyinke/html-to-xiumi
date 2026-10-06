Python 3.11+；在线命令需要仓库 requirements.txt 中的 Selenium、已安装的 Edge/Chrome 和对应驱动。prepare 仅依赖 Python 标准库，无浏览器操作。

仓库 skill 不依赖 cwd；用本技能 scripts/run.py 的绝对路径启动。个人安装需保留源码 checkout，settings.json 中 upstream 指向它，python 是安装时的解释器。若 checkout 或虚拟环境移动，重新安装或修正路径。可选设置 browser、driver、profile；命令行参数优先。首次无头运行可能没有有效登录态，应去掉 --headless 由用户登录。

完整参数：`python <run.py绝对路径> --help`；子命令为 prepare、doctor、publish、verify。所有子命令需要 --report；在线命令还需 --profile，默认 browser=edge；--driver 可省略，由 Selenium Manager 查找对应驱动。publish 和 verify 需要 --title；verify 还需 --draft-url。详细说明在源码 checkout 的 docs/codex.md。

错误恢复：prepared/browser_ready 只表示离线或浏览器诊断通过。报告会记录失败 stage/error、源码 SHA256 和已知草稿链接；有链接时先 verify。发现未保存内容恢复提示时普通核验会停止，先让用户处理，不能把本地恢复版本当作服务器保存结果。不要重复运行仍在等待登录的 publish。

报告、截图、事件日志和专用浏览器 profile 包含正文或登录会话，留在用户 output 目录，不提交到公开仓库。普通 verify 不改正文；--edit-probe 仅对明确授权的专用测试稿追加标记并再次保存。模型或核验失败不会自动切换到丢样式的粘贴流程。
