import html
import os
import re
from pathlib import Path
from typing import List, Tuple

from generators.h5_generator import FOOTER_LINE, HEADER_SUBTITLE_LINE, HEADER_TITLE_LINE, SECTION_LEADS
from wanyou.image_paths import clean_markdown_image_target, is_remote_or_data_image, resolve_existing_image_path

THEME_BADGE_ALTS = {"物理系风格标识", "物理系风格标识-页尾"}
TIME_LABELS = {"日期", "时间", "发布日期", "报告时间", "截止时间", "活动时间", "演出时间", "开票时间"}
META_LABELS = {
    "日期",
    "时间",
    "地点",
    "票价",
    "发布日期",
    "报告时间",
    "报告地点",
    "报告人",
    "来源公众号",
    "作者",
    "链接",
    "摘要",
    "报告摘要",
    "截止时间",
    "活动时间",
}

PAGE_STYLE = "margin:0 auto;padding:0 0 8px;background:#fffaf0;color:#3d3525;font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif;line-height:1.75;font-size:15px;"
HERO_STYLE = "margin:0 0 18px;padding:22px 18px 20px;border:1px solid #ead9a8;background:#fff3c4;border-radius:12px;"
HERO_MARK_STYLE = "display:inline-block;margin-bottom:8px;padding:3px 8px;background:#f96e57;color:#fff;border-radius:999px;font-size:12px;letter-spacing:.08em;"
H1_STYLE = "margin:0;color:#312714;font-size:26px;font-weight:800;line-height:1.25;"
SUBTITLE_STYLE = "margin:8px 0 0;color:#7a6a45;font-size:14px;"
SECTION_STYLE = "margin:22px 0 0;padding:0;"
SECTION_TAG_STYLE = "display:inline-block;margin:0 0 8px;padding:4px 10px;background:#f5c833;color:#fff;border-radius:4px;font-size:13px;letter-spacing:.08em;"
SECTION_TITLE_STYLE = "margin:0;color:#312714;font-size:22px;font-weight:800;line-height:1.35;"
SECTION_LEAD_STYLE = "margin:8px 0 10px;color:#7d704d;font-size:14px;line-height:1.7;"
CARD_STYLE = "margin:12px 0 0;padding:15px 14px;background:#fffdf6;border:1px solid #ecdcae;border-radius:10px;box-shadow:0 4px 14px rgba(120,90,20,.06);"
CARD_TITLE_STYLE = "margin:0 0 10px;color:#322714;font-size:18px;font-weight:700;line-height:1.45;"
PARA_STYLE = "margin:8px 0;color:#443929;font-size:15px;line-height:1.75;"
LEDE_STYLE = "margin:10px 0;padding:10px 12px;background:#fff0df;border-left:4px solid #f96e57;border-radius:6px;"
LEDE_TAG_STYLE = "margin:0 0 4px;color:#f96e57;font-size:13px;font-weight:700;"
META_ROW_STYLE = "margin:5px 0;color:#4f432f;font-size:14px;line-height:1.65;"
META_LABEL_STYLE = "display:inline-block;margin-right:6px;color:#8f7a49;font-weight:700;"
TIME_VALUE_STYLE = "color:#f96e57;font-weight:700;"
LINK_STYLE = "color:#2f6f9f;text-decoration:underline;word-break:break-all;"
BULLET_STYLE = "margin:6px 0 6px 1em;color:#443929;font-size:15px;line-height:1.7;"
IMAGE_STYLE = "display:block;width:100%;max-width:100%;height:auto;margin:10px auto;border-radius:8px;"
FOOTER_STYLE = "margin:24px 0 0;padding:14px 10px;text-align:center;color:#8a7c58;font-size:14px;"
TABLE_WRAP_STYLE = "margin:10px 0;overflow-x:auto;border:1px solid #ecdcae;border-radius:8px;background:#fffdf6;"
TABLE_STYLE = "width:100%;border-collapse:collapse;font-size:14px;line-height:1.6;"
TH_STYLE = "padding:7px 8px;border:1px solid #ecdcae;background:#fff0bf;color:#6f5716;font-weight:700;text-align:left;vertical-align:top;"
TD_STYLE = "padding:7px 8px;border:1px solid #ecdcae;color:#443929;text-align:left;vertical-align:top;"


