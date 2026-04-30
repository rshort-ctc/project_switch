import ast
import re
from dataclasses import dataclass

from app.indexing.types import CodeSymbol, SymbolKind

IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\s+(.+)|import\s+(.+))")
JS_IMPORT_RE = re.compile(r"^\s*import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]")
JS_EXPORT_RE = re.compile(r"^\s*export\s+(?:default\s+)?(?:class|function|const|let|var)\s+(\w+)")
JS_FUNCTION_RE = re.compile(r"^\s*(?:export\s+)?function\s+(\w+)\s*\(")
JS_CLASS_RE = re.compile(r"^\s*(?:export\s+)?class\s+(\w+)")


@dataclass(frozen=True)
class SymbolExtraction:
    symbols: list[CodeSymbol]
    imports: list[str]
    exports: list[str]


def extract_symbols(*, text: str, language: str, file_path: str) -> SymbolExtraction:
    _probe_tree_sitter(language)
    if language == "python":
        return _extract_python(text=text, file_path=file_path)
    if language in {"javascript", "typescript"}:
        return _extract_javascript_like(text=text, language=language, file_path=file_path)
    return _extract_generic(text=text, language=language, file_path=file_path)


def _probe_tree_sitter(language: str) -> None:
    try:
        __import__("tree_sitter")
    except ImportError:
        return
    _ = language


def _extract_python(*, text: str, file_path: str) -> SymbolExtraction:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _extract_generic(text=text, language="python", file_path=file_path)
    symbols: list[CodeSymbol] = []
    imports: list[str] = []
    exports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.append(module)
        elif isinstance(node, ast.ClassDef):
            end_line = getattr(node, "end_lineno", node.lineno)
            symbols.append(
                CodeSymbol(
                    name=node.name,
                    kind=SymbolKind.CLASS,
                    file_path=file_path,
                    language="python",
                    start_line=node.lineno,
                    end_line=end_line,
                )
            )
            exports.append(node.name)
            for child in node.body:
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    symbols.append(
                        CodeSymbol(
                            name=child.name,
                            kind=SymbolKind.METHOD,
                            file_path=file_path,
                            language="python",
                            start_line=child.lineno,
                            end_line=getattr(child, "end_lineno", child.lineno),
                            parent=node.name,
                        )
                    )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if _is_class_child(tree, node):
                continue
            symbols.append(
                CodeSymbol(
                    name=node.name,
                    kind=SymbolKind.FUNCTION,
                    file_path=file_path,
                    language="python",
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                )
            )
            exports.append(node.name)
    return SymbolExtraction(
        symbols=sorted(symbols, key=lambda item: item.start_line), imports=imports, exports=exports
    )


def _is_class_child(tree: ast.Module, function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(isinstance(node, ast.ClassDef) and function in node.body for node in ast.walk(tree))


def _extract_javascript_like(*, text: str, language: str, file_path: str) -> SymbolExtraction:
    symbols: list[CodeSymbol] = []
    imports: list[str] = []
    exports: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        if match := JS_IMPORT_RE.match(line):
            imports.append(match.group(1))
        if match := JS_EXPORT_RE.match(line):
            exports.append(match.group(1))
            kind = SymbolKind.CLASS if "class" in line else SymbolKind.EXPORT
            symbols.append(_line_symbol(match.group(1), kind, file_path, language, index))
            continue
        if match := JS_CLASS_RE.match(line):
            symbols.append(
                _line_symbol(match.group(1), SymbolKind.CLASS, file_path, language, index)
            )
        elif match := JS_FUNCTION_RE.match(line):
            symbols.append(
                _line_symbol(match.group(1), SymbolKind.FUNCTION, file_path, language, index)
            )
    return SymbolExtraction(symbols=symbols, imports=imports, exports=exports)


def _extract_generic(*, text: str, language: str, file_path: str) -> SymbolExtraction:
    imports: list[str] = []
    for line in text.splitlines():
        if match := IMPORT_RE.match(line):
            imports.extend(part for part in match.groups() if part)
    return SymbolExtraction(symbols=[], imports=imports, exports=[])


def _line_symbol(
    name: str,
    kind: SymbolKind,
    file_path: str,
    language: str,
    line_number: int,
) -> CodeSymbol:
    return CodeSymbol(
        name=name,
        kind=kind,
        file_path=file_path,
        language=language,
        start_line=line_number,
        end_line=line_number,
    )
