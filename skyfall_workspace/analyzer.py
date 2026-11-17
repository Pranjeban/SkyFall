"""Static, local-only metadata extraction for supported engineering files.

The analyzer never executes code and never returns source contents. It extracts
bounded structural metadata so SKYFALL can catalogue approved workspaces.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".ps1": "PowerShell",
    ".psm1": "PowerShell module",
    ".psd1": "PowerShell data/manifest",
    ".py": "Python",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".md": "Markdown",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "Configuration",
    ".bat": "Batch",
    ".cmd": "Command script",
    ".sql": "SQL",
    ".xml": "XML",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".cs": "C#",
    ".bicep": "Bicep",
    ".tf": "Terraform",
    ".sh": "Shell",
}

SCRIPT_EXTENSIONS = {".ps1", ".psm1", ".py", ".bat", ".cmd", ".sh"}

# Explicit credential/key files are excluded before they are opened.
# Content-based detection below is heuristic: it runs locally after reading a
# supported file and excludes flagged files from all search/MCP results.
EXCLUDED_FILE_NAMES = {
    ".netrc", "netrc", "credentials", "credentials.json", "secrets.json",
    "token.json", "auth.json", ".npmrc", ".pypirc", ".git-credentials",
    "id_rsa", "id_ed25519", "known_hosts", "azureprofile.json",
    "azure-profile.json", "serviceprincipal.json", "service-principal.json",
    "azureauth.json",
}
EXCLUDED_SUFFIXES = {
    ".pem", ".pfx", ".p12", ".key", ".kdbx", ".jks", ".keystore",
    ".sqlite", ".db", ".cer", ".crt", ".der",
}

_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:(?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY|ENCRYPTED PRIVATE KEY|PGP PRIVATE KEY BLOCK)-----", re.I),
    # Common assignments in PowerShell, Python, JSON, YAML, TOML and INI.
    re.compile(
        r"(?im)(?:^|[\s,{])['\"]?[A-Za-z0-9_.-]*(?:client[_-]?secret|secret|"
        r"access[_-]?token|refresh[_-]?token|token|password|passwd|pwd|"
        r"connection[_-]?string|api[_-]?key|subscription[_-]?key|access[_-]?key|"
        r"sharedaccesssignature|accountkey)[A-Za-z0-9_.-]*['\"]?\s*[:=]\s*"
        r"['\"]?[^\s'\",}]{8,}"
    ),
    # XML-style key/name + value attributes.
    re.compile(
        r"(?is)(?:key|name)\s*=\s*['\"][^'\"]*(?:secret|token|password|"
        r"connectionstring|api[_-]?key)[^'\"]*['\"][^>]{0,200}?"
        r"value\s*=\s*['\"][^'\"]{8,}['\"]"
    ),
    re.compile(r"(?im)(?:AccountKey|SharedAccessSignature|client_secret|clientSecret)\s*=\s*['\"]?[^;\s'\"]{12,}"),
    re.compile(r"(?i)Authorization\s*[:=]\s*['\"]?(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)SharedAccessSignature=sv=[^;]+;sig=[^;]+"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
]


def detect_sensitive_content(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def _unique(values: list[str], limit: int = 40) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean[:120])
        if len(result) >= limit:
            break
    return result


def _extract_powershell(text: str) -> dict[str, Any]:
    parameters: list[str] = []
    functions: list[str] = []
    imports: list[str] = []
    commands: list[str] = []
    synopsis = ""

    param_match = re.search(r"(?is)\bparam\s*\((.*?)\)", text)
    if param_match:
        block = param_match.group(1)
        parameters = _unique(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", block))

    code_text = re.sub(r"(?is)<#.*?#>", "", text)
    code_text = "\n".join(
        line for line in code_text.splitlines()
        if not line.lstrip().startswith("#")
    )
    functions = _unique(re.findall(r"(?im)^\s*function\s+([A-Za-z_][A-Za-z0-9:-]*)", code_text))
    imports = _unique(re.findall(r"(?im)^\s*Import-Module\s+['\"]?([A-Za-z0-9_.-]+)", code_text))
    commands = _unique(re.findall(r"(?im)^\s*(?:&\s*)?([A-Za-z][A-Za-z0-9_.-]+)(?=\s|$)", code_text))

    # Construct a structural summary from identifiers only. Do not copy synopsis
    # comments or source lines into metadata that may be shared with Copilot.
    features = []
    if parameters:
        features.append(f"{len(parameters)} parameter(s)")
    if functions:
        features.append(f"{len(functions)} function(s)")
    if imports:
        features.append(f"{len(imports)} imported module(s)")
    synopsis = "PowerShell automation file"
    if features:
        synopsis += " with " + ", ".join(features)
    synopsis += ". Structural metadata extracted locally; source code is not returned."

    return {
        "summary": synopsis,
        "parameters": parameters,
        "functions": functions,
        "imports": imports,
        "commands": commands,
        "parse_status": "static_analysis",
    }


def _extract_python(text: str) -> dict[str, Any]:
    parameters: list[str] = []
    functions: list[str] = []
    imports: list[str] = []
    classes: list[str] = []
    summary = ""
    parse_status = "parsed"
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
                parameters.extend(arg.arg for arg in node.args.args)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            if arg.value.startswith("-"):
                                parameters.append(arg.value)
                elif isinstance(node.func, ast.Name) and node.func.id == "add_argument":
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("-"):
                            parameters.append(arg.value)
    except (SyntaxError, ValueError, RecursionError) as exc:
        line_number = getattr(exc, "lineno", None) or 0
        parse_status = f"syntax_error_line_{line_number}"

    if parse_status.startswith("syntax_error"):
        summary = "Python source module could not be parsed; only file metadata is available."
    else:
        features = []
        if functions:
            features.append(f"{len(_unique(functions))} function(s)")
        if classes:
            features.append(f"{len(_unique(classes))} class(es)")
        if imports:
            features.append(f"{len(_unique(imports))} imported module(s)")
        summary = "Python source module"
        if features:
            summary += " with " + ", ".join(features)
        summary += ". Structural metadata extracted locally; source code is not returned."
    return {
        "summary": summary[:500],
        "parameters": _unique(parameters),
        "functions": _unique(functions),
        "classes": _unique(classes),
        "imports": _unique(imports),
        "commands": [],
        "parse_status": parse_status,
    }


def _extract_documentation(text: str, extension: str) -> dict[str, Any]:
    """Extract names/structure only; never copy arbitrary config or source lines."""
    headings: list[str] = []
    summary = ""

    if extension == ".md":
        headings = _unique(re.findall(r"(?m)^#{1,6}\s+(.+)$", text))
        summary = (
            f"Markdown documentation file with {len(headings)} heading(s)."
            if headings else "Markdown documentation file; no headings detected."
        )
    elif extension == ".json":
        try:
            value = json.loads(text)
            keys = list(value.keys()) if isinstance(value, dict) else []
            headings = _unique([str(key) for key in keys])
            summary = (
                f"JSON data document with {len(headings)} top-level key(s)."
                if headings else "JSON data document; no top-level object keys detected."
            )
        except (json.JSONDecodeError, RecursionError, ValueError):
            summary = "JSON file could not be parsed; only file metadata is available."
    elif extension in {".yaml", ".yml"}:
        headings = _unique(re.findall(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*:(?!=)", text))
        summary = f"YAML configuration with {len(headings)} key name(s)."
    elif extension in {".toml", ".ini", ".cfg"}:
        sections = re.findall(r"(?m)^\s*\[([^\]]+)\]", text)
        keys = re.findall(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*=", text)
        headings = _unique(sections + keys)
        summary = f"Configuration file with {len(headings)} section/key name(s)."
    elif extension == ".xml":
        headings = _unique(re.findall(r"<\s*([A-Za-z_][A-Za-z0-9_.:-]*)\b", text))
        summary = f"XML document with {len(headings)} distinct element name(s)."
    elif extension == ".sql":
        declarations = re.findall(
            r'(?im)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(TABLE|VIEW|FUNCTION|PROCEDURE)\s+([A-Za-z0-9_.\[\]`"]+)',
            text,
        )
        headings = _unique([kind.upper() + " " + name.strip('[]`"') for kind, name in declarations])
        summary = f"SQL file with {len(headings)} detected object declaration(s)."
    elif extension in {".tf", ".bicep"}:
        declarations = re.findall(
            r"(?im)^\s*(resource|data|module|variable|output|param|var)\s+['\"]?([A-Za-z_][A-Za-z0-9_.-]*)",
            text,
        )
        headings = _unique([f"{kind} {name}" for kind, name in declarations])
        summary = f"Infrastructure-as-code file with {len(headings)} declared resource/variable symbol(s)."
    elif extension in {".js", ".ts", ".cs"}:
        declarations = re.findall(
            r"(?im)^\s*(?:export\s+)?(?:async\s+)?(?:class|interface|type|function|const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)",
            text,
        )
        headings = _unique(declarations)
        summary = f"Source file with {len(headings)} detected top-level declaration name(s)."
    else:
        # Batch and shell metadata is intentionally generic in this release.
        summary = f"{SUPPORTED_EXTENSIONS.get(extension, 'Text')} file; no source lines are shared."

    return {
        "summary": summary[:500],
        "parameters": [],
        "functions": [],
        "classes": [],
        "imports": [],
        "commands": [],
        "top_level_keys_or_headings": headings[:40],
        "parse_status": "static_analysis",
    }


def analyze_file(path: Path, text: str) -> dict[str, Any]:
    extension = path.suffix.lower()
    if extension in {".ps1", ".psm1", ".psd1"}:
        details = _extract_powershell(text)
    elif extension == ".py":
        details = _extract_python(text)
    else:
        details = _extract_documentation(text, extension)

    return {
        "language": SUPPORTED_EXTENSIONS.get(extension, "Other"),
        "kind": "script" if extension in SCRIPT_EXTENSIONS else "document_or_config",
        "summary": str(details.get("summary", ""))[:500],
        "parameters": details.get("parameters", [])[:40],
        "functions": details.get("functions", [])[:40],
        "classes": details.get("classes", [])[:40],
        "imports": details.get("imports", [])[:40],
        "commands": details.get("commands", [])[:40],
        "top_level_keys_or_headings": details.get("top_level_keys_or_headings", [])[:40],
        "parse_status": str(details.get("parse_status", "static_analysis")),
    }
