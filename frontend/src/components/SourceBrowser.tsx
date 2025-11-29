import React, { useEffect, useState } from 'react';
import { Search, Folder, ChevronDown, FileText, Image, ChevronRight, CheckCircle2, Filter, X } from 'lucide-react';
import { api } from '../api';
import type { CourseNode, SourceSlide } from '../api';
import { useDraggable } from '@dnd-kit/core';
import { useAppStore } from '../store';
import { useSelectionStore } from '../stores/selectionStore';
import clsx from 'clsx';

interface SourceBrowserProps {
    discipline: string;
}

export const SourceBrowser: React.FC<SourceBrowserProps> = ({ discipline }) => {
    const [tree, setTree] = useState<CourseNode[]>([]);
    const [searchQuery, setSearchQuery] = useState('');

    // Filter State
    const [filters, setFilters] = useState({
        origin: '',
        domain: '',
        intent: '',
        type: ''
    });
    const [filterOptions, setFilterOptions] = useState({
        origins: [] as string[],
        domains: [] as string[],
        intents: [] as string[],
        types: [] as string[]
    });
    const [showFilters, setShowFilters] = useState(false);

    // Fetch Filter Options
    useEffect(() => {
        api.getFilterOptions().then(setFilterOptions).catch(console.error);
    }, []);

    // Fetch Tree or Search
    useEffect(() => {
        const fetchData = async () => {
            // Check if any filter is active or query exists
            const hasFilters = Object.values(filters).some(v => v !== '') || searchQuery.length > 0;

            if (hasFilters) {
                // Use Search Endpoint
                try {
                    const results = await api.searchSourceTree({
                        query: searchQuery || undefined,
                        filters: {
                            origin: filters.origin || undefined,
                            domain: filters.domain || undefined,
                            intent: filters.intent || undefined,
                            type: filters.type || undefined
                        }
                    });
                    setTree(results);
                } catch (e) {
                    console.error("Search failed", e);
                }
            } else {
                // Default View
                api.getSourceTree(discipline).then(setTree);
            }
        };

        const debounce = setTimeout(fetchData, 300);
        return () => clearTimeout(debounce);
    }, [discipline, searchQuery, filters]);

    const clearFilters = () => {
        setFilters({ origin: '', domain: '', intent: '', type: '' });
        setSearchQuery('');
    };

    return (
        <div className="flex flex-col h-full bg-white">
            {/* Header & Search */}
            <div className="p-4 border-b border-slate-100 bg-white z-10 space-y-3">
                <div className="flex items-center justify-between text-slate-800">
                    <div className="flex items-center gap-2">
                        <Folder className="text-brand-teal" size={18} />
                        <h2 className="font-semibold text-sm">Source Map</h2>
                    </div>
                    <button
                        onClick={() => setShowFilters(!showFilters)}
                        className={clsx("p-1 rounded hover:bg-slate-100 transition-colors", showFilters && "bg-slate-100 text-brand-teal")}
                    >
                        <Filter size={14} />
                    </button>
                </div>

                <div className="relative group">
                    <Search className="absolute left-3 top-2.5 text-slate-400 group-focus-within:text-brand-teal transition-colors" size={14} />
                    <input
                        type="text"
                        placeholder="Search concepts (e.g. 'Safety')..."
                        className="w-full pl-9 pr-8 py-2 bg-slate-50 border border-slate-200 rounded-md text-xs focus:outline-none focus:border-brand-teal transition-all"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                    {searchQuery && (
                        <button onClick={() => setSearchQuery('')} className="absolute right-2 top-2.5 text-slate-400 hover:text-slate-600">
                            <X size={14} />
                        </button>
                    )}
                </div>

                {/* Filters Panel */}
                {showFilters && (
                    <div className="grid grid-cols-2 gap-2 p-2 bg-slate-50 rounded-md border border-slate-100 animate-in slide-in-from-top-2">
                        <select
                            className="text-[10px] p-1 rounded border border-slate-200 bg-white"
                            value={filters.origin}
                            onChange={e => setFilters({ ...filters, origin: e.target.value })}
                        >
                            <option value="">All Origins</option>
                            {filterOptions.origins.map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                        <select
                            className="text-[10px] p-1 rounded border border-slate-200 bg-white"
                            value={filters.domain}
                            onChange={e => setFilters({ ...filters, domain: e.target.value })}
                        >
                            <option value="">All Domains</option>
                            {filterOptions.domains.map(d => <option key={d} value={d}>{d}</option>)}
                        </select>
                        <select
                            className="text-[10px] p-1 rounded border border-slate-200 bg-white"
                            value={filters.intent}
                            onChange={e => setFilters({ ...filters, intent: e.target.value })}
                        >
                            <option value="">All Intents</option>
                            {filterOptions.intents.map(i => <option key={i} value={i}>{i}</option>)}
                        </select>
                        <select
                            className="text-[10px] p-1 rounded border border-slate-200 bg-white"
                            value={filters.type}
                            onChange={e => setFilters({ ...filters, type: e.target.value })}
                        >
                            <option value="">All Types</option>
                            {filterOptions.types.map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                        <button onClick={clearFilters} className="col-span-2 text-[10px] text-brand-teal hover:underline text-center mt-1">
                            Clear Filters
                        </button>
                    </div>
                )}
            </div>

            {/* Tree View */}
            <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
                {tree.length === 0 && (
                    <div className="text-center text-slate-400 text-xs mt-10 italic">
                        No content found.
                    </div>
                )}

                {tree.map((bu) => (
                    <BusinessUnitNode key={bu.name} node={bu} />
                ))}
            </div>
        </div>
    );
};

const BusinessUnitNode: React.FC<{ node: CourseNode }> = ({ node }) => {
    const [expanded, setExpanded] = useState(true);
    const { selectedSourceIds, selectMultiple, deselectMultiple } = useSelectionStore();

    // Get all descendant IDs (courses in this BU)
    const getAllDescendantIds = (n: CourseNode): string[] => {
        const ids: string[] = [];
        if (n.children) {
            for (const child of n.children) {
                ids.push(child.id);
                ids.push(...getAllDescendantIds(child));
            }
        }
        return ids;
    };

    const descendantIds = getAllDescendantIds(node);
    const selectedCount = descendantIds.filter(id => selectedSourceIds.has(id)).length;
    const isFullySelected = selectedCount === descendantIds.length && descendantIds.length > 0;
    const isPartiallySelected = selectedCount > 0 && selectedCount < descendantIds.length;

    const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        e.stopPropagation();
        if (isFullySelected) {
            deselectMultiple(descendantIds);
        } else {
            selectMultiple(descendantIds);
        }
    };

    return (
        <div className="mb-2">
            <div
                className="flex items-center gap-2 p-2 hover:bg-slate-50 rounded cursor-pointer select-none group"
            >
                <input
                    type="checkbox"
                    checked={isFullySelected}
                    ref={(input) => {
                        if (input) input.indeterminate = isPartiallySelected;
                    }}
                    onChange={handleCheckboxChange}
                    onClick={(e) => e.stopPropagation()}
                    className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500 cursor-pointer"
                />
                <div
                    className="flex items-center gap-2 flex-1"
                    onClick={() => setExpanded(!expanded)}
                >
                    {expanded ? <ChevronDown size={14} className="text-slate-400 group-hover:text-slate-600" /> : <ChevronRight size={14} className="text-slate-400 group-hover:text-slate-600" />}
                    <span className="text-xs font-bold text-slate-700 uppercase tracking-wide">{node.name}</span>
                    <span className="text-[10px] text-slate-400 bg-slate-100 px-1.5 rounded-full">{node.children?.length || 0}</span>
                </div>
            </div>

            {expanded && (
                <div className="pl-2 border-l border-slate-100 ml-3 space-y-1 mt-1">
                    {node.children?.map(course => (
                        <CourseItem key={course.id} course={course} />
                    ))}
                </div>
            )}
        </div>
    );
};

const CourseItem: React.FC<{ course: CourseNode }> = ({ course }) => {
    // If course has pre-loaded slides (from search), expand by default
    const preloadedSlides = (course as any).slides as SourceSlide[] | undefined;
    const [expanded, setExpanded] = useState(!!preloadedSlides);
    const [slides, setSlides] = useState<SourceSlide[]>(preloadedSlides || []);
    const [loading, setLoading] = useState(false);
    const { selectedSourceIds, toggleSelection } = useSelectionStore();

    const isSelected = selectedSourceIds.has(course.id);

    // Update slides if prop changes (e.g. new search results)
    useEffect(() => {
        if (preloadedSlides) {
            setSlides(preloadedSlides);
            setExpanded(true);
        } else {
            // Reset if switching back to default view
            // But we don't want to clear if we just fetched them manually.
            // If course.slides is undefined, it means we are in default view.
            // We should keep existing state unless we want to force collapse?
            // Let's leave it.
        }
    }, [preloadedSlides]);

    const toggle = async () => {
        if (!expanded && slides.length === 0) {
            setLoading(true);
            try {
                const refs = await api.getCourseSlides(course.id);
                // In default view, we need to fetch details. 
                // Optimization: The search endpoint returns details. 
                // The default endpoint returns {id, number, text}.
                // We need to fetch details for drag preview.
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

    const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        e.stopPropagation();
        toggleSelection(course.id);
    };

    return (
        <div>
            <div
                className={clsx(
                    "flex items-center gap-2 p-2 rounded cursor-pointer text-xs transition-colors select-none",
                    expanded ? "bg-brand-teal/5 text-brand-teal font-medium" : "text-slate-600 hover:bg-slate-50"
                )}
            >
                <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={handleCheckboxChange}
                    onClick={(e) => e.stopPropagation()}
                    className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500 cursor-pointer"
                />
                <div className="flex items-center gap-2 flex-1" onClick={toggle}>
                    <FileText size={14} className="opacity-70" />
                    <span className="truncate flex-1">{course.name}</span>
                    {loading && <span className="animate-spin">⟳</span>}
                    {preloadedSlides && <span className="text-[9px] bg-brand-teal/10 px-1 rounded text-brand-teal">{preloadedSlides.length}</span>}
                </div>
            </div>

            {expanded && (
                <div className="pl-4 py-1 space-y-2">
                    {slides.length === 0 && !loading && <div className="text-[10px] text-slate-400 pl-2">No slides found.</div>}
                    {slides.map(slide => (
                        <SlideRow key={slide.id} slide={slide} isHighlighted={false} />
                    ))}
                </div>
            )}
        </div>
    );
};

const SlideRow: React.FC<{ slide: SourceSlide, isHighlighted: boolean }> = ({ slide, isHighlighted }) => {
    const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
        id: `source-${slide.id}`,
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
        setActiveSlideId(slide.id);
    };

    const style = transform ? {
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
                        Slide {slide.id.split('_p')[1] || slide.id}
                    </span>
                    {isUsed && <span className="text-[9px] text-brand-teal font-medium">Used</span>}
                </div>

                {/* Concepts Tags */}
                <div className="flex gap-1 mt-1 overflow-hidden">
                    {(slide.concepts || []).slice(0, 2).map((c, i) => (
                        <span key={i} className="text-[9px] bg-slate-100 text-slate-500 px-1 rounded truncate max-w-[60px]">
                            {c.name}
                        </span>
                    ))}
                    {(slide.concepts || []).length > 2 && <span className="text-[9px] text-slate-400">+{(slide.concepts || []).length - 2}</span>}
                </div>
            </div>
        </div>
    );
};
