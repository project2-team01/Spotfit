"""로컬 미리보기와 Mermaid SVG 내보내기. 지정한 두 SVG만 loopback에서 저장."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent

class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        name = self.path.removeprefix('/__diagram_export/')
        if self.path != '/__diagram_export/' + name or name not in {'analysis', 'mbti'}:
            self.send_error(404); return
        if self.headers.get('Origin') not in {None, 'http://127.0.0.1:8767', 'http://localhost:8767'}:
            self.send_error(403); return
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length < 1_000_000:
            self.send_error(413); return
        source = self.rfile.read(length).decode('utf-8')
        try:
            element = ET.fromstring(source)
            if element.tag != '{http://www.w3.org/2000/svg}svg': raise ValueError('Not SVG')
            if any(e.tag.rsplit('}', 1)[-1] in {'script', 'foreignObject'} for e in element.iter()):
                raise ValueError('Unexpected active SVG content')
        except (ET.ParseError, ValueError):
            self.send_error(400); return
        (ROOT / 'diagrams' / f'{name}.svg').write_text(source, encoding='utf-8')
        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')

if __name__ == '__main__':
    os.chdir(ROOT)
    print('SpotFit preview http://127.0.0.1:8767/dist/index.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8767), Handler).serve_forever()
