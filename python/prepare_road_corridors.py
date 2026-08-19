"""
Edmonton Road-Corridor Vegetation Change road data preparation for Google Earth Engine

This script:
1. Downloads Edmonton's public road-network data.
2. Cleans and projects the road geometries.
3. Selects eligible arterial road segments.
4. Dissolves segments by street name to create road corridors.
5. Creates 15 m road buffers.
6. Exports a zipped Shapefile for Google Earth Engine.
"""

from pathlib import Path
import shutil
import tempfile
import geopandas as gpd
import requests




# Configuration
BASE_URL = "https://data.edmonton.ca/resource"
DATASET_ID = "9j8t-zm52"

TARGET_CRS = "EPSG:32612"
BUFFER_DISTANCE_M = 15

PROJECT_FOLDER = Path(__file__).resolve().parent.parent
DATA_FOLDER = PROJECT_FOLDER / "data"
OUTPUTS_FOLDER = PROJECT_FOLDER / "outputs"

DATA_FOLDER.mkdir(exist_ok = True)
OUTPUTS_FOLDER.mkdir(exist_ok = True)

RAW_ROADS_PATH = DATA_FOLDER / "edmonton_road_network_raw.gpkg"
CLEAN_ROADS_PATH = DATA_FOLDER / "edmonton_road_network_clean.gpkg"
PREPARED_ROADS_PATH = DATA_FOLDER / "edmonton_arterial_roads_prepared.gpkg"
BUFFER_PATH = DATA_FOLDER / "edmonton_road_buffers.gpkg"
GEE_ZIP_PATH = OUTPUTS_FOLDER / "edmonton_road_buffers_gee.zip"


REQUIRED_FIELDS = [
    "centerlineid",
    "street_name_full",
    "centerline_type",
    "functional_class_code",
    "responsible_party_description"]


ARTERIAL_CLASSES = [
    "Arterial-Class C (Truck Route, Low speeds)",
    "Arterial-Class D (Non-Truck Route, Low speeds)"]






# Download Edmonton road network
def get_record_count(dataset_id):
    count_url = f"{BASE_URL}/{dataset_id}.json?$select=count(*)"
    response = requests.get(count_url, timeout=60)
    response.raise_for_status()
    return int(response.json()[0]["count"])


def download_road_network(dataset_id):
    record_count = get_record_count(dataset_id)

    data_url = (
        f"{BASE_URL}/{dataset_id}.geojson"
        f"?$limit={record_count}")


    roads = gpd.read_file(data_url)
    print(f"Records available from API: {record_count:,}")
    print(f"Rows downloaded: {len(roads):,}")
    print(f"Source CRS: {roads.crs}")


    if len(roads) != record_count:
        print("WARNING: Row count does not match.")
    return roads


print("\n--- Downloading Edmonton Road Network ---")
roads_raw = download_road_network(DATASET_ID)

roads_raw.to_file(RAW_ROADS_PATH, layer = "road_network_raw", driver = "GPKG")
print(f"Raw road network saved to:\n{RAW_ROADS_PATH}")






# Clean and project road network
print("\n--- Cleaning Road Network ---")

missing_fields = [
    field for field in REQUIRED_FIELDS
    if field not in roads_raw.columns]


if missing_fields:
    raise ValueError(
        "Required fields are missing: "
        + ", ".join(missing_fields))


if roads_raw.crs is None:
    raise ValueError("Source CRS is undefined.")




# Remove null and empty geometries
roads_clean = roads_raw[
    roads_raw.geometry.notna()
    & ~roads_raw.geometry.is_empty
].copy()

removed_geometry_count = len(roads_raw) - len(roads_clean)
print(f"Removed null/empty geometries: {removed_geometry_count:,}")



# Repair invalid geometries if needed
invalid_geometry_count = int((~roads_clean.geometry.is_valid).sum())

if invalid_geometry_count > 0:
    roads_clean["geometry"] = roads_clean.geometry.make_valid()

invalid_after_repair = int((~roads_clean.geometry.is_valid).sum())

print(f"Invalid geometries found: {invalid_geometry_count:,}")
print(f"Invalid geometries remaining: {invalid_after_repair:,}")






