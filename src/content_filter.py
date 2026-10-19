"""Conservative line filtering for naming/category evidence; never alters stored OCR."""
import re

PROMPT = re.compile(r"^(?:[^\w]*\([^)]*\)\s*)?\s*(?:PS\s+)?[A-Z]:[\\/].*?>\s*(.*)$", re.I)
SHELL_PROMPT = re.compile(r"^(?:[\w.-]+@[\w.-]+:[^\s]*\s*)?[$>]\s+(.*)$")
HISTORY = re.compile(r"^#?\d+[\s_|]+.*?\b(?:copied|moved|skipped|planned|error)\b", re.I)
GENERATED = re.compile(r"^(?:\d+[_ ]+)?(?:copied|moved|skipped|planned)[_ ]+", re.I)
FILE = re.compile(r"^\S+\.(?:png|jpe?g|webp)\b", re.I)
PATH = re.compile(r"(?:[A-Z]:[\\/]|\\\\|^/\w+/)", re.I)
LOG = re.compile(r"^(?:\[?\d{4}-\d\d-\d\d[T ].*?\s+)?\[?(?:INFO|DEBUG|WARNING|WARN)\]?\s*[: -]\s*", re.I)
FIELDS = re.compile(r"^(?:original filename|generated filename|destination path|extracted title|category|processing status)\s*:", re.I)
COMMAND = re.compile(r"^(?:[\w.\\/:-]+[\\/])?(pythonw?(?:\.exe)?|py|pip|pytest|git|npm|node|dotnet|Get-[\w-]+|Set-[\w-]+)\b(.*)$", re.I)


def meaningful_line(text: str) -> str | None:
    """Strip prompt location, keep a grounded command; reject administrative output."""
    text = text.strip()
    prompt = PROMPT.match(text) or SHELL_PROMPT.match(text)
    if prompt:
        command = COMMAND.match(prompt.group(1).strip())
        if not command:
            return None
        # Locations and generated file arguments aren't topic evidence.
        args = [arg for arg in command.group(2).split()
                if not PATH.search(arg) and not FILE.match(arg) and not arg.startswith(('.\\', './'))]
        return ' '.join([command.group(1).removesuffix('.exe'), *args])
    if (HISTORY.search(text) or GENERATED.match(text) or FILE.match(text)
            or re.fullmatch(r"[\w_]+_\d{4}-\d{2}-\d{2}(?:_\d+)?", text)
            or FIELDS.match(text) or LOG.match(text)):
        return None
    if re.match(r"^(?:id\s+)?(?:date|processed_at)\s+.*(?:status|category)", text, re.I):
        return None
    if re.fullmatch(r"[-=+|\s]+", text):
        return None
    if PATH.search(text):
        # Preserve an actual diagnostic, but not the path within it.
        if not re.search(r"\b\w*(?:Error|Exception)\b", text):
            return None
        text = re.sub(r"[A-Z]:[\\/][^\s\"']+", "", text, flags=re.I)
    return text or None
