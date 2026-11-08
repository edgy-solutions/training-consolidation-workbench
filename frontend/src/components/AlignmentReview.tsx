import React, { useEffect, useState } from 'react';
import { AlertTriangle, Check, Loader2, X } from 'lucide-react';
import { toast } from 'sonner';
import { api, httpError } from '../api';
import type { AlignmentProposal } from '../api';

interface Props {
    // False when the api holds writes to the shared graph (WB_STORE_WRITES): the list shows, decisions don't.
    writesEnabled: boolean;
    onClose: () => void;
}

const MEMBERS_SHOWN = 4;

const errorText = (e: unknown, fallback: string) => {
    const { status, detail } = httpError(e);
    if (typeof detail === 'string') return detail;
    return status ? `${fallback} (HTTP ${status})` : fallback;
};

const rowKey = (p: AlignmentProposal) => `${p.concept_id}|${p.canonical_id}`;

export const AlignmentReview: React.FC<Props> = ({ writesEnabled, onClose }) => {
    const [courses, setCourses] = useState<{ id: string; name: string }[] | null>(null);
    const [courseId, setCourseId] = useState('');
    const [proposals, setProposals] = useState<AlignmentProposal[] | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    // Per row: the key being decided, and the last refusal shown inline.
    const [pending, setPending] = useState<Set<string>>(new Set());
    const [rowErrors, setRowErrors] = useState<Record<string, string>>({});

    // The same course list the source browser shows: every course under every business unit.
    useEffect(() => {
        api.getSourceTree()
            .then(tree => {
                const list = tree.flatMap(n => (n.type === 'Course' ? [n] : n.children ?? []));
                setCourses(list.map(c => ({ id: c.id, name: c.name })));
                if (list.length) setCourseId(list[0].id);
            })
            .catch(err => {
                console.error("Failed to load courses", err);
                setLoadError(errorText(err, 'Could not load the courses.'));
            });
    }, []);

    useEffect(() => {
        if (!courseId) return;
        let stale = false;
        setProposals(null);
        setLoadError(null);
        setRowErrors({});
        api.getAlignmentProposals(courseId)
            .then(rows => { if (!stale) setProposals(rows); })
            .catch(err => {
                console.error("Failed to load proposals", err);
                if (!stale) setLoadError(errorText(err, 'Could not load the proposals.'));
            });
        return () => { stale = true; };
    }, [courseId]);

    const decide = async (p: AlignmentProposal, decision: 'accept' | 'reject') => {
        const key = rowKey(p);
        setPending(s => new Set(s).add(key));
        setRowErrors(e => { const { [key]: _, ...rest } = e; return rest; });
        try {
            await api.reviewAlignmentProposal(p.concept_id, p.canonical_id, decision);
            setProposals(rows => (rows ?? []).filter(r => rowKey(r) !== key));
            toast.success(`${decision === 'accept' ? 'Accepted' : 'Rejected'}: ${p.concept} → ${p.canonical}`);
        } catch (err) {
            setRowErrors(e => ({ ...e, [key]: errorText(err, 'The review failed.') }));
        } finally {
            setPending(s => { const n = new Set(s); n.delete(key); return n; });
        }
    };

    return (
        <div className="fixed inset-0 z-[100] bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
            <div
                role="dialog"
                aria-modal="true"
                aria-label="Review alignment proposals"
                className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[92vh] flex flex-col text-slate-800"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-slate-200">
                    <div className="min-w-0">
                        <h2 className="text-lg font-semibold">Alignment review</h2>
                        <p className="text-sm text-slate-600">Open proposals that fold a course concept into a canonical one.</p>
                    </div>
                    <button type="button" aria-label="Close" onClick={onClose} className="text-slate-500 hover:text-slate-800">
                        <X size={18} />
                    </button>
                </div>

                <div className="px-5 py-3 border-b border-slate-200 flex items-center gap-3">
                    <label htmlFor="review-course" className="text-sm font-medium">Course</label>
                    <select
                        id="review-course"
                        value={courseId}
                        onChange={e => setCourseId(e.target.value)}
                        disabled={!courses?.length}
                        className="flex-1 min-w-0 border border-slate-300 rounded-md px-2 py-1.5 text-sm"
                    >
                        {(courses ?? []).map(c => (
                            <option key={c.id} value={c.id}>{c.name}</option>
                        ))}
                    </select>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto p-5 space-y-3">
                    {!writesEnabled && (
                        <div className="text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded-md px-3 py-2" role="status">
                            Read-only: writes to the shared graph are off on this deployment, so decisions can't be saved.
                        </div>
                    )}
                    {loadError && (
                        <div className="flex items-center gap-2 text-sm text-red-800 bg-red-50 border border-red-200 rounded-md px-3 py-2" role="alert">
                            <AlertTriangle size={14} /> {loadError}
                        </div>
                    )}
                    {!loadError && courses && !courses.length && <p className="text-sm text-slate-500">No courses.</p>}
                    {!loadError && courseId && proposals === null && (
                        <p className="flex items-center gap-2 text-sm text-slate-500"><Loader2 size={14} className="animate-spin" /> Loading proposals</p>
                    )}
                    {!loadError && proposals?.length === 0 && (
                        <p className="text-sm text-slate-500">No open proposals for this course.</p>
                    )}
                    {proposals?.map(p => {
                        const key = rowKey(p);
                        const busy = pending.has(key);
                        const locked = busy || !writesEnabled;
                        const members = p.members ?? [];
                        const meta = [
                            `${p.shared ?? 0} shared slides`,
                            p.confidence != null ? `confidence ${p.confidence}` : null,
                            p.method,
                        ].filter(Boolean).join(' · ');
                        return (
                            <div key={key} className="border border-slate-200 rounded-lg px-4 py-3">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <div className="text-sm font-medium">{p.concept} <span className="text-slate-400">{'→'}</span> {p.canonical}</div>
                                        <div className="text-xs text-slate-600 mt-0.5">{meta}</div>
                                        {members.length > 0 && (
                                            <div className="text-xs text-slate-400 mt-0.5 truncate" title={members.join(', ')}>
                                                {members.slice(0, MEMBERS_SHOWN).join(', ')}
                                                {members.length > MEMBERS_SHOWN && ` +${members.length - MEMBERS_SHOWN} more`}
                                            </div>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-2 shrink-0">
                                        <button
                                            disabled={locked}
                                            onClick={() => decide(p, 'reject')}
                                            className="px-3 py-1.5 text-sm rounded-md border border-slate-300 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            Reject
                                        </button>
                                        <button
                                            disabled={locked}
                                            onClick={() => decide(p, 'accept')}
                                            className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-md bg-brand-teal text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                                            Accept
                                        </button>
                                    </div>
                                </div>
                                {rowErrors[key] && (
                                    <div className="mt-2 text-sm text-red-800" role="alert">{rowErrors[key]}</div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
};
