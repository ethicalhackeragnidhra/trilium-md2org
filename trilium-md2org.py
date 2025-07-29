#!/usr/bin/env python3
"""
Trilium Markdown to Org-mode converter
Preserves metadata and directory structure while converting content
"""

import sys
from pathlib import Path
import yaml
import pypandoc
import re
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def extract_metadata(text):
    """Extract YAML metadata from markdown file if present."""
    yaml_pattern = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
    match = yaml_pattern.match(text)
    
    if match:
        try:
            metadata = yaml.safe_load(match.group(1))
            content = text[match.end():]
            return metadata, content
        except yaml.YAMLError as e:
            logger.warning(f"YAML parsing error: {e}")
            return {}, text
    return {}, text

def format_org_metadata(metadata):
    """Convert metadata dictionary to Org-mode properties drawer format."""
    if not metadata:
        return ""
        
    lines = [":PROPERTIES:"]
    for key, value in metadata.items():
        # Handle lists/arrays
        if isinstance(value, list):
            value = " ".join(str(v) for v in value)
        # Handle dates
        elif isinstance(value, datetime):
            value = value.strftime("%Y-%m-%d %H:%M:%S")
        
        key = key.upper().replace(' ', '_')
        lines.append(f":{key}: {value}")
    lines.append(":END:\n")
    
    return "\n".join(lines)

def convert_file(md_path, org_path):
    """Convert a single markdown file to org format with metadata preservation."""
    logger.info(f"Converting: {md_path}")
    
    # Ensure parent directory exists
    org_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Read markdown file
        text = md_path.read_text(encoding='utf-8')
        
        # Extract and process metadata
        metadata, content = extract_metadata(text)
        
        # Convert markdown content to org using pandoc
        org_content = pypandoc.convert_text(
            content,
            'org',
            format='markdown',
            extra_args=['--wrap=none']
        )
        
        # Combine metadata and converted content
        final_content = format_org_metadata(metadata) + org_content
        
        # Write output
        org_path.write_text(final_content, encoding='utf-8')
        logger.info(f"Successfully converted to: {org_path}")
        
    except Exception as e:
        logger.error(f"Error processing {md_path}: {type(e).__name__}: {e}")
        raise

def main(src_root, dst_root):
    """Process all markdown files in source directory."""
    src = Path(src_root).expanduser()
    dst = Path(dst_root).expanduser()
    
    if not src.is_dir():
        logger.error(f"Source directory not found: {src}")
        sys.exit(1)
    
    # Create destination directory if needed
    dst.mkdir(parents=True, exist_ok=True)
    
    # Process all markdown files
    md_files = list(src.rglob('*.md'))
    logger.info(f"Found {len(md_files)} markdown files to process")
    
    for md in md_files:
        # Preserve directory structure
        rel_path = md.relative_to(src)
        org_path = dst / rel_path.with_suffix('.org')
        
        try:
            convert_file(md, org_path)
        except Exception as e:
            logger.error(f"Failed to convert {md}: {e}")
            continue

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: trilium_md2org.py <source-md-dir> <dest-org-dir>")
        sys.exit(1)
        
    main(sys.argv[1], sys.argv[2])
