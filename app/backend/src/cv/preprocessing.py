"""Optional offline experiments. Live enrollment uses baseline until evaluated."""
import cv2
import numpy as np

POLICIES = ("baseline", "gamma", "clahe", "white_balance", "sharpen", "denoise")


def enhance_face(image, policy="baseline"):
    if policy == "baseline":
        return image.copy()
    if policy == "gamma":
        brightness = float(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).mean())
        gamma = 0.85 if brightness < 90 else 1.15 if brightness > 180 else 1.0
        table = np.clip(255 * (np.arange(256) / 255) ** gamma, 0, 255).astype(np.uint8)
        return cv2.LUT(image, table)
    if policy == "clahe":
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(4, 4)).apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    if policy == "white_balance":
        values = image.astype(np.float32)
        means = values.mean(axis=(0, 1))
        scale = np.clip(means.mean() / np.maximum(means, 1), 0.85, 1.15)
        return np.clip(values * scale, 0, 255).astype(np.uint8)
    if policy == "sharpen":
        return cv2.addWeighted(image, 1.25, cv2.GaussianBlur(image, (3, 3), 0), -0.25, 0)
    if policy == "denoise":
        return cv2.bilateralFilter(image, 3, 15, 15)
    raise ValueError(f"Unknown preprocessing policy: {policy}")
