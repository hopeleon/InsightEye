from __future__ import annotations

from email.parser import BytesParser
import contextlib
from email.policy import default
import io
import mimetypes
import sqlite3
import json
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Optional, List
from urllib.parse import urlparse

import numpy as np

from .analysis import analyze_interview_full
from .audio_transcription import AudioTranscriptionError, transcribe_audio_bytes, transcribe_audio_chunk_bytes
from .config import BASE_DIR, STATIC_DIR, REALTIME_WS_PORT
from .realtime_analyzer import build_realtime_transcript
from .realtime_session import store as realtime_store
from .speaker_database import SpeakerDatabase

# ==================== 声纹数据库 API 实现 ====================

# 全局数据库实例（延迟初始化，避免启动时模型未就绪）
_speaker_db: Optional[SpeakerDatabase] = None


def _get_speaker_db() -> SpeakerDatabase:
    """获取声纹数据库实例（懒加载）"""
    global _speaker_db
    if _speaker_db is None:
        _speaker_db = SpeakerDatabase()
    return _speaker_db


def _serve_speaker_list(handler: BaseHTTPRequestHandler) -> None:
    """GET /api/speakers — 返回所有声纹人员列表"""
    try:
        db = _get_speaker_db()
        speakers = db.load_all(active_only=True)
        stats = db.get_stats()
        # 返回不含 embedding 的摘要（减少传输量），但包含识别统计
        safe_speakers = []
        for s in speakers:
            # 安全地获取数值字段，确保不会返回负数或 None
            sample_count = s.get("sample_count")
            sample_count = max(0, int(sample_count)) if sample_count is not None else 0

            quality = s.get("quality")
            quality = float(quality) if quality is not None else 0.0

            total_idents = s.get("total_identifications")
            total_idents = max(0, int(total_idents)) if total_idents is not None else 0

            last_conf = s.get("last_confidence")
            last_conf = round(float(last_conf), 3) if last_conf is not None else None

            avg_conf = s.get("avg_confidence")
            avg_conf = round(float(avg_conf), 3) if avg_conf is not None else None

            safe_speakers.append({
                "speaker_id": s.get("speaker_id"),
                "name": s.get("name"),
                "role": s.get("role"),
                "department": s.get("department"),
                "sample_count": sample_count,
                "quality": quality,
                "registered_at": s.get("registered_at"),
                "updated_at": s.get("updated_at"),
                "is_active": bool(s.get("is_active", True)),
                # 识别统计
                "total_identifications": total_idents,
                "avg_confidence": avg_conf,
                "last_recognized_at": s.get("last_recognized_at"),
                "last_confidence": last_conf,
                # 声纹向量统计特性
                "embedding_std_mean": s.get("embedding_std_mean"),
                "embedding_std_max": s.get("embedding_std_max"),
            })
        _json_response(handler, {"speakers": safe_speakers, "stats": stats})
    except Exception as exc:
        import traceback
        traceback.print_exc()
        _json_response(handler, {"error": f"加载声纹数据库失败: {exc}", "speakers": [], "stats": {}}, status=500)


def _serve_speaker_stats(handler: BaseHTTPRequestHandler) -> None:
    """GET /api/speakers/stats — 返回统计信息"""
    db = _get_speaker_db()
    stats = db.get_stats()
    similarity_dist = db.compute_similarity_distribution()
    _json_response(handler, {
        **stats,
        "similarity_distribution": similarity_dist[:50],  # 最多返回 top 50 相似对
    })


