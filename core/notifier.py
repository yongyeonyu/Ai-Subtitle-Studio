# Version: 02.02.00
# Phase: PHASE1-B
"""
core/notifier.py
ntfy 푸시 알림 전송 유틸
- backend.py / editor_pipeline.py에서 분리
"""

import config
from logger import get_logger


def send_ntfy(title: str, message: str, tags: str = ""):
    """ntfy.sh로 푸시 알림 전송 (백그라운드 안전)"""
    try:
        import urllib.request
        import base64

        topic = getattr(config, "NTFY_TOPIC", "")
        if not topic:
            return

        url = f"https://ntfy.sh/{topic}"
        encoded_title = (
            f"=?UTF-8?B?"
            f"{base64.b64encode(title.encode('utf-8')).decode('utf-8')}"
            f"?="
        )

        req = urllib.request.Request(
            url,
            data=message.encode("utf-8"),
            method="POST"
        )
        req.add_header("Title", encoded_title)
        if tags:
            req.add_header("Tags", tags)

        urllib.request.urlopen(req, timeout=3)
    except Exception as e:
        get_logger().log(f"⚠️ 알림 전송 실패: {e}")