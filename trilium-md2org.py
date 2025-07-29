#!/usr/bin/env python3
import sys
from pathlib import Path
import yaml
import pypandoc
import re
import shutil
import logging
from urllib.parse import unquote
import hashlib
from datetime import datetime

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    filename='trilium_conversion.log'
)
logger = logging.getLogger(__name__)

class ConversionError(Exception):
    """Custom exception for conversion errors"""
    pass

DEFAULT_METADATA = {
    'title': '',
    'created': '',
    'modified': '',
    'type': 'note',
    'tags': []
}

def is_valid_file(filepath: Path) -> bool:
    """
    Validate if path is a file and has .md extension
    
    Args:
        filepath (Path): Path to check
        
    Returns:
        bool: True if valid markdown file, False otherwise
    """
    try:
        return filepath.is_file() and filepath.suffix.lower() == '.md'
    except Exception as e:
        logger.error(f"Error checking file validity for {filepath}: {e}")
        return False

def ensure_metadata(metadata: dict) -> dict:
    """
    Ensure all required metadata fields exist with proper typing
    
    Args:
        metadata (dict): Original metadata
        
    Returns:
        dict: Complete metadata with defaults
    """
    complete_metadata = DEFAULT_METADATA.copy()
    if isinstance(metadata, dict):
        # Type checking and conversion for each field
        for key, value in metadata.items():
            if key in complete_metadata:
                if isinstance(complete_metadata[key], list) and not isinstance(value, list):
                    value = [value] if value else []
                complete_metadata[key] = value
    return complete_metadata

def extract_metadata(text: str) -> tuple:
    """
    Extract YAML metadata with enhanced error handling
    
    Args:
        text (str): Input text content
        
    Returns:
        tuple: (metadata dict, remaining content)
    """
    yaml_pattern = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
    match = yaml_pattern.match(text)
    
    if not match:
        return {}, text
        
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
        if not isinstance(metadata, dict):
            metadata = {'content': str(metadata)}
        content = text[match.end():]
        return metadata, content
    except yaml.YAMLError as e:
        logger.warning(f"YAML parsing error: {e}")
        return {}, text

def format_org_metadata(metadata: dict) -> str:
    """
    Convert metadata to Org format with type safety
    
    Args:
        metadata (dict): Metadata to convert
        
    Returns:
        str: Formatted Org properties
    """
    if not isinstance(metadata, dict):
        return ""
        
    lines = [":PROPERTIES:"]
    for key, value in metadata.items():
        if value is None:
            continue
            
        try:
            if isinstance(value, (list, tuple)):
                value = " ".join(str(v) for v in value if v is not None)
            elif isinstance(value, datetime):
                value = value.strftime("%Y-%m-%d %H:%M:%S")
            else:
                value = str(value)
                
            if key and value:
                key = str(key).upper().replace(' ', '_')
                lines.append(f":{key}: {value}")
        except Exception as e:
            logger.warning(f"Error formatting metadata key {key}: {e}")
            
    lines.append(":END:\n")
    return "\n".join(lines)

