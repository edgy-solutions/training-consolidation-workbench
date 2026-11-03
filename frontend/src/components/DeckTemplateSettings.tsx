import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Circle, Loader2, RotateCcw, Upload, X } from 'lucide-react';
import clsx from 'clsx';
import axios from 'axios';
import { toast } from 'sonner';
import { api } from '../api';
import type {
    DeckTemplateSettings as Settings,
    FieldMapping,
    RoleMapping,
    TemplateInspection,
    TemplateLayout,
    TemplatePlaceholder,
} from '../api';

const NOTES_PAGE = 'notes-page';
const MISSING = 'missing'; // the select's value for a saved layout the template does not have

const FIELD_COLORS: Record<string, string> = {
    title: '#2563eb',
    body: '#0d9488',
    citation: '#d97706',
    image: '#9333ea',
    notes: '#db2777',
};

const FIELD_HINTS: Record<string, string> = {
    title: 'Slide title',
    body: 'Body text (the subtitle on a title slide)',
    citation: 'Source citation line',
    image: 'The figure; needs a picture or object placeholder',
    notes: 'Speaker notes',
};

interface Props {
    onClose: () => void;
}

const errorMessage = (err: unknown): { message: string; problems: string[] } => {
    if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        if (detail && typeof detail === 'object' && Array.isArray(detail.problems)) {
            return { message: 'The template was not saved.', problems: detail.problems };
        }
        if (typeof detail === 'string') return { message: detail, problems: [detail] };
    }
    const message = err instanceof Error ? err.message : 'Request failed';
    return { message, problems: [message] };
};

const fieldsOf = (spec: Settings['role_spec'][string]) => [...spec.required, ...spec.optional];

/** A convenience only: the server validates whatever is sent. */
const prefill = (layout: TemplateLayout, spec: Settings['role_spec'][string]): FieldMapping => {
    const phs = layout.placeholders.filter(p => p.mappable);
    const taken = new Set<number>();
    const pick = (types: string[], filter: (p: TemplatePlaceholder) => boolean = () => true) => {
        for (const t of types) {
            const p = phs.find(q => q.type === t && !taken.has(q.idx) && filter(q));
            if (p) {
                taken.add(p.idx);
                return p.idx;
            }
        }
        return undefined;
    };
    const out: FieldMapping = {};
    const want = (f: string) => spec.required.includes(f);
    if (want('title')) {
        const v = pick(['TITLE', 'CENTER_TITLE']);
        if (v !== undefined) out.title = v;
    }
    if (want('image')) {
        const v = pick(['PICTURE', 'OBJECT'], p => p.accepts_image);
        if (v !== undefined) out.image = v;
    }
    if (want('body')) {
        const v = pick(['BODY', 'OBJECT', 'SUBTITLE']);
        if (v !== undefined) out.body = v;
    }
    if (want('citation')) {
        const v = pick(['BODY', 'OBJECT', 'SUBTITLE']);
        if (v !== undefined) out.citation = v;
    }
    if (fieldsOf(spec).includes('notes')) out.notes = NOTES_PAGE;
    return out;
};

/** The layout a role uses: its layout_index when that position still holds the named layout, else the first with the name. */
const resolveLayout = (inspection: TemplateInspection, m?: RoleMapping[string]): TemplateLayout | undefined => {
    if (!m?.layout) return undefined;
    const at = m.layout_index === undefined ? undefined : inspection.layouts[m.layout_index];
    return at && at.name === m.layout ? at : inspection.layouts.find(l => l.name === m.layout);
};

const isComplete = (
    role: string,
    roles: RoleMapping,
    spec: Settings['role_spec'],
    inspection: TemplateInspection,
) => {
    const m = roles[role];
    if (!m?.layout) return false;
    const layout = resolveLayout(inspection, m);
    if (!layout) return false;
    const idxs = new Set(layout.placeholders.map(p => p.idx));
    return spec[role].required.every(f => {
        const v = m.placeholders[f];
        return typeof v === 'number' && idxs.has(v);
    });
};

/** Drops role choices that the (new) template cannot honour. */
const reconcile = (roles: RoleMapping, inspection: TemplateInspection): RoleMapping => {
    const out: RoleMapping = {};
    for (const [role, m] of Object.entries(roles)) {
        const layout = resolveLayout(inspection, m);
        if (!layout) continue;
        const kept: FieldMapping = {};
        for (const [f, v] of Object.entries(m.placeholders)) {
            if (typeof v !== 'number') {
                kept[f] = v;
                continue;
            }
            const ph = layout.placeholders.find(p => p.idx === v);
            if (ph && ph.mappable && (f !== 'image' || ph.accepts_image)) kept[f] = v;
        }
        out[role] = { layout: m.layout, placeholders: kept };
        if (layout.name_count > 1) out[role].layout_index = layout.index;
    }
    return out;
};

