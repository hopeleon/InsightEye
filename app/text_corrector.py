"""
MacBERT4CSC 中文文本纠错模块
用于对 ASR 转录结果进行后处理纠错

模型下载地址: https://huggingface.co/shibing624/macbert4csc-base-chinese
下载后放入 models/macbert 目录
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
import os

# 获取模型本地路径
def _get_local_model_dir() -> str:
    """获取本地模型目录"""
    from pathlib import Path
    base_dir = Path(__file__).resolve().parent.parent
    return str(base_dir / "models" / "macbert")

# 全局单例（延迟加载）
_corrector_instance: Optional["MacBertCorrectorWrapper"] = None


class MacBertCorrectorWrapper:
    """
    MacBERT4CSC 纠错器封装
    支持单句和批量纠错
    """

    def __init__(self, model_name: str = "shibing624/macbert4csc-base-chinese"):
        """
        Args:
            model_name: HuggingFace 模型名称
        """
        self.model_name = model_name
        self._model = None
        self._tokenizer = None
        self._initialized = False

        # 检查本地模型路径
        self._local_model_path = os.path.join(_get_local_model_dir(), model_name.replace("/", "_"))
        self._use_local = os.path.exists(self._local_model_path) or os.path.exists(_get_local_model_dir())

    def _ensure_initialized(self):
        """延迟初始化模型"""
        if self._initialized:
            return

        print(f"[MacBERT纠错] 正在加载模型...")

        # 优先使用本地模型
        local_model_path = self._local_model_path
        if os.path.exists(local_model_path):
            print(f"[MacBERT纠错] 使用本地模型: {local_model_path}")
        else:
            # 使用 HuggingFace 远程模型（会自动下载到缓存）
            local_model_path = self.model_name
            print(f"[MacBERT纠错] 本地模型未找到，使用 HuggingFace 模型: {self.model_name}")
            print(f"[MacBERT纠错] 模型会自动下载到缓存目录")
            print(f"[MacBERT纠错] 如需离线使用，请手动下载模型到: {self._local_model_path}")

        try:
            from transformers import BertTokenizerFast, BertForMaskedLM
            import torch

            self._tokenizer = BertTokenizerFast.from_pretrained(local_model_path)
            self._model = BertForMaskedLM.from_pretrained(local_model_path)

            # 设置设备
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model.to(device)
            self._model.eval()
            self._device = device

            self._initialized = True
            print(f"[MacBERT纠错] 模型加载完成，使用设备: {device}")

        except Exception as e:
            print(f"[MacBERT纠错] transformers 加载失败: {e}")
            print("[MacBERT纠错] 将使用 pycorrector 库作为备选...")
            self._initialized = "fallback"
            self._load_fallback()

    def _load_fallback(self):
        """加载 pycorrector 作为备选方案"""
        try:
            from pycorrector import MacBertCorrector
            self._fallback = MacBertCorrector(self.model_name)
            self._initialized = "fallback"
        except Exception as e:
            print(f"[MacBERT纠错] pycorrector 加载失败: {e}")
            self._initialized = "failed"

    def correct(self, text: str) -> Dict[str, Any]:
        """
        纠错单个文本

        Args:
            text: 待纠错文本

        Returns:
            {
                "source": 原始文本,
                "target": 纠错后文本,
                "errors": [("错字", "正字", 位置), ...],
                "corrected": 是否被纠正
            }
        """
        self._ensure_initialized()

        if self._initialized is True:
            return self._correct_direct(text)
        elif self._initialized == "fallback":
            return self._correct_fallback(text)
        else:
            # 加载失败，返回原文本
            return {
                "source": text,
                "target": text,
                "errors": [],
                "corrected": False
            }

    def _correct_direct(self, text: str) -> Dict[str, Any]:
        """直接使用 transformers 进行纠错"""
        import torch

        source = text.strip()
        if not source:
            return {
                "source": source,
                "target": source,
                "errors": [],
                "corrected": False
            }

        # Tokenize
        inputs = self._tokenizer(source, return_tensors="pt", truncation=True, max_length=512)
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        # 获取预测
        with torch.no_grad():
            outputs = self._model(**inputs)
            predictions = outputs.logits.argmax(dim=-1)[0]

        # 找出需要纠正的位置
        tokens = self._tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])
        errors = []
        corrected_text = []

        for i, (token_id, pred_id) in enumerate(zip(inputs["input_ids"][0], predictions)):
            token = tokens[i]

            # 跳过特殊 token
            if token in ["[CLS]", "[SEP]", "[PAD]"]:
                continue

            # 检查是否需要替换
            if token_id != pred_id and pred_id != self._tokenizer.pad_token_id:
                # 获取原始字符和预测字符
                original_chars = self._tokenizer.convert_ids_to_tokens([token_id.item()])
                pred_chars = self._tokenizer.convert_ids_to_tokens([pred_id.item()])

                if original_chars and pred_chars:
                    orig_char = original_chars[0].replace("##", "")
                    pred_char = pred_chars[0].replace("##", "")

                    # 只记录有意义的替换（汉字或相关字符）
                    if orig_char != pred_char and not orig_char.startswith("##"):
                        # 计算字符位置（简化处理）
                        pos = len("".join(corrected_text))
                        errors.append((orig_char, pred_char, pos))
                        corrected_text.append(pred_char)
                    else:
                        corrected_text.append(self._tokenizer.convert_ids_to_tokens([token_id.item()])[0].replace("##", ""))
                else:
                    corrected_text.append(self._tokenizer.decode(token_id).replace("##", ""))
            else:
                decoded = self._tokenizer.decode(token_id)
                if decoded.startswith("##"):
                    corrected_text.append(decoded[2:])
                else:
                    corrected_text.append(decoded)

        target = "".join(corrected_text).replace("[PAD]", "").replace("[UNK]", "")

        return {
            "source": source,
            "target": target if target else source,
            "errors": errors,
            "corrected": len(errors) > 0
        }

    def _correct_fallback(self, text: str) -> Dict[str, Any]:
        """使用 pycorrector 纠错"""
        source = text.strip()
        if not source:
            return {
                "source": source,
                "target": source,
                "errors": [],
                "corrected": False
            }

        try:
            result = self._fallback.correct(source)
            if result and len(result) > 0:
                return result[0] if isinstance(result, list) else result
        except Exception as e:
            print(f"[MacBERT纠错] pycorrector 纠错失败: {e}")

        return {
            "source": source,
            "target": source,
            "errors": [],
            "corrected": False
        }

    def correct_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        批量纠错

        Args:
            texts: 待纠错文本列表

        Returns:
            每个文本的纠错结果
        """
        return [self.correct(text) for text in texts]


