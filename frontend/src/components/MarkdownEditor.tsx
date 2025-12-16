import React, { useEffect, useRef, useState } from 'react';
import { useEditor, EditorContent, ReactNodeViewRenderer, NodeViewWrapper } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import { Bold, Italic, List, ListOrdered, Heading2, Link as LinkIcon, Code, X } from 'lucide-react';
import clsx from 'clsx';
import { marked } from 'marked';
import TurndownService from 'turndown';
import { useLayout } from './LayoutContext';
import { api } from '../api';

// ... (other code)

interface MarkdownEditorProps {
    content: string;
    onSave: (markdown: string) => void;
    onJsonChange?: (json: any) => void; // Optional: export Tiptap JSON for spatial preview
}

// Configure marked v17 to properly render images and allow raw HTML
marked.use({
    // Allow raw HTML to pass through (for resized images saved as <img> tags)
    async: false,
    breaks: false,
    gfm: true,
    renderer: {
        image({ href, title, text }: { href: string; title: string | null; text: string }) {
            const titleAttr = title ? ` title="${title}"` : '';
            return `<img src="${href}" alt="${text}"${titleAttr} class="max-w-full h-auto rounded-lg shadow-sm my-2" />`;
        }
    }
});

// Enable HTML passthrough - raw <img> tags in markdown will render properly
// @ts-ignore - marked types may not include this but it works
marked.setOptions({
    // In marked v17, HTML is allowed by default, but we ensure it
});

// Initialize turndown for HTML to Markdown conversion
const turndownService = new TurndownService({
    headingStyle: 'atx',
    codeBlockStyle: 'fenced',
});

/**
 * Convert a presigned MinIO URL to a stable minio:// reference.
 * This prevents URLs from expiring in saved content.
 * 
 * Input:  http://localhost:9000/training-content/abc123/images/fig1.jpg?X-Amz-...
 * Output: minio://training-content/abc123/images/fig1.jpg
 */
