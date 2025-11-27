import React, { useEffect, useState } from 'react';
import { Search, Folder, ChevronDown, FileText, Image, ChevronRight, CheckCircle2 } from 'lucide-react';
import { api } from '../api';
import type { CourseNode, SourceSlide } from '../api';
import { useDraggable } from '@dnd-kit/core';
import { useAppStore } from '../store';
import clsx from 'clsx';

interface SourceBrowserProps {
    discipline: string;
}

export const SourceBrowser: React.FC<SourceBrowserProps> = ({ discipline }) => {
    const [tree, setTree] = useState<CourseNode[]>([]);
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<string[]>([]); // Slide IDs

    // Fetch Tree
    useEffect(() => {
        api.getSourceTree(discipline).then(setTree);
    }, [discipline]);

    // Search Logic
    useEffect(() => {
        if (searchQuery.length > 2) {
            const delayDebounceFn = setTimeout(() => {
                api.searchConcepts(searchQuery).then(setSearchResults);
            }, 500);
            return () => clearTimeout(delayDebounceFn);
        } else {
            setSearchResults([]);
        }
    }, [searchQuery]);

    return (
        <div className="flex flex-col h-full bg-white">
            {/* Header & Search */}
            <div className="p-4 border-b border-slate-100 bg-white z-10">
                <div className="flex items-center gap-2 mb-3 text-slate-800">
                    <Folder className="text-brand-teal" size={18} />
                    <h2 className="font-semibold text-sm">Source Map</h2>
                </div>

                <div className="relative group">
                    <Search className="absolute left-3 top-2.5 text-slate-400 group-focus-within:text-brand-teal transition-colors" size={14} />
                    <input
                        type="text"
                        placeholder="Search concepts (e.g. 'Safety')..."
                        className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-md text-xs focus:outline-none focus:border-brand-teal transition-all"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>

                {/* Filters (Mock for now) */}
                <div className="flex gap-2 mt-3 overflow-x-auto pb-1 scrollbar-none">
                    {['All Types', 'PDF', 'PPTX', 'Doc'].map(f => (
                        <button key={f} className="text-[10px] px-2 py-1 bg-slate-100 hover:bg-slate-200 rounded text-slate-600 whitespace-nowrap transition-colors">
                            {f}
                        </button>
                    ))}
                </div>
            </div>

            {/* Tree View */}
            <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
                {tree.length === 0 && (
                    <div className="text-center text-slate-400 text-xs mt-10 italic">No content found for {discipline}</div>
                )}

                {tree.map((bu) => (
                    <BusinessUnitNode key={bu.name} node={bu} highlightIds={searchResults} />
                ))}
            </div>
        </div>
    );
};

const BusinessUnitNode: React.FC<{ node: CourseNode, highlightIds: string[] }> = ({ node, highlightIds }) => {
    const [expanded, setExpanded] = useState(true);

    return (
        <div className="mb-2">
            <div
                className="flex items-center gap-2 p-2 hover:bg-slate-50 rounded cursor-pointer select-none group"
                onClick={() => setExpanded(!expanded)}
            >
                {expanded ? <ChevronDown size={14} className="text-slate-400 group-hover:text-slate-600" /> : <ChevronRight size={14} className="text-slate-400 group-hover:text-slate-600" />}
                <span className="text-xs font-bold text-slate-700 uppercase tracking-wide">{node.name}</span>
                <span className="text-[10px] text-slate-400 bg-slate-100 px-1.5 rounded-full">{node.children?.length || 0}</span>
            </div>

            {expanded && (
                <div className="pl-2 border-l border-slate-100 ml-3 space-y-1 mt-1">
                    {node.children?.map(course => (
                        <CourseItem key={course.id} course={course} highlightIds={highlightIds} />
                    ))}
                </div>
            )}
        </div>
    );
};

