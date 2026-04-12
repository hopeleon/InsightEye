# 本地模型配置指南

## 一、概述

项目内置了以下模型，默认存放在项目根目录的 `models/` 文件夹中：

| 模型类型 | 默认路径 | 说明 |
|---------|---------|------|
| FunASR (VAD + ASR) | `models/funasr/` | 语音活动检测 + 自动语音识别 |
| CAM++ 中文声纹 | `models/campplus/zh-cn/` | 中文说话人声纹识别 |
| CAM++ 英文声纹 | `models/campplus/en/` | 英文说话人声纹识别（VoxCeleb） |

---

## 二、配置方式（优先级从高到低）

配置优先级：`local_settings.py` > 环境变量 > 默认值

### 方式 1：通过 `local_settings.py` 配置（推荐）

编辑项目根目录的 `local_settings.py` 文件：

```python
# ===== 本地模型配置 (FunASR + CAM++) =====
# 使用本地模型替代云端服务（无需 API Key）
USE_LOCAL_ASR = True

# 模型根目录（用于 Silero VAD 缓存，可选）
# 如果为空，使用项目内置的 models/ 目录
LOCAL_MODEL_DIR = ""

# FunASR 模型路径（ASR + VAD）
# 留空使用内置模型，自定义示例：
FUNASR_MODEL_DIR = "D:/my_models/funasr"

# CAM++ 中文声纹模型路径
CAMPPLUS_MODEL_DIR = "D:/my_models/campplus/zh-cn"

# CAM++ 英文声纹模型路径（VoxCeleb）
CAMPPLUS_EN_MODEL_DIR = "D:/my_models/campplus/en"

# 运行设备："cuda" 或 "cpu"
LOCAL_DEVICE = "cuda"
```

#### 配置示例

**示例 1：使用项目内置模型（默认）**

```python
FUNASR_MODEL_DIR = ""
CAMPPLUS_MODEL_DIR = ""
CAMPPLUS_EN_MODEL_DIR = ""
```

**示例 2：使用自定义路径**

```python
# Windows 绝对路径
FUNASR_MODEL_DIR = "D:/AI_models/funasr"
CAMPPLUS_MODEL_DIR = "D:/AI_models/campplus/zh-cn"
CAMPPLUS_EN_MODEL_DIR = "D:/AI_models/campplus/en"

# Linux/Mac 绝对路径
FUNASR_MODEL_DIR = "/home/user/models/funasr"
CAMPPLUS_MODEL_DIR = "/home/user/models/campplus/zh-cn"
CAMPPLUS_EN_MODEL_DIR = "/home/user/models/campplus/en"
```

---

### 方式 2：通过环境变量配置

在系统环境变量或 `.env` 文件中设置：

```bash
# Windows PowerShell
$env:FUNASR_MODEL_DIR = "D:/my_models/funasr"
$env:CAMPPLUS_MODEL_DIR = "D:/my_models/campplus/zh-cn"
$env:CAMPPLUS_EN_MODEL_DIR = "D:/my_models/campplus/en"
$env:LOCAL_DEVICE = "cuda"

# Linux/Mac Bash
export FUNASR_MODEL_DIR="/home/user/models/funasr"
export CAMPPLUS_MODEL_DIR="/home/user/models/campplus/zh-cn"
export CAMPPLUS_EN_MODEL_DIR="/home/user/models/campplus/en"
export LOCAL_DEVICE="cuda"
```

或在项目根目录创建 `.env` 文件：

```env
# .env 文件
FUNASR_MODEL_DIR=D:/my_models/funasr
CAMPPLUS_MODEL_DIR=D:/my_models/campplus/zh-cn
CAMPPLUS_EN_MODEL_DIR=D:/my_models/campplus/en
LOCAL_DEVICE=cuda
```

---

## 三、模型目录结构要求

### 3.1 FunASR 模型目录结构

```
funasr/
├── model.pt              # 模型权重文件（约 859 MB，必须）
├── config.yaml           # 配置文件（必须）
├── configuration.json    # 配置（可选）
├── tokens.json           # 词汇表（必须）
├── seg_dict              # 分段词典（可选）
├── am.mvn               # 声学模型配置（可选）
├── example/              # 示例音频（可选）
│   └── asr_example.wav
├── fig/                  # 文档图片（可选）
│   └── struct.png
└── README.md             # 模型说明（可选）
```

### 3.2 CAM++ 中文声纹模型目录结构

```
campplus/zh-cn/
├── config.yaml               # 模型配置（必须）
├── configuration.json        # 配置（可选）
├── campplus_cn_common.bin   # 模型权重（必须，约 27 MB）
├── ding.png                 # 图标（可选）
├── structure.png            # 模型结构图（可选）
├── quickstart.md            # 快速开始（可选）
├── README.md                # 模型说明（可选）
├── requirements.txt         # 依赖（可选）
├── examples/                # 示例音频（可选）
│   ├── speaker1_a_cn_16k.wav
│   ├── speaker1_b_cn_16k.wav
│   └── speaker2_a_cn_16k.wav
└── .mdl / .msc / .mv       # 模型元数据（必须）
```

