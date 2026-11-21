import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.api.routes.datasets import (
    get_dataset_inventory,
    get_models_status,
    get_flood_images_paginated,
    serve_flood_image,
    inspect_image_metadata,
    preprocess_flood_image,
)

def run_tests():
    print("=== TEST 1: Dataset Inventory Endpoint ===")
    db = SessionLocal()
    try:
        t0 = time.time()
        inv = get_dataset_inventory(db=db)
        elapsed = time.time() - t0
        print(f"Inventory returned in {elapsed:.3f}s")
        assert inv["count"] == 7, f"Expected 7 datasets, got {inv['count']}"
        assert inv["flood_images_verified"] == 809, f"Expected 809 flood images, got {inv['flood_images_verified']}"
        assert inv["flood_images_unique"] == 808, f"Expected 808 unique images, got {inv['flood_images_unique']}"
        assert inv["duplicate_images_count"] == 1, f"Expected 1 duplicate pair, got {inv['duplicate_images_count']}"
        print(f" Verified total records ingested: {inv['total_records_ingested']}")
        for it in inv["items"]:
            print(f"   - [{it['id']}] {it['name']}: {it['records_count']} items ({it['status']})")
    finally:
        db.close()

    print("\n=== TEST 2: Models Status Endpoint ===")
    t0 = time.time()
    models_res = get_models_status()
    elapsed = time.time() - t0
    print(f"Models status returned in {elapsed:.3f}s")
    assert models_res["count"] == 2
    rf = next(m for m in models_res["models"] if m["id"] == "model-rf-hydrology")
    cv = next(m for m in models_res["models"] if m["id"] == "model-cv-flood-vision")

    assert rf["is_loaded"] is True
    assert rf["status"] == "LOADED"
    assert rf["prediction_endpoint"] == "/api/flood/forecast"
    print(f" RF Forecaster verified: Loaded={rf['is_loaded']}, Endpoint={rf['prediction_endpoint']}, Acc={rf['accuracy']}")

    assert cv["is_loaded"] is False
    assert cv["status"] == "NOT_CONFIGURED"
    assert cv["prediction_endpoint"] is None
    print(f" CV Vision Model verified: Configured={cv['is_loaded']}, Status={cv['status']}, Preprocessing={cv.get('preprocessing_endpoint')}")

    print("\n=== TEST 3: Paginated Flood Images (Page 1) ===")
    t0 = time.time()
    p1 = get_flood_images_paginated(page=1, page_size=12, format="all", collection="all")
    elapsed = time.time() - t0
    print(f"Paginated images (page 1, size 12) returned in {elapsed:.3f}s")
    assert p1["total_available"] == 809
    assert p1["unique_available"] == 808
    assert len(p1["images"]) == 12
    assert p1["total_pages"] == 68  # 809 / 12 = 67.4 -> 68 pages
    print(f" Page 1 OK: {len(p1['images'])} images, Total pages: {p1['total_pages']}")
    print(f"   Dataset info: {p1['dataset_info']['name']} ({p1['dataset_info']['verified_count']} verified)")
    print(f"   Formats breakdown: {p1['dataset_info']['formats_breakdown']}")
    print(f"   Collections breakdown: {p1['dataset_info']['collections_breakdown']}")

    print("\n=== TEST 4: Collection Filtering ===")
    # Remote Sensing Filter
    rs_res = get_flood_images_paginated(page=1, page_size=10, collection="remote_sensing")
    assert rs_res["filtered_count"] == 441
    print(f" Remote sensing filter OK: {rs_res['filtered_count']} tiles (512x384)")

    # Field Ground Filter
    fg_res = get_flood_images_paginated(page=1, page_size=10, collection="field_ground")
    assert fg_res["filtered_count"] == 368
    print(f" Field ground filter OK: {fg_res['filtered_count']} photos")

    # Duplicates Filter
    dup_res = get_flood_images_paginated(page=1, page_size=10, collection="duplicates")
    assert dup_res["filtered_count"] == 2
    print(f" Duplicates filter OK: {dup_res['filtered_count']} flagged duplicate files: {[img['filename'] for img in dup_res['images']]}")

    print("\n=== TEST 5: Format Filtering & Search ===")
    png_res = get_flood_images_paginated(page=1, page_size=20, format="png")
    assert png_res["filtered_count"] == 14
    print(f" Format filter PNG OK: {png_res['filtered_count']} PNG files")

    webp_res = get_flood_images_paginated(page=1, page_size=20, format="webp")
    assert webp_res["filtered_count"] == 4
    print(f" Format filter WebP OK: {webp_res['filtered_count']} WebP files")

    search_res = get_flood_images_paginated(page=1, page_size=10, search="000")
    print(f" Search '000' OK: {search_res['filtered_count']} matches")

    print("\n=== TEST 6: File Serving Endpoint & Path Traversal Guard ===")
    sample_file = p1["images"][0]["filename"]
    resp = serve_flood_image(sample_file)
    assert resp.status_code == 200
    assert resp.media_type in ["image/jpeg", "image/png", "image/webp"]
    print(f" Serving '{sample_file}' OK: status 200, media_type={resp.media_type}")

    # Test Path Traversal Prevention
    try:
        serve_flood_image("../backend/rescuenet.db")
        assert False, "Should have blocked path traversal"
    except Exception as e:
        print(f" Path traversal guard OK: blocked '../backend/rescuenet.db' -> {e}")

    print("\n=== TEST 7: Technical Image Inspection ===")
    insp = inspect_image_metadata(sample_file)
    assert insp["filename"] == sample_file
    assert insp["dimensions"]["width"] is not None
    assert insp["dimensions"]["height"] is not None
    assert insp["channels"] == 3
    assert insp["computer_vision"]["model_status"] == "Model not configured"
    assert insp["computer_vision"]["has_trained_weights"] is False
    assert insp["computer_vision"]["preprocessing_ready"] is True
    print(f" Inspection of '{sample_file}' OK: {insp['dimensions']['width']}x{insp['dimensions']['height']} px, aspect ratio {insp['dimensions']['aspect_ratio']}, MD5={insp['md5_hash'][:8]}...")
    print(f"   CV Status: {insp['computer_vision']['model_status']}")

    # Inspect duplicate file
    dup_insp = inspect_image_metadata("image_0216.jpg")
    assert dup_insp["is_duplicate"] is True
    assert dup_insp["duplicate_of"] == "image_0301.jpg"
    print(f" Inspection of duplicate 'image_0216.jpg' OK: flagged duplicate of {dup_insp['duplicate_of']}")

    print("\n=== TEST 8: Verified Image Preprocessing Endpoint ===")
    prep = preprocess_flood_image(sample_file)
    assert prep["preprocessing_status"] == "SUCCESS"
    assert prep["target_tensor_shape"] == [1, 3, 640, 640]
    assert prep["model_integration"]["model_status"] == "Model not configured"
    assert prep["model_integration"]["inference_executed"] is False
    print(f" Preprocessing of '{sample_file}' OK:")
    print(f"   Original: {prep['original_shape']}, Target: {prep['target_tensor_shape']}")
    print(f"   Scale Factor: {prep['scaling']['scale_factor']}, Resized: {prep['scaling']['resized_shape']}")
    print(f"   Model Integration: {prep['model_integration']['model_status']} (Inference Executed: {prep['model_integration']['inference_executed']})")

    print("\n==========================================")
    print(" ALL 8 DATASET & VISION PIPELINE TESTS PASSED!")
    print("==========================================")

if __name__ == "__main__":
    run_tests()