def _convert_audio_to_pcm(audio_bytes: bytes, filename: str, mime_type: str) -> np.ndarray:
    """
    将任意音频格式（PCM/WAV/MP3/OGG/FLAC/AAC 等）转换为 16kHz mono int16 PCM numpy 数组。
    优先级：soundfile > torchaudio > ffmpeg subprocess
    """
    import tempfile, subprocess, os

    PCM_SIGNATURE = b"RIFF"
    WAV_SIGNATURE = b"WAVE"

    # 1. 已经是原始 PCM（裸 int16）—— 直接返回
    if audio_bytes[:4] == PCM_SIGNATURE or (
        len(audio_bytes) % 2 == 0
        and not filename.lower().endswith(('.mp3', '.ogg', '.flac', '.aac', '.m4a', '.wma'))
    ):
        if len(audio_bytes) % 2 != 0:
            audio_bytes = audio_bytes[:-1]
        return np.frombuffer(audio_bytes, dtype=np.int16)

    # 2. WAV 文件 —— soundfile 直接解析
    if filename.lower().endswith(".wav") or "wav" in mime_type.lower():
        import soundfile as sf
        data, sr = sf.read(io.BytesIO(audio_bytes))
        return _resample_to_16k_mono(data, sr)

    # 3. MP3 / OGG / FLAC 等 —— 尝试 soundfile（含 libsndfile，支持大多数格式）
    try:
        import soundfile as sf
        data, sr = sf.read(io.BytesIO(audio_bytes))
        return _resample_to_16k_mono(data, sr)
    except Exception:
        pass  # soundfile 不支持该格式，尝试下一个方案

    # 4. 兜底：ffmpeg 转码
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "wav"
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp_in:
        tmp_in.write(audio_bytes)
        tmp_in.flush()
        tmp_in_name = tmp_in.name

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_out:
            tmp_out_name = tmp_out.name

        result = subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", tmp_in_name,
                "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
                tmp_out_name,
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr.decode(errors='replace')}")

        with open(tmp_out_name, "rb") as f:
            wav_bytes = f.read()

        import soundfile as sf
        data, sr = sf.read(io.BytesIO(wav_bytes))
        return _resample_to_16k_mono(data, sr)
    finally:
        os.unlink(tmp_in_name)
        if "tmp_out_name" in dir():
            os.unlink(tmp_out_name)


def _resample_to_16k_mono(audio_data: np.ndarray, sr: int) -> np.ndarray:
    """将任意采样率/声道的音频转换为 16kHz mono int16"""
    TARGET_SR = 16000

    # float32 / float64 → 归一化 float32
    if audio_data.dtype in (np.float32, np.float64):
        if audio_data.dtype == np.float64:
            audio_data = audio_data.astype(np.float32)
        audio_data = np.clip(audio_data, -1.0, 1.0)
        audio_int16 = (audio_data * 32767.0).astype(np.int16)
    else:
        audio_int16 = audio_data.astype(np.int16)

    # 多声道 → 单声道
    if audio_int16.ndim > 1:
        audio_int16 = np.mean(audio_int16, axis=1).astype(np.int16)

    # 已是 16kHz
    if sr == TARGET_SR:
        return audio_int16

    # 重采样（scipy）
    from scipy import signal
    num_samples = int(len(audio_int16) * TARGET_SR / sr)
    resampled = signal.resample_poly(audio_int16, TARGET_SR, sr)
    return resampled.astype(np.int16)


