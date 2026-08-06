from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class DeprecatedAPIFinding:
    """A single deprecated API usage finding in scanned source."""
    package: str
    symbol: str
    file_path: str
    line: int
    replacement: str
    severity: str
    note: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this finding to a plain dictionary."""
        return asdict(self)


class DeprecatedAPIScannerError(Exception):
    """Raised when deprecation rules or source scanning fails."""
    pass


class DeprecatedAPIScanner:
    """AST scanner that finds deprecated API usages from configured rules."""
    def __init__(self, rules: Dict[str, Any] | None = None) -> None:
        """Initialize the scanner from a rules dict (empty dict = no symbols)."""
        self.rules = rules if rules is not None else {}

    def scan_repository_path(self, repo_path: str) -> List[DeprecatedAPIFinding]:
        """Scan all Python files under a repository path for deprecated APIs."""
        root = Path(repo_path)
        if not root.exists() or not root.is_dir():
            raise DeprecatedAPIScannerError(f"Invalid repository path: {repo_path}")

        findings: List[DeprecatedAPIFinding] = []
        for file_path in root.rglob("*.py"):
            findings.extend(self.scan_python_file(str(file_path)))
        return findings

    def scan_python_file(self, file_path: str) -> List[DeprecatedAPIFinding]:
        """Scan a single Python file path for deprecated API usages."""
        path = Path(file_path)
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DeprecatedAPIScannerError(f"Failed to read file: {file_path}") from exc

        return self.scan_python_source(source, file_path)

    def scan_python_source(self, source: str, file_path: str = "<memory>") -> List[DeprecatedAPIFinding]:
        """Scan Python source text for deprecated API usages against loaded rules."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        symbol_uses = list(self._extract_symbol_uses(tree))
        findings: List[DeprecatedAPIFinding] = []
        seen_findings: set[tuple[str, str, int]] = set()

        for package, package_rules in self.rules.items():
            deprecated = package_rules.get("deprecated_symbols", {})
            for symbol, metadata in deprecated.items():
                for used_symbol, line in symbol_uses:
                    if used_symbol == symbol or used_symbol.startswith(symbol + "."):
                        finding_key = (symbol, file_path, line)
                        if finding_key in seen_findings:
                            continue
                        seen_findings.add(finding_key)
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
        """Yield imported and attribute symbol uses with their line numbers."""
        module_bindings = self._extract_module_bindings(tree)

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
                    root, separator, remainder = full.partition(".")
                    if root not in module_bindings:
                        continue
                    normalized = module_bindings[root]
                    yield f"{normalized}{separator}{remainder}", node.lineno

    def _extract_module_bindings(self, tree: ast.AST) -> Dict[str, str]:
        """Build a mapping from import aliases to their module root names."""
        bindings: Dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        bindings[alias.asname] = alias.name
                    else:
                        root = alias.name.split(".", maxsplit=1)[0]
                        bindings[root] = root
        return bindings

    def _attribute_to_str(self, node: ast.Attribute) -> str | None:
        """Convert an Attribute AST node into a dotted name string when possible."""
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
