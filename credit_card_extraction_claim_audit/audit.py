"""Offline documentation and AST inspection. No project code is executed."""
import ast
import os
from pathlib import Path
import re

from .phrases import CREDITCARDEXTRACTION, NOCREDITCARDEXTRACTION, GENERIC_NAMES

CLIENTS = {'azure.ai.formrecognizer.DocumentAnalysisClient',
           'azure.ai.documentintelligence.DocumentIntelligenceClient'}
SDK_MODULES = {'azure.ai.formrecognizer', 'azure.ai.documentintelligence'}
POSITIVE_RULE = 'documented-credit-card-extraction-claim-false'
NEGATIVE_RULE = 'documented-no-credit-card-extraction-claim-false'


def normalize(text):
    return ' '.join(text.lower().replace("n't", ' not').replace('-', ' ').split())


def _pattern(phrase):
    return re.compile(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)')


def match_phrases(text):
    """Return denial and positive matches, masking denials first."""
    text = normalize(text)
    negative = []
    for phrase in sorted(NOCREDITCARDEXTRACTION, key=lambda p: (-len(p), p)):
        pattern = _pattern(phrase)
        if pattern.search(text):
            negative.append(phrase)
            text = pattern.sub(lambda m: ' ' * len(m.group()), text)
    positive = []
    for phrase in sorted(CREDITCARDEXTRACTION, key=lambda p: (-len(p), p)):
        pattern = _pattern(phrase)
        if pattern.search(text):
            positive.append(phrase)
            text = pattern.sub(lambda m: ' ' * len(m.group()), text)
    return negative, positive


def paragraphs(text):
    fence = None
    lines = []
    for line in text.splitlines():
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            lines.append('')
        elif marker:
            fence = marker[1]
            lines.append('')
        else:
            lines.append(line)
    return re.split(r'\n\s*\n', '\n'.join(lines))


def _targets(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}


def source_evidence(source):
    """Recognize one complete route in one syntactically valid module."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    imports = {}
    gate = False
    shadow = set()
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
                gate = gate or any(alias.name == m or alias.name.startswith(m + '.') for m in SDK_MODULES)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            module = node.module or ''
            for alias in node.names:
                full = module + '.' + alias.name
                imports[alias.asname or alias.name] = full
                gate = gate or any(module == m or module.startswith(m + '.') or full == m for m in SDK_MODULES)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            shadow.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                bound.update(_targets(target))
        elif isinstance(node, ast.AnnAssign):
            bound.update(_targets(node.target))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars:
                    bound.update(_targets(item.optional_vars))
    blocked = shadow | bound

    def resolve(node):
        if isinstance(node, ast.Name):
            return imports.get(node.id, '') if node.id not in blocked else ''
        if isinstance(node, ast.Attribute):
            base = resolve(node.value)
            return base + '.' + node.attr if base else ''
        return ''

    constructed = False
    analyzed = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            resolved = resolve(func)
            original = resolved.rsplit('.', 1)[-1]
            if original in GENERIC_NAMES and original not in shadow and func.id not in blocked:
                return True
            if resolved in CLIENTS and original not in shadow:
                constructed = True
        elif isinstance(func, ast.Attribute):
            if func.attr in GENERIC_NAMES and func.attr not in shadow:
                # A receiver bound by assignment is normal; a locally defined route is not.
                return True
            if func.attr in {'DocumentAnalysisClient', 'DocumentIntelligenceClient'} and func.attr not in shadow:
                resolved = resolve(func.value)
                if resolved == 'azure' or resolved.startswith('azure.'):
                    constructed = True
            if func.attr in {'begin_analyze_document', 'begin_analyze_document_from_url'} and func.attr not in shadow:
                candidates = list(node.args[:1]) + [k.value for k in node.keywords if k.arg == 'model_id']
                if any(isinstance(v, ast.Constant) and v.value == 'prebuilt-creditCard' for v in candidates):
                    analyzed = True
    return bool(gate and constructed and analyzed)


def audit(root, ignore=()):
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise OSError('Root must be a readable, non-symlink directory: ' + str(root))
    prefixes = [Path(p).as_posix().strip('/') for p in ignore]

    def ignored(rel):
        value = rel.as_posix()
        return any(p in ('', '.') or value == p or value.startswith(p + '/') for p in prefixes)

    docs = []
    production = []
    tests = []
    source_count = 0

    def walk_error(error):
        raise error

    for current, dirs, files in os.walk(root, onerror=walk_error, followlinks=False):
        base = Path(current)
        dirs[:] = sorted(d for d in dirs if not (base / d).is_symlink() and not ignored((base / d).relative_to(root)))
        for name in sorted(files):
            path = base / name
            rel = path.relative_to(root)
            if path.is_symlink() or ignored(rel):
                continue
            parts = rel.parts[:-1]
            if rel.as_posix() == 'README.md' or (path.suffix == '.md' and 'docs' in parts):
                for paragraph in paragraphs(path.read_text(encoding='utf-8')):
                    negative, positive = match_phrases(paragraph)
                    if negative:
                        docs.append(('negative', rel.as_posix()))
                    if positive:
                        docs.append(('positive', rel.as_posix()))
            if path.suffix == '.py':
                source_count += 1
                if any(p in {'fixtures', 'docs', 'examples'} for p in parts):
                    continue
                if source_evidence(path.read_text(encoding='utf-8')):
                    test = 'tests' in parts or name.startswith('test_') or name.endswith('_test.py')
                    (tests if test else production).append(rel.as_posix())
    findings = []
    positive_docs = sorted({p for kind, p in docs if kind == 'positive'})
    negative_docs = sorted({p for kind, p in docs if kind == 'negative'})
    if positive_docs and not production:
        severity = 'MEDIUM' if tests else 'HIGH'
        findings.append({'rule': POSITIVE_RULE, 'severity': severity,
                         'message': 'Documented capability has evidence only in tests.' if tests else 'Documented capability has no production evidence.',
                         'locations': positive_docs})
    if negative_docs and production:
        findings.append({'rule': NEGATIVE_RULE, 'severity': 'HIGH',
                         'message': 'Documented denial contradicts production evidence.', 'locations': negative_docs})
    return {'verdict': 'FAIL' if findings else 'PASS', 'findings': findings,
            'evidence': {'production': production, 'tests': tests}, 'source_files': source_count}
