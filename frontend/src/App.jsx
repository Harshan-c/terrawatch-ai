import React, { useMemo, useState } from 'react';
import { Satellite, Upload, ScanSearch, FileDown, ShieldCheck, Activity, Image as ImageIcon, AlertTriangle, CheckCircle2, LoaderCircle, ArrowRight, Sparkles } from 'lucide-react';

// Use the deployed backend on Vercel, with localhost as the development fallback.
const API = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

function formatBytes(bytes) {
  if (!bytes) return '';
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(0)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function ImageDrop({ label, file, setFile, hint }) {
  const [drag, setDrag] = useState(false);
  const choose = (f) => { if (f && f.type.startsWith('image/')) setFile(f); };
  return <div className={`drop-card ${drag ? 'dragging' : ''}`}
    onDragOver={e => { e.preventDefault(); setDrag(true); }}
    onDragLeave={() => setDrag(false)}
    onDrop={e => { e.preventDefault(); setDrag(false); choose(e.dataTransfer.files?.[0]); }}>
    <div className="drop-top"><span className="step-dot">{label.startsWith('01') ? '01' : '02'}</span><span className="drop-label">{label.slice(3)}</span></div>
    <label className="drop-zone">
      {file ? <img className="upload-preview" src={URL.createObjectURL(file)} alt={label} /> : <div className="upload-empty"><div className="upload-icon"><Upload size={22}/></div><strong>Drop image here</strong><span>or click to browse</span><small>JPG, PNG, WEBP</small></div>}
      <input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => choose(e.target.files?.[0])} />
    </label>
    <div className="file-meta"><span>{file ? file.name : hint}</span><span>{file ? formatBytes(file.size) : 'No file selected'}</span></div>
  </div>;
}

