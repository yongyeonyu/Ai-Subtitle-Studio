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
from core.runtime.logger import get_logger


_DIARIZE_DEPENDENCIES = (
    ("torch", "torch"),
    ("torchaudio", "torchaudio"),
    ("speechbrain", "speechbrain"),
    ("sklearn", "scikit-learn"),
)
_missing_dependency_notice_logged = False


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

def get_speaker_map(file_path: str, min_speakers: int = 1, max_speakers: int = 2) -> list[dict]:
    cache_file = f"{os.path.splitext(file_path)[0]}_speaker_cache.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                speaker_map = json.load(f)
            if speaker_map:
                get_logger().log("⚡ [캐시 적중] 이전에 분석한 화자 분리 데이터를 불러왔습니다!")
                return speaker_map
        except Exception: pass

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
        
        if torch.backends.mps.is_available():
            classifier.device = torch.device("mps")
            classifier.mods.to("mps")
            get_logger().log("  └ 🚀 Mac 애플 실리콘(MPS) GPU 가속 활성화!")
        elif torch.cuda.is_available():
            classifier.device = torch.device("cuda")
            classifier.mods.to("cuda")
            get_logger().log("  └ 🚀 CUDA 가속 활성화!")
        else:
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
        
        kmeans = KMeans(n_clusters=max_speakers, random_state=42, n_init=10)
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
        
    if not speaker_map:
        get_logger().log("⚠️ 2명 이상의 화자를 구분하지 못하여 단일 화자로 처리합니다.")
        dur = total_samples / 16000.0 if 'total_samples' in locals() else 0.0
        speaker_map.append({"start": 0.0, "end": dur, "speaker": "SPEAKER_00"})
    else:
        get_logger().log(f"✅ 화자 분리 완료! 총 {len(speaker_map)}번의 대화 교체가 감지되었습니다.")
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(speaker_map, f, ensure_ascii=False, indent=2)
        except Exception: pass
        
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
