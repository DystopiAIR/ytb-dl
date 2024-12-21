# YouTube Video Downloader

一个简单的 YouTube 视频下载器，使用 FastAPI + yt-dlp 实现。

## 功能特点

- 支持输入 YouTube 视频链接下载视频
- 显示下载进度
- 支持视频预览
- 支持删除已下载的视频

## 安装步骤

1. 克隆仓库

git clone https://github.com/DystopiAIR/ytb-dl.git
cd ytb-dl


2. 安装依赖

pip install -r requirements.txt


3. 运行程序

uvicorn main:app --reload

4. 访问网页
打开浏览器访问 http://localhost:8000