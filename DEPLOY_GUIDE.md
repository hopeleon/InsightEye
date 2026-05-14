# InsightEye 部署指南

## 环境要求

- Docker Desktop（已启用 GPU 支持）
- NVIDIA 显卡 + nvidia-container-toolkit
- Git

## 快速开始

### 1. 克隆项目

```bash
git clone <仓库地址> InsightEye
cd InsightEye
```

### 2. 配置

复制配置模板并填写必要信息：

```bash
copy local_settings.py.example local_settings.py
```

编辑 `local_settings.py`，至少填写以下两项：

```python
OPENAI_API_KEY = "your-api-key-here"
OPENAI_BASE_URL = "https://api.zhizengzeng.com/v1"   # 或你自己的 API 地址
```

其余配置均可留空，系统会使用内置默认值。

### 3. 构建并运行（Docker）

```bash
docker build -t insighteye .
docker run -d -p 8000:8000 --gpus all insighteye
```

打开浏览器访问 http://localhost:8000 即可。

### 4. 备选：直接用 Python 运行（无需 Docker）

```bash
# 创建 conda 环境
conda env create -f environment.yml
conda activate insighteye

# 安装本地模型依赖
pip install addict modelscope

# 启动服务
python run_demo.py
```

---

## 常见问题

**Q: Docker 构建时 PyTorch 下载失败？**

这通常是网络问题。可以尝试：
1. 挂载代理后重新构建
2. 换用国内镜像源（需修改 Dockerfile 中的 pip install 命令）

**Q: 提示 GPU 不可用？**

确保 Docker Desktop 已启用 GPU 支持，且宿主机安装了 NVIDIA 驱动。

**Q: 实时语音功能如何使用？**

配置阿里 DashScope API Key 后，进入实时工作台即可使用麦克风/系统音频的实时转录与分析。

**Q: 不配置 API Key 能跑吗？**

可以。本地规则分析链路（DISC 等）无需外部 API，独立运行。LLM 分析功能才需要 API Key。
