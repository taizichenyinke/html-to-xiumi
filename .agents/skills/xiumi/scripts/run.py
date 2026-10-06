"""Locate the checkout from this skill, independently of the working directory."""
import importlib.util
import json
from pathlib import Path
import sys

SKILL = Path(__file__).resolve().parents[1]


def main(argv=None):
    settings_path = SKILL / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    root = Path(settings.get("upstream", str(Path(__file__).resolve().parents[4]))).resolve()
    source = root / "scripts" / "codex_xiumi.py"
    if not source.is_file():
        print("找不到 Codex 执行器；请重新运行仓库的 scripts/install_codex_skill.py 或修正 settings.json", file=sys.stderr)
        return 1
    spec = importlib.util.spec_from_file_location("codex_xiumi", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"prepare", "doctor", "publish", "verify"}:
        defaults = {} if args[0] == "doctor" else {"--upstream": root}
        if args[0] != "prepare":
            for key in ("browser", "driver", "profile"):
                if settings.get(key):
                    defaults["--" + key] = settings[key]
        for key, value in defaults.items():
            if not any(a == key or a.startswith(key + "=") for a in args):
                args.extend([key, str(value)])
    return module.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
