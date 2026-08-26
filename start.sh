#!/bin/bash
# ── AI virtual training prototype startup ────────────────────────
# UI and synthetic seed can be inspected without an API key.
# Interactive Role / Coach / Tracking calls require a valid API key and model.

set -e
echo "🎯 AI练兵平台 启动中..."
echo ""

# Check whether configuration is present in the environment or local .env.
aihr_key_configured=false
aihr_model_configured=false
[ -n "${ARK_API_KEY:-}" ] && aihr_key_configured=true
[ -n "${ARK_MODEL:-}" ] && aihr_model_configured=true
if [ -f ".env" ]; then
    grep -Eq '^ARK_API_KEY=.+$' .env && aihr_key_configured=true
    grep -Eq '^ARK_MODEL=.+$' .env && aihr_model_configured=true
fi

if [ "$aihr_key_configured" = true ] && [ "$aihr_model_configured" = true ]; then
    echo "✅ ARK_API_KEY and ARK_MODEL detected → interactive LLM roles enabled"
else
    echo "⚠️  API configuration incomplete"
    echo "   The UI and synthetic seed remain available, but interactive Role / Coach / Tracking training requires ARK_API_KEY and ARK_MODEL."
fi
echo ""

echo "📦 安装依赖..."
pip install -q -r requirements.txt

echo ""
echo "🌐 启动地址：http://localhost:8501"
echo "   Ctrl+C 停止"
echo ""

streamlit run app.py \
    --server.port 8501 \
    --server.headless false \
    --browser.gatherUsageStats false
