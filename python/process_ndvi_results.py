"""
Edmonton Road-Corridor Vegetation Change
Process Google Earth Engine road-level NDVI results

This script:
1. Reads the GeoJSON exported from Google Earth Engine.
2. Checks required fields, geometry, and NDVI values.
3. Classifies into five classes.
4. Removes unnecessary Google Earth Engine system IDs from CSV outputs.
5. Creates Top 10 increase and decrease ranking CSV tables.
6. Reprojects the final spatial results for ArcGIS Pro.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd



# Configuration
TARGET_CRS = "EPSG:32612"

CHANGE_BREAK_1 = 0.03
CHANGE_BREAK_2 = 0.08

TOP_N = 10

PROJECT_FOLDER = Path(__file__).resolve().parent.parent
DATA_FOLDER = PROJECT_FOLDER / "data"
OUTPUTS_FOLDER = PROJECT_FOLDER / "outputs"

DATA_FOLDER.mkdir(exist_ok=True)
OUTPUTS_FOLDER.mkdir(exist_ok=True)

INPUT_PATH = DATA_FOLDER / "edmonton_road_ndvi_change_2020_2025.geojson"
PROCESSED_OUTPUT_PATH = OUTPUTS_FOLDER / "edmonton_road_ndvi_results.gpkg"

TOP_INCREASES_OUTPUT_PATH = OUTPUTS_FOLDER / "top_10_ndvi_increases.csv"
TOP_DECREASES_OUTPUT_PATH = OUTPUTS_FOLDER / "top_10_ndvi_decreases.csv"


REQUIRED_FIELDS = [
    "road_uid",
    "street_nam",
    "length_m",
    "buffer_m",
    "ndvi_2020",
    "ndvi_2025",
    "ndvi_change",
    "geometry",
]



# Read and validate GEE results
print("\n--- Reading GEE Road-Level NDVI Results ---")

road_ndvi = gpd.read_file(INPUT_PATH)

print(f"Feature count: {len(road_ndvi):,}")
print(f"Input CRS: {road_ndvi.crs}")


missing_fields = [field for field in REQUIRED_FIELDS if field not in road_ndvi.columns]

if missing_fields:
    raise ValueError(
        "Missing required fields: "
        + ", ".join(missing_fields))


missing_geometry_count = int(
    road_ndvi.geometry.isna().sum()
    + road_ndvi.geometry.is_empty.sum())


missing_ndvi_count = int(
    road_ndvi[["ndvi_2020", "ndvi_2025", "ndvi_change"]]
    .isna()
    .any(axis=1)
    .sum())


print(f"Missing geometries: {missing_geometry_count:,}")
print(f"Rows with missing NDVI: {missing_ndvi_count:,}")





# Classify NDVI change
# Direction is kept as a simple sign-based field for quick filtering.
# The five-class field below is the one used for map symbology.
road_ndvi["change_direction"] = np.select(
    [road_ndvi["ndvi_change"] < 0,
     road_ndvi["ndvi_change"] > 0,
    ],
    ["Decrease",
     "Increase",],
    default = "No change")





# Classify NDVI change for mapping
"""
These thresholds are project-specific interpretation breaks.
They were chosen to separate small corridor-level changes from more noticeable NDVI differences.
"""
classification_bins = [
    -np.inf,
    -CHANGE_BREAK_2,
    -CHANGE_BREAK_1,
    CHANGE_BREAK_1,
    CHANGE_BREAK_2,
    np.inf,
]

classification_labels = [
    "Strong decrease",
    "Moderate decrease",
    "Little or no change",
    "Moderate increase",
    "Strong increase",
]

road_ndvi["change_class"] = pd.cut(
    road_ndvi["ndvi_change"],
    bins=classification_bins,
    labels=classification_labels,
    include_lowest=True,
    right=True,
)


print("\n--- NDVI Change Classification ---")

class_counts = road_ndvi["change_class"].value_counts(sort=False)

for class_name, count in class_counts.items():
    percentage = count / len(road_ndvi) * 100

    print(
        f"{class_name}: "
        f"{count:,} corridors "
        f"({percentage:.1f}%)"
    )




# Create Top 10 ranking tables
# Rankings are based on the corridor mean NDVI change exported from GEE.
# They identify the largest positive and negative corridor averages; they do
# not mean every location along that road changed by the same amount.
top_increases = (road_ndvi.loc[road_ndvi["ndvi_change"] > 0]
                 .sort_values("ndvi_change", ascending = False).head(TOP_N).copy())

top_decreases = (road_ndvi.loc[road_ndvi["ndvi_change"] < 0]
                 .sort_values("ndvi_change", ascending = True, ).head(TOP_N).copy())


top_increases.insert(0, "rank", range(1, len(top_increases) + 1))
top_decreases.insert(0, "rank", range(1, len(top_decreases) + 1))




# Convert categorical mapping class to text
road_ndvi["change_class"] = (road_ndvi["change_class"].astype(str))







# Save final spatial results
# The GeoJSON exported from GEE is read as EPSG:4326.
# Reproject it back to the Edmonton project CRS for the final ArcGIS Pro output.
print("\n--- Saving Final GeoPackage ---")

road_ndvi = road_ndvi.to_crs(TARGET_CRS)
print(f"Output CRS: {road_ndvi.crs}")

road_ndvi.to_file(PROCESSED_OUTPUT_PATH, layer = "road_ndvi_results", driver = "GPKG")
print(f"Saved to:\n{PROCESSED_OUTPUT_PATH}")






# Save Top 10 ranking tables
print("\n--- Saving Top 10 Ranking Tables ---")


gee_system_fields = [field for field in [
        "system:index",
        "system_index",
        "system_id"]
    if field in road_ndvi.columns]


top_increases_table = top_increases.drop(
    columns=[top_increases.geometry.name, *[field for field in gee_system_fields
            if field in top_increases.columns
        ],
    ], errors="ignore")


top_decreases_table = top_decreases.drop(
    columns=[top_decreases.geometry.name, *[field for field in gee_system_fields
            if field in top_decreases.columns
        ],
    ],
    errors="ignore")


top_increases_table.to_csv(TOP_INCREASES_OUTPUT_PATH, index = False)
top_decreases_table.to_csv(TOP_DECREASES_OUTPUT_PATH, index = False)

print(f"Top 10 increases saved to:\n{TOP_INCREASES_OUTPUT_PATH}")
print(f"Top 10 decreases saved to:\n{TOP_DECREASES_OUTPUT_PATH}")