def get_corrector(model_name: str = "shibing624/macbert4csc-base-chinese") -> MacBertCorrectorWrapper:
    """
    获取全局纠错器单例

    Args:
        model_name: 模型名称

    Returns:
        MacBertCorrectorWrapper 实例
    """
    global _corrector_instance

    if _corrector_instance is None:
        _corrector_instance = MacBertCorrectorWrapper(model_name)

    return _corrector_instance


def correct_text(text: str, model_name: str = "shibing624/macbert4csc-base-chinese") -> Dict[str, Any]:
    """
    便捷函数：对单个文本进行纠错

    Args:
        text: 待纠错文本
        model_name: 模型名称

    Returns:
        {
            "source": 原始文本,
            "target": 纠错后文本,
            "errors": [("错字", "正字", 位置), ...],
            "corrected": 是否被纠正
        }
    """
    corrector = get_corrector(model_name)
    return corrector.correct(text)


def correct_and_compare(
    asr_text: str,
    gt_text: str = None,
    model_name: str = "shibing624/macbert4csc-base-chinese"
) -> Dict[str, Any]:
    """
    纠错并对比 GT（Ground Truth）

    Args:
        asr_text: ASR 识别结果
        gt_text: 标准答案（可选）
        model_name: 模型名称

    Returns:
        包含纠错信息和对比结果的字典
    """
    corrector = get_corrector(model_name)
    correction = corrector.correct(asr_text)

    result = {
        "asr_text": asr_text,
        "corrected_text": correction["target"],
        "errors": correction["errors"],
        "was_corrected": correction["corrected"],
    }

    if gt_text is not None:
        result["gt_text"] = gt_text
        result["asr_matches_gt"] = asr_text.strip() == gt_text.strip()
        result["corrected_matches_gt"] = correction["target"].strip() == gt_text.strip()

        # 计算改进
        from difflib import SequenceMatcher
        asr_sim = SequenceMatcher(None, asr_text, gt_text).ratio()
        corrected_sim = SequenceMatcher(None, correction["target"], gt_text).ratio()

        result["asr_similarity"] = asr_sim
        result["corrected_similarity"] = corrected_sim
        result["improved"] = corrected_sim > asr_sim

    return result
