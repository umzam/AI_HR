#!/bin/bash
# ── AI练兵平台启动脚本 ────────────────────────────────────────────
# 无API Key → Mock演示模式（预设剧本，完整流程）
# 有API Key → 火山引擎真实AI模式

set -e
echo "🎯 AI练兵平台 启动中..."
echo ""

# 检查运行模式
if [ -f ".env" ] && grep -q "ARK_API_KEY=sk\|ARK_API_KEY=[a-zA-Z0-9]" .env 2>/dev/null; then
    echo "✅ 检测到 ARK_API_KEY → 真实AI模式（火山引擎）"
else
    echo "🎭 未配置 ARK_API_KEY → Mock演示模式"
    echo "   如需接入火山引擎：复制 .env.example 为 .env 并填入配置"
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
