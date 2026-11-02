"""Embedding normalization and identity matching."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from .types import MatchResult


def l2_normalize(vec: np.ndarray, axis: int = -1, eps: float = 1e-12) -> np.ndarray:
    """Chuẩn hóa vector hoặc ma trận vector theo chuẩn L2."""
    arr = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(arr, axis=axis, keepdims=True)
    return arr / np.maximum(norm, eps)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Tính Cosine Similarity giữa 2 vector 1D (trong khoảng [-1, 1])."""
    a = l2_normalize(vec_a.reshape(-1))
    b = l2_normalize(vec_b.reshape(-1))
    return float(np.dot(a, b))



def validate_embeddings(value: np.ndarray, *, batch: bool = False) -> np.ndarray:
    """Validate the 512-D embedding contract before scoring or enrollment."""
    arr = np.asarray(value, dtype=np.float32)
    valid_shape = (arr.ndim == 2 and arr.shape[0] > 0 and arr.shape[1] == 512) if batch else arr.shape == (512,)
    if not valid_shape:
        raise ValueError(f"Embedding shape không hợp lệ: {arr.shape}")
    if not np.isfinite(arr).all():
        raise ValueError("Embedding phải chứa các giá trị hữu hạn")
    norms = np.linalg.norm(arr.astype(np.float64), axis=-1)
    if np.any(norms <= 1e-12):
        raise ValueError("Embedding không được là vector zero")
    return arr

def match(
    query_embedding: np.ndarray,
    gallery: Dict[str, np.ndarray],
    threshold: float = 0.55,
    min_margin: float = 0.08,
) -> MatchResult:
    """
    So khớp vector khuôn mặt `query_embedding` (512,) với danh sách nhân viên `gallery`.

    - `gallery`: Dict ánh xạ `employee_id -> np.ndarray` có shape `(512,)` (1 vector centroid)
      hoặc `(K, 512)` (nhiều mẫu góc mặt của nhân viên đó).
    - Quy tắc chấp nhận (Mục 4.1 - PLAN.MD):
      1. Điểm khớp cao nhất `best_score >= threshold`.
      2. Nếu trong gallery có từ 2 nhân viên trở lên, khoảng cách giữa người khớp nhất
         và người khớp nhì phải thỏa `best_score - second_best_score >= min_margin`.
    """
    if not np.isfinite(threshold) or not -1 <= threshold <= 1:
        raise ValueError("threshold phải thuộc [-1, 1]")
    if not np.isfinite(min_margin) or min_margin < 0:
        raise ValueError("min_margin phải hữu hạn và không âm")
    query = validate_embeddings(query_embedding)
    if not gallery:
        return MatchResult(
            matched=False,
            employee_id=None,
            similarity=0.0,
            second_best_employee_id=None,
            second_best_similarity=0.0,
            margin=0.0,
            threshold=threshold,
            min_margin=min_margin,
            reason="empty_gallery",
        )

    q = l2_normalize(query)
    scores: List[Tuple[str, float]] = []

    for emp_id, ref in gallery.items():
        ref_arr = np.asarray(ref, dtype=np.float32)
        validate_embeddings(ref_arr, batch=ref_arr.ndim == 2)
        if ref_arr.ndim == 1:
            ref_norm = l2_normalize(ref_arr)
            score = float(np.dot(q, ref_norm))
        elif ref_arr.ndim == 2:
            ref_norm = l2_normalize(ref_arr, axis=1)
            score = float(np.max(ref_norm @ q))
        else:
            raise ValueError(
                f"Embedding của nhân viên '{emp_id}' có shape không hợp lệ: {ref_arr.shape}"
            )
        scores.append((emp_id, score))

    scores.sort(key=lambda item: item[1], reverse=True)
    best_emp, best_score = scores[0]
    if len(scores) > 1:
        second_emp, second_score = scores[1]
        margin = float(best_score - second_score)
    else:
        second_emp, second_score = None, -1.0
        margin = float("inf")

    if best_score < threshold:
        return MatchResult(
            matched=False,
            employee_id=None,
            similarity=best_score,
            second_best_employee_id=second_emp,
            second_best_similarity=second_score,
            margin=margin,
            threshold=threshold,
            min_margin=min_margin,
            reason="below_threshold",
        )

    if len(scores) > 1 and margin < min_margin:
        return MatchResult(
            matched=False,
            employee_id=None,
            similarity=best_score,
            second_best_employee_id=second_emp,
            second_best_similarity=second_score,
            margin=margin,
            threshold=threshold,
            min_margin=min_margin,
            reason="ambiguous_margin",
        )

    return MatchResult(
        matched=True,
        employee_id=best_emp,
        similarity=best_score,
        second_best_employee_id=second_emp,
        second_best_similarity=second_score,
        margin=margin,
        threshold=threshold,
        min_margin=min_margin,
        reason="accepted",
    )
