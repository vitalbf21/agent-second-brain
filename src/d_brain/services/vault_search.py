"""Morphological search for Russian-language vault content.

Uses Russian suffix stripping + system grep to find relevant notes.
Inspired by Life Pilot Agent's vault_search.py.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Russian suffixes sorted longest-first for greedy stripping
_SUFFIXES = [
    "остью", "ением", "ания", "ями", "ого", "ему", "ать", "ить",
    "ыть", "ять", "ей", "ой", "ие", "ами", "ов", "ев", "ах", "ях",
    "ам", "ям", "ом", "ем", "ую", "юю", "ий", "ый", "ая", "яя",
    "ое", "ее", "ть", "ся", "сь", "тся", "но", "на", "та", "ко",
    "ка", "ки", "ок", "ек", "ик", "ов", "ей",
]

_CATEGORY_MAP = {
    "daily": "daily",
    "ideas": "idea",
    "learnings": "learning",
    "projects": "project",
    "reflections": "reflection",
    "thoughts": "thought",
    "summaries": "summary",
    "goals": "goal",
    "MOC": "index",
    "templates": "template",
    "blog": "blog",
}


def _get_stems(keyword: str) -> list[str]:
    """Generate morphological variants (stems) for a Russian word."""
    keyword = keyword.strip().lower()
    if len(keyword) < 3:
        return [keyword]

    stems = [keyword]
    for suffix in _SUFFIXES:
        if keyword.endswith(suffix) and len(keyword) - len(suffix) >= 3:
            stem = keyword[: -len(suffix)]
            if stem not in stems:
                stems.append(stem)
    return stems


def _grep_files(variant: str, vault_path: Path) -> list[Path]:
    """Run grep for a single variant, return matching .md files."""
    try:
        result = subprocess.run(
            ["grep", "-ril", "--include=*.md", variant, str(vault_path)],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(vault_path),
        )
        if result.returncode == 0:
            return [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def _get_category(file_path: Path, vault_path: Path) -> str:
    """Determine category from file path."""
    try:
        rel = file_path.relative_to(vault_path)
        parts = rel.parts
        if parts:
            return _CATEGORY_MAP.get(parts[0], parts[0])
    except ValueError:
        pass
    return "unknown"


def _get_date(file_path: Path) -> str:
    """Extract date from filename or fall back to mtime."""
    import re
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", file_path.name)
    if date_match:
        return date_match.group(1)
    try:
        from datetime import datetime
        mtime = file_path.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except OSError:
        return "unknown"


def search_vault(
    keywords: str,
    vault_path: Path,
    limit: int = 10,
    max_chars: int = 800,
) -> list[dict]:
    """Search vault with morphological Russian keyword expansion.

    Args:
        keywords: Space-separated search query
        vault_path: Path to Obsidian vault
        limit: Maximum results
        max_chars: Max content chars per result

    Returns:
        List of dicts with path, date, category, content
    """
    import re

    # Extract meaningful words (filter stop words, short words)
    stop_words = {
        "как", "что", "где", "когда", "это", "его", "её", "их",
        "был", "была", "были", "будет", "будут", "можно", "нужно",
        "надо", "ещё", "уже", "или", "но", "а", "в", "на", "из",
        "по", "для", "от", "до", "не", "ни", "да", "нет", "ты",
        "я", "мы", "он", "она", "оно", "они", "все", "всё", "вся",
        "мой", "моя", "моё", "твой", "его", "её", "наш", "ваш",
        "свой", "этот", "эта", "эти", "тот", "та", "те",
    }
    words = re.findall(r"[а-яА-ЯёЁa-zA-Z]{4,}", keywords.lower())
    words = [w for w in words if w not in stop_words][:8]

    if not words:
        return []

    # Search each word with morphological variants
    seen: dict[Path, dict] = {}
    for word in words:
        for stem in _get_stems(word):
            for fpath in _grep_files(stem, vault_path):
                if fpath not in seen:
                    category = _get_category(fpath, vault_path)
                    date = _get_date(fpath)
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="replace")[:max_chars]
                    except OSError:
                        content = ""
                    seen[fpath] = {
                        "path": str(fpath.relative_to(vault_path)),
                        "date": date,
                        "category": category,
                        "content": content,
                    }

    # Sort by date (newest first)
    results = sorted(seen.values(), key=lambda x: x["date"], reverse=True)
    return results[:limit]
