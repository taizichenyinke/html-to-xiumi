"""Codex CLI adapter reusing this repository's original Xiumi model writer.

Offline preparation extracts parser functions without importing Selenium.
Live execution calls publish_xiumi_draft.py and verifies the reopened draft.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import html
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

HOME_URL = "https://xiumi.us/studio/v5?lang=zh_CN#/"
ROOT = Path(__file__).resolve().parents[1]
PARSER_FUNCTIONS = {"_extract_main_html", "_xiumi_camelize_css", "_xiumi_flatten_inner_html", "_xiumi_html_to_blocks"}


class BridgeError(ValueError):
    pass


def upstream_source(root: Path) -> Path:
    source = root.resolve() / "scripts" / "publish_xiumi_draft.py"
    if not source.is_file():
        raise BridgeError(f"缺少上游脚本：{source}")
    return source


def parser_functions(root: Path) -> dict:
    source = upstream_source(root)
    tree = ast.parse(source.read_text(encoding="utf-8"))
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in PARSER_FUNCTIONS]
    if {n.name for n in selected} != PARSER_FUNCTIONS:
        raise BridgeError("上游解析函数发生变化，请重新审查该版本")
    namespace = {"re": re, "_XIUMI_WS": re.compile(r"\s+")}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


def normalized_text(value: str) -> str:
    return re.sub(r"[\s\u200b\ufeff]+", "", value)


def canonical_url(value: str) -> str:
    return "https:" + value if value.startswith("//") else value


def canonical_css(value: str) -> str:
    # Xiumi rewrites persistent CDN URLs as protocol-relative on save.
    # Compare their meaning on its HTTPS editor, without ignoring any URL path/query.
    return re.sub(r"url\(\s*([\"']?)(.*?)\1\s*\)",
                  lambda m: "url(" + canonical_url(m.group(2)) + ")", str(value).strip())


class HtmlInput(HTMLParser):
    """Normalize image attributes and CSS URLs without executing source HTML."""
    def __init__(self, base: Path):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.parts: list[str] = []
        self.text: list[str] = []
        self.images: list[str] = []
        self.local_images: dict[str, Path] = {}
        self.warnings: list[str] = []
        self.section_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "iframe", "object", "embed", "style", "link", "base", "form", "svg"}:
            raise BridgeError(f"不支持 <{tag}>；请提供使用行内样式的静态 HTML")
        values = dict(attrs)
        for key, value in values.items():
            if key.startswith("on") or key == "srcdoc":
                raise BridgeError(f"不支持可执行属性 {key}")
            if value and re.search(r"(?:javascript|vbscript)\s*:", value, re.I):
                raise BridgeError("不支持可执行 URL")
        style = values.get("style", "") or ""
        if re.search(r"expression\s*\(|@import|behavior\s*:", style, re.I):
            raise BridgeError("不支持可执行 CSS")

        def css_url(match):
            url = match.group(1).strip().strip("\"'")
            if not url.startswith("https://") or re.search(r"[\s&;\"'()<>\\]", url):
                raise BridgeError("CSS 背景必须为不含 & 或 ; 等解析歧义字符的 HTTPS 地址；请先上传本地背景")
            return f"url({url})"

        if style:
            values["style"] = re.sub(r"url\((.*?)\)", css_url, style, flags=re.I)
        if tag == "section":
            if self.section_depth == 0 and re.search(r"[\"'&]", values.get("style", "") or ""):
                raise BridgeError("顶层 section 样式含上游无法可靠解析的引号或 &；请简化该 CSS 值")
            if self.section_depth:
                self.warnings.append("嵌套 section 会按上游规则展平为 p，需人工检查布局")
            self.section_depth += 1
        if tag == "img":
            src = values.get("src", "") or ""
            if not src or values.get("srcset"):
                raise BridgeError("图片必须有唯一 src，不支持 srcset")
            if src.startswith("//"):
                src = "https:" + src
            if not src.startswith("https://"):
                if re.match(r"(?:data|file|https?):", src, re.I):
                    raise BridgeError("图片使用 HTTPS 地址或本地文件路径，不接受 data/file/HTTP URL")
                path = (self.base / src).resolve()
                if not path.is_file():
                    raise BridgeError(f"本地图片不存在：{path}")
                self.local_images[src] = path
            values["src"] = src
            self.images.append(src)
        if tag == "div":
            self.warnings.append("内层 div 按上游规则转换成 p；复杂布局需人工视觉验收")
        self.parts.append("<" + tag + "".join(
            f' {key}="{html.escape(value or "", quote=True)}"' for key, value in values.items()) + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag == "section":
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "section":
            self.section_depth -= 1
            if self.section_depth < 0:
                raise BridgeError("section 标签不成对")
        self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        self.parts.append(html.escape(data, quote=False))
        self.text.append(data)


def prepare(source: Path, root: Path) -> dict:
    functions = parser_functions(root)
    raw = source.read_text(encoding="utf-8-sig")
    if re.search(r"<(?:style|link)\b", raw, re.I):
        raise BridgeError("请先将 style/外部 CSS 转为行内样式；模型写入不读取样式表")
    fragment = functions["_extract_main_html"](raw)
    parsed = HtmlInput(source.resolve().parent)
    parsed.feed(fragment)
    if parsed.section_depth:
        raise BridgeError("section 标签未闭合")
    content = "".join(parsed.parts)
    blocks = functions["_xiumi_html_to_blocks"](content)
    if not blocks:
        raise BridgeError("未找到完整的顶层 section，拒绝创建空稿")
    flattened = HtmlInput(source.resolve().parent)
    flattened.feed("".join(block["text"] for block in blocks))
    if normalized_text("".join(parsed.text)) != normalized_text("".join(flattened.text)):
        raise BridgeError("上游分块会丢失 section 外的正文，拒绝写入")
    if parsed.images != flattened.images:
        raise BridgeError("上游分块会丢失或重排图片，拒绝写入")
    return {
        "status": "prepared", "mode": "internal-model", "source": str(source.resolve()),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "upstream_sha256": hashlib.sha256(upstream_source(root).read_bytes()).hexdigest(),
        "html": content, "blocks": blocks, "local_images": {k: str(v) for k, v in parsed.local_images.items()},
        "warnings": sorted(set(parsed.warnings)), "scope": "offline only; no browser or draft writes",
    }


def load_upstream(root: Path):
    source = upstream_source(root)
    sys.path.insert(0, str(root.resolve()))
    spec = importlib.util.spec_from_file_location("xiumi_external_publisher", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_login_waiter(upstream, *, headless: bool):
    """Never inherit upstream's input() prompt inside a Codex PTY."""
    def wait(browser, timeout):
        if headless:
            raise BridgeError("needs_login: 当前无头会话未登录；去掉 --headless 后由用户登录")
        links = upstream._visible_login_links(browser)
        if links:
            links[0].click()
        print("请在专用浏览器窗口完成秀米登录；程序自动检测，无需在终端按回车。", flush=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if upstream._xiumi_login_state(browser).get("authenticated"):
                return True
            time.sleep(1)
        return False
    upstream._wait_for_manual_login = wait


def make_browser(name: str, profile: Path, driver: Path | None, headless: bool, log: Path):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.edge.service import Service as EdgeService
    profile.mkdir(parents=True, exist_ok=True)
    options = webdriver.EdgeOptions() if name == "edge" else webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile.resolve()}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    if headless:
        options.add_argument("--headless=new")
    options.page_load_strategy = "eager"
    service_type = EdgeService if name == "edge" else ChromeService
    service = service_type(executable_path=str(driver.resolve()) if driver else None, log_output=str(log))
    constructor = webdriver.Edge if name == "edge" else webdriver.Chrome
    browser = constructor(options=options, service=service)
    browser.set_page_load_timeout(45)
    browser.set_window_size(1280, 1000)
    return browser


