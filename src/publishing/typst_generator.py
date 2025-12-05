import re
from typing import List, Dict, Any

def sanitize_typst_string(text: str) -> str:
    """Escapes characters that might break Typst syntax."""
    if not text:
        return ""
    # Simple escape for now - expanding as needed
    return text.replace('"', '\\"')

def markdown_to_typst(markdown: str) -> str:
    """
    Naive Markdown to Typst converter.
    Replaces headers, lists, bold/italic text, and images.
    """
    if not markdown:
        return ""
    
    lines = markdown.split('\n')
    typst_lines = []
    
    for line in lines:
        # Check for markdown image: ![alt](url)
        # Convert to Typst image: #image("url", alt: "alt")
        line = re.sub(
            r'!\[([^\]]*)\]\(([^)]+)\)', 
            lambda m: f'#figure(\n  image("{m.group(2)}", width: 80%),\n  caption: [{m.group(1)}]\n)' if m.group(1) else f'#image("{m.group(2)}", width: 80%)',
            line
        )
        
        # Headers
        if line.startswith('# '):
            typst_lines.append(f"= {line[2:]}")
        elif line.startswith('## '):
            typst_lines.append(f"== {line[3:]}")
        elif line.startswith('### '):
            typst_lines.append(f"=== {line[4:]}")
        # Lists
        elif line.strip().startswith('- '):
            typst_lines.append(f"- {line.strip()[2:]}")
        elif re.match(r'^\d+\. ', line.strip()):
            typst_lines.append(f"+ {line.strip().split('. ', 1)[1]}")
        else:
            # Text formatting
            # Bold **text** -> *text*
            line = re.sub(r'\*\*(.*?)\*\*', r'*\1*', line)
            # Italic *text* -> _text_ (Typst uses _ for italic)
            # Need to be careful not to conflict with bold replacement if regex overlaps
            # Simplified: Assume MD uses * or _ for italic, but we just handle basic bold
            typst_lines.append(line)
            
    return '\n'.join(typst_lines)

def generate_typst_document(project_title: str, nodes: List[Dict[str, Any]]) -> str:
    """
    Generates a full Typst document string from the project structure.
    Images are converted to Typst image syntax.
    """
    
    header = f"""
#set page(paper: "us-letter")
#set text(font: "Linux Libertine", size: 11pt)
#set par(justify: true)

#align(center, text(17pt)[
  *{sanitize_typst_string(project_title)}*
])

#grid(
  columns: (1fr, 1fr),
  align(left)[
    Training Consolidation Workbench
  ],
  align(right)[
    #datetime.today().display()
  ]
)

#line(length: 100%)

"""
    
    body = []
    
    # Sort nodes by order
    # Assuming simple flat list with order for now, or we traverse hierarchy
    # The graph query returns flattened list, we might need to reconstruct hierarchy or just trust order
    # For now, just iterate in order.
    
    sorted_nodes = sorted(nodes, key=lambda x: x.get('order', 0))
    
    for node in sorted_nodes:
        title = node.get('title', 'Untitled Section')
        content = node.get('content_markdown', '')
        
        # Section Title
        body.append(f"= {title}\n")
        
        # Section Content
        if content:
            typst_content = markdown_to_typst(content)
            body.append(typst_content)
            body.append("\n")
        else:
            body.append("_No content available for this section._\n")
            
    return header + "\n".join(body)
