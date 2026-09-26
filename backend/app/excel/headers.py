COLUMN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "number": ("№", "#", "id", "номер", "n"),
    "name": ("задача", "название", "наименование", "task", "name"),
    "description": ("описание", "description"),
    "assignee": ("исполнитель", "ответственный", "assignee", "owner", "resource"),
    "duration": ("длительность", "дни", "длительность (дн)", "duration", "days"),
    "predecessors": ("предшественники", "зависимости", "predecessors", "depends on"),
    "constraint": ("не раньше", "начать не раньше", "snet", "start no earlier than"),
}


def normalize_header(value: object) -> str:
    return " ".join(str(value).strip().casefold().split()) if value is not None else ""


def match_column(value: object) -> str | None:
    header = normalize_header(value)
    for key, names in COLUMN_SYNONYMS.items():
        if header in names:
            return key
    return None
