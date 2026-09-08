"""Převod HTML na markdown (těla e-mailů) – bez závislostí, deterministicky.

QTextDocument.toMarkdown() by to uměl, ale výsledek závisí na platformě
a fontech (headless testy ztrácejí tučné písmo); Android klient má vlastní
převodník se stejným záběrem, takže obě aplikace dávají podobný výstup.

Podporované: odstavce a bloky, nadpisy, tučné/kurzíva/přeškrtnuté, odkazy,
obrázky, seznamy (i vnořené, číslované), citace, kód (inline i bloky),
oddělovníky, tabulky (buňky oddělené ``|``). ``script``/``style``/``head`` se
přeskakují celé, neznámé značky se zahodí a obsah zůstane.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_SKIP = {"script", "style", "head", "title", "meta", "link"}
_BLOCKS = {"p", "div", "section", "article", "header", "footer", "main", "aside",
           "nav", "table", "thead", "tbody", "tfoot", "figure", "address"}
_INLINE_MARKS = {"b": "**", "strong": "**", "i": "*", "em": "*",
                 "s": "~~", "del": "~~", "strike": "~~"}
_MARKS = ("**", "*", "~~", "`")
_NO_SPACE_BEFORE = ".,;:!?)]"


class _Converter(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.pre = 0
        self.quote = 0
        self.lists: list[list] = []   # [typ, čítač]
        self.links: list[str | None] = []
        self.cell_open = False
        self.pending_space = False    # mezera odsunutá za uzavírací značku

    # ----- pomocné -----
    def _emit(self, s: str) -> None:
        if s:
            self.out.append(s)

    def _tail(self) -> str:
        return self.out[-1] if self.out else ""

    def _at_line_start(self) -> bool:
        return not self.out or self._tail().endswith("\n")

    def _flush_space(self, next_text: str = "") -> None:
        """Odsunutou mezeru vlož jen před text, který ji potřebuje."""
        if not self.pending_space:
            return
        self.pending_space = False
        if self._at_line_start() or self._tail().endswith(" "):
            return
        if next_text and next_text[0] in _NO_SPACE_BEFORE:
            return
        self._emit(" ")

    def _newline(self) -> None:
        self.pending_space = False
        if self.out and not self._at_line_start():
            self._emit("\n")

    def _block(self) -> None:
        """Konec/začátek bloku = prázdný řádek (jen když už něco je)."""
        self.pending_space = False
        if not self.out:
            return
        text = "".join(self.out[-2:])
        if text.endswith("\n\n"):
            return
        self._emit("\n" if text.endswith("\n") else "\n\n")

    def _open_mark(self, mark: str) -> None:
        self._flush_space("x")
        self._emit(mark)

    def _close_mark(self, mark: str) -> None:
        if self._tail() == mark:          # prázdný element -> nic
            self.out.pop()
            return
        # mezera před uzavírací značkou by markdown rozbila (`**text **`)
        if self.out and self.out[-1].endswith(" "):
            stripped = self.out[-1].rstrip(" ")
            if stripped:
                self.out[-1] = stripped
            else:
                self.out.pop()
            self.pending_space = True
        self._emit(mark)

    # ----- značky -----
    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        a = dict(attrs)
        if tag in _INLINE_MARKS:
            self._open_mark(_INLINE_MARKS[tag])
        elif tag == "code":
            if not self.pre:
                self._open_mark("`")
        elif tag == "pre":
            self._block()
            self._emit("```\n")
            self.pre += 1
        elif tag == "br":
            self.pending_space = False
            self._emit("\n" if self.pre else "  \n")
        elif tag == "hr":
            self._block()
            self._emit("---")
            self._block()
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._block()
            self._emit("#" * int(tag[1]) + " ")
        elif tag in ("ul", "ol"):
            if self.lists:
                self._newline()
            else:
                self._block()
            self.lists.append([tag, 0])
        elif tag == "li":
            self._newline()
            indent = "  " * max(0, len(self.lists) - 1)
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                self._emit(f"{indent}{self.lists[-1][1]}. ")
            else:
                self._emit(f"{indent}- ")
        elif tag == "blockquote":
            self._block()
            self.quote += 1
        elif tag == "a":
            href = (a.get("href") or "").strip()
            self.links.append(href if href and not href.lower().startswith("javascript:") else None)
            if self.links[-1]:
                self._flush_space("x")
                self._emit("[")
        elif tag == "img":
            alt = (a.get("alt") or "").strip()
            src = (a.get("src") or "").strip()
            self._flush_space("x")
            if src and not src.lower().startswith(("cid:", "data:")):
                self._emit(f"![{alt}]({src})")
            elif alt:
                self._emit(alt)
        elif tag == "tr":
            self._newline()
            self.cell_open = False
        elif tag in ("td", "th"):
            self.pending_space = False
            if self.cell_open:
                self._emit(" | ")
            self.cell_open = True
        elif tag in _BLOCKS:
            self._block()

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in _INLINE_MARKS:
            self._close_mark(_INLINE_MARKS[tag])
        elif tag == "code":
            if not self.pre:
                self._close_mark("`")
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self._newline()
            self._emit("```")
            self._block()
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._block()
        elif tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            if self.lists:
                self._newline()
            else:
                self._block()
        elif tag == "li":
            self._newline()
        elif tag == "blockquote":
            self.quote = max(0, self.quote - 1)
            self._block()
        elif tag == "a":
            href = self.links.pop() if self.links else None
            if href:
                if self._tail() == "[":
                    self.out.pop()
                    self._emit(href)
                else:
                    if self.out and self.out[-1].endswith(" "):
                        self.out[-1] = self.out[-1].rstrip(" ")
                        self.pending_space = True
                    self._emit(f"]({href})")
        elif tag == "tr":
            self._newline()
            self.cell_open = False
        elif tag in _BLOCKS:
            self._block()

    def handle_data(self, data):
        if self.skip or not data:
            return
        if self.pre:
            self._emit(data)
            return
        text = re.sub(r"\s+", " ", data)
        if self._at_line_start():
            self.pending_space = False
            text = text.lstrip()
            if text and self.quote:
                self._emit("> " * self.quote)
        if not text:
            return
        # mezera hned za otevírací značkou (`** text`) patří před ni
        if text.startswith(" ") and self._tail() in _MARKS:
            mark = self.out.pop()
            if not self._tail().endswith((" ", "\n")):
                self._emit(" ")
            self._emit(mark)
            text = text.lstrip()
            if not text:
                return
        if text == " ":
            if self.pending_space or self._tail().endswith(" ") or self._at_line_start():
                return
        elif self.pending_space:
            self._flush_space(text.lstrip())
            text = text.lstrip()
        self._emit(text)

    def result(self) -> str:
        text = "".join(self.out)
        lines = [ln.rstrip() if not ln.endswith("  ") else ln.rstrip() + "  " for ln in text.split("\n")]
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_markdown(html: str) -> str:
    conv = _Converter()
    try:
        conv.feed(html or "")
        conv.close()
    except Exception:
        pass
    return conv.result()
