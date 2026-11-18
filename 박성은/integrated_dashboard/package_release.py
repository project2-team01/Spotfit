"""완성된 정적 웹을 자체 자산·데이터와 함께 결정적으로 묶는다."""
from pathlib import Path
import hashlib
import json
import zipfile

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'dist'
OUT=HERE/'release'
OUT.mkdir(exist_ok=True)
archive=OUT/'SpotFit_통합대시보드_v1.zip'
entries=[]
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in sorted(SOURCE.rglob('*')):
        if not p.is_file():continue
        name=p.relative_to(SOURCE).as_posix();data=p.read_bytes()
        info=zipfile.ZipInfo(name,date_time=(2026,11,18,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(info,data)
        entries.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    text='SpotFit 통합 대시보드 v1\n\n이 폴더에서 python -m http.server 27186 실행 후 http://127.0.0.1:27186/#overview 로 접속하세요.\nindex.html을 더블클릭하면 브라우저 파일 보안 제한으로 JSON을 읽지 못할 수 있습니다.\n공유 주소: https://spotfit-park-2025.park24401859.chatgpt.site/#overview\n\n박성은 통합 구현 기준이며 창업 성과 예측 모델이나 팀 전체 승인으로 주장하지 않습니다.\n'
    info=zipfile.ZipInfo('사용안내.txt',date_time=(2026,11,18,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,text.encode('utf-8-sig'))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for entry in entries:assert hashlib.sha256(z.read(entry['path'])).hexdigest()==entry['sha256']
manifest={'archive':archive.name,'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':entries}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'files':len(entries),'integrity':'passed'},ensure_ascii=False))
