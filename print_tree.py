from pathlib import Path
from typing import Iterable

IGNORE_DIRS = {
    ".git", ".idea", ".vscode", "__pycache__",
    "venv", ".venv", "node_modules", "migrations",
}

MAX_DEPTH = 4


def iter_children(path: Path) -> Iterable[Path]:
    return sorted(
        (p for p in path.iterdir() if p.name not in IGNORE_DIRS),
        key=lambda p: (p.is_file(), p.name.lower()),
    )


def print_tree(root: Path, prefix: str = "", depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        return

    children = list(iter_children(root))
    count = len(children)

    for idx, child in enumerate(children):
        is_last = idx == count - 1
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}{child.name}")

        if child.is_dir():
            extension = "    " if is_last else "│   "
            print_tree(child, prefix + extension, depth + 1)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    print(root.name)
    print_tree(root)
