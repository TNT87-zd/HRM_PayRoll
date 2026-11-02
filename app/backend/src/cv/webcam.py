"""OpenCV webcam demo; imported only when explicitly requested."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, Optional, Union

import cv2
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def run_webcam(
    engine,
    gallery: Dict[str, np.ndarray],
    camera_id: int = 0,
    threshold: float = 0.55,
    min_margin: float = 0.08,
    mirror: bool = True,
    save_dir: Optional[Union[str, Path]] = None,
) -> None:  # pragma: no cover
    """
    Bật Webcam nhận diện khuôn mặt thời gian thực (Kiosk Realtime Mode).
    Phím tắt trên cửa sổ camera:
      - `q` hoặc `ESC`: Thoát camera.
      - `c`: Chụp và lưu khung hình hiện tại (phục vụ thu thập thêm ảnh mẫu).
    """
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        raise RuntimeError(
            f"Không thể mở camera (camera_id={camera_id}). "
            "Trên macOS, hãy kiểm tra quyền Camera cho Terminal / VS Code trong System Settings > Privacy & Security > Camera."
        )

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    window_name = "HRM_PayRoll - Kiosk Face Recognition (Press 'q' to exit, 'c' to capture)"
    print(f"\n[WEBCAM] Đang mở camera {camera_id}... Nhấn 'q' hoặc ESC trên cửa sổ video để thoát.")

    save_root = Path(save_dir) if save_dir else (_PROJECT_ROOT / "data" / "face" / "captures")
    fps_ema = 0.0

    try:
        while True:
            t_start = time.perf_counter()
            ok, frame = cap.read()
            if not ok or frame is None:
                print("[WEBCAM] Không đọc được khung hình từ camera.")
                break

            if mirror:
                frame = cv2.flip(frame, 1)

            display = frame.copy()
            face, report = engine.extract_single_face(
                frame,
                require_single_face=True,
                check_quality=True,
                allow_pose_variation=False,
            )

            infer_ms = (time.perf_counter() - t_start) * 1000.0
            inst_fps = 1000.0 / max(infer_ms, 1e-3)
            fps_ema = inst_fps if fps_ema == 0.0 else (0.85 * fps_ema + 0.15 * inst_fps)

            status_text = "NO FACE DETECTED"
            status_color = (180, 180, 180)

            if face is not None:
                x1, y1, x2, y2 = [int(v) for v in face.bbox]

                if report.is_valid and face.embedding is not None:
                    match_res = engine.match(
                        face.embedding,
                        gallery,
                        threshold=threshold,
                        min_margin=min_margin,
                    )
                    if match_res.matched and match_res.employee_id is not None:
                        box_color = (0, 210, 0)  # Xanh lá: Nhận diện thành công
                        label = f"{match_res.employee_id} | sim={match_res.similarity:.2f}"
                        status_text = f"CHECK-IN OK: {match_res.employee_id} ({match_res.similarity:.3f})"
                        status_color = (0, 230, 0)
                    else:
                        box_color = (0, 0, 235)  # Đỏ: Người lạ / dưới ngưỡng
                        label = f"UNKNOWN | sim={match_res.similarity:.2f}"
                        status_text = f"REJECTED ({match_res.reason}: {match_res.similarity:.3f})"
                        status_color = (0, 0, 255)
                else:
                    box_color = (0, 165, 255)  # Cam: Chất lượng khung hình chưa đạt
                    reasons_str = ", ".join(report.reasons)
                    label = f"QUALITY: {reasons_str}"
                    status_text = f"WARNING: {reasons_str}"
                    status_color = (0, 180, 255)

                # Vẽ khung mặt & 5 điểm mốc
                cv2.rectangle(display, (x1, y1), (x2, y2), box_color, 2)
                for pt in face.kps.astype(int):
                    cv2.circle(display, (int(pt[0]), int(pt[1])), 3, (255, 255, 0), -1)

                cv2.putText(
                    display,
                    label,
                    (x1, max(30, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    box_color,
                    2,
                    cv2.LINE_AA,
                )

            # Thanh thông tin Kiosk ở góc trên
            cv2.rectangle(display, (0, 0), (display.shape[1], 75), (25, 25, 25), -1)
            cv2.putText(
                display,
                f"Latency: {infer_ms:.1f} ms | FPS: {fps_ema:.1f} | Gallery: {len(gallery)} emp",
                (15, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.68,
                (240, 240, 240),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                display,
                status_text,
                (15, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.78,
                status_color,
                2,
                cv2.LINE_AA,
            )

            cv2.imshow(window_name, display)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):  # 'q' hoặc ESC
                break
            if key == ord("c"):
                save_root.mkdir(parents=True, exist_ok=True)
                ts_name = f"capture_{int(time.time() * 1000)}.jpg"
                out_file = save_root / ts_name
                cv2.imwrite(str(out_file), frame)
                print(f"[WEBCAM] Đã lưu ảnh chụp tại: {out_file}")
    finally:
        cap.release()
        cv2.destroyAllWindows()
