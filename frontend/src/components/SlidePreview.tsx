import React from 'react';
import type { LayoutArchetype } from './LayoutContext';
import clsx from 'clsx';
import { marked } from 'marked';

interface TiptapNode {
    type: string;
    content?: TiptapNode[];
    attrs?: {
        src?: string;
        alt?: string;
        layoutRole?: string;
        [key: string]: any;
    };
    text?: string;
}

interface SlidePreviewProps {
    tiptapContent?: TiptapNode | null;
    markdown?: string | null;
    layoutArchetype: LayoutArchetype;
    title?: string;
}

// Helper to extract text content from Tiptap JSON
function extractText(node: TiptapNode): string {
    if (node.text) return node.text;
    if (!node.content) return '';
    return node.content.map(extractText).join('');
}

// Helper to extract all images from Tiptap JSON
function extractImages(node: TiptapNode): Array<{ src: string; alt: string; layoutRole: string }> {
    const images: Array<{ src: string; alt: string; layoutRole: string }> = [];

    if (node.type === 'image' && node.attrs?.src) {
        const layoutRole = node.attrs.layoutRole || 'auto';
        images.push({
            src: node.attrs.src,
            alt: node.attrs.alt || '',
            layoutRole: layoutRole,
        });
    }

    if (node.content) {
        node.content.forEach(child => {
            images.push(...extractImages(child));
        });
    }

    return images;
}

// Helper to render text paragraphs
function renderTextContent(node: TiptapNode): React.ReactNode[] {
    const elements: React.ReactNode[] = [];

    if (node.content) {
        node.content.forEach((child, idx) => {
            if (child.type === 'paragraph') {
                elements.push(
                    <p key={idx} className="text-sm text-slate-700 mb-2">
                        {extractText(child)}
                    </p>
                );
            } else if (child.type === 'bulletList') {
                elements.push(
                    <ul key={idx} className="list-disc list-inside text-sm text-slate-700 mb-2">
                        {child.content?.map((li, liIdx) => (
                            <li key={liIdx}>{extractText(li)}</li>
                        ))}
                    </ul>
                );
            } else if (child.type === 'heading') {
                const level = child.attrs?.level || 2;
                // Use explicit handling for heading types to avoid JSX type errors
                const headingClass = clsx(
                    "font-bold text-slate-800 mb-2",
                    level === 1 ? "text-xl" : level === 2 ? "text-lg" : "text-base"
                );
                if (level === 1) {
                    elements.push(<h1 key={idx} className={headingClass}>{extractText(child)}</h1>);
                } else if (level === 2) {
                    elements.push(<h2 key={idx} className={headingClass}>{extractText(child)}</h2>);
                } else {
                    elements.push(<h3 key={idx} className={headingClass}>{extractText(child)}</h3>);
                }
            }
        });
    }

    return elements;
}

// Documentary Layout - vertical stack
const DocumentaryLayout: React.FC<{ content?: TiptapNode; markdown?: string; title?: string }> = ({ content, markdown, title }) => {
    // If we have Tiptap content, use it; otherwise fall back to markdown
    if (content) {
        const textContent = renderTextContent(content);
        const images = extractImages(content);

        return (
            <div className="p-4 flex flex-col gap-2 bg-white h-full overflow-auto">
                {title && <h1 className="text-lg font-bold text-slate-800 border-b pb-2">{title}</h1>}
                <div className="flex-1">
                    {textContent}
                    {images.map((img, idx) => (
                        <img
                            key={idx}
                            src={img.src}
                            alt={img.alt}
                            className="w-1/2 mx-auto rounded-md shadow-sm my-2"
                        />
                    ))}
                </div>
            </div>
        );
    }

    // Markdown fallback
    return (
        <div className="p-4 flex flex-col gap-2 bg-white h-full overflow-auto">
            {title && <h1 className="text-lg font-bold text-slate-800 border-b pb-2">{title}</h1>}
            <div
                className="flex-1 prose prose-sm max-w-none text-slate-700"
                dangerouslySetInnerHTML={{ __html: marked.parse(markdown || '') as string }}
            />
        </div>
    );
};