def _run_speaker_register(handler: BaseHTTPRequestHandler, fields: dict, files: dict) -> None:
    """POST /api/speakers/register — 注册新人声纹（支持多段音频）"""
    # 提取字段
    name = (fields.get("name") or "").strip()
    role = (fields.get("role") or "").strip() or None
    department = (fields.get("department") or "").strip() or None
    speaker_id = (fields.get("speaker_id") or "").strip()

    if not name:
        _json_response(handler, {"error": "姓名（name）为必填项"}, status=400)
        return

    if not speaker_id:
        # 自动生成：拼音首字母 + 时间戳
        import time
        def to_pinyin_initials(s):
            m = {"张":"Z","李":"L","王":"W","刘":"H","陈":"C","杨":"Y","赵":"H","黄":"H",
                 "周":"Z","吴":"W","徐":"X","孙":"S","马":"M","胡":"H","朱":"Z","郭":"G",
                 "何":"H","高":"G","林":"L","罗":"H","钱":"Q","冯":"F","褚":"C","卫":"W",
                 "蒋":"J","沈":"S","韩":"H"}
            initials = "".join(m.get(c, c[0].upper() if c.isalpha() else "") for c in s if c not in " \t")
            return initials or "P"
        speaker_id = f"{to_pinyin_initials(name)}_{int(time.time())}"

    # 获取所有音频文件（支持单段和多段）
    audio_files = files.get("audio", [])
    if not audio_files:
        _json_response(handler, {"error": "音频文件（audio）为必填项"}, status=400)
        return

    # 使用 CAM++ 提取声纹
    try:
        from .model_manager import get_model_manager, SpeakerEmbeddingExtractor
        mm = get_model_manager()
        if not mm.is_initialized():
            _json_response(handler, {"error": "模型尚未加载完成，请稍后重试"}, status=503)
            return
        camp = mm.get_camp_model()
        if camp is None:
            _json_response(handler, {"error": "CAM++ 模型未加载，声纹注册暂不可用"}, status=503)
            return
        extractor = SpeakerEmbeddingExtractor(camp, device=mm.device)

        embeddings = []
        quality_scores = []
        sample_count = len(audio_files)

        for i, audio_file in enumerate(audio_files):
            audio_bytes = audio_file["content"]
            audio_filename = audio_file.get("filename", f"voice_{i}.pcm")
            audio_mime = audio_file.get("content_type", "application/octet-stream")

            # 将任意音频格式转换为 16kHz mono int16 PCM
            try:
                audio_int16 = _convert_audio_to_pcm(audio_bytes, audio_filename, audio_mime)
            except Exception as exc:
                _json_response(handler, {"error": f"音频格式转换失败 (样本 {i+1}): {exc}"}, status=400)
                return

            # 转换音频：int16 PCM bytes → float32 numpy
            audio_float32 = audio_int16.astype(np.float32) / 32768.0

            if len(audio_float32) < mm.vad_model_samplerate * 0.5:
                continue  # 跳过过短的音频

            # 提取声纹
            try:
                embedding = extractor.extract(audio_float32)
                embeddings.append(embedding)

                # 声纹质量评估
                energy = float(np.sqrt(np.mean(audio_float32 ** 2)))
                emb_norm = float(np.linalg.norm(embedding))
                energy_score = min(1.0, energy / 0.15) if energy < 0.15 else max(0.5, 1.0 - (energy - 0.15) / 0.35)
                emb_score = 1.0 if 0.9 <= emb_norm <= 1.1 else max(0.3, 1.0 - abs(emb_norm - 1.0) * 2)
                duration_s = len(audio_float32) / 16000.0
                duration_score = min(1.0, duration_s / 3.0)
                q = round(energy_score * 0.4 + emb_score * 0.4 + duration_score * 0.2, 2)
                quality_scores.append(max(0.1, min(0.99, q)))
            except Exception as exc:
                print(f"[注册] 样本 {i+1} 声纹提取失败: {exc}")
                continue

        if len(embeddings) == 0:
            _json_response(handler, {"error": "所有音频样本均无效（时长过短或提取失败）"}, status=400)
            return

        # 多样本融合：计算平均 embedding
        embeddings_arr = np.array(embeddings)
        final_embedding = np.mean(embeddings_arr, axis=0)
        final_embedding = final_embedding / (np.linalg.norm(final_embedding) + 1e-8)

        # 平均质量
        final_quality = np.mean(quality_scores) if quality_scores else 0.5

        # 如果有多个样本，计算样本间一致性作为额外质量指标
        if len(embeddings) >= 2:
            pair_sims = []
            for ii in range(len(embeddings)):
                for jj in range(ii + 1, len(embeddings)):
                    sim = float(np.dot(embeddings[ii], embeddings[jj]) /
                               (np.linalg.norm(embeddings[ii]) * np.linalg.norm(embeddings[jj]) + 1e-8))
                    pair_sims.append(sim)
            consistency = np.mean(pair_sims)
            # 质量 = 平均质量 * 样本一致性
            final_quality = final_quality * (0.7 + 0.3 * consistency)

    except Exception as exc:
        import traceback
        traceback.print_exc()
        _json_response(handler, {"error": f"声纹提取失败: {exc}"}, status=500)
        return

    # 保存到数据库
    db = _get_speaker_db()
    try:
        saved = db.save_speaker(
            speaker_id=speaker_id,
            embedding=final_embedding.astype(np.float32),
            name=name,
            role=role,
            department=department,
            individual_embeddings=[e.astype(np.float32) for e in embeddings],
            quality=final_quality,
            embedding_mean=final_embedding.astype(np.float32),
            sample_count=len(embeddings),
            overwrite=False,
        )
        if not saved:
            _json_response(handler, {"error": f"声纹ID「{speaker_id}」已存在，请使用其他ID"}, status=409)
            return
    except Exception as exc:
        _json_response(handler, {"error": f"数据库保存失败: {exc}"}, status=500)
        return

    _json_response(handler, {
        "success": True,
        "speaker_id": speaker_id,
        "name": name,
        "message": f"「{name}」声纹注册成功！",
        "quality": final_quality,
        "sample_count": len(embeddings),
    })


