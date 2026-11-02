"""Model-independent regression tests for the CV package."""
import ssl
import sys
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cv.face_engine import FaceEngine, InsightFaceEngine
from cv.matching import match
from cv.model_store import ModelStore
from cv.types import DetectedFace, FaceQualityReport


@pytest.fixture
def basis():
    return np.eye(5, 512, dtype=np.float32)


def fake_engine():
    engine = FaceEngine.__new__(FaceEngine)
    def extract(image_or_path, **kwargs):
        report = FaceQualityReport(is_valid=True, num_faces=1)
        return DetectedFace(
            bbox=np.array([0, 0, 100, 100]), det_score=1.0,
            kps=np.zeros((5, 2)), embedding=image_or_path, quality=report,
        ), report
    engine.extract_single_face = extract
    return engine


def test_legacy_alias_and_matching(basis):
    assert InsightFaceEngine is FaceEngine
    result = FaceEngine.match(basis[0], {'A': basis[0], 'B': basis[1]})
    assert result.matched and result.employee_id == 'A'
    assert result.similarity == pytest.approx(1.0)


@pytest.mark.parametrize('value', [np.nan, np.inf, -np.inf, 0.0])
def test_invalid_query_and_gallery_are_rejected(basis, value):
    invalid = np.full(512, value, dtype=np.float32)
    with pytest.raises(ValueError):
        match(invalid, {'A': basis[0]})
    with pytest.raises(ValueError):
        match(basis[0], {'A': invalid})
    with pytest.raises(ValueError):
        match(basis[0], {'A': np.vstack([basis[0], invalid])})


@pytest.mark.parametrize('shape', [(511,), (1, 512), (512, 1)])
def test_query_shape_contract(basis, shape):
    with pytest.raises(ValueError):
        match(np.ones(shape), {'A': basis[0]})


def test_matching_decisions(basis):
    assert match(basis[0], {}).reason == 'empty_gallery'
    assert match(basis[0], {'A': basis[1]}).reason == 'below_threshold'
    assert match(basis[0], {'A': basis[0], 'B': basis[0]}).reason == 'ambiguous_margin'
    assert match(basis[0], {'A': np.vstack([basis[1], basis[0]])}).matched
    with pytest.raises(ValueError):
        match(basis[0], {'A': np.empty((0, 512))})


def test_unrelated_enrollment_is_rejected(basis):
    result = fake_engine().enroll_from_images(list(basis))
    assert not result.success
    assert result.centroid_embedding is None
    assert 'cross-sample' in result.message


def test_single_outlier_is_rejected(basis):
    result = fake_engine().enroll_from_images([basis[0]] * 4 + [basis[1]])
    assert not result.success


def test_consistent_enrollment_and_gallery(basis, tmp_path):
    engine = fake_engine()
    result = engine.enroll_from_images([basis[0]] * 3, employee_id='A')
    assert result.success
    assert np.linalg.norm(result.centroid_embedding) == pytest.approx(1.0)
    engine.enroll_from_images = Mock(return_value=result)
    (tmp_path / 'A').mkdir()
    gallery, results = engine.enroll_gallery_from_root(tmp_path)
    assert gallery['A'].shape == (4, 512)
    assert results == [result]


def test_invalid_enrollment_embedding_is_reported(basis):
    result = fake_engine().enroll_from_images([basis[0]] * 2 + [np.full(512, np.nan)])
    assert not result.success
    assert result.rejected_files['frame_2'][0].startswith('invalid_embedding:')


def test_model_store_local_pair(tmp_path):
    pack = tmp_path / 'models' / 'buffalo_l'
    pack.mkdir(parents=True)
    det, rec = pack / 'det_10g.onnx', pack / 'w600k_r50.onnx'
    det.touch()
    rec.touch()
    store = ModelStore('buffalo_l', tmp_path, ['CPUExecutionProvider'], (640, 640), .5)
    assert store.resolve_paths(None, None, False) == (det, rec)


def test_download_does_not_retry_without_tls_verification(tmp_path):
    store = ModelStore('buffalo_l', tmp_path, [], (640, 640), .5)
    error = urllib.error.URLError(ssl.SSLCertVerificationError('untrusted'))
    with patch('cv.model_store.urllib.request.urlopen', side_effect=error) as opener, patch(
        'cv.model_store.importlib.import_module', side_effect=ImportError
    ):
        with pytest.raises(RuntimeError, match='TLS'):
            store._download_pack_via_insightface()
        assert opener.call_count == 1


def test_disconnected_identity_groups_are_rejected(basis):
    result = fake_engine().enroll_from_images([basis[0]] * 2 + [basis[1]] * 2)
    assert not result.success
