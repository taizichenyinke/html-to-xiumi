"""Install the repository's Codex skill without copying browser sessions."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def install(destination: Path, replace: bool = False):
    destination = destination.expanduser().resolve()
    if destination.exists() and not replace:
        raise ValueError(f"技能目录已存在：{destination}；确认更新时显式使用 --replace")
    source = ROOT / ".agents" / "skills" / "xiumi"
    if destination == source.resolve() or source.resolve() in destination.parents:
        raise ValueError("安装目录不能位于技能源码目录中")
    if not (ROOT / "scripts" / "codex_xiumi.py").is_file():
        raise ValueError("缺少执行器，请保留完整源码 checkout")
    settings_path = destination / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    shutil.copytree(source, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "settings.json"))
    settings.update(upstream=str(ROOT), python=sys.executable)
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description="安装个人 xiumi Codex skill，保留源码 checkout 作为执行依赖")
    codex_dir = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--destination", type=Path, default=codex_dir / "skills" / "xiumi")
    parser.add_argument("--replace", action="store_true", help="明确更新已存在的 xiumi skill；保留浏览器路径设置")
    args = parser.parse_args(argv)
    try:
        path = install(args.destination, args.replace)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"已安装：{path}\n执行器依赖：{ROOT}\n请在 Codex 新会话中检查 xiumi skill。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