def _serve_speaker_delete(handler: BaseHTTPRequestHandler) -> None:
    """POST /api/speakers/delete — 删除声纹人员"""
    if handler.command != "POST":
        _json_response(handler, {"error": "Method not allowed"}, status=405)
        return
    content_length = int(handler.headers.get("Content-Length", "0"))
    payload = _parse_payload(handler.rfile.read(content_length))
    if payload is None:
        _json_response(handler, {"error": "Body must be valid JSON"}, status=400)
        return
    speaker_id = (payload.get("speaker_id") or "").strip()
    if not speaker_id:
        _json_response(handler, {"error": "speaker_id 为必填项"}, status=400)
        return
    db = _get_speaker_db()
    ok = db.deactivate_speaker(speaker_id)
    if not ok:
        _json_response(handler, {"error": f"未找到声纹ID「{speaker_id}」"}, status=404)
        return
    _json_response(handler, {"success": True, "speaker_id": speaker_id, "message": "已删除"})


def _serve_speaker_search(handler: BaseHTTPRequestHandler) -> None:
    """GET /api/speakers/search?name=xxx — 搜索声纹人员"""
    parsed = urlparse(handler.path)
    from urllib.parse import parse_qs
    params = parse_qs(parsed.query)
    keyword = (params.get("name", [""])[0] or "").strip()
    db = _get_speaker_db()
    if keyword:
        results = db.search_by_name(keyword)
    else:
        results = db.load_all(active_only=True)
    safe = []
    for s in results:
        safe.append({
            "speaker_id": s.get("speaker_id"),
            "name": s.get("name"),
            "role": s.get("role"),
            "department": s.get("department"),
            "sample_count": s.get("sample_count", 0),
            "quality": s.get("quality", 0.0),
            "registered_at": s.get("registered_at"),
            "is_active": s.get("is_active", True),
        })
    _json_response(handler, {"speakers": safe, "total": len(safe)})

_server_host: str = "127.0.0.1"  # run() 时由主线程写入，Docker 模式下自动设为 localhost
from .realtime_ws_server import bridge_server

SAMPLES_DIR = BASE_DIR / "samples"
llm_tasks: dict[str, dict[str, Any]] = {}
tasks_lock = Lock()


def generate_task_id() -> str:
    return str(uuid.uuid4())


def run_full_analysis_async(task_id: str, transcript: str, job_hint: str, force_llm: bool) -> None:
    from workflow.engine import run_disc_workflow, run_local_workflow, should_trigger_llm

    try:
        with tasks_lock:
            llm_tasks[task_id]["status"] = "local_running"
            llm_tasks[task_id]["progress"] = "Running local rule analysis..."

        local_result = run_local_workflow(transcript, job_hint)
        need_llm, reason = should_trigger_llm(local_result)
        if force_llm:
            need_llm = True
            reason = "LLM analysis forced by user"

        with tasks_lock:
            llm_tasks[task_id]["status"] = "local_completed"
            llm_tasks[task_id]["local_result"] = local_result
            llm_tasks[task_id]["llm_triggered"] = need_llm
            llm_tasks[task_id]["llm_reason"] = reason
            llm_tasks[task_id]["progress"] = "Local analysis completed"

        if not need_llm:
            with tasks_lock:
                llm_tasks[task_id]["status"] = "completed"
                llm_tasks[task_id]["progress"] = "Completed without LLM"
            return

        with tasks_lock:
            llm_tasks[task_id]["status"] = "llm_running"
            llm_tasks[task_id]["progress"] = "Running LLM analysis..."

        llm_result = run_disc_workflow(transcript, job_hint)
        with tasks_lock:
            llm_tasks[task_id]["status"] = "completed"
            llm_tasks[task_id]["llm_result"] = llm_result
            llm_tasks[task_id]["progress"] = "LLM analysis completed"
    except Exception as exc:
        with tasks_lock:
            llm_tasks[task_id]["status"] = "failed"
            llm_tasks[task_id]["error"] = str(exc)
            llm_tasks[task_id]["progress"] = f"Failed: {exc}"


