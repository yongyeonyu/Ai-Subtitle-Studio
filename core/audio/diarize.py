# Version: 03.01.05
# Phase: PHASE1-B
"""
diarize.py - AI 화자 분리 (SpeechBrain 엔진 적용 완료)
[추가] 첫 음성 화자 1번 강제 할당 (시간순 정렬)
[추가] 대표님 목소리 지문(Embedding) 학습 및 화자 1번 강제 매칭 알고리즘 
"""
import os
import platform
import time
import json
import threading
import importlib.util
import numpy as np
from core.audio.runtime_cleanup import clear_audio_model_memory_caches
from core.audio.torch_acceleration import move_torch_model_to_preferred_device
from core.runtime.logger import get_logger
from core.speaker_profile_settings import trained_speaker_profiles


_DIARIZE_DEPENDENCIES = (
    ("torch", "torch"),
    ("torchaudio", "torchaudio"),
    ("speechbrain", "speechbrain"),
    ("sklearn", "scikit-learn"),
)
_missing_dependency_notice_logged = False
_DIARIZE_CACHE_SCHEMA = "ai_subtitle_studio.speaker_cache.v2"
_REFERENCE_MATCH_MIN_SIM = 0.20
_AUTO_CLUSTER_MIN_SILHOUETTE = 0.18


def _diarization_runtime_settings(settings: dict | None = None) -> dict:
    runtime = dict(settings or {})
    gpu_opt_in = str(os.environ.get("AI_SUBTITLE_STUDIO_ENABLE_GPU_SPEAKER_DIARIZATION", "") or "").strip().lower()
    if platform.system() == "Darwin" and gpu_opt_in not in {"1", "true", "yes", "on"}:
        # SpeechBrain diarization uses torch conv/relu kernels that have been
        # unstable on macOS MPS during active subtitle generation.
        runtime["audio_torch_gpu_enabled"] = False
    return runtime


def _apply_diarization_device(classifier, torch_module, settings: dict | None = None) -> None:
    runtime_settings = _diarization_runtime_settings(settings)
    device_name = move_torch_model_to_preferred_device(
        classifier.mods,
        settings=runtime_settings,
        task="speaker_diarization",
        log_label="화자 분리",
    )
    classifier.device = torch_module.device(device_name if device_name != "cpu" else "cpu")
    if device_name == "cpu":
        get_logger().log("  └ 💻 CPU 연산 모드")


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
        "⚠️ [화자 분리] 자동 화자 분리에 필요한 패키지가 없습니다. "
        f"누락: {packages}. 이번 작업은 단일 화자로 계속 진행합니다. "
        f"화자 분리가 필요하면 venv/bin/python -m pip install {packages}"
    )


def _normalize_embedding(vector) -> np.ndarray:
    arr = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm <= 1e-9:
        return arr
    return arr / norm


def _speaker_similarity(left, right) -> float:
    left_arr = _normalize_embedding(left)
    right_arr = _normalize_embedding(right)
    denom = float(np.linalg.norm(left_arr) * np.linalg.norm(right_arr))
    if denom <= 1e-9:
        return 0.0
    return float(np.dot(left_arr, right_arr) / denom)


def _speaker_cache_key(settings: dict | None, max_speakers: int, reference_profiles: list[dict]) -> dict:
    refs = []
    for row in list(reference_profiles or []):
        path = str(row.get("primary_voice_path", "") or "")
        try:
            stat = os.stat(path) if path and os.path.exists(path) else None
        except Exception:
            stat = None
        refs.append(
            {
                "id": str(row.get("id", "") or ""),
                "name": str(row.get("name", "") or ""),
                "path": os.path.basename(path) if path else "",
                "mtime_ns": int(getattr(stat, "st_mtime_ns", 0) or 0),
                "size": int(getattr(stat, "st_size", 0) or 0),
            }
        )
    return {
        "schema": _DIARIZE_CACHE_SCHEMA,
        "max_speakers": int(max_speakers or 1),
        "references": refs,
    }


