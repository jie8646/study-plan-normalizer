#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学习计划文档规范化工具（study-plan-normalizer）

把"叙事型"学习计划 Markdown 转换为标准 Markdown 表格，供「每日日志」App 表格解析分支直接识别。

支持的输入结构（以用户《线性代数-每日执行表.md》为基准）：
  ## ▶ 第X周 · 章节名           -> 章节分组（表格分类）
  ### ☐ D1 · 2026-08-05 周三 · 主题   -> 一天开始（学习日 D1）
  ### ✓ D2 · 2026-08-06 周四 · 主题   -> 已完成日（学习日标「D2（已完成）」）
  ### 🔴 2026-08-09 周日 · 缓冲（W1 补漏 + 周测） -> 缓冲日（学习日 W1缓冲/缓冲）
  - 📖 读：...                  -> 当天一个子任务（每个子任务独立成行）
  - ☐ 完成打卡                 -> 完成打卡也保留为任务
  注：无周几的过期缓冲日（如「🟡 2026-08-09（已过期）」）不生成任务，其列表内容也不会混入上一天。

输出：同目录 {原名}-normalized.md
规则要点：
  - 日期统一为 "MM-DD 周X"（App parseTableCellDate 可识别）
  - 默认每天只生成一条 App 任务：标题=清洗后的每日主题，子任务读/练/SLAM 合并进备注
  - 每个章节输出独立表格，App 自动取章节标题为分类

用法：
  python normalize_plan.py <输入.md> [--detail]
  --detail 展开模式：每个子任务一行（旧行为）
