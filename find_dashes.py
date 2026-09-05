import os

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('.git', 'ven', '__pycache__', 'node_modules')]
    for fname in files:
        if fname.endswith(('.py', '.html')):
            path = os.path.join(root, fname)
            try:
                with open(path, encoding='utf-8') as f:
                    for i, line in enumerate(f, 1):
                        if '—' in line:
                            print(f'{path}:{i} -> {line.strip()[:100]}')
            except Exception:
                pass