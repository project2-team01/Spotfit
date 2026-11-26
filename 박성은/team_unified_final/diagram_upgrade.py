"""기존 화면을 보존하며 Mermaid SVG 두 개를 설명 접기 안에 포함한다."""
from pathlib import Path
import html
import re

HERE = Path(__file__).resolve().parent
CSS = '''/* BEGIN SPOTFIT MERMAID */
.flow-card { margin-block: 18px; }
.flow-card summary { color: var(--accent); }
.flow-card .flow-intro { font-size: 1rem; margin: 12px 0; }
.flow-viewport { overflow-x: auto; max-width: 100%; padding: 12px 4px; background: var(--surface); }
.flow-viewport:focus-visible { outline: 3px solid var(--accent); outline-offset: -3px; }
.flow-viewport > svg { display: block; width: 100%; height: auto; margin: auto; max-width: 900px !important; min-width: 620px; }
.flow-viewport svg text, .flow-viewport svg tspan { fill: var(--ink) !important; font-size: 16px !important; font-family: inherit; }
.flow-viewport svg .node rect, .flow-viewport svg .node polygon, .flow-viewport svg .node path { fill: var(--surface) !important; stroke: var(--border) !important; stroke-width: 1.5px !important; }
.flow-viewport svg .node.focus rect, .flow-viewport svg .node.focus polygon { fill: var(--seq1) !important; stroke: var(--accent) !important; stroke-width: 2px !important; }
.flow-viewport svg .cluster rect { fill: var(--surface-2) !important; stroke: var(--axis) !important; }
.flow-viewport svg .flowchart-link { stroke: var(--ink2) !important; }
.flow-viewport svg marker path { fill: var(--ink2) !important; stroke: var(--ink2) !important; }
.flow-viewport svg .edgeLabel rect, .flow-viewport svg .labelBkg { fill: var(--surface) !important; background-color: var(--surface) !important; }
.flow-notes { padding-left: 22px; font-size: 1rem; }
.flow-source summary { font-size: .875rem; color: var(--ink2); }
.flow-source pre { white-space: pre-wrap; word-break: normal; font-size: .875rem; max-height: 320px; overflow: auto; }
@media print { .flow-viewport > svg { min-width: 0; } .flow-source { display: none; } }
/* END SPOTFIT MERMAID */'''

def block(name, title, intro, notes):
    svg = (HERE / 'diagrams' / f'{name}.svg').read_text(encoding='utf-8')
    source = (HERE / 'diagrams' / f'{name}.mmd').read_text(encoding='utf-8')
    assert '<svg' in svg and '<script' not in svg and '<foreignObject' not in svg
    items = ''.join(f'<li>{note}</li>' for note in notes)
    return f'''<!-- BEGIN SPOTFIT FLOW {name} -->
  <details class="card fold flow-card" id="{name}-flow">
    <summary>{title} · Mermaid 흐름도 펼치기</summary>
    <p class="flow-intro">{intro}</p>
    <p class="note">작은 화면에서는 그림 안을 좌우로 움직여 볼 수 있습니다. 아래에 같은 내용을 글로 정리했습니다.</p>
    <div class="flow-viewport" role="region" tabindex="0" aria-label="{title}">{svg}</div>
    <ol class="flow-notes">{items}</ol>
    <details class="flow-source"><summary>Mermaid 원본 보기</summary><pre>{html.escape(source)}</pre></details>
  </details>
<!-- END SPOTFIT FLOW {name} -->'''

def upgrade(web=HERE / 'web'):
    template = (web / 'template.html').read_text(encoding='utf-8')
    template = re.sub(r'[ \t]*<!-- BEGIN SPOTFIT FLOW (analysis|mbti) -->.*?<!-- END SPOTFIT FLOW \1 -->\n?', '', template, flags=re.S)
    template = re.sub(r'(?m)^[ \t]+$', '', template)
    template = re.sub(r'\n{3,}', '\n\n', template)
    analysis = block('analysis', '분석 과정 한눈에 보기', '점수와 상권 유형을 각각 만든 뒤, 희망 업종과 운영 선호를 연결해 후보를 비교합니다.', [
        '자료 준비: 상권 코드와 기간을 맞추고 관광특구를 제외합니다. 자료 없음은 0으로 채우지 않습니다.',
        '점수 계산: 연간 평균 점포 5개 이상·업종 내 비교 30곳 이상에서 매출·경쟁·안정성·수요를 비교합니다. 기본 비중은 30·25·15·30이며 결측 영역은 나머지 영역에 비중을 나눕니다.',
        '유형 분류: 인구 구성 L/V, 희망 업종 건당 금액 E/P, 공식 영업 기간 S/D를 별도로 연결합니다. 유형이 점수나 가중치를 자동으로 바꾸지는 않습니다.',
        '대시보드 이용: 희망 업종을 선택해 전체를 비교하거나 운영 선호 조건을 적용합니다. 브라우저 안에서 지도·목록·상세·CSV가 연결됩니다.'
    ])
    mbti = block('mbti', 'MBTI 추천 과정 한눈에 보기', '문항 수에 따른 판정과 미리보기·조건 적용을 구별합니다. 여기서 MBTI는 팀이 만든 운영 선호 초안입니다.', [
        '입력 선택: 15문항은 축마다 5문항, 7문항은 고객층 2·가격 운영 3·영업 환경 2문항입니다. 유형을 직접 고를 수도 있습니다.',
        '축별 조건: 15문항은 4:1·5:0만, 7문항은 각 축 전원 일치(2:0·3:0·2:0)만 씁니다. 3:2·1:1·2:1·미완료 축은 해당 버전의 기준에 따라 제한하지 않습니다.',
        '미리보기와 적용: 적용 중인 선호가 없으면 응답에 따른 후보를 먼저 볼 수 있습니다. 기존 적용 조건이 있으면 그 조건이 우선합니다. 뚜렷한 축이 1개 이상일 때 ‘선호 조건 적용’을 눌러 공통 조건을 바꿉니다. 검사 탭 전환만으로는 바뀌지 않습니다.',
        '후보 비교: 선택한 축이 일치하고 점수가 있는 상권만 현재 가중치로 정렬합니다. 적용한 축의 상권 자료가 없으면 일치 후보에 넣지 않습니다. 7장은 서울 전체 상위 20곳, 6장은 일치 필터·선택 구·CSV를 연결합니다.',
        '범위: 점수가 없는 업종은 추천 목록을 만들지 않습니다. 선호 축을 전부 보류하면 제한 없는 후보 미리보기이며, 일치 후보가 없어도 다른 유형으로 자동 대체하지 않습니다. 점수는 창업 성공 확률이 아닙니다.'
    ])
    anchor = '  <div class="tiles" id="kpiTiles"></div>'
    assert template.count(anchor) == 1
    template = template.replace(anchor, anchor + '\n\n  ' + analysis)
    anchor = '  <div class="seg big" id="mbtiMode"'
    assert template.count(anchor) == 1
    template = template.replace(anchor, '  ' + mbti + '\n' + anchor)
    (web / 'template.html').write_text(template, encoding='utf-8')
    css = (web / 'style.css').read_text(encoding='utf-8')
    css = re.sub(r'/\* BEGIN SPOTFIT MERMAID \*/.*?/\* END SPOTFIT MERMAID \*/\n?', '', css, flags=re.S)
    (web / 'style.css').write_text(css.rstrip() + '\n\n' + CSS + '\n', encoding='utf-8')

if __name__ == '__main__':
    upgrade()
    print('Mermaid 설명 흐름도 2개 추가 완료 · 계산 코드 변경 없음')
