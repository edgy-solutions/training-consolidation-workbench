import React, { useEffect, useState, useRef } from 'react';
import { FileText, Image as ImageIcon, Maximize2, XCircle, Sparkles, Download } from 'lucide-react';
import { useAppStore } from '../store';
import { api } from '../api';
import type { SourceSlide, TargetDraftNode } from '../api';
import clsx from 'clsx';
import ReactMarkdown from 'react-markdown';

export const SlideInspector: React.FC = () => {
    const activeSlideId = useAppStore(state => state.activeSlideId);
    const activeNodeId = useAppStore(state => state.activeNodeId);
    const structure = useAppStore(state => state.structure);
    const projectId = useAppStore(state => state.projectId);
    const heatmapMode = useAppStore(state => state.heatmapMode);
    const searchQuery = useAppStore(state => state.searchQuery);
    const heatmapData = useAppStore(state => state.heatmapData);

    const [slide, setSlide] = useState<SourceSlide | null>(null);
    const [loading, setLoading] = useState(false);
    const [rendering, setRendering] = useState(false);

    // Refs for scrolling
    const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({});

    // Effect for Source Slides
    useEffect(() => {
        if (activeSlideId) {
            setLoading(true);
            api.getSlideDetails(activeSlideId)
                .then(setSlide)
                .catch(console.error)
                .finally(() => setLoading(false));
        } else if (!activeNodeId) {
            // Only clear if no active node either
            setSlide(null);
        }
    }, [activeSlideId]);

    // Effect to scroll active synthesized node into view
    useEffect(() => {
        if (activeNodeId && !activeSlideId && nodeRefs.current[activeNodeId]) {
            nodeRefs.current[activeNodeId]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, [activeNodeId, activeSlideId]);

    const handleRender = async () => {
        if (!projectId) return;
        setRendering(true);
        try {
            await api.triggerRender(projectId);
            alert("Render job started in background!");
        } catch (e) {
            console.error(e);
            alert("Failed to trigger render.");
        } finally {
            setRendering(false);
        }
    };

    // Render Logic
    // Case 1: Viewing a synthesized node (show ALL nodes)
    if (activeNodeId && !activeSlideId) {
        // Filter for nodes that have content (or are the active one) and sort by order
        const synthesizedNodes = structure
            .filter(n => n.content_markdown || n.id === activeNodeId) // Show active even if empty? Maybe just those with content
            .sort((a, b) => (a.order || 0) - (b.order || 0));

        return (
            <div className="h-full flex flex-col bg-white">
                {/* Header */}
                <div className="p-4 border-b border-slate-100 bg-teal-50 shrink-0">
                    <h2 className="font-bold text-slate-800 text-sm flex items-center gap-2">
                        <Sparkles size={16} className="text-teal-600" />
                        Synthesis Inspector
                    </h2>
                    <p className="text-xs text-slate-500 mt-1 font-medium">Full Course Preview</p>
                </div>

                {/* Markdown Content List */}
                <div className="flex-1 overflow-y-auto bg-slate-50 p-4 space-y-6 custom-scrollbar">
                    {synthesizedNodes.length === 0 && (
                        <div className="text-center text-slate-400 text-xs mt-10 italic">
                            No synthesized content to display.
                        </div>
                    )}

                    {synthesizedNodes.map((node, index) => (
                        <div
                            key={node.id}
                            ref={el => nodeRefs.current[node.id] = el}
                            className={clsx(
                                "bg-white border rounded-lg shadow-sm p-6 transition-all duration-500",
                                node.id === activeNodeId ? "ring-2 ring-teal-600 shadow-md" : "border-slate-200 opacity-80 hover:opacity-100"
                            )}
                        >
                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-3 border-b border-slate-100 pb-2 flex justify-between">
                                <span>Section {index + 1}: {node.title}</span>
                                {node.id === activeNodeId && <span className="text-teal-600">Active</span>}
                            </div>

                            {node.content_markdown ? (
                                <div className="prose prose-sm max-w-none text-slate-700">
                                    <ReactMarkdown>{node.content_markdown}</ReactMarkdown>
                                </div>
                            ) : (
                                <div className="text-center text-slate-300 text-xs italic py-4">
                                    (Content pending...)
                                </div>
                            )}
                        </div>
                    ))}
                </div>

                {/* Footer / Render Actions */}
                <div className="p-4 border-t border-slate-100 bg-white shrink-0 flex justify-between items-center shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)]">
                    <div className="text-[10px] text-slate-400">
                        {synthesizedNodes.length} sections ready
                    </div>
                    <button
                        onClick={handleRender}
                        disabled={rendering}
                        className="bg-teal-600 text-white text-xs font-medium px-4 py-2 rounded-md shadow-sm hover:bg-teal-700 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        {rendering ? (
                            <span className="animate-pulse">Starting Job...</span>
                        ) : (
                            <>
                                <Download size={14} />
                                Render to File
                            </>
                        )}
                    </button>
                </div>
            </div>
        );
    }
    // Case 2: No selection
    if (!activeSlideId) {
        return (
            <div className="h-full flex flex-col items-center justify-center text-slate-400 p-8 text-center">
                <ImageIcon size={48} className="mb-4 opacity-20" />
                <p className="font-medium">No Item Selected</p>
                <p className="text-xs mt-2">Click on a source slide or synthesized block to inspect details.</p>
            </div>
        );
    }

    // Case 3: Loading Slide
    if (loading || !slide) {
        return (
            <div className="h-full flex items-center justify-center text-slate-400">
                <span className="animate-pulse">Loading details...</span>
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col bg-white">
            {/* Header */}
            <div className="p-4 border-b border-slate-100 flex justify-between items-start">
                <div>
                    <h2 className="font-bold text-slate-800 text-sm flex items-center gap-2">
                        <FileText size={16} className="text-teal-600" />
                        Slide Inspector
                    </h2>
                    <p className="text-xs text-slate-500 mt-1 font-mono">{slide.id}</p>
                </div>
            </div>

            {/* Image Preview (Top Half) */}
            <div className="flex-1 bg-slate-100 relative overflow-hidden flex items-center justify-center border-b border-slate-200 min-h-[40%]">
                {slide.s3_url ? (
                    <img src={slide.s3_url} className="max-w-full max-h-full object-contain shadow-lg" alt="Slide Full" />
                ) : (
                    <div className="text-slate-400 text-xs flex flex-col items-center">
                        <XCircle size={24} className="mb-2" />
                        No Image Available
                    </div>
                )}
                <button className="absolute top-3 right-3 bg-black/50 text-white p-1.5 rounded hover:bg-black/70 transition-colors">
                    <Maximize2 size={16} />
                </button>
            </div>

            {/* Text & Metadata (Bottom Half) */}
            <div className="flex-1 overflow-y-auto p-4">
                {/* Concepts */}
                <div className="mb-6">
                    <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Detected Concepts</h3>
                    <div className="flex flex-wrap gap-2">
                        {([...slide.concepts])
                            .sort((a, b) => (b.salience || 0) - (a.salience || 0))
                            .map((c, i) => {
                                // Heatmap Logic
                                const heat = (slide && heatmapData) ? heatmapData[slide.id] : undefined;
                                const intensity = heat?.score || 0;

                                return (
                                    <span key={i} className={clsx(
                                        "text-xs px-2 py-1 rounded-md flex items-center gap-2 border transition-colors",
                                        // Heatmap Logic: Highlight concept tag if it likely matches the search
                                        (heatmapMode && intensity > 0 && searchQuery && c.name.toLowerCase().includes(searchQuery.toLowerCase()))
                                            ? (c.salience > 0.7
                                                ? "bg-red-100 text-red-700 border-red-300 font-medium ring-1 ring-red-200"
                                                : "bg-orange-100 text-orange-700 border-orange-300 font-medium ring-1 ring-orange-200")
                                            : "bg-teal-50 text-teal-600 border-teal-100"
                                    )}>
                                        <span>{c.name}</span>
                                        {c.salience !== undefined && (
                                            <span className={clsx(
                                                "font-mono text-[10px] px-1 rounded",
                                                // Heatmap Mode: Only color red if this specific concept is a match
                                                heatmapMode && intensity > 0
                                                    ? (searchQuery && c.name.toLowerCase().includes(searchQuery.toLowerCase())
                                                        ? (c.salience > 0.7 ? "text-red-600 font-bold" : "text-orange-500 font-medium")
                                                        : "text-slate-500")
                                                    : (c.salience > 0.7 ? "bg-teal-100 text-teal-700 font-bold border border-teal-200" : "bg-slate-100 text-slate-500 border border-slate-200")
                                            )}>
                                                {c.salience.toFixed(2)}
                                            </span>
                                        )}
                                    </span>
                                )
                            })}
                        {slide.concepts.length === 0 && <span className="text-xs text-slate-400 italic">None detected</span>}
                    </div>
                </div>

                {/* Extracted Text */}
                <div>
                    <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Extracted Text</h3>
                    <div className="bg-slate-50 p-3 rounded border border-slate-100 text-xs text-slate-600 font-mono whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto custom-scrollbar">
                        {slide.text_preview || <span className="italic opacity-50">No text content extracted.</span>}
                    </div>
                </div>
            </div>
        </div>
    );
};
