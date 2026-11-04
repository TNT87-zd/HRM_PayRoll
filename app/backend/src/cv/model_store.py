"""Local model discovery and TLS-verified model downloads."""

from __future__ import annotations

import importlib
import logging
import ssl
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)


class ModelStore:
    """Resolve local model pairs and provision missing model packs."""

    def __init__(
        self,
        model_pack: str,
        model_root: Union[str, Path],
        providers: Sequence[str],
        det_size: Tuple[int, int],
        det_thresh: float,
    ) -> None:
        self.model_pack = model_pack
        self.model_root = Path(model_root)
        self.providers = providers
        self.det_size = det_size
        self.det_thresh = det_thresh

    # Cặp tên file model chuẩn trong các gói của InsightFace
    KNOWN_PACK_FILES: Dict[str, Tuple[str, str]] = {
        "buffalo_l": ("det_10g.onnx", "w600k_r50.onnx"),
        "buffalo_s": ("det_500m.onnx", "w600k_mbf.onnx"),
        "buffalo_sc": ("det_500m.onnx", "w600k_mbf.onnx"),
    }

    def resolve_paths(
        self,
        det_model_path: Optional[Union[str, Path]],
        rec_model_path: Optional[Union[str, Path]],
        auto_download: bool,
    ) -> Tuple[Path, Path]:
        """Tìm đường dẫn file `.onnx` của SCRFD và ArcFace hoặc tải tự động nếu được phép."""
        if det_model_path and rec_model_path:
            det_p = Path(det_model_path).expanduser().resolve()
            rec_p = Path(rec_model_path).expanduser().resolve()
            if not det_p.is_file():
                raise FileNotFoundError(f"Không tìm thấy model SCRFD tại: {det_p}")
            if not rec_p.is_file():
                raise FileNotFoundError(f"Không tìm thấy model ArcFace tại: {rec_p}")
            return det_p, rec_p

        pack_dir = self.model_root / "models" / self.model_pack
        det_p, rec_p = self._find_models_in_dir(pack_dir)

        if (det_p is None or rec_p is None) and auto_download:
            self._download_pack_via_insightface()
            det_p, rec_p = self._find_models_in_dir(pack_dir)

        if det_p is None or rec_p is None:
            expected_det, expected_rec = self.KNOWN_PACK_FILES.get(
                self.model_pack, ("det_*.onnx", "w600k_*.onnx")
            )
            raise FileNotFoundError(
                f"Không tìm thấy bộ model ONNX '{self.model_pack}' trong '{pack_dir}'.\n"
                f"Cần có file SCRFD ({expected_det}) và ArcFace ({expected_rec}), "
                f"hoặc cài đặt gói `insightface` để tự động tải về."
            )

        return det_p, rec_p


    def _find_models_in_dir(
        self, directory: Path
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """Tìm cặp model SCRFD (`det_*.onnx`) và ArcFace (`w600k_*.onnx` / `glintr*.onnx`) trong thư mục."""
        if not directory.is_dir():
            return None, None

        if self.model_pack in self.KNOWN_PACK_FILES:
            det_name, rec_name = self.KNOWN_PACK_FILES[self.model_pack]
            det_candidate = directory / det_name
            rec_candidate = directory / rec_name
            if det_candidate.is_file() and rec_candidate.is_file():
                return det_candidate, rec_candidate

        det_matches = sorted(directory.glob("det_*.onnx")) or sorted(
            directory.glob("scrfd_*.onnx")
        )
        rec_matches = (
            sorted(directory.glob("w600k_*.onnx"))
            or sorted(directory.glob("glintr*.onnx"))
            or sorted(directory.glob("*arcface*.onnx"))
        )

        det_p = det_matches[0] if det_matches else None
        rec_p = rec_matches[0] if rec_matches else None
        return det_p, rec_p


    def _download_pack_via_insightface(self) -> None:
        """
        Tải gói model chuẩn của InsightFace.
        Ưu tiên dùng `insightface.app.FaceAnalysis` nếu có; nếu không cài `insightface`
        (ví dụ trên Python 3.13), tự động tải trực tiếp gói `.zip` từ GitHub Releases
        của InsightFace và giải nén vào `<model_root>/models/<model_pack>/`.
        """
        try:
            insightface_app = importlib.import_module("insightface.app")
            face_analysis_cls = getattr(insightface_app, "FaceAnalysis")

            logger.info("Đang tải gói model '%s' qua insightface...", self.model_pack)
            app = face_analysis_cls(
                name=self.model_pack,
                root=str(self.model_root),
                allowed_modules=["detection", "recognition"],
                providers=self.providers,
            )
            app.prepare(ctx_id=0, det_size=self.det_size, det_thresh=self.det_thresh)
            return
        except (ImportError, AttributeError):
            pass

        url = (
            f"https://github.com/deepinsight/insightface/releases/download/v0.7/"
            f"{self.model_pack}.zip"
        )
        models_dir = self.model_root / "models"
        pack_dir = models_dir / self.model_pack
        zip_path = models_dir / f"{self.model_pack}.zip"
        part_path = models_dir / f"{self.model_pack}.zip.part"
        pack_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Đang tải gói model ONNX '%s' từ %s ...", self.model_pack, url)
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (HRM_PayRoll FaceEngine)"},
            )
            # Xử lý chứng chỉ SSL trên macOS (Python.org installer thiếu cert.pem mặc định)
            cafile: Optional[str] = None
            try:
                certifi_mod = importlib.import_module("certifi")
                cafile = str(certifi_mod.where())
            except ImportError:
                if Path("/etc/ssl/cert.pem").is_file():
                    cafile = "/etc/ssl/cert.pem"

            try:
                ssl_ctx = (
                    ssl.create_default_context(cafile=cafile)
                    if cafile
                    else ssl.create_default_context()
                )
                response = urllib.request.urlopen(req, timeout=120, context=ssl_ctx)
            except urllib.error.URLError as url_err:
                if isinstance(url_err.reason, ssl.SSLError):
                    raise RuntimeError(
                        "Không thể xác minh chứng chỉ TLS khi tải model. "
                        "Hãy cấu hình CA tin cậy hoặc cài certifi."
                    ) from url_err
                else:
                    raise

            with response, open(part_path, "wb") as out_file:
                total_header = response.headers.get("Content-Length")
                total_bytes = int(total_header) if total_header and total_header.isdigit() else 0
                downloaded = 0
                next_log_pct = 10
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if total_bytes > 0:
                        pct = int(downloaded * 100 / total_bytes)
                        if pct >= next_log_pct:
                            logger.info(
                                "  Đang tải %s: %d%% (%.1f / %.1f MB)",
                                self.model_pack,
                                pct,
                                downloaded / (1024 * 1024),
                                total_bytes / (1024 * 1024),
                            )
                            next_log_pct = ((pct // 10) + 1) * 10
            part_path.replace(zip_path)

            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    filename = Path(member.filename).name
                    if not filename:
                        continue
                    target_file = pack_dir / filename
                    with zf.open(member) as src, open(target_file, "wb") as dst:
                        dst.write(src.read())
        except Exception as exc:
            raise RuntimeError(
                f"Không thể tự động tải gói model '{self.model_pack}' từ {url}: {exc}"
            ) from exc
        finally:
            for tmp_file in (part_path, zip_path):
                if tmp_file.exists():
                    try:
                        tmp_file.unlink()
                    except OSError:
                        pass
