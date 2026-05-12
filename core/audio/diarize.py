# Version: 03.01.05
# Phase: PHASE1-B
"""
diarize.py - AI 화자 분리 (SpeechBrain 엔진 적용 완료)
[추가] 첫 음성 화자 1번 강제 할당 (시간순 정렬)
[추가] 대표님 목소리 지문(Embedding) 학습 및 화자 1번 강제 매칭 알고리즘 
"""
import os
import time
import json
import threading
import importlib.util
import numpy as np
from core.audio.runtime_cleanup import clear_audio_model_memory_caches
from core.audio.torch_acceleration import move_torch_model_to_preferred_device
from core.runtime.logger import get_logger


_DIARIZE_DEPENDENCIES = (
    ("torch", "torch"),
    ("torchaudio", "torchaudio"),
    ("speechbrain", "speechbrain"),
    ("sklearn", "scikit-learn"),
)
_missing_dependency_notice_logged = False
_SPEAKER_CACHE_SCHEMA = "ai_subtitle_studio.diarization_cache.v2"


def missing_diarization_packages() -> list[str]:
    missing = []
    for module_name, package_name in _DIARIZE_DEPENDENCIES:
        try:
            if importlib.util.find_spec(module_name) is None:
                missing.append(package_name)
        except (ImportError, ValueError):
            missing.append(package_name)
    return missing


def diarization_dependencies_available(*, log: bool = False) -> bool:
    missing = missing_diarization_packages()
    if missing and log:
        log_missing_diarization_dependencies(missing)
    return not missing


def log_missing_diarization_dependencies(missing: list[str] | None = None) -> None:
    global _missing_dependency_notice_logged
    missing = list(missing or missing_diarization_packages())
    if not missing or _missing_dependency_notice_logged:
        return
    _missing_dependency_notice_logged = True
    packages = " ".join(missing)
    get_logger().log(
        "⚠️ [화자 분리] 선택 화자 수가 2명 이상이지만 필요한 패키지가 없습니다. "
        f"누락: {packages}. 이번 작업은 단일 화자로 계속 진행합니다. "
        f"화자 분리가 필요하면 venv/bin/python -m pip install {packages}"
    )


def _normalize_speaker_id(raw) -> str:
    speaker = str(raw or "").strip()
    if speaker.startswith("SPEAKER_"):
        speaker = speaker.replace("SPEAKER_", "", 1)
    return speaker or "00"


def _clean_caption_line(text: str) -> str:
    parts: list[str] = []
    for raw_line in str(text or "").replace("\u2028", "\n").splitlines():
        line = " ".join(str(raw_line or "").split()).strip()
        if line.startswith("-"):
            line = line[1:].strip()
        if line:
            parts.append(line)
    return " ".join(parts).strip()


def _load_cached_speaker_map(cache_file: str, *, min_speakers: int, max_speakers: int) -> list[dict]:
    if not os.path.exists(cache_file):
        return []
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return []

    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    cached_map = payload.get("speaker_map")
    if not isinstance(cached_map, list):
        return []
    if str(payload.get("schema") or "") not in {"", _SPEAKER_CACHE_SCHEMA}:
        return []
    try:
        cached_min = int(payload.get("min_speakers", min_speakers) or min_speakers)
        cached_max = int(payload.get("max_speakers", max_speakers) or max_speakers)
    except Exception:
        cached_min = int(min_speakers or 1)
        cached_max = int(max_speakers or 1)
    if cached_min != int(min_speakers or 1) or cached_max != int(max_speakers or 1):
        return []
    return [dict(item) for item in cached_map if isinstance(item, dict)]


