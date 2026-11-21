export type IncidentStatus =
  | 'REPORTED' | 'UNDER_VERIFICATION' | 'VERIFIED' | 'QUEUED' | 'TRIAGE_IN_PROGRESS'
  | 'PENDING_APPROVAL' | 'DISPATCHED' | 'IN_TRANSIT' | 'ON_SCENE' | 'RESOLVED'
  | 'DUPLICATE' | 'REJECTED' | 'CANCELLED';

export type DataLabel = 'OBSERVED' | 'PREDICTED' | 'SIMULATED';

export interface Incident {
  id: string;
  title: string;
  description: string;
  area: string;
  latitude: float;
  longitude: float;
  severity: 'CRITICAL' | 'HIGH' | 'MODERATE' | 'LOW';
  people_affected: number;
  status: IncidentStatus;
  source: string;
  data_label?: DataLabel | string;
  beacon_id?: string | null;
  location_method?: string | null;
  verified_by?: string | null;
  duplicate_of?: string | null;
  reported_water_depth?: WaterDepth | null;
  photo_analysis?: Partial<VisionAnalysis> | null;
  incident_type?: string;
  image_url?: string | null;
  reporter_name?: string | null;
  reporter_contact?: string | null;
  device_battery_pct?: number | null;
  mesh_hops?: number | null;
  assigned_team_id?: string | null;
  created_at: string;
  updated_at: string;
}

export type float = number;

export interface RescueTeam {
  id: string;
  name: string;
  callsign: string;
  status: 'AVAILABLE' | 'DEPLOYED' | 'STANDBY';
  vehicle_type: string;
  members_count: number;
  skills: string;
  latitude: number;
  longitude: number;
  base_station: string;
  contact_number: string;
}

export interface Volunteer {
  id: string;
  name: string;
  phone: string;
  email: string;
  skills: string;
  area: string;
  is_verified: boolean;
  status: 'AVAILABLE' | 'ASSIGNED' | 'STANDBY';
  registered_at: string;
}

export interface Alert {
  id: string;
  title: string;
  message: string;
  severity: 'CRITICAL' | 'HIGH' | 'WARNING' | 'INFO';
  area: string;
  latitude: number;
  longitude: number;
  radius_km: number;
  status: 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED';
  delivery_channel: string;
  acknowledged_count: number;
  created_at: string;
  resolved_at?: string | null;
}

export interface Facility {
  id: string;
  name: string;
  facility_type: 'HOSPITAL' | 'SHELTER' | 'RELIEF_CAMP' | 'RESCUE_HQ';
  address: string;
  latitude: number;
  longitude: number;
  total_capacity: number;
  current_occupancy: number;
  status: 'OPERATIONAL' | 'NEAR_CAPACITY' | 'FULL';
  contact: string;
  distance_km?: number;
}

export interface RescueRecord {
  id: string;
  incident_id: string;
  team_id: string;
  location: string;
  people_rescued: number;
  survivors: number;
  missing: number;
  deceased: number;
  severe_injuries: number;
  minor_injuries: number;
  notes?: string;
  completed_at: string;
}

