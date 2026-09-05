import os, re
emoji_pattern = re.compile(
    '[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E0-\U0001F1FF]'
)
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('.git', 'ven', '__pycache__', 'node_modules')]
    for fname in files:
        if fname.endswith(('.py', '.html')):
            path = os.path.join(root, fname)
            try:
                with open(path, encoding='utf-8') as f:
                    for i, line in enumerate(f, 1):
                        matches = emoji_pattern.findall(line)
                        if matches:
                            print(f'{path}:{i} -> {matches} | {line.strip()[:80]}')
            except Exception:
                pass