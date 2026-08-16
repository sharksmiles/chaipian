"""极简 Markdown → HTML 转换器（零依赖，只覆盖本工具报告用到的语法）

支持：标题、表格、代码块、引用、粗体、行内代码、链接、列表、分隔线、段落。
"""
import html
import re

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _inline(text):
    text = html.escape(text)
    text = _LINK.sub(r'<a href="\2">\1</a>', text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _INLINE_CODE.sub(r"<code>\1</code>", text)
    return text


def _is_table_sep(row):
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    return all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c) and cells


def _parse_table(rows):
    header = [_inline(c.strip()) for c in rows[0].strip().strip("|").split("|")]
    body = []
    for row in rows[2:]:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        body.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
    thead = "<tr>" + "".join(f"<th>{c}</th>" for c in header) + "</tr>"
    return f"<table><thead>{thead}</thead><tbody>{''.join(body)}</tbody></table>"


def md_to_html(md):
    md = (md or "").lstrip("\ufeff")
    lines = md.replace("\r\n", "\n").split("\n")
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        # 代码块
        if line.startswith("```"):
            buf = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过结束 ``` 
            out.append(f"<pre><code>{html.escape(chr(10).join(buf))}</code></pre>")
            continue
        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue
        # 分隔线
        if re.fullmatch(r"-{3,}", line.strip()):
            out.append("<hr>")
            i += 1
            continue
        # 表格
        if line.strip().startswith("|"):
            j = i
            while j < n and lines[j].strip().startswith("|"):
                j += 1
            rows = lines[i:j]
            if len(rows) >= 2 and _is_table_sep(rows[1]):
                out.append(_parse_table(rows))
                i = j
                continue
        # 引用块
        if line.startswith(">"):
            buf = []
            while i < n and (lines[i].startswith(">") or lines[i].strip() == ""):
                if lines[i].startswith(">"):
                    buf.append(lines[i].lstrip(">").strip())
                i += 1
            inner = "<br>".join(_inline(b) for b in buf if b)
            out.append(f"<blockquote>{inner}</blockquote>")
            continue
        # 列表
        if re.match(r"^\s*[-*]\s+", line) or re.match(r"^\s*\d+\.\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            tag = "ol" if ordered else "ul"
            buf = []
            while i < n and (re.match(r"^\s*[-*]\s+", lines[i]) or re.match(r"^\s*\d+\.\s+", lines[i])):
                item = re.sub(r"^\s*[-*]\s+", "", lines[i])
                item = re.sub(r"^\s*\d+\.\s+", "", item)
                buf.append(f"<li>{_inline(item)}</li>")
                i += 1
            out.append(f"<{tag}>{''.join(buf)}</{tag}>")
            continue
        # 空行
        if not line.strip():
            i += 1
            continue
        # 段落（合并连续非空行，遇到特殊块起始行则停止）
        buf = []
        while i < n and lines[i].strip():
            ln = lines[i].strip()
            if (
                ln.startswith(("#", "```", ">", "|", "---"))
                or re.match(r"^\s*[-*]\s+", ln)
                or re.match(r"^\s*\d+\.\s+", ln)
            ):
                break
            buf.append(ln)
            i += 1
        if buf:
            out.append(f"<p>{_inline(' '.join(buf))}</p>")
            continue
        i += 1
    return "\n".join(out)