def _save_cached_speaker_map(
    cache_file: str,
    speaker_map: list[dict],
    *,
    min_speakers: int,
    max_speakers: int,
    detected_speakers: int,
) -> None:
    payload = {
        "schema": _SPEAKER_CACHE_SCHEMA,
        "min_speakers": int(min_speakers or 1),
        "max_speakers": int(max_speakers or 1),
        "detected_speakers": int(detected_speakers or 1),
        "speaker_map": [dict(item) for item in list(speaker_map or []) if isinstance(item, dict)],
    }
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _estimate_speaker_count(
    embeddings: np.ndarray,
    *,
    min_speakers: int,
    max_speakers: int,
) -> tuple[int, dict]:
    try:
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
    except Exception:
        return max(1, min(int(max_speakers or 1), 3)), {
            "reason": "metrics_unavailable",
            "candidates": [],
        }

    total = int(len(embeddings) or 0)
    upper = max(1, min(int(max_speakers or 1), 3, total))
    lower = max(1, min(int(min_speakers or 1), upper))
    if total < 6 or upper <= 1:
        return max(1, lower), {
            "reason": "short_audio",
            "candidates": [],
        }

    scored: list[dict] = []
    for cluster_count in range(max(2, lower), upper + 1):
        if total < cluster_count * 2:
            continue
        try:
            kmeans = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
            labels = kmeans.fit_predict(embeddings)
        except Exception:
            continue
        unique = sorted(set(int(item) for item in list(labels)))
        if len(unique) < 2:
            continue
        try:
            score = float(silhouette_score(embeddings, labels))
        except Exception:
            continue
        counts = np.bincount(labels, minlength=cluster_count).astype(int).tolist()
        smallest = min(counts or [0])
        largest = max(counts or [1])
        balance = float(smallest) / float(max(1, largest))
        penalty = 0.0
        if balance < 0.08:
            penalty = 0.08
        elif balance < 0.14:
            penalty = 0.03
        adjusted = score - penalty
        scored.append(
            {
                "count": cluster_count,
                "score": round(score, 4),
                "adjusted": round(adjusted, 4),
                "balance": round(balance, 4),
                "counts": counts,
            }
        )

    if not scored:
        return max(1, lower), {
            "reason": "insufficient_candidates",
            "candidates": [],
        }

    scored.sort(key=lambda item: (float(item.get("adjusted", -1.0)), float(item.get("score", -1.0))), reverse=True)
    best = dict(scored[0])
    detected = int(best.get("count", 1) or 1)
    adjusted = float(best.get("adjusted", 0.0) or 0.0)
    if lower <= 1 and adjusted < 0.12:
        detected = 1
    elif detected == 3 and len(scored) > 1:
        second = dict(scored[1])
        if int(second.get("count", 1) or 1) == 2:
            if adjusted - float(second.get("adjusted", adjusted) or adjusted) < 0.025:
                detected = 2

    return max(lower, detected), {
        "reason": "silhouette_search",
        "selected": best,
        "candidates": scored,
    }

