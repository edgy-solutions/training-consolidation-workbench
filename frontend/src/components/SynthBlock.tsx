import React, { useState, useEffect, useRef } from 'react';
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { Sparkles, GripVertical, X, MessageSquare, ChevronRight, ChevronDown, LayoutTemplate } from 'lucide-react';
import clsx from 'clsx';
import { api } from '../api';
import type { TargetDraftNode } from '../api';
import { useAppStore } from '../store';
import { MarkdownEditor } from './MarkdownEditor';
import { AssetDrawer } from './AssetDrawer';

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
    const { isOver, setNodeRef } = useDroppable({
        id: node.id,
        data: { type: 'target', node }
    });

    const [instruction, setInstruction] = useState("");
    const [synthesizing, setSynthesizing] = useState(false);
    const [expanded, setExpanded] = useState(true);

    // Ref for the title input to enable auto-focus
    const titleInputRef = useRef<HTMLInputElement>(null);
    const newlyAddedNodeId = useAppStore(state => state.newlyAddedNodeId);
    const setNewlyAddedNodeId = useAppStore(state => state.setNewlyAddedNodeId);

    // Determine effective items (manual sources OR suggested sources)
    const effectiveItems = node.is_suggestion
        ? (node.suggested_source_ids || [])
        : node.source_refs;

    const [items, setItems] = useState(effectiveItems);
    const [thumbnails, setThumbnails] = useState<Record<string, string>>({});

    // Auto-focus on newly added nodes
    useEffect(() => {
        if (newlyAddedNodeId === node.id && titleInputRef.current) {
            titleInputRef.current.focus();
            titleInputRef.current.select();
            setNewlyAddedNodeId(null); // Clear after focusing
        }
    }, [newlyAddedNodeId, node.id, setNewlyAddedNodeId]);

    // Sync local items with props
    useEffect(() => {
        const currentEffective = node.is_suggestion
            ? (node.suggested_source_ids || [])
            : node.source_refs;

        if (JSON.stringify(items) !== JSON.stringify(currentEffective)) {
            setItems(currentEffective);
        }
    }, [node.source_refs, node.suggested_source_ids, node.is_suggestion]);

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
        // Allow removing from suggestions (will convert to draft on backend)

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

    const handleAccept = async () => {
        try {
            await api.acceptSuggestedNode(node.id);
            onRefresh();
        } catch (e) {
            console.error("Failed to accept suggestion", e);
            alert("Failed to accept suggestion");
        }
    };

    const isUnassigned = node.title === "Unassigned / For Review";
    // Robust check: Use flag OR fallback to rationale string for legacy data
    const isPlaceholder = node.is_placeholder || node.rationale === "NO_SOURCE_DATA";
    const isSuggestion = node.is_suggestion && !isPlaceholder;

    return (
        <div
            className={clsx(
                "border rounded-xl transition-all mb-6 shadow-sm group relative overflow-hidden",
                isSuggestion
                    ? "bg-purple-50/50 border-purple-200 border-dashed"
                    : isUnassigned
                        ? "bg-slate-100 border-slate-300 border-dashed bg-[repeating-linear-gradient(45deg,transparent,transparent_10px,#e2e8f0_10px,#e2e8f0_20px)]"
                        : "bg-white border-slate-200"
            )}
        >
            {/* Header Row */}
            <div className={clsx(
                "flex items-center p-3 border-b rounded-t-xl",
                isSuggestion ? "border-purple-100 bg-purple-50/80" :
                    isUnassigned ? "border-slate-300 bg-slate-200" : "border-slate-100 bg-slate-50/50"
            )}>
                <button onClick={() => setExpanded(!expanded)} className="text-slate-400 hover:text-slate-600 mr-2">
                    {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
                <div className="flex-1 mr-4">
                    {/* Title is editable for technical sections only */}
                    {node.section_type === 'technical' ? (
                        <input
                            ref={titleInputRef}
                            type="text"
                            defaultValue={node.title}
                            className="bg-transparent font-bold text-slate-800 text-sm focus:outline-none focus:ring-1 focus:ring-brand-teal/30 focus:bg-white rounded px-1 -ml-1 w-full"
                            onBlur={async (e) => {
                                const newTitle = e.target.value.trim();
                                if (newTitle && newTitle !== node.title) {
                                    try {
                                        await api.updateNodeTitle(node.id, newTitle);
                                        onRefresh();
                                    } catch (err) {
                                        console.error("Failed to update title", err);
                                        e.target.value = node.title; // Revert
                                    }
                                }
                            }}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    e.currentTarget.blur();
                                }
                            }}
                        />
                    ) : (
                        <span className="font-bold text-slate-800 text-sm">{node.title}</span>
                    )}
                    {node.rationale && !isPlaceholder && (
                        <div className="text-[10px] text-slate-500 mt-0.5 italic truncate">
                            {node.rationale}
                        </div>
                    )}
                    {isPlaceholder && (
                        <div className="text-[10px] text-amber-600 mt-0.5 italic truncate flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 inline-block" />
                            Content missing from source material
                        </div>
                    )}
                </div>

                <div className="flex items-center gap-3">
                    {/* Layout Selector */}
                    {!isSuggestion && !isUnassigned && !isPlaceholder && (
                        <div className="relative group/layout">
                            <select
                                className="appearance-none bg-slate-100 hover:bg-slate-200 text-[10px] font-medium text-slate-600 px-2 py-1 pr-6 rounded cursor-pointer border-transparent focus:border-brand-teal outline-none transition-colors"
                                value={node.target_layout || 'documentary'}
                                onChange={async (e) => {
                                    try {
                                        await api.updateNodeLayout(node.id, e.target.value);
                                        onRefresh();
                                    } catch (err) {
                                        console.error("Failed to update layout", err);
                                    }
                                }}
                            >
                                <option value="documentary">Content (Standard)</option>
                                <option value="hero">Title Slide</option>
                                <option value="split">Split (Text + Img)</option>
                                <option value="content_caption">Image w/ Caption</option>
                                <option value="grid">Grid (Multi-Img)</option>
                                <option value="table">Table</option>
                                <option value="blank">Blank</option>
                            </select>
                            <LayoutTemplate size={12} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                        </div>
                    )}

                    {/* Suggestion Badge Inline */}
                    {isSuggestion && (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-purple-100 text-purple-700 text-[10px] font-medium border border-purple-200 whitespace-nowrap">
                            <Sparkles size={10} />
                            AI Suggestion
                        </span>
                    )}
                    {isUnassigned && (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-slate-300 text-slate-700 text-[10px] font-medium border border-slate-400 whitespace-nowrap">
                            Parking Lot
                        </span>
                    )}

                    <span className="text-[10px] bg-slate-200 text-slate-600 px-2 py-0.5 rounded-full whitespace-nowrap">
                        {items.length} Sources
                    </span>
                </div>
            </div>

            {expanded && (
                <div className="p-4 flex gap-6">
                    {/* Left: Ingredients (Source Stack) */}
                    <div className="w-1/3 flex flex-col border-r border-slate-100 pr-6">
                        <div className="text-[10px] font-bold text-slate-400 uppercase mb-2 tracking-wider">
                            {isUnassigned ? "Unused Slides" : "Ingredients"}
                        </div>

                        <div
                            ref={setNodeRef}
                            className={clsx(
                                "flex-1 min-h-[100px] rounded-lg border p-2 transition-colors",
                                isSuggestion
                                    ? "bg-white/50 border-purple-100 border-dashed"
                                    : isUnassigned
                                        ? "bg-white/80 border-slate-300 border-dashed"
                                        : "bg-slate-50 border-dashed border-slate-200",
                                isOver && !isSuggestion ? "border-brand-teal bg-brand-teal/5 ring-2 ring-brand-teal/20" : ""
                            )}
                        >
                            {items.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center text-slate-400 text-center">
                                    <Sparkles size={16} className="mb-2 opacity-50" />
                                    <span className="text-xs italic">
                                        {isSuggestion ? "No sources found" : isUnassigned ? "All slides assigned!" : "Drag source slides here"}
                                    </span>
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
                    <div className="flex-1 flex flex-col min-w-0">
                        {isSuggestion ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-center p-6 bg-white/50 rounded-lg border border-purple-100 border-dashed">
                                <Sparkles size={24} className="text-purple-300 mb-3" />
                                <h4 className="text-sm font-medium text-purple-900 mb-1">AI Suggested Section</h4>

                                {node.rationale && (
                                    <div className="mb-4 px-4 py-2 bg-purple-50 rounded border border-purple-100 text-xs text-purple-800 italic relative">
                                        <span className="absolute top-0 left-1 text-purple-300 text-lg">"</span>
                                        {node.rationale}
                                        <span className="absolute bottom-0 right-1 text-purple-300 text-lg">"</span>
                                    </div>
                                )}

                                <p className="text-xs text-purple-600 mb-4 max-w-xs">
                                    Review the suggested sources and rationale. Accept to edit and synthesize.
                                </p>
                                <div className="flex gap-3">
                                    <button
                                        onClick={async () => {
                                            try {
                                                await api.rejectSuggestedNode(node.id);
                                                onRefresh();
                                            } catch (e) {
                                                console.error("Failed to reject suggestion", e);
                                                alert("Failed to reject suggestion");
                                            }
                                        }}
                                        className="px-3 py-1.5 text-xs font-medium text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
                                    >
                                        {node.section_type === 'technical' ? 'Reject' : 'Clear Suggestions'}
                                    </button>
                                    <button
                                        onClick={handleAccept}
                                        className="px-4 py-1.5 text-xs font-medium text-white bg-purple-600 hover:bg-purple-700 rounded-md shadow-sm transition-colors flex items-center gap-1.5"
                                    >
                                        <Sparkles size={12} />
                                        Accept Suggestion
                                    </button>
                                </div>
                            </div>
                        ) : isUnassigned ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-center p-6">
                                <div className="text-slate-400 mb-4">
                                    <p className="font-medium text-sm">Review Unassigned Slides</p>
                                    <p className="text-xs mt-1 max-w-xs mx-auto">
                                        These slides were not used in the generated curriculum. Drag them to other sections if needed, or clear them.
                                    </p>
                                </div>
                                <button
                                    onClick={() => {
                                        // Clear all items
                                        items.forEach(id => handleRemove(id));
                                    }}
                                    className="px-4 py-2 text-xs font-medium text-red-600 bg-white border border-red-200 hover:bg-red-50 rounded-md shadow-sm transition-colors flex items-center gap-2"
                                >
                                    <X size={14} />
                                    Clear All Unassigned
                                </button>
                            </div>
                        ) : isPlaceholder && items.length === 0 && !node.content_markdown ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-center p-6 bg-slate-50 rounded-lg border border-slate-200 border-dashed">
                                <div className="text-slate-400 mb-2">
                                    <Sparkles size={20} className="mx-auto mb-2 opacity-50" />
                                    <p className="font-medium text-sm text-slate-600">No Content Found</p>
                                    <p className="text-xs mt-1 max-w-xs mx-auto text-slate-500">
                                        The source material didn't contain information for this section.
                                    </p>
                                </div>
                                <div className="text-[10px] text-slate-400 italic">
                                    Drag relevant slides here or write content manually.
                                </div>
                            </div>
                        ) : (
                            <>
                                <div className="text-[10px] font-bold text-slate-400 uppercase mb-2 tracking-wider">
                                    Synthesis
                                </div>

                                {/* Output Preview/Editor (if exists) */}
                                {node.content_markdown ? (
                                    <div className="mb-4 overflow-hidden">
                                        <div className="flex items-center justify-between mb-2">
                                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                                                Editable Content
                                            </div>
                                            <button
                                                onClick={() => {
                                                    // Set active Node ID to show in Inspector
                                                    useAppStore.getState().setActiveSlideId(null);
                                                    useAppStore.getState().setActiveNodeId(node.id);
                                                }}
                                                className="text-xs text-brand-teal hover:text-brand-teal-dark flex items-center gap-1 font-medium transition-colors"
                                            >
                                                <Sparkles size={12} />
                                                View Preview →
                                            </button>
                                        </div>
                                        <MarkdownEditor
                                            content={node.content_markdown}
                                            onSave={(markdown) => {
                                                // Use the store's debounced action
                                                useAppStore.getState().updateNodeContent(node.id, markdown);
                                            }}
                                        />
                                        <div className="text-[10px] text-slate-500 mt-2 flex items-center gap-1">
                                            <Sparkles size={10} className="text-brand-teal" />
                                            Auto-saved as you type
                                        </div>

                                        {/* Visual Assets Drawer */}
                                        <AssetDrawer
                                            slideIds={items}
                                            onInsert={(url, filename) => {
                                                // Insert markdown image at cursor or end
                                                const imageMarkdown = `\n\n![${filename}](${url})\n\n`;
                                                const currentContent = node.content_markdown || '';
                                                const newContent = currentContent + imageMarkdown;
                                                useAppStore.getState().updateNodeContent(node.id, newContent);
                                            }}
                                        />
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
                                            className="bg-teal-600 text-white text-xs font-medium px-3 py-1.5 rounded-md flex items-center gap-1.5 hover:bg-teal-700 disabled:bg-slate-300 disabled:text-slate-500 disabled:cursor-not-allowed transition-colors shadow-sm"
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
                            </>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};