const toStableUrl = (url: string): string => {
    try {
        // Check if it's already a stable URL
        if (url.startsWith('minio://')) return url;

        // Check if it's a presigned MinIO URL
        if (url.includes('X-Amz-') || url.includes('/training-content/') || url.includes('/published/')) {
            const parsed = new URL(url);
            // Remove query params (the signature) and convert to minio:// format
            const path = parsed.pathname.replace(/^\//, ''); // Remove leading slash
            return `minio://${path}`;
        }

        return url;
    } catch {
        return url;
    }
};

// Ensure turndown properly converts images back to markdown with stable URLs
turndownService.addRule('images', {
    filter: 'img',
    replacement: function (_content, node) {
        const img = node as HTMLImageElement;
        const alt = (img.alt || '').replace(/"/g, '&quot;'); // Escape quotes in ALT
        const rawSrc = img.src || '';
        const src = toStableUrl(rawSrc); // Convert to stable URL
        const title = (img.title || '').replace(/"/g, '&quot;'); // Escape quotes in TITLE
        const width = img.getAttribute('width');

        // If width is explicitly set (resized), enable HTML output to persist it
        if (width) {
            return `<img src="${src}" alt="${alt}" width="${width}"${title ? ` title="${title}"` : ''} />`;
        }

        // standard markdown fallback
        return `![${alt}](${src}${title ? ` "${title}"` : ''})`;
    }
});

// Custom Resizable Image Node View with Layout Role Selector
const ImageNodeView = (props: any) => {
    const { node, updateAttributes, deleteNode, selected } = props;
    const [resizing, setResizing] = useState(false);
    const [width, setWidth] = useState(node.attrs.width || '100%');
    const imgRef = useRef<HTMLImageElement>(null);
    const startXRef = useRef(0);
    const startWidthRef = useRef(0);

    // Get layout context for role options
    const { getLayoutRoles, currentLayout } = useLayout();
    const layoutRoles = getLayoutRoles();

    useEffect(() => {
        setWidth(node.attrs.width || '100%');
    }, [node.attrs.width]);

    const handleMouseDown = (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (!imgRef.current) return;

        setResizing(true);
        startXRef.current = e.clientX;
        startWidthRef.current = imgRef.current.offsetWidth;

        const handleMouseMove = (moveEvent: MouseEvent) => {
            if (resizing || startWidthRef.current) {
                const currentX = moveEvent.clientX;
                const diffX = currentX - startXRef.current;
                const newWidth = Math.max(50, startWidthRef.current + diffX); // Min width 50px
                setWidth(`${newWidth}px`);
            }
        };

        const handleMouseUp = (upEvent: MouseEvent) => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
            setResizing(false);

            // Commit the width change - explicitly preserve layoutRole
            const currentX = upEvent.clientX;
            const diffX = currentX - startXRef.current;
            const finalWidth = Math.max(50, startWidthRef.current + diffX);
            const currentLayoutRole = node.attrs.layoutRole || 'auto';
            updateAttributes({ width: `${finalWidth}px`, layoutRole: currentLayoutRole });
        };

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
    };
    // Destructure to exclude layoutRole from being spread to DOM
    const { layoutRole: _layoutRole, ...domAttrs } = node.attrs;

    return (
        <NodeViewWrapper className="relative inline-block group leading-none my-2 max-w-full">
            <div className="relative inline-block">
                <img
                    ref={imgRef}
                    src={domAttrs.src}
                    alt={domAttrs.alt || ''}
                    title={domAttrs.title || undefined}
                    style={{ ...domAttrs.style, width: width }}
                    className={clsx(
                        "max-w-full h-auto rounded-lg shadow-sm transition-shadow",
                        selected ? "ring-2 ring-brand-teal" : ""
                    )}
                />

                {/* Layout Role Selector - appears when selected */}
                {selected && (
                    <div className="absolute top-2 left-2 z-20">
                        <select
                            value={node.attrs.layoutRole || 'auto'}
                            onChange={(e) => updateAttributes({ layoutRole: e.target.value })}
                            className="text-xs px-2 py-1 bg-white/95 border border-slate-300 rounded shadow-md focus:outline-none focus:ring-1 focus:ring-brand-teal"
                            title={`Layout role for ${currentLayout} layout`}
                        >
                            {layoutRoles.map(role => (
                                <option key={role.value} value={role.value}>
                                    {role.label}
                                </option>
                            ))}
                        </select>
                    </div>
                )}

                {/* Resize Handle */}
                <div
                    onMouseDown={handleMouseDown}
                    className="absolute bottom-1 right-1 w-3 h-3 bg-brand-teal border border-white rounded-full cursor-nwse-resize opacity-0 group-hover:opacity-100 transition-opacity z-20 shadow-sm"
                    title="Resize image"
                />

                {/* Delete Button */}
                <button
                    onClick={() => deleteNode()}
                    className="absolute top-2 right-2 bg-white/90 p-1.5 rounded-full text-slate-500 hover:text-red-500 hover:bg-white shadow-md opacity-0 group-hover:opacity-100 transition-opacity z-10"
                    title="Remove image"
                    type="button"
                >
                    <X size={14} />
                </button>
            </div>
        </NodeViewWrapper>
    );
};

// ... (rest of imports)

// ... inside MarkdownEditor component ...

export const MarkdownEditor: React.FC<MarkdownEditorProps> = ({ content, onSave, onJsonChange }) => {
    const lastSavedContent = useRef(content);
    const [viewMode, setViewMode] = useState<'wysiwyg' | 'markdown'>('wysiwyg');
    const [markdownText, setMarkdownText] = useState(content);
    const [resolvedContent, setResolvedContent] = useState<string | null>(null);

    /**
     * Resolve minio:// URLs in markdown to fresh presigned URLs.
     * This is called when content is loaded to make images displayable.
     */
    const resolveMinioUrls = async (markdown: string): Promise<string> => {
        // Find all minio:// URLs in the content
        const minioUrlPattern = /minio:\/\/[^\s"')\]]+/g;
        const matches = markdown.match(minioUrlPattern);

        if (!matches || matches.length === 0) {
            return markdown;
        }

        // Deduplicate
        const uniqueUrls = [...new Set(matches)];

        try {
            // Resolve all URLs in one batch request
            const urlMap = await api.resolveImageUrls(uniqueUrls);

            // Replace all occurrences
            let resolved = markdown;
            for (const [stable, presigned] of Object.entries(urlMap)) {
                // Escape special regex chars in the stable URL
                const escaped = stable.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                resolved = resolved.replace(new RegExp(escaped, 'g'), presigned);
            }

            return resolved;
        } catch (e) {
            console.error('Failed to resolve minio URLs:', e);
            return markdown;
        }
    };

    // Resolve URLs when content prop changes
    useEffect(() => {
        let cancelled = false;

        const resolve = async () => {
            if (content) {
                const resolved = await resolveMinioUrls(content);
                if (!cancelled) {
                    setResolvedContent(resolved);
                }
            } else {
                setResolvedContent(content);
            }
        };

        resolve();

        return () => { cancelled = true; };
    }, [content]);

    const editor = useEditor({
        extensions: [
            StarterKit.configure({
                heading: {
                    levels: [1, 2, 3],
                },
            }),
            Placeholder.configure({
                placeholder: 'Start editing the synthesized content...',
            }),
            Link.configure({
                openOnClick: false,
            }),
            // Use extend to add React Node View and support width
            Image.extend({
                addAttributes() {
                    return {
                        src: { default: null },
                        alt: { default: null },
                        title: { default: null },
                        width: {
                            default: null,
                            parseHTML: element => element.getAttribute('width'),
                            renderHTML: attributes => {
                                if (!attributes.width) return {};
                                return { width: attributes.width };
                            }
                        },
                        layoutRole: {
                            default: 'auto',
                            parseHTML: element => element.getAttribute('data-layout-role') || 'auto',
                            renderHTML: attributes => {
                                if (!attributes.layoutRole || attributes.layoutRole === 'auto') return {};
                                return { 'data-layout-role': attributes.layoutRole };
                            }
                        },
                    };
                },
                addNodeView() {
                    return ReactNodeViewRenderer(ImageNodeView);
                },
            }).configure({
                inline: false,
                allowBase64: true,
            }),
        ],
        // Start empty - content will be set via useEffect once URLs are resolved
        content: '',
        editorProps: {
            attributes: {
                class: 'prose prose-sm max-w-none focus:outline-none min-h-[200px] p-3 overflow-x-hidden break-words',
                style: 'word-break: break-word; overflow-wrap: anywhere;',
            },
            handleDrop: (view, event, _slice, moved) => {
                // Handle dropped content - check if it's an image or image markdown
                if (!moved && event.dataTransfer) {
                    const text = event.dataTransfer.getData('text/plain');
                    const assetData = event.dataTransfer.getData('application/x-asset');

                    // Calculate the actual drop position from mouse coordinates
                    const coordinates = view.posAtCoords({ left: event.clientX, top: event.clientY });
                    const dropPos = coordinates ? coordinates.pos : view.state.selection.from;

                    // Check for our custom asset data (from AssetDrawer)
                    if (assetData) {
                        try {
                            const asset = JSON.parse(assetData);
                            if (asset.url) {
                                // Build alt text with optional size metadata
                                let altText = asset.filename || '';

                                // If we have bounding box and canvas dimensions, include them
                                if (asset.bbox && asset.canvas_width && asset.canvas_height) {
                                    const sizeInfo = {
                                        bw: Math.round(asset.bbox.width),
                                        bh: Math.round(asset.bbox.height),
                                        cw: Math.round(asset.canvas_width),
                                        ch: Math.round(asset.canvas_height)
                                    };
                                    altText = `${asset.filename}|${JSON.stringify(sizeInfo)}`;
                                }

                                // Insert as image node at drop position
                                const { schema } = view.state;
                                const node = schema.nodes.image.create({ src: asset.url, alt: altText });
                                const transaction = view.state.tr.insert(dropPos, node);
                                view.dispatch(transaction);
                                event.preventDefault();
                                return true;
                            }
                        } catch (e) {
                            console.error('Failed to parse asset data:', e);
                        }
                    }

                    // Check for markdown image syntax: ![alt](url)
                    const imageMarkdownMatch = text?.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
                    if (imageMarkdownMatch) {
                        const [, alt, url] = imageMarkdownMatch;
                        const { schema } = view.state;
                        const node = schema.nodes.image.create({ src: url, alt: alt || '' });
                        const transaction = view.state.tr.insert(dropPos, node);
                        view.dispatch(transaction);
                        event.preventDefault();
                        return true;
                    }
                }
                return false;
            },
        },
        onUpdate: ({ editor }) => {
            // Export Tiptap JSON for spatial preview (preserves layoutRole)
            // This must be called on EVERY update, not just markdown changes
            if (onJsonChange) {
                onJsonChange(editor.getJSON());
            }

            // Convert HTML back to markdown
            const html = editor.getHTML();
            const markdown = turndownService.turndown(html);

            // Only save to backend if content actually changed
            if (markdown !== lastSavedContent.current) {
                lastSavedContent.current = markdown;
                setMarkdownText(markdown);
                onSave(markdown);
            }
        },
    });

    // Track the last content we loaded into the editor (the prop value, not resolved)
    const lastLoadedContentRef = useRef<string | null>(null);

    // Update editor content when resolved content is ready or content prop changes
    useEffect(() => {
        if (!editor) return;

        // If we have resolved content and it's different from what we last loaded
        if (resolvedContent !== null && content !== lastLoadedContentRef.current) {
            const newHtml = marked.parse(resolvedContent || '') as string;
            editor.commands.setContent(newHtml);
            lastLoadedContentRef.current = content; // Track that we loaded this content
            lastSavedContent.current = content; // Track original content for save comparisons
            setMarkdownText(content); // Keep original (with minio://) for raw view
            console.log('[MarkdownEditor] Content updated from props');
        }
    }, [resolvedContent, editor, content]);

    if (!editor) {
        return <div className="p-4 text-slate-400 text-sm">Loading editor...</div>;
    }

    return (
        <div className="border border-slate-200 rounded-lg bg-white overflow-hidden">
            {/* Toolbar */}
            <div className="flex items-center justify-between gap-1 p-2 bg-slate-50 border-b border-slate-200 flex-wrap">
                <div className="flex items-center gap-1">
                    {viewMode === 'wysiwyg' && (
                        <>
                            <button
                                onClick={() => editor.chain().focus().toggleBold().run()}
                                className={clsx(
                                    'p-1.5 rounded hover:bg-slate-200 transition-colors',
                                    editor.isActive('bold') ? 'bg-slate-200 text-brand-teal' : 'text-slate-600'
                                )}
                                title="Bold (Ctrl+B)"
                            >
                                <Bold size={14} />
                            </button>
                            <button
                                onClick={() => editor.chain().focus().toggleItalic().run()}
                                className={clsx(
                                    'p-1.5 rounded hover:bg-slate-200 transition-colors',
                                    editor.isActive('italic') ? 'bg-slate-200 text-brand-teal' : 'text-slate-600'
                                )}
                                title="Italic (Ctrl+I)"
                            >
                                <Italic size={14} />
                            </button>
                            <div className="w-px h-4 bg-slate-300 mx-1" />
                            <button
                                onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
                                className={clsx(
                                    'p-1.5 rounded hover:bg-slate-200 transition-colors',
                                    editor.isActive('heading', { level: 2 }) ? 'bg-slate-200 text-brand-teal' : 'text-slate-600'
                                )}
                                title="Heading 2"
                            >
                                <Heading2 size={14} />
                            </button>
                            <div className="w-px h-4 bg-slate-300 mx-1" />
                            <button
                                onClick={() => editor.chain().focus().toggleBulletList().run()}
                                className={clsx(
                                    'p-1.5 rounded hover:bg-slate-200 transition-colors',
                                    editor.isActive('bulletList') ? 'bg-slate-200 text-brand-teal' : 'text-slate-600'
                                )}
                                title="Bullet List"
                            >
                                <List size={14} />
                            </button>
                            <button
                                onClick={() => editor.chain().focus().toggleOrderedList().run()}
                                className={clsx(
                                    'p-1.5 rounded hover:bg-slate-200 transition-colors',
                                    editor.isActive('orderedList') ? 'bg-slate-200 text-brand-teal' : 'text-slate-600'
                                )}
                                title="Ordered List"
                            >
                                <ListOrdered size={14} />
                            </button>
                            <div className="w-px h-4 bg-slate-300 mx-1" />
                            <button
                                onClick={() => {
                                    const url = window.prompt('Enter URL:');
                                    if (url) {
                                        editor.chain().focus().setLink({ href: url }).run();
                                    }
                                }}
                                className={clsx(
                                    'p-1.5 rounded hover:bg-slate-200 transition-colors',
                                    editor.isActive('link') ? 'bg-slate-200 text-brand-teal' : 'text-slate-600'
                                )}
                                title="Add Link"
                            >
                                <LinkIcon size={14} />
                            </button>
                        </>
                    )}
                </div>

                {/* Toggle between WYSIWYG and Markdown */}
                <button
                    onClick={() => setViewMode(viewMode === 'wysiwyg' ? 'markdown' : 'wysiwyg')}
                    className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-slate-600 hover:text-brand-teal hover:bg-slate-100 rounded transition-colors"
                    title={viewMode === 'wysiwyg' ? 'View Raw Markdown' : 'View Rich Editor'}
                >
                    <Code size={12} />
                    {viewMode === 'wysiwyg' ? 'View Markdown' : 'View Editor'}
                </button>
            </div>

            {/* Editor Content */}
            {viewMode === 'wysiwyg' ? (
                <EditorContent editor={editor} className="bg-white" />
            ) : (
                <textarea
                    value={markdownText}
                    onChange={(e) => {
                        const newMarkdown = e.target.value;
                        setMarkdownText(newMarkdown);

                        // Update TipTap editor with new markdown
                        const html = marked.parse(newMarkdown || '') as string;
                        editor.commands.setContent(html);

                        // Save
                        lastSavedContent.current = newMarkdown;
                        onSave(newMarkdown);
                    }}
                    className="w-full min-h-[200px] p-3 font-mono text-sm text-slate-700 bg-white focus:outline-none resize-none"
                    placeholder="Enter markdown here..."
                />
            )}
        </div>
    );
};