def get_speaker_map(file_path: str, min_speakers: int = 1, max_speakers: int = 2) -> list[dict]:
    cache_file = f"{os.path.splitext(file_path)[0]}_speaker_cache.json"
    speaker_map = _load_cached_speaker_map(
        cache_file,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )
    if speaker_map:
        get_logger().log("⚡ [캐시 적중] 이전에 분석한 화자 분리 데이터를 불러왔습니다!")
        return speaker_map

    missing = missing_diarization_packages()
    if missing:
        log_missing_diarization_dependencies(missing)
        return []

    try:
        import torch
        import torchaudio
        from speechbrain.inference.classifiers import EncoderClassifier
        from sklearn.cluster import KMeans
    except ImportError as exc:
        log_missing_diarization_dependencies(missing_diarization_packages() or [str(exc)])
        return []

    get_logger().log("⏳ SpeechBrain 화자 분석 AI 로딩 중... (HuggingFace 토큰 불필요! 🚀)")
    
    try:
        classifier = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb", 
            savedir=os.path.join(os.path.expanduser("~"), ".cache", "speechbrain")
        )

        device_name = move_torch_model_to_preferred_device(classifier.mods, log_label="화자 분리")
        if device_name != "cpu":
            classifier.device = torch.device(device_name)
        else:
            classifier.device = torch.device("cpu")
            get_logger().log("  └ 💻 CPU 연산 모드")
    except Exception as e:
        get_logger().log(f"❌ 모델 로딩 에러: {e}")
        clear_audio_model_memory_caches(include_gpu=True)
        return []

    get_logger().log(f"🧠 목소리 지문(Embedding) 추출 및 분류 시작... (최대 {max_speakers}명)")
    
    is_running = True
    start_time = time.time()
    
    def heartbeat_logger():
        while is_running:
            for _ in range(10):
                if not is_running: return
                time.sleep(1)
            if not is_running: return
            elapsed = int(time.time() - start_time)
            get_logger().log(f"  ⏳ 화자 분석 진행 중... (약 {elapsed}초 경과 - 초고속 분석 중 🚀)")

    t_logger = threading.Thread(target=heartbeat_logger, daemon=True)
    t_logger.start()
    
    speaker_map: list[dict] = []

    try:
        signal, fs = torchaudio.load(file_path)
        if signal.shape[0] > 1:
            signal = signal.mean(dim=0, keepdim=True)
        if fs != 16000:
            signal = torchaudio.functional.resample(signal, fs, 16000)
            fs = 16000
            
        signal = torch.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
        signal = signal.to(classifier.device)
        
        chunk_len = int(1.5 * fs)
        hop_len = int(0.5 * fs)
        total_samples = signal.shape[1]
        
        embeddings = []
        timestamps = []
        
        for start_samp in range(0, total_samples, hop_len):
            end_samp = start_samp + chunk_len
            if end_samp > total_samples:
                break
            chunk = signal[:, start_samp:end_samp]
            
            with torch.no_grad():
                emb = classifier.encode_batch(chunk)
                embeddings.append(emb.squeeze().cpu().numpy())
                timestamps.append((start_samp / fs, end_samp / fs))
        
        # [diarize.py] 중간 즈음 (if not embeddings: 아래 부분)

        if not embeddings:
            raise ValueError("오디오가 너무 짧거나 추출에 실패했습니다.")
            
        # 💡 [핵심 해결 1] 임베딩(목소리 지문) 정규화! 
        # 크기(음량)를 무시하고 오직 '목소리 톤'만으로 비교하여 20분 중 3분만 말하는 게스트의 목소리가 묻히지 않게 살려냅니다!
        embeddings = np.array(embeddings)
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

        detected_speakers, detection_meta = _estimate_speaker_count(
            embeddings,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        get_logger().log(
            "🗣️ [화자 분리] 전체 오디오 기준 화자 수 자동 판정: "
            f"{detected_speakers}명 (후보 {detection_meta.get('candidates', [])})"
        )

        if detected_speakers <= 1:
            labels = np.zeros(len(embeddings), dtype=int)
        else:
            kmeans = KMeans(n_clusters=detected_speakers, random_state=42, n_init=10)
            labels = kmeans.fit_predict(embeddings)
        
        smoothed_labels = list(labels)
        for i in range(1, len(labels)-1):
            if labels[i-1] == labels[i+1]:
                smoothed_labels[i] = labels[i-1]
        labels = smoothed_labels

        # 💡 [핵심] 대표님 목소리 학습 및 화자 1 고정 알고리즘
        centroids = {}
        for i, l in enumerate(labels):
            if l not in centroids: centroids[l] = []
            centroids[l].append(embeddings[i])
            
        for l in centroids:
            centroids[l] = np.mean(centroids[l], axis=0)

        _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ref_file = os.path.join(_project_root, "voice_data", "spk1_voice.wav")
        ref_emb = None
        try:
            from core.settings import load_settings
            settings = load_settings()
            ref_disabled = bool(settings.get("spk1_voice_disabled", False))
            configured = str(settings.get("spk1_voice_file", "") or "").strip()
            if configured:
                candidate = os.path.join(_project_root, "voice_data", configured)
                if os.path.exists(candidate):
                    ref_file = candidate
            elif not os.path.exists(ref_file):
                import glob
                candidates = sorted(glob.glob(os.path.join(_project_root, "voice_data", "spk1_*.wav")))
                if candidates:
                    ref_file = candidates[0]
        except Exception:
            ref_disabled = False
        if ref_disabled:
            get_logger().log("🔇 화자 1 학습 데이터가 사용 해제되어 목소리 매칭을 건너뜁니다.")
        if os.path.exists(ref_file) and not ref_disabled:
            get_logger().log(f"🔊 화자 학습 데이터 사용: {ref_file}")
            try:
                get_logger().log("🎙️ 대표님 목소리(화자 1) 지문 데이터를 분석하여 우선 매칭합니다...")
                r_sig, r_fs = torchaudio.load(ref_file)
                if r_sig.shape[0] > 1: r_sig = r_sig.mean(dim=0, keepdim=True)
                if r_fs != 16000: r_sig = torchaudio.functional.resample(r_sig, r_fs, 16000)
                
                # 메모리 방지를 위해 학습 데이터는 첫 15초만 잘라서 핵심 톤만 파악
                max_samples = 16000 * 15
                if r_sig.shape[1] > max_samples: r_sig = r_sig[:, :max_samples]
                
                r_sig = torch.nan_to_num(r_sig, nan=0.0, posinf=0.0, neginf=0.0).to(classifier.device)
                with torch.no_grad():
                    ref_emb = classifier.encode_batch(r_sig).squeeze().cpu().numpy()
            except Exception as e:
                get_logger().log(f"⚠️ 목소리 학습 데이터 분석 실패 (시간순 분리로 자동 전환): {e}")

        # [diarize.py] 대표님 목소리 매칭 및 번호 할당 로직 부분 교체
        # [diarize.py] 화자 번호 할당 및 정렬 로직 수정
        mapping = {}
        if ref_emb is not None:
            best_sim = -1
            best_label = None
            # 영상 속 목소리들 중 대표님 목소리와 가장 똑같은 톤 찾기 (코사인 유사도)
            for l, centroid in centroids.items():
                sim = np.dot(ref_emb, centroid) / (np.linalg.norm(ref_emb) * np.linalg.norm(centroid))
                if sim > best_sim:
                    best_sim = sim
                    best_label = l
                    
            # 💡 유사도 기준을 충족하여 대표님(0번)으로 확정된 경우에만 0번을 사용합니다.
            if best_label is not None and best_sim > 0.2: 
                mapping[best_label] = 0
                get_logger().log(f"🎯 대표님 목소리 매칭 완료! (유사도: {best_sim*100:.1f}%)")
            else:
                if best_label is not None:
                    get_logger().log(f"⚠️ 대표님 목소리 인식 실패 (최고 유사도 {best_sim*100:.1f}% < 기준 20%)")

        # 💡 [핵심 버그 수정] 실제로 0번(화자 1)이 매칭되었는지 확인하여 다음 번호를 결정합니다.
        # 만약 매칭에 실패했다면 0번이 비어있으므로, 첫 번째 화자에게 0번을 줍니다.
        next_id = 1 if 0 in mapping.values() else 0
        
        for l in labels:
            if l not in mapping:
                mapping[l] = next_id
                next_id += 1

        labels = [mapping[l] for l in labels]
        
        # 4. 동일한 화자 구간 병합
        speaker_map = []
        current_speaker = labels[0]
        current_start = timestamps[0][0]
        current_end = timestamps[0][1]
        
        for i in range(1, len(labels)):
            if labels[i] == current_speaker:
                current_end = timestamps[i][1]
            else:
                speaker_map.append({
                    "start": current_start, 
                    "end": current_end, 
                    "speaker": f"SPEAKER_{current_speaker:02d}"
                })
                current_speaker = labels[i]
                current_start = timestamps[i][0]
                current_end = timestamps[i][1]
                
        speaker_map.append({
            "start": current_start, 
            "end": current_end, 
            "speaker": f"SPEAKER_{current_speaker:02d}"
        })
        
    except Exception as e:
        get_logger().log(f"❌ 화자 분리 연산 중 에러 발생: {e}")
        return []
    finally:
        is_running = False
        try:
            if "classifier" in locals() and hasattr(classifier, "mods"):
                classifier.mods.to("cpu")
        except Exception:
            pass
        try:
            del classifier
        except Exception:
            pass
        try:
            del signal
        except Exception:
            pass
        try:
            del chunk
        except Exception:
            pass
        try:
            del emb
        except Exception:
            pass
        try:
            del r_sig
        except Exception:
            pass
        try:
            del ref_emb
        except Exception:
            pass
        try:
            del embeddings
        except Exception:
            pass
        try:
            del centroids
        except Exception:
            pass
        try:
            del kmeans
        except Exception:
            pass
        clear_audio_model_memory_caches(include_gpu=True)

    detected_unique = len({str(item.get("speaker") or "") for item in list(speaker_map or []) if isinstance(item, dict)})
    if not speaker_map:
        get_logger().log("⚠️ 2명 이상의 화자를 구분하지 못하여 단일 화자로 처리합니다.")
        dur = total_samples / 16000.0 if 'total_samples' in locals() else 0.0
        speaker_map.append({"start": 0.0, "end": dur, "speaker": "SPEAKER_00"})
        detected_unique = 1
    else:
        get_logger().log(
            f"✅ 화자 분리 완료! 화자 {max(1, detected_unique)}명 / "
            f"대화 교체 {len(speaker_map)}개 구간 감지"
        )
    _save_cached_speaker_map(
        cache_file,
        speaker_map,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        detected_speakers=max(1, detected_unique),
    )
        
    return speaker_map

def get_speaker_for_segment(start_t: float, end_t: float, speaker_map: list[dict]) -> str:
    if not speaker_map: return "SPEAKER_00"
    mid_time = (start_t + end_t) / 2.0
    
    overlap_durations = {}
    for spk_seg in speaker_map:
        overlap_start = max(start_t, spk_seg["start"])
        overlap_end = min(end_t, spk_seg["end"])
        if overlap_start < overlap_end:
            overlap = overlap_end - overlap_start
            overlap_durations[spk_seg["speaker"]] = overlap_durations.get(spk_seg["speaker"], 0) + overlap
            
    if overlap_durations:
        return max(overlap_durations.items(), key=lambda x: x[1])[0]
        
    closest_spk = "SPEAKER_00"
    min_dist = float('inf')
    for spk_seg in speaker_map:
        if spk_seg["start"] <= mid_time <= spk_seg["end"]: return spk_seg["speaker"]
        dist = min(abs(mid_time - spk_seg["start"]), abs(mid_time - spk_seg["end"]))
        if dist < min_dist:
            min_dist = dist; closest_spk = spk_seg["speaker"]
    return closest_spk


def assign_speaker_map_to_segment(segment: dict, speaker_map: list[dict]) -> dict:
    row = dict(segment or {})
    if not speaker_map:
        speaker = _normalize_speaker_id(row.get("speaker", row.get("spk", "00")))
        row["speaker"] = speaker
        row.setdefault("speaker_list", [speaker])
        return row

    start_t = float(row.get("start", 0.0) or 0.0)
    end_t = float(row.get("end", start_t) or start_t)
    dominant = _normalize_speaker_id(get_speaker_for_segment(start_t, end_t, speaker_map))
    row["speaker"] = dominant

    words = [dict(word) for word in list(row.get("words") or []) if isinstance(word, dict)]
    speakers_in_order: list[str] = []
    if words:
        updated_words = []
        for word in words:
            word_start = float(word.get("start", start_t) or start_t)
            word_end = float(word.get("end", word_start) or word_start)
            word_speaker = _normalize_speaker_id(get_speaker_for_segment(word_start, word_end, speaker_map))
            updated = dict(word)
            updated["speaker"] = word_speaker
            updated_words.append(updated)
            if word_speaker not in speakers_in_order:
                speakers_in_order.append(word_speaker)
        row["words"] = updated_words
    if not speakers_in_order:
        speakers_in_order = [dominant]
    row["speaker_list"] = speakers_in_order[:3]
    return row


def assign_speakers_to_segments(segments: list[dict], speaker_map: list[dict]) -> list[dict]:
    return [
        assign_speaker_map_to_segment(seg, speaker_map)
        for seg in list(segments or [])
        if isinstance(seg, dict)
    ]


def _speaker_line_items_for_segment(segment: dict, *, max_lines: int = 2) -> list[dict]:
    row = dict(segment or {})
    existing_lines = [line.strip() for line in str(row.get("text", "") or "").replace("\u2028", "\n").splitlines() if line.strip()]
    existing_speakers = [_normalize_speaker_id(item) for item in list(row.get("speaker_list", []) or []) if str(item or "").strip()]
    if len(existing_lines) > 1 and len(existing_speakers) >= len(existing_lines):
        return [
            {
                "speaker": existing_speakers[idx],
                "text": _clean_caption_line(line),
            }
            for idx, line in enumerate(existing_lines[:max_lines])
            if _clean_caption_line(line)
        ]
    words = [dict(word) for word in list(row.get("words") or []) if isinstance(word, dict)]
    runs: list[dict] = []
    for word in sorted(words, key=lambda item: (float(item.get("start", 0.0) or 0.0), float(item.get("end", 0.0) or 0.0))):
        text = _clean_caption_line(word.get("word", ""))
        if not text:
            continue
        speaker = _normalize_speaker_id(word.get("speaker", row.get("speaker", "00")))
        start = float(word.get("start", row.get("start", 0.0)) or row.get("start", 0.0) or 0.0)
        end = float(word.get("end", start) or start)
        if runs and runs[-1]["speaker"] == speaker and start - float(runs[-1]["end"]) <= 0.18:
            runs[-1]["text"] = f"{runs[-1]['text']} {text}".strip()
            runs[-1]["end"] = end
            continue
        runs.append(
            {
                "speaker": speaker,
                "text": text,
                "start": start,
                "end": end,
            }
        )
    if 1 < len(runs) <= max_lines:
        if all(float(runs[idx + 1]["start"]) - float(runs[idx]["end"]) <= 0.22 for idx in range(len(runs) - 1)):
            return runs
    fallback_speaker = _normalize_speaker_id(row.get("speaker", row.get("spk", "00")))
    fallback_text = _clean_caption_line(row.get("text", ""))
    return [{"speaker": fallback_speaker, "text": fallback_text}] if fallback_text else []


def merge_speaker_overlap_subtitles(
    segments: list[dict],
    *,
    max_lines: int = 2,
    join_gap_sec: float = 0.18,
    min_overlap_sec: float = 0.08,
) -> list[dict]:
    ordered = [
        dict(seg)
        for seg in sorted(
            [seg for seg in list(segments or []) if isinstance(seg, dict)],
            key=lambda item: (float(item.get("start", 0.0) or 0.0), float(item.get("end", item.get("start", 0.0)) or 0.0)),
        )
    ]
    if not ordered:
        return []

    merged: list[dict] = []
    for seg in ordered:
        line_items = _speaker_line_items_for_segment(seg, max_lines=max_lines)
        if not line_items:
            continue
        seg_start = float(seg.get("start", 0.0) or 0.0)
        seg_end = float(seg.get("end", seg_start) or seg_start)
        candidate = dict(seg)
        candidate["_speaker_lines"] = line_items[:max_lines]
        candidate["speaker"] = line_items[0]["speaker"]
        candidate["speaker_list"] = [str(item.get("speaker") or "") for item in line_items[:max_lines]]

        prev = merged[-1] if merged else None
        if prev is not None:
            prev_lines = list(prev.get("_speaker_lines") or [])
            overlap = max(0.0, min(seg_end, float(prev.get("end", seg_start) or seg_start)) - max(seg_start, float(prev.get("start", 0.0) or 0.0)))
            gap = seg_start - float(prev.get("end", seg_start) or seg_start)
            can_append = (
                len(prev_lines) == 1
                and len(line_items) == 1
                and len(prev_lines) + len(line_items) <= max_lines
                and str(prev_lines[-1].get("speaker") or "") != str(line_items[0].get("speaker") or "")
                and (overlap >= min_overlap_sec or gap <= join_gap_sec)
            )
            if can_append:
                prev_lines.append(dict(line_items[0]))
                prev["_speaker_lines"] = prev_lines
                prev["speaker_list"] = [str(item.get("speaker") or "") for item in prev_lines]
                prev["end"] = max(float(prev.get("end", seg_start) or seg_start), seg_end)
                if seg_start < float(prev.get("start", seg_start) or seg_start):
                    prev["start"] = seg_start
                if seg.get("words"):
                    prev_words = [dict(word) for word in list(prev.get("words") or []) if isinstance(word, dict)]
                    prev_words.extend([dict(word) for word in list(seg.get("words") or []) if isinstance(word, dict)])
                    prev["words"] = sorted(
                        prev_words,
                        key=lambda item: (float(item.get("start", 0.0) or 0.0), float(item.get("end", 0.0) or 0.0)),
                    )
                if seg.get("stt_candidates"):
                    prev_candidates = [dict(item) for item in list(prev.get("stt_candidates") or []) if isinstance(item, dict)]
                    prev_candidates.extend([dict(item) for item in list(seg.get("stt_candidates") or []) if isinstance(item, dict)])
                    prev["stt_candidates"] = prev_candidates
                prev["multispeaker_overlap"] = True
                continue
        merged.append(candidate)

    out: list[dict] = []
    for seg in merged:
        row = dict(seg)
        speaker_lines = [dict(item) for item in list(row.pop("_speaker_lines", []) or []) if isinstance(item, dict)]
        if not speaker_lines:
            continue
        texts = [str(item.get("text") or "").strip() for item in speaker_lines if str(item.get("text") or "").strip()]
        speakers = [_normalize_speaker_id(item.get("speaker")) for item in speaker_lines if str(item.get("speaker") or "").strip()]
        if not texts:
            continue
        row["speaker"] = speakers[0] if speakers else _normalize_speaker_id(row.get("speaker", "00"))
        row["speaker_list"] = speakers[:max_lines] if speakers else [row["speaker"]]
        if len(texts) > 1:
            row["text"] = "\n".join(f"- {text}" for text in texts[:max_lines])
            row["multispeaker_overlap"] = True
        else:
            row["text"] = texts[0]
        out.append(row)
    return out