const Blueprint: React.FC<{
    inspection: TemplateInspection;
    layout: TemplateLayout;
    mapping: FieldMapping;
}> = ({ inspection, layout, mapping }) => {
    const { slide_width: W, slide_height: H } = inspection;
    const fieldOf = (idx: number) => Object.entries(mapping).find(([, v]) => v === idx)?.[0];
    const drawn = layout.placeholders.filter(p => p.left != null && p.top != null && p.width != null && p.height != null);
    const undrawn = layout.placeholders.filter(p => !drawn.includes(p));
    const font = H * 0.032;

    return (
        <div>
            <svg
                viewBox={`0 0 ${W} ${H}`}
                className="w-full bg-white border border-slate-300 rounded shadow-sm"
                role="img"
                aria-label={`Blueprint of layout ${layout.name}`}
            >
                {drawn.map(p => {
                    const field = fieldOf(p.idx);
                    const color = !p.mappable ? '#94a3b8' : field ? FIELD_COLORS[field] ?? '#475569' : '#cbd5e1';
                    return (
                        <g key={p.idx}>
                            <title>{`${p.idx} · ${p.name} (${p.type})${field ? ` -> ${field}` : ''}${p.mappable ? '' : ' (cannot be filled)'}`}</title>
                            <rect
                                x={p.left!} y={p.top!} width={p.width!} height={p.height!}
                                fill={color} fillOpacity={p.mappable ? (field ? 0.22 : 0.12) : 0.08}
                                stroke={color} strokeWidth={2} strokeDasharray={p.mappable ? undefined : '6 4'}
                                vectorEffect="non-scaling-stroke"
                            />
                            <svg x={p.left!} y={p.top!} width={p.width!} height={p.height!} overflow="hidden">
                                <text x={font * 0.4} y={font * 1.3} fontSize={font} fill="#0f172a" fillOpacity={p.mappable ? 1 : 0.5}>
                                    {p.idx} · {p.name}
                                </text>
                                {field && (
                                    <text x={font * 0.4} y={font * 2.6} fontSize={font} fontWeight="bold" fill={color}>
                                        {field}
                                    </text>
                                )}
                            </svg>
                        </g>
                    );
                })}
            </svg>
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-slate-600">
                {Object.entries(FIELD_COLORS).map(([f, c]) => (
                    <span key={f} className="flex items-center gap-1">
                        <span className="inline-block w-3 h-3 rounded-sm" style={{ background: c }} />
                        {f}
                    </span>
                ))}
                <span className="flex items-center gap-1">
                    <span className="inline-block w-3 h-3 rounded-sm border border-dashed border-slate-400 bg-slate-100" />
                    cannot be filled (date, footer, slide number)
                </span>
            </div>
            {undrawn.length > 0 && (
                <div className="mt-3 text-xs text-slate-600">
                    <div className="font-semibold">Placeholders with no position in the layout</div>
                    <ul className="list-disc pl-5">
                        {undrawn.map(p => (
                            <li key={p.idx}>
                                {p.idx} · {p.name} ({p.type})
                                {fieldOf(p.idx) ? ` -> ${fieldOf(p.idx)}` : ''}
                                {p.mappable ? '' : ' - cannot be filled'}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
};

export const DeckTemplateSettings: React.FC<Props> = ({ onClose }) => {
    const [settings, setSettings] = useState<Settings | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [draftFile, setDraftFile] = useState<File | null>(null);
    const [draftInspection, setDraftInspection] = useState<TemplateInspection | null>(null);
    const [roles, setRoles] = useState<RoleMapping>({});
    const [selected, setSelected] = useState<string>('title');
    const [problems, setProblems] = useState<string[]>([]);
    const [busy, setBusy] = useState<'upload' | 'save' | 'reset' | null>(null);
    const fileInput = useRef<HTMLInputElement>(null);

    const adopt = useCallback((s: Settings) => {
        setSettings(s);
        setDraftFile(null);
        setDraftInspection(null);
        setRoles(JSON.parse(JSON.stringify(s.roles)));
        setProblems([]);
    }, []);

    useEffect(() => {
        api.getDeckTemplate()
            .then(adopt)
            .catch(err => setLoadError(errorMessage(err).message));
    }, [adopt]);

    const inspection = draftInspection ?? settings?.template ?? null;
    const spec = settings?.role_spec ?? {};
    const roleNames = Object.keys(spec);
    const canEdit = !!settings && settings.store_enabled && settings.can_configure;
    const allComplete = !!inspection && roleNames.length > 0 && roleNames.every(r => isComplete(r, roles, spec, inspection));
    // The stand-in and a deployment's template can't be re-saved from here: the server keeps no .pptx for them.
    const hasPptx = !!draftFile || settings?.source === 'saved';
    const dirty = !!settings && (!!draftFile || JSON.stringify(roles) !== JSON.stringify(settings.roles));

    const requestClose = useCallback(() => {
        if (dirty && !window.confirm('Discard your unsaved template changes?')) return;
        onClose();
    }, [dirty, onClose]);

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') requestClose();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [requestClose]);

    const mapping = roles[selected];
    const roleSpec = spec[selected];
    const layout = inspection ? resolveLayout(inspection, mapping) : undefined;

    const setLayout = (index: string) => {
        const next = inspection?.layouts[Number(index)];
        if (index === '' || !next || !roleSpec) return;
        const chosen: RoleMapping[string] = { layout: next.name, placeholders: prefill(next, roleSpec) };
        if (next.name_count > 1) chosen.layout_index = next.index;
        setRoles(r => ({ ...r, [selected]: chosen }));
    };

    // n of count among the layouts that share a name, in template order
    const nameOrder = (l: TemplateLayout) =>
        inspection ? inspection.layouts.filter(o => o.name === l.name && o.index <= l.index).length : 1;

    const setField = (field: string, value: string) => {
        setRoles(r => {
            const cur = r[selected] ?? { layout: '', placeholders: {} };
            const placeholders = { ...cur.placeholders };
            if (value === '') delete placeholders[field];
            else placeholders[field] = value === NOTES_PAGE ? NOTES_PAGE : Number(value);
            return { ...r, [selected]: { ...cur, placeholders } };
        });
    };

    const onFile = async (file: File | undefined) => {
        if (!file) return;
        setBusy('upload');
        try {
            const inspected = await api.inspectDeckTemplate(file);
            setDraftFile(file);
            setDraftInspection(inspected);
            setRoles(r => reconcile(r, inspected));
            setProblems([]);
            toast.success(`${file.name} loaded as an unsaved draft`);
        } catch (err) {
            toast.error(errorMessage(err).message);
        } finally {
            setBusy(null);
            if (fileInput.current) fileInput.current.value = '';
        }
    };

    const save = async () => {
        setBusy('save');
        setProblems([]);
        try {
            adopt(await api.saveDeckTemplate(roles, draftFile));
            toast.success('Deck template saved');
        } catch (err) {
            const e = errorMessage(err);
            setProblems(e.problems);
            toast.error(e.message);
        } finally {
            setBusy(null);
        }
    };

    const reset = async () => {
        if (!window.confirm('Reset to the deployment default? Exports will stop using the saved template.')) return;
        setBusy('reset');
        try {
            adopt(await api.resetDeckTemplate());
            toast.success('Back to the deployment default');
        } catch (err) {
            toast.error(errorMessage(err).message);
        } finally {
            setBusy(null);
        }
    };

    const inForce = useMemo(() => {
        if (!settings) return '';
        if (settings.source === 'saved') {
            const when = settings.saved_at ? new Date(settings.saved_at).toLocaleString() : '';
            return [settings.filename, settings.saved_by && `saved by ${settings.saved_by}`, when].filter(Boolean).join(' · ');
        }
        return settings.source === 'deployment' ? 'Set by deployment' : 'Stand-in';
    }, [settings]);

    const optionLabel = (p: TemplatePlaceholder) => `${p.idx} · ${p.name} (${p.type})`;

    const fieldOptions = (field: string) => {
        if (!layout) return [];
        const usedByOthers = new Set(
            Object.entries(mapping?.placeholders ?? {})
                .filter(([f, v]) => f !== field && typeof v === 'number')
                .map(([, v]) => v as number),
        );
        return layout.placeholders
            .filter(p => p.mappable && (field !== 'image' || p.accepts_image))
            .map(p => ({ p, taken: usedByOthers.has(p.idx) }));
    };

    return (
        <div
            className="fixed inset-0 z-[100] bg-black/50 flex items-center justify-center p-4"
            onClick={requestClose}
        >
            <div
                role="dialog"
                aria-modal="true"
                aria-label="Deck template settings"
                className="bg-white rounded-xl shadow-2xl w-full max-w-6xl max-h-[92vh] flex flex-col text-slate-800"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-slate-200">
                    <div className="min-w-0">
                        <h2 className="text-lg font-semibold">Deck template</h2>
                        {settings && (
                            <p className="text-sm text-slate-600 truncate" title={inForce}>
                                In force: <span className="font-medium">{inForce}</span>
                                {draftFile && <span className="ml-2 text-amber-700">Unsaved draft: {draftFile.name}</span>}
                            </p>
                        )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                        <input
                            ref={fileInput}
                            type="file"
                            accept=".pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation"
                            className="hidden"
                            onChange={e => onFile(e.target.files?.[0])}
                        />
                        <button
                            disabled={!canEdit || busy !== null}
                            onClick={() => fileInput.current?.click()}
                            className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-md border border-slate-300 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {busy === 'upload' ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                            Upload a .pptx
                        </button>
                        {settings?.source === 'saved' && (
                            <button
                                disabled={!canEdit || busy !== null}
                                onClick={reset}
                                className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-md border border-slate-300 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <RotateCcw size={14} />
                                Reset to deployment default
                            </button>
                        )}
                        <button onClick={requestClose} aria-label="Close" className="p-1.5 rounded-md hover:bg-slate-100">
                            <X size={18} />
                        </button>
                    </div>
                </div>

                {settings && !settings.store_enabled && (
                    <div className="px-5 py-2 text-sm bg-amber-50 text-amber-900 border-b border-amber-200">
                        Saving a template needs <code>DECK_TEMPLATE_STORE</code> to be set on the API. The current mapping is shown read-only.
                    </div>
                )}
                {settings && settings.store_enabled && !settings.can_configure && (
                    <div className="px-5 py-2 text-sm bg-amber-50 text-amber-900 border-b border-amber-200">
                        You do not have permission to change the deck template. The current mapping is shown read-only.
                    </div>
                )}

                {loadError && <div className="p-6 text-sm text-red-700">Could not load the deck template: {loadError}</div>}
                {!settings && !loadError && (
                    <div className="p-6 flex items-center gap-2 text-sm text-slate-600">
                        <Loader2 size={16} className="animate-spin" /> Loading
                    </div>
                )}

                {settings && inspection && (
                    <div className="flex flex-1 min-h-0">
                        <div className="w-56 shrink-0 border-r border-slate-200 overflow-y-auto p-2">
                            {roleNames.map(r => {
                                const ok = isComplete(r, roles, spec, inspection);
                                return (
                                    <button
                                        key={r}
                                        onClick={() => setSelected(r)}
                                        className={clsx(
                                            'w-full flex items-center justify-between gap-2 px-3 py-2 rounded-md text-sm text-left',
                                            selected === r ? 'bg-brand-teal/10 font-medium' : 'hover:bg-slate-50',
                                        )}
                                    >
                                        <span>{r}</span>
                                        {ok ? (
                                            <span className="flex items-center gap-1 text-xs text-emerald-700">
                                                <CheckCircle2 size={14} /> mapped
                                            </span>
                                        ) : (
                                            <span className="flex items-center gap-1 text-xs text-slate-500">
                                                <Circle size={14} /> unmapped
                                            </span>
                                        )}
                                    </button>
                                );
                            })}
                        </div>

                        <div className="w-80 shrink-0 border-r border-slate-200 overflow-y-auto p-4 space-y-4">
                            <div>
                                <label htmlFor="dts-layout" className="block text-xs font-semibold text-slate-600 mb-1">
                                    Layout for {selected}
                                </label>
                                <select
                                    id="dts-layout"
                                    disabled={!canEdit}
                                    value={layout ? String(layout.index) : mapping?.layout ? MISSING : ''}
                                    onChange={e => setLayout(e.target.value)}
                                    className="w-full border border-slate-300 rounded-md px-2 py-1.5 text-sm disabled:bg-slate-50"
                                >
                                    <option value="">Choose a layout</option>
                                    {mapping?.layout && !layout && (
                                        <option value={MISSING} disabled>
                                            {mapping.layout} (not in this template)
                                        </option>
                                    )}
                                    {inspection.layouts.map(l => (
                                        <option key={l.index} value={String(l.index)}>
                                            {l.name}
                                            {l.name_count > 1 ? ` (${nameOrder(l)} of ${l.name_count} with this name)` : ''}
                                        </option>
                                    ))}
                                </select>
                                {layout && layout.name_count > 1 && (
                                    <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1 mt-1">
                                        {layout.name_count} layouts are named "{layout.name}". This role uses the one you picked;
                                        renaming them in PowerPoint would make this clearer.
                                    </p>
                                )}
                            </div>

                            {layout && roleSpec &&
                                fieldsOf(roleSpec).map(field => {
                                    const required = roleSpec.required.includes(field);
                                    const value = mapping?.placeholders[field];
                                    return (
                                        <div key={field}>
                                            <label htmlFor={`dts-${field}`} className="block text-xs font-semibold text-slate-600 mb-1">
                                                <span className="inline-block w-2.5 h-2.5 rounded-sm mr-1.5" style={{ background: FIELD_COLORS[field] }} />
                                                {field}
                                                {required ? ' (required)' : ' (optional)'}
                                            </label>
                                            <select
                                                id={`dts-${field}`}
                                                disabled={!canEdit}
                                                value={value === undefined ? (field === 'notes' ? NOTES_PAGE : '') : String(value)}
                                                onChange={e => setField(field, e.target.value)}
                                                className="w-full border border-slate-300 rounded-md px-2 py-1.5 text-sm disabled:bg-slate-50"
                                            >
                                                {!required && field !== 'notes' && <option value="">(none)</option>}
                                                {required && <option value="">Choose a placeholder</option>}
                                                {field === 'notes' && <option value={NOTES_PAGE}>Speaker notes page</option>}
                                                {fieldOptions(field).map(({ p, taken }) => (
                                                    <option key={p.idx} value={p.idx} disabled={taken}>
                                                        {optionLabel(p)}
                                                        {taken ? ' - used by another field' : ''}
                                                    </option>
                                                ))}
                                            </select>
                                            <p className="text-xs text-slate-500 mt-0.5">{FIELD_HINTS[field]}</p>
                                        </div>
                                    );
                                })}
                        </div>

                        <div className="flex-1 min-w-0 overflow-y-auto p-4">
                            {layout ? (
                                <Blueprint inspection={inspection} layout={layout} mapping={mapping?.placeholders ?? {}} />
                            ) : (
                                <p className="text-sm text-slate-500">Choose a layout to see its blueprint.</p>
                            )}
                        </div>
                    </div>
                )}

                {settings && settings.warnings.length > 0 && (
                    <div className="px-5 py-3 border-t border-amber-200 bg-amber-50 text-sm text-amber-900 max-h-32 overflow-y-auto">
                        <div className="flex items-center gap-2 font-semibold">
                            <AlertTriangle size={14} /> Worth a look (this does not stop a save or an export)
                        </div>
                        <ul className="list-disc pl-6 mt-1">
                            {settings.warnings.map((w, i) => (
                                <li key={i}>{w}</li>
                            ))}
                        </ul>
                    </div>
                )}

                {problems.length > 0 && (
                    <div className="px-5 py-3 border-t border-red-200 bg-red-50 text-sm text-red-800 max-h-40 overflow-y-auto" role="alert">
                        <div className="flex items-center gap-2 font-semibold">
                            <AlertTriangle size={14} /> The server refused this template
                        </div>
                        <ul className="list-disc pl-6 mt-1">
                            {problems.map((p, i) => (
                                <li key={i}>{p}</li>
                            ))}
                        </ul>
                    </div>
                )}

                <div className="flex items-center justify-between gap-3 px-5 py-3 border-t border-slate-200">
                    <span className="text-xs text-slate-500">
                        {canEdit && !hasPptx && 'Upload a .pptx to replace this template.'}
                        {canEdit && hasPptx && !allComplete && 'Every role needs a layout and all its required fields before this can be saved.'}
                    </span>
                    <div className="flex items-center gap-2">
                        <button onClick={requestClose} className="px-3 py-1.5 text-sm rounded-md border border-slate-300 hover:bg-slate-50">
                            Close
                        </button>
                        <button
                            disabled={!canEdit || !hasPptx || !allComplete || busy !== null}
                            onClick={save}
                            className="flex items-center gap-2 px-4 py-1.5 text-sm rounded-md bg-brand-teal text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {busy === 'save' && <Loader2 size={14} className="animate-spin" />}
                            Save
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};