SNAPSHOT_JS = r"""
const visible = [...document.querySelectorAll('[contenteditable="true"]')].filter(e => e.offsetWidth > 0);
let scope;
for (const el of visible) {
  for (let node = el; node; node = node.parentElement) {
    const s = window.angular && window.angular.element(node).scope();
    if (s && s._$ && s._$.pages && s._$.pages[0]?.layers?.[0]?.comps?.items) { scope = s; break; }
  }
  if (scope) break;
}
if (!scope) return {ready:false};
const items = scope._$.pages[0].layers[0].comps.items;
function signature(value) {
  const el = document.createElement('div'); el.innerHTML = value;
  return {text:el.textContent.replace(/[\s\u200b\ufeff]+/g,''),
    images:[...el.querySelectorAll('img')].map(i=>i.getAttribute('src')),
    inline:[...el.querySelectorAll('[style]')].map(n=>({tag:n.tagName, style:n.style.cssText}))};
}
function block(value) { return {style:value.style || {}, ...signature(value.text || '')}; }
return {ready:true, title:document.querySelector('input.title')?.value,
  component_count:items.length, blocks:items.filter(i=>i.txt1).map(i=>block(i.txt1)),
  expected:arguments[0].map(block), editable_count:visible.length,
  rendered_text:visible.map(e=>e.textContent.replace(/[\s\u200b\ufeff]+/g,'')).join(''),
  images:visible.flatMap(e=>[...e.querySelectorAll('img')].map(i=>({src:i.src,loaded:i.complete && i.naturalWidth>0}))),
  overflow:visible.some(e=>e.scrollWidth>e.clientWidth+2)};
"""


