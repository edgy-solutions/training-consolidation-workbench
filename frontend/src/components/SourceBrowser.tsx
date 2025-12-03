import React, { useEffect, useState, useMemo } from 'react';
import { Search, Folder, ChevronDown, FileText, Image, ChevronRight, CheckCircle2, Filter, X } from 'lucide-react';
import { api } from '../api';
import type { CourseNode, SourceSlide } from '../api';
import { useDraggable } from '@dnd-kit/core';
import { useAppStore } from '../store';
import { useSelectionStore } from '../stores/selectionStore';
import { SidebarActionPanel } from './SidebarActionPanel';
import clsx from 'clsx';

interface SourceBrowserProps {
    discipline: string;
}

export const SourceBrowser: React.FC<SourceBrowserProps> = ({ discipline }) => {
    const [tree, setTree] = useState<CourseNode[]>([]);

    // Global State
    const heatmapMode = useAppStore(state => state.heatmapMode);
    const searchQuery = useAppStore(state => state.searchQuery);
    const heatmapData = useAppStore(state => state.heatmapData);
    const setHeatmapMode = useAppStore(state => state.setHeatmapMode);
    const setSearchQuery = useAppStore(state => state.setSearchQuery);
    const setHeatmapData = useAppStore(state => state.setHeatmapData);

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
            // 1. Always fetch tree data first (either search results or default tree)
            // Check if any filter is active or query exists
            const hasFilters = Object.values(filters).some(v => v !== '') || searchQuery.length > 0;

            if (hasFilters) {
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
                // Only fetch default if we haven't loaded it or if filters were cleared
                // But also if search query is cleared, we need to restore original tree structure (preserving expansion state if possible, but api returns new structure)
                // The issue is if we search, setTree overwrites. If we clear search, we need to fetch default tree.
                if (tree.length === 0 || (!searchQuery && !heatmapMode && !hasFilters)) {
                    const results = await api.getSourceTree(discipline);
                    setTree(results);
                }
            }

            // 2. Fetch Heatmap Data if active
            if (heatmapMode && searchQuery.length > 2) {
                try {
                    const data = await api.getConceptHeatmap(searchQuery);
                    console.log("Heatmap Data:", data); // Debug
                    setHeatmapData(data);
                } catch (e) {
                    console.error("Heatmap failed", e);
                }
            } else {
                setHeatmapData({});
            }
        };

        const debounce = setTimeout(fetchData, 300);
        return () => clearTimeout(debounce);
    }, [discipline, searchQuery, filters, heatmapMode]);

    const clearFilters = () => {
        setFilters({ origin: '', domain: '', intent: '', type: '' });
        setSearchQuery('');
        setHeatmapMode(false);
    };

    return (
        <div className="flex flex-col h-full bg-white relative">
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
                    <Search className={clsx("absolute left-3 top-2.5 transition-colors", heatmapMode ? "text-red-500" : "text-slate-400 group-focus-within:text-brand-teal")} size={14} />
                    <input
                        type="text"
                        placeholder="Search concepts (e.g. 'Safety')..."
                        className={clsx(
                            "w-full pl-9 pr-24 py-2 bg-slate-50 border rounded-md text-xs focus:outline-none transition-all",
                            heatmapMode ? "border-red-200 focus:border-red-500 ring-1 ring-red-100" : "border-slate-200 focus:border-brand-teal"
                        )}
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />

                    {/* Heatmap Toggle inside input */}
                    <div className="absolute right-8 top-2 flex items-center gap-1">
                        <label className="flex items-center gap-1 cursor-pointer select-none">
                            <span className={clsx("text-[10px] font-medium transition-colors", heatmapMode ? "text-red-600" : "text-slate-400")}>
                                Heatmap
                            </span>
                            <div className="relative inline-flex items-center">
                                <input
                                    type="checkbox"
                                    className="sr-only peer"
                                    checked={heatmapMode}
                                    onChange={() => setHeatmapMode(!heatmapMode)}
                                />
                                <div className="w-6 h-3 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[1px] after:left-[1px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-2.5 after:w-2.5 after:transition-all peer-checked:bg-red-500"></div>
                            </div>
                        </label>
                    </div>

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
            <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar pb-24">
                {tree.length === 0 && (
                    <div className="text-center text-slate-400 text-xs mt-10 italic">
                        No content found.
                    </div>
                )}

                {tree.map((bu) => (
                    <BusinessUnitNode key={bu.name} node={bu} heatmapData={heatmapData} heatmapMode={heatmapMode} searchQuery={searchQuery} />
                ))}
            </div>

            {/* Selection Action Panel - Moved inside SourceBrowser */}
            <SidebarActionPanel />
        </div>
    );
};

