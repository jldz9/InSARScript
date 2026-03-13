import { useState, useRef, useCallback, useMemo, useEffect } from 'react'
import Map from './Map'
import TopBar from './TopBar'
import MapToolbar, { type DrawMode, type Basemap } from './MapToolbar'
import SearchFilters, { type Filters, DEFAULT_FILTERS, hasActiveFilters } from './SearchFilters'
import BasemapSwitcher from './BasemapSwitcher'
import ScenePanel from './ScenePanel'
import StackSceneList from './StackSceneList'
import SceneDetailPanel from './SceneDetailPanel'
import SettingsPanel from './SettingsPanel'
import JobQueueDrawer from './JobQueueDrawer'
import { bboxToWkt, geometryToWkt, getGeometryBbox, type Bbox } from './geoUtils'
import { DARK, LIGHT } from './theme'
import shpjs from 'shpjs'

const API = 'http://localhost:8000'

export default function App() {
  // Theme
  const [isDark, setIsDark] = useState(true)
  const theme = isDark ? DARK : LIGHT

  // Search state
  const [searching,   setSearching]   = useState(false)
  const [resultCount, setResultCount] = useState('')
  const [footprints,  setFootprints]  = useState<GeoJSON.FeatureCollection | null>(null)
  const [_sessionId,  setSessionId]   = useState<string | null>(null)

  // AOI state
  const [aoi,        setAoi]        = useState<Bbox>([-180, -90, 180, 90])
  const [aoiWkt,     setAoiWkt]     = useState<string | null>(null)
  const [aoiGeoJson, setAoiGeoJson] = useState<GeoJSON.Feature | null>(null)

  // Map UI state
  const [drawMode,        setDrawMode]        = useState<DrawMode>(null)
  const [basemap,         setBasemap]         = useState<Basemap>('satellite')
  const [mouseCoords,     setMouseCoords]     = useState<{ lat: number; lng: number } | null>(null)
  const [selectedFeature, setSelectedFeature] = useState<GeoJSON.Feature | null>(null)
  const [stackOpen,       setStackOpen]       = useState(false)
  const [detailScene,     setDetailScene]     = useState<GeoJSON.Feature | null>(null)
  const [workdir,         setWorkdir]         = useState('.')
  const [settingsOpen,    setSettingsOpen]    = useState(false)
  const [jobsOpen,        setJobsOpen]        = useState(false)
  const [downloaderType,    setDownloaderType]    = useState('S1_SLC')
  const [downloaderOptions, setDownloaderOptions] = useState<string[]>(['S1_SLC'])

  // Fetch server settings + available downloaders once on mount
  useEffect(() => {
    fetch(`${API}/api/settings`)
      .then(r => r.json())
      .then(d => { setWorkdir(d.workdir); setDownloaderType(d.downloader) })
      .catch(() => {})
    fetch(`${API}/api/workflows`)
      .then(r => r.json())
      .then(d => { if (d.downloaders) setDownloaderOptions(Object.keys(d.downloaders)) })
      .catch(() => {})
  }, [])

  // Scenes belonging to the same stack as the selected footprint
  const stackScenes = useMemo(() => {
    if (!selectedFeature || !footprints) return []
    const key = selectedFeature.properties?._stack
    return footprints.features.filter(f => f.properties?._stack === key)
  }, [selectedFeature, footprints])

  // Actual date range of the stack (earliest / latest scene acquisition)
  const stackDateRange = useMemo(() => {
    const dates = stackScenes
      .map(f => f.properties?.startTime as string | undefined)
      .filter(Boolean)
      .map(s => s!.slice(0, 10))   // YYYY-MM-DD
      .sort()
    if (!dates.length) return { start: undefined, end: undefined }
    return { start: dates[0], end: dates[dates.length - 1] }
  }, [stackScenes])

  // Filter state
  const [filters,      setFilters]      = useState<Filters>(DEFAULT_FILTERS)
  const [filtersOpen,  setFiltersOpen]  = useState(false)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Polling helper ────────────────────────────────────────────────────────
  const pollJob = useCallback((jobId: string, onDone: (data: any) => void) => {
    pollRef.current = setInterval(async () => {
      const res = await fetch(`${API}/api/jobs/${jobId}`)
      const job = await res.json()
      if (job.status === 'done' || job.status === 'error') {
        clearInterval(pollRef.current!)
        setSearching(false)
        if (job.status === 'done') onDone(job.data)
        else setResultCount(`Error: ${job.message}`)
      }
    }, 1500)
  }, [])

  // ── Search ────────────────────────────────────────────────────────────────
  async function handleSearch() {
    if (!filters.startDate || !filters.endDate) {
      setResultCount('Set start and end dates in Filters')
      setFiltersOpen(true)
      return
    }
    setSearching(true)
    setDrawMode(null)
    setResultCount('Searching…')

    const wkt = aoiWkt ?? bboxToWkt(aoi)

    const res = await fetch(`${API}/api/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        west: aoi[0], south: aoi[1], east: aoi[2], north: aoi[3],
        wkt, start: filters.startDate, end: filters.endDate,
        maxResults:      filters.maxResults ? parseInt(filters.maxResults) : 2000,
        flightDirection: filters.flightDirection  || null,
        pathStart:       filters.pathStart  ? parseInt(filters.pathStart)  : null,
        pathEnd:         filters.pathEnd    ? parseInt(filters.pathEnd)    : null,
        frameStart:      filters.frameStart ? parseInt(filters.frameStart) : null,
        frameEnd:        filters.frameEnd   ? parseInt(filters.frameEnd)   : null,
      }),
    })
    const { job_id } = await res.json()
    pollJob(job_id, (data) => {
      setResultCount(data.summary)
      setFootprints(data.geojson)
      setSessionId(data.session_id)
    })
  }

  // ── AOI drawn on map ──────────────────────────────────────────────────────
  function handleAoiDrawn(wkt: string, bbox: Bbox, feature?: GeoJSON.Feature) {
    setAoiWkt(wkt)
    setAoi(bbox)
    setAoiGeoJson(feature ?? null)
    setDrawMode(null)
  }

  function handleAoiWktChange(wkt: string | null) {
    setAoiWkt(wkt)
    setAoiGeoJson(null)
  }

  function handleClearAoi() {
    setAoiWkt(null)
    setAoiGeoJson(null)
    setAoi([-180, -90, 180, 90])
  }

  // ── Shapefile upload ──────────────────────────────────────────────────────
  async function handleShapefileUpload(file: File) {
    try {
      const ext    = file.name.split('.').pop()?.toLowerCase()
      const buffer = await file.arrayBuffer()
      let feature: GeoJSON.Feature | undefined

      if (ext === 'gpkg') {
        // Backend parses GeoPackage via geopandas (base64 JSON — no multipart needed)
        const b64 = btoa(String.fromCharCode(...new Uint8Array(buffer)))
        const res = await fetch(`${API}/api/parse-aoi`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: file.name, data: b64 }),
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }))
          setResultCount(`GeoPackage error: ${err.detail}`)
          return
        }
        const { feature: f } = await res.json()
        feature = f
      } else {
        const geojson = await shpjs(buffer)
        const fc      = Array.isArray(geojson) ? geojson[0] : geojson
        feature = fc.features[0]
      }

      if (!feature) { setResultCount('No features found in file'); return }
      const wkt  = geometryToWkt(feature.geometry)
      const bbox = getGeometryBbox(feature.geometry)
      handleAoiDrawn(wkt, bbox, feature)   // pass feature → polygon shape preserved
    } catch (err) {
      setResultCount(`File error: ${err}`)
    }
  }

  return (
    <div style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden' }}>

      <TopBar
        downloaderType={downloaderType}
        downloaderOptions={downloaderOptions}
        onDownloaderTypeChange={setDownloaderType}
        aoiWkt={aoiWkt}
        onAoiWktChange={handleAoiWktChange}
        startDate={filters.startDate}
        endDate={filters.endDate}
        onDatesChange={(s, e) => setFilters(f => ({ ...f, startDate: s, endDate: e }))}
        onSearch={() => handleSearch()}
        searching={searching}
        resultCount={resultCount}
        theme={theme}
        onThemeToggle={() => {
          setIsDark(d => {
            const next = !d
            setBasemap(next ? 'satellite' : 'osm')
            return next
          })
        }}
        onFiltersOpen={() => setFiltersOpen(true)}
        hasActiveFilters={hasActiveFilters(filters)}
        onJobsOpen={() => setJobsOpen(o => !o)}
        jobsOpen={jobsOpen}
        onSettingsOpen={() => setSettingsOpen(true)}
      />

      <MapToolbar
        drawMode={drawMode}
        onDrawModeChange={setDrawMode}
        onClearAoi={handleClearAoi}
        onShapefileUpload={handleShapefileUpload}
        mouseCoords={mouseCoords}
        theme={theme}
      />

      {/* Map */}
      <div style={{ position: 'absolute', top: 84, left: 0, right: 0, bottom: 0 }}>
        <Map
          footprints={footprints}
          aoi={aoi}
          aoiGeojson={aoiGeoJson}
          drawMode={drawMode}
          basemap={basemap}
          footprintOpacity={0.5}
          onAoiDrawn={handleAoiDrawn}
          onMouseMove={setMouseCoords}
          onFootprintClick={setSelectedFeature}
        />
        <BasemapSwitcher
          basemap={basemap}
          onBasemapChange={setBasemap}
          theme={theme}
        />
      </div>

      {/* Cascading scene panels — L3 · L2 · L1 (left to right) */}
      {selectedFeature && (
        <div style={{
          position: 'absolute', top: 84, right: 0, bottom: 0,
          display: 'flex', flexDirection: 'row', zIndex: 110,
        }}>
          {detailScene && (
            <SceneDetailPanel
              feature={detailScene}
              theme={theme}
              workdir={workdir}
              onClose={() => setDetailScene(null)}
            />
          )}
          {stackOpen && (
            <StackSceneList
              stackKey={selectedFeature.properties?._stack ?? ''}
              scenes={stackScenes}
              theme={theme}
              selectedScene={detailScene}
              onClose={() => { setStackOpen(false); setDetailScene(null) }}
              onSceneClick={setDetailScene}
            />
          )}
          <ScenePanel
            feature={selectedFeature}
            theme={theme}
            stackStart={stackDateRange.start}
            stackEnd={stackDateRange.end}
            stackCount={stackScenes.length}
            stackUrls={stackScenes.map(f => f.properties?.url).filter(Boolean)}
            workdir={workdir}
            aoiWkt={aoiWkt}
            downloaderType={downloaderType}
            stackOpen={stackOpen}
            onClose={() => { setSelectedFeature(null); setStackOpen(false); setDetailScene(null) }}
            onStackClick={() => { setStackOpen(o => !o); setDetailScene(null) }}
          />
        </div>
      )}

      {/* Job queue drawer */}
      {jobsOpen && (
        <JobQueueDrawer
          theme={theme}
          workdir={workdir}
          onClose={() => setJobsOpen(false)}
        />
      )}

      {/* Settings panel */}
      {settingsOpen && (
        <SettingsPanel
          theme={theme}
          downloaderType={downloaderType}
          onDownloaderTypeChange={setDownloaderType}
          startDate={filters.startDate}
          endDate={filters.endDate}
          aoiWkt={aoiWkt}
          onDatesChange={(s, e) => setFilters(f => ({ ...f, startDate: s, endDate: e }))}
          onAoiWktChange={handleAoiWktChange}
          onClose={() => {
            setSettingsOpen(false)
            fetch(`${API}/api/settings`).then(r => r.json()).then(d => { setWorkdir(d.workdir); setDownloaderType(d.downloader) }).catch(() => {})
          }}
        />
      )}

      {/* Filter panel — mounts fresh each open so draft resets */}
      {filtersOpen && (
        <SearchFilters
          open={filtersOpen}
          filters={filters}
          theme={theme}
          onClose={() => setFiltersOpen(false)}
          onApply={setFilters}
        />
      )}

    </div>
  )
}