def compare_snapshot(snapshot: dict, expected_count: int, title: str) -> dict:
    checks = {"model_available": bool(snapshot.get("ready")),
              "component_count": snapshot.get("component_count") == expected_count,
              "title": snapshot.get("title") == title,
              "editable": snapshot.get("editable_count", 0) > 0,
              "no_horizontal_overflow": snapshot.get("overflow") is False}
    expected = snapshot.get("expected", [])
    actual = snapshot.get("blocks", [])
    matched_counts = len(expected) == expected_count and len(actual) == expected_count
    checks["text"] = matched_counts and all(a.get("text") == e.get("text") for a, e in zip(actual, expected))
    checks["inline_styles"] = matched_counts and all(a.get("inline") == e.get("inline") for a, e in zip(actual, expected))
    checks["text_and_inline_styles"] = len(expected) == expected_count and len(actual) == expected_count and all(
        a.get("text") == e.get("text") and a.get("inline") == e.get("inline")
        and [canonical_url(s) for s in a.get("images", [])] == [canonical_url(s) for s in e.get("images", [])]
        for a, e in zip(actual, expected))
    checks["section_styles"] = len(actual) == expected_count and len(expected) == expected_count and all(
        all(canonical_css(a.get("style", {}).get(k, "")) == canonical_css(v) for k, v in e["style"].items())
        for a, e in zip(actual, expected))
    checks["rendered_text"] = bool(expected) and snapshot.get("rendered_text") == "".join(e["text"] for e in expected)
    expected_images = [src for e in expected for src in e["images"]]
    rendered_images = snapshot.get("images", [])
    checks["rendered_images"] = [i["src"] for i in rendered_images] == expected_images and all(i["loaded"] for i in rendered_images)
    return {"passed": all(checks.values()), "checks": checks}


def snapshot_when_ready(browser, blocks: list, timeout: int = 30) -> dict:
    from selenium.webdriver.support.ui import WebDriverWait
    return WebDriverWait(browser, timeout).until(
        lambda b: (data if (data := b.execute_script(SNAPSHOT_JS, blocks)).get("ready") else False))