def _json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.end_headers()
    with contextlib.suppress((BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
        handler.wfile.write(body)


def _serve_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    if not path.exists() or not path.is_file():
        handler.send_error(HTTPStatus.NOT_FOUND, "File not found")
        return
    mime_type, _ = mimetypes.guess_type(str(path))
    data = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", f"{mime_type or 'application/octet-stream'}; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.end_headers()
    handler.wfile.write(data)


def _parse_payload(raw_body: bytes) -> dict | None:
    try:
        return json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        return None

def _parse_multipart_form(handler: BaseHTTPRequestHandler) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]]]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    body = handler.rfile.read(content_length)
    raw = b"Content-Type: " + handler.headers.get("Content-Type", "").encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    message = BytesParser(policy=default).parsebytes(raw)

    fields: dict[str, str] = {}
    files: dict[str, list[dict[str, Any]]] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            # 多文件支持：同一 name 的多个文件存为列表
            if name not in files:
                files[name] = []
            files[name].append({
                "filename": filename,
                "content": payload,
                "content_type": part.get_content_type(),
            })
        else:
            fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    return fields, files


def _run_audio_transcription(handler: BaseHTTPRequestHandler, fields: dict[str, str], files: dict[str, list[dict[str, Any]]]) -> None:
    audio_list = files.get("audio", [])
    file_item = audio_list[0] if audio_list else None
    if not file_item:
        _json_response(handler, {"error": "Missing audio file"}, status=400)
        return

    audio_bytes = file_item["content"]
    filename = file_item.get("filename") or "interview_audio.wav"
    mime_type = file_item.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    language = str(fields.get("language", "zh") or "zh").strip() or "zh"

    try:
        result = transcribe_audio_bytes(audio_bytes, filename=filename, mime_type=mime_type, language=language)
    except AudioTranscriptionError as exc:
        _json_response(handler, {"error": str(exc)}, status=400)
        return

    _json_response(
        handler,
        {
            "model": result["model"],
            "language": result["language"],
            "segment_count": len(result["segments"]),
            "segments": result["segments"],
            "transcript_preview": build_realtime_transcript(result["segments"]),
        },
    )


