import React, { useState, useEffect } from 'react';
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { Sparkles, GripVertical, X, MessageSquare, ChevronRight, ChevronDown } from 'lucide-react';
import clsx from 'clsx';
import { api } from '../api';
import type { TargetDraftNode } from '../api';
import { useAppStore } from '../store';

// Reuse the SortableThumbnail from previous implementation (will need to export/move it or redefine)
// For now, I'll redefine a simpler version or import if I extract it. 
// Let's extract SortableSlideThumbnail to a shared component first? 
// Or just include it here for now.

import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

const SortableSlideThumbnail: React.FC<{ id: string, url?: string, onRemove?: () => void, parentNode: TargetDraftNode }> = ({ id, url, onRemove, parentNode }) => {
    const { attributes, listeners, setNodeRef, transform, transition } = useSortable({
        id,
        data: { type: 'sortable-item', node: parentNode }
    });

    const setActiveSlideId = useAppStore(state => state.setActiveSlideId);
    const activeSlideId = useAppStore(state => state.activeSlideId);
    const isActive = activeSlideId === id;

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
    };

    return (
        <div
            ref={setNodeRef}
            style={style}
            onClick={() => setActiveSlideId(id)}
            className={clsx(
                "group relative w-full h-14 bg-white border rounded flex items-center gap-3 p-1.5 shadow-sm hover:shadow-md transition-all",
                isActive ? "border-brand-teal ring-1 ring-brand-teal/20 bg-brand-teal/5" : "border-slate-200 hover:border-brand-teal"
            )}
        >
            {/* Drag Handle */}
            <div {...attributes} {...listeners} className="cursor-grab active:cursor-grabbing text-slate-300 hover:text-slate-500 p-1">
                <GripVertical size={14} />
            </div>

            {/* Thumbnail */}
            <div className="w-16 h-10 bg-slate-100 rounded overflow-hidden flex-shrink-0 border border-slate-100">
                {url ? (
                    <img src={url} alt="Thumbnail" className="w-full h-full object-cover" />
                ) : (
                    <div className="w-full h-full flex items-center justify-center text-[8px] text-slate-400">No Img</div>
                )}
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
                <span className="text-[10px] font-medium text-slate-700 block truncate">Slide {id.split('_p')[1]}</span>
                <span className="text-[9px] text-slate-400 block truncate">{id}</span>
            </div>

            {/* Remove Action (Visual only for now, logic later) */}
            <button onClick={onRemove} className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 p-1 transition-opacity">
                <X size={14} />
            </button>
        </div>
    );
};

interface SynthBlockProps {
    node: TargetDraftNode;
    onRefresh: () => void;
}

