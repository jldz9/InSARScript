// Geometry utilities — WKT conversion and bbox extraction

export type Bbox = [number, number, number, number]  // [west, south, east, north]

export function geometryToWkt(geometry: GeoJSON.Geometry): string {
  if (geometry.type === 'Point') {
    const [lng, lat] = geometry.coordinates as number[]
    return `POINT (${lng} ${lat})`
  }
  if (geometry.type === 'Polygon') {
    const rings = (geometry.coordinates as number[][][]).map(ring =>
      ring.map(([lng, lat]) => `${lng} ${lat}`).join(', ')
    )
    return `POLYGON ((${rings.join('), (')}))`
  }
  if (geometry.type === 'MultiPolygon') {
    // Use first polygon
    const rings = (geometry.coordinates as number[][][][])[0].map(ring =>
      ring.map(([lng, lat]) => `${lng} ${lat}`).join(', ')
    )
    return `POLYGON ((${rings.join('), (')}))`
  }
  throw new Error(`Unsupported geometry type: ${geometry.type}`)
}

export function bboxToWkt([w, s, e, n]: Bbox): string {
  return `POLYGON ((${w} ${s}, ${e} ${s}, ${e} ${n}, ${w} ${n}, ${w} ${s}))`
}

export function getGeometryBbox(geometry: GeoJSON.Geometry): Bbox {
  let coords: number[][] = []
  if (geometry.type === 'Point') {
    coords = [geometry.coordinates as number[]]
  } else if (geometry.type === 'Polygon') {
    coords = (geometry.coordinates as number[][][])[0]
  } else if (geometry.type === 'MultiPolygon') {
    coords = (geometry.coordinates as number[][][][]).flat(2)
  }
  const lngs = coords.map(c => c[0])
  const lats  = coords.map(c => c[1])
  return [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)]
}