def _cache_matches(payload, cache_key: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("schema") != _DIARIZE_CACHE_SCHEMA:
        return False
    return dict(payload.get("cache_key") or {}) == dict(cache_key or {})


def _choose_cluster_count(embeddings: np.ndarray, max_speakers: int) -> tuple[int, list[int], dict]:
    sample_count = int(len(embeddings) or 0)
    if sample_count <= 0:
        return 1, [], {"reason": "no_embeddings"}
    max_clusters = max(1, min(int(max_speakers or 1), 3, sample_count))
    if max_clusters <= 1 or sample_count < 4:
        return 1, [0] * sample_count, {"reason": "single_cluster_default", "sample_count": sample_count}

    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    best: dict | None = None
    for cluster_count in range(2, max_clusters + 1):
        if sample_count <= cluster_count:
            break
        model = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
        labels = model.fit_predict(embeddings)
        if len(set(labels)) < 2:
            continue
        try:
            score = float(silhouette_score(embeddings, labels))
        except Exception:
            score = -1.0
        if best is None or score > float(best.get("score", -1.0)):
            best = {
                "cluster_count": cluster_count,
                "labels": list(labels),
                "score": score,
            }
    if not best or float(best.get("score", -1.0)) < _AUTO_CLUSTER_MIN_SILHOUETTE:
        return 1, [0] * sample_count, {
            "reason": "silhouette_low",
            "sample_count": sample_count,
            "score": float((best or {}).get("score", -1.0) or -1.0),
        }
    return int(best["cluster_count"]), list(best["labels"]), {
        "reason": "silhouette_best",
        "sample_count": sample_count,
        "score": round(float(best["score"]), 4),
    }


def _smooth_cluster_labels(labels: list[int]) -> list[int]:
    if len(labels) <= 2:
        return list(labels)
    smoothed = list(labels)
    for idx in range(1, len(labels) - 1):
        if labels[idx - 1] == labels[idx + 1]:
            smoothed[idx] = labels[idx - 1]
    return smoothed


def _cluster_centroids(embeddings: np.ndarray, labels: list[int]) -> dict[int, np.ndarray]:
    centroids: dict[int, list[np.ndarray]] = {}
    for idx, label in enumerate(list(labels or [])):
        centroids.setdefault(int(label), []).append(np.asarray(embeddings[idx], dtype=np.float32))
    return {
        label: _normalize_embedding(np.mean(np.stack(items), axis=0))
        for label, items in centroids.items()
        if items
    }


def _profile_numeric_id(profile: dict) -> int:
    raw_id = str(profile.get("id", "") or "").strip()
    if raw_id.isdigit():
        return max(0, min(98, int(raw_id)))
    return max(0, int(profile.get("index", 1) or 1) - 1)


def _match_reference_profiles(
    centroids: dict[int, np.ndarray],
    reference_profiles: list[dict],
    *,
    similarity_threshold: float = _REFERENCE_MATCH_MIN_SIM,
) -> tuple[dict[int, int], list[dict]]:
    candidates: list[tuple[float, int, dict]] = []
    for profile in list(reference_profiles or []):
        embedding = profile.get("embedding")
        if embedding is None:
            continue
        for label, centroid in centroids.items():
            score = _speaker_similarity(embedding, centroid)
            candidates.append((score, int(label), dict(profile)))
    mapping: dict[int, int] = {}
    details: list[dict] = []
    used_labels: set[int] = set()
    used_ids: set[int] = set()
    for score, label, profile in sorted(candidates, key=lambda item: item[0], reverse=True):
        numeric_id = _profile_numeric_id(profile)
        if score < float(similarity_threshold):
            continue
        if label in used_labels or numeric_id in used_ids:
            continue
        mapping[int(label)] = numeric_id
        used_labels.add(int(label))
        used_ids.add(numeric_id)
        details.append(
            {
                "label": int(label),
                "id": f"{numeric_id:02d}",
                "name": str(profile.get("name", "") or ""),
                "score": round(float(score), 4),
            }
        )
    return mapping, details


def _assign_remaining_cluster_ids(labels: list[int], mapping: dict[int, int], *, limit: int = 3) -> dict[int, int]:
    assigned = dict(mapping or {})
    used_ids = {int(value) for value in assigned.values()}
    remaining_ids = [idx for idx in range(max(1, int(limit or 3))) if idx not in used_ids]
    ordered_labels: list[int] = []
    for label in list(labels or []):
        value = int(label)
        if value not in ordered_labels:
            ordered_labels.append(value)
    next_id = max(remaining_ids[-1] + 1, len(used_ids)) if remaining_ids else len(used_ids)
    for label in ordered_labels:
        if label in assigned:
            continue
        if remaining_ids:
            assigned[label] = remaining_ids.pop(0)
        else:
            assigned[label] = next_id
            next_id += 1
    return assigned


def _load_reference_profile_embeddings(classifier, torch, torchaudio, settings: dict | None) -> list[dict]:
    references: list[dict] = []
    for profile in trained_speaker_profiles(settings):
        path = str(profile.get("primary_voice_path", "") or "")
        if not path or not os.path.exists(path):
            continue
        try:
            get_logger().log(f"🔊 화자 학습 데이터 사용: {path}")
            signal, sample_rate = torchaudio.load(path)
            if signal.shape[0] > 1:
                signal = signal.mean(dim=0, keepdim=True)
            if sample_rate != 16000:
                signal = torchaudio.functional.resample(signal, sample_rate, 16000)
            max_samples = 16000 * 15
            if signal.shape[1] > max_samples:
                signal = signal[:, :max_samples]
            signal = torch.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0).to(classifier.device)
            with torch.no_grad():
                embedding = classifier.encode_batch(signal).squeeze().cpu().numpy()
            references.append(
                {
                    **profile,
                    "embedding": _normalize_embedding(embedding),
                }
            )
        except Exception as exc:
            get_logger().log(f"⚠️ {profile.get('name', '화자')} 학습 데이터 분석 실패: {exc}")
    return references

