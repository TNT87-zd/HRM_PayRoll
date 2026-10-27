import numpy as np
# from cv.face_engine import FaceEngine

class FaceService:
    def __init__(self):
        self.engine = None                          # TODO: FaceEngine(model_pack="buffalo_l")
        self.gallery: dict[str, np.ndarray] = {}

    def startup(self, db):
        """Gọi 1 lần ở lifespan: nạp model + gallery."""
        # TODO: self.engine = FaceEngine(...)
        # TODO: self.load_gallery(db)
        pass

    def load_gallery(self, db):
        # TODO: đọc bảng FaceEmbedding -> self.gallery
        pass

    def recognize(self, img_bgr: np.ndarray) -> dict:
        # TODO: extract_single_face -> match -> dict khớp RecognizeResponse
        raise NotImplementedError

    def enroll(self, employee_id: str, imgs: list[np.ndarray], db) -> dict:
        # TODO: engine.enroll_from_images -> lưu DB -> load_gallery
        raise NotImplementedError

face_service = FaceService()