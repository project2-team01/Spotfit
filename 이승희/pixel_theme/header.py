# -*- coding: utf-8 -*-
"""SpotFit 도트 디자인의 가벼운 조각 (folium 없이 불러올 수 있다): 도트 핀 그림과 대시보드 머리말."""
from __future__ import annotations

import html

BLUE, YELLOW = "#1F5FC4", "#F4C430"

_PIN_PATHS = ('<path fill="#2B2A26" d="M2 0h6v1H2zM1 1h8v1H1zM0 2h10v4H0zM1 6h8v2H1zM2 8h6v1H2zM3 9h4v1H3zM4 10h2v2H4z"></path>'
              '<path fill="{body}" d="M3 1h4v1H3zM2 2h6v1H2zM1 3h8v3H1zM2 6h6v1H2zM3 7h4v1H3zM4 8h2v1H4z"></path>'
              '<path fill="{dot}" d="M4 3h2v1H4zM3 4h4v1H3zM4 5h2v1H4z"></path>')


def pin_svg(width: int = 30, body: str = "#E5484D", dot: str = "#FFFFFF") -> str:
    """도트 위치 핀 (가로 10 × 세로 13 픽셀)."""
    return (f'<svg width="{width}" height="{round(width * 1.3)}" viewBox="0 0 10 13" '
            'style="image-rendering:pixelated;shape-rendering:crispEdges" aria-hidden="true">'
            + _PIN_PATHS.format(body=body, dot=dot) + "</svg>")


def header_html(subtitle: str, note: str = "") -> str:
    """도트 로고 + 'SPOTFIT' 도트 제목 + 한글 부제. 글꼴과 색은 spotfit.css(.sf-*)를 따른다."""
    logo = pin_svg(48, body=BLUE, dot=YELLOW)
    extra = f'<p class="sf-note">{html.escape(note)}</p>' if note else ""
    return (f'<header class="sf-header">{logo}<div><h1 class="sf-title">SPOTFIT</h1>'
            f'<p class="sf-sub">{html.escape(subtitle)}</p>{extra}</div></header>')