def verify_reopened(browser, upstream, blocks, args, result):
    """Read server-loaded state in a fresh tab, allowing images/render to settle."""
    browser.switch_to.new_window("tab")
    browser.get(result["draft_url"])
    from selenium.webdriver.support.ui import WebDriverWait
    def editor_or_recovery(b):
        state = b.execute_script("""
          const text=document.body?.innerText || '';
          return {recovery:text.includes('上次没有保存到服务器'), text,
            ready:!!document.querySelector('[contenteditable=true]')};
        """)
        if state['recovery']:
            if not args.edit_probe or args.title not in state['text']:
                raise BridgeError('发现未保存内容恢复提示；请用户处理后再核验，不能将本地恢复内容当作服务器结果')
            # Explicit edit probe owns this dedicated test draft; discard only
            # its unsaved probe changes to inspect the actual server version.
            clicked = b.execute_script("""
              const button=[...document.querySelectorAll('button')].find(e=>e.offsetWidth>0 && e.textContent.trim()==='取消');
              if(button) button.click(); return !!button;
            """)
            if not clicked:
                raise BridgeError('未找到测试稿恢复提示的取消按钮')
            result['discarded_unsaved_test_probe'] = True
            return False
        return state['ready']
    WebDriverWait(browser, 30).until(editor_or_recovery)
    upstream._wait_editor_ready(browser, 30)
    deadline = time.monotonic() + 12
    while True:
        snapshot = snapshot_when_ready(browser, blocks)
        verification = compare_snapshot(snapshot, len(blocks), args.title)
        if verification["passed"] or time.monotonic() >= deadline:
            break
        time.sleep(0.5)
    result["verification"] = verification
    result["snapshot"] = snapshot
    screenshot = args.report.resolve().with_suffix(".png")
    browser.save_screenshot(str(screenshot))
    result["screenshot"] = str(screenshot)
    result["status"] = "verified" if verification["passed"] else "verification_failed"
    result["stage"] = "complete"
    result["scope"] = "saved draft reopened in a new tab; mobile preview and edit/resave cycle not verified"


def edit_probe(browser, upstream, blocks, args, result):
    """Explicit test-only option: edit rendered text, save, and reopen again."""
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    marker = "【Codex可编辑复核】"
    result["initial_verification"] = result["verification"]
    result["stage"] = "edit_probe"
    browser.set_window_size(1280, 1000)
    target_text = result["snapshot"]["expected"][-1]["text"]
    target = browser.execute_script(r"""
      return [...document.querySelectorAll('[contenteditable=true]')].find(e=>
        e.offsetWidth>0 && e.textContent.replace(/[\s\u200b\ufeff]+/g,'')===arguments[0]);
    """, target_text)
    if not target:
        raise BridgeError("未找到可编辑组件")
    browser.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
    target.click()
    # Editor selection can replace the rendered node. Refetch the focused editor.
    target = browser.execute_script(r"""
      return [...document.querySelectorAll('[contenteditable=true]')].find(e=>
        e.offsetWidth>0 && e.textContent.replace(/[\s\u200b\ufeff]+/g,'')===arguments[0]);
    """, target_text)
    browser.execute_script("arguments[0].focus();", target)
    result["edit_target"] = browser.execute_script("return {tag:arguments[0]?.tagName,editable:arguments[0]?.isContentEditable,width:innerWidth,height:innerHeight};", target)
    target.send_keys(Keys.CONTROL, Keys.END)
    target.send_keys(marker)
    browser.find_element("css selector", "input.title").click()
    edited = copy.deepcopy(blocks)
    edited[-1]["text"] += marker
    deadline = time.monotonic() + 8
    while True:
        snapshot = snapshot_when_ready(browser, edited)
        check = compare_snapshot(snapshot, len(edited), args.title)
        if check["passed"] or time.monotonic() > deadline:
            break
        time.sleep(0.3)
    result["edit_before_save"] = check
    failed = {key for key, passed in check["checks"].items() if not passed}
    # Editing in Xiumi can normalize paragraph CSS. Record it as a limitation,
    # never call this an exact style-preserving edit or weaken normal import QA.
    normalized_edit = failed and failed <= {"inline_styles", "text_and_inline_styles"}
    unchanged_blocks = snapshot.get("blocks", [])[:-1] == result["snapshot"].get("blocks", [])[:-1]
    if not check["passed"] and not (normalized_edit and unchanged_blocks):
        result["edit_snapshot"] = snapshot
        raise BridgeError("键盘修改后的内容或样式不符，未继续保存")
    if normalized_edit:
        result["edit_style_changes"] = {"before": snapshot["expected"][-1]["inline"],
                                        "after": snapshot["blocks"][-1]["inline"],
                                        "section_after": snapshot["blocks"][-1]["style"]}
    upstream._click_save(browser)
    WebDriverWait(browser, args.save_timeout).until(lambda b: b.execute_script("""
      let s=window.angular.element(document.querySelector('button.btn-img.op-btn.save')).scope();
      while(s && typeof s.onBtnClickSave!=='function') s=s.$parent;
      return s?.undoStatus?.isDirty === false;
    """))
    result["stage"] = "edit_reopen_verify"
    verify_reopened(browser, upstream, edited, args, result)
    failed_after = {key for key, passed in result["verification"]["checks"].items() if not passed}
    if normalized_edit and failed_after and failed_after <= {"inline_styles", "text_and_inline_styles"}:
        result["status"] = "verified_with_edit_normalization"
    result["edit_probe_marker"] = marker
    result["scope"] = "saved, reopened, edited via keyboard, saved and reopened again; mobile preview not verified"


