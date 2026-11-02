"""Enrollment orchestration and construction of employee galleries."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from .matching import l2_normalize, validate_embeddings
from .types import EnrollmentResult


def enroll_from_images(
    engine,
    images_or_dir: Union[str, Path, Sequence[Union[str, Path, np.ndarray]]],
    employee_id: Optional[str] = None,
    min_valid_images: int = 3,
    min_intra_similarity: float = 0.35,
    check_quality: bool = True,
) -> EnrollmentResult:
    """
    Đăng ký khuôn mặt nhân viên từ thư mục ảnh (ví dụ `data/face/raw/NV0001`)
    hoặc danh sách 3-5 ảnh chụp ở các góc (thẳng, trái, phải, trên, dưới).

    Quy trình (Mục 4.1 - PLAN.MD):
    1. Kiểm tra chất lượng từng ảnh (loại ảnh mờ, tối, nhiều mặt, không thấy mặt).
    2. Căn chỉnh theo 5 điểm mốc và trích xuất vector 512 chiều cho từng ảnh hợp lệ.
    3. Kiểm tra độ đồng nhất giữa các ảnh đăng ký (tránh trộn ảnh của 2 người khác nhau).
    4. Tính vector đại diện (centroid) đã chuẩn hóa L2.
    """
    if min_valid_images < 2:
        raise ValueError("Cần ít nhất 2 ảnh để kiểm tra tính đồng nhất")
    if not np.isfinite(min_intra_similarity) or not -1 <= min_intra_similarity <= 1:
        raise ValueError("min_intra_similarity phải thuộc [-1, 1]")
    if isinstance(images_or_dir, (str, Path)):
        dir_path = Path(images_or_dir)
        if dir_path.is_dir():
            if employee_id is None:
                employee_id = dir_path.name
            valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
            items: List[Union[str, Path, np.ndarray]] = [
                p
                for p in sorted(dir_path.iterdir())
                if p.is_file() and p.suffix.lower() in valid_exts
            ]
        else:
            items = [dir_path]
    else:
        items = list(images_or_dir)

    embeddings: List[np.ndarray] = []
    valid_files: List[str] = []
    rejected_files: Dict[str, List[str]] = {}

    for idx, item in enumerate(items):
        label = str(item) if isinstance(item, (str, Path)) else f"frame_{idx}"
        try:
            face, report = engine.extract_single_face(
                image_or_path=item,
                require_single_face=True,
                check_quality=check_quality,
                allow_pose_variation=True,  # Cho phép góc nghiêng nhẹ khi enrollment
            )
        except Exception as exc:
            rejected_files[label] = [f"read_error:{exc}"]
            continue

        if face is None or face.embedding is None or (check_quality and not report.is_valid):
            rejected_files[label] = report.reasons or ["invalid_face"]
            continue

        try:
            embedding = l2_normalize(validate_embeddings(face.embedding))
        except ValueError as exc:
            rejected_files[label] = [f"invalid_embedding:{exc}"]
            continue
        embeddings.append(embedding)
        valid_files.append(label)

    if len(embeddings) < min_valid_images:
        return EnrollmentResult(
            success=False,
            employee_id=employee_id,
            centroid_embedding=None,
            embeddings=embeddings,
            valid_files=valid_files,
            rejected_files=rejected_files,
            mean_intra_similarity=0.0,
            message=(
                f"Số lượng ảnh hợp lệ ({len(embeddings)}) ít hơn mức tối thiểu ({min_valid_images})."
            ),
        )

    emb_matrix = np.vstack(embeddings).astype(np.float32)  # (K, 512)
    centroid = l2_normalize(emb_matrix.mean(axis=0))

    # Tính độ tương đồng trung bình giữa từng ảnh góc với vector trung tâm
    sims_to_centroid = np.asarray(emb_matrix @ centroid, dtype=np.float32)
    mean_sim = float(sims_to_centroid.mean())
    # Compare each sample with a centroid that excludes itself, so unrelated
    # samples cannot validate their own contribution. Require a connected group
    # of cross-sample matches while allowing wider differences between poses.
    other_centroids = l2_normalize(emb_matrix.sum(axis=0) - emb_matrix, axis=1)
    cross_scores = np.sum(emb_matrix * other_centroids, axis=1)
    min_sim = float(cross_scores.min())
    links = (emb_matrix @ emb_matrix.T) >= min_intra_similarity
    visited = {0}
    pending = [0]
    while pending:
        current = pending.pop()
        neighbors = set(np.flatnonzero(links[current])) - visited
        visited.update(neighbors)
        pending.extend(neighbors)
    consistent = len(visited) == len(embeddings)

    if not consistent or min_sim < min_intra_similarity:
        return EnrollmentResult(
            success=False,
            employee_id=employee_id,
            centroid_embedding=None,
            embeddings=embeddings,
            valid_files=valid_files,
            rejected_files=rejected_files,
            mean_intra_similarity=mean_sim,
            message=(
                f"Các ảnh đăng ký không đồng nhất (min cross-sample similarity = {min_sim:.3f} < {min_intra_similarity:.3f})."
            ),
        )

    return EnrollmentResult(
        success=True,
        employee_id=employee_id,
        centroid_embedding=centroid,
        embeddings=embeddings,
        valid_files=valid_files,
        rejected_files=rejected_files,
        mean_intra_similarity=mean_sim,
        message=f"Đăng ký thành công {len(embeddings)}/{len(items)} ảnh.",
    )


def enroll_gallery_from_root(
    engine,
    raw_root_or_emp_dir: Union[str, Path],
    min_valid_images: int = 3,
) -> Tuple[Dict[str, np.ndarray], List[EnrollmentResult]]:
    """
    Tự động nạp danh sách nhân viên từ một thư mục gốc (ví dụ `data/face/raw/` chứa `NV0001`, `NV0002`...)
    hoặc từ thư mục của 1 nhân viên (`data/face/raw/NV0001`).

    Lưu cả vector trung tâm (`centroid_embedding`) lẫn các vector từng góc chụp hợp lệ thành ma trận
    `(K + 1, 512)` cho mỗi nhân viên để tăng độ chính xác khi nhận diện nghiêng đầu trên camera.
    """
    root_path = Path(raw_root_or_emp_dir)
    if not root_path.exists():
        return {}, []

    subdirs = sorted([d for d in root_path.iterdir() if d.is_dir()])
    target_dirs = subdirs if subdirs else [root_path]

    gallery: Dict[str, np.ndarray] = {}
    results: List[EnrollmentResult] = []
    for emp_dir in target_dirs:
        res = engine.enroll_from_images(
            emp_dir,
            employee_id=emp_dir.name,
            min_valid_images=min_valid_images,
        )
        results.append(res)
        if res.success and res.centroid_embedding is not None:
            all_vecs = np.vstack([res.centroid_embedding] + res.embeddings).astype(
                np.float32
            )
            gallery[str(res.employee_id)] = all_vecs

    return gallery, results
