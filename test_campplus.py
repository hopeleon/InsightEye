"""测试 CAM++ 模型加载和使用"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_campplus():
    print("=" * 50)
    print("CAM++ 模型测试")
    print("=" * 50)
    
    # 1. 测试导入
    print("\n[1] 测试导入...")
    try:
        import torch
        print(f"    torch 版本: {torch.__version__}")
        print(f"    torch 设备: {torch.cuda.is_available() and 'cuda' or 'cpu'}")
    except Exception as e:
        print(f"    导入 torch 失败: {e}")
        return
    
    try:
        from modelscope import snapshot_download
        print("    modelscope 导入成功")
    except Exception as e:
        print(f"    导入 modelscope 失败: {e}")
        return
    
    # 2. 测试模型下载
    print("\n[2] 测试模型下载...")
    campplus_model = "iic/speech_campplus_sv_zh-cn_16k"
    local_model_dir = "D:/model"  # 使用本地模型目录
    os.makedirs(local_model_dir, exist_ok=True)
    
    try:
        print(f"    下载模型: {campplus_model}")
        model_dir = snapshot_download(campplus_model, cache_dir=local_model_dir)
        print(f"    模型路径: {model_dir}")
    except Exception as e:
        print(f"    模型下载失败: {e}")
        return
    
    # 3. 检查模型文件
    print("\n[3] 检查模型文件...")
    import glob
    model_files = glob.glob(os.path.join(model_dir, "**", "*"), recursive=True)
    print(f"    模型文件数量: {len(model_files)}")
    for f in model_files[:20]:  # 只显示前20个
        if os.path.isfile(f):
            size = os.path.getsize(f)
            print(f"    - {os.path.basename(f)} ({size/1024/1024:.1f} MB)")
    
    # 4. 测试 pipeline 创建
    print("\n[4] 测试 pipeline 创建...")
    try:
        from modelscope.pipelines import pipeline
        camp_model = pipeline(
            tasks="speaker-verification",
            model=model_dir,
            device="cpu",
        )
        print("    Pipeline 创建成功")
    except Exception as e:
        print(f"    Pipeline 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 5. 测试声纹提取
    print("\n[5] 测试声纹提取...")
    import numpy as np
    
    # 生成测试音频（16kHz, 1秒）
    test_audio = np.random.randn(16000).astype(np.float32) * 0.1
    print(f"    测试音频形状: {test_audio.shape}, 采样率: 16000")
    
    try:
        result = camp_model(test_audio)
        print(f"    声纹提取成功: {result}")
    except Exception as e:
        print(f"    声纹提取失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "=" * 50)
    print("CAM++ 测试全部通过!")
    print("=" * 50)

if __name__ == "__main__":
    test_campplus()