def _run_realtime_chunk_transcription(handler: BaseHTTPRequestHandler, session_id: str, fields: dict[str, str], files: dict[str, list[dict[str, Any]]]) -> None:
    audio_list = files.get("audio", [])
    file_item = audio_list[0] if audio_list else None
    if not file_item:
        _json_response(handler, {"error": "Missing audio file"}, status=400)
        return

    audio_bytes = file_item["content"]
    filename = file_item.get("filename") or "live_chunk.webm"
    mime_type = file_item.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    language = str(fields.get("language", "zh") or "zh").strip() or "zh"
    speaker_id = str(fields.get("speaker_id", "speaker_a") or "speaker_a").strip() or "speaker_a"
    start_ms = int(str(fields.get("start_ms", "0") or "0"))
    end_ms = int(str(fields.get("end_ms", "0") or "0"))

    print(f"[ChunkTranscribe] session={session_id} speaker={speaker_id} bytes={len(audio_bytes)} start_ms={start_ms} end_ms={end_ms}")
    try:
        result = transcribe_audio_chunk_bytes(
            audio_bytes,
            filename=filename,
            mime_type=mime_type,
            language=language,
            speaker_id=speaker_id,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    except AudioTranscriptionError as exc:
        print(f"[ChunkTranscribe] failed session={session_id} speaker={speaker_id} error={exc}")
        _json_response(handler, {"error": str(exc)}, status=400)
        return

    session = realtime_store.status(session_id)
    segment = result.get("segment")
    if segment:
        session = realtime_store.append_segment(session_id, segment)

    _json_response(
        handler,
        {
            "session": _realtime_session_response(session),
            "transcribed": bool(segment),
            "text": result.get("text", ""),
            "speaker_id": speaker_id,
            "model": result.get("model"),
        },
    )


def _run_full_mode_analysis(handler: BaseHTTPRequestHandler, payload: dict) -> None:
    transcript = (payload.get("interview_transcript") or "").strip()
    if not transcript:
        _json_response(handler, {"error": "Missing interview_transcript"}, status=400)
        return
    job_hint = (payload.get("job_hint_optional") or "").strip()
    report = analyze_interview_full(transcript, job_hint)
    _json_response(handler, report)


def _realtime_session_response(session: dict[str, Any]) -> dict[str, Any]:
    rolling = session.get("rolling_analysis") or {}
    voice_mapping = session.get("voice_mapping", {})
    rolling_disc = session.get("rolling_disc_analysis") or {}
    return {
        "session_id": session["session_id"],
        "status": session["status"],
        "job_hint_optional": session.get("job_hint", ""),
        "segment_count": len(session.get("segments") or []),
        "segments": session.get("segments") or [],
        "voice_registered": session.get("voice_registered", False),
        "voice_mapping": voice_mapping,
        "display_transcript": build_realtime_transcript(
            session.get("segments") or [],
            voice_mapping
        ),
        "rolling_analysis": {
            "summary": rolling.get("summary", ""),
            "risk_summary": rolling.get("risk_summary", ""),
            "evidence_gaps": rolling.get("evidence_gaps", []),
            "follow_up_questions": rolling.get("follow_up_questions", []),
            "recommended_action": rolling.get("recommended_action", ""),
            "mbti_type": rolling.get("mbti_type", ""),
            "mbti_summary": rolling.get("mbti_summary", ""),
            "local_result": rolling.get("local_result"),
        },
        "rolling_disc_analysis": rolling_disc,
        "final_report": session.get("final_report"),
    }


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        route = urlparse(self.path).path

        if route.startswith("/api/llm_status/"):
            task_id = route.replace("/api/llm_status/", "")
            with tasks_lock:
                task = llm_tasks.get(task_id)
            if not task:
                _json_response(self, {"error": "Task not found"}, status=404)
                return

            response = {
                "task_id": task_id,
                "status": task["status"],
                "progress": task.get("progress", ""),
            }
            if task["status"] in {"local_completed", "llm_running", "completed"}:
                response["local_result"] = task.get("local_result")
                response["llm_triggered"] = task.get("llm_triggered", False)
                response["llm_reason"] = task.get("llm_reason", "")
            if task["status"] == "completed" and task.get("llm_result"):
                response["llm_result"] = task.get("llm_result")
            if task["status"] == "failed":
                response["error"] = task.get("error", "Unknown error")
            _json_response(self, response)

            # 已完成或失败的任务及时清理，避免 llm_tasks 字典无限增长
            if task["status"] in ("completed", "failed"):
                with tasks_lock:
                    llm_tasks.pop(task_id, None)
                print(f"[Server] 清理已完成任务 {task_id}，llm_tasks 剩余 {len(llm_tasks)} 个")
            return

        if route.startswith("/api/realtime/session/") and route.endswith("/status"):
            session_id = route.replace("/api/realtime/session/", "", 1).replace("/status", "", 1).strip("/")
            try:
                session = realtime_store.status(session_id)
            except KeyError:
                _json_response(self, {"error": "Realtime session not found"}, status=404)
                return
            _json_response(self, _realtime_session_response(session))
            return

        # ==================== 声纹数据库管理 API ====================
        if route == "/api/speakers":
            _serve_speaker_list(self)
            return

        if route == "/api/speakers/stats":
            _serve_speaker_stats(self)
            return

        if route == "/api/speakers/search":
            _serve_speaker_search(self)
            return

        if route == "/":
            _serve_file(self, STATIC_DIR / "index.html")
            return
        if route.startswith("/static/"):
            _serve_file(self, STATIC_DIR / route.replace("/static/", "", 1))
            return
        if route.startswith("/samples/"):
            _serve_file(self, SAMPLES_DIR / route.replace("/samples/", "", 1))
            return
        if route == "/api/health":
            _json_response(self, {"ok": True})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        content_type = self.headers.get("Content-Type", "")

        if route == "/api/audio/transcribe":
            if "multipart/form-data" not in content_type:
                _json_response(self, {"error": "Content-Type must be multipart/form-data"}, status=400)
                return
            fields, files = _parse_multipart_form(self)
            _run_audio_transcription(self, fields, files)
            return

        if route.startswith("/api/realtime/session/") and route.endswith("/transcribe_chunk"):
            if "multipart/form-data" not in content_type:
                _json_response(self, {"error": "Content-Type must be multipart/form-data"}, status=400)
                return
            session_id = route.replace("/api/realtime/session/", "", 1).replace("/transcribe_chunk", "", 1).strip("/")
            try:
                realtime_store.status(session_id)
            except KeyError:
                _json_response(self, {"error": "Realtime session not found"}, status=404)
                return
            fields, files = _parse_multipart_form(self)
            _run_realtime_chunk_transcription(self, session_id, fields, files)
            return

        # ==================== 声纹数据库管理 API (POST multipart) ====================
        if route == "/api/speakers/register":
            if "multipart/form-data" not in content_type:
                _json_response(self, {"error": "Content-Type must be multipart/form-data"}, status=400)
                return
            fields, files = _parse_multipart_form(self)
            _run_speaker_register(self, fields, files)
            return

        if route == "/api/speakers/delete":
            _serve_speaker_delete(self)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        payload = _parse_payload(self.rfile.read(content_length))
        if payload is None:
            _json_response(self, {"error": "Body must be valid JSON"}, status=400)
            return

        if route == "/api/analyze/full":
            _run_full_mode_analysis(self, payload)
            return

        if route == "/api/analyze":
            transcript = (payload.get("interview_transcript") or "").strip()
            job_hint = (payload.get("job_hint_optional") or "").strip()
            force_llm = bool(payload.get("force_llm", False))
            if not transcript:
                _json_response(self, {"error": "Missing interview transcript"}, status=400)
                return

            task_id = generate_task_id()
            with tasks_lock:
                llm_tasks[task_id] = {
                    "status": "local_pending",
                    "progress": "Preparing local analysis...",
                    "transcript": transcript,
                    "job_hint": job_hint,
                    "force_llm": force_llm,
                    "local_result": None,
                    "llm_result": None,
                    "error": None,
                    "llm_triggered": False,
                    "llm_reason": "",
                }

            Thread(
                target=run_full_analysis_async,
                args=(task_id, transcript, job_hint, force_llm),
                daemon=True,
            ).start()
            _json_response(self, {"task_id": task_id, "message": "Task started"})
            return

        if route == "/api/realtime/session/start":
            job_hint = (payload.get("job_hint_optional") or "").strip()
            session = realtime_store.create(job_hint=job_hint)
            # 注入声纹数据库实例，供 Mode 2 自动识别使用
            session["speaker_database"] = _get_speaker_db()
            _json_response(
                self,
                {
                    "session_id": session["session_id"],
                    "status": session["status"],
                    "message": "Realtime session started",
                    "append_path": f"/api/realtime/session/{session['session_id']}/append",
                    "status_path": f"/api/realtime/session/{session['session_id']}/status",
                    "end_path": f"/api/realtime/session/{session['session_id']}/end",
                    "ws_url": f"ws://{_server_host}:{REALTIME_WS_PORT}/realtime?session_id={session['session_id']}",
                },
            )
            return

        if route.startswith("/api/realtime/session/") and route.endswith("/append"):
            session_id = route.replace("/api/realtime/session/", "", 1).replace("/append", "", 1).strip("/")
            try:
                session = realtime_store.append_segment(session_id, payload)
            except KeyError:
                _json_response(self, {"error": "Realtime session not found"}, status=404)
                return
            except ValueError as exc:
                _json_response(self, {"error": str(exc)}, status=400)
                return
            _json_response(self, _realtime_session_response(session))
            return

        if route.startswith("/api/realtime/session/") and route.endswith("/end"):
            session_id = route.replace("/api/realtime/session/", "", 1).replace("/end", "", 1).strip("/")
            try:
                session = realtime_store.end(session_id)
            except KeyError:
                _json_response(self, {"error": "Realtime session not found"}, status=404)
                return
            _json_response(self, _realtime_session_response(session))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args) -> None:
        return


def run(host: str = "127.0.0.1", port: int = 8001) -> None:
    global _server_host
    # Docker 容器绑定 0.0.0.0 时，宿主机浏览器通过 localhost 访问
    _server_host = "localhost" if host == "0.0.0.0" else host

    # 启动时清空历史识别记录，使今日识别次数归零
    try:
        db = _get_speaker_db()
        db.clear_identification_log()
        print("[Server] 已清空历史识别记录，识别计数器已重置")
    except Exception as e:
        print(f"[Server] 清空识别记录失败: {e}")

    bridge_server.start(host=host, port=REALTIME_WS_PORT)
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"InsightEye demo running at http://{host}:{port}")
    print(f"InsightEye realtime websocket running at ws://{host}:{REALTIME_WS_PORT}/realtime")
    server.serve_forever()
