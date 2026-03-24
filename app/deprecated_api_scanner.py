from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class DeprecatedAPIFinding:
    package: str
    symbol: str
    file_path: str
    line: int
    replacement: str
    severity: str
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DeprecatedAPIScannerError(Exception):
    pass


class DeprecatedAPIScanner:
    def __init__(self, rules_path: str = "data/deprecation_rules.json") -> None:
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        if not self.rules_path.exists():
            raise DeprecatedAPIScannerError(f"Rules file not found: {self.rules_path}")

        try:
            return json.loads(self.rules_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DeprecatedAPIScannerError("Invalid deprecation rules JSON") from exc

    def scan_repository_path(self, repo_path: str) -> List[DeprecatedAPIFinding]:
        root = Path(repo_path)
        if not root.exists() or not root.is_dir():
            raise DeprecatedAPIScannerError(f"Invalid repository path: {repo_path}")

        findings: List[DeprecatedAPIFinding] = []
        for file_path in root.rglob("*.py"):
            findings.extend(self.scan_python_file(str(file_path)))
        return findings

    def scan_python_file(self, file_path: str) -> List[DeprecatedAPIFinding]:
        path = Path(file_path)
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DeprecatedAPIScannerError(f"Failed to read file: {file_path}") from exc

        return self.scan_python_source(source, file_path)

    def scan_python_source(self, source: str, file_path: str = "<memory>") -> List[DeprecatedAPIFinding]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        symbol_uses = list(self._extract_symbol_uses(tree))
        findings: List[DeprecatedAPIFinding] = []

        for package, package_rules in self.rules.items():
            deprecated = package_rules.get("deprecated_symbols", {})
            for symbol, metadata in deprecated.items():
                for used_symbol, line in symbol_uses:
                    if used_symbol == symbol or used_symbol.startswith(symbol + "."):
                        findings.append(
                            DeprecatedAPIFinding(
                                package=package,
                                symbol=symbol,
                                file_path=file_path,
                                line=line,
                                replacement=str(metadata.get("replacement", "")),
                                severity=str(metadata.get("severity", "medium")),
                                note=str(metadata.get("note", "")),
                            )
                        )

        return findings

    def _extract_symbol_uses(self, tree: ast.AST) -> Iterable[tuple[str, int]]:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield alias.name, node.lineno

            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    if module:
                        yield f"{module}.{alias.name}", node.lineno
                    else:
                        yield alias.name, node.lineno

            if isinstance(node, ast.Attribute):
                full = self._attribute_to_str(node)
                if full:
                    yield full, node.lineno

    def _attribute_to_str(self, node: ast.Attribute) -> str | None:
        parts: List[str] = []
        current: ast.AST | None = node

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)
        else:
            return None

        return ".".join(reversed(parts))