// Split Layout - two columns
const SplitLayout: React.FC<{ content?: TiptapNode; markdown?: string; title?: string }> = ({ content, markdown, title }) => {
    if (content && content.content) {
        // Find the horizontal rule index to split content
        const hrIndex = content.content.findIndex(node => node.type === 'horizontalRule');

        let leftNodes: TiptapNode[];
        let rightNodes: TiptapNode[];

        if (hrIndex !== -1) {
            // Split at the horizontal rule
            leftNodes = content.content.slice(0, hrIndex);
            rightNodes = content.content.slice(hrIndex + 1);
        } else {
            // No horizontal rule - put all text on left, images on right
            leftNodes = content.content.filter(n => n.type !== 'image');
            rightNodes = content.content.filter(n => n.type === 'image');
        }

        // Create synthetic TipTap nodes for each column
        const leftContent: TiptapNode = { type: 'doc', content: leftNodes };
        const rightContent: TiptapNode = { type: 'doc', content: rightNodes };

        const leftText = renderTextContent(leftContent);
        const rightText = renderTextContent(rightContent);
        const leftImages = extractImages(leftContent);
        const rightImages = extractImages(rightContent);

        return (
            <div className="p-4 grid grid-cols-2 gap-4 h-full bg-white">
                {title && (
                    <div className="col-span-2 text-lg font-bold text-slate-800 border-b pb-2">
                        {title}
                    </div>
                )}
                <div className="bg-slate-50 p-3 rounded-md overflow-auto">
                    {leftText}
                    {leftImages.map((img, idx) => (
                        <img key={idx} src={img.src} alt={img.alt} className="w-full rounded-md shadow-sm my-2" />
                    ))}
                </div>
                <div className="bg-slate-100 p-3 rounded-md overflow-auto">
                    {rightText.length > 0 || rightImages.length > 0 ? (
                        <>
                            {rightText}
                            {rightImages.map((img, idx) => (
                                <img key={idx} src={img.src} alt={img.alt} className="max-w-full max-h-48 rounded-md shadow-sm" />
                            ))}
                        </>
                    ) : (
                        <span className="text-slate-400 text-xs italic">Right Column</span>
                    )}
                </div>
            </div>
        );
    }

    // Markdown fallback - split on --- separator (LLM-generated split marker)
    // Content before --- goes to left column, after --- goes to right column
    const mdContent = markdown || '';

    // Split on horizontal rule (--- on its own line)
    const parts = mdContent.split(/\n---+\n/);
    const leftContent = parts[0] || '';
    const rightContent = parts.slice(1).join('\n---\n') || ''; // Join remaining parts for right

    return (
        <div className="p-4 grid grid-cols-2 gap-4 h-full bg-white">
            {title && (
                <div className="col-span-2 text-lg font-bold text-slate-800 border-b pb-2">
                    {title}
                </div>
            )}
            <div className="bg-slate-50 p-3 rounded-md overflow-auto">
                <div
                    className="prose prose-sm max-w-none text-slate-700"
                    dangerouslySetInnerHTML={{ __html: marked.parse(leftContent) as string }}
                />
            </div>
            <div className="bg-slate-100 p-3 rounded-md overflow-auto">
                {rightContent ? (
                    <div
                        className="prose prose-sm max-w-none text-slate-700"
                        dangerouslySetInnerHTML={{ __html: marked.parse(rightContent) as string }}
                    />
                ) : (
                    <span className="text-slate-400 text-xs italic">Right column empty</span>
                )}
            </div>
        </div>
    );
};