const CourseItem: React.FC<{ course: CourseNode, highlightIds: string[] }> = ({ course, highlightIds }) => {
    const [expanded, setExpanded] = useState(false);
    const [slides, setSlides] = useState<SourceSlide[]>([]);
    const [loading, setLoading] = useState(false);

    // Auto-expand if search matches this course context? 
    // For now, we just highlight.

    const toggle = async () => {
        if (!expanded && slides.length === 0) {
            setLoading(true);
            try {
                // Fetch list of slides (lightweight)
                // Currently API returns basic info, we need details for image? 
                // Actually, SourceBrowser previously fetched ALL details. That's heavy.
                // Ideally we fetch list, then fetch details on render or lazily.
                // But drag needs URL.
                // Let's stick to the current API behavior: getCourseSlides returns [{id, number, text}]
                // And then fetch details for each? 
                // Optimization: Modify API to return thumbnail URL in list.
                // For now, we'll fetch details in parallel as before.
                const refs = await api.getCourseSlides(course.id);
                const details = await Promise.all(refs.map(s => api.getSlideDetails(s.id)));
                setSlides(details);
            } catch (e) {
                console.error(e);
            } finally {
                setLoading(false);
            }
        }
        setExpanded(!expanded);
    };

    // Check if any child slide matches search
    const hasMatch = highlightIds.some(id => id.startsWith(course.id));

    return (
        <div>
            <div
                className={clsx(
                    "flex items-center gap-2 p-2 rounded cursor-pointer text-xs transition-colors select-none",
                    expanded ? "bg-brand-teal/5 text-brand-teal font-medium" : "text-slate-600 hover:bg-slate-50",
                    hasMatch && !expanded && "ring-1 ring-brand-teal/30 bg-yellow-50" // Highlight match hint
                )}
                onClick={toggle}
            >
                <FileText size={14} className={hasMatch ? "text-brand-teal" : "opacity-70"} />
                <span className="truncate flex-1">{course.name}</span>
                {loading && <span className="animate-spin">⟳</span>}
            </div>

            {expanded && (
                <div className="pl-4 py-1 space-y-2">
                    {slides.length === 0 && !loading && <div className="text-[10px] text-slate-400 pl-2">No slides found.</div>}
                    {slides.map(slide => (
                        <SlideRow key={slide.id} slide={slide} isHighlighted={highlightIds.includes(slide.id)} />
                    ))}
                </div>
            )}
        </div>
    );
};

const SlideRow: React.FC<{ slide: SourceSlide, isHighlighted: boolean }> = ({ slide, isHighlighted }) => {
    const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
        id: slide.id,
        data: { slide }
    });

    // Check usage status from store
    const structure = useAppStore(state => state.structure);
    const isUsed = structure.some(node => node.source_refs.includes(slide.id));

    // Inspection Logic
    const activeSlideId = useAppStore(state => state.activeSlideId);
    const setActiveSlideId = useAppStore(state => state.setActiveSlideId);
    const isActive = activeSlideId === slide.id;

    const handleClick = () => {
        // Prevent conflict with Drag handle if needed, but dnd-kit handles drag on attributes
        // If we click without dragging:
        setActiveSlideId(slide.id);
    };

    const style = transform ? {
        // transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, // Don't transform the original item
        zIndex: 1000,
        opacity: isDragging ? 0.5 : 1
    } : undefined;

    return (
        <div
            ref={setNodeRef}
            {...listeners}
            {...attributes}
            style={style}
            onClick={handleClick}
            className={clsx(
                "flex gap-3 bg-white border rounded p-2 cursor-grab active:cursor-grabbing group transition-all hover:shadow-sm",
                (isHighlighted || isActive) ? "border-brand-teal ring-1 ring-brand-teal/20" : "border-slate-100 hover:border-slate-300",
                isDragging && "opacity-50",
                isActive && "bg-brand-teal/5"
            )}
        >
            {/* Thumbnail */}
            <div className="w-12 h-9 bg-slate-100 rounded overflow-hidden flex-shrink-0 relative">
                {slide.s3_url ? (
                    <img src={slide.s3_url} className="w-full h-full object-cover" alt="slide" />
                ) : (
                    <Image size={12} className="text-slate-300 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
                )}
                {isUsed && (
                    <div className="absolute inset-0 bg-brand-teal/80 flex items-center justify-center">
                        <CheckCircle2 size={12} className="text-white" />
                    </div>
                )}
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0 flex flex-col justify-center">
                <div className="flex items-center justify-between">
                    <span className="text-[10px] font-bold text-slate-700 truncate">
                        Slide {slide.id.split('_p')[1]}
                    </span>
                    {isUsed && <span className="text-[9px] text-brand-teal font-medium">Used</span>}
                </div>

                {/* Concepts Tags */}
                <div className="flex gap-1 mt-1 overflow-hidden">
                    {slide.concepts.slice(0, 2).map((c, i) => (
                        <span key={i} className="text-[9px] bg-slate-100 text-slate-500 px-1 rounded truncate max-w-[60px]">
                            {c.name}
                        </span>
                    ))}
                    {slide.concepts.length > 2 && <span className="text-[9px] text-slate-400">+{slide.concepts.length - 2}</span>}
                </div>
            </div>
        </div>
    );
};
