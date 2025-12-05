import React, { useEffect, useState } from 'react';
import { Image, ChevronLeft, ChevronRight, GripVertical, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { api } from '../api';

interface EmbeddedImage {
    filename: string;
    url: string;
    size: number;
    bbox?: {
        x: number;
        y: number;
        width: number;
        height: number;
    };
    canvas_width?: number;
    canvas_height?: number;
    page_number?: number;
}

interface AssetDrawerProps {
    slideIds: string[];
    onInsert?: (url: string, filename: string) => void;
}

export const AssetDrawer: React.FC<AssetDrawerProps> = ({ slideIds, onInsert }) => {
    const scrollRef = React.useRef<HTMLDivElement>(null);
    const [showLeftArrow, setShowLeftArrow] = useState(false);
    const [showRightArrow, setShowRightArrow] = useState(true);
    const [images, setImages] = useState<EmbeddedImage[]>([]);
    const [loading, setLoading] = useState(false);

    // Fetch embedded images when slideIds change
    useEffect(() => {
        if (slideIds.length === 0) {
            setImages([]);
            return;
        }

        setLoading(true);
        api.getEmbeddedImagesForSlides(slideIds)
            .then(res => {
                setImages(res.images || []);
            })
            .catch(err => {
                console.error('Failed to fetch embedded images:', err);
                setImages([]);
            })
            .finally(() => setLoading(false));
    }, [slideIds]);

    const handleScroll = () => {
        if (!scrollRef.current) return;
        const { scrollLeft, scrollWidth, clientWidth } = scrollRef.current;
        setShowLeftArrow(scrollLeft > 0);
        setShowRightArrow(scrollLeft + clientWidth < scrollWidth - 10);
    };

    const scroll = (direction: 'left' | 'right') => {
        if (!scrollRef.current) return;
        const scrollAmount = 200;
        scrollRef.current.scrollBy({
            left: direction === 'left' ? -scrollAmount : scrollAmount,
            behavior: 'smooth'
        });
    };

    const handleDragStart = (e: React.DragEvent, image: EmbeddedImage) => {
        // Set data for drop into TipTap or other targets
        e.dataTransfer.setData('text/plain', `![${image.filename}](${image.url})`);
        e.dataTransfer.setData('application/x-asset', JSON.stringify(image));
        e.dataTransfer.effectAllowed = 'copy';
    };

    if (loading) {
        return (
            <div className="border-t border-slate-200 bg-slate-50/50 p-3">
                <div className="flex items-center gap-2 text-slate-400">
                    <Loader2 size={14} className="animate-spin" />
                    <span className="text-[10px]">Loading extracted assets...</span>
                </div>
            </div>
        );
    }

    if (images.length === 0) {
        return null; // Don't render if no assets
    }

    return (
        <div className="border-t border-slate-200 bg-slate-50/50 p-3 mt-4 rounded-b-lg">
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <Image size={14} className="text-slate-400" />
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                        Extracted Assets
                    </span>
                    <span className="text-[10px] text-slate-400">
                        ({images.length} images)
                    </span>
                </div>
                <span className="text-[10px] text-slate-400 italic">
                    Drag or click to insert
                </span>
            </div>

            {/* Scrollable Container */}
            <div className="relative">
                {/* Left Arrow */}
                {showLeftArrow && (
                    <button
                        onClick={() => scroll('left')}
                        className="absolute left-0 top-1/2 -translate-y-1/2 z-10 w-8 h-8 bg-white/90 border border-slate-200 rounded-full shadow-md flex items-center justify-center hover:bg-slate-50 transition-colors"
                    >
                        <ChevronLeft size={16} className="text-slate-600" />
                    </button>
                )}

                {/* Thumbnail Reel */}
                <div
                    ref={scrollRef}
                    onScroll={handleScroll}
                    className="flex gap-3 overflow-x-auto scrollbar-hide py-1 px-1"
                    style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
                >
                    {images.map((image, idx) => (
                        <div
                            key={`${image.filename}-${idx}`}
                            draggable
                            onDragStart={(e) => handleDragStart(e, image)}
                            onClick={() => onInsert?.(image.url, image.filename)}
                            className={clsx(
                                "flex-shrink-0 group relative cursor-grab active:cursor-grabbing",
                                "w-28 h-20 rounded-lg overflow-hidden border-2 border-slate-200",
                                "hover:border-brand-teal hover:shadow-lg transition-all",
                                "bg-white"
                            )}
                        >
                            <img
                                src={image.url}
                                alt={image.filename}
                                className="w-full h-full object-contain bg-white"
                                draggable={false}
                            />

                            {/* Filename Overlay */}
                            <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                                <div className="absolute bottom-1 left-1 right-1 flex items-center justify-between">
                                    <span className="text-[8px] text-white font-medium truncate px-1 max-w-[80%]">
                                        {image.filename}
                                    </span>
                                    <GripVertical size={10} className="text-white/80" />
                                </div>
                            </div>
                        </div>
                    ))}
                </div>

                {/* Right Arrow */}
                {showRightArrow && images.length > 3 && (
                    <button
                        onClick={() => scroll('right')}
                        className="absolute right-0 top-1/2 -translate-y-1/2 z-10 w-8 h-8 bg-white/90 border border-slate-200 rounded-full shadow-md flex items-center justify-center hover:bg-slate-50 transition-colors"
                    >
                        <ChevronRight size={16} className="text-slate-600" />
                    </button>
                )}
            </div>
        </div>
    );
};