def _split_label_value(text: str) -> Tuple[str, str]:
    match = re.match(r"^([^:：]{1,12})[:：]\s*(.+)$", text)
    if not match:
        return "", text
    return match.group(1).strip(), match.group(2).strip()


def _strip_emphasis(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
        return stripped[2:-2].strip()
    if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
        return stripped[1:-1].strip()
    return stripped


def _resolve_image_src(src: str, markdown_path: str) -> str:
    cleaned = src.strip().strip("<>").strip('"').strip("'")
    if not cleaned or is_remote_or_data_image(cleaned):
        return cleaned

    markdown_dir = os.path.dirname(markdown_path)
    resolved_path = resolve_existing_image_path(cleaned, base_dir=markdown_dir)
    if resolved_path is not None:
        resolved = str(resolved_path)
    else:
        resolved = os.path.normpath(os.path.join(markdown_dir, clean_markdown_image_target(cleaned)))
    return resolved.replace("\\", "/")


def _render_text(value: str) -> str:
    return html.escape(_strip_emphasis(value or ""))


def _render_meta(label: str, value: str) -> str:
    escaped_label = html.escape(label)
    if label == "链接" and re.match(r"^https?://", value or ""):
        escaped_url = html.escape(value)
        rendered_value = f"<a href=\"{escaped_url}\" style=\"{LINK_STYLE}\">{escaped_url}</a>"
    else:
        value_style = TIME_VALUE_STYLE if label in TIME_LABELS else "color:#4f432f;"
        rendered_value = f"<span style=\"{value_style}\">{_render_text(value)}</span>"
    return f"<p style=\"{META_ROW_STYLE}\"><span style=\"{META_LABEL_STYLE}\">{escaped_label}</span>{rendered_value}</p>"


def _is_table_row(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _is_table_separator(text: str) -> bool:
    return bool(re.match(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", text.strip()))


def _split_table_row(text: str) -> List[str]:
    stripped = text.strip().strip("|")
    return [cell.replace(r"\|", "|").strip() for cell in re.split(r"(?<!\\)\|", stripped)]


def _render_markdown_table(table_lines: List[str]) -> str:
    rows = [line for line in table_lines if _is_table_row(line) and not _is_table_separator(line)]
    if not rows:
        return ""
    parsed = [_split_table_row(line) for line in rows]
    max_cols = max(len(row) for row in parsed)
    for row in parsed:
        row.extend([""] * (max_cols - len(row)))
    header = parsed[0]
    body = parsed[1:]
    head = "".join(f"<th style=\"{TH_STYLE}\">{html.escape(cell)}</th>" for cell in header)
    rows_html = "".join(
        "<tr>" + "".join(f"<td style=\"{TD_STYLE}\">{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in body
    )
    return f"<section style=\"{TABLE_WRAP_STYLE}\"><table style=\"{TABLE_STYLE}\"><thead><tr>{head}</tr></thead><tbody>{rows_html}</tbody></table></section>"


def markdown_to_wechat_inline_html(markdown_text: str, markdown_path: str = "") -> str:
    blocks: List[str] = [f"<section style=\"{PAGE_STYLE}\">"]
    section_open = False
    card_open = False

    def close_card():
        nonlocal card_open
        if card_open:
            blocks.append("</section>")
            card_open = False

    def close_section():
        nonlocal section_open
        close_card()
        if section_open:
            blocks.append("</section>")
            section_open = False

    def open_section(title: str):
        nonlocal section_open
        close_section()
        lead = SECTION_LEADS.get(title, "把这部分内容整理成适合快速阅读的信息卡片。")
        blocks.append(f"<section style=\"{SECTION_STYLE}\">")
        blocks.append(f"<span style=\"{SECTION_TAG_STYLE}\">本期栏目</span>")
        blocks.append(f"<h2 style=\"{SECTION_TITLE_STYLE}\">{html.escape(title)}</h2>")
        blocks.append(f"<p style=\"{SECTION_LEAD_STYLE}\">{html.escape(lead)}</p>")
        section_open = True

    def open_card(title: str):
        nonlocal card_open
        close_card()
        blocks.append(f"<section style=\"{CARD_STYLE}\">")
        blocks.append(f"<h3 style=\"{CARD_TITLE_STYLE}\">{html.escape(title)}</h3>")
        card_open = True

    blocks.append(f"<section style=\"{HERO_STYLE}\">")
    blocks.append(f"<span style=\"{HERO_MARK_STYLE}\">清物语 · 物理系风格</span>")
    blocks.append(f"<h1 style=\"{H1_STYLE}\">万有预报</h1>")
    blocks.append(f"<p style=\"{SUBTITLE_STYLE}\">清华大学物理系校园信息整理</p>")
    blocks.append("</section>")

    lines = (markdown_text or "").splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if _is_table_row(stripped) and index + 1 < len(lines) and _is_table_separator(lines[index + 1].strip()):
            table_lines = [stripped, lines[index + 1].strip()]
            index += 2
            while index < len(lines) and _is_table_row(lines[index].strip()):
                table_lines.append(lines[index].strip())
                index += 1
            rendered_table = _render_markdown_table(table_lines)
            if rendered_table:
                blocks.append(rendered_table)
            continue
        if _is_table_row(stripped):
            lookahead = index + 1
            while lookahead < len(lines) and not lines[lookahead].strip():
                lookahead += 1
            if lookahead < len(lines) and _is_table_separator(lines[lookahead].strip()):
                table_lines = [stripped, lines[lookahead].strip()]
                index = lookahead + 1
                while index < len(lines):
                    candidate = lines[index].strip()
                    if not candidate:
                        index += 1
                        continue
                    if not _is_table_row(candidate):
                        break
                    table_lines.append(candidate)
                    index += 1
                rendered_table = _render_markdown_table(table_lines)
                if rendered_table:
                    blocks.append(rendered_table)
                continue
        index += 1
        if not stripped:
            continue
        if stripped in {HEADER_TITLE_LINE, HEADER_SUBTITLE_LINE, FOOTER_LINE}:
            continue

        image_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            alt = image_match.group(1).strip()
            if alt in THEME_BADGE_ALTS:
                continue
            src = html.escape(_resolve_image_src(image_match.group(2), markdown_path), quote=True)
            blocks.append(f"<img src=\"{src}\" alt=\"{html.escape(alt or '配图')}\" style=\"{IMAGE_STYLE}\" />")
            continue

        if stripped.startswith("# "):
            open_section(stripped[2:].strip())
            continue
        if stripped.startswith("## "):
            if not section_open:
                open_section("未分类")
            open_card(stripped[3:].strip())
            continue
        if stripped.startswith("### "):
            blocks.append(f"<p style=\"{PARA_STYLE}font-weight:700;color:#6a5427;\">{html.escape(stripped[4:].strip())}</p>")
            continue

        label, value = _split_label_value(stripped)
        if label == "要点透视":
            blocks.append(f"<section style=\"{LEDE_STYLE}\"><p style=\"{LEDE_TAG_STYLE}\">要点透视</p><p style=\"{PARA_STYLE}\">{_render_text(value)}</p></section>")
            continue
        if label in META_LABELS:
            blocks.append(_render_meta(label, value))
            continue
        if stripped.startswith("- "):
            blocks.append(f"<p style=\"{BULLET_STYLE}\">• {_render_text(stripped[2:])}</p>")
            continue
        if stripped.startswith("*") and stripped.endswith("*"):
            blocks.append(f"<p style=\"{PARA_STYLE}color:#7d704d;\">{_render_text(stripped)}</p>")
            continue

        blocks.append(f"<p style=\"{PARA_STYLE}\">{_render_text(stripped)}</p>")

    close_section()
    blocks.append(f"<section style=\"{FOOTER_STYLE}\">万有预报，下期再见。</section>")
    blocks.append("</section>")
    return "\n".join(blocks)