def safe_url(browser) -> str:
    try:
        return browser.current_url
    except Exception:
        return ""


def write_report(path: Path, result: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def run_live(args) -> dict:
    """Create one new draft. Never silently fall back to style-stripping paste."""
    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    result = {"status": "running", "mode": "internal-model", "stage": "prepare", "draft_url": ""}
    browser = None
    try:
        if args.command != "doctor":
            prepared = prepare(args.html, args.upstream)
            result.update({k: prepared[k] for k in ("source_sha256", "upstream_sha256", "warnings")})
            upstream = load_upstream(args.upstream)
            install_login_waiter(upstream, headless=args.headless)
            upstream._XIUMI_DEBUG_LOG_PATH = report.with_suffix(".events.jsonl")
        result["stage"] = "browser_start"
        write_report(report, result)
        browser = make_browser(args.browser, args.profile, args.driver, args.headless, report.with_suffix(".webdriver.log"))
        result["browser_version"] = browser.capabilities.get("browserVersion")
        if args.command == "doctor":
            browser.get("about:blank")
            result.update(status="browser_ready", stage="complete", scope="about:blank only; no Xiumi writes")
            return result
        if args.command == "verify":
            if not re.search(r"^https://xiumi\.us/studio/v5.*#/paper/for/\d+/", args.draft_url):
                raise BridgeError("verify 仅接受已有的 https://xiumi.us/studio/v5#/paper/for/<数字>/ 草稿地址")
            if prepared["local_images"]:
                raise BridgeError("核验含本地图片的稿件时，请提供上传后含 HTTPS 图片 URL 的 HTML")
            result.update(stage="reopen_verify", draft_url=args.draft_url)
            write_report(report, result)
            verify_reopened(browser, upstream, prepared["blocks"], args, result)
            if result["status"] == "verified" and args.edit_probe:
                edit_probe(browser, upstream, prepared["blocks"], args, result)
            return result
        result["stage"] = "login_and_new_draft"
        write_report(report, result)
        print("正在打开独立浏览器；如显示登录页，请在该浏览器中登录秀米。", flush=True)
        upstream._open_xiumi_editor(browser, HOME_URL, args.login_timeout, 30)
        # The upstream UI locator may land on an existing editor. Refuse to replace it.
        if not re.search(r"/paper/for/new(?:[/#?]|$)", safe_url(browser)):
            raise BridgeError("编辑器不是新建草稿，停止以避免覆盖现有文章")
        result["stage"] = "upload_images"
        content = prepared["html"]
        for src, path in prepared["local_images"].items():
            url = upstream._paste_image_get_cdn_url(browser, upstream._image_file_to_data_url(Path(path)))
            if not url:
                raise BridgeError(f"图片上传未得到持久 URL：{src}")
            if url.startswith("//"):
                url = "https:" + url
            content = content.replace(f'src="{html.escape(src, quote=True)}"', f'src="{html.escape(url, quote=True)}"')
        blocks = upstream._xiumi_html_to_blocks(content)
        result["stage"] = "model_write"
        write_report(report, result)
        upstream._fill_xiumi_fields(browser, args.title, args.author, "", "")
        upstream._paste_xiumi_html(browser, "<section><p>seed</p></section>")
        snapshot_when_ready(browser, blocks)
        if not upstream._build_xiumi_comps_from_blocks(browser, blocks):
            raise BridgeError("Angular comps.items 写入失败；未退回普通粘贴")
        if not upstream._mark_xiumi_document_dirty(browser).get("applied"):
            raise BridgeError("未能标记文稿待保存")
        before = snapshot_when_ready(browser, blocks)
        result["before_save"] = compare_snapshot(before, len(blocks), args.title)
        if not result["before_save"]["passed"]:
            result["before_snapshot"] = before
            raise BridgeError("保存前读回不符，停止保存")
        result["stage"] = "save"
        write_report(report, result)
        upstream._click_save(browser)
        from selenium.webdriver.support.ui import WebDriverWait
        url = WebDriverWait(browser, args.save_timeout).until(
            lambda b: (u if re.search(r"^https://xiumi\.us/studio/v5.*#/paper/for/\d+/", u := safe_url(b)) else False))
        result["draft_url"] = url
        result["stage"] = "reopen_verify"
        write_report(report, result)
        verify_reopened(browser, upstream, blocks, args, result)
        if result["status"] == "verified" and args.edit_probe:
            edit_probe(browser, upstream, blocks, args, result)
    except (Exception, KeyboardInterrupt) as exc:
        result.update(status="error", error=f"{type(exc).__name__}: {exc}", editor_url=safe_url(browser))
        if browser:
            try:
                browser.save_screenshot(str(report.with_suffix(".error.png")))
            except Exception:
                pass
    finally:
        if browser:
            try:
                browser.quit()
            except Exception:
                pass
        write_report(report, result)
    return result


def main(argv=None) -> int:
    import argparse
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="通过 html-to-xiumi 内部模型写入并重开核验秀米草稿")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "doctor", "publish", "verify"):
        cmd = sub.add_parser(command)
        cmd.add_argument("--report", type=Path, required=True)
        if command != "doctor":
            cmd.add_argument("html", type=Path)
            cmd.add_argument("--upstream", type=Path, default=ROOT, help="html-to-xiumi 完整源码目录；默认使用此仓库")
        if command != "prepare":
            cmd.add_argument("--browser", choices=("edge", "chrome"), default="edge")
            cmd.add_argument("--driver", type=Path)
            cmd.add_argument("--profile", type=Path, required=True, help="专用浏览器 profile，不使用日常浏览器目录")
            cmd.add_argument("--headless", action="store_true")
        if command in {"publish", "verify"}:
            cmd.add_argument("--title", required=True)
            cmd.add_argument("--save-timeout", type=int, default=45)
            cmd.add_argument("--edit-probe", action="store_true", help="仅用于测试稿：追加复核标记，保存后再次重开；会修改正文")
        if command == "verify":
            cmd.add_argument("--draft-url", required=True)
        if command == "publish":
            cmd.add_argument("--author", default="")
            cmd.add_argument("--login-timeout", type=int, default=300)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        try:
            result = prepare(args.html, args.upstream)
        except Exception as exc:
            result = {"status": "error", "stage": "prepare", "error": f"{type(exc).__name__}: {exc}"}
        write_report(args.report, result)
    else:
        result = run_live(args)
    print(json.dumps({k: v for k, v in result.items() if k not in {"html", "blocks", "snapshot", "before_snapshot", "edit_snapshot"}}, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"prepared", "browser_ready", "verified", "verified_with_edit_normalization"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
