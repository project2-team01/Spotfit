"""GitHub 공유 파일과 명시된 최종 가공본 ZIP의 경로·링크·용량을 검사한다."""
from pathlib import Path
import ast
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
EXCLUDED = {'outputs', '__pycache__', 'node_modules', '.analysis_deps', '.venv'}
DATA_ZIP = 'data/park_step23_2025_v0.1.zip'
RESULT = HERE / 'reports/upload_validation.json'
tracked = set(subprocess.run(['git', '-C', str(REPO), 'ls-files'], check=True, capture_output=True, encoding='utf-8').stdout.splitlines())
errors = []
records = []
links = 0
for file in sorted(HERE.rglob('*')):
    rel = file.relative_to(HERE)
    if not file.is_file() or file == RESULT or set(rel.parts) & EXCLUDED:
        continue
    if file.suffix not in {'.md', '.py', '.txt', '.csv', '.json', '.xlsx', '.zip', '.sha256'} and file.name != '.gitignore':
        errors.append(f'Unexpected file: {rel}')
    raw = file.read_bytes()
    if file.suffix == '.zip' and rel.as_posix() != DATA_ZIP:
        errors.append(f'Unexpected archive: {rel}')
    limit = 50 * 1024 * 1024 if rel.as_posix() == DATA_ZIP else 1024 * 1024
    if len(raw) > limit:
        errors.append(f'File exceeds allowed size: {rel}')
    if file.suffix not in {'.xlsx', '.zip'}:
        text = raw.decode('utf-8-sig')
        if re.search(r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}', text):
            errors.append(f'Possible credential: {rel}')
        if re.search(r'[A-Z]:[\\/]+Users[\\/]', text):
            errors.append(f'Nonportable user path: {rel}')
        if file.suffix == '.py':
            ast.parse(text)
        if file.suffix == '.md':
            for dest in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
                if dest.startswith(('https:', 'http:', '#', 'mailto:')):
                    continue
                target = (file.parent / unquote(dest.split('#')[0])).resolve()
                try:
                    repo_rel = target.relative_to(REPO).as_posix()
                except ValueError:
                    errors.append(f'Link outside repository: {rel}')
                    continue
                if not target.exists():
                    errors.append(f'Missing link: {rel} -> {dest}')
                elif not target.is_relative_to(HERE) and repo_rel not in tracked:
                    errors.append(f'Link to unshared external file: {rel} -> {dest}')
                links += 1
    records.append({'path': file.relative_to(REPO).as_posix(), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
total = sum(r['bytes'] for r in records)
if total > 55 * 1024 * 1024:
    errors.append('Upload package exceeds 55 MiB')
result = {'status': 'passed' if not errors else 'failed', 'audited_file_count': len(records),
          'audited_bytes': total, 'relative_links_checked': links, 'errors': errors,
          'scope': '박성은/ only, including the named final processed ZIP; raw data, interim data and runtime packages excluded', 'files': records}
RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='files'}, ensure_ascii=False))
if errors:
    raise SystemExit(1)
