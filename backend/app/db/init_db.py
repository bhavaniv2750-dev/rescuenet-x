import csv
from datetime import datetime, timezone
from pathlib import Path
from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.db.beacon_registry import BENGALURU_HOTSPOTS
from app.db.migrate import upgrade_schema
from app.db.seed_users import seed_users
from app.models.entities import (
    Alert,
    Beacon,
    DatasetRegistry,
    Facility,
    Incident,
    RescueRecord,
    RescueTeam,
    SupervisorTask,
    Volunteer,
)

def init_db():
    _init_core()
    seed_users()


def _init_core():
    print("[init_db] Creating all database tables...")
    Base.metadata.create_all(bind=engine)
    added = upgrade_schema(engine)
    if added:
        print(f"[init_db] Added missing columns: {', '.join(added)}")

    db = SessionLocal()
    try:
        # The beacon registry is seeded separately so older databases get it too.
        if db.query(Beacon).count() == 0:
            db.add_all(
                Beacon(beacon_id=bid, hotspot=name, latitude=lat, longitude=lon, data_label="SIMULATED")
                for bid, name, lat, lon in BENGALURU_HOTSPOTS
            )
            db.commit()
            print(f"[init_db] Seeded {len(BENGALURU_HOTSPOTS)} simulated LoRa beacons at Bengaluru hotspots")

        # Check if already seeded
        if db.query(RescueTeam).count() > 0:
            print("[init_db] Database already contains records. Skipping initial seed.")
            return

        print("[init_db] Seeding Rescue Teams...")
        teams = [
            RescueTeam(
                id="TEAM-NDRF-10",
                name="NDRF 10th Battalion Alpha",
                callsign="Thunder-1",
                status="AVAILABLE",
                vehicle_type="Inflatable Rescue Boat + Amphibious Transport",
                members_count=8,
                skills="Swiftwater Rescue, Combat Diving, Emergency Triage",
                latitude=12.9716,
                longitude=77.5946,
                base_station="Cubbon Park NDRF Staging Post",
                contact_number="+91 80 2297 5001",
            ),
            RescueTeam(
                id="TEAM-SDRF-02",
                name="Karnataka SDRF Water Squad",
                callsign="Varuna-2",
                status="DEPLOYED",
                vehicle_type="Rigid Inflatable Hull Boat (RIB)",
                members_count=6,
                skills="Flood Evacuation, Medical Evacuation, Rope Rescue",
                latitude=12.9818,
                longitude=77.6256,
                base_station="Ulsoor Lake Operations Dock",
                contact_number="+91 80 2297 5002",
            ),
            RescueTeam(
                id="TEAM-KSFES-07",
                name="Fire & Emergency Quick Response",
                callsign="Agni-7",
                status="AVAILABLE",
                vehicle_type="High-Clearance 4x4 Rescue Tender",
                members_count=5,
                skills="Submerged Vehicle Extraction, Heavy Pumping",
                latitude=13.0033,
                longitude=77.6966,
                base_station="KR Puram Fire Station",
                contact_number="+91 80 2297 5003",
            ),
            RescueTeam(
                id="TEAM-CIVIL-04",
                name="Bengaluru Civil Defense Disaster Wing",
                callsign="Rakshak-4",
                status="AVAILABLE",
                vehicle_type="All-Terrain Utility Carrier",
                members_count=6,
                skills="Shelter Management, Citizen Evacuation, Food Distribution",
                latitude=12.9352,
                longitude=77.6844,
                base_station="Bellandur Relief Coordination Hub",
                contact_number="+91 80 2297 5004",
            ),
            RescueTeam(
                id="TEAM-MEDIC-01",
                name="Disaster Emergency Medical Unit",
                callsign="Sanjeevani-1",
                status="STANDBY",
                vehicle_type="Mobile Advanced Life Support Ambulance",
                members_count=4,
                skills="Advanced Trauma Care, Hypothermia Treatment, Paramedic",
                latitude=12.9592,
                longitude=77.6534,
                base_station="HAL Airport Emergency Terminal",
                contact_number="+91 80 2297 5005",
            ),
        ]
        db.add_all(teams)

        print("[init_db] Seeding Facilities & Shelters...")
        facilities = [
            Facility(
                id="FAC-HOSP-01",
                name="Bowring & Lady Curzon Hospital",
                facility_type="HOSPITAL",
                address="Lady Curzon Road, Tasker Town, Shivajinagar, Bengaluru",
                latitude=12.9822,
                longitude=77.6044,
                total_capacity=650,
                current_occupancy=412,
                status="OPERATIONAL",
                contact="+91 80 2559 1325",
            ),
            Facility(
                id="FAC-HOSP-02",
                name="Manipal Hospital Old Airport Road",
                facility_type="HOSPITAL",
                address="98, HAL Old Airport Rd, Kodihalli, Bengaluru",
                latitude=12.9587,
                longitude=77.6568,
                total_capacity=450,
                current_occupancy=290,
                status="OPERATIONAL",
                contact="+91 80 2502 4444",
            ),
            Facility(
                id="FAC-SHELTER-01",
                name="KR Puram Community Emergency Shelter",
                facility_type="SHELTER",
                address="Devasandra Main Rd, KR Puram, Bengaluru",
                latitude=13.0076,
                longitude=77.6953,
                total_capacity=300,
                current_occupancy=85,
                status="OPERATIONAL",
                contact="+91 80 2851 2234",
            ),
            Facility(
                id="FAC-SHELTER-02",
                name="Bellandur Multi-Purpose Relief Center",
                facility_type="RELIEF_CAMP",
                address="Near Bellandur Central, Outer Ring Rd, Bengaluru",
                latitude=12.9298,
                longitude=77.6754,
                total_capacity=400,
                current_occupancy=140,
                status="OPERATIONAL",
                contact="+91 80 2574 8891",
            ),
            Facility(
                id="FAC-HQ-01",
                name="Ulsoor Lake Water Rescue Command Post",
                facility_type="RESCUE_HQ",
                address="Sivanchetti Gardens, Ulsoor, Bengaluru",
                latitude=12.9840,
                longitude=77.6210,
                total_capacity=150,
                current_occupancy=35,
                status="OPERATIONAL",
                contact="+91 80 2297 5000",
            ),
            Facility(
                id="FAC-SHELTER-03",
                name="Hebbal Government School Relief Camp",
                facility_type="SHELTER",
                address="Bellary Road, Hebbal, Bengaluru",
                latitude=13.0358,
                longitude=77.5970,
                total_capacity=250,
                current_occupancy=60,
                status="OPERATIONAL",
                contact="+91 80 2362 7711",
            ),
        ]
        db.add_all(facilities)

        print("[init_db] Seeding Volunteers...")
        volunteers = [
            Volunteer(
                id="VOL-101",
                name="Vikram Rao",
                phone="+91 98450 11223",
                email="vikram.rao@rescue.net",
                skills="Certified Swiftwater Swimmer, First Aid CPR",
                area="Indiranagar, Bengaluru",
                is_verified=True,
                status="AVAILABLE",
            ),
            Volunteer(
                id="VOL-102",
                name="Dr. Priya Nambiar",
                phone="+91 98451 22334",
                email="priya.n@health.org",
                skills="Emergency Medical Doctor, Trauma Triage",
                area="HAL / Marathahalli",
                is_verified=True,
                status="AVAILABLE",
            ),
            Volunteer(
                id="VOL-103",
                name="Siddharth Gowda",
                phone="+91 98452 33445",
                email="sid.gowda@mesh.in",
                skills="HAM Radio Operator (VU2XYZ), Drone Recon Pilot",
                area="KR Puram, Bengaluru",
                is_verified=True,
                status="AVAILABLE",
            ),
            Volunteer(
                id="VOL-104",
                name="Amina Khan",
                phone="+91 98453 44556",
                email="amina.k@redcross.org",
                skills="Shelter Logistics, Water Purification, Translation",
                area="Shivajinagar, Bengaluru",
                is_verified=True,
                status="DISPATCHED",
            ),
            Volunteer(
                id="VOL-105",
                name="Karthik Mohan",
                phone="+91 98454 55667",
                email="karthik.m@tech.com",
                skills="Motorboat Driving, Mechanical Repair",
                area="Whitefield, Bengaluru",
                is_verified=False,
                status="AVAILABLE",
            ),
        ]
        db.add_all(volunteers)

        print("[init_db] Seeding Initial Bengaluru Hotspot Incidents...")
        initial_bengaluru_incidents = [
            Incident(
                id="INC-1042",
                title="Severe Inundation at Devasandra Lowlands",
                description="Water level reaching 1.8 meters across ground floor residential dwellings. Elderly residents and children trapped.",
                area="KR Puram, Bengaluru",
                latitude=13.0068,
                longitude=77.6980,
                severity="CRITICAL",
                people_affected=12,
                status="DISPATCHED",
                source="CITIZEN_REPORT",
                data_label="SIMULATED",
                assigned_team_id="TEAM-KSFES-07",
            ),
            Incident(
                id="INC-1041",
                title="Yemalur Overflow Crossing Ring Road",
                description="Bellandur stormwater discharge overflowed culvert near Orchid Enclave. Road impassable, 4 vehicles submerged.",
                area="Marathahalli / Yemalur",
                latitude=12.9482,
                longitude=77.6784,
                severity="HIGH",
                people_affected=8,
                status="ON_SCENE",
                source="CITIZEN_REPORT",
                data_label="SIMULATED",
                assigned_team_id="TEAM-SDRF-02",
            ),
            Incident(
                id="INC-1040",
                title="Rainbow Drive Layout Basement Flooding",
                description="Compound wall breach from storm drain. Multiple basement power substations submerged.",
                area="Bellandur / Sarjapur Rd",
                latitude=12.9231,
                longitude=77.6835,
                severity="HIGH",
                people_affected=5,
                status="VERIFIED",
                source="CITIZEN_REPORT",
                data_label="SIMULATED",
            ),
            Incident(
                id="INC-1039",
                title="Hebbal Flyover Service Lane Waterlogging",
                description="Storm drain backflow causing 0.7m water depth on service lane. Bus stranded.",
                area="Hebbal, Bengaluru",
                latitude=13.0360,
                longitude=77.5960,
                severity="MODERATE",
                people_affected=3,
                status="REPORTED",
                source="CITIZEN_REPORT",
                data_label="SIMULATED",
            ),
            Incident(
                id="INC-1038",
                title="Manyata Tech Park Gate 2 Drain Breach",
                description="Primary stormwater channel backing up towards office park basement car parks.",
                area="Nagavara / Manyata",
                latitude=13.0489,
                longitude=77.6213,
                severity="HIGH",
                people_affected=14,
                status="REPORTED",
                source="CITIZEN_REPORT",
                data_label="SIMULATED",
            ),
        ]
        db.add_all(initial_bengaluru_incidents)

        # Simulated LoRa SOS incidents from the Bengaluru beacon registry.
        # (clean_rescuenet_sos_data.csv has Mumbai coordinates, so it is not used for the map.)
        import random

        rng = random.Random(2026)
        severities = ["CRITICAL", "HIGH", "MODERATE"]
        for bid, name, lat, lon in BENGALURU_HOTSPOTS[:12]:
            trapped = rng.randint(1, 9)
            batt = rng.randint(18, 96)
            hops = rng.randint(1, 5)
            db.add(
                Incident(
                    id=f"INC-LORA-{bid}",
                    title=f"LoRa Mesh SOS from beacon {bid} ({name})",
                    description=f"Mesh beacon relay. Trapped persons: {trapped}. Device battery: {batt}%. Mesh hop distance: {hops}.",
                    area=f"{name}, Bengaluru",
                    latitude=lat,
                    longitude=lon,
                    severity=rng.choice(severities),
                    people_affected=trapped,
                    status="REPORTED",
                    source="MESH_SOS",
                    device_battery_pct=batt,
                    mesh_hops=hops,
                    beacon_id=bid,
                    location_method="GPS",
                    data_label="SIMULATED",
                )
            )
        print("[init_db] Seeded 12 simulated LoRa SOS incidents")

        print("[init_db] Seeding Geo-Targeted Alerts...")
        alerts = [
            Alert(
                id="ALT-2026-01",
                title="Critical Inundation Warning — Bellandur & Varthur Drainage Basin",
                message="Flash flood surge in primary stormwater channels. Low-lying residents in Bellandur, Yamalur, and Rainbow Drive advised to move to upper floors or designated relief centers.",
                severity="CRITICAL",
                area="Bellandur, Bengaluru",
                latitude=12.9352,
                longitude=77.6778,
                radius_km=3.5,
                status="ACTIVE",
                delivery_channel="SIMULATED_CAP_ALERT",
                acknowledged_count=18,
            ),
            Alert(
                id="ALT-2026-02",
                title="High Water Level Alert — KR Puram & Hoodi Environs",
                message="Storm runoff exceeding storm channel capacity by 45%. Sump overflow reported across Devasandra main road.",
                severity="HIGH",
                area="KR Puram, Bengaluru",
                latitude=13.0068,
                longitude=77.6980,
                radius_km=2.8,
                status="ACTIVE",
                delivery_channel="SIMULATED_CAP_ALERT",
                acknowledged_count=12,
            ),
            Alert(
                id="ALT-2026-03",
                title="Weather Warning — Sustained Downpour Forecasted Next 60 Minutes",
                message="IMD Doppler radar indicates continuous 35mm/hr convective cell moving across East Bengaluru corridor.",
                severity="WARNING",
                area="East Bengaluru Corridor",
                latitude=12.9716,
                longitude=77.6412,
                radius_km=5.0,
                status="ACTIVE",
                delivery_channel="SIMULATED_CAP_ALERT",
                acknowledged_count=45,
            ),
        ]
        db.add_all(alerts)

        print("[init_db] Seeding Rescue Records...")
        records = [
            RescueRecord(
                id="REC-2026-001",
                incident_id="INC-1035",
                team_id="TEAM-NDRF-10",
                location="Kaggadasapura Lake Slums",
                people_rescued=18,
                survivors=18,
                missing=0,
                deceased=0,
                severe_injuries=2,
                minor_injuries=5,
                notes="Evacuated 4 families using inflatable boat. Elderly grandmother treated for hypothermia.",
            ),
            RescueRecord(
                id="REC-2026-002",
                incident_id="INC-1036",
                team_id="TEAM-KSFES-07",
                location="Mahadevapura Outer Ring Rd Underpass",
                people_rescued=6,
                survivors=6,
                missing=0,
                deceased=0,
                severe_injuries=0,
                minor_injuries=1,
                notes="Extracted 3 passengers from partially submerged car. Vehicle winched clear of drainage inlet.",
            ),
        ]
        db.add_all(records)

        print("[init_db] Seeding Supervisor Agent Tasks...")
        tasks = [
            SupervisorTask(
                id="TASK-801",
                task_type="TRIAGE",
                title="Multi-Agency Triage: KR Puram Flood Surge",
                status="COMPLETED",
                agent_flow="Supervisor -> Flood Risk Analysis -> Rescue Coordination -> Facility Finder",
                input_summary="Incident INC-1042 reported 12 trapped persons in KR Puram lowland. Water level 1.8m rising.",
                findings="Critical severity confirmed. Water level telemetry 4.2m upstream at Cauvery/Shimsha gauge. Nearest rescue boat at Ulsoor is 8.4 km away; Fire Tender at KR Puram Station is 1.2 km away.",
                recommendations="Immediate dispatch of KSFES Fire Tender (TEAM-KSFES-07). Divert SDRF boat Varuna-2 for backup. Reserve 15 beds at Bowring Hospital emergency triage.",
                requires_human_approval=True,
                approved_by="Incident Commander (OP-01)",
            ),
            SupervisorTask(
                id="TASK-802",
                task_type="ALERT_ASSESSMENT",
                title="Geotargeted Radius Warning for Bellandur Spillway",
                status="COMPLETED",
                agent_flow="Supervisor -> Geospatial Intelligence -> Alert Dispatcher",
                input_summary="Sensor telemetry at Station Hydro 04 crossed 3.9m water level threshold.",
                findings="Estimated 3.5 km radius downstream flood spread impact. 4 relief shelters in zone with 850 combined capacity.",
                recommendations="Publish simulated Level 3 emergency push notification to Bellandur/Yamalur geofence. Pre-alert volunteer drivers.",
                requires_human_approval=False,
                approved_by="Automated AI Threshold Guard",
            ),
        ]
        db.add_all(tasks)

        print("[init_db] Seeding Dataset Registry Metadata...")
        datasets = [
            DatasetRegistry(
                id="DATA-01",
                name="Clean Flood Prediction Telemetry",
                category="SENSOR_TELEMETRY",
                records_count=1000,
                status="INGESTED_AND_TRAINED",
                coverage="STATION_HYDRO_04 (Water Level, Rainfall, Humidity, Temp)",
                description="Cleaned hourly telemetry dataset used to train Random Forest classifier (Accuracy: 100%, ROC-AUC: 1.0).",
            ),
            DatasetRegistry(
                id="DATA-02",
                name="RescueNet LoRa Mesh SOS Ingestion",
                category="CLEAN_SOS",
                records_count=250,
                status="INGESTED",
                coverage="External sample: Mumbai coordinates (latitude 19.0 to 19.1, longitude 72.8 to 72.9)",
                description="Sample multi-hop SOS records (trapped count, battery, hops). Their coordinates are outside Karnataka, so they are kept for reference only; the Bengaluru map uses the simulated 35-beacon registry.",
            ),
            DatasetRegistry(
                id="DATA-03",
                name="IndoFloods River Gauge Network",
                category="INDOFLOODS_GAUGES",
                records_count=214,
                status="ACTIVE_MONITORING",
                coverage="All-India (23 River Gauges in Karnataka across Cauvery/Krishna)",
                description="Warning levels, danger thresholds, river tributaries and geographic coordinates.",
            ),
            DatasetRegistry(
                id="DATA-04",
                name="IndoFloods Historical Flood Events",
                category="HISTORICAL_FLOODS",
                records_count=4548,
                status="INDEXED",
                coverage="Historical flood events across Indian river gauges",
                description="Peak flood levels, discharge volume, flood duration in days.",
            ),
            DatasetRegistry(
                id="DATA-05",
                name="Hydrological Catchments Shapefiles",
                category="SHAPEFILES",
                records_count=775,
                status="PARSED_GEOJSON",
                coverage="Karnataka & National River Catchments (Gauge 361 Shimsha, Gauge 394 Biligundulu)",
                description="ESRI shapefile boundaries converted to GeoJSON for digital-twin GIS layer.",
            ),
            DatasetRegistry(
                id="DATA-06",
                name="Flood Imagery Dataset (Field & Remote Sensing)",
                category="IMAGERY",
                records_count=809,
                status="VERIFIED_ON_DISK",
                coverage="Raw aerial, remote sensing, and ground flood observations (Karnataka & global analog regions)",
                description="809 verified field & remote sensing disaster images (808 unique, 1 byte-duplicate pair) in flood/ directory. Computer vision model not configured.",
            ),
            DatasetRegistry(
                id="DATA-07",
                name="Roboflow Flood Survivor Dataset",
                category="PEOPLE_DETECTION",
                records_count=109,
                status="ARCHIVE_VERIFIED",
                coverage="Survivor, boat, and water hazard bounding-box annotations (Roboflow export)",
                description="109 annotated images with CSV bounding boxes for Person -Flood-, Person -On Boat-, and Person -Safe- classes.",
            ),
        ]
        db.add_all(datasets)

        db.commit()
        print("[init_db] Database seeded successfully!")

    except Exception as e:
        db.rollback()
        print(f"[init_db] Error seeding database: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
