import gpxpy
import gpxpy.gpx

def parse_garmin_gpx(file_path):
    """
    Parses a Garmin GPX file, handling missing timestamps and 
    extracting standard coordinates, elevations, and extension metrics.
    """
    with open(file_path, 'r', encoding='utf-8') as gpx_file:
        try:
            gpx = gpxpy.parse(gpx_file)
        except Exception as e:
            raise ValueError(f"Failed to parse GPX XML structure: {e}")

    parsed_points = []
    
    # Process tracks (and routes if your files include them)
    all_segments = []
    for track in gpx.tracks:
        all_segments.extend(track.segments)
    
    # Fallback if the file is structured as a route rather than a track
    if not all_segments and gpx.routes:
        # Convert route points into a pseudo-segment structure for uniform handling
        class PseudoSegment:
            def __init__(self, points):
                self.points = points
        all_segments = [PseudoSegment(route.points) for route in gpx.routes]

    for segment in all_segments:
        for point in segment.points:
            # Handle missing timestamps gracefully (common in Garmin Course files)
            point_time = point.time.isoformat() if point.time else None
            
            point_record = {
                'latitude': point.latitude,
                'longitude': point.longitude,
                'elevation': point.elevation,
                'time': point_time
            }
            
            # Safely extract Garmin TrackPoint Extensions (e.g., HR, Cadence, Power)
            if point.extensions:
                for extension in point.extensions:
                    for child in extension:
                        # Strip XML namespace URI to get clean keys (e.g., 'hr', 'cad', 'power')
                        tag_name = child.tag.split('}')[-1]
                        point_record[tag_name] = child.text
                        
            parsed_points.append(point_record)
            
    return parsed_points
