#!/bin/zsh
set -e
cd -- "$(dirname -- "$0")/../.."
if [[ ! -x .venv/bin/marimo ]]; then
  print '프로젝트 가상환경이 필요합니다. claude_dashboard/README.md의 설치 명령을 확인하세요.'
  read -r '?Enter를 누르면 닫습니다. '
  exit 1
fi
exec .venv/bin/marimo run 김지영/claude_dashboard/app.py --port 2730
