#!/bin/zsh
set -e
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi
python update_tsmc_tracker.py --mode local
echo ""
echo "本機測試完成。輸出位於 local_test/，不會覆蓋雲端 Dashboard，也不會發送通知。"
read "?按 Enter 關閉視窗..."
