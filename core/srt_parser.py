"""
srt_parser.py — SRT file reader/writer with auto encoding detection.
Supports UTF-8 BOM, UTF-8, GBK/GB2312, CP1252.
"""

import re
import os


class SrtBlock:
    __slots__ = ("idx", "timestamp", "text")

    def __init__(self, idx: int, timestamp: str, text: str):
        self.idx = idx
        self.timestamp = timestamp
        self.text = text

    def __repr__(self):
        return f"SrtBlock(idx={self.idx}, ts={self.timestamp!r})"


# ---------------------------------------------------------------------------
# Encoding detection
# ---------------------------------------------------------------------------

def _detect_encoding(data: bytes) -> str:
    if data[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        import codecs
        codecs.lookup("gbk")
        data.decode("gbk")
        return "gbk"
    except (LookupError, UnicodeDecodeError):
        pass
    return "cp1252"


# ---------------------------------------------------------------------------
# SRT repair helpers
# ---------------------------------------------------------------------------

_TS_DOT_RE = re.compile(r"(\d{2}:\d{2}:\d{2})\.(\d{3})")
_TS_LINE_RE = re.compile(r"\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}")


def _repair(text: str) -> str:
    """Fix common SRT defects."""
    text = _TS_DOT_RE.sub(r"\1,\2", text)
    # Remove zero-width space & soft hyphen
    text = text.replace("\u200b", "").replace("\u00ad", "")
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_srt(filepath: str) -> list:
    """
    Parse an SRT file, return list of SrtBlock.
    Auto-detects encoding.
    """
    with open(filepath, "rb") as fh:
        raw = fh.read()

    enc = _detect_encoding(raw)
    text = raw.decode(enc, errors="replace")

    # Normalize
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.lstrip("\ufeff")
    text = _repair(text)

    blocks = []
    for chunk in re.split(r"\n{2,}", text.strip()):
        lines = chunk.strip().split("\n")
        if len(lines) < 2:
            continue
        idx_line = lines[0].strip()
        if not re.match(r"^\d+$", idx_line):
            continue
        if not _TS_LINE_RE.search(lines[1]):
            continue
        body = "\n".join(lines[2:]).strip() if len(lines) > 2 else ""
        blocks.append(SrtBlock(int(idx_line), lines[1].strip(), body))

    return blocks


def write_srt(blocks: list, filepath: str) -> None:
    """
    Write translated blocks to an SRT file (UTF-8 with BOM for Windows compat).
    """
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    parts = []
    for b in blocks:
        parts.append(str(b.idx))
        parts.append(b.timestamp)
        parts.append(b.text or "")
        parts.append("")
    content = "\n".join(parts)
    with open(filepath, "w", encoding="utf-8-sig", newline="\n") as fh:
        fh.write(content)


def get_output_path(source_path: str, lang_code: str) -> str:
    """
    Returns output path: <source_dir>/output/<LANG_CODE>/<filename>
    """
    src_dir = os.path.dirname(os.path.abspath(source_path))
    filename = os.path.basename(source_path)
    return os.path.join(src_dir, "output", lang_code, filename)


LANG_CODE_MAP = {
    "indonesian":  "ID",
    "thai":        "TH",
    "vietnamese":  "VI",
    "hindi":       "HI",
    "korean":      "KO",
    "spanish":     "ES",
    "french":      "FR",
    "german":      "DE",
    "portuguese":  "PT_BR",
    "english":     "EN",
    "turkish":     "TR",
    "filipino":    "PH",
    "russian":     "RU",
    "japanese":    "JA",
    "chinese":     "ZH",
    "arabic":      "AR",
}


def lang_to_code(lang: str) -> str:
    return LANG_CODE_MAP.get(lang.lower(), lang.upper()[:2])
