import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from codex_xiumi import BridgeError, HtmlInput, compare_snapshot, install_login_waiter, prepare, run_live, safe_url


class InputTests(unittest.TestCase):
    def test_real_parser_preserves_sections_text_and_styles(self):
        result = prepare(ROOT / "examples/codex-sample.html", ROOT)
        self.assertEqual(result["status"], "prepared")
        self.assertEqual(len(result["blocks"]), 2)
        self.assertEqual(result["blocks"][0]["style"]["backgroundColor"], "#f2f6f4")
        self.assertIn("可编辑的秀米文章", result["blocks"][0]["text"])
        self.assertIn("font-size:24px", result["blocks"][0]["text"])

    def test_rejects_lost_text_images_and_unpaired_sections(self):
        cases = ("<p>没有章节</p>", "<p>丢失</p><section><p>保留</p></section>",
                 '<img src="https://example.com/a.png"><section><p>文字</p></section>',
                 "<section><p>未闭合</p>", "</section><section><p>错误</p></section>")
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "input.html"
            for content in cases:
                with self.subTest(content=content):
                    source.write_text(content, encoding="utf-8")
                    with self.assertRaises(BridgeError):
                        prepare(source, ROOT)

    def test_sibling_markdown_never_overrides_html(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "input.html"
            source.write_text("<section><p>指定 HTML</p></section>", encoding="utf-8")
            source.with_suffix(".md").write_text("不应读取此文", encoding="utf-8")
            self.assertIn("指定 HTML", prepare(source, ROOT)["blocks"][0]["text"])

    def test_quoted_background_url_and_local_image_normalize(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            image = base / "image.png"
            image.write_bytes(b"local-image-fixture")
            reader = HtmlInput(base)
            reader.feed('<section style="background-image:url(\'https://example.com/paper.png\')"><img src=\'image.png\'></section>')
            self.assertIn("url(https://example.com/paper.png)", "".join(reader.parts))
            self.assertIn('src="image.png"', "".join(reader.parts))
            self.assertEqual(reader.local_images["image.png"], image)

    def test_rejects_executable_css_and_unresolvable_assets(self):
        cases = ('<script>alert(1)</script>', '<p onclick="a()">文字</p>',
                 '<img src="missing.png">', '<img src="data:image/png;base64,123">',
                 '<section style="background:url(local.png)">',
                 '<section style="background:url(https://example.com/a?x=1&amp;y=2)">',
                 '<p style="width:expression(alert(1))">文字</p>')
        for content in cases:
            with self.subTest(content=content), self.assertRaises(BridgeError):
                HtmlInput(ROOT).feed(content)


class VerificationTests(unittest.TestCase):
    def setUp(self):
        block = {"text": "测试", "images": [], "inline": [{"tag": "P", "style": "color: red;"}],
                 "style": {"backgroundColor": "#abcdef"}}
        self.snapshot = {"ready": True, "title": "标题", "component_count": 1,
                         "blocks": [copy.deepcopy(block)], "expected": [copy.deepcopy(block)],
                         "editable_count": 1, "rendered_text": "测试", "images": [], "overflow": False}

    def test_saved_content_passes_only_when_all_checks_pass(self):
        self.assertTrue(compare_snapshot(self.snapshot, 1, "标题")["passed"])
        for key, value in (("text", "错误"), ("style", {}), ("inline", [])):
            changed = copy.deepcopy(self.snapshot)
            changed["blocks"][0][key] = value
            self.assertFalse(compare_snapshot(changed, 1, "标题")["passed"])
        self.snapshot["rendered_text"] = ""
        self.assertFalse(compare_snapshot(self.snapshot, 1, "标题")["passed"])

    def test_background_protocol_is_equivalent_but_path_and_query_are_checked(self):
        self.snapshot["expected"][0]["style"]["backgroundImage"] = "url(https://example.com/a.png?x=1)"
        self.snapshot["blocks"][0]["style"]["backgroundImage"] = "url(//example.com/a.png?x=1)"
        self.assertTrue(compare_snapshot(self.snapshot, 1, "标题")["passed"])
        for address in ("url(//example.com/b.png?x=1)", "url(//example.com/a.png?x=2)"):
            self.snapshot["blocks"][0]["style"]["backgroundImage"] = address
            self.assertFalse(compare_snapshot(self.snapshot, 1, "标题")["passed"])

    def test_empty_extra_or_noneditable_results_fail(self):
        self.assertFalse(compare_snapshot({}, 1, "标题")["passed"])
        for key, value in (("component_count", 2), ("editable_count", 0), ("overflow", True)):
            changed = copy.deepcopy(self.snapshot)
            changed[key] = value
            self.assertFalse(compare_snapshot(changed, 1, "标题")["passed"])

    def test_loaded_images_are_required(self):
        self.snapshot["expected"][0]["images"] = ["https://example.com/image.png"]
        self.snapshot["blocks"][0]["images"] = ["//example.com/image.png"]
        self.snapshot["images"] = [{"src": "https://example.com/image.png", "loaded": False}]
        self.assertFalse(compare_snapshot(self.snapshot, 1, "标题")["passed"])
        self.snapshot["images"][0]["loaded"] = True
        self.assertTrue(compare_snapshot(self.snapshot, 1, "标题")["passed"])

    def test_headless_login_fails_and_visible_login_never_reads_stdin(self):
        upstream = Mock()
        install_login_waiter(upstream, headless=True)
        with self.assertRaisesRegex(BridgeError, "needs_login"):
            upstream._wait_for_manual_login(Mock(), 300)
        install_login_waiter(upstream, headless=False)
        upstream._visible_login_links.return_value = []
        upstream._xiumi_login_state.return_value = {"authenticated": True}
        with patch("builtins.input", side_effect=AssertionError("must not read stdin")):
            self.assertTrue(upstream._wait_for_manual_login(Mock(), 1))

    def test_browser_crash_writes_error_report_and_closes_browser(self):
        with tempfile.TemporaryDirectory() as temp:
            args = SimpleNamespace(command="doctor", report=Path(temp) / "report.json", browser="edge",
                                   profile=Path(temp) / "profile", driver=None, headless=True)
            browser = Mock()
            browser.capabilities = {"browserVersion": "test"}
            browser.current_url = ""
            browser.get.side_effect = RuntimeError("tab crashed")
            with patch("codex_xiumi.make_browser", return_value=browser):
                result = run_live(args)
            self.assertEqual(result["status"], "error")
            self.assertEqual(json.loads(args.report.read_text(encoding="utf-8"))["status"], "error")
            browser.quit.assert_called_once()

    def test_dead_browser_does_not_mask_original_error(self):
        class DeadBrowser:
            @property
            def current_url(self):
                raise RuntimeError("dead session")
        self.assertEqual(safe_url(DeadBrowser()), "")


class PortabilityTests(unittest.TestCase):
    def run_command(self, args, cwd):
        completed = subprocess.run([sys.executable, "-X", "utf8", *map(str, args)], cwd=cwd,
                                   capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        return completed

    def test_checkout_and_installed_skill_work_outside_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            external = Path(temp)
            sample = ROOT / "examples/codex-sample.html"
            for launcher in (ROOT / "scripts/codex_xiumi.py", ROOT / ".agents/skills/xiumi/scripts/run.py"):
                report = external / "report.json"
                self.run_command([launcher, "prepare", sample, "--report", report], external)
                self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["status"], "prepared")
            destination = external / "skills/xiumi"
            installer = ROOT / "scripts/install_codex_skill.py"
            self.run_command([installer, "--destination", destination], external)
            settings = json.loads((destination / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(settings["upstream"]), ROOT)
            self.run_command([destination / "scripts/run.py", "prepare", sample, "--report", external / "installed.json"], external)
            self.assertEqual(json.loads((external / "installed.json").read_text(encoding="utf-8"))["status"], "prepared")
            settings["browser"] = "chrome"
            (destination / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
            refused = subprocess.run([sys.executable, str(installer), "--destination", str(destination)], capture_output=True)
            self.assertNotEqual(refused.returncode, 0)
            self.run_command([installer, "--destination", destination, "--replace"], external)
            self.assertEqual(json.loads((destination / "settings.json").read_text(encoding="utf-8"))["browser"], "chrome")


if __name__ == "__main__":
    unittest.main()
