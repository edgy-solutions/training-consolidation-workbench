import React, { useEffect, useState } from 'react';
import { FileText, Image as ImageIcon, Maximize2, XCircle } from 'lucide-react';
import { useAppStore } from '../store';
import { api } from '../api';
import type { SourceSlide } from '../api';
import clsx from 'clsx';

export const SlideInspector: React.FC = () => {
    const activeSlideId = useAppStore(state => state.activeSlideId);
    const [slide, setSlide] = useState<SourceSlide | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (activeSlideId) {
            setLoading(true);
            api.getSlideDetails(activeSlideId)
                .then(setSlide)
                .catch(console.error)
                .finally(() => setLoading(false));
        } else {
            setSlide(null);
        }
    }, [activeSlideId]);

    if (!activeSlideId) {
        return (
            <div className="h-full flex flex-col items-center justify-center text-slate-400 p-8 text-center">
                <ImageIcon size={48} className="mb-4 opacity-20" />
                <p className="font-medium">No Slide Selected</p>
                <p className="text-xs mt-2">Click on any slide in the Source Map or Draft to inspect details.</p>
            </div>
        );
    }

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
                        <FileText size={16} className="text-brand-teal" />
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
                            .map((c, i) => (
                            <span key={i} className="text-xs bg-brand-teal/5 text-brand-teal border border-brand-teal/20 px-2 py-1 rounded-md flex items-center gap-2">
                                <span>{c.name}</span>
                                {c.salience !== undefined && (
                                    <span className={clsx(
                                        "font-mono text-[10px] px-1 rounded",
                                        c.salience > 0.7 ? "bg-teal-100 text-teal-700 font-bold border border-teal-200" : "bg-slate-100 text-slate-500 border border-slate-200"
                                    )}>
                                        {c.salience.toFixed(2)}
                                    </span>
                                )}
                            </span>
                        ))}
                        {slide.concepts.length === 0 && <span className="text-xs text-slate-400 italic">None detected</span>}
                    </div>
                </div>

                {/* Extracted Text */}
                <div>
                    <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Extracted Text</h3>
                    <div className="bg-slate-50 p-3 rounded border border-slate-100 text-xs text-slate-600 font-mono whitespace-pre-wrap leading-relaxed">
                        {slide.text_preview || <span className="italic opacity-50">No text content extracted.</span>}
                    </div>
                </div>
            </div>
        </div>
    );
};