const BusinessUnitNode: React.FC<{ node: CourseNode, heatmapData?: Record<string, { score: number, type: string }>, heatmapMode?: boolean, searchQuery?: string }> = ({ node, heatmapData, heatmapMode, searchQuery }) => {
    const [expanded, setExpanded] = useState(true);
    const { selectedSourceIds, selectMultiple, deselectMultiple } = useSelectionStore();

    // Determine if this BU has heat (sum of child courses)
    // We don't have course IDs at BU level easily unless we iterate children
    // Just pass data down. 

    // Optional: Highlight BU if it contains any heat?

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
                        <CourseItem key={course.id} course={course} heatmapData={heatmapData} heatmapMode={heatmapMode} searchQuery={searchQuery} />
                    ))}
                </div>
            )}
        </div>
    );
};

const CourseItem: React.FC<{ course: CourseNode, heatmapData?: Record<string, { score: number, type: string }>, heatmapMode?: boolean, searchQuery?: string }> = ({ course, heatmapData, heatmapMode, searchQuery }) => {
    const { selectedSourceIds, toggleSelection } = useSelectionStore();
    // If course has pre-loaded slides (from search), expand by default
    const preloadedSlides = (course as any).slides as SourceSlide[] | undefined;
    const [expanded, setExpanded] = useState(!!preloadedSlides);
    const [slides, setSlides] = useState<SourceSlide[]>(preloadedSlides || []);
    const [loading, setLoading] = useState(false);

    const isSelected = selectedSourceIds.has(course.id);

    // Heatmap Logic for Course
    const heat = heatmapData ? heatmapData[course.id] : undefined;
    const intensity = heat?.score || 0;

    // Styling based on Heat
    // If heatmapMode is on, gray out non-matches, highlight matches
    const containerClass = useMemo(() => {
        if (!heatmapMode) return "text-slate-600 hover:bg-slate-50";
        if (intensity > 0) {
            // Red-Orange-Yellow scale (matching Slide thresholds now that we use Max aggregation)
            if (intensity > 0.8) return "bg-red-100 text-red-900 border-l-4 border-red-500";
            if (intensity > 0.4) return "bg-orange-50 text-orange-900 border-l-4 border-orange-400";
            return "bg-yellow-50 text-yellow-800 border-l-4 border-yellow-400";
        }
        return "text-slate-300 opacity-50"; // Fade out irrelevant
    }, [heatmapMode, intensity]);

    useEffect(() => {
        // Reset slides if we are switching from search mode (where slides are preloaded) back to tree mode
        // In search mode, course.slides is populated. In default mode, it's undefined.
        if (preloadedSlides) {
            setSlides(preloadedSlides);
            setExpanded(true);
        } else {
            // Switching to default view.
            // If we were previously expanded with preloaded slides, we need to either:
            // 1. Clear slides and collapse (simple)
            // 2. Fetch slides for this course again (better UX but more requests)
            // Let's reset to empty so the user has to click to expand, ensuring correct data.
            // OR keep existing slides if they were manually fetched? 
            // The issue is `setTree` creates new object references for courses, so this component re-mounts or updates.
            // If course prop changes from "Search Course" to "Default Course", preloadedSlides becomes undefined.
            setSlides([]);
            setExpanded(false);
        }
    }, [preloadedSlides, course.id]); // Add course.id to force reset if course identity changes logically but not physically (React key)

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
                    // Override or merge classes
                    containerClass,
                    expanded && !heatmapMode ? "bg-brand-teal/5 text-brand-teal font-medium" : ""
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
                        <SlideRow key={slide.id} slide={slide} isHighlighted={false} heatmapData={heatmapData} heatmapMode={heatmapMode} searchQuery={searchQuery} />
                    ))}
                </div>
            )}
        </div>
    );
};