"""
import re
import sys
import pathlib

DAY_HEADER_D = re.compile(
    r"^###\s*[☐🔴✅⚠✓]*\s*(D\d+)\s*[·•]\s*(\d{4})-(\d{2})-(\d{2})\s*(周[一二三四五六日天])\s*[·•]\s*(.+)$"
)
DAY_HEADER_SUN = re.compile(
    r"^###\s*[☐🔴✅⚠🟡✓]*\s*(\d{4})-(\d{2})-(\d{2})\s*(周[一二三四五六日天])\s*[·•]\s*(.+)$"
)
CHAPTER_HEADER = re.compile(r"^##\s+(.+)$")


def parse(text: str):
    """返回 [(chapter, [day_dict, ...]), ...]；day_dict = {date, day, theme, rows, selfcheck}"""
    sections = []            # 已完成章节
    days_in_chapter = []     # 当前章节累积的天记录
    chapter = "未分类"
    cur = None               # 当前学习日 dict(date, day, theme, rows, selfcheck)

    def flush():
        nonlocal cur
        if cur:
            days_in_chapter.append(cur)
        cur = None

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue

        # 章节标题 ## ▶ 第X周 ... / ## 缓冲日约定 / ## 🚦 ...
        m = CHAPTER_HEADER.match(stripped)
        if m:
            flush()
            if days_in_chapter:
                sections.append((chapter, days_in_chapter))
                days_in_chapter = []
            title = re.sub(r"^▶\s*", "", m.group(1)).strip()
            chapter = title if title else "未分类"
            continue
        if stripped.startswith("# "):   # 文档主标题，跳过
            flush()
            continue

        # 学习日 D1：### ☐ D1 · 2026-08-05 周三 · 主题（主题=每日模块）
        m = DAY_HEADER_D.match(stripped)
        if m:
            flush()
            day, y, mo, d, wd, topic = m.groups()
            done = ("✓" in stripped or "✅" in stripped)
            cur = {"date": f"{mo}-{d} {wd}", "day": day + ("（已完成）" if done else ""),
                   "theme": topic.strip(), "rows": [], "selfcheck": ""}
            continue
        # 缓冲日（无 D 编号，从主题括号提取 W 编号）
        m = DAY_HEADER_SUN.match(stripped)
        if m:
            flush()
            y, mo, d, wd, topic = m.groups()
            wm = re.search(r"（\s*(W\d+)", topic)
            day = (wm.group(1) if wm else "") + "缓冲"
            cur = {"date": f"{mo}-{d} {wd}", "day": day,
                   "theme": topic.strip(), "rows": [], "selfcheck": ""}
            continue

        # 未识别的 ### 标题（如「🟡 2026-08-09（已过期）· 缓冲」无周几无法匹配）：
        # 结束当前学习日，避免其列表内容混入上一天
        if stripped.startswith("###"):
            flush()
            continue

        # 子任务列表行（仅在有当前学习日时收集；缩进子项也计入）
        if stripped.startswith("- ") and cur is not None:
            title = stripped[2:].strip()
            if title:
                # 去内部加粗标记，整体加粗包裹 → App 提取完整标题
                title = title.replace("**", "").replace("|", "｜")
                sm = re.match(r"^❓\s*自测[：:]\s*(.+)$", title)
                if sm:
                    cur["selfcheck"] = sm.group(1).strip()
                cur["rows"].append(f"**{title}**")

    flush()
    if days_in_chapter:
        sections.append((chapter, days_in_chapter))
    return sections


def clean_week_prefix(topic: str) -> str:
    """去掉 '第1-2周·' / '第X周·' 这类计划前缀，保留每日核心主题"""
    return re.sub(r"^第\d+(?:-\d+)?周[·•]\s*", "", topic).strip()


def clean_chapter_name(chapter: str) -> str:
    """章节标题去掉括号内的补充说明，让模块列更短"""
    return re.sub(r"[（(][^）)]*[）)]", "", chapter).strip() or chapter


def render(sections: list, doc_title: str, detail: bool = False) -> str:
    out = [f"# {doc_title}（规范化版）", ""]
    if not detail:
        out.append("> 默认每天一条：App 任务标题 = 每日主题，子任务读/练/SLAM 合并进备注，验收标准 = 自测题。")
        out.append("")
    for chapter, days in sections:
        rows = []
        for d in days:
            if detail:
                # 展开模式：每条子任务一行（旧行为，保留兼容）
                for t in d["rows"]:
                    rows.append((d["date"], d["day"], d["theme"], t, ""))
            else:
                # 默认：每天一条
                if d["day"].endswith("缓冲"):
                    module = "缓冲/补漏"
                    theme = d["theme"]
                else:
                    module = clean_chapter_name(chapter)
                    theme = clean_week_prefix(d["theme"])

                # 子任务合并到备注（去掉打卡项；自测单独进验收标准）
                detail_parts = []
                for raw in d["rows"]:
                    raw = raw.strip("*")
                    if raw.startswith("☐ 完成打卡"):
                        continue
                    if raw.startswith("❓ 自测"):
                        continue
                    detail_parts.append(raw)

                detail_text = "；".join(detail_parts).replace("|", "｜")
                full_theme = f"**{theme.replace('|', '｜')}**"
                if detail_text:
                    full_theme += f"；{detail_text}"
                accept = d["selfcheck"].replace("|", "｜")
                rows.append((d["date"], d["day"], module.replace("|", "｜"), full_theme, accept))

        if not rows:
            continue
        out.append(f"## {chapter}")
        out.append("")
        out.append("| 日期(2026) | 学习日 | 模块 | 当日主题 | 验收标准 |")
        out.append("|---|---|---|---|---|")
        for date_str, day, module, theme, accept in rows:
            out.append(f"| {date_str} | {day} | {module} | {theme} | {accept} |")
        out.append("")
    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        print("用法: python normalize_plan.py <输入.md> [--detail]")
        print("  --detail  展开模式：每个子任务独立成一条 App 任务（旧行为）")
        sys.exit(1)
    args = sys.argv[1:]
    detail = "--detail" in args
    src_path = next(a for a in args if not a.startswith("--"))
    src = pathlib.Path(src_path)
    if not src.exists():
        print(f"文件不存在: {src}")
        sys.exit(1)
    text = src.read_text(encoding="utf-8")
    sections = parse(text)
    out_text = render(sections, src.stem, detail=detail)
    dst = src.with_name(src.stem + "-normalized.md")
    dst.write_text(out_text, encoding="utf-8")
    if detail:
        total = sum(len(d["rows"]) for _, days in sections for d in days)
    else:
        total = sum(len(days) for _, days in sections)
    mode = "展开" if detail else "每日一条"
    print(f"✅ 完成（{mode}）：{len(sections)} 个章节，共 {total} 条任务")
    print(f"   输出：{dst}")


if __name__ == "__main__":
    main()