// Grid Layout - 2x2 grid
const GridLayout: React.FC<{ content?: TiptapNode; markdown?: string; title?: string }> = ({ content, markdown, title }) => {
    if (content) {
        const textContent = renderTextContent(content);
        const images = extractImages(content);

        const slots = ['slot_1', 'slot_2', 'slot_3', 'slot_4'];
        const slotImages = slots.map(slot => images.find(i => i.layoutRole === slot));

        // Auto-assign images without explicit slot roles (including unrecognized roles from other layouts)
        const autoImages = images.filter(i => !slots.includes(i.layoutRole));
        slots.forEach((_slot, idx) => {
            if (!slotImages[idx] && autoImages.length > idx) {
                slotImages[idx] = autoImages[idx];
            }
        });

        return (
            <div className="p-4 flex flex-col h-full bg-white">
                {title && <div className="text-lg font-bold text-slate-800 border-b pb-2 mb-3">{title}</div>}
                <div className="grid grid-cols-2 grid-rows-2 gap-2 flex-1">
                    {slots.map((_slot, idx) => (
                        <div key={`slot-${idx}`} className="bg-slate-100 rounded-md flex items-center justify-center p-1 overflow-hidden">
                            {slotImages[idx] ? (
                                <img src={slotImages[idx]!.src} alt={slotImages[idx]!.alt} className="max-w-full max-h-full object-contain rounded" />
                            ) : (
                                <span className="text-slate-400 text-xs italic">Slot {idx + 1}</span>
                            )}
                        </div>
                    ))}
                </div>
                <div className="mt-2 text-xs text-slate-600">{textContent}</div>
            </div>
        );
    }

    // Markdown fallback
    return (
        <div className="p-4 flex flex-col h-full bg-white">
            {title && <div className="text-lg font-bold text-slate-800 border-b pb-2 mb-3">{title}</div>}
            <div className="grid grid-cols-2 grid-rows-2 gap-2 flex-1">
                {[1, 2, 3, 4].map(idx => (
                    <div key={`slot-${idx}`} className="bg-slate-100 rounded-md flex items-center justify-center p-1">
                        <span className="text-slate-400 text-xs italic">Slot {idx}</span>
                    </div>
                ))}
            </div>
            <div
                className="mt-2 prose prose-xs max-w-none text-slate-600"
                dangerouslySetInnerHTML={{ __html: marked.parse(markdown || '') as string }}
            />
        </div>
    );
};

// Hero Layout - full-bleed image with overlay
const HeroLayout: React.FC<{ content?: TiptapNode; markdown?: string; title?: string }> = ({ content, markdown, title }) => {
    if (content) {
        const textContent = renderTextContent(content);
        const images = extractImages(content);
        const backgroundImage = images.find(i => i.layoutRole === 'background') || images[0];

        return (
            <div className="relative h-full bg-slate-800 overflow-hidden">
                {backgroundImage && (
                    <img
                        src={backgroundImage.src}
                        alt={backgroundImage.alt}
                        className="absolute inset-0 w-full h-full object-cover opacity-60"
                    />
                )}
                <div className="relative z-10 p-4 h-full flex flex-col justify-end">
                    {title && <h1 className="text-xl font-bold text-white mb-2 drop-shadow-lg">{title}</h1>}
                    <div className="text-white/90 text-xs drop-shadow">
                        {textContent}
                    </div>
                </div>
                {!backgroundImage && (
                    <div className="absolute inset-0 flex items-center justify-center">
                        <span className="text-slate-400 text-xs italic">Add background image</span>
                    </div>
                )}
            </div>
        );
    }

    // Markdown fallback - hero with gradient background
    return (
        <div className="relative h-full bg-gradient-to-br from-slate-700 to-slate-900 overflow-hidden">
            <div className="relative z-10 p-4 h-full flex flex-col justify-end">
                {title && <h1 className="text-xl font-bold text-white mb-2 drop-shadow-lg">{title}</h1>}
                <div
                    className="text-white/90 text-xs drop-shadow prose prose-invert prose-xs"
                    dangerouslySetInnerHTML={{ __html: marked.parse(markdown || '') as string }}
                />
            </div>
        </div>
    );
};

export const SlidePreview: React.FC<SlidePreviewProps> = ({
    tiptapContent,
    markdown,
    layoutArchetype,
    title
}) => {
    // If no content at all, show placeholder
    if (!tiptapContent && !markdown) {
        return (
            <div className="h-full flex items-center justify-center bg-slate-100 rounded-lg">
                <span className="text-slate-400 text-sm">No content to preview</span>
            </div>
        );
    }

    // Pass content or markdown to layout components
    switch (layoutArchetype) {
        case 'split':
            return <SplitLayout content={tiptapContent || undefined} markdown={markdown || undefined} title={title} />;
        case 'grid':
            return <GridLayout content={tiptapContent || undefined} markdown={markdown || undefined} title={title} />;
        case 'hero':
            return <HeroLayout content={tiptapContent || undefined} markdown={markdown || undefined} title={title} />;
        case 'documentary':
        default:
            return <DocumentaryLayout content={tiptapContent || undefined} markdown={markdown || undefined} title={title} />;
    }
};

export default SlidePreview;
