# ============================================================
# InsightEye Dockerfile (GPU Only)
# ============================================================
# 构建命令:  docker build -t elysiaandcyrene/eyes:latest .
#
# 运行命令:  docker run -d -p 8000:8000 --gpus all elysiaandcyrene/eyes:latest
# ============================================================

FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

WORKDIR /app

# 安装 Python 3.11 和系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    ffmpeg \
    libsndfile1 \
    sox \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11

# 复制项目文件
COPY requirements.txt .
COPY app/ ./app/
COPY knowledge/ ./knowledge/
COPY prompts/ ./prompts/
COPY static/ ./static/
COPY workflow/ ./workflow/
COPY models/ ./models/
COPY run_demo.py .
COPY local_settings.py.example ./local_settings.py

# 安装 Python 依赖
# 注意：torch/torchaudio/funasr 由以下步骤单独安装，不在 requirements.txt 中
RUN python3.11 -m pip install --upgrade pip wheel

# 安装 PyTorch（CUDA 12.1，适配 nvidia/cuda:12.1.1 基础镜像）
RUN python3.11 -m pip install --no-cache-dir \
        torch==2.5.1 torchaudio==2.5.1 \
        --index-url https://download.pytorch.org/whl/cu121

# 安装 funasr（含 Silero VAD 及 onnxruntime 依赖）
RUN python3.11 -m pip install --no-cache-dir -i https://pypi.org/simple/ funasr>=1.3.0

# 安装其他依赖（使用 PyPI 官方源）
RUN python3.11 -m pip install --no-cache-dir -i https://pypi.org/simple/ -r requirements.txt

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV OPENAI_API_KEY=sk-zk24d0977d588f88f0d6bf136f9f1b5b42569c1f1efc0763
ENV OPENAI_BASE_URL=https://api.zhizengzeng.com/v1
ENV OPENAI_PARSER_MODEL=gpt-5-mini
ENV OPENAI_ANALYSIS_MODEL=gpt-5.4
ENV LOCAL_DEVICE=cuda

EXPOSE 8000

CMD ["python", "run_demo.py"]