def get_speaker_map(file_path: str, min_speakers: int = 1, max_speakers: int = 2) -> list[dict]:
    cache_file = f"{os.path.splitext(file_path)[0]}_speaker_cache.json"
    try:
        from core.settings import load_settings

        settings = load_settings()
    except Exception:
        settings = {}
    reference_profiles = trained_speaker_profiles(settings)
    cache_key = _speaker_cache_key(settings, max_speakers, reference_profiles)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_payload = json.load(f)
            if _cache_matches(cached_payload, cache_key):
                speaker_map = list(cached_payload.get("speaker_map") or [])
                if speaker_map:
                    get_logger().log("⚡ [캐시 적중] 자동 화자 분리 캐시를 재사용합니다!")
                    return speaker_map
            elif isinstance(cached_payload, list):
                get_logger().log("♻️ [화자 분리] 레거시 캐시를 자동 화자 프로필 기준으로 다시 계산합니다.")
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            get_logger().log(f"⚠️ [화자 분리] 캐시 로드 실패: {exc}")

    missing = missing_diarization_packages()
    if missing:
        log_missing_diarization_dependencies(missing)
        return []

    try:
        import torch
        import torchaudio
        from speechbrain.inference.classifiers import EncoderClassifier
    except ImportError as exc:
        log_missing_diarization_dependencies(missing_diarization_packages() or [str(exc)])
        return []

    get_logger().log("⏳ SpeechBrain 화자 분석 AI 로딩 중... (HuggingFace 토큰 불필요! 🚀)")
    
    try:
        classifier = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb", 
            savedir=os.path.join(os.path.expanduser("~"), ".cache", "speechbrain")
        )
        _apply_diarization_device(classifier, torch, settings)
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
            
        embeddings = np.array([_normalize_embedding(item) for item in embeddings], dtype=np.float32)
        cluster_count, labels, cluster_meta = _choose_cluster_count(embeddings, max_speakers)
        labels = _smooth_cluster_labels(labels)
        centroids = _cluster_centroids(embeddings, labels)

        reference_embeddings = _load_reference_profile_embeddings(classifier, torch, torchaudio, settings)
        mapping, matched_profiles = _match_reference_profiles(centroids, reference_embeddings)
        mapping = _assign_remaining_cluster_ids(labels, mapping, limit=max(3, int(max_speakers or 1)))
        labels = [mapping[int(label)] for label in labels]

        if matched_profiles:
            for match in matched_profiles:
                get_logger().log(
                    "🎯 화자 학습 프로필 매칭 완료: "
                    f"{match.get('name') or match.get('id')} -> SPEAKER_{match.get('id')} "
                    f"(유사도 {float(match.get('score', 0.0) or 0.0) * 100:.1f}%)"
                )
        get_logger().log(
            "🧠 자동 화자 군집 결정: "
            f"{cluster_count}명 ({cluster_meta.get('reason')}, score={cluster_meta.get('score', 'n/a')})"
        )
        
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
            del embeddings
        except Exception:
            pass
        try:
            del centroids
        except Exception:
            pass
        clear_audio_model_memory_caches(include_gpu=True)
        
    if not speaker_map:
        get_logger().log("⚠️ 2명 이상의 화자를 구분하지 못하여 단일 화자로 처리합니다.")
        dur = total_samples / 16000.0 if 'total_samples' in locals() else 0.0
        speaker_map.append({"start": 0.0, "end": dur, "speaker": "SPEAKER_00"})
    else:
        get_logger().log(f"✅ 화자 분리 완료! 총 {len(speaker_map)}번의 대화 교체가 감지되었습니다.")
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "schema": _DIARIZE_CACHE_SCHEMA,
                        "cache_key": cache_key,
                        "speaker_map": speaker_map,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except (OSError, TypeError, ValueError) as exc:
            get_logger().log(f"⚠️ [화자 분리] 캐시 저장 실패: {exc}")
        
    return speaker_map

def get_speaker_for_segment(start_t: float, end_t: float, speaker_map: list[dict]) -> str:
    from core.engine.subtitle_speaker_diarization import speaker_for_segment

    return speaker_for_segment(start_t, end_t, speaker_map)
