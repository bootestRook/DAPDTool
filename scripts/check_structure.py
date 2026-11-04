"""Check source size and import boundaries without importing application code."""
import ast
from importlib.util import resolve_name
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".css"}
UI = "dapd_tool.ui"


def source_files(root):
    paths = list(root.glob("*.py"))
    for directory in ("dapd_tool", "tests", "scripts", "editor/src"):
        paths.extend(p for p in (root / directory).rglob("*")
                     if p.is_file() and p.suffix in SOURCE_SUFFIXES
                     and "editor_dist" not in p.relative_to(root).parts)
    return sorted(set(paths))


def module_name(path, root):
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imports(tree, module, package):
    """Include imports inside functions: delayed imports cannot bypass rules."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                try:
                    base = resolve_name("." * node.level + base, package)
                except (ImportError, ValueError):
                    yield "<invalid-relative-import>", node.lineno
                    continue
            yield base, node.lineno
            for alias in node.names:
                yield base + "." + alias.name, node.lineno


def boundary_error(source, target):
    core = source == "dapd_api" or source.startswith("dapd_tool.") and not source.startswith(UI + ".")
    if core and (target == UI or target.startswith(UI + ".") or target.startswith("PySide6")):
        return "business modules must not import UI or Qt"
    shared = source in {UI + ".controls", UI + ".theme", UI + ".runner", UI + ".activity", UI + ".session"}
    shared |= source.startswith(UI + ".widgets.")
    composed = (UI + ".pages.", UI + ".dialogs.")
    if shared and (target.startswith(composed) or target == UI + ".main_window"):
        return "shared UI must not import pages, dialogs or the main window"
    feature = source.startswith(composed)
    if feature and target == UI + ".main_window":
        return "features must not depend on the main window"
    if feature and target.startswith(UI + ".pages.") and target != source:
        return "features communicate through signals, not page imports"
    return None


def cycles(graph):
    visiting, visited, stack = set(), set(), []
    found = []

    def visit(module):
        if module in visiting:
            found.append(stack[stack.index(module):] + [module])
            return
        if module in visited:
            return
        visiting.add(module)
        stack.append(module)
        for target in sorted(graph[module]):
            visit(target)
        stack.pop()
        visiting.remove(module)
        visited.add(module)

    for module in sorted(graph):
        visit(module)
    return found


def check(root=ROOT):
    errors, reviews, modules = [], [], {}
    for path in source_files(root):
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8-sig")
        count = len(source.splitlines())
        if count > 500:
            errors.append(f"{relative}: {count} lines exceeds the 500-line limit")
        elif count > 300:
            reviews.append(f"{relative}: {count} lines; review module responsibility")
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(source, filename=relative)
        except SyntaxError as exc:
            errors.append(f"{relative}:{exc.lineno}: {exc.msg}")
            continue
        name = module_name(path, root)
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        modules[name] = (relative, tree, package)
        for node in ast.walk(tree):
            limit = 300 if isinstance(node, ast.ClassDef) else 60
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                size = node.end_lineno - node.lineno + 1
                if size > limit:
                    reviews.append(f"{relative}:{node.lineno}: {node.name} has {size} lines; review responsibility")
    graph = {name: set() for name in modules}
    for name, (path, tree, package) in modules.items():
        for target, line in imports(tree, name, package):
            reason = boundary_error(name, target)
            if reason:
                errors.append(f"{path}:{line}: {reason}: {target}")
            if target == "<invalid-relative-import>":
                errors.append(f"{path}:{line}: invalid relative import")
            if target in modules:
                graph[name].add(target)
            elif target.startswith("dapd_tool."):
                # A from-import can name an attribute; its containing module must exist.
                parent = target.rpartition(".")[0]
                if parent not in modules:
                    errors.append(f"{path}:{line}: missing local module: {target}")
    for cycle in cycles(graph):
        errors.append("import cycle: " + " -> ".join(cycle))
    return sorted(set(errors)), sorted(set(reviews))


def main():
    errors, reviews = check()
    for review in reviews:
        print("REVIEW " + review)
    for error in errors:
        print("ERROR " + error)
    print(f"Structure check: {len(errors)} errors, {len(reviews)} responsibility review notices.")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
