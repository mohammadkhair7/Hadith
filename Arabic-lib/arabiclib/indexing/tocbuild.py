"""Synthetic TOC assembly (§12.7): build a toc tree from detected headings
across a book's pages, with page mapping, ready to insert into toc_nodes."""
from dataclasses import dataclass, field

from .headings import Heading, detect_headings


@dataclass
class TocEntry:
    level: int
    title: str
    page_ord: int                          # ordinal of the source page
    start_char: int
    children: list["TocEntry"] = field(default_factory=list)


def build_toc(pages: list[str]) -> list[TocEntry]:
    """pages: flat page texts in reading order -> nested TOC roots."""
    flat: list[TocEntry] = []
    for ord_, page_text in enumerate(pages):
        for h in detect_headings(page_text):
            flat.append(TocEntry(level=h.level, title=h.title,
                                 page_ord=ord_, start_char=h.start_char))
    roots: list[TocEntry] = []
    stack: list[TocEntry] = []
    for e in flat:
        while stack and stack[-1].level >= e.level:
            stack.pop()
        if stack:
            stack[-1].children.append(e)
        else:
            roots.append(e)
        stack.append(e)
    return roots