**config.yaml 关键配置**：

```yaml
model: CAMPPlus
model_conf:
    feat_dim: 80                    # 特征维度
    embedding_size: 192              # 声纹向量维度
    growth_rate: 32
    bn_size: 4
    init_channels: 128
    config_str: 'batchnorm-relu'
    memory_efficient: True
    output_level: 'segment'
```

### 3.3 CAM++ 英文声纹模型目录结构（VoxCeleb）

```
campplus/en/
├── configuration.json        # 模型配置（必须）
├── campplus_voxceleb.bin   # 模型权重（必须，约 28 MB）
├── ding.png                 # 图标（可选）
├── structure.png            # 模型结构图（可选）
├── quickstart.md            # 快速开始（可选）
├── README.md                # 模型说明（可选）
├── examples/                # 示例音频（可选）
│   ├── speaker1_a_en_16k.wav
│   ├── speaker1_b_en_16k.wav
│   └── speaker2_a_en_16k.wav
└── .mdl / .msc / .mv       # 模型元数据（必须）
```

**configuration.json 关键配置**：

```json
{
    "framework": "pytorch",
    "task": "speaker-verification",
    "model": {
        "type": "cam++-sv",
        "model_config": {
            "sample_rate": 16000,
            "fbank_dim": 80,
            "emb_size": 512
        },
        "pretrained_model": "campplus_voxceleb.bin"
    }
}
```

---

## 四、获取模型的方式

### 4.1 使用项目内置模型（默认）

模型已内置在 `models/` 目录中，无需额外下载。

### 4.2 从 ModelScope 下载

如果你需要自定义模型，可以从 ModelScope 下载：

```python
from modelscope import snapshot_download

# FunASR 模型
funasr_dir = snapshot_download(
    "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    cache_dir="./my_models"
)

# CAM++ 中文声纹模型
camp_cn_dir = snapshot_download(
    "iic/speech_campplus_sv_zh-cn_16k-common",
    cache_dir="./my_models"
)

# CAM++ 英文声纹模型
camp_en_dir = snapshot_download(
    "iic/speech_campplus_sv_en_voxceleb_16k",
    cache_dir="./my_models"
)

print(f"FunASR 路径: {funasr_dir}")
print(f"CAM++ 中文路径: {camp_cn_dir}")
print(f"CAM++ 英文路径: {camp_en_dir}")
```

### 4.3 从 HuggingFace 下载

部分模型也可从 HuggingFace 获取：

```bash
# 安装 huggingface_hub
pip install huggingface_hub

# 下载 FunASR 模型
huggingface-cli download iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch --local-dir ./my_models/funasr
```

---

## 五、验证配置是否正确

### 5.1 检查路径配置

在项目根目录运行：

```python
import sys
sys.path.insert(0, '.')
from app.config import FUNASR_MODEL_DIR, CAMPPLUS_MODEL_DIR, CAMPPLUS_EN_MODEL_DIR

print(f"FunASR 模型: {FUNASR_MODEL_DIR}")
print(f"CAM++ 中文模型: {CAMPPLUS_MODEL_DIR}")
print(f"CAM++ 英文模型: {CAMPPLUS_EN_MODEL_DIR}")
```

### 5.2 检查文件是否存在

```python
import os

paths = {
    "FunASR": FUNASR_MODEL_DIR,
    "CAM++ 中文": CAMPPLUS_MODEL_DIR,
    "CAM++ 英文": CAMPPLUS_EN_MODEL_DIR,
}

for name, path in paths.items():
    exists = os.path.exists(path)
    model_file = os.path.join(path, "model.pt" if "funasr" in path else "campplus_cn_common.bin" if "zh-cn" in path else "campplus_voxceleb.bin")
    model_exists = os.path.exists(model_file)
    print(f"{name}:")
    print(f"  目录存在: {exists}")
    print(f"  模型文件存在: {model_exists} ({model_file})")
```

### 5.3 启动时日志检查

启动服务时，观察日志输出中的模型加载信息：

```
[ModelPaths] FunASR 模型路径: D:\InsightEye\models\funasr
[ModelPaths] CAM++ 中文模型路径: D:\InsightEye\models\campplus\zh-cn
[ModelPaths] CAM++ 英文模型路径: D:\InsightEye\models\campplus\en
[ModelPaths] 使用设备: cuda
[ModelManager] 开始加载模型...
[ModelManager] 加载 CAM++ 中文声纹模型 from: D:\InsightEye\models\campplus\zh-cn
[ModelManager] CAM++ 中文模型权重文件: D:\InsightEye\models\campplus\zh-cn\campplus_cn_common.bin
```

