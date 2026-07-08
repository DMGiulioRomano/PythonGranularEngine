#!/usr/bin/env python3
# =============================================================================
# Riscrittura import flat -> pge.* (Fase 3 refactor library/CLI).
#
# Script UNICO e RIPETIBILE (idempotente: i pattern sono ancorati e non
# ri-matchano cio' che e' gia' `pge.`): riscrive import e letterali stringa
# sui 9 nomi package storici in src/, tests/ e nei sources dei docs.
# rope/LibCST non riscrivono le stringhe (chiavi sys.modules, target di
# patch(...)): l'arbitro finale sono i ~4900 test + il grep-gate:
#
#   grep -rnE "^(from|import) (core|engine|rendering|parameters|controllers|\
#              envelopes|strategies|export|shared)\b" src tests  -> 0 risultati
#
# Uso: python utils/rename_to_pge.py
# =============================================================================

import os
import re
import sys

PACKAGES = (
    'core', 'engine', 'rendering', 'parameters', 'controllers',
    'envelopes', 'strategies', 'export', 'shared',
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _rules():
    rules = []
    for name in PACKAGES:
        rules += [
            # from X. / from X import  (a inizio statement, anche indentato)
            (re.compile(rf'(^\s*)from {name}\.', re.M), rf'\1from pge.{name}.'),
            (re.compile(rf'(^\s*)from {name} import', re.M),
             rf'\1from pge.{name} import'),
            # import X. (anche con alias)
            (re.compile(rf'(^\s*)import {name}\.', re.M),
             rf'\1import pge.{name}.'),
            # letterali stringa: chiavi sys.modules, target di patch(...)
            (re.compile(rf"'{name}\."), rf"'pge.{name}."),
            (re.compile(rf'"{name}\.'), rf'"pge.{name}.'),
        ]
    # moduli singoli: api -> pge.api, main -> pge.cli
    rules += [
        (re.compile(r'(^\s*)from main import', re.M), r'\1from pge.cli import'),
        (re.compile(r"import_module\('main'\)"), "import_module('pge.cli')"),
        (re.compile(r'(^\s*)from api import', re.M), r'\1from pge.api import'),
        (re.compile(r"import_module\('api'\)"), "import_module('pge.api')"),
    ]
    return rules


def _doc_rules():
    rules = [(re.compile(rf'src/{name}/'), rf'src/pge/{name}/')
             for name in PACKAGES]
    rules += [
        (re.compile(r'src/api\.py'), 'src/pge/api.py'),
    ]
    return rules


def rewrite(path, rules):
    with open(path, encoding='utf-8') as f:
        original = f.read()
    text = original
    for pattern, repl in rules:
        text = pattern.sub(repl, text)
    if text != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return True
    return False


def main():
    changed = []
    py_rules = _rules()
    for base in ('src', 'tests'):
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, base)):
            dirnames[:] = [d for d in dirnames if d != '__pycache__']
            for fn in filenames:
                if fn.endswith('.py'):
                    p = os.path.join(dirpath, fn)
                    if rewrite(p, py_rules):
                        changed.append(os.path.relpath(p, ROOT))
    doc_rules = _doc_rules()
    for quadrant in ('reference', 'explanation', 'how-to'):
        droot = os.path.join(ROOT, 'docs', quadrant)
        if not os.path.isdir(droot):
            continue
        for dirpath, _, filenames in os.walk(droot):
            for fn in filenames:
                if fn.endswith('.md'):
                    p = os.path.join(dirpath, fn)
                    if rewrite(p, doc_rules):
                        changed.append(os.path.relpath(p, ROOT))
    print(f"Riscritti {len(changed)} file")
    for p in changed:
        print(f"  {p}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
