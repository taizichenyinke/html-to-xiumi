---
name: html-to-xiumi
description: Publish a local HTML file (or an HTML + Markdown pair) into a Xiumi 秀米 draft automatically. Use when a finished HTML design needs to become a saved Xiumi editor draft — with original inline styles preserved (backgrounds, gradients, borders, fonts) when requested. Focuses on the single publish step; does not crawl or generate content.
---

# HTML to Xiumi Draft

## Purpose

Take a finished local HTML file and turn it into a saved Xiumi (秀米) editor draft, keeping the source design's inline styles where possible. Supports two paths:

- **Paste path (default)** — feed the HTML to Xiumi's paste handler. Simple, but the handler strips inline styles (only `text-align:justify` survives).
- **`--preserve-styles` model-build path** — write styles directly into the Angular comp model so colors/backgrounds/gradients/borders/fonts survive render, save, and exported preview verbatim.

## Commands

### Basic publish (paste path)

```powershell
python scripts/publish_xiumi_draft.py path/to/your.html --title "推送标题" --author "作者"
```

### Publish an HTML + Markdown pair

When a sibling `.md` exists it is auto-detected; pass `--markdown` to force a specific one:

```powershell
python scripts/publish_xiumi_draft.py output/xxx/wanyou_xxx.html --markdown output/xxx/wanyou_xxx.md --title "推送标题"
```

### Preserve the source design styles (model-build path)

```powershell
python scripts/publish_xiumi_draft.py path/to/your.html --title "推送标题" --preserve-styles --no-base-format
```

- `--preserve-styles` keeps the source design's inline styles by building `comps.items` in the model directly.
- `--no-base-format` avoids the default 14px/18px normalization that squashes custom large typography.
- In this mode local images are pasted to trigger Xiumi's own upload, then inlined as **CDN URLs** (`img.xiumi.us/...`) inside the text comp — these persist through save, unlike `data:` URLs (see Pitfalls).

### Dry run (fill editor but do not click save)

```powershell
python scripts/publish_xiumi_draft.py path/to/your.html --title "推送标题" --dry-run
```

### Browser / profile options

```powershell
python scripts/publish_xiumi_draft.py path/to/your.html --title "推送标题" --profile-dir output/selenium_cache/my-xiumi-profile --home-url "https://xiumi.us/studio/v5?lang=zh_CN#/"
```

- `--profile-dir` keeps the login session across runs. Without it, the browser profile is cleaned up after the browser closes.
- The script keeps the browser open after save for manual verification; press Enter in the terminal to close it.

## Environment

Windows PowerShell does not inherit bash env vars — set these on every command:

```powershell
$env:WANYOU_SELENIUM_BROWSER='chrome'; $env:PYTHONIOENCODING='utf-8'
```

Xiumi image handling is controlled by `XIUMI_IMAGE_MODE` in `.env`:

| `XIUMI_IMAGE_MODE` | Behavior |
|---|---|
| `upload` (default) | Upload local images to the Xiumi gallery, rewrite URLs, then apply layout. |
| `inline` | Convert local images to base64 data URLs inline. Larger HTML but no upload step. |
| `auto` | Try inline; fall back to omit if HTML exceeds `XIUMI_MAX_INLINE_IMAGE_HTML_CHARS`. |
| `omit` | Remove all images and leave placeholders. |

## Xiumi Editor Publish Pitfalls (verified against real drafts)

Read before touching editor-write logic in `scripts/publish_xiumi_draft.py`.

### Direct innerHTML injection saves but never renders → empty draft

The Xiumi editor is an Angular app. The rendering layer is `comps.items`; content injected via `innerHTML=` or `scope.cell.text=` lands in `_qiBlock.items` (frozen layer — it saves but never renders). Symptom: save reports success but the body opens empty.

**Fix: trusted paste.** `navigator.clipboard.write([new ClipboardItem({'text/html': blob, 'text/plain': blob})])` → focus `[contenteditable]` → CDP `Input.dispatchKeyEvent` Ctrl+V (`modifiers:2, key:"v", code:"KeyV", windowsVirtualKeyCode:86`). This makes Xiumi's own paste handler build rendering-layer components under `comps.items`.

### Paste handler strips all inline styles

Only `text-align:justify` survives; `<h1>/<h2>/<h3>` map to semantic font-size 180%/140%/120%; adjacent blocks merge into ONE text component. Paste cannot preserve colors/backgrounds/borders. To keep the full source design, use `--preserve-styles` above.

### data: image URLs get stripped after save; CDN URLs persist

A `data:image/...` URL written into a text comp's model renders in the editor but its `src` is stripped on save (reopening shows `<img src>` empty). Workaround: paste a fragment containing the data URL so Xiumi's own paste handler uploads it, read back the resulting `//img.xiumi.us/xmi/ua/...` URL from the generated image comp, then inline that **CDN URL** into the text comp. CDN URLs persist through save and reopen.

### Clear-then-paste is idempotent, but re-pasting identical content clears the draft

Clear = Ctrl+A + Delete, then re-paste; only the last content survives. Gotcha: when the HTML has no images, `final_html == text_first_html`, so the second clear+paste wipes the already-rendered content → empty draft. `_fill_xiumi_body_then_images` guards with `if final_html != text_first_html:` to skip the second paste.

### Preserve-styles comp schema

Each TOP-LEVEL `<section>` of the source becomes one block:

- The section's inline CSS (camelCased) → `comps.items[].txt1.style`
- The inner HTML (paragraphs/spans with their inline styles) → `txt1.text`
- Convert nested `<section>`/`<div>` to `<p>` (keep their style; the browser's HTML parser auto-closes nested `<p>`), drop empty `<p></p>` artifacts.

Comp schema:

```python
{
  "_comp": {
    "constraint": {"opMenu": {"text-merged": True}, "pose": {"resize": "h"}},
    "pose": {"position": "static", "width": None, "height": None},
    "style": {},
    "tplId": "paper-cp:header/1-txt-normal",
    "_$uuid": "comp-xxx",
  },
  "txt1": {"type": "text", "text": "<p style=...>...</p>", "style": {"camelCase CSS"}},
}
```

Reach the model:

```javascript
window.angular.element(contenteditable).scope()._$.pages[0].layers[0].comps.items
```

### Persistent-profile recover dialog blocks the editor

The editor may pop a "上次没有保存到服务器，是否恢复?" dialog that blocks editing. It must be dismissed (click 取消/确定). Handled automatically by `_dismiss_xiumi_recover_dialog`.

## Debug Rules

- If login fails or is not detected, look for `output/xiumi_debug/*.jsonl` for login/upload diagnostics. The browser is kept open on error — check the browser window directly.
- If the editor enters but text is not applied, the `contenteditable` / Angular scope detection may need updating — check `xiumi_body_text_model_applied` in the debug log.
- If image upload fails for all images (consecutive failures >= `XIUMI_IMAGE_UPLOAD_MAX_FAILURES`), the script aborts image upload and leaves placeholders.
- If individual images fail to upload, they are skipped and replaced with a "[配图上传未完成]" placeholder rather than blocking the whole draft.
- If the editor save state is "uncertain", the draft may still have been saved — check the editor URL in the browser. The browser window stays open after save for manual verification.
- Use `--dry-run` to test without saving, avoiding orphan drafts in Xiumi.
- `output/xiumi_debug/*.jsonl` is the primary diagnostics target. Look there before changing `scripts/publish_xiumi_draft.py`.