---

## 六、常见问题排查

### 问题 1：模型路径正确但加载失败

**症状**：
```
FileNotFoundError: FunASR 模型目录不存在
```

**排查步骤**：
1. 确认路径中没有中文或特殊字符
2. 确认路径使用正斜杠 `/` 或双反斜杠 `\\`
3. 确认目录包含完整的模型文件

**解决方案**：
```python
# 错误 ❌
FUNASR_MODEL_DIR = "D:/我的模型/funasr"  # 中文路径
FUNASR_MODEL_DIR = "D:\models\funasr"    # 单反斜杠

# 正确 ✅
FUNASR_MODEL_DIR = "D:/models/funasr"    # 正斜杠
FUNASR_MODEL_DIR = "D:/models/funasr".replace("/", os.sep)  # 跨平台
```

### 问题 2：CAM++ 模型加载成功但声纹识别异常

**症状**：
- 模型加载日志显示成功
- 但声纹相似度异常高（所有音频 > 0.9）或异常低（所有音频 < 0.3）

**排查步骤**：
1. 确认使用的是 `campplus_cn_common.bin`（中文模型）或 `campplus_voxceleb.bin`（英文模型）
2. 确认 `config.yaml` 或 `configuration.json` 存在且格式正确

**解决方案**：
检查模型配置文件是否存在：
```python
import yaml
config = yaml.safe_load(open("models/campplus/zh-cn/config.yaml"))
print("embedding_size:", config["model_conf"]["embedding_size"])
```

### 问题 3：CUDA 内存不足

**症状**：
```
RuntimeError: CUDA out of memory
```

**解决方案**：
```python
# 方案 1：切换到 CPU
LOCAL_DEVICE = "cpu"

# 方案 2：减少 FunASR 的 CPU 线程数
# 在 model_manager.py 中修改 ncpu 参数
self.funasr_model = AutoModel(
    model=model_path,
    device="cuda",
    disable_update=True,
    ncpu=2,  # 减少线程数
)
```

### 问题 4：FunASR 模型下载失败

**症状**：
```
ConnectionError: Failed to download model
```

**解决方案**：
1. 检查网络连接
2. 使用代理：
```python
import os
os.environ["http_proxy"] = "http://127.0.0.1:7890"
os.environ["https_proxy"] = "http://127.0.0.1:7890"
```

---

## 七、最佳实践

### 7.1 模型管理建议

```
项目根目录/
├── models/              # 内置模型（Git 管理）
├── my_models/          # 自定义模型（可选，不纳入 Git）
│   ├── funasr/
│   └── campplus/
└── local_settings.py   # 配置文件
```

在 `.gitignore` 中添加：
```gitignore
# 自定义模型（可选）
# my_models/
```

### 7.2 环境隔离建议

使用虚拟环境管理依赖：
```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 7.3 生产环境部署

在生产环境中，建议：
1. 使用绝对路径配置模型目录
2. 将模型放在 SSD 或高速存储设备上
3. 使用 CUDA 加速（如有 NVIDIA 显卡）
4. 监控 GPU 内存使用情况

---

## 八、完整配置示例

### 示例 1：使用内置模型（最简单）

`local_settings.py`:
```python
# 全部留空，使用内置模型
USE_LOCAL_ASR = True
LOCAL_MODEL_DIR = ""
FUNASR_MODEL_DIR = ""
CAMPPLUS_MODEL_DIR = ""
CAMPPLUS_EN_MODEL_DIR = ""
LOCAL_DEVICE = "cuda"
```

### 示例 2：使用外部模型目录

`local_settings.py`:
```python
USE_LOCAL_ASR = True

# 集中管理所有模型
LOCAL_MODEL_DIR = "E:/AI_Models"

# 分别指定各模型路径
FUNASR_MODEL_DIR = "E:/AI_Models/funasr"
CAMPPLUS_MODEL_DIR = "E:/AI_Models/campplus_zh"
CAMPPLUS_EN_MODEL_DIR = "E:/AI_Models/campplus_en"

LOCAL_DEVICE = "cuda"
```

### 示例 3：混合使用（部分内置，部分外部）

```python
USE_LOCAL_ASR = True

# FunASR 使用内置
FUNASR_MODEL_DIR = ""

# CAM++ 中文使用内置，英文使用外部
CAMPPLUS_MODEL_DIR = ""
CAMPPLUS_EN_MODEL_DIR = "D:/models/campplus_voxceleb"

LOCAL_DEVICE = "cuda"
```

---

## 九、联系方式与支持

如果在配置过程中遇到问题，请提供以下信息：

1. 模型路径配置
2. 启动日志（包含 `[ModelManager]` 的部分）
3. 错误信息完整内容
4. 操作系统和 Python 版本

可通过项目 GitHub Issues 获取帮助。