export default function App() {
  const [before, setBefore] = useState(null);
  const [after, setAfter] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [view, setView] = useState('overlay');
  const [health, setHealth] = useState('checking');

  React.useEffect(() => {
    fetch(`${API}/health`).then(r => r.ok ? setHealth('online') : setHealth('offline')).catch(() => setHealth('offline'));
  }, []);

  const canAnalyze = before && after && !busy;
  const downloadReport = () => {
    if (!result?.report) return;
    const blob = new Blob([JSON.stringify(result.report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'terrawatch-change-report.json'; a.click();
    URL.revokeObjectURL(url);
  };
  const analyze = async () => {
    setBusy(true); setError(''); setResult(null);
    try {
      const form = new FormData();
      form.append('before', before); form.append('after', after);
      const res = await fetch(`${API}/analyze`, { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Analysis failed');
      setResult(data); setView('overlay');
    } catch (e) {
      setError(`${e.message}. Check that the backend is running at ${API}.`);
    } finally { setBusy(false); }
  };

  const activeImage = result ? ({ overlay: result.overlay, before: result.before_preview, after: result.after_preview, mask: result.mask }[view]) : null;
  const stats = result?.stats;

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Satellite size={21}/></div><div><b>TerraWatch<span> AI</span></b><small>EARTH OBSERVATION</small></div></div>
      <div className="side-section">WORKSPACE</div>
      <div className="nav-item active"><ScanSearch size={17}/><span>Change Detection</span><span className="nav-pill">01</span></div>
      <div className="nav-item muted"><Activity size={17}/><span>Analysis History</span></div>
      <div className="side-bottom"><div className="status-indicator"><span className={`status-dot ${health}`}></span><div><b>Analysis engine</b><small>{health === 'online' ? 'API connected' : health === 'checking' ? 'Connecting…' : 'Backend offline'}</small></div></div><div className="sidebar-note">HACKATHON PROTOTYPE<br/>v1.0.0 · LOCAL ENVIRONMENT</div></div>
    </aside>

    <main className="main">
      <header className="topbar"><div className="breadcrumb">Workspace <span>/</span> <b>Change Detection</b></div><div className="top-right"><span className="live-chip"><span></span> LIVE WORKSPACE</span><div className="avatar">TW</div></div></header>
      <section className="hero">
        <div className="hero-copy"><div className="eyebrow"><Sparkles size={13}/> SATELLITE INTELLIGENCE PLATFORM</div><h1>See what changed<br/><em>on Earth.</em></h1><p>Compare satellite imagery across time. Detect potential changes, map affected regions, and turn observations into actionable intelligence.</p><div className="hero-meta"><span><ShieldCheck size={15}/> Image-based analysis</span><span><Activity size={15}/> Near-instant results</span></div></div>
        <div className="orbit-art"><div className="orbit orbit-one"></div><div className="orbit orbit-two"></div><div className="earth"><div className="earth-land land-one"></div><div className="earth-land land-two"></div><div className="earth-glow"></div></div><div className="satellite-icon"><Satellite size={29}/></div><div className="orbit-label label-a">EARTH OBSERVATION</div><div className="orbit-label label-b">CHANGE ANALYTICS</div></div>
      </section>

      <section className="section-heading"><div><div className="section-kicker">01 / INPUT DATA</div><h2>Image comparison</h2><p>Upload two images of the same area captured at different times.</p></div><div className="data-tag"><span className="tiny-dot"></span> {before && after ? '2 IMAGES READY' : 'AWAITING INPUT'}</div></section>
      <section className="upload-grid">
        <ImageDrop label="01 BEFORE IMAGE" file={before} setFile={setBefore} hint="Earlier capture · T1"/>
        <div className="compare-arrow"><ArrowRight size={18}/></div>
        <ImageDrop label="02 AFTER IMAGE" file={after} setFile={setAfter} hint="Later capture · T2"/>
      </section>
      <div className="action-row"><div className="hint"><span className="hint-dot"></span> Best results with similar framing, scale, and lighting.</div><button className="primary-button" disabled={!canAnalyze} onClick={analyze}>{busy ? <><LoaderCircle className="spin" size={17}/> Analyzing imagery…</> : <><ScanSearch size={17}/> Detect changes <ArrowRight size={16}/></>}</button></div>
      {error && <div className="error-banner"><AlertTriangle size={18}/><span>{error}</span></div>}

      {result && <section className="results-section">
        <div className="section-heading results-heading"><div><div className="section-kicker">02 / ANALYSIS OUTPUT</div><h2>Change intelligence</h2><p>Potential visual differences identified between the two captures.</p></div><button className="secondary-button" onClick={downloadReport}><FileDown size={16}/> Export report</button></div>
        <div className="stats-grid">
          <div className="stat-card"><div className="stat-label">CHANGED PIXELS</div><div className="stat-value">{stats.changed_pixel_count.toLocaleString()}</div><div className="stat-foot">Pixels in detected regions</div></div>
          <div className="stat-card accent-stat"><div className="stat-label">FLAGGED IMAGE AREA</div><div className="stat-value">{stats.changed_area_percentage}<small>%</small></div><div className="stat-foot">Approx. share of image pixels</div></div>
          <div className="stat-card"><div className="stat-label">DETECTED REGIONS</div><div className="stat-value">{stats.detected_regions}</div><div className="stat-foot">Connected change candidates</div></div>
          <div className="stat-card"><div className="stat-label">IMAGE RESOLUTION</div><div className="stat-value">{stats.width}<small> × </small>{stats.height}</div><div className="stat-foot">Normalized comparison canvas</div></div>
        </div>
        <div className="analysis-grid">
          <div className="panel image-panel"><div className="panel-head"><div><b>Visual change map</b><small>Detected regions are highlighted in red</small></div><span className="result-chip"><CheckCircle2 size={13}/> ANALYSIS COMPLETE</span></div>
            <div className="view-tabs">{[['overlay','Change overlay'],['before','Before'],['after','After'],['mask','Binary mask']].map(([key,label])=><button key={key} className={view===key?'selected':''} onClick={()=>setView(key)}>{label}</button>)}</div>
            <div className="result-image-wrap"><img src={activeImage} alt="Satellite change analysis result"/></div>
            <div className="image-caption"><span><span className="legend-red"></span> Potential change</span><span>{stats.width} × {stats.height} px</span></div>
          </div>
          <div className="panel region-panel"><div className="panel-head"><div><b>Region observations</b><small>Largest detected candidates</small></div><span className="count-badge">{result.regions.length}</span></div>
            {result.regions.length ? <div className="region-list">{result.regions.slice(0,8).map(r=><div className="region-row" key={r.id}><div className="region-icon"><ScanSearch size={16}/></div><div className="region-info"><b>Region {String(r.id).padStart(2,'0')}</b><small>{r.width} × {r.height} px · {r.pixels.toLocaleString()} px²</small></div><div className="region-pct">{r.relative_size_pct}%</div></div>)}</div> : <div className="empty-regions"><ImageIcon size={26}/><b>No significant regions</b><span>Try a pair with more visible differences.</span></div>}
            <div className="caution"><AlertTriangle size={15}/><span>Visual differences can be caused by shadows, clouds, seasonality, or image misalignment. Review before drawing conclusions.</span></div>
          </div>
        </div>
        <div className="report-strip"><div className="report-icon"><FileDown size={20}/></div><div><b>Your analysis report is ready</b><p>Includes metrics, region coordinates, method, and limitations.</p></div><button className="secondary-button" onClick={downloadReport}>Download JSON <FileDown size={15}/></button></div>
      </section>}

      {!result && <section className="empty-state"><div className="empty-icon"><ImageIcon size={22}/></div><div><b>Your analysis workspace is ready</b><p>Upload both images to reveal detected changes, region metrics, and your exportable report.</p></div><div className="empty-status"><span></span> READY</div></section>}
      <footer><span>© 2026 TERRAWATCH AI</span><span>BUILT FOR ORCA CODER · HACKATHON DEMO</span><span>NOT FOR OPERATIONAL DECISIONS</span></footer>
    </main>
  </div>;
}