const SlideRow: React.FC<{ slide: SourceSlide, isHighlighted: boolean, heatmapData?: Record<string, { score: number, type: string }>, heatmapMode?: boolean, searchQuery?: string }> = ({ slide, isHighlighted, heatmapData, heatmapMode, searchQuery }) => {
    const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
        id: `source-${slide.id}`,
        data: { slide }
    });

    // Heatmap Logic
    const heat = heatmapData ? heatmapData[slide.id] : undefined;
    const intensity = heat?.score || 0;

    const heatmapClass = useMemo(() => {
        if (!heatmapMode) return "";
        if (intensity > 0) {
            // Orange scale for better visibility
            if (intensity > 0.8) return "border-orange-500 bg-orange-100 ring-1 ring-orange-500";
            if (intensity > 0.4) return "border-orange-300 bg-orange-50";
            return "border-orange-200 bg-orange-50/30";
        }
        // Fix: Don't grayscale internal content, just the container or handle opacity carefully
        // Actually, applying grayscale to the container affects images.
        // Let's use opacity but keep color if needed, or just reduce contrast.
        return "opacity-40 grayscale";
    }, [heatmapMode, intensity]);

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
                heatmapMode ? heatmapClass : ((isHighlighted || isActive) ? "border-brand-teal ring-1 ring-brand-teal/20" : "border-slate-100 hover:border-slate-300"),
                isDragging && "opacity-50",
                isActive && !heatmapMode && "bg-brand-teal/5"
            )}
        >
            {/* Thumbnail */
                /* Note: Removed grayscale from container to avoid blanking out images in some browsers if mixed with opacity. 
                   If images are blank, it might be opacity+grayscale interaction on the parent div affecting the img tag.
                   Let's apply grayscale only to the image wrapper if needed, or ensure opacity isn't too low. */
            }
            <div className={clsx(
                "w-12 h-9 bg-slate-100 rounded overflow-hidden flex-shrink-0 relative",
                // Optional: Grayscale the thumbnail specifically if low heat
                heatmapMode && intensity === 0 && "grayscale"
            )}>
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
                <div className={clsx("flex flex-wrap gap-1 mt-1", heatmapMode && intensity === 0 && "grayscale")}>
                    {([...(slide.concepts || [])])
                        .sort((a, b) => (b.salience || 0) - (a.salience || 0))
                        .slice(0, 6)
                        .map((c, i) => (
                            <span key={i} className={clsx(
                                "text-[9px] px-1.5 py-0.5 rounded truncate max-w-[100px] border flex items-center gap-1",
                                // Heatmap Logic: Highlight concept tag if it likely matches the search
                                // Simple heuristic: Check if search query is part of concept name
                                (heatmapMode && intensity > 0 && searchQuery && c.name.toLowerCase().includes(searchQuery.toLowerCase()))
                                    ? ((c.salience || 0) > 0.7
                                        ? "bg-red-100 text-red-700 border-red-300 font-medium ring-1 ring-red-200"
                                        : "bg-orange-100 text-orange-700 border-orange-300 font-medium ring-1 ring-orange-200")
                                    : "bg-slate-100 text-slate-500 border-slate-200"
                            )}>
                                <span className="truncate">{c.name}</span>
                                {c.salience !== undefined && (
                                    <span className={clsx(
                                        "font-mono text-[8px]",
                                        // Heatmap Mode: Only color red if this specific concept is a match
                                        // Otherwise default to slate (grayscale parent handles opacity)
                                        heatmapMode && intensity > 0
                                            ? (searchQuery && c.name.toLowerCase().includes(searchQuery.toLowerCase())
                                                ? (c.salience > 0.7 ? "text-red-600 font-bold" : "text-orange-500 font-medium") // Match: Red if high, Orange if low
                                                : "text-slate-500") // Non-Match: Force Slate
                                            : (c.salience > 0.7 ? "text-green-600 font-bold" : "text-slate-400")
                                    )}>
                                        {c.salience.toFixed(1)}
                                    </span>
                                )}
                            </span>
                        ))}
                    {(slide.concepts || []).length > 6 && (
                        <span className="text-[9px] text-slate-400 self-center pl-1">
                            +{(slide.concepts || []).length - 6}
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
};