export const SynthBlock: React.FC<SynthBlockProps> = ({ node, onRefresh }) => {
    // Handle Drop from Source Browser to Block
    // We make the "Ingredients" box the specific drop target
    const { isOver, setNodeRef } = useDroppable({
        id: node.id,
        data: { type: 'target', node }
    });

    const [instruction, setInstruction] = useState("");
    const [synthesizing, setSynthesizing] = useState(false);
    const [expanded, setExpanded] = useState(true);
    const [items, setItems] = useState(node.source_refs);
    const [thumbnails, setThumbnails] = useState<Record<string, string>>({});

    // Sync local items with props
    useEffect(() => {
        if (JSON.stringify(items) !== JSON.stringify(node.source_refs)) {
            setItems(node.source_refs);
        }
    }, [node.source_refs]);

    // Load thumbnails
    useEffect(() => {
        const load = async () => {
            const thumbs: Record<string, string> = {};
            for (const refId of items) {
                try {
                    const details = await api.getSlideDetails(refId);
                    thumbs[refId] = details.s3_url;
                } catch (e) { console.error(e); }
            }
            setThumbnails(thumbs);
        };
        if (items.length > 0) load();
    }, [items]);

    const handleRemove = async (slideId: string) => {
        const newItems = items.filter(id => id !== slideId);
        setItems(newItems); // Optimistic update
        try {
            await api.mapSlideToNode(node.id, newItems);
            onRefresh();
        } catch (e) {
            console.error("Failed to remove slide", e);
            onRefresh(); // Revert
        }
    };

    const handleSynthesize = async () => {
        setSynthesizing(true);
        try {
            await api.triggerSynthesis(node.id, instruction || "Professional standard");
            // Poll
            const poll = setInterval(async () => {
                const status = await api.getSynthesisPreview(node.id);
                if (status.status === 'complete' || status.content) {
                    setSynthesizing(false);
                    clearInterval(poll);
                    onRefresh();
                }
            }, 2000);
        } catch (e) {
            setSynthesizing(false);
        }
    };

    return (
        <div
            className="bg-white border border-slate-200 rounded-xl transition-all mb-6 shadow-sm group"
        >
            {/* Header Row */}
            <div className="flex items-center p-3 border-b border-slate-100 bg-slate-50/50 rounded-t-xl">
                <button onClick={() => setExpanded(!expanded)} className="text-slate-400 hover:text-slate-600 mr-2">
                    {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
                <div className="flex-1">
                    <input
                        type="text"
                        defaultValue={node.title}
                        className="bg-transparent font-bold text-slate-800 text-sm focus:outline-none w-full"
                    />
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-[10px] bg-slate-200 text-slate-600 px-2 py-0.5 rounded-full">
                        {items.length} Sources
                    </span>
                </div>
            </div>

            {expanded && (
                <div className="p-4 flex gap-6">
                    {/* Left: Ingredients (Source Stack) */}
                    <div className="w-1/3 flex flex-col border-r border-slate-100 pr-6">
                        <div className="text-[10px] font-bold text-slate-400 uppercase mb-2 tracking-wider">
                            Ingredients
                        </div>

                        <div
                            ref={setNodeRef}
                            className={clsx(
                                "flex-1 min-h-[100px] bg-slate-50 rounded-lg border border-dashed p-2 transition-colors",
                                isOver ? "border-brand-teal bg-brand-teal/5 ring-2 ring-brand-teal/20" : "border-slate-200 hover:border-slate-300"
                            )}
                        >
                            {items.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center text-slate-400 text-center">
                                    <Sparkles size={16} className="mb-2 opacity-50" />
                                    <span className="text-xs italic">Drag source slides here</span>
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    <SortableContext items={items} strategy={verticalListSortingStrategy}>
                                        {items.map(refId => (
                                            <SortableSlideThumbnail
                                                key={refId}
                                                id={refId}
                                                url={thumbnails[refId]}
                                                parentNode={node}
                                                onRemove={() => handleRemove(refId)}
                                            />
                                        ))}
                                    </SortableContext>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Right: Synthesis (Instruction + Output) */}
                    <div className="flex-1 flex flex-col">
                        <div className="text-[10px] font-bold text-slate-400 uppercase mb-2 tracking-wider">
                            Synthesis
                        </div>

                        {/* Output Preview (if exists) */}
                        {node.content_markdown ? (
                            <div className="prose prose-sm max-w-none mb-4 p-3 bg-white border border-slate-100 rounded-lg shadow-sm">
                                <div className="whitespace-pre-wrap text-slate-700 text-sm">{node.content_markdown}</div>
                            </div>
                        ) : null}

                        {/* Controls */}
                        <div className="mt-auto bg-slate-50 p-3 rounded-lg border border-slate-200">
                            <div className="flex items-start gap-2 mb-3">
                                <MessageSquare size={14} className="text-slate-400 mt-1" />
                                <textarea
                                    className="w-full bg-transparent text-xs text-slate-700 resize-none focus:outline-none"
                                    placeholder="Instructions for AI: e.g. 'Merge these slides, emphasizing safety protocols...'"
                                    rows={2}
                                    value={instruction}
                                    onChange={(e) => setInstruction(e.target.value)}
                                />
                            </div>
                            <div className="flex justify-end">
                                <button
                                    onClick={handleSynthesize}
                                    disabled={synthesizing || items.length === 0}
                                    className="bg-brand-teal text-white text-xs font-medium px-3 py-1.5 rounded-md flex items-center gap-1.5 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                >
                                    {synthesizing ? (
                                        <span className="animate-pulse">Synthesizing...</span>
                                    ) : (
                                        <>
                                            <Sparkles size={12} />
                                            Synthesize Block
                                        </>
                                    )}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
