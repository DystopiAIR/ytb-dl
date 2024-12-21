from fastapi import FastAPI, Request, BackgroundTasks, WebSocket, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import yt_dlp
import os
import json
from pathlib import Path
import asyncio
import humanize
import logging
from typing import Dict
from datetime import datetime
import re

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# 静态文件和模板配置
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")
templates = Jinja2Templates(directory="templates")

# 创建必要的目录和文件
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

VIDEO_INFO_FILE = Path("video_info.json")

# 确保video_info.json存在
if not VIDEO_INFO_FILE.exists():
    VIDEO_INFO_FILE.write_text("[]", encoding="utf-8")

def load_video_info():
    try:
        if VIDEO_INFO_FILE.exists():
            content = VIDEO_INFO_FILE.read_text(encoding="utf-8").strip()
            if not content:  # 如果文件为空
                VIDEO_INFO_FILE.write_text("[]", encoding="utf-8")
                return []
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # 如果JSON解析失败,重置文件
                logger.warning("Invalid JSON in video_info.json, resetting file")
                VIDEO_INFO_FILE.write_text("[]", encoding="utf-8")
                return []
        return []
    except Exception as e:
        logger.error(f"Error loading video info: {e}")
        return []

def save_video_info(info):
    try:
        video_list = load_video_info()
        video_list.append(info)
        with open(VIDEO_INFO_FILE, "w", encoding="utf-8") as f:
            json.dump(video_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving video info: {e}")

# 存储下载进度
download_progress: Dict[str, int] = {}

def sanitize_filename(filename):
    # 移除或替换不安全的字符
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # 移除末尾的空格和点
    filename = filename.strip('. ')
    return filename

async def download_video(url: str):
    try:
        ydl_opts = {
            'format': 'best',
            'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
            'quiet': False,
            'progress_hooks': [lambda d: update_progress(d, url)],
            'retries': 10,
            'socket_timeout': 30,
            'noplaylist': True,
            'restrictfilenames': True,  # 添加这个选项来限制文件名
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 获取视频信息
            logger.info(f"Extracting video info for URL: {url}")
            info = ydl.extract_info(url, download=False)
            
            # 下载视频
            logger.info(f"Downloading video: {info['title']}")
            ydl.download([url])
            
            filename = ydl.prepare_filename(info)
            filename = sanitize_filename(filename)  # 清理文件名
            
            # 确保文件已下载
            if not os.path.exists(filename):
                raise Exception("Download failed: File not found")
                
            # 记录下载完成时间
            download_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 准备视频信息
            video_info = {
                'title': info['title'],
                'filesize': humanize.naturalsize(os.path.getsize(filename)),
                'local_path': f"/downloads/{os.path.basename(filename)}",
                'download_time': download_time
            }
            
            # 保存视频信息
            save_video_info(video_info)
            logger.info(f"Video downloaded and saved: {video_info['title']}")
            return video_info
            
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return {"error": str(e)}

def update_progress(d, url):
    if d['status'] == 'downloading':
        # 去除ANSI转义序列
        percent_str = re.sub(r'\x1b\[[0-9;]*m', '', d['_percent_str'])
        download_progress[url] = float(percent_str.strip('%'))
    elif d['status'] == 'finished':
        download_progress[url] = 100

@app.get("/progress")
async def get_progress(url: str):
    return {"progress": download_progress.get(url, 0)}

@app.get("/")
async def home(request: Request):
    try:
        videos = load_video_info()
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "videos": videos}
        )
    except Exception as e:
        logger.error(f"Error rendering home page: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": "Internal server error"}
        )

# 定义请求体模型
class DownloadRequest(BaseModel):
    url: str

@app.post("/download")
async def download(request: DownloadRequest, background_tasks: BackgroundTasks):
    try:
        background_tasks.add_task(download_video, request.url)
        return {"message": "Download started"}
    except Exception as e:
        logger.error(f"Error starting download: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": str(e)}
        )

@app.get("/video-list")
async def video_list():
    try:
        return JSONResponse(load_video_info())
    except Exception as e:
        logger.error(f"Error getting video list: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": str(e)}
        )

@app.post("/delete")
async def delete_video(request: Request):
    data = await request.json()
    local_path = data.get('local_path')

    if not local_path:
        logger.error("Invalid request: local_path is missing")
        raise HTTPException(status_code=400, detail="Invalid request")

    # 删除视频文件
    file_path = Path(local_path.lstrip('/'))
    if file_path.exists():
        file_path.unlink()
        logger.info(f"Deleted video file: {file_path}")

    # 删除视频信息
    video_list = load_video_info()
    video_list = [video for video in video_list if video['local_path'] != local_path]
    with open(VIDEO_INFO_FILE, "w", encoding="utf-8") as f:
        json.dump(video_list, f, ensure_ascii=False, indent=2)
        logger.info("Updated video info file")

    return {"message": "Video deleted"} 