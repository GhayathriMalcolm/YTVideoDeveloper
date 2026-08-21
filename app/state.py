import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text[:60] or "untitled"


class Project:
    def __init__(self, slug: str):
        self.slug = slug
        self.dir: Path = config.PROJECTS_DIR / slug
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "images").mkdir(exist_ok=True)
        self.state_file = self.dir / "state.json"

    @classmethod
    def create(cls, topic: str) -> "Project":
        base_slug = slugify(topic)
        slug = base_slug
        i = 2
        while (config.PROJECTS_DIR / slug).exists():
            slug = f"{base_slug}_{i}"
            i += 1
        project = cls(slug)
        project.save(
            {
                "slug": slug,
                "topic": topic,
                "status": "created",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return project

    @classmethod
    def load(cls, slug: str) -> "Project":
        project = cls(slug)
        if not project.state_file.exists():
            raise FileNotFoundError(f"No project named '{slug}'")
        return project

    @classmethod
    def exists(cls, slug: str) -> bool:
        return (config.PROJECTS_DIR / slug / "state.json").exists()

    @classmethod
    def list_all(cls):
        if not config.PROJECTS_DIR.exists():
            return []
        return sorted(
            p.name
            for p in config.PROJECTS_DIR.iterdir()
            if p.is_dir() and (p / "state.json").exists()
        )

    def read(self) -> dict:
        if not self.state_file.exists():
            return {}
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def save(self, data: dict) -> dict:
        current = self.read()
        current.update(data)
        self.state_file.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return current

    def path(self, *parts: str) -> Path:
        return self.dir.joinpath(*parts)

    def write_text_file(self, filename: str, content: str) -> Path:
        p = self.path(filename)
        p.write_text(content, encoding="utf-8")
        return p
