import re
import json
import asyncio
from datetime import datetime
import pandas as pd
import streamlit as st
from playwright.async_api import async_playwright

# ------------------------------
# 核心抓取函数（异步，单个视频）
# ------------------------------
async def fetch_tiktok_data(video_url: str):
    """
    使用 Playwright 访问视频页面，提取内嵌 JSON 数据中的关键字段。
    返回字典：包含时长、文案、发布时间、点赞、评论、粉丝、播放量。
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(video_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)  # 等待动态脚本执行
            
            html = await page.content()
            
            # 提取内嵌 JSON（TikTok 主要使用 __UNIVERSAL_DATA_FOR_REHYDRATION__）
            json_match = re.search(
                r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>',
                html, re.DOTALL
            )
            if not json_match:
                # 备用：SIGI_STATE
                json_match = re.search(
                    r'<script id="SIGI_STATE" type="application/json">(.*?)</script>',
                    html, re.DOTALL
                )
            
            if not json_match:
                raise ValueError("未找到页面数据 JSON，可能页面结构已更新或链接无效。")
            
            data = json.loads(json_match.group(1))
            
            # 根据不同数据结构，尝试多种路径提取视频信息
            video_data = None
            author_stats = {}
            
            # 路径1：__UNIVERSAL_DATA_FOR_REHYDRATION__
            try:
                item_info = data['__DEFAULT_SCOPE__']['webapp.video-detail']['itemInfo']
                video_data = item_info['itemStruct']
                author_stats = item_info.get('authorStats', {})
            except:
                pass
            
            # 路径2：SIGI_STATE 中的 ItemModule
            if not video_data:
                try:
                    video_id = video_url.split('/')[-1].split('?')[0]
                    video_data = data['ItemModule'][video_id]
                    author_info = data.get('UserModule', {}).get('users', {}).get(video_data['authorId'], {})
                    author_stats = author_info.get('stats', {})
                except:
                    pass
            
            if not video_data:
                raise ValueError("无法从页面 JSON 中解析视频数据，请检查链接是否正确。")
            
            # 提取字段
            desc = video_data.get('desc', '')
            duration_sec = video_data.get('video', {}).get('duration', 0)
            create_time = video_data.get('createTime', 0)
            stats = video_data.get('stats', {})
            likes = stats.get('diggCount', 0)
            comments = stats.get('commentCount', 0)
            # 播放量：优先从 stats.plays 获取，若无则尝试其他字段
            plays = stats.get('playCount', stats.get('plays', 0))
            if plays == 0:
                # 某些情况下播放量在 video.playCount 中
                plays = video_data.get('video', {}).get('playCount', 0)
            
            # 作者粉丝数（从 author_stats 或 video_data.authorStats）
            if not author_stats:
                author_stats = video_data.get('authorStats', {})
            followers = author_stats.get('followerCount', 0)
            
            # 格式化发布时间
            if create_time:
                publish_date = datetime.fromtimestamp(int(create_time)).strftime('%Y-%m-%d %H:%M:%S')
            else:
                publish_date = ''
            
            # 时长格式转换（秒 -> mm:ss）
            if duration_sec:
                mins = duration_sec // 60
                secs = duration_sec % 60
                duration_str = f"{mins:02d}:{secs:02d}"
            else:
                duration_str = ''
            
            return {
                "视频链接": video_url,
                "时长": duration_str,
                "文案": desc,
                "发布时间": publish_date,
                "点赞量": likes,
                "评论量": comments,
                "粉丝订阅量": followers,
                "播放量": plays
            }
        
        except Exception as e:
            return {
                "视频链接": video_url,
                "时长": "",
                "文案": f"抓取失败: {str(e)}",
                "发布时间": "",
                "点赞量": "",
                "评论量": "",
                "粉丝订阅量": "",
                "播放量": ""
            }
        finally:
            await browser.close()

# ------------------------------
# 批量处理入口（异步）
# ------------------------------
async def batch_fetch(urls):
    """并发执行多个抓取任务，提高批量效率"""
    tasks = [fetch_tiktok_data(url) for url in urls]
    results = await asyncio.gather(*tasks)
    return results

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
        # 运行异步批量抓取
        results = asyncio.run(batch_fetch(urls))
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
        
        # 可选导出 Excel
        if st.button("导出 Excel (xlsx)"):
            with pd.ExcelWriter("tiktok_data.xlsx") as writer:
                df.to_excel(writer, index=False)
            with open("tiktok_data.xlsx", "rb") as f:
                st.download_button("下载 Excel", f, file_name="tiktok_data.xlsx")
else:
    if st.button("开始提取") and not urls:
        st.warning("请先输入或上传有效的视频链接。")

# 使用提示
with st.expander("📌 使用说明"):
    st.markdown("""
    1. **链接格式**：必须是完整的 TikTok 视频链接，例如 `https://www.tiktok.com/@username/video/123456789`。
    2. **批量限制**：建议单次不超过 50 个链接，避免等待时间过长。
    3. **数据可靠性**：工具直接从页面 JSON 提取，未经 TikTok 官方 API 授权，若页面结构变更可能导致抓取失败。
    4. **合法使用**：请遵守 TikTok 服务条款，仅用于个人学习或合理用途。
    5. **错误处理**：若某个视频抓取失败，表格中会在“文案”列显示错误原因。
    """)