# Project to UTM Zone 12N for distance and buffer calculations
# Buffers are created in the projected CRS, so the distance is measured in metres.
roads_clean = roads_clean.to_crs(TARGET_CRS)
roads_clean["length_m"] = roads_clean.geometry.length
zero_length_count = int((roads_clean["length_m"] <= 0).sum())
roads_clean = roads_clean[roads_clean["length_m"] > 0].copy()

print(f"Removed zero-length geometries: {zero_length_count:,}")
print(f"Clean road segments: {len(roads_clean):,}")
print(f"Projected CRS: {roads_clean.crs}")







# Basic source-ID QA
null_id_count = int(roads_clean["centerlineid"].isna().sum())
duplicate_id_count = int(roads_clean["centerlineid"].duplicated().sum())

if null_id_count > 0:
    raise ValueError(
        f"{null_id_count:,} null centerline IDs found.")

if duplicate_id_count > 0:
    raise ValueError(
        f"{duplicate_id_count:,} duplicate centerline IDs found.")


roads_clean.to_file(
    CLEAN_ROADS_PATH,
    layer="road_network_clean",
    driver="GPKG")

print(f"Clean road network saved to:\n{CLEAN_ROADS_PATH}")







# Select and dissolve arterial road corridors
print("\n--- Preparing Road Corridors ---")

selected_roads = roads_clean[
    roads_clean["street_name_full"].notna()
    & (roads_clean["centerline_type"] == "Road")
    & (
        roads_clean["responsible_party_description"]
        == "City of Edmonton"
    )
    & roads_clean["functional_class_code"].isin(ARTERIAL_CLASSES)
].copy()

print(f"Selected arterial road segments: {len(selected_roads):,}")





"""
- Keep only the road name and geometry before dissolve.
- Segment-level attributes are removed because they may no longer 
    describe the combined road corridor after dissolving.
- All segments with the same street name are grouped into one corridor,
    including sections that are not spatially connected.
"""

selected_roads = selected_roads[["street_name_full", "geometry"]].copy()

prepared_roads = selected_roads.dissolve(
    by = "street_name_full",
    as_index = False)


prepared_roads["road_uid"] = range(1, len(prepared_roads) + 1)
prepared_roads["length_m"] = prepared_roads.geometry.length

print(f"Prepared road corridors: {len(prepared_roads):,}")


prepared_roads.to_file(PREPARED_ROADS_PATH, layer = "arterial_roads", driver = "GPKG")

print(f"Prepared corridors saved to:\n{PREPARED_ROADS_PATH}")






# Create 15 m road buffers
print("\n--- Creating Road Buffers ---")

road_buffers = prepared_roads.copy()
road_buffers["geometry"] = road_buffers.geometry.buffer(BUFFER_DISTANCE_M)
road_buffers["buffer_m"] = BUFFER_DISTANCE_M

print(f"Buffer distance: {BUFFER_DISTANCE_M} m")
print(f"Buffers created: {len(road_buffers):,}")


road_buffers.to_file(BUFFER_PATH, layer = "road_buffers", driver = "GPKG")

print(f"Projected buffers saved to:\n{BUFFER_PATH}")






# Export Google Earth Engine input
print("\n--- Exporting GEE Input ---")

gee_buffers = road_buffers[
    [
        "road_uid",
        "street_name_full",
        "length_m",
        "buffer_m",
        "geometry",
    ]
].copy()




# CSV was tested first, but it was not reliable for preserving the road-buffer
# geometry during the GEE upload. A zipped Shapefile was used instead.
with tempfile.TemporaryDirectory() as temp_folder:
    temp_shapefile = (Path(temp_folder) / "edmonton_road_buffers_gee.shp")
    gee_buffers.to_file(temp_shapefile, driver = "ESRI Shapefile", encoding = "utf-8")


    if GEE_ZIP_PATH.exists():
        GEE_ZIP_PATH.unlink()

    shutil.make_archive(
        base_name=str(GEE_ZIP_PATH.with_suffix("")),
        format="zip",
        root_dir=temp_folder)


print(f"GEE upload file saved to:\n{GEE_ZIP_PATH}")
