import { useState, useEffect } from 'react';
import {
  FileCheck, AlertCircle, Copy, CheckCircle, Upload, ClipboardPaste,
  Shield, Globe, Truck, FileText, ChevronDown, X, RefreshCw, Loader2,
  Search, Flag, Plus, Sparkles
} from 'lucide-react';
import { api, Carrier, ValidationResult } from '../services/api';


// ═══════════════════════════════════════════
// CORRECTION API HELPER
// ═══════════════════════════════════════════

const API_BASE = 'http://localhost:8000';

const correctionApi = {
  async submit(data: {
    carrier: string;
    field: string;
    correction_type: 'wrong_error' | 'missing_check';
    actual_value?: string;
    notes?: string;
  }) {
    const r = await fetch(`${API_BASE}/api/corrections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return r.json();
  },
};


// ═══════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════

interface CarrierMatch {
  carrier_id: string;
  carrier_name: string;
  spec_name: string;
  confidence: number;
  match_reasons: string[];
  is_best_match: boolean;
}

interface DetectionSignals {
  carrier: string;
  origin_country: string;
  destination_country: string;
  origin_region: string;
  destination_region: string;
  service_type: string;
  tracking_number: string;
  is_international: boolean;
  is_domestic: boolean;
  [key: string]: any;
}

interface DetectionResult {
  signals: DetectionSignals;
  best_match: CarrierMatch | null;
  alternatives: CarrierMatch[];
  all_carriers: { _id: string; carrier: string }[];
  needs_confirmation: boolean;
  message: string;
}


// ═══════════════════════════════════════════
// INLINE ERROR FEEDBACK — "This is wrong"
// ═══════════════════════════════════════════
// Replaces each error row when user flags it.
// Sits inside the existing error list, same styling.

function ErrorWithFeedback({
  error,
  carrier,
  onCorrected,
}: {
  error: { field: string; expected: string; actual: string; description?: string };
  carrier: string;
  onCorrected: (field: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [value, setValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      await correctionApi.submit({
        carrier,
        field: error.field,
        correction_type: 'wrong_error',
        actual_value: value || undefined,
      });
      setDone(true);
      onCorrected(error.field);
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  if (done) {
    return (
      <div className="bg-green-50 p-3 rounded border border-green-200 flex items-center gap-3">
        <Sparkles className="w-4 h-4 text-green-600 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="font-medium text-green-900">{error.field}</p>
          <p className="text-xs text-green-700">Learned — this won't be flagged again for {carrier}.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-red-50 rounded border border-red-200 overflow-hidden">
      <div className="p-3 flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="font-medium text-red-900">{error.field}</p>
          <p className="text-sm text-red-700">{error.description}</p>
          <p className="text-xs text-red-600 mt-1">Expected: {error.expected} | Actual: {error.actual}</p>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="shrink-0 flex items-center gap-1 px-2 py-1 text-xs font-medium text-red-600 border border-red-200 rounded hover:bg-red-100 transition-colors"
          title="Flag this error as incorrect"
        >
          <Flag className="w-3 h-3" />
          <span className="hidden sm:inline">Wrong</span>
        </button>
      </div>
      {expanded && (
        <div className="border-t border-red-100 bg-red-50/60 px-3 py-2">
          <p className="text-xs text-gray-600 mb-1.5">
            What's the actual value on the label? <span className="text-gray-400">(optional)</span>
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={`e.g., the actual ${error.field}`}
              className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-sm focus:ring-1 focus:ring-blue-500 outline-none"
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            />
            <button
              onClick={handleSubmit}
              disabled={saving}
              className="px-3 py-1.5 bg-[#4a4337] text-white text-sm rounded hover:bg-[#3a3529] disabled:bg-gray-300 flex items-center gap-1"
            >
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
              Confirm
            </button>
            <button onClick={() => setExpanded(false)} className="px-2 py-1.5 text-gray-400 hover:text-gray-600 rounded hover:bg-gray-100">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════
// "Report Missing Check" — shows after results
// ═══════════════════════════════════════════

function ReportMissingCheck({
  carrier,
  onAdded,
}: {
  carrier: string;
  onAdded: (field: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [field, setField] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!field.trim()) return;
    setSaving(true);
    try {
      const result = await correctionApi.submit({
        carrier,
        field: field.trim(),  // Backend normalizes: "Shipment Date" → "shipment_date"
        correction_type: 'missing_check',
        notes: notes || undefined,
      });
      onAdded(result.normalized_field || field.trim());
      setField('');
      setNotes('');
      setOpen(false);
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm text-gray-500 border border-dashed border-gray-300 rounded-lg hover:border-[#4a4337] hover:text-[#4a4337] hover:bg-[#f5f3f0] transition-all"
      >
        <Plus className="w-4 h-4" />
        Report a missing check
      </button>
    );
  }

  return (
    <div className="border border-amber-200 bg-amber-50 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-amber-900">What did the validator miss?</p>
        <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-gray-600">
          <X className="w-4 h-4" />
        </button>
      </div>
      <input
        type="text"
        value={field}
        onChange={(e) => setField(e.target.value)}
        placeholder="Field name — e.g., Shipment Date, Piece Count, sender phone"
        className="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:ring-1 focus:ring-[#4a4337] outline-none"
      />
      <input
        type="text"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Why is it required? (optional)"
        className="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:ring-1 focus:ring-[#4a4337] outline-none"
        onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
      />
      <button
        onClick={handleSubmit}
        disabled={!field.trim() || saving}
        className="w-full px-4 py-2 bg-amber-600 text-white text-sm font-medium rounded hover:bg-amber-700 disabled:bg-gray-300 flex items-center justify-center gap-2"
      >
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
        {saving ? 'Saving...' : 'Make this mandatory'}
      </button>
    </div>
  );
}


// ═══════════════════════════════════════════
// CARRIER CONFIRMATION COMPONENT (unchanged)
// ═══════════════════════════════════════════

function CarrierConfirmation({
  detectionResult,
  loading,
  error,
  onConfirm,
  onCancel,
  onRetry,
  type,
}: {
  detectionResult: DetectionResult | null;
  loading: boolean;
  error: string | null;
  onConfirm: (carrierId: string, carrierName: string) => void;
  onCancel: () => void;
  onRetry: () => void;
  type: 'label' | 'edi';
}) {
  const [selectedMatch, setSelectedMatch] = useState<CarrierMatch | null>(null);
  const [showAlternatives, setShowAlternatives] = useState(false);
  const [manualMode, setManualMode] = useState(false);
  const [manualCarrierId, setManualCarrierId] = useState('');

  useEffect(() => {
    if (detectionResult?.best_match) {
      setSelectedMatch(detectionResult.best_match);
      setManualMode(false);
    } else if (detectionResult && !detectionResult.best_match) {
      setManualMode(true);
    }
  }, [detectionResult]);

  const handleConfirm = () => {
    if (manualMode && manualCarrierId) {
      const carrier = detectionResult?.all_carriers.find(c => c._id === manualCarrierId);
      if (carrier) onConfirm(carrier._id, carrier.carrier);
    } else if (selectedMatch) {
      onConfirm(selectedMatch.carrier_id, selectedMatch.carrier_name);
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-xl border-2 border-[#e8e5e0] p-8">
        <div className="flex items-center gap-4">
          <Loader2 className="w-8 h-8 text-[#4a4337] animate-spin" />
          <div>
            <h3 className="text-lg font-semibold text-gray-900">
              Analyzing {type === 'label' ? 'label' : 'EDI file'}...
            </h3>
            <p className="text-sm text-gray-500 mt-1">Detecting carrier, region, and matching specification</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-xl border-2 border-red-100 p-8">
        <div className="flex items-center gap-3 text-red-600 mb-4">
          <AlertCircle className="w-6 h-6" />
          <h3 className="text-lg font-semibold">Detection Failed</h3>
        </div>
        <p className="text-gray-600 mb-4">{error}</p>
        <div className="flex gap-3">
          <button onClick={onRetry} className="px-4 py-2 bg-[#4a4337] text-white rounded-lg hover:bg-[#3a3529] flex items-center gap-2">
            <RefreshCw className="w-4 h-4" /> Retry
          </button>
          <button onClick={onCancel} className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
        </div>
      </div>
    );
  }

  if (!detectionResult) return null;

  const { signals, best_match, alternatives, all_carriers, message } = detectionResult;
  const confidence = selectedMatch?.confidence || 0;
  const cc = confidence >= 0.8
    ? { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', bar: 'bg-green-500', badge: 'bg-green-100 text-green-800' }
    : confidence >= 0.5
    ? { bg: 'bg-yellow-50', border: 'border-yellow-200', text: 'text-yellow-700', bar: 'bg-yellow-500', badge: 'bg-yellow-100 text-yellow-800' }
    : { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', bar: 'bg-red-500', badge: 'bg-red-100 text-red-800' };

  return (
    <div className="bg-white rounded-xl border-2 border-[#e8e5e0] shadow-sm overflow-hidden">
      <div className="bg-gradient-to-r from-[#f5f3f0] to-[#eae7e2] px-6 py-4 border-b border-[#e8e5e0]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield className="w-6 h-6 text-[#4a4337]" />
            <h3 className="text-lg font-semibold text-gray-900">Carrier Detection</h3>
          </div>
          <button onClick={onCancel} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="p-6">
        {signals && Object.values(signals).some(v => v) && (
          <div className="mb-6">
            <h4 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">Detected from {type}</h4>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {signals.carrier && (
                <div className="bg-gray-50 rounded-lg p-3">
                  <div className="flex items-center gap-2 text-xs text-gray-500 mb-1"><Truck className="w-3.5 h-3.5" /> Carrier</div>
                  <span className="font-semibold text-gray-900 uppercase">{signals.carrier}</span>
                </div>
              )}
              {signals.origin_country && (
                <div className="bg-gray-50 rounded-lg p-3">
                  <div className="flex items-center gap-2 text-xs text-gray-500 mb-1"><Globe className="w-3.5 h-3.5" /> Origin</div>
                  <span className="font-semibold text-gray-900">
                    {signals.origin_country}
                    {signals.origin_region && <span className="text-gray-400 font-normal text-xs ml-1">({signals.origin_region})</span>}
                  </span>
                </div>
              )}
              {signals.destination_country && (
                <div className="bg-gray-50 rounded-lg p-3">
                  <div className="flex items-center gap-2 text-xs text-gray-500 mb-1"><Globe className="w-3.5 h-3.5" /> Destination</div>
                  <span className="font-semibold text-gray-900">
                    {signals.destination_country}
                    {signals.destination_region && <span className="text-gray-400 font-normal text-xs ml-1">({signals.destination_region})</span>}
                  </span>
                </div>
              )}
              {signals.service_type && (
                <div className="bg-gray-50 rounded-lg p-3">
                  <div className="flex items-center gap-2 text-xs text-gray-500 mb-1"><FileText className="w-3.5 h-3.5" /> Service</div>
                  <span className="font-semibold text-gray-900 text-sm">{signals.service_type}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {!manualMode && selectedMatch ? (
          <>
            <div className={`${cc.bg} ${cc.border} border-2 rounded-xl p-5 mb-4`}>
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <FileText className={`w-5 h-5 ${cc.text}`} />
                    <h4 className="font-semibold text-gray-900 text-lg">{selectedMatch.carrier_name}</h4>
                  </div>
                  {selectedMatch.match_reasons && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {selectedMatch.match_reasons.map((reason, i) => (
                        <span key={i} className={`text-xs px-2 py-0.5 rounded-full ${cc.badge}`}>{reason}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="text-right">
                  <div className={`text-2xl font-bold ${cc.text}`}>{Math.round(confidence * 100)}%</div>
                  <div className="text-xs text-gray-500">confidence</div>
                </div>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div className={`${cc.bar} rounded-full h-2 transition-all duration-500`} style={{ width: `${confidence * 100}%` }} />
              </div>
            </div>

            {alternatives && alternatives.length > 0 && (
              <div className="mb-4">
                <button onClick={() => setShowAlternatives(!showAlternatives)} className="flex items-center gap-2 text-sm text-[#4a4337] hover:text-[#2a2519] font-medium">
                  <ChevronDown className={`w-4 h-4 transition-transform ${showAlternatives ? 'rotate-180' : ''}`} />
                  {showAlternatives ? 'Hide' : 'Not correct? Show'} {alternatives.length} alternative{alternatives.length > 1 ? 's' : ''}
                </button>
                {showAlternatives && (
                  <div className="mt-3 space-y-2">
                    {alternatives.map((alt, i) => (
                      <button key={i} onClick={() => { setSelectedMatch(alt); setShowAlternatives(false); }}
                        className={`w-full text-left p-3 rounded-lg border-2 transition-colors ${
                          selectedMatch?.carrier_id === alt.carrier_id ? 'border-[#4a4337] bg-[#f5f3f0]' : 'border-gray-200 hover:border-[#8a8377] hover:bg-[#f5f3f0]'
                        }`}>
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-gray-900">{alt.carrier_name}</span>
                          <span className="text-sm font-semibold text-gray-600">{Math.round(alt.confidence * 100)}%</span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            <button onClick={() => setManualMode(true)} className="text-sm text-gray-500 hover:text-gray-700 mb-4 flex items-center gap-1">
              <Search className="w-3.5 h-3.5" /> Select carrier manually instead
            </button>
          </>
        ) : (
          <div className="mb-4">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
              <p className="text-amber-800 text-sm">
                {best_match ? 'Manual selection mode. Pick the correct carrier below.' : message || 'No matching carrier found automatically. Please select manually.'}
              </p>
            </div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Select Carrier</label>
            <select value={manualCarrierId} onChange={(e) => setManualCarrierId(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#4a4337] focus:border-transparent">
              <option value="">Choose a carrier...</option>
              {all_carriers.map((c) => (<option key={c._id} value={c._id}>{c.carrier}</option>))}
            </select>
            {best_match && (
              <button onClick={() => { setManualMode(false); setSelectedMatch(best_match); }} className="text-sm text-[#4a4337] hover:text-[#2a2519] mt-2 flex items-center gap-1">
                ← Back to auto-detected result
              </button>
            )}
          </div>
        )}

        <div className="flex gap-3">
          <button onClick={handleConfirm} disabled={manualMode ? !manualCarrierId : !selectedMatch}
            className="flex-1 px-5 py-3 bg-[#4a4337] text-white rounded-lg font-medium hover:bg-[#3a3529] disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors">
            <CheckCircle className="w-5 h-5" /> Confirm & Validate
          </button>
          <button onClick={onCancel} className="px-5 py-3 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium text-gray-600 transition-colors">Cancel</button>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════
// MAIN VALIDATION DASHBOARD
// ═══════════════════════════════════════════

export default function ValidationDashboard() {
  // ── Label state ──
  const [labelFile, setLabelFile] = useState<File | null>(null);
  const [labelPasteText, setLabelPasteText] = useState('');
  const [labelInputMode, setLabelInputMode] = useState<'upload' | 'paste'>('upload');
  const [labelDetecting, setLabelDetecting] = useState(false);
  const [labelDetectError, setLabelDetectError] = useState<string | null>(null);
  const [labelDetection, setLabelDetection] = useState<DetectionResult | null>(null);
  const [labelConfirmed, setLabelConfirmed] = useState<{ carrierId: string; carrierName: string } | null>(null);
  const [labelValidating, setLabelValidating] = useState(false);
  const [labelResult, setLabelResult] = useState<ValidationResult | null>(null);
  // NEW: feedback state
  const [labelCorrectedFields, setLabelCorrectedFields] = useState<Set<string>>(new Set());
  const [labelAddedFields, setLabelAddedFields] = useState<string[]>([]);

  // ── EDI state ──
  const [ediFile, setEdiFile] = useState<File | null>(null);
  const [ediPasteText, setEdiPasteText] = useState('');
  const [ediInputMode, setEdiInputMode] = useState<'upload' | 'paste'>('upload');
  const [ediDetecting, setEdiDetecting] = useState(false);
  const [ediDetectError, setEdiDetectError] = useState<string | null>(null);
  const [ediDetection, setEdiDetection] = useState<DetectionResult | null>(null);
  const [ediConfirmed, setEdiConfirmed] = useState<{ carrierId: string; carrierName: string } | null>(null);
  const [ediValidating, setEdiValidating] = useState(false);
  const [ediResult, setEdiResult] = useState<ValidationResult | null>(null);
  // NEW: feedback state
  const [ediCorrectedFields, setEdiCorrectedFields] = useState<Set<string>>(new Set());
  const [ediAddedFields, setEdiAddedFields] = useState<string[]>([]);

  const [copied, setCopied] = useState<string | null>(null);

  // ── Helpers ──
  const textToFile = (text: string, filename: string): File => {
    const blob = new Blob([text], { type: 'text/plain' });
    return new File([blob], filename, { type: 'text/plain' });
  };

  const copyToClipboard = (text: string, type: string) => {
    navigator.clipboard.writeText(text);
    setCopied(type);
    setTimeout(() => setCopied(null), 2000);
  };

  // ═══════════════════════════════════════════
  // LABEL FLOW
  // ═══════════════════════════════════════════

  const getLabelFile = (): File | null => {
    if (labelInputMode === 'upload') return labelFile;
    if (labelPasteText.trim()) {
      const isZpl = labelPasteText.includes('^XA') || labelPasteText.includes('^FD');
      return textToFile(labelPasteText, 'pasted_label' + (isZpl ? '.zpl' : '.txt'));
    }
    return null;
  };

  const handleLabelDetect = async () => {
    const file = getLabelFile();
    if (!file) return;
    setLabelResult(null);
    setLabelConfirmed(null);
    setLabelDetecting(true);
    setLabelDetectError(null);
    setLabelDetection(null);
    setLabelCorrectedFields(new Set());
    setLabelAddedFields([]);
    try {
      const data = await api.detectSpec(file);
      setLabelDetection(data);
    } catch (err: any) {
      setLabelDetectError(err.message || 'Failed to analyze label');
    } finally {
      setLabelDetecting(false);
    }
  };

  const handleLabelConfirm = async (carrierId: string, carrierName: string) => {
    setLabelConfirmed({ carrierId, carrierName });
    setLabelDetection(null);
    setLabelValidating(true);
    setLabelResult(null);
    const file = getLabelFile();
    if (!file) { setLabelValidating(false); return; }
    try {
      const response = await api.validateLabel(carrierId, file, false, carrierName);
      if (response.success) setLabelResult(response.validation);
    } catch (error) {
      console.error('Validation failed:', error);
    } finally {
      setLabelValidating(false);
    }
  };

  // NEW: Re-validate after corrections
  const handleLabelRevalidate = () => {
    if (labelConfirmed) {
      handleLabelConfirm(labelConfirmed.carrierId, labelConfirmed.carrierName);
    }
  };

  const handleLabelCancel = () => { setLabelDetection(null); setLabelDetecting(false); setLabelDetectError(null); };
  const resetLabelState = () => { setLabelResult(null); setLabelDetection(null); setLabelConfirmed(null); setLabelDetectError(null); setLabelCorrectedFields(new Set()); setLabelAddedFields([]); };

  // ═══════════════════════════════════════════
  // EDI FLOW
  // ═══════════════════════════════════════════

  const getEdiFile = (): File | null => {
    if (ediInputMode === 'upload') return ediFile;
    if (ediPasteText.trim()) {
      const trimmed = ediPasteText.trim();
      let ext = '.txt';
      if (trimmed.startsWith('{') || trimmed.startsWith('[')) ext = '.json';
      else if (trimmed.startsWith('<')) ext = '.xml';
      else if (trimmed.includes('~') && trimmed.includes('*')) ext = '.edi';
      return textToFile(ediPasteText, 'pasted_edi' + ext);
    }
    return null;
  };

  const handleEdiDetect = async () => {
    const file = getEdiFile();
    if (!file) return;
    setEdiResult(null); setEdiConfirmed(null); setEdiDetecting(true); setEdiDetectError(null); setEdiDetection(null);
    setEdiCorrectedFields(new Set()); setEdiAddedFields([]);
    try {
      const data = await api.detectEdiSpec(file);
      setEdiDetection(data);
    } catch (err: any) {
      setEdiDetectError(err.message || 'Failed to analyze EDI');
    } finally {
      setEdiDetecting(false);
    }
  };

  const handleEdiConfirm = async (carrierId: string, carrierName: string) => {
    setEdiConfirmed({ carrierId, carrierName });
    setEdiDetection(null); setEdiValidating(true); setEdiResult(null);
    const file = getEdiFile();
    if (!file) { setEdiValidating(false); return; }
    try {
      const response = await api.validateEDI(carrierId, file);
      if (response.success) setEdiResult(response.validation);
    } catch (error) {
      console.error('Validation failed:', error);
    } finally {
      setEdiValidating(false);
    }
  };

  const handleEdiRevalidate = () => {
    if (ediConfirmed) {
      handleEdiConfirm(ediConfirmed.carrierId, ediConfirmed.carrierName);
    }
  };

  const handleEdiCancel = () => { setEdiDetection(null); setEdiDetecting(false); setEdiDetectError(null); };
  const resetEdiState = () => { setEdiResult(null); setEdiDetection(null); setEdiConfirmed(null); setEdiDetectError(null); setEdiCorrectedFields(new Set()); setEdiAddedFields([]); };

  // ═══════════════════════════════════════════
  // READY FLAGS
  // ═══════════════════════════════════════════

  const labelHasInput = (labelInputMode === 'upload' && labelFile) || (labelInputMode === 'paste' && labelPasteText.trim());
  const ediHasInput = (ediInputMode === 'upload' && ediFile) || (ediInputMode === 'paste' && ediPasteText.trim());
  const labelBusy = labelDetecting || labelValidating;
  const ediBusy = ediDetecting || ediValidating;

  const labelHasChanges = labelCorrectedFields.size > 0 || labelAddedFields.length > 0;
  const ediHasChanges = ediCorrectedFields.size > 0 || ediAddedFields.length > 0;

  // ═══════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════

  return (
    <div className="min-h-screen bg-gray-50 pt-8 pb-8 px-4">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Validation Dashboard</h1>
          <p className="text-gray-600">Upload a label or EDI file — carrier will be detected automatically</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* ═══ Label Validation ═══ */}
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <FileCheck className="w-5 h-5" /> Label Validation
              </h2>
              <div className="space-y-4">
                <div className="flex rounded-lg border border-gray-200 overflow-hidden">
                  <button onClick={() => setLabelInputMode('upload')}
                    className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors ${labelInputMode === 'upload' ? 'bg-[#f5f3f0] text-[#3a3529] border-b-2 border-[#4a4337]' : 'text-gray-500 hover:bg-gray-50'}`}>
                    <Upload className="w-4 h-4" /> Upload File
                  </button>
                  <button onClick={() => setLabelInputMode('paste')}
                    className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors ${labelInputMode === 'paste' ? 'bg-[#f5f3f0] text-[#3a3529] border-b-2 border-[#4a4337]' : 'text-gray-500 hover:bg-gray-50'}`}>
                    <ClipboardPaste className="w-4 h-4" /> Paste Script
                  </button>
                </div>

                {labelInputMode === 'upload' ? (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Upload Label File</label>
                    <input type="file" accept=".zpl,.png,.jpg,.jpeg,.pdf,.txt"
                      onChange={(e) => { setLabelFile(e.target.files?.[0] || null); resetLabelState(); }} className="w-full" />
                  </div>
                ) : (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Paste Label Script (ZPL, text, etc.)</label>
                    <textarea value={labelPasteText} onChange={(e) => { setLabelPasteText(e.target.value); resetLabelState(); }}
                      placeholder={"Paste your ZPL or label script here...\n\nExample:\n^XA\n^FO50,50^A0N,30,30^FDHello World^FS\n^XZ"}
                      className="w-full min-h-[160px] px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm focus:ring-2 focus:ring-[#4a4337] focus:border-transparent resize-y" />
                    {labelPasteText.trim() && (
                      <p className="mt-1 text-xs text-gray-500">
                        {labelPasteText.length} characters • {labelPasteText.includes('^XA') ? ' ZPL detected' : ' Plain text'}
                      </p>
                    )}
                  </div>
                )}

                <button onClick={handleLabelDetect} disabled={!labelHasInput || labelBusy || !!labelDetection}
                  className="w-full bg-[#4a4337] text-white py-3 rounded-lg font-medium hover:bg-[#3a3529] disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2">
                  {labelValidating ? <><Loader2 className="w-5 h-5 animate-spin" /> Validating...</>
                    : labelDetecting ? <><Loader2 className="w-5 h-5 animate-spin" /> Detecting carrier...</>
                    : 'Validate Label'}
                </button>
              </div>
            </div>

            {(labelDetecting || labelDetection || labelDetectError) && (
              <CarrierConfirmation detectionResult={labelDetection} loading={labelDetecting} error={labelDetectError}
                onConfirm={handleLabelConfirm} onCancel={handleLabelCancel} onRetry={handleLabelDetect} type="label" />
            )}

            {labelConfirmed && !labelDetection && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <CheckCircle className="w-5 h-5 text-green-600" />
                  <span className="text-green-800">Validating against: <strong>{labelConfirmed.carrierName}</strong></span>
                </div>
                <button onClick={() => { setLabelConfirmed(null); handleLabelDetect(); }} className="text-sm text-green-700 hover:text-green-900 underline">Change</button>
              </div>
            )}

            {/* ═══ Label Results — WITH FEEDBACK ═══ */}
            {labelResult && (
              <div className="bg-white rounded-lg shadow p-6 space-y-4">
                <div className={`p-4 rounded-lg ${labelResult.status === 'PASS' ? 'bg-green-50' : 'bg-red-50'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    {labelResult.status === 'PASS'
                      ? <CheckCircle className="w-5 h-5 text-green-600" />
                      : <AlertCircle className="w-5 h-5 text-red-600" />}
                    <span className={`font-semibold ${labelResult.status === 'PASS' ? 'text-green-800' : 'text-red-800'}`}>
                      {labelResult.status}
                    </span>
                  </div>
                  <p className="text-sm">
                    {labelResult.status === 'PASS'
                      ? 'Label is valid and ready to use.'
                      : `${labelResult.errors.length} issue(s) found. Please review below.`}
                  </p>
                </div>

                {/* CHANGED: Error rows now have "This is wrong" button */}
                {labelResult.errors?.length > 0 && (
                  <div>
                    <h3 className="font-medium mb-2">Errors Found:</h3>
                    <div className="space-y-2 max-h-64 overflow-auto">
                      {labelResult.errors.map((error, idx) => (
                        <ErrorWithFeedback
                          key={idx}
                          error={error}
                          carrier={labelConfirmed?.carrierName || 'unknown'}
                          onCorrected={(f) => setLabelCorrectedFields(p => new Set([...p, f]))}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* NEW: Learning summary */}
                {labelCorrectedFields.size > 0 && (
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-start gap-2">
                    <Sparkles className="w-4 h-4 text-blue-600 mt-0.5 shrink-0" />
                    <p className="text-xs text-blue-800">
                      {labelCorrectedFields.size} error{labelCorrectedFields.size > 1 ? 's' : ''} marked as incorrect — the system has learned and won't repeat {labelCorrectedFields.size > 1 ? 'them' : 'it'}.
                    </p>
                  </div>
                )}

                {/* NEW: Report missing check */}
                <ReportMissingCheck
                  carrier={labelConfirmed?.carrierName || 'unknown'}
                  onAdded={(f) => setLabelAddedFields(p => [...p, f])}
                />

                {/* NEW: Added fields confirmation */}
                {labelAddedFields.length > 0 && (
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
                    <Sparkles className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
                    <p className="text-xs text-amber-800">
                      {labelAddedFields.map(f => `"${f}"`).join(', ')} will now be enforced for all future {labelConfirmed?.carrierName} validations.
                    </p>
                  </div>
                )}

                {/* NEW: Re-validate button */}
                {labelHasChanges && (
                  <button onClick={handleLabelRevalidate}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-[#4a4337] text-white rounded-lg font-medium hover:bg-[#3a3529]">
                    <RefreshCw className="w-4 h-4" /> Re-validate with learned corrections
                  </button>
                )}

                {labelResult.corrected_label_script && (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-medium">Corrected Label Script</h3>
                      <button onClick={() => copyToClipboard(labelResult.corrected_label_script!, 'label')}
                        className="flex items-center gap-2 px-3 py-1 bg-gray-100 hover:bg-gray-200 rounded text-sm">
                        {copied === 'label' ? <><CheckCircle className="w-4 h-4" /> Copied!</> : <><Copy className="w-4 h-4" /> Copy</>}
                      </button>
                    </div>
                    <pre className="bg-gray-100 p-4 rounded text-sm overflow-x-auto max-h-64">{labelResult.corrected_label_script}</pre>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ═══ EDI Validation ═══ */}
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <FileCheck className="w-5 h-5" /> EDI Validation
              </h2>
              <div className="space-y-4">
                <div className="flex rounded-lg border border-gray-200 overflow-hidden">
                  <button onClick={() => setEdiInputMode('upload')}
                    className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors ${ediInputMode === 'upload' ? 'bg-[#f5f3f0] text-[#3a3529] border-b-2 border-[#4a4337]' : 'text-gray-500 hover:bg-gray-50'}`}>
                    <Upload className="w-4 h-4" /> Upload File
                  </button>
                  <button onClick={() => setEdiInputMode('paste')}
                    className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors ${ediInputMode === 'paste' ? 'bg-[#f5f3f0] text-[#3a3529] border-b-2 border-[#4a4337]' : 'text-gray-500 hover:bg-gray-50'}`}>
                    <ClipboardPaste className="w-4 h-4" /> Paste Script
                  </button>
                </div>

                {ediInputMode === 'upload' ? (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Upload EDI File</label>
                    <input type="file" accept=".edi,.txt,.json,.xml,.csv"
                      onChange={(e) => { setEdiFile(e.target.files?.[0] || null); resetEdiState(); }} className="w-full" />
                  </div>
                ) : (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Paste EDI Content (X12, EDIFACT, JSON, XML)</label>
                    <textarea value={ediPasteText} onChange={(e) => { setEdiPasteText(e.target.value); resetEdiState(); }}
                      placeholder={"Paste your EDI content here...\n\nExample X12:\nISA*00*          *00*          *ZZ*SENDER...~"}
                      className="w-full min-h-[160px] px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm focus:ring-2 focus:ring-[#4a4337] focus:border-transparent resize-y" />
                    {ediPasteText.trim() && (
                      <p className="mt-1 text-xs text-gray-500">
                        {ediPasteText.length} characters •
                        {ediPasteText.includes('~') && ediPasteText.includes('*') ? ' X12 detected' :
                         ediPasteText.includes("'") && ediPasteText.includes('+') ? ' EDIFACT detected' :
                         ediPasteText.trim().startsWith('{') ? ' JSON detected' :
                         ediPasteText.trim().startsWith('<') ? ' XML detected' : ' Plain text'}
                      </p>
                    )}
                  </div>
                )}

                <button onClick={handleEdiDetect} disabled={!ediHasInput || ediBusy || !!ediDetection}
                  className="w-full bg-[#4a4337] text-white py-3 rounded-lg font-medium hover:bg-[#3a3529] disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2">
                  {ediValidating ? <><Loader2 className="w-5 h-5 animate-spin" /> Validating...</>
                    : ediDetecting ? <><Loader2 className="w-5 h-5 animate-spin" /> Detecting carrier...</>
                    : 'Validate EDI'}
                </button>
              </div>
            </div>

            {(ediDetecting || ediDetection || ediDetectError) && (
              <CarrierConfirmation detectionResult={ediDetection} loading={ediDetecting} error={ediDetectError}
                onConfirm={handleEdiConfirm} onCancel={handleEdiCancel} onRetry={handleEdiDetect} type="edi" />
            )}

            {ediConfirmed && !ediDetection && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <CheckCircle className="w-5 h-5 text-green-600" />
                  <span className="text-green-800">Validating against: <strong>{ediConfirmed.carrierName}</strong></span>
                </div>
                <button onClick={() => { setEdiConfirmed(null); handleEdiDetect(); }} className="text-sm text-green-700 hover:text-green-900 underline">Change</button>
              </div>
            )}

            {/* ═══ EDI Results — WITH FEEDBACK ═══ */}
            {ediResult && (
              <div className="bg-white rounded-lg shadow p-6 space-y-4">
                <div className={`p-4 rounded-lg ${ediResult.status === 'PASS' ? 'bg-green-50' : 'bg-red-50'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    {ediResult.status === 'PASS'
                      ? <CheckCircle className="w-5 h-5 text-green-600" />
                      : <AlertCircle className="w-5 h-5 text-red-600" />}
                    <span className={`font-semibold ${ediResult.status === 'PASS' ? 'text-green-800' : 'text-red-800'}`}>
                      {ediResult.status}
                    </span>
                  </div>
                  <p className="text-sm">Compliance Score: {(ediResult.compliance_score * 100).toFixed(1)}%</p>
                </div>

                {/* CHANGED: Error rows now have "This is wrong" button */}
                {ediResult.errors?.length > 0 && (
                  <div>
                    <h3 className="font-medium mb-2">Errors Found:</h3>
                    <div className="space-y-2 max-h-64 overflow-auto">
                      {ediResult.errors.map((error, idx) => (
                        <ErrorWithFeedback
                          key={idx}
                          error={error}
                          carrier={ediConfirmed?.carrierName || 'unknown'}
                          onCorrected={(f) => setEdiCorrectedFields(p => new Set([...p, f]))}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {ediCorrectedFields.size > 0 && (
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-start gap-2">
                    <Sparkles className="w-4 h-4 text-blue-600 mt-0.5 shrink-0" />
                    <p className="text-xs text-blue-800">
                      {ediCorrectedFields.size} error{ediCorrectedFields.size > 1 ? 's' : ''} marked as incorrect — the system has learned.
                    </p>
                  </div>
                )}

                <ReportMissingCheck
                  carrier={ediConfirmed?.carrierName || 'unknown'}
                  onAdded={(f) => setEdiAddedFields(p => [...p, f])}
                />

                {ediAddedFields.length > 0 && (
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
                    <Sparkles className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
                    <p className="text-xs text-amber-800">
                      {ediAddedFields.map(f => `"${f}"`).join(', ')} will now be enforced for all future {ediConfirmed?.carrierName} validations.
                    </p>
                  </div>
                )}

                {ediHasChanges && (
                  <button onClick={handleEdiRevalidate}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-[#4a4337] text-white rounded-lg font-medium hover:bg-[#3a3529]">
                    <RefreshCw className="w-4 h-4" /> Re-validate with learned corrections
                  </button>
                )}

                {ediResult.corrected_edi_script && (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-medium">Corrected EDI Script</h3>
                      <button onClick={() => copyToClipboard(ediResult.corrected_edi_script!, 'edi')}
                        className="flex items-center gap-2 px-3 py-1 bg-gray-100 hover:bg-gray-200 rounded text-sm">
                        {copied === 'edi' ? <><CheckCircle className="w-4 h-4" /> Copied!</> : <><Copy className="w-4 h-4" /> Copy</>}
                      </button>
                    </div>
                    <pre className="bg-gray-100 p-4 rounded text-sm overflow-x-auto max-h-64">{ediResult.corrected_edi_script}</pre>
                  </div>
                )}
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}