/* 
Edmonton Road-Corridor Vegetation Change
Validates an uploaded 15 m road-buffer asset and calculates summer Sentinel-2 NDVI change between 2020 to 2025.


Workflow:
1. Load and validate the road-buffer asset.
2. Load Sentinel-2 Surface Reflectance imagery.
3. Filter imagery by location, date, and cloud cover.
4. Mask cloudy pixels using Sentinel-2 Cloud Probability.
5. Calculate NDVI for each image.
6. Create summer NDVI composites for two comparison years.
7. Calculate NDVI change between the two years.
8. Calculate mean NDVI and NDVI change for each road corridor.
9. Export road-level results for Python post-processing.
*/



// Configuration
var START_YEAR = 2020;
var END_YEAR = 2025;

var SUMMER_START_MONTH = 6;
var SUMMER_END_MONTH = 9;

var MAX_CLOUD_PERCENT = 20;
var MAX_CLOUD_PROBABILITY = 40;


var ROAD_BUFFER_ASSET =
    'projects/selected_project/assets/edmonton_road_buffers';




// Load and validate road-buffer asset
var roadBuffers = ee.FeatureCollection(ROAD_BUFFER_ASSET);

print('Road buffer count:', roadBuffers.size());
print('First road buffer:', roadBuffers.first());
print('Property names:', roadBuffers.first().propertyNames());

print(
  'First geometry centroid:',
  roadBuffers
    .first()
    .geometry()
    .centroid()
    .coordinates());

print('Collection bounds:', roadBuffers.geometry().bounds(1));


// Map preview
Map.centerObject(roadBuffers, 10);
Map.addLayer(roadBuffers, {color: 'red'}, 'Edmonton road buffers');





// Study area & date ranges
// Summer period: June 1 through August 31
var studyArea = roadBuffers.geometry().bounds();

var startYear_startDate = ee.Date.fromYMD(START_YEAR, SUMMER_START_MONTH, 1);
var startYear_endDate = ee.Date.fromYMD(START_YEAR, SUMMER_END_MONTH, 1);

var endYear_startDate = ee.Date.fromYMD(END_YEAR, SUMMER_START_MONTH, 1);
var endYear_endDate = ee.Date.fromYMD(END_YEAR, SUMMER_END_MONTH, 1);


print('Start-year date range:', startYear_startDate, startYear_endDate);
print('End-year date range:', endYear_startDate, endYear_endDate);




// Sentinel-2 source collections
var sentinel2_SurfaceRef = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED');
var sentinel2_CloudPro = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY');





// Processing functions
function maskClouds(image) {
  var cloud_Probability_Image = ee.Image(
    image.get('cloud_probability'));


  var cloud_Probability = cloud_Probability_Image.select('probability');
  var clear_SkyMask = cloud_Probability.lt(MAX_CLOUD_PROBABILITY);


  return image
    .updateMask(clear_SkyMask)
    .copyProperties(image, ['system:time_start']);}





// NDVI function = (B8 - B4) / (B8 + B4)
function addNdvi(image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');

  return image
    .addBands(ndvi)
    .copyProperties(image, ['system:time_start']);}





// Prepare one summer Sentinel-2 collection
function summer_collection(startDate, endDate) {
  var surface_Reflectance = sentinel2_SurfaceRef
    .filterBounds(studyArea)
    .filterDate(startDate, endDate)
    .filter(
      ee.Filter.lt(
        'CLOUDY_PIXEL_PERCENTAGE',
        MAX_CLOUD_PERCENT));


  var cloud_Probability = sentinel2_CloudPro
    .filterBounds(studyArea)
    .filterDate(startDate, endDate);


  var joined_Collection = ee.Join.saveFirst('cloud_probability').apply({
    primary: surface_Reflectance,
    secondary: cloud_Probability,
    condition: ee.Filter.equals({
      leftField: 'system:index',
      rightField: 'system:index'
    })
  });


  return ee.ImageCollection(joined_Collection)
    .filter(
      ee.Filter.notNull(['cloud_probability']))
    .map(maskClouds)
    .map(addNdvi)}





// Prepare summer collections
var startYear_Collection = summer_collection(startYear_startDate, startYear_endDate);
var endYear_Collection = summer_collection(endYear_startDate, endYear_endDate);


print(START_YEAR + ' image count:', startYear_Collection.size());
print(END_YEAR + ' image count:', endYear_Collection.size());





// Create summer NDVI composites
var startYear_Ndvi = startYear_Collection
  .select('NDVI')
  .median()
  .clip(studyArea)
  .rename('NDVI_' + START_YEAR);

var endYear_Ndvi = endYear_Collection
  .select('NDVI')
  .median()
  .clip(studyArea)
  .rename('NDVI_' + END_YEAR);


print(START_YEAR + 'NDVI composite:', startYear_Ndvi);
print(END_YEAR + 'NDVI composite:',endYear_Ndvi);





// NDVI visualization
var ndvi_Visual = {
  min: -0.2,
  max: 0.8,
  palette: [
    'brown',
    'yellow',
    'lightgreen',
    'green',
    'darkgreen'
  ]};

Map.addLayer(startYear_Ndvi, ndvi_Visual, START_YEAR + 'summer NDVI');
Map.addLayer(endYear_Ndvi, ndvi_Visual, END_YEAR + 'summer NDVI');





// Calculate NDVI change
var ndvi_change = endYear_Ndvi.subtract(startYear_Ndvi).rename('ndvi_change');
print('NDVI change image:', ndvi_change);


var ndviChange_Visualization = {
    min: -0.3,
    max: 0.3,
    palette: [
        'darkred',
        'red',
        'white',
        'lightgreen',
        'darkgreen']};


Map.addLayer(ndvi_change, ndviChange_Visualization,
  END_YEAR + ' minus ' + START_YEAR + ' NDVI change');







// Calculate road-level NDVI statistics
var ndvi_Sta_Image = startYear_Ndvi.rename('ndvi_' + START_YEAR)
    .addBands(endYear_Ndvi.rename('ndvi_' + END_YEAR)).addBands(ndvi_change);

print('NDVI statistics bands:', ndvi_Sta_Image.bandNames());




var road_Ndvi_Sta = ndvi_Sta_Image.reduceRegions({
    collection: roadBuffers,
    reducer: ee.Reducer.mean(),
    scale: 10,
    tileScale: 4});

print('Road-level NDVI statistics:', road_Ndvi_Sta.limit(5));
print('First road with NDVI statistics:', road_Ndvi_Sta.first());
print('Output property names:', road_Ndvi_Sta.first().propertyNames());





// Export road-corridor results to Google Drive
Export.table.toDrive({
    collection: road_Ndvi_Sta,
    description: 'edmonton_road_ndvi_change_2020_2025',
    folder: 'GEE_Exports',
    fileNamePrefix: 'edmonton_road_ndvi_change_2020_2025',
    fileFormat: 'GeoJSON'});
