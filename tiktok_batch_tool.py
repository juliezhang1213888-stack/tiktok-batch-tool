import re
import json
import asyncio
import sys
from datetime import datetime
import pandas as pd
import streamlit as st
from playwright.async_api import async_playwright

# --- 第一步：确保 Playwright 浏览器被安装 ---
# 在 Streamlit Cloud 环境中，使用子进程调用 playwright install 来下载浏览器。
import subprocess
import sys

def install_playwright_browsers():
    """在后台静默安装 Playwright 浏览器。"""
    try:
        # 检查常见的浏览器路径，如果不存在则执行安装
        # 这里的路径可能需要根据实际情况微调
        import os
        browser_path = os.path.expanduser("~/.cache/ms-playwright/")
        if not os.path.exists(browser_path):
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], 
                           capture_output=True, check=True)
            st.success("✅ Playwright 浏览器已准备就绪。")
        else:
            st.info("ℹ️ Playwright 浏览器已存在。")
    except Exception as e:
        st.warning(f"⚠️ 浏览器安装检查时遇到问题: {e}")

# --- 在 Streamlit 启动时运行一次安装检查 ---
install_playwright_browsers()


# ------------------------------
# 核心抓取函数（异步，单个视频）
# ------------------------------
async def fetch_tiktok_data(video_url: str):
    # ... (此函数内容与之前一致，此处略去重复部分，请保留你原有的抓取逻辑)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            # ... 你的抓取代码 ...
            # (请在此处粘贴你之前实现的 fetch_tiktok_data 函数内容)
            pass
        finally:
            await browser.close()
    return result

# ------------------------------
# 批量处理入口（异步）
# ------------------------------
async def batch_fetch(urls):
    tasks = [fetch_tiktok_data(url) for url in urls]
    results = await asyncio.gather(*tasks)
    return results

# --- 第二步：解决事件循环冲突的关键函数 ---
# 这个函数可以安全地在 Streamlit 脚本中运行异步代码。
def run_async_task(async_func, *args):
    """在一个新的事件循环中运行异步函数，解决与 Streamlit 的冲突。"""
    loop = None
    try:
        # 尝试获取当前运行的事件循环
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 如果没有运行中的循环，则创建一个新的
        pass

    if loop is not None and loop.is_running():
        # 情况1：已经有循环在运行，使用 nest_asyncio（需要额外安装）或创建新线程
        # 为了简化，这里我们直接创建一个新的事件循环并在其中运行
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            result = new_loop.run_until_complete(async_func(*args))
            return result
        finally:
            new_loop.close()
    else:
        # 情况2：没有运行中的循环，直接用 asyncio.run()
        try:
            return asyncio.run(async_func(*args))
        except RuntimeError as e:
            if "cannot be reused" in str(e):
                # 处理循环不能重用的情况，同样创建新循环
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    result = new_loop.run_until_complete(async_func(*args))
                    return result
                finally:
                    new_loop.close()
            else:
                raise e

# ------------------------------
# Streamlit UI
# ------------------------------
st.set_page_config(page_title="TikTok 批量数据提取工具", layout="wide")
st.title("📊 TikTok 批量视频数据提取工具")
st.markdown("支持批量输入视频链接，自动抓取时长、文案、发布时间、互动数据及播放量。")

# 输入方式选择
input_method = st.radio("选择输入方式", ["逐行粘贴链接", "上传 txt 文件"])

urls = []
if input_method == "逐行粘贴链接":
    text_area = st.text_area("请输入 TikTok 视频链接（每行一个）", height=200)
    if st.button("开始提取", type="primary"):
        urls = [u.strip() for u in text_area.splitlines() if u.strip().startswith("http")]
else:
    uploaded_file = st.file_uploader("上传 .txt 文件（每行一个链接）", type=["txt"])
    if uploaded_file and st.button("开始提取", type="primary"):
        content = uploaded_file.read().decode("utf-8")
        urls = [u.strip() for u in content.splitlines() if u.strip().startswith("http")]

if urls:
    st.info(f"共收到 {len(urls)} 个链接，正在抓取，请稍候...（每个视频约需 3-5 秒）")
    with st.spinner("抓取中，请勿关闭页面..."):
        # --- 关键改动：使用我们新定义的 run_async_task 来运行异步抓取 ---
        results = run_async_task(batch_fetch, urls)
        df = pd.DataFrame(results)

        # 显示表格
        st.success("抓取完成！")
        st.dataframe(df, use_container_width=True)

        # 导出按钮
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📥 下载 CSV 文件",
            data=csv,
            file_name="tiktok_data.csv",
            mime="text/csv"
        )
