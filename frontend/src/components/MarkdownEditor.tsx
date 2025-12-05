import React, { useEffect, useRef, useState } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import { Bold, Italic, List, ListOrdered, Heading2, Link as LinkIcon, Code } from 'lucide-react';
import clsx from 'clsx';
import { marked } from 'marked';
import TurndownService from 'turndown';

interface MarkdownEditorProps {
    content: string;
    onSave: (markdown: string) => void;
}

// Configure marked v17 to properly render images using the new API
marked.use({
    renderer: {
        image({ href, title, text }: { href: string; title: string | null; text: string }) {
            const titleAttr = title ? ` title="${title}"` : '';
            return `<img src="${href}" alt="${text}"${titleAttr} class="max-w-full h-auto rounded-lg shadow-sm my-2" />`;
        }
    }
});

// Initialize turndown for HTML to Markdown conversion
const turndownService = new TurndownService({
    headingStyle: 'atx',
    codeBlockStyle: 'fenced',
});

// Ensure turndown properly converts images back to markdown
turndownService.addRule('images', {
    filter: 'img',
    replacement: function (content, node) {
        const img = node as HTMLImageElement;
        const alt = img.alt || '';
        const src = img.src || '';
        const title = img.title ? ` "${img.title}"` : '';
        return `![${alt}](${src}${title})`;
    }
});

export const MarkdownEditor: React.FC<MarkdownEditorProps> = ({ content, onSave }) => {
    const lastSavedContent = useRef(content);
    const [viewMode, setViewMode] = useState<'wysiwyg' | 'markdown'>('wysiwyg');
    const [markdownText, setMarkdownText] = useState(content);

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
            Image.configure({
                inline: false,
                allowBase64: true,
                HTMLAttributes: {
                    class: 'max-w-full h-auto rounded-lg shadow-sm my-2',
                },
            }),
        ],
        // Convert markdown to HTML for initial content
        content: marked.parse(content || '') as string,
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
            // Convert HTML back to markdown
            const html = editor.getHTML();
            const markdown = turndownService.turndown(html);

            // Only save if content actually changed
            if (markdown !== lastSavedContent.current) {
                lastSavedContent.current = markdown;
                setMarkdownText(markdown);
                onSave(markdown);
            }
        },
    });

    // Update editor content when prop changes externally
    useEffect(() => {
        if (editor && content !== lastSavedContent.current) {
            const html = marked.parse(content || '') as string;
            editor.commands.setContent(html);
            lastSavedContent.current = content;
            setMarkdownText(content);
        }
    }, [content, editor]);

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
