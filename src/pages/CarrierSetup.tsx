import { useState, useEffect, useCallback, useRef } from 'react';
import { Upload, Trash2, CheckCircle, AlertCircle, Copy, Loader2, Pencil, Check, X, Search, ChevronDown, ChevronUp, FileText, RefreshCw, Eye } from 'lucide-react';
import { api, Carrier } from '../services/api';

// ─── AI Pipeline Constants ───
const PIPELINE_STEPS = [
  'PDF Upload', 'Extract Raw Text', 'Detect Sections', 'Filter Relevant',
  'Split Chunks', 'Send to Claude', 'Extract Rules', 'Normalize',
  'Canonicalize', 'Merge Rules', 'Output Final',
];

const RELEVANT_KW = [
  'label','barcode','routing','address','format','dimension','encoding','field',
  'mandatory','required','shipment','tracking','postal','weight','service','zone',
  'segment','edi','element','composite','delimiter','envelope','transaction','loop',
];

const FIELD_MAP: Record<string, string[]> = {
  shipment_number: ['shipment_number','airwaybill','awb','waybill','tracking_number','consignment_number'],
  postal_code: ['postal_code','postcode','zip','zip_code','zipcode'],
  routing_barcode: ['routing_barcode','routing_code','sort_code'],
  license_plate: ['license_plate','sscc','lp'],
  weight: ['weight','gross_weight','actual_weight','package_weight'],
  service_type: ['service_type','service_code','product_code'],
  country_code: ['country_code','country','destination_country'],
  reference_number: ['reference_number','reference','customer_reference'],
};

function canon(f: string) {
  const l = f.toLowerCase().replace(/[\s-]+/g, '_');
  for (const [c, a] of Object.entries(FIELD_MAP)) if (a.includes(l)) return c;
  return l;
}
function relev(t: string) { return RELEVANT_KW.some(k => t.toLowerCase().includes(k)); }

function detectSec(text: string) {
  const lines = text.split('\n');
  const secs: { number: string; heading: string; body: string }[] = [];
  let cur: { number: string; heading: string; body: string } | null = null;
  for (const line of lines) {
    const m = line.match(/^(\d+\.[\d.]*)\s+(.+)/);
    if (m) { if (cur) secs.push(cur); cur = { number: m[1], heading: m[2].trim(), body: '' }; }
    else if (cur) { cur.body += line + '\n'; }
  }
  if (cur) secs.push(cur);
  if (!secs.length && text.trim()) secs.push({ number: '0', heading: 'Content', body: text });
  return secs;
}
function filterSec(s: ReturnType<typeof detectSec>) {
  const f = s.filter(x => relev(x.heading) || relev(x.body.substring(0, 400)));
  return f.length ? f : s;
}
function chunk(text: string, mx = 2500) {
  const ch: string[] = []; const sn = text.split(/(?<=[.!?\n])\s+/); let b = '';
  for (const s of sn) { if (b.length + s.length > mx && b) { ch.push(b.trim()); b = ''; } b += s + ' '; }
  if (b.trim()) ch.push(b.trim()); return ch;
}

interface Rule { field: string; required: boolean; regex: string; description: string }

function norm(rules: Rule[]): Rule[] {
  return rules.map(r => ({ field: canon(r.field || 'unknown'), required: typeof r.required === 'boolean' ? r.required : false, regex: r.regex || '', description: (r.description || '').trim() }));
}
function merge(rules: Rule[]): Rule[] {
  const m = new Map<string, Rule>();
  for (const r of rules) { const k = `${r.field}__${r.regex}`; if (m.has(k)) { const e = m.get(k)!; if (!e.description.includes(r.description)) e.description += '; ' + r.description; e.required = e.required || r.required; } else { m.set(k, { ...r }); } }
  return [...m.values()];
}