export interface SupervisorTask {
  id: string;
  task_type: string;
  title: string;
  status: 'COMPLETED' | 'PENDING_APPROVAL' | 'APPROVED' | 'DECLINED' | 'EXECUTING' | 'FAILED';
  agent_flow: string;
  input_summary: string;
  findings: string;
  recommendations: string;
  requires_human_approval: boolean;
  approved_by?: string | null;
  incident_id?: string | null;
  suggested_team_id?: string | null;
  suggested_facility_id?: string | null;
  decision_note?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContributingFactor {
  factor: string;
  impact: string;
  weight: number;
}

export interface FloodPredictionResult {
  risk_level: 'CRITICAL' | 'HIGH' | 'MODERATE' | 'LOW';
  probability: number;
  horizon_30m: number;
  horizon_45m: number;
  horizon_60m: number;
  confidence_level: string;
  contributing_factors: ContributingFactor[];
  model_name: string;
  is_simulated: boolean;
  data_source: string;
  evaluation_metrics: {
    model_architecture: string;
    training_samples: number;
    test_samples: number;
    accuracy: number;
    precision: number;
    recall: number;
    f1_score: number;
    roc_auc: number;
    confusion_matrix?: number[][];
    cv_5fold_accuracy_mean?: number;
    cv_5fold_accuracy_std?: number;
    cv_5fold_f1_mean?: number;
    cv_5fold_roc_auc_mean?: number;
    chronological_holdout_accuracy?: number;
    chronological_confusion_matrix?: number[][];
    class_distribution?: {
      total_records: number;
      non_flood_class_0: number;
      flood_class_1: number;
      flood_prevalence_pct: number;
    };
    validation_audit?: Record<string, string>;
    evaluation_suite?: Record<string, EvaluationResult>;
    model_inputs?: string[];
    feature_importances: Record<string, number>;
  };
  advisory: string;
  gauge_rule_triggered?: boolean;
}

export interface EvaluationResult {
  description: string;
  accuracy_mean: number;
  accuracy_std: number;
  f1_mean: number;
  recall_mean: number;
  roc_auc_mean: number;
}

export interface RiverGauge {
  gauge_id: string;
  station_name: string;
  river: string;
  basin: string;
  latitude: number;
  longitude: number;
  warning_level_m: number;
  danger_level_m: number;
  status: string;
}

export interface DatasetItem {
  id: string;
  name: string;
  category: string;
  records_count: number;
  status: string;
  coverage: string;
  description: string;
  last_synced?: string;
}

export interface DashboardData {
  region: string;
  data_mode: string;
  summary: {
    total_incidents: number;
    active_incidents: number;
    critical_alerts: number;
    people_affected: number;
    response_teams: {
      total: number;
      available: number;
      deployed: number;
    };
    active_alerts: number;
    volunteers: {
      total: number;
      verified: number;
    };
    facilities: {
      total: number;
      capacity: number;
      occupancy: number;
      available_beds: number;
    };
    people_rescued: number;
  };
  forecast_preview: FloodPredictionResult;
  priority_incidents: Array<{
    id: string;
    title: string;
    location: string;
    severity: string;
    status: string;
    people: number;
    source: string;
    assigned_team_id?: string;
  }>;
  active_alerts_feed: Array<{
    id: string;
    title: string;
    severity: string;
    area: string;
    radius_km: number;
    acknowledged_count: number;
    created_at: string;
  }>;
}

export interface ModelItem {
  id: string;
  name: string;
  type: string;
  framework: string;
  artifact: string;
  status: 'LOADED' | 'NOT_CONFIGURED' | 'NOT_TRAINED';
  is_loaded: boolean;
  prediction_endpoint: string | null;
  preprocessing_endpoint?: string | null;
  input_features: string[];
  accuracy: number | null;
  roc_auc: number | null;
  cv_5fold_accuracy_mean?: number | null;
  cv_5fold_accuracy_std?: number | null;
  f1_score?: number | null;
  confusion_matrix?: number[][] | null;
  class_distribution?: {
    total: number;
    negative_count: number;
    positive_count: number;
    positive_ratio: number;
  } | null;
  validation_note?: string;
  training_samples?: number | null;
  test_samples?: number | null;
  dataset_provenance: string;
  notes?: string;
}

export interface ImageItem {
  filename: string;
  size_kb: number;
  format: string;
  collection?: string;
  dimensions?: {
    width: number | null;
    height: number | null;
    aspect_ratio: string | null;
  };
  is_duplicate?: boolean;
  duplicate_of?: string | null;
  url: string;
  inspect_url: string;
  preprocess_url?: string;
  dataset_name: string;
  labels: string[];
}

export interface ImageInspectionResult {
  filename: string;
  file_size_bytes: number;
  file_size_kb: number;
  format: string;
  dimensions: {
    width: number | null;
    height: number | null;
    aspect_ratio: string | null;
  };
  channels: number;
  md5_hash?: string;
  is_duplicate?: boolean;
  duplicate_of?: string | null;
  collection?: string;
  dataset_membership: {
    dataset_name: string;
    source_folder: string;
    total_in_dataset: number;
    unique_in_dataset?: number;
  };
  computer_vision: {
    model_status: string;
    has_trained_weights: boolean;
    inference_supported: boolean;
    preprocessing_ready: boolean;
    labels: string[];
    preprocessing_specs?: {
      color_space: string;
      target_yolo_resolution: string;
      target_unet_resolution: string;
      aspect_ratio_preservation: string;
      normalization_parameters: string;
      raw_sample_luminance?: number;
    };
    explanation: string;
  };
  url: string;
  preprocess_url?: string;
}

export interface ImagePreprocessingResult {
  filename: string;
  preprocessing_status: string;
  original_shape: number[];
  target_tensor_shape: number[];
  scaling: {
    scale_factor: number;
    resized_shape: number[];
    letterbox_padding: {
      top: number;
      bottom: number;
      left: number;
      right: number;
    };
  };
  normalization: {
    mean: number[];
    std: number[];
    value_range: string;
  };
  model_integration: {
    model_status: string;
    inference_executed: boolean;
    message: string;
  };
}

export interface PaginatedImagesResponse {
  total_available: number;
  unique_available?: number;
  filtered_count: number;
  page: number;
  page_size: number;
  total_pages: number;
  dataset_info: {
    name: string;
    source_directory: string;
    verified_count: number;
    unique_count?: number;
    duplicate_count?: number;
    formats_breakdown: Record<string, number>;
    collections_breakdown?: Record<string, number>;
    status: string;
    error?: string;
    labels: string[];
    model_status: string;
  };
  images: ImageItem[];
}

export interface AuditEntry {
  id: number;
  actor: string;
  role: string;
  action: string;
  target_type: string;
  target_id: string;
  details?: string | null;
  created_at: string;
}

export interface Beacon {
  beacon_id: string;
  hotspot: string;
  latitude: number;
  longitude: number;
  last_battery_pct?: number | null;
  last_hops?: number | null;
  last_seen?: string | null;
  data_label: string;
}

export interface VisionAnalysis {
  data_label: string;
  model: string;
  flood_detected: boolean;
  flood_probability: number;
  closest_description: string;
  water_coverage_pct: number;
  water_coverage_lower_half_pct?: number;
  people_detected: number;
  people_in_water: number;
  vehicles_detected: number;
  vehicles_in_water: number;
  boats_detected: number;
  suggested_severity: 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL';
  inference_ms: number;
  caveats?: string[];
  overlay_png_base64?: string;
  filename?: string;
}

export type WaterDepth = 'ANKLE' | 'KNEE' | 'WAIST' | 'CHEST_OR_DEEPER' | 'UNKNOWN';