def process_image_links(content: str, md_path: Path, org_path: Path, image_dir: Path) -> str:
    """
    Process and copy image files with enhanced error handling
    
    Args:
        content (str): Document content
        md_path (Path): Source markdown path
        org_path (Path): Destination org path
        image_dir (Path): Image directory path
        
    Returns:
        str: Updated content with processed image links
    """
    image_patterns = [
        r'!\[(.*?)\]\((.*?)\)',
        r'<img\s+src=[\'"]([^\'"]+)[\'"].*?>',
        r'\[\[(file:)?([^\]]+\.(png|jpg|jpeg|gif|svg))\]\]'
    ]
    
    def process_image(match):
        try:
            if len(match.groups()) == 2:
                alt_text, img_path = match.groups()
            else:
                img_path = match.group(1)
                alt_text = ""

            img_path = unquote(img_path)
            img_source = Path(img_path)
            if not img_source.is_absolute():
                img_source = md_path.parent / img_path

            if img_source.is_file():
                img_hash = hashlib.md5(str(img_source).encode()).hexdigest()[:8]
                new_filename = f"{img_hash}_{img_source.name}"
                new_img_path = image_dir / new_filename
                
                image_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(img_source, new_img_path)
                logger.info(f"Copied image: {img_source} -> {new_img_path}")
                
                rel_path = new_img_path.relative_to(org_path.parent)
                return f"[[file:{rel_path}][{alt_text}]]"
            else:
                logger.warning(f"Image not found: {img_source}")
                return match.group(0)
        except Exception as e:
            logger.error(f"Error processing image {match.group(0)}: {e}")
            return match.group(0)

    new_content = content
    for pattern in image_patterns:
        new_content = re.sub(pattern, process_image, new_content)
    
    return new_content

def convert_file(md_path: Path, org_path: Path) -> bool:
    """
    Convert markdown to org with comprehensive error handling
    
    Args:
        md_path (Path): Source markdown file path
        org_path (Path): Destination org file path
        
    Returns:
        bool: True if conversion successful, False otherwise
    """
    if not is_valid_file(md_path):
        logger.error(f"Invalid markdown file: {md_path}")
        return False
        
    try:
        # Create backup
        backup_path = md_path.with_suffix(md_path.suffix + '.bak')
        shutil.copy2(md_path, backup_path)
        
        # Setup image directory
        image_dir = org_path.parent / "images"
        
        # Read and process content
        text = md_path.read_text(encoding='utf-8')
        metadata, content = extract_metadata(text)
        metadata = ensure_metadata(metadata)
        
        # Process images and convert content
        content = process_image_links(content, md_path, org_path, image_dir)
        org_content = pypandoc.convert_text(
            content,
            'org',
            format='markdown-raw_html',
            extra_args=['--wrap=none']
        )
        
        # Write output file
        org_path.parent.mkdir(parents=True, exist_ok=True)
        final_content = format_org_metadata(metadata) + org_content
        org_path.write_text(final_content, encoding='utf-8')
        
        logger.info(f"Successfully converted: {org_path}")
        return True
        
        except Exception as e:
        logger.error(f"Error converting {md_path}: {e}")
        return False

def main(src_root: str, dst_root: str) -> None:
    """
    Main function to process all markdown files recursively
    
    Args:
        src_root (str): Source directory path
        dst_root (str): Destination directory path
    """
    try:
        src = Path(src_root).expanduser().resolve()
        dst = Path(dst_root).expanduser().resolve()
        
        if not src.is_dir():
            logger.error(f"Source directory not found: {src}")
            sys.exit(1)
            
        dst.mkdir(parents=True, exist_ok=True)
        
        # Find all markdown files recursively
        md_files = [f for f in src.rglob('*.md') if f.is_file()]
        total_files = len(md_files)
        
        if total_files == 0:
            logger.warning(f"No markdown files found in {src}")
            sys.exit(0)
            
        logger.info(f"Found {total_files} markdown files to process")
        success_count = 0
        
        # Process each file
        for md in md_files:
            try:
                rel_path = md.relative_to(src)
                org_path = dst / rel_path.with_suffix('.org')
                
                if convert_file(md, org_path):
                    success_count += 1
                    print(f"Progress: {success_count}/{total_files} files processed")
            
            except Exception as e:
                logger.error(f"Error processing {md}: {e}")
                
        # Final statistics
        logger.info(f"Conversion complete. Successfully converted {success_count}/{total_files} files")
        if success_count < total_files:
            logger.warning(f"Failed to convert {total_files - success_count} files. Check logs for details.")
            
    except KeyboardInterrupt:
        logger.info("Conversion interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python trilium-md2org.py <source_directory> <destination_directory>")
        sys.exit(1)
        
    main(sys.argv[1], sys.argv[2])
