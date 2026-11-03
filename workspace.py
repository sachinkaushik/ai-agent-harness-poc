"""Local folders for company instructions, skills, and task output."""
import shutil
from pathlib import Path

from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import DeleteResult, EditResult, FileUploadResponse, WriteResult

from company import ROOT


def reference_sources():
    return [ROOT / "company/AGENTS.md", *sorted((ROOT / "skills").rglob("*.md"))]


def prepare_workspace(path):
    """Create a local workspace and copy company instructions and skills on first use."""
    folder = Path(path).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    for source in reference_sources():
        target = folder / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
    (folder / "work").mkdir(exist_ok=True)
    return folder


def recover_old_files(folder, files):
    """Copy checkpoint-held drafts under /work/ to disk without overwriting local edits."""
    folder = Path(folder).resolve()
    for name, data in files.items():
        if not name.startswith("/work/"):
            continue
        target = (folder / name.lstrip("/")).resolve()
        if not target.is_relative_to(folder / "work") or target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        content = data["content"]
        target.write_text(content if isinstance(content, str) else "\n".join(content))


def working_files(folder):
    """Read saved text artifacts under /work/ for the UI file panel."""
    folder = Path(folder).resolve()
    if not (folder / "work").exists():
        return {}
    return {"/" + str(p.relative_to(folder)): p.read_text()
            for p in (folder / "work").rglob("*")
            if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(folder)}


class ReferenceBackend(FilesystemBackend):
    """Read-only company instructions and skills, used before a writable workspace exists."""

    def write(self, file_path, content):
        return WriteResult(error="References are read-only. Return the draft in chat.")

    def edit(self, file_path, old_string, new_string, replace_all=False):
        return EditResult(error="References are read-only. Return revisions in chat.")

    def delete(self, file_path):
        return DeleteResult(error="References are read-only.")

    def upload_files(self, files):
        return [FileUploadResponse(path=path, error="permission_denied") for path, _ in files]


def reference_backend(path):
    """Load current company references into a read-only backend."""
    folder = prepare_workspace(Path(path) / "references")
    for source in reference_sources():
        shutil.copyfile(source, folder / source.relative_to(ROOT))
    return ReferenceBackend(root_dir=folder, virtual_mode=True)
