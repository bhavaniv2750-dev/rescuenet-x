import React, { useState, useEffect } from 'react';
import { api } from '../../api/client';
import type {
  DatasetItem,
  ModelItem,
  ImageItem,
  ImageInspectionResult,
  ImagePreprocessingResult,
  PaginatedImagesResponse,
} from '../../api/types';
import {
  Database,
  Image as ImageIcon,
  Cpu,
  HardDrive,
  Search,
  ChevronLeft,
  ChevronRight,
  Eye,
  X,
  AlertTriangle,
  CheckCircle2,
  Info,
  ExternalLink,
  Sparkles,
} from 'lucide-react';

export const DatasetsView: React.FC = () => {
  // Datasets & Models State
  const [datasets, setDatasets] = useState<DatasetItem[]>([]);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [totalRecords, setTotalRecords] = useState<number>(0);
  const [verifiedImgCount, setVerifiedImgCount] = useState<number>(0);
  const [uniqueImgCount, setUniqueImgCount] = useState<number>(0);
  const [duplicateCount, setDuplicateCount] = useState<number>(0);
  const [isLoadingDatasets, setIsLoadingDatasets] = useState<boolean>(true);

  // Image Browser State
  const [imagesData, setImagesData] = useState<PaginatedImagesResponse | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(12);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [formatFilter, setFormatFilter] = useState<string>('all');
  const [collectionFilter, setCollectionFilter] = useState<string>('all');
  const [isLoadingImages, setIsLoadingImages] = useState<boolean>(false);
  const [imageErrorMap, setImageErrorMap] = useState<Record<string, boolean>>({});

  // Inspection & Preprocessing Modal State
  const [selectedImage, setSelectedImage] = useState<ImageItem | null>(null);
  const [inspectionData, setInspectionData] = useState<ImageInspectionResult | null>(null);
  const [isLoadingInspection, setIsLoadingInspection] = useState<boolean>(false);
  const [preprocessingData, setPreprocessingData] = useState<ImagePreprocessingResult | null>(null);
  const [isPreprocessing, setIsPreprocessing] = useState<boolean>(false);

  // Load Datasets and Models
  useEffect(() => {
    async function loadMetadata() {
      setIsLoadingDatasets(true);
      try {
        const [dRes, mRes] = await Promise.all([
          api.getDatasets(),
          api.getModels(),
        ]);
        setDatasets(dRes.items || []);
        setTotalRecords(dRes.total_records_ingested || 0);
        setVerifiedImgCount(dRes.flood_images_verified || 0);
        setUniqueImgCount(dRes.flood_images_unique || (dRes.flood_images_verified ? dRes.flood_images_verified - 1 : 0));
        setDuplicateCount(dRes.duplicate_images_count || 1);
        setModels(mRes.models || []);
      } catch (err: any) {
        console.error('Failed to load dataset metadata:', err);
      } finally {
        setIsLoadingDatasets(false);
      }
    }
    loadMetadata();
  }, []);

  // Load Paginated Images
  useEffect(() => {
    async function fetchImages() {
      setIsLoadingImages(true);
      try {
        const res = await api.getFloodImages({
          page: currentPage,
          page_size: pageSize,
          search: searchQuery,
          format: formatFilter,
          collection: collectionFilter,
        });
        setImagesData(res);
        if (res.dataset_info?.verified_count) {
          setVerifiedImgCount(res.dataset_info.verified_count);
        }
        if (res.unique_available) {
          setUniqueImgCount(res.unique_available);
        }
      } catch (err: any) {
        console.error('Failed to load flood images:', err);
      } finally {
        setIsLoadingImages(false);
      }
    }
    fetchImages();
  }, [currentPage, pageSize, searchQuery, formatFilter, collectionFilter]);

  // Handle Search Input Change
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
    setCurrentPage(1);
  };

  // Handle Format Filter Change
  const handleFormatChange = (fmt: string) => {
    setFormatFilter(fmt);
    setCurrentPage(1);
  };

  // Handle Collection Filter Change
  const handleCollectionChange = (col: string) => {
    setCollectionFilter(col);
    setCurrentPage(1);
  };

  // Inspect Image Modal Trigger
  const handleInspectImage = async (img: ImageItem) => {
    setSelectedImage(img);
    setIsLoadingInspection(true);
    setInspectionData(null);
    setPreprocessingData(null);
    try {
      const data = await api.inspectImage(img.filename);
      setInspectionData(data);
    } catch (err: any) {
      console.error('Failed to inspect image:', err);
    } finally {
      setIsLoadingInspection(false);
    }
  };

  // Run Real Preprocessing Validation
  const handleRunPreprocessing = async () => {
    if (!selectedImage) return;
    setIsPreprocessing(true);
    try {
      const result = await api.preprocessImage(selectedImage.filename);
      setPreprocessingData(result);
    } catch (err: any) {
      console.error('Failed to preprocess image:', err);
    } finally {
      setIsPreprocessing(false);
    }
  };

  const closeInspectionModal = () => {
    setSelectedImage(null);
    setInspectionData(null);
    setPreprocessingData(null);
  };

  const activeForecaster = models.find((m) => m.is_loaded);

  return (
    <div className="datasets-container">
      {/* View Header */}
      <div className="view-header">
        <div>
          <h2>Integrated Dataset Inventory & Model Provenance</h2>
          <p>
            Real workspace data repositories: IndoFloods Catchment Shapefiles, Gauge Telemetry,
            Clean RescueNet LoRa SOS records, and Verified Flood Inundation Imagery.
          </p>
        </div>
        <div className="stats-badges">
          <span className="badge">
            <HardDrive size={14} /> {datasets.length} Active Datasets
          </span>
          <span className="badge">
            <Database size={14} /> {totalRecords.toLocaleString()} Tabular Records
          </span>
          <span className="badge">
            <ImageIcon size={14} className="text-cyan" /> {verifiedImgCount} Verified Images ({uniqueImgCount} Unique)
          </span>
          <span className="badge">
            <Cpu size={14} className={activeForecaster ? 'text-emerald' : 'text-amber'} />{' '}
            {activeForecaster ? 'RF Forecaster Active' : 'No Model Loaded'}
          </span>
        </div>
      </div>

      {/* SECTION 1: Real Machine Learning Models & Capabilities */}
      <div className="section-title-bar" style={{ marginTop: '12px', marginBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Cpu size={18} className="text-cyan" />
          <h3 style={{ margin: 0, fontSize: '15px' }}>Machine Learning Models & Prediction Endpoints</h3>
        </div>
        <span className="font-mono text-xs text-muted">Real Backend Inference Status</span>
      </div>

      <div className="models-grid">
        {models.map((m) => (
          <div key={m.id} className={`panel model-card ${m.is_loaded ? 'model-loaded' : 'model-unconfigured'}`}>
            <div className="model-card-header">
              <div>
                <span className="model-type-tag font-mono">{m.type}</span>
                <h4 className="model-name">{m.name}</h4>
              </div>
              <span className={`status-pill ${m.is_loaded ? 'pill-active' : 'pill-warning'}`}>
                {m.status === 'LOADED' ? (
                  <>
                    <CheckCircle2 size={12} style={{ display: 'inline', marginRight: '4px' }} />
                    LOADED & ACTIVE
                  </>
                ) : (
                  <>
                    <AlertTriangle size={12} style={{ display: 'inline', marginRight: '4px' }} />
                    NOT CONFIGURED
                  </>
                )}
              </span>
            </div>

            <div className="model-meta-table">
              <div className="model-meta-row">
                <span>Framework:</span>
                <span className="font-mono">{m.framework}</span>
              </div>
              <div className="model-meta-row">
                <span>Model Artifact:</span>
                <span className="font-mono text-xs">{m.artifact}</span>
              </div>
              <div className="model-meta-row">
                <span>Prediction Endpoint:</span>
                {m.prediction_endpoint ? (
                  <span className="font-mono text-xs text-cyan">{m.prediction_endpoint}</span>
                ) : (
                  <span className="font-mono text-xs text-muted">None (Inference Disabled)</span>
                )}
              </div>
              {m.preprocessing_endpoint && (
                <div className="model-meta-row">
                  <span>Preprocessing API:</span>
                  <span className="font-mono text-xs text-emerald">{m.preprocessing_endpoint}</span>
                </div>
              )}
              <div className="model-meta-row">
                <span>Dataset Grounding:</span>
                <span className="font-mono text-xs">{m.dataset_provenance}</span>
              </div>
              {m.accuracy !== null && (
                <>
                  <div className="model-meta-row">
                    <span>Holdout Accuracy:</span>
                    <strong className="font-mono text-emerald">{(m.accuracy * 100).toFixed(1)}% (ROC-AUC: {m.roc_auc})</strong>
                  </div>
                  {m.cv_5fold_accuracy_mean !== undefined && m.cv_5fold_accuracy_mean !== null && (
                    <div className="model-meta-row">
                      <span>5-Fold Stratified CV:</span>
                      <strong className="font-mono text-cyan">{(m.cv_5fold_accuracy_mean * 100).toFixed(1)}% (±{((m.cv_5fold_accuracy_std ?? 0) * 100).toFixed(1)}%)</strong>
                    </div>
                  )}
                  {m.confusion_matrix && (
                    <div className="model-meta-row">
                      <span>Confusion Matrix:</span>
                      <span className="font-mono text-xs text-muted">
                        TN: {m.confusion_matrix[0][0]} | FP: {m.confusion_matrix[0][1]} | FN: {m.confusion_matrix[1][0]} | TP: {m.confusion_matrix[1][1]}
                      </span>
                    </div>
                  )}
                  {m.validation_note && (
                    <div className="model-meta-row" style={{ display: 'block', paddingTop: '4px', borderTop: '1px dashed var(--border-color, #334155)' }}>
                      <span className="badge" style={{ fontSize: '10px', background: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8', padding: '2px 6px', borderRadius: '4px' }}>
                        Curated Benchmark (Deterministic Water-Level Threshold: &gt;4.21m)
                      </span>
                      <p style={{ margin: '4px 0 0', fontSize: '11px', color: '#94a3b8' }}>{m.validation_note}</p>
                    </div>
                  )}
                </>
              )}
            </div>

            {m.notes && (
              <div className="model-note-box">
                <Info size={14} className="text-amber" style={{ flexShrink: 0, marginTop: '2px' }} />
                <span>{m.notes}</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* SECTION 2: Verified Datasets Inventory */}
      <div className="section-title-bar" style={{ marginTop: '24px', marginBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Database size={18} className="text-cyan" />
          <h3 style={{ margin: 0, fontSize: '15px' }}>Verified Dataset Repositories</h3>
        </div>
        <span className="font-mono text-xs text-muted">Direct Local Filesystem Provenance</span>
      </div>

      <div className="datasets-grid">
        {isLoadingDatasets ? (
          <div style={{ gridColumn: '1 / -1', padding: '36px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
            <span className="spinner" style={{ width: '24px', height: '24px', display: 'inline-block' }}></span>
            <p style={{ marginTop: '8px', fontSize: '12px' }}>Loading dataset metadata from backend...</p>
          </div>
        ) : (
          datasets.map((item) => (
            <div key={item.id} className="panel dataset-card">
              <div className="dataset-card-top">
                <span className="dataset-cat-tag font-mono">{item.category}</span>
                <span className="dataset-status-pill">{item.status}</span>
              </div>

              <h3 className="dataset-name">{item.name}</h3>
              <p className="dataset-desc">{item.description}</p>

              <div className="dataset-meta-box">
                <div className="dataset-meta-row">
                  <span>Verified Records / Files:</span>
                  <strong className="font-mono text-cyan">{item.records_count.toLocaleString()}</strong>
                </div>
                <div className="dataset-meta-row">
                  <span>Coverage / Context:</span>
                  <span>{item.coverage}</span>
                </div>
                <div className="dataset-meta-row">
                  <span>Registry Identifier:</span>
                  <span className="font-mono text-xs">{item.id}</span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* SECTION 3: Proper Flood Imagery Dataset Browser */}
      <div className="panel image-browser-panel" style={{ marginTop: '24px' }}>
        {/* Panel Header */}
        <div className="panel-title-bar" style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '17px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <ImageIcon size={20} className="text-cyan" />
              Flood Imagery Dataset
            </h3>
            <p style={{ margin: '4px 0 0', color: 'var(--text-muted)', fontSize: '13px' }}>
              Verified repository of <strong>{verifiedImgCount} field & remote sensing flood disaster images</strong> ({uniqueImgCount} unique files, {duplicateCount} duplicate pair flagged) stored in the{' '}
              <code>flood/</code> directory. Real-time serving, pagination, duplicate detection, and computer vision preprocessing.
            </p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span className="status-pill pill-warning" style={{ fontSize: '11px', padding: '3px 8px' }}>
              <AlertTriangle size={12} style={{ display: 'inline', marginRight: '4px' }} />
              Vision Model: Not Configured
            </span>
          </div>
        </div>

        {/* Dataset Metadata Highlights Banner */}
        <div className="dataset-provenance-banner">
          <div className="prov-item">
            <span className="prov-label">Dataset Name</span>
            <span className="prov-val">Flood Imagery Dataset (Field & Remote Sensing)</span>
          </div>
          <div className="prov-item">
            <span className="prov-label">Verified Image Count</span>
            <span className="prov-val font-mono text-cyan">{verifiedImgCount} Files ({uniqueImgCount} Unique)</span>
          </div>
          <div className="prov-item">
            <span className="prov-label">Storage Location</span>
            <span className="prov-val font-mono">flood/ (Local Directory)</span>
          </div>
          <div className="prov-item">
            <span className="prov-label">Discovered Sub-Collections</span>
            <span className="prov-val">441 Remote Sensing (512x384) + 368 Field Ground Captures</span>
          </div>
          <div className="prov-item">
            <span className="prov-label">Companion Dataset</span>
            <span className="prov-val font-mono">Roboflow People Archive (101 Images, 212 BBoxes)</span>
          </div>
        </div>

        {/* Filter and Search Controls Toolbar */}
        <div className="browser-toolbar">
          {/* Search Box */}
          <div className="search-box-wrap">
            <Search size={15} className="search-icon text-muted" />
            <input
              type="text"
              placeholder="Search images by filename (e.g. image_000, 1655, 0216)..."
              value={searchQuery}
              onChange={handleSearchChange}
              className="toolbar-search-input"
            />
            {searchQuery && (
              <button
                className="clear-search-btn"
                onClick={() => {
                  setSearchQuery('');
                  setCurrentPage(1);
                }}
              >
                <X size={14} />
              </button>
            )}
          </div>

          {/* Collection Filter Group */}
          <div className="format-pills-group">
            <button
              className={`format-pill ${collectionFilter === 'all' ? 'active' : ''}`}
              onClick={() => handleCollectionChange('all')}
              title="Show all collections"
            >
              All Collections ({imagesData?.dataset_info?.collections_breakdown?.all ?? verifiedImgCount})
            </button>
            <button
              className={`format-pill ${collectionFilter === 'remote_sensing' ? 'active' : ''}`}
              onClick={() => handleCollectionChange('remote_sensing')}
              title="Remote Sensing Drone / Aerial tiles (512x384)"
            >
              Remote Sensing ({imagesData?.dataset_info?.collections_breakdown?.remote_sensing ?? 441})
            </button>
            <button
              className={`format-pill ${collectionFilter === 'field_ground' ? 'active' : ''}`}
              onClick={() => handleCollectionChange('field_ground')}
              title="Ground field observation photographs"
            >
              Field Photos ({imagesData?.dataset_info?.collections_breakdown?.field_ground ?? 368})
            </button>
            <button
              className={`format-pill ${collectionFilter === 'duplicates' ? 'active' : ''}`}
              onClick={() => handleCollectionChange('duplicates')}
              title="Flagged duplicate file instances"
            >
              Duplicates ({imagesData?.dataset_info?.collections_breakdown?.duplicates ?? 2})
            </button>
          </div>

          {/* Format Filter Group */}
          <div className="format-pills-group">
            <button
              className={`format-pill ${formatFilter === 'all' ? 'active' : ''}`}
              onClick={() => handleFormatChange('all')}
            >
              All Formats
            </button>
            <button
              className={`format-pill ${formatFilter === 'jpg' ? 'active' : ''}`}
              onClick={() => handleFormatChange('jpg')}
            >
              JPG ({imagesData?.dataset_info?.formats_breakdown?.jpg ?? 0})
            </button>
            <button
              className={`format-pill ${formatFilter === 'png' ? 'active' : ''}`}
              onClick={() => handleFormatChange('png')}
            >
              PNG ({imagesData?.dataset_info?.formats_breakdown?.png ?? 0})
            </button>
            <button
              className={`format-pill ${formatFilter === 'webp' ? 'active' : ''}`}
              onClick={() => handleFormatChange('webp')}
            >
              WebP ({imagesData?.dataset_info?.formats_breakdown?.webp ?? 0})
            </button>
          </div>

          {/* Page Size Selector */}
          <div className="page-size-selector">
            <span className="text-xs text-muted">Per Page:</span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setCurrentPage(1);
              }}
              className="toolbar-select"
            >
              <option value={12}>12</option>
              <option value={24}>24</option>
              <option value={48}>48</option>
            </select>
          </div>
        </div>

        {/* Images Grid */}
        <div className="images-browser-grid">
          {isLoadingImages ? (
            <div className="gallery-loading-state">
              <span className="spinner" style={{ width: '28px', height: '28px' }}></span>
              <p>Loading image records from backend...</p>
            </div>
          ) : imagesData?.dataset_info?.status === 'DIR_NOT_FOUND' ? (
            <div className="gallery-empty-state" style={{ color: 'var(--accent-red)' }}>
              <AlertTriangle size={36} />
              <p>Image directory flood/ was not found on local disk.</p>
              <span className="font-mono text-xs text-muted">{imagesData.dataset_info.error}</span>
            </div>
          ) : imagesData && imagesData.images.length > 0 ? (
            imagesData.images.map((img) => (
              <div key={img.filename} className={`image-card-item ${img.is_duplicate ? 'border-amber' : ''}`}>
                <div className="image-card-thumb-wrap" onClick={() => handleInspectImage(img)}>
                  {imageErrorMap[img.filename] ? (
                    <div className="image-fallback-box">
                      <AlertTriangle size={24} className="text-amber" />
                      <span className="font-mono text-xs">Preview Unavailable</span>
                    </div>
                  ) : (
                    <img
                      src={img.url}
                      alt={img.filename}
                      className="image-card-thumb"
                      loading="lazy"
                      onError={() => {
                        setImageErrorMap((prev) => ({ ...prev, [img.filename]: true }));
                      }}
                    />
                  )}
                  {img.is_duplicate && (
                    <div style={{ position: 'absolute', top: '6px', left: '6px', zIndex: 2 }}>
                      <span className="status-pill pill-warning" style={{ fontSize: '9px', padding: '2px 6px' }}>
                        Duplicate File
                      </span>
                    </div>
                  )}
                  <div className="image-card-hover-overlay">
                    <button className="inspect-btn" onClick={(e) => { e.stopPropagation(); handleInspectImage(img); }}>
                      <Eye size={14} /> Inspect & Preprocess
                    </button>
                  </div>
                </div>

                <div className="image-card-footer">
                  <div className="image-card-title-row">
                    <span className="image-filename font-mono" title={img.filename}>
                      {img.filename}
                    </span>
                    <span className="image-format-badge">{img.format}</span>
                  </div>
                  <div className="image-card-sub-row">
                    <span>{img.size_kb} KB</span>
                    <span className="text-xs text-cyan">{img.collection}</span>
                  </div>
                  {img.is_duplicate && (
                    <div style={{ fontSize: '10px', color: 'var(--accent-amber)', marginTop: '2px' }}>
                      Duplicate of {img.duplicate_of}
                    </div>
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="gallery-empty-state">
              <ImageIcon size={36} className="text-muted" />
              <p>No images matched your filters.</p>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setSearchQuery('');
                  setFormatFilter('all');
                  setCollectionFilter('all');
                  setCurrentPage(1);
                }}
              >
                Reset All Filters
              </button>
            </div>
          )}
        </div>

        {/* Pagination Bar */}
        {imagesData && imagesData.filtered_count > 0 && (
          <div className="pagination-bar">
            <div className="pagination-info text-xs text-muted">
              Showing{' '}
              <strong className="text-white">
                {(currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, imagesData.filtered_count)}
              </strong>{' '}
              of <strong className="text-white">{imagesData.filtered_count}</strong> images (Total in dataset:{' '}
              {imagesData.total_available}, Unique: {imagesData.unique_available || uniqueImgCount})
            </div>

            <div className="pagination-controls">
              <button
                className="btn btn-secondary btn-sm"
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft size={14} /> Previous
              </button>

              <span className="pagination-page-indicator font-mono text-xs">
                Page {currentPage} of {imagesData.total_pages}
              </span>

              <button
                className="btn btn-secondary btn-sm"
                disabled={currentPage >= imagesData.total_pages}
                onClick={() => setCurrentPage((p) => Math.min(imagesData.total_pages, p + 1))}
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* SECTION 4: Image Metadata & Inspection Modal */}
      {selectedImage && (
        <div className="image-modal-backdrop" onClick={closeInspectionModal}>
          <div className="image-modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="image-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Eye size={18} className="text-cyan" />
                <h3 style={{ margin: 0, fontSize: '16px' }} className="font-mono">
                  {selectedImage.filename}
                </h3>
              </div>
              <button className="modal-close-btn" onClick={closeInspectionModal}>
                <X size={18} />
              </button>
            </div>

            <div className="image-modal-body">
              {/* Left Column: Full Image Preview */}
              <div className="modal-image-preview-col">
                <img
                  src={selectedImage.url}
                  alt={selectedImage.filename}
                  className="modal-full-image"
                />
              </div>

              {/* Right Column: Technical Inspection Metadata */}
              <div className="modal-meta-col">
                <h4 style={{ margin: '0 0 12px', fontSize: '14px', color: 'var(--accent-cyan)' }}>
                  Technical Image Inspection
                </h4>

                {isLoadingInspection ? (
                  <div style={{ padding: '24px 0', textAlign: 'center' }}>
                    <span className="spinner" style={{ width: '24px', height: '24px' }}></span>
                    <p className="text-xs text-muted" style={{ marginTop: '8px' }}>
                      Extracting image binary headers...
                    </p>
                  </div>
                ) : inspectionData ? (
                  <div className="inspection-details-list">
                    <div className="insp-row">
                      <span className="insp-label">File Name:</span>
                      <span className="insp-val font-mono">{inspectionData.filename}</span>
                    </div>
                    <div className="insp-row">
                      <span className="insp-label">Format:</span>
                      <span className="insp-val font-mono text-cyan">{inspectionData.format}</span>
                    </div>
                    <div className="insp-row">
                      <span className="insp-label">File Size:</span>
                      <span className="insp-val font-mono">
                        {inspectionData.file_size_kb} KB ({inspectionData.file_size_bytes.toLocaleString()} bytes)
                      </span>
                    </div>
                    <div className="insp-row">
                      <span className="insp-label">Resolution:</span>
                      <span className="insp-val font-mono">
                        {inspectionData.dimensions.width && inspectionData.dimensions.height
                          ? `${inspectionData.dimensions.width} × ${inspectionData.dimensions.height} px`
                          : 'Detected via stream'}
                      </span>
                    </div>
                    {inspectionData.dimensions.aspect_ratio && (
                      <div className="insp-row">
                        <span className="insp-label">Aspect Ratio:</span>
                        <span className="insp-val font-mono">{inspectionData.dimensions.aspect_ratio}</span>
                      </div>
                    )}
                    <div className="insp-row">
                      <span className="insp-label">Color Channels:</span>
                      <span className="insp-val font-mono">{inspectionData.channels} (RGB)</span>
                    </div>
                    {inspectionData.md5_hash && (
                      <div className="insp-row">
                        <span className="insp-label">MD5 Hash:</span>
                        <span className="insp-val font-mono text-xs">{inspectionData.md5_hash.substring(0, 16)}...</span>
                      </div>
                    )}
                    <div className="insp-row">
                      <span className="insp-label">Collection:</span>
                      <span className="insp-val font-mono">{inspectionData.collection}</span>
                    </div>

                    {inspectionData.is_duplicate && (
                      <div style={{ padding: '8px 10px', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '4px', marginTop: '6px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--accent-amber)', fontWeight: 600 }}>
                          Duplicate File Notice:
                        </span>
                        <p style={{ margin: '2px 0 0', fontSize: '11px', color: '#e2e8f0' }}>
                          This file has an identical MD5 hash to <code>{inspectionData.duplicate_of}</code>.
                        </p>
                      </div>
                    )}

                    {/* Computer Vision Preprocessing Section */}
                    <div className="cv-integration-box">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                        <AlertTriangle size={15} className="text-amber" />
                        <strong style={{ fontSize: '12px' }}>Computer Vision Model Status</strong>
                      </div>
                      <p style={{ margin: 0, fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.4' }}>
                        {inspectionData.computer_vision.explanation}
                      </p>
                      <div style={{ marginTop: '8px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        <span className="status-pill pill-warning" style={{ fontSize: '9px' }}>
                          Model Not Configured
                        </span>
                        <span className="status-pill pill-active" style={{ fontSize: '9px' }}>
                          Preprocessing Ready
                        </span>
                      </div>

                      {/* Interactive Preprocessing Button */}
                      <div style={{ marginTop: '12px' }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          style={{ width: '100%', fontSize: '11px', justifyContent: 'center' }}
                          onClick={handleRunPreprocessing}
                          disabled={isPreprocessing}
                        >
                          <Sparkles size={13} className="text-cyan" />
                          {isPreprocessing ? 'Computing Tensor Scaling...' : 'Run Preprocessing Validation'}
                        </button>
                      </div>

                      {/* Preprocessing Output */}
                      {preprocessingData && (
                        <div style={{ marginTop: '10px', padding: '8px', background: '#030712', border: '1px solid var(--border-subtle)', borderRadius: '4px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '4px' }}>
                            <CheckCircle2 size={13} className="text-emerald" />
                            <strong style={{ fontSize: '11px', color: 'var(--accent-emerald)' }}>Preprocessing Validated</strong>
                          </div>
                          <div style={{ fontSize: '10px', color: '#94a3b8', lineHeight: '1.5' }}>
                            <div>Target Tensor: <code>{JSON.stringify(preprocessingData.target_tensor_shape)}</code></div>
                            <div>Scale Factor: <code>{preprocessingData.scaling.scale_factor}</code> (Resized: {preprocessingData.scaling.resized_shape[1]}x{preprocessingData.scaling.resized_shape[0]} px)</div>
                            <div>Letterbox Padding: Top/Bottom: {preprocessingData.scaling.letterbox_padding.top}px, Left/Right: {preprocessingData.scaling.letterbox_padding.left}px</div>
                            <div style={{ marginTop: '4px', color: 'var(--accent-amber)' }}>
                              {preprocessingData.model_integration.message}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-muted">Inspection details could not be loaded.</p>
                )}

                <div style={{ marginTop: 'auto', paddingTop: '16px' }}>
                  <a
                    href={selectedImage.url}
                    target="_blank"
                    rel="noreferrer"
                    className="btn btn-secondary btn-sm"
                    style={{ width: '100%', justifyContent: 'center' }}
                  >
                    <ExternalLink size={14} /> Open Full Resolution in New Tab
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