function buildPrompt(chk: string, sec: string) {
  return `You are a carrier specification rule extraction engine.\nAnalyze text from section: "${sec}".\nEXTRACT ONLY validation rules. Focus on: mandatory fields, field formats, regex patterns, barcode structure, routing rules, address formats, label dimensions, encoding standards, EDI segment/element requirements.\nOUTPUT FORMAT (STRICT JSON ONLY):\n{"rules":[{"field":"<snake_case>","required":true/false,"regex":"<only if clearly defined>","description":"<brief>"}]}\nRULES: Return ONLY valid JSON. If no rules: {"rules":[]}. Do NOT invent regex. Do NOT guess.\nTEXT:\n"""\n${chk}\n"""`;
}

async function callClaude(chk: string, sec: string): Promise<{ rules: Rule[] }> {
  try {
    const r = await fetch('https://api.anthropic.com/v1/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: 'claude-sonnet-4-20250514', max_tokens: 1000, messages: [{ role: 'user', content: buildPrompt(chk, sec) }] }) });
    const d = await r.json(); const t = d.content?.map((b: any) => b.text || '').join('') || ''; const m = t.match(/\{[\s\S]*\}/);
    return m ? JSON.parse(m[0]) : { rules: [] };
  } catch { return { rules: [] }; }
}

async function extractTextFromFile(file: File): Promise<string> {
  if (file.name.endsWith('.pdf')) {
    return new Promise(resolve => {
      const reader = new FileReader();
      reader.onload = e => {
        const bytes = new Uint8Array(e.target!.result as ArrayBuffer);
        let text = ''; let inStream = false; let buf: number[] = [];
        for (let i = 0; i < bytes.length; i++) {
          if (!inStream) { if (bytes[i]===0x73&&bytes[i+1]===0x74&&bytes[i+2]===0x72&&bytes[i+3]===0x65&&bytes[i+4]===0x61&&bytes[i+5]===0x6D) { inStream = true; i += 6; if (bytes[i]===0x0D) i++; if (bytes[i]===0x0A) i++; i--; continue; } }
          else { if (bytes[i]===0x65&&bytes[i+1]===0x6E&&bytes[i+2]===0x64&&bytes[i+3]===0x73&&bytes[i+4]===0x74&&bytes[i+5]===0x72) { const arr = new Uint8Array(buf); try { const decoded = new TextDecoder('utf-8', { fatal: false }).decode(arr); const rd = decoded.replace(/[^\x20-\x7E\n\r\t]/g, ' ').replace(/\s{3,}/g, '\n').trim(); if (rd.length > 20) text += rd + '\n'; } catch {} buf = []; inStream = false; i += 5; continue; } buf.push(bytes[i]); }
        }
        if (text.trim().length < 100) { const full = new TextDecoder('utf-8', { fatal: false }).decode(bytes); text = full.replace(/[^\x20-\x7E\n\r\t]/g, ' ').replace(/\s{3,}/g, '\n'); }
        resolve(text);
      };
      reader.readAsArrayBuffer(file);
    });
  }
  return await file.text();
}


// ═══════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════
export default function CarrierSetup() {
  const [carriers, setCarriers] = useState<Carrier[]>([]);
  const [carrierName, setCarrierName] = useState('');
  const [labelSpec, setLabelSpec] = useState<File | null>(null);
  const [ediSpec, setEdiSpec] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // AI Pipeline state
  const [pipelineActive, setPipelineActive] = useState(false);
  const [pipelineStep, setPipelineStep] = useState(-1);
  const [pipelineStatus, setPipelineStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [pipelineLogs, setPipelineLogs] = useState<string[]>([]);
  const [extractedRules, setExtractedRules] = useState<{ rules: Rule[] } | null>(null);

  // Rename state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [renaming, setRenaming] = useState(false);

  // Search
  const [carrierSearch, setCarrierSearch] = useState('');

  // Expanded carrier + spec replacement
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [updatingSpec, setUpdatingSpec] = useState<{ carrierId: string; type: string } | null>(null);

  // PDF viewer
  const [viewingPdf, setViewingPdf] = useState<{ url: string; name: string } | null>(null);

  const labelRef = useRef<HTMLInputElement>(null);
  const ediRef = useRef<HTMLInputElement>(null);
  const replaceFileRef = useRef<HTMLInputElement>(null);
  const pendingReplace = useRef<{ carrierId: string; type: 'label' | 'edi' } | null>(null);

  useEffect(() => { loadCarriers(); }, []);

  const loadCarriers = async () => {
    try {
      const response = await api.listCarriers();
      if (response.success) setCarriers(response.carriers);
    } catch (error) {
      console.error('Failed to load carriers:', error);
    }
  };

  const filteredCarriers = carriers.filter(c =>
    c.carrier.toLowerCase().includes(carrierSearch.toLowerCase().trim())
  );

  const addLog = useCallback((msg: string) => {
    setPipelineLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  }, []);

  // ─── Helper: get filename from path ───
  const getFileName = (path?: string) => {
    if (!path) return null;
    return path.split('/').pop() || path.split('\\').pop() || path;
  };

  // ─── View PDF ───
  const handleViewPdf = (specPath: string, specName: string) => {
    const url = `http://localhost:8000/api/carriers/files/${encodeURIComponent(specPath)}`;
    setViewingPdf({ url, name: specName });
  };

  // ─── Replace spec: trigger file picker ───
  const startReplaceSpec = (carrierId: string, type: 'label' | 'edi') => {
    pendingReplace.current = { carrierId, type };
    setTimeout(() => replaceFileRef.current?.click(), 50);
  };

  // ─── Replace spec: handle file selected ───
  const handleReplaceFileSelected = async (file: File) => {
    if (!pendingReplace.current) return;
    const { carrierId, type } = pendingReplace.current;
    pendingReplace.current = null;

    setUpdatingSpec({ carrierId, type });
    try {
      const formData = new FormData();
      formData.append('spec_type', type);
      formData.append('spec_file', file);

      const response = await api.updateCarrierSpec(carrierId, formData);
      if (response.success) {
        setMessage({ type: 'success', text: response.message || `${type} spec updated and rules re-extracted` });
        loadCarriers();
      } else {
        setMessage({ type: 'error', text: response.error || 'Failed to update spec' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Failed to update spec file' });
    } finally {
      setUpdatingSpec(null);
    }
  };

  // ─── AI Rule Extraction Pipeline ───
  async function runPipeline(text: string, type: string) {
    setPipelineActive(true); setPipelineStatus('running'); setPipelineLogs([]); setExtractedRules(null);
    let all: Rule[] = [];
    try {
      setPipelineStep(0); addLog(`✓ ${type} spec received`); await new Promise(r => setTimeout(r, 120));
      setPipelineStep(1); addLog(`✓ Extracted ${text.length} chars`); await new Promise(r => setTimeout(r, 120));
      setPipelineStep(2); const secs = detectSec(text); addLog(`✓ ${secs.length} sections`); await new Promise(r => setTimeout(r, 120));
      setPipelineStep(3); const rel = filterSec(secs); addLog(`✓ ${rel.length} relevant sections`); await new Promise(r => setTimeout(r, 120));
      setPipelineStep(4);
      const chs: { text: string; section: string }[] = [];
      for (const s of rel) { chunk(s.body).forEach(t => chs.push({ text: t, section: s.heading })); }
      addLog(`✓ ${chs.length} chunks`); await new Promise(r => setTimeout(r, 120));
      for (let i = 0; i < chs.length; i++) {
        setPipelineStep(5); addLog(`→ Chunk ${i + 1}/${chs.length} [${chs[i].section}]`);
        const res = await callClaude(chs[i].text, chs[i].section);
        setPipelineStep(6);
        if (res.rules?.length) { all = [...all, ...res.rules]; addLog(`  ✓ ${res.rules.length} rules`); }
        else { addLog(`  – No rules`); }
      }
      addLog(`✓ Raw total: ${all.length}`);
      setPipelineStep(7); all = norm(all); addLog(`✓ Normalized`);
      setPipelineStep(8); addLog(`✓ Canonicalized`);
      setPipelineStep(9); all = merge(all); addLog(`✓ Merged → ${all.length} unique`);
      setPipelineStep(10); setExtractedRules({ rules: all }); addLog(`✓ Done — ${all.length} final rules`); setPipelineStatus('done');
    } catch (e: any) { addLog(`✗ ${e.message}`); setPipelineStatus('error'); }
  }

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!carrierName.trim()) { setMessage({ type: 'error', text: 'Please enter a carrier name' }); return; }
    if (!labelSpec && !ediSpec) { setMessage({ type: 'error', text: 'Please upload at least one specification file' }); return; }
    setUploading(true); setMessage(null);
    if (labelSpec) { const text = await extractTextFromFile(labelSpec); if (text.trim().length > 20) await runPipeline(text, 'Label'); }
    if (ediSpec) { const text = await extractTextFromFile(ediSpec); if (text.trim().length > 20) await runPipeline(text, 'EDI'); }
    try {
      const formData = new FormData();
      formData.append('carrier_name', carrierName);
      if (labelSpec) formData.append('label_spec', labelSpec);
      if (ediSpec) formData.append('edi_spec', ediSpec);
      const response = await api.uploadCarrierSpec(formData);
      if (response.success) {
        setMessage({ type: 'success', text: `Carrier '${carrierName}' uploaded successfully!` });
        setCarrierName(''); setLabelSpec(null); setEdiSpec(null);
        if (labelRef.current) labelRef.current.value = '';
        if (ediRef.current) ediRef.current.value = '';
        loadCarriers();
      } else { setMessage({ type: 'error', text: 'Upload failed. Please try again.' }); }
    } catch { setMessage({ type: 'error', text: 'Upload failed. Check connection.' }); }
    finally { setUploading(false); }
  };

  const handleDelete = async (carrierId: string, name: string) => {
    if (!confirm(`Delete carrier '${name}'?`)) return;
    try { await api.deleteCarrier(carrierId); setMessage({ type: 'success', text: `Carrier '${name}' deleted successfully` }); if (expandedId === carrierId) setExpandedId(null); loadCarriers(); }
    catch { setMessage({ type: 'error', text: 'Failed to delete carrier' }); }
  };

  const startEditing = (carrier: Carrier) => { setEditingId(carrier._id); setEditName(carrier.carrier); };
  const cancelEditing = () => { setEditingId(null); setEditName(''); };
  const handleRename = async (carrierId: string) => {
    const trimmed = editName.trim(); if (!trimmed) return;
    setRenaming(true);
    try { const response = await api.renameCarrier(carrierId, trimmed); if (response.success) { setMessage({ type: 'success', text: `Carrier renamed to '${trimmed}'` }); setEditingId(null); setEditName(''); loadCarriers(); } else { setMessage({ type: 'error', text: response.error || 'Rename failed' }); } }
    catch { setMessage({ type: 'error', text: 'Failed to rename carrier' }); }
    finally { setRenaming(false); }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Carrier Setup</h1>
          <p className="text-gray-600">Upload carrier specifications to create validation rule templates</p>
        </div>

        {message && (
          <div className={`mb-6 p-4 rounded-lg flex items-center gap-2 ${message.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
            {message.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
            <span>{message.text}</span>
          </div>
        )}

        {/* PDF Viewer Modal */}
        {viewingPdf && (
          <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl h-[80vh] flex flex-col">
              <div className="flex items-center justify-between p-4 border-b border-gray-200">
                <div className="flex items-center gap-2">
                  <FileText className="w-5 h-5 text-[#4a4337]" />
                  <h3 className="font-semibold text-gray-900">{viewingPdf.name}</h3>
                </div>
                <button onClick={() => setViewingPdf(null)} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="flex-1 p-1">
                <iframe src={viewingPdf.url} className="w-full h-full rounded border border-gray-200" title={viewingPdf.name} />
              </div>
            </div>
          </div>
        )}

        {/* Hidden file input for spec replacement */}
        <input ref={replaceFileRef} type="file" accept=".pdf" className="hidden" onChange={(e) => { const file = e.target.files?.[0]; if (file) handleReplaceFileSelected(file); e.target.value = ''; }} />

        {/* Side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Upload New Carrier */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Upload New Carrier</h2>
            <form onSubmit={handleUpload} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Carrier Name</label>
                <input type="text" value={carrierName} onChange={(e) => setCarrierName(e.target.value)} className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#4a4337] focus:border-transparent" placeholder="e.g., DHL, UPS, FedEx" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Label Specification (PDF)</label>
                <div className="border-2 border-dashed border-gray-300 rounded-lg p-4 hover:border-[#4a4337] transition-colors">
                  <input ref={labelRef} type="file" accept=".pdf" onChange={(e) => setLabelSpec(e.target.files?.[0] || null)} className="w-full" />
                  {labelSpec && <p className="mt-2 text-sm text-green-600 flex items-center gap-2"><CheckCircle className="w-4 h-4" />{labelSpec.name}</p>}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">EDI Specification (PDF)</label>
                <div className="border-2 border-dashed border-gray-300 rounded-lg p-4 hover:border-[#4a4337] transition-colors">
                  <input ref={ediRef} type="file" accept=".pdf" onChange={(e) => setEdiSpec(e.target.files?.[0] || null)} className="w-full" />
                  {ediSpec && <p className="mt-2 text-sm text-green-600 flex items-center gap-2"><CheckCircle className="w-4 h-4" />{ediSpec.name}</p>}
                </div>
              </div>
              <button type="submit" disabled={uploading} className="w-full bg-[#4a4337] text-white py-3 rounded-lg font-medium hover:bg-[#3a3529] disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2">
                {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
                {uploading ? 'Uploading & Extracting...' : 'Upload Carrier Specs'}
              </button>
            </form>
          </div>

          {/* Configured Carriers */}
          <div className="bg-white rounded-lg shadow p-6 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Configured Carriers</h2>
              {carriers.length > 0 && <span className="text-sm text-gray-500">{carriers.length} total</span>}
            </div>

            {carriers.length > 0 && (
              <div className="relative mb-4">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input type="text" value={carrierSearch} onChange={(e) => setCarrierSearch(e.target.value)} placeholder="Search carriers..." className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-[#4a4337] focus:border-transparent placeholder:text-gray-400" />
                {carrierSearch && <button onClick={() => setCarrierSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>}
              </div>
            )}

            {carriers.length === 0 ? (
              <div className="text-center py-12 text-gray-500 flex-1 flex flex-col items-center justify-center">
                <p>No carriers configured yet</p>
                <p className="text-sm mt-2">Upload a carrier specification to get started</p>
              </div>
            ) : filteredCarriers.length === 0 ? (
              <div className="text-center py-12 text-gray-500 flex-1 flex flex-col items-center justify-center">
                <p className="text-sm">No carriers matching "{carrierSearch}"</p>
              </div>
            ) : (
              <div className="carrier-scroll space-y-3 overflow-y-auto flex-1 pr-1" style={{ maxHeight: '500px' }}>
                <style>{`
                  .carrier-scroll::-webkit-scrollbar { width: 6px; }
                  .carrier-scroll::-webkit-scrollbar-track { background: #f5f3f0; border-radius: 3px; }
                  .carrier-scroll::-webkit-scrollbar-thumb { background: #4a4337; border-radius: 3px; }
                  .carrier-scroll::-webkit-scrollbar-thumb:hover { background: #3a3529; }
                  .carrier-scroll { scrollbar-width: thin; scrollbar-color: #4a4337 #f5f3f0; }
                `}</style>

                {filteredCarriers.map((carrier) => {
                  const isExpanded = expandedId === carrier._id;
                  const isUpdating = updatingSpec?.carrierId === carrier._id;

                  return (
                    <div key={carrier._id} className={`border rounded-lg transition-colors ${isExpanded ? 'border-[#4a4337] bg-[#faf9f7]' : 'border-gray-200 hover:border-[#4a4337]'}`}>
                      {/* Carrier Row */}
                      <div className="flex items-center justify-between p-4">
                        {editingId === carrier._id ? (
                          <div className="flex items-center gap-2 flex-1 mr-2">
                            <input type="text" value={editName} onChange={(e) => setEditName(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') handleRename(carrier._id); if (e.key === 'Escape') cancelEditing(); }} autoFocus className="flex-1 px-3 py-1.5 border border-[#5a5347] rounded-lg text-sm focus:ring-2 focus:ring-[#4a4337] focus:border-transparent" />
                            <button onClick={() => handleRename(carrier._id)} disabled={renaming || !editName.trim()} className="p-1.5 text-green-600 hover:bg-green-50 rounded-lg transition-colors disabled:opacity-50" title="Save">
                              {renaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                            </button>
                            <button onClick={cancelEditing} className="p-1.5 text-gray-400 hover:bg-gray-50 rounded-lg transition-colors" title="Cancel"><X className="w-4 h-4" /></button>
                          </div>
                        ) : (
                          <>
                            <button onClick={() => setExpandedId(isExpanded ? null : carrier._id)} className="flex items-center gap-2 flex-1 text-left">
                              {isExpanded ? <ChevronUp className="w-4 h-4 text-[#4a4337]" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                              <h3 className="font-medium text-gray-900">{carrier.carrier}</h3>
                            </button>
                            <div className="flex items-center gap-1">
                              <button onClick={() => startEditing(carrier)} className="p-2 text-gray-400 hover:text-[#4a4337] hover:bg-[#f5f3f0] rounded-lg transition-colors" title="Rename"><Pencil className="w-4 h-4" /></button>
                              <button onClick={() => handleDelete(carrier._id, carrier.carrier)} className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="Delete"><Trash2 className="w-4 h-4" /></button>
                            </div>
                          </>
                        )}
                      </div>

                      {/* Expanded Detail */}
                      {isExpanded && (
                        <div className="px-4 pb-4 border-t border-gray-200 pt-3 space-y-3">
                          {/* Label Spec Row */}
                          <div className="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              <FileText className="w-4 h-4 text-[#4a4337] flex-shrink-0" />
                              <div className="min-w-0">
                                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Label Spec</p>
                                <p className="text-sm text-gray-900 truncate">
                                  {getFileName(carrier.label_spec_path) || <span className="text-gray-400 italic">Not uploaded</span>}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                              {carrier.label_spec_path && (
                                <button onClick={() => handleViewPdf(carrier.label_spec_path!, getFileName(carrier.label_spec_path) || 'Label Spec')} className="p-1.5 text-[#4a4337] hover:bg-[#f5f3f0] rounded-lg transition-colors" title="View PDF"><Eye className="w-4 h-4" /></button>
                              )}
                              <button onClick={() => startReplaceSpec(carrier._id, 'label')} disabled={isUpdating} className="p-1.5 text-[#4a4337] hover:bg-[#f5f3f0] rounded-lg transition-colors disabled:opacity-50" title={carrier.label_spec_path ? 'Replace & re-learn' : 'Upload label spec'}>
                                {isUpdating && updatingSpec?.type === 'label' ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                              </button>
                            </div>
                          </div>

                          {/* EDI Spec Row */}
                          <div className="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              <FileText className="w-4 h-4 text-[#4a4337] flex-shrink-0" />
                              <div className="min-w-0">
                                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">EDI Spec</p>
                                <p className="text-sm text-gray-900 truncate">
                                  {getFileName(carrier.edi_spec_path) || <span className="text-gray-400 italic">Not uploaded</span>}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                              {carrier.edi_spec_path && (
                                <button onClick={() => handleViewPdf(carrier.edi_spec_path!, getFileName(carrier.edi_spec_path) || 'EDI Spec')} className="p-1.5 text-[#4a4337] hover:bg-[#f5f3f0] rounded-lg transition-colors" title="View PDF"><Eye className="w-4 h-4" /></button>
                              )}
                              <button onClick={() => startReplaceSpec(carrier._id, 'edi')} disabled={isUpdating} className="p-1.5 text-[#4a4337] hover:bg-[#f5f3f0] rounded-lg transition-colors disabled:opacity-50" title={carrier.edi_spec_path ? 'Replace & re-learn' : 'Upload EDI spec'}>
                                {isUpdating && updatingSpec?.type === 'edi' ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                              </button>
                            </div>
                          </div>

                          {/* Re-learning indicator */}
                          {isUpdating && (
                            <div className="flex items-center gap-2 p-3 bg-[#f5f3f0] rounded-lg text-sm text-[#4a4337]">
                              <Loader2 className="w-4 h-4 animate-spin" />
                              <span>Re-learning rules from new {updatingSpec?.type} spec...</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {carrierSearch && filteredCarriers.length > 0 && (
              <p className="mt-3 text-xs text-gray-400 text-center">Showing {filteredCarriers.length} of {carriers.length} carriers</p>
            )}
          </div>
        </div>

        {/* AI Pipeline Panel */}
        {pipelineActive && (
          <div className="mt-8 bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold flex items-center gap-2">
                {pipelineStatus === 'running' && <Loader2 className="w-5 h-5 animate-spin text-[#4a4337]" />}
                {pipelineStatus === 'done' && <CheckCircle className="w-5 h-5 text-green-600" />}
                {pipelineStatus === 'error' && <AlertCircle className="w-5 h-5 text-red-600" />}
                AI Rule Extraction Pipeline
              </h2>
              {extractedRules && <button onClick={() => navigator.clipboard?.writeText(JSON.stringify(extractedRules, null, 2))} className="flex items-center gap-2 px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm font-medium"><Copy className="w-4 h-4" /> Copy JSON</button>}
            </div>
            <div className="flex flex-wrap gap-2 mb-6">
              {PIPELINE_STEPS.map((s, i) => {
                const done = i < pipelineStep || (i === pipelineStep && pipelineStatus === 'done');
                const active = i === pipelineStep && pipelineStatus === 'running';
                const fail = i === pipelineStep && pipelineStatus === 'error';
                let cls = 'bg-gray-100 text-gray-500';
                if (done) cls = 'bg-green-100 text-green-800';
                if (active) cls = 'bg-[#e8e5e0] text-[#2a2519]';
                if (fail) cls = 'bg-red-100 text-red-800';
                return <span key={i} className={`px-3 py-1 rounded-full text-xs font-medium ${cls}`}>{done ? '✓ ' : active ? '▶ ' : fail ? '✗ ' : ''}{i + 1}. {s}</span>;
              })}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Pipeline Logs</h3>
                <pre className="bg-gray-900 text-gray-300 p-4 rounded-lg text-xs font-mono max-h-64 overflow-auto">{pipelineLogs.join('\n') || 'Waiting...'}</pre>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Extracted Rules ({extractedRules?.rules?.length || 0})</h3>
                {extractedRules?.rules?.length ? (
                  <div className="max-h-64 overflow-auto border border-gray-200 rounded-lg">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50 sticky top-0">
                        <tr>
                          <th className="text-left px-3 py-2 text-xs font-semibold text-gray-600">Field</th>
                          <th className="text-left px-3 py-2 text-xs font-semibold text-gray-600">Req</th>
                          <th className="text-left px-3 py-2 text-xs font-semibold text-gray-600">Regex</th>
                          <th className="text-left px-3 py-2 text-xs font-semibold text-gray-600">Description</th>
                        </tr>
                      </thead>
                      <tbody>
                        {extractedRules.rules.map((r, i) => (
                          <tr key={i} className="border-t border-gray-100">
                            <td className="px-3 py-2 font-mono text-[#3a3529] text-xs">{r.field}</td>
                            <td className="px-3 py-2"><span className={`px-1.5 py-0.5 rounded text-xs font-medium ${r.required ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-500'}`}>{r.required ? 'YES' : 'NO'}</span></td>
                            <td className="px-3 py-2 font-mono text-xs text-yellow-700 max-w-32 truncate">{r.regex || '—'}</td>
                            <td className="px-3 py-2 text-xs text-gray-600 max-w-48 truncate">{r.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="bg-gray-50 rounded-lg p-8 text-center text-gray-500 text-sm">{pipelineStatus === 'running' ? 'Extracting rules...' : 'No rules extracted'}</div>
                )}
                {extractedRules && (
                  <details className="mt-3">
                    <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-700">View raw JSON</summary>
                    <pre className="mt-2 bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs font-mono max-h-48 overflow-auto">{JSON.stringify(extractedRules, null, 2)}</pre>
                  </details>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}