"""Check the explicit sync-module map and its import boundaries."""
from __future__ import annotations

import ast
import importlib.util
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ('protocol', 'financial_adapters', 'runtime_boundary')
UPPER = ('lightning.ui', 'lightning.desktop', 'lightning.runtime', 'lightning.bootstrap')
# Envelope authentication imports the existing signature verifier lazily; this is the sole protocol exception.
PROTOCOL_EXCEPTIONS = {('lightning.sync.journal.codec', 'lightning.sync.identity')}
# Finance validates replicated effects against the journal store's schema.
ADAPTER_EXCEPTIONS = {('lightning.sync.journal.finance', 'lightning.sync.journal.store')}


def policy_problems(package: Path, policies: dict[str, list[str]]) -> list[str]:
    """Report missing, stale and conflicting assignments and forbidden direct imports."""
    problems = []
    if set(policies) != set(GROUPS):
        problems.append('policy groups must be protocol, financial_adapters and runtime_boundary')
    counts = Counter(name for names in policies.values() for name in names)
    paths = {'.'.join(('lightning', *path.relative_to(package.parent).with_suffix('').parts[:-1]))
             if path.name == '__init__.py' else
             '.'.join(('lightning', *path.relative_to(package.parent).with_suffix('').parts)): path
             for path in package.rglob('*.py')}
    modules = set(paths)
    problems += [f'unassigned: {name}' for name in sorted(modules - counts.keys())]
    problems += [f'unknown module: {name}' for name in sorted(counts.keys() - modules)]
    problems += [f'multiple policies: {name}' for name in sorted(name for name, count in counts.items() if count > 1)]
    protocol = set(policies.get('protocol', ()))
    adapters = set(policies.get('financial_adapters', ()))
    runtime = {name for name in policies.get('runtime_boundary', ())
               if name in paths and paths[name].name != '__init__.py'}
    for name in sorted(modules):
        path = paths[name]
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                context = name if path.name == '__init__.py' else name.rpartition('.')[0]
                base = importlib.util.resolve_name('.' * node.level + (node.module or ''), context) if node.level else node.module or ''
                children = [base + '.' + alias.name for alias in node.names
                            if base + '.' + alias.name in modules or base + '.' + alias.name in UPPER]
                imports = children or [base]
            for dependency in imports:
                if not dependency.startswith('lightning.'):
                    continue
                if any(dependency == upper or dependency.startswith(upper + '.') for upper in UPPER):
                    problems.append(f'{name}:{node.lineno} imports upper layer {dependency}')
                elif name in protocol and dependency not in protocol and (name, dependency) not in PROTOCOL_EXCEPTIONS:
                    problems.append(f'{name}:{node.lineno} imports outside protocol {dependency}')
                elif (name in adapters and dependency in runtime
                      and (name, dependency) not in ADAPTER_EXCEPTIONS):
                    problems.append(f'{name}:{node.lineno} imports runtime module {dependency}')
    return problems


def check(root: Path = ROOT) -> list[str]:
    config = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    return policy_problems(root / 'lightning' / 'sync', config['tool']['lightning-sync-policy'])


if __name__ == '__main__':
    problems = check()
    print('\n'.join(problems) if problems else 'Sync module policies and direct imports: OK')
    raise SystemExit(bool(